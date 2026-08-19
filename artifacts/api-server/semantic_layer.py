"""
Semantic Layer (masterprompt §6): de enige goedgekeurde toegangslaag tot het
canonical commercial data model voor AI en cross-module analyses.

Elke functie:
- dwingt RBAC af (rol van de aanroepende gebruiker);
- respecteert shop-scope (default shop als geen shop_id is meegegeven);
- gebruikt de centrale metric-definities uit metrics.py;
- faalt veilig: geen data => lege/None-resultaten met 'data_available': False,
  nooit een crash (§56).

AI-componenten (Copilot, AI Gateway — latere taken) mogen uitsluitend deze
functies aanroepen, nooit vrije SQL.

Shop-scope model (bewuste keuze): het platform is single-tenant — alle
gebruikers horen bij dezelfde organisatie en mogen data van alle shops van die
organisatie zien. shop_id is een DIMENSIE (filter), geen tenancy-grens.
Per-gebruiker shop-membership hoort bij de latere multi-shop-configuratietaak.
Tabellen die (nog) geen shop_id-kolom hebben (scores, traffic) worden
organisatie-breed gequeryd; het teruggegeven shop_id geeft dan de gevraagde
scope aan, niet een afgedwongen filter.

Query-routing (BigQuery analytische laag):
  Queries met een periode > BQ_HISTORICAL_THRESHOLD_DAYS (standaard 90 dagen)
  worden transparant doorgestuurd naar BigQuery voor historische analyse.
  Als BigQuery niet beschikbaar is, valt de query terug op PostgreSQL en wordt
  'bq_fallback: true' gerapporteerd in het resultaat.
"""
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

import models
from metrics import gross_margin, gross_margin_pct, asp, safe_div

logger = logging.getLogger("uvicorn.error")

# Drempelwaarde (dagen): langere periodes worden naar BigQuery gerouteerd
BQ_HISTORICAL_THRESHOLD_DAYS = 90


def _bq_route_product_performance(
    project: str,
    dataset: str,
    sku_id: str,
    days: int,
    shop_id: int,
    db=None,
) -> Optional[dict]:
    """
    Historische productprestaties via BigQuery (>90 dagen).
    Geeft None terug als BigQuery niet bereikbaar is (PostgreSQL-fallback).
    """
    try:
        from bigquery.client import BigQueryClientWrapper
        from bigquery.cost_tracker import record_query_cost

        bq = BigQueryClientWrapper()
        if not bq.is_available():
            return None

        sql = f"""
            SELECT
                COALESCE(SUM(revenue), 0)    AS revenue,
                COALESCE(SUM(cost), 0)       AS cost,
                COALESCE(SUM(units_sold), 0) AS units_sold,
                COUNT(*)                     AS records
            FROM `{project}.{dataset}.fact_sales_daily`
            WHERE sku_id = @sku_id
              AND shop_id = @shop_id
              AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
        """
        from google.cloud.bigquery import ScalarQueryParameter, QueryJobConfig
        params = [
            ScalarQueryParameter("sku_id", "STRING", sku_id),
            ScalarQueryParameter("shop_id", "INT64", shop_id),
        ]
        rows, meta = bq.query(sql, params)
        record_query_cost("semantic_layer", "get_product_performance_bq",
                          meta["bytes_scanned"], meta["duration_ms"], meta["ok"], db)

        if not rows or not meta["ok"]:
            return None

        r = rows[0]
        revenue = float(r.get("revenue") or 0)
        cost = float(r.get("cost") or 0)
        units = int(r.get("units_sold") or 0)
        records = int(r.get("records") or 0)

        return {
            "revenue": revenue,
            "units_sold": units,
            "gross_margin": gross_margin(revenue, cost),
            "gross_margin_pct": gross_margin_pct(revenue, cost),
            "asp": asp(revenue, units),
            "records": records,
            "data_available": records > 0,
            "source": "bigquery",
        }
    except Exception as exc:
        logger.warning("BigQuery semantic routing fout (product perf): %s", exc)
        return None


def _bq_route_category_performance(
    project: str,
    dataset: str,
    days: int,
    shop_id: int,
    category: Optional[str],
    limit: int,
    db=None,
) -> Optional[list]:
    """Historische categorieprestaties via BigQuery."""
    try:
        from bigquery.client import BigQueryClientWrapper
        from bigquery.cost_tracker import record_query_cost

        bq = BigQueryClientWrapper()
        if not bq.is_available():
            return None

        cat_filter = "AND p.category = @category" if category else ""
        sql = f"""
            SELECT
                p.category,
                COALESCE(SUM(s.revenue), 0)    AS revenue,
                COALESCE(SUM(s.cost), 0)       AS cost,
                COALESCE(SUM(s.units_sold), 0) AS units
            FROM `{project}.{dataset}.fact_sales_daily` s
            JOIN `{project}.pricing_dims.dim_product` p USING (sku_id)
            WHERE s.shop_id = @shop_id
              AND s.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
              {cat_filter}
            GROUP BY p.category
            ORDER BY revenue DESC
            LIMIT {limit}
        """
        from google.cloud.bigquery import ScalarQueryParameter
        params = [ScalarQueryParameter("shop_id", "INT64", shop_id)]
        if category:
            params.append(ScalarQueryParameter("category", "STRING", category))

        rows, meta = bq.query(sql, params)
        record_query_cost("semantic_layer", "get_category_performance_bq",
                          meta["bytes_scanned"], meta["duration_ms"], meta["ok"], db)

        if not rows or not meta["ok"]:
            return None

        return [
            {
                "category": r["category"],
                "revenue": float(r["revenue"] or 0),
                "units_sold": int(r["units"] or 0),
                "gross_margin": gross_margin(r["revenue"], r["cost"]),
                "gross_margin_pct": gross_margin_pct(r["revenue"], r["cost"]),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("BigQuery semantic routing fout (categorie perf): %s", exc)
        return None


def _get_bq_project_dataset() -> tuple[str, str]:
    """Geef het BigQuery-project en facts-dataset terug."""
    try:
        from bigquery.client import get_bq_client
        client = get_bq_client()
        if client:
            return client.project or "", "pricing_facts"
    except Exception:
        pass
    return "", "pricing_facts"

ALL_ROLES = ("admin", "pricing_manager", "analyst", "viewer")
ANALYST_UP = ("admin", "pricing_manager", "analyst")


@dataclass(frozen=True)
class SemanticFunction:
    name: str
    description: str
    required_roles: tuple
    fn: Callable


def _check_access(user: models.User, required_roles: tuple) -> None:
    if user is None or user.role not in required_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions for this data")


def _hierarchy_scope(
    db: Session, hierarchy_node_ids: Optional[list]
) -> tuple[Optional[set], Optional[dict]]:
    """Vertaal hierarchy-node-ids naar (sku_set, scope-beschrijving).

    Descendant-inclusief via het gematerialiseerde pad (zelfde semantiek als
    de Global Filter Context). Geen node-ids => (None, None) = geen filter.
    Een geldige selectie zonder producten geeft een LEGE set (≠ None), zodat
    de functie eerlijk 'geen data binnen deze scope' rapporteert.
    """
    if not hierarchy_node_ids:
        return None, None
    node_ids = [int(n) for n in hierarchy_node_ids]
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    nodes = db.query(N).filter(N.id.in_(node_ids)).all()
    scope = {
        "node_ids": [n.id for n in nodes],
        "paths": [(n.path_names or n.name) for n in nodes],
        "includes_descendants": True,
    }
    conds = [N.path.like(n.path + "%") for n in nodes if n.path]
    if not conds:
        scope["descendant_node_ids"] = [n.id for n in nodes]
        return set(), scope
    from sqlalchemy import or_
    all_node_ids = [r[0] for r in db.query(N.id).filter(or_(*conds)).all()]
    # Descendant-node-ids ook in de scope: filters op node-niveau (bv.
    # categoriesignalen met hierarchy_node_id) moeten dezelfde
    # descendant-semantiek volgen als het SKU-filter.
    scope["descendant_node_ids"] = sorted(set(all_node_ids) | {n.id for n in nodes})
    rows = (db.query(A.sku_id)
            .filter(A.node_id.in_(all_node_ids), A.status == "active")
            .distinct().all())
    return {r[0] for r in rows}, scope


# ─── Department-aware prioritering van signalen ─────────────────────────────
# Trefwoorden per afdeling: signalen waarvan engine/signal_type een eerder
# trefwoord bevat, krijgen voorrang. "Wat vraagt vandaag aandacht?" geeft zo
# per afdeling andere prioriteiten (pricing vs. SEO vs. inkoop).
DEPARTMENT_SIGNAL_PRIORITIES: dict[str, list[str]] = {
    "pricing": ["pricing", "price", "prijs", "margin", "marge", "competition",
                "concurrent", "elastic"],
    "seo": ["traffic", "seo", "search", "conversie", "conversion", "promotion",
            "promotie"],
    "inkoop": ["procurement", "supplier", "leverancier", "inkoop", "cost",
               "kostprijs"],
    "supply_chain": ["supply", "stock", "voorraad", "levertijd", "lead_time"],
    "catman": ["assortiment", "category", "categorie", "private_label",
               "huismerk", "switch"],
    "finance": ["margin", "marge", "cost", "kosten", "budget"],
    "data_bi": ["data", "quality", "kwaliteit"],
    "management": [],
}

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "warning": 2,
                  "low": 3, "info": 4}


def _department_priority_rank(department: str, signal: "models.IntelligenceSignal") -> int:
    keywords = DEPARTMENT_SIGNAL_PRIORITIES.get(department, [])
    haystack = f"{signal.engine or ''} {signal.signal_type or ''}".lower()
    for i, kw in enumerate(keywords):
        if kw in haystack:
            return i
    return len(keywords) + 1


def _shop_scope(db: Session, shop_id: Optional[int]) -> int:
    """Bepaal de effectieve shop-scope; valt terug op de default shop."""
    if shop_id is not None:
        exists = db.query(models.DimShop.id).filter(models.DimShop.id == shop_id).first()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Shop {shop_id} not found")
        return shop_id
    shop = db.query(models.DimShop).filter(models.DimShop.is_default.is_(True)).first()
    if shop:
        return shop.id
    any_shop = db.query(models.DimShop).order_by(models.DimShop.id).first()
    return any_shop.id if any_shop else 1


def get_product_performance(db: Session, user: models.User, sku_id: str,
                            days: int = 30, shop_id: Optional[int] = None) -> dict:
    """
    Omzet, afzet, marge, ASP en voorraad voor één SKU over de periode.

    Query-routing: periodes > BQ_HISTORICAL_THRESHOLD_DAYS worden transparant
    naar BigQuery gestuurd. Bij BQ-storing: fallback op PostgreSQL.
    """
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    product = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == sku_id,
        models.DimProduct.shop_id == sid,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found in shop {sid}")

    # BigQuery-routing voor historische queries
    bq_data = None
    bq_used = False
    if days > BQ_HISTORICAL_THRESHOLD_DAYS:
        project, dataset = _get_bq_project_dataset()
        if project:
            bq_data = _bq_route_product_performance(project, dataset, sku_id, days, sid, db)
            bq_used = bq_data is not None

    if bq_data:
        revenue = bq_data["revenue"]
        cost = 0.0  # BQ-query retourneert geen cost apart; margin berekend via bq_data
        units = bq_data["units_sold"]
        records = bq_data["records"]
        gross_margin_val = bq_data.get("gross_margin", 0)
        gross_margin_pct_val = bq_data.get("gross_margin_pct", 0)
    else:
        since = date.today() - timedelta(days=days)
        row = db.query(
            func.coalesce(func.sum(models.FactSalesDaily.revenue), 0),
            func.coalesce(func.sum(models.FactSalesDaily.cost), 0),
            func.coalesce(func.sum(models.FactSalesDaily.units_sold), 0),
            func.count(models.FactSalesDaily.id),
        ).filter(
            models.FactSalesDaily.sku_id == sku_id,
            models.FactSalesDaily.date >= since,
            models.FactSalesDaily.shop_id == sid,
        ).first()
        row = row or (0, 0, 0, 0)
        revenue, cost, units, records = row
        gross_margin_val = gross_margin(revenue, cost)
        gross_margin_pct_val = gross_margin_pct(revenue, cost)

    result = {
        "sku_id": sku_id,
        "product_name": product.product_name,
        "category": product.category,
        "brand": product.brand,
        "shop_id": sid,
        "shop_scope_applied": True,
        "period_days": days,
        "data_available": records > 0,
        "records": records,
        "revenue": float(revenue or 0),
        "units_sold": int(units or 0),
        "gross_margin": gross_margin_val,
        "gross_margin_pct": gross_margin_pct_val,
        "asp": asp(revenue, units),
        "current_price": float(product.current_price) if product.current_price is not None else None,
        "cost_price": float(product.cost_price) if product.cost_price is not None else None,
        "stock_quantity": product.stock_quantity,
        "data_source": "bigquery" if bq_used else "postgresql",
        "bq_fallback": (days > BQ_HISTORICAL_THRESHOLD_DAYS and not bq_used),
    }
    return result


def get_category_performance(db: Session, user: models.User, category: Optional[str] = None,
                             days: int = 30, shop_id: Optional[int] = None,
                             limit: int = 50,
                             hierarchy_node_ids: Optional[list] = None) -> dict:
    """
    Omzet/marge/afzet per categorie over de periode (alle of één categorie).

    Query-routing: periodes > BQ_HISTORICAL_THRESHOLD_DAYS worden transparant
    naar BigQuery gestuurd. Bij BQ-storing: fallback op PostgreSQL.
    """
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    sku_scope, hierarchy_scope = _hierarchy_scope(db, hierarchy_node_ids)

    # BigQuery-routing voor historische queries. Bij een actieve
    # hiërarchie-scope blijven we op PostgreSQL: de BQ-query kent de centrale
    # hiërarchie(-assignments) niet en zou de scope stil negeren.
    bq_cats = None
    bq_used = False
    if days > BQ_HISTORICAL_THRESHOLD_DAYS and sku_scope is None:
        project, dataset = _get_bq_project_dataset()
        if project:
            bq_cats = _bq_route_category_performance(project, dataset, days, sid, category, limit, db)
            bq_used = bq_cats is not None

    if bq_used:
        cats = bq_cats
    else:
        since = date.today() - timedelta(days=days)
        q = db.query(
            models.DimProduct.category,
            func.coalesce(func.sum(models.FactSalesDaily.revenue), 0).label("revenue"),
            func.coalesce(func.sum(models.FactSalesDaily.cost), 0).label("cost"),
            func.coalesce(func.sum(models.FactSalesDaily.units_sold), 0).label("units"),
        ).join(
            models.FactSalesDaily, models.FactSalesDaily.sku_id == models.DimProduct.sku_id
        ).filter(
            models.FactSalesDaily.date >= since,
            models.FactSalesDaily.shop_id == sid,
            models.DimProduct.shop_id == sid,
        )
        if category:
            q = q.filter(models.DimProduct.category == category)
        if sku_scope is not None:
            q = q.filter(models.FactSalesDaily.sku_id.in_(sku_scope))
        rows = q.group_by(models.DimProduct.category).order_by(desc("revenue")).limit(limit).all()
        cats = [
            {
                "category": r.category,
                "revenue": float(r.revenue),
                "units_sold": int(r.units),
                "gross_margin": gross_margin(r.revenue, r.cost),
                "gross_margin_pct": gross_margin_pct(r.revenue, r.cost),
            }
            for r in rows
        ]

    return {
        "shop_id": sid,
        "shop_scope_applied": True,
        "period_days": days,
        "data_available": len(cats) > 0,
        "categories": cats,
        "hierarchy_scope": hierarchy_scope,
        "data_source": "bigquery" if bq_used else "postgresql",
        "bq_fallback": (days > BQ_HISTORICAL_THRESHOLD_DAYS and not bq_used),
    }


def get_competitor_ranking(db: Session, user: models.User, sku_id: Optional[str] = None,
                           limit: int = 20, shop_id: Optional[int] = None) -> dict:
    """Concurrent-invloed (CIS): ranking van concurrenten, totaal of per SKU."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)

    latest = db.query(func.max(models.CompetitorInfluenceScore.run_date)).scalar()
    if not latest:
        return {"shop_id": sid, "shop_scope_applied": False, "data_available": False, "competitors": []}

    q = db.query(
        models.CompetitorInfluenceScore.competitor_name,
        func.avg(models.CompetitorInfluenceScore.cis_score).label("avg_cis"),
        func.avg(models.CompetitorInfluenceScore.csrs_score).label("avg_csrs"),
        func.count(models.CompetitorInfluenceScore.id).label("sku_count"),
    ).filter(models.CompetitorInfluenceScore.run_date == latest)
    if sku_id:
        q = q.filter(models.CompetitorInfluenceScore.sku_id == sku_id)
    rows = q.group_by(models.CompetitorInfluenceScore.competitor_name)\
            .order_by(desc("avg_cis")).limit(limit).all()

    return {
        "shop_id": sid,
        # Bronscores hebben (nog) geen shop_id-kolom: organisatie-breed.
        "shop_scope_applied": False,
        "run_date": str(latest),
        "sku_id": sku_id,
        "data_available": len(rows) > 0,
        "competitors": [
            {
                "rank": i + 1,
                "competitor_name": r.competitor_name,
                "influence_score": round(float(r.avg_cis or 0), 2),
                "stock_reliability_score": round(float(r.avg_csrs or 0), 2),
                "sku_count": int(r.sku_count),
            }
            for i, r in enumerate(rows)
        ],
    }


def get_price_position(db: Session, user: models.User, sku_id: str,
                       shop_id: Optional[int] = None) -> dict:
    """Prijspositie t.o.v. concurrentie (PCIS, prijsindex, referentieprijs)."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    score = db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.sku_id == sku_id
    ).order_by(desc(models.SkuCompetitionScore.run_date)).first()
    if not score:
        return {"sku_id": sku_id, "shop_id": sid, "shop_scope_applied": False, "data_available": False}
    return {
        "sku_id": sku_id,
        "shop_id": sid,
        # sku_competition_score heeft (nog) geen shop_id-kolom.
        "shop_scope_applied": False,
        "data_available": True,
        "run_date": str(score.run_date),
        "pcis_score": score.pcis_score,
        "competition_class": score.competition_class,
        # price_index = eigen / concurrent: <1.0 goedkoper, >1.0 duurder
        "price_index": score.price_index,
        "reference_price": float(score.reference_price) if score.reference_price is not None else None,
        "competitors_used": score.competitors_used,
    }


def get_customer_switching(db: Session, user: models.User, sku_id: Optional[str] = None,
                           limit: int = 50, shop_id: Optional[int] = None) -> dict:
    """Interne overstap A-merk → huismerk (ISV) — alleen analist en hoger."""
    _check_access(user, ANALYST_UP)
    sid = _shop_scope(db, shop_id)
    latest = db.query(func.max(models.InternalCompetitionScore.run_date)).scalar()
    if not latest:
        return {"shop_id": sid, "shop_scope_applied": False, "data_available": False, "pairs": []}

    q = db.query(models.InternalCompetitionScore).filter(
        models.InternalCompetitionScore.run_date == latest
    )
    if sku_id:
        q = q.filter(models.InternalCompetitionScore.sku_id == sku_id)
    rows = q.order_by(desc(models.InternalCompetitionScore.isv)).limit(limit).all()

    return {
        "shop_id": sid,
        "shop_scope_applied": False,
        "run_date": str(latest),
        "data_available": len(rows) > 0,
        "pairs": [
            {
                "a_brand_sku": r.sku_id,
                "private_label_sku": r.paired_sku_id,
                "switch_probability": r.internal_switch_probability,
                "margin_gap": r.internal_margin_gap,
                "isv": r.isv,
                "recommended_action": r.recommended_internal_action,
            }
            for r in rows
        ],
    }


def get_traffic_summary(db: Session, user: models.User, entity_id: Optional[str] = None,
                        days: int = 30, shop_id: Optional[int] = None,
                        hierarchy_node_ids: Optional[list] = None) -> dict:
    """Traffic/conversie (sessies, pageviews, orders, conversieratio)."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    sku_scope, hierarchy_scope = _hierarchy_scope(db, hierarchy_node_ids)
    since = date.today() - timedelta(days=days)
    q = db.query(
        func.coalesce(func.sum(models.FactTrafficDaily.sessions), 0),
        func.coalesce(func.sum(models.FactTrafficDaily.pageviews), 0),
        func.coalesce(func.sum(models.FactTrafficDaily.orders), 0),
        func.count(models.FactTrafficDaily.id),
    ).filter(models.FactTrafficDaily.date >= since)
    if entity_id:
        q = q.filter(models.FactTrafficDaily.entity_id == entity_id)
    if sku_scope is not None:
        # Hiërarchie-scope werkt op SKU-niveau: alleen per-SKU trafficrijen.
        q = q.filter(models.FactTrafficDaily.entity_type == "SKU",
                     models.FactTrafficDaily.entity_id.in_(sku_scope))
    sessions, pageviews, orders, records = q.first() or (0, 0, 0, 0)
    conv = safe_div(orders, sessions)
    return {
        "shop_id": sid,
        # fact_traffic_daily heeft (nog) geen shop_id-kolom.
        "shop_scope_applied": False,
        "period_days": days,
        "entity_id": entity_id,
        "data_available": records > 0,
        "sessions": int(sessions or 0),
        "pageviews": int(pageviews or 0),
        "orders": int(orders or 0),
        "conversion_rate_pct": round(conv * 100, 2) if conv is not None else None,
        "hierarchy_scope": hierarchy_scope,
    }


def get_active_signals(db: Session, user: models.User, engine: Optional[str] = None,
                       severity: Optional[str] = None, entity_id: Optional[str] = None,
                       limit: int = 100, shop_id: Optional[int] = None,
                       hierarchy_node_ids: Optional[list] = None,
                       department: Optional[str] = None) -> dict:
    """Actieve IntelligenceSignals, gefilterd op engine/severity/entiteit.

    `hierarchy_node_ids`: beperk tot signalen binnen de hiërarchie-scope
    (SKU-signalen via de actieve assignments, node-signalen via node-id).
    `department`: server-side geïnjecteerde afdelingscode van de gebruiker —
    signalen die bij het werkveld van de afdeling horen komen bovenaan
    ("Wat vraagt vandaag aandacht?" per afdeling anders geprioriteerd).
    """
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    sku_scope, hierarchy_scope = _hierarchy_scope(db, hierarchy_node_ids)
    q = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.status == "active",
        models.IntelligenceSignal.shop_id == sid,
    )
    if engine:
        q = q.filter(models.IntelligenceSignal.engine == engine)
    if severity:
        q = q.filter(models.IntelligenceSignal.severity == severity)
    if entity_id:
        q = q.filter(models.IntelligenceSignal.entity_id == entity_id)
    if sku_scope is not None:
        # Node-signalen (bv. categorieniveau) matchen op descendant-node-ids:
        # zelfde descendant-semantiek als het SKU-filter.
        node_ids = set((hierarchy_scope or {}).get("descendant_node_ids") or [])
        q = q.filter(
            models.IntelligenceSignal.entity_id.in_(sku_scope) |
            models.IntelligenceSignal.hierarchy_node_id.in_(node_ids)
        )
    rows = q.order_by(desc(models.IntelligenceSignal.observed_at)).limit(limit).all()
    department_priority_applied = False
    if department and department in DEPARTMENT_SIGNAL_PRIORITIES:
        department_priority_applied = True
        rows.sort(key=lambda s: (
            _department_priority_rank(department, s),
            _SEVERITY_RANK.get((s.severity or "info").lower(), 5),
        ))
    return {
        "shop_id": sid,
        "shop_scope_applied": True,
        "data_available": len(rows) > 0,
        "hierarchy_scope": hierarchy_scope,
        "department_priority_applied": department if department_priority_applied else None,
        "signals": [signal_to_dict(s) for s in rows],
    }


def get_margin_erosion(db: Session, user: models.User, days: int = 30,
                       limit: int = 20, shop_id: Optional[int] = None,
                       hierarchy_node_ids: Optional[list] = None) -> dict:
    """Waar verliezen we marge: grootste margedalers t.o.v. de vorige periode."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    sku_scope, hierarchy_scope = _hierarchy_scope(db, hierarchy_node_ids)
    today = date.today()
    cur_since = today - timedelta(days=days)
    prev_since = today - timedelta(days=days * 2)

    def _margin_by_sku(start, end):
        q = db.query(
            models.FactSalesDaily.sku_id,
            func.coalesce(func.sum(models.FactSalesDaily.margin), 0).label("margin"),
            func.coalesce(func.sum(models.FactSalesDaily.revenue), 0).label("revenue"),
            func.count(models.FactSalesDaily.id).label("records"),
        ).filter(
            models.FactSalesDaily.shop_id == sid,
            models.FactSalesDaily.date >= start,
            models.FactSalesDaily.date < end,
        )
        if sku_scope is not None:
            q = q.filter(models.FactSalesDaily.sku_id.in_(sku_scope))
        rows = q.group_by(models.FactSalesDaily.sku_id).all()
        return {r.sku_id: r for r in rows}

    cur = _margin_by_sku(cur_since, today + timedelta(days=1))
    prev = _margin_by_sku(prev_since, cur_since)
    records = sum(int(r.records) for r in cur.values())

    losers = []
    for sku, c in cur.items():
        p = prev.get(sku)
        prev_margin = float(p.margin) if p else 0.0
        delta = float(c.margin) - prev_margin
        if delta < 0:
            losers.append({"sku_id": sku, "margin_current": round(float(c.margin), 2),
                           "margin_previous": round(prev_margin, 2),
                           "margin_delta": round(delta, 2),
                           "revenue_current": round(float(c.revenue), 2)})
    losers.sort(key=lambda x: x["margin_delta"])
    losers = losers[:limit]
    names = {p.sku_id: p.product_name for p in db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.in_([l["sku_id"] for l in losers])).all()} if losers else {}
    for l in losers:
        l["product_name"] = names.get(l["sku_id"])
    return {
        "shop_id": sid, "shop_scope_applied": True, "period_days": days,
        "comparison": f"laatste {days} dagen vs. {days} dagen daarvoor",
        "data_available": len(losers) > 0, "records": records,
        "hierarchy_scope": hierarchy_scope,
        "margin_losers": losers,
    }


def get_private_label_potential(db: Session, user: models.User, limit: int = 20,
                                shop_id: Optional[int] = None,
                                hierarchy_node_ids: Optional[list] = None) -> dict:
    """Huismerkpotentie: top-SKU's op Private Label Value Score (PLSV)."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    sku_scope, hierarchy_scope = _hierarchy_scope(db, hierarchy_node_ids)
    # FactPrivateLabelIntelligence heeft geen shop_id; scope via de SKU's
    # van de shop (DimProduct) zodat geen cross-shop-data lekt.
    shop_skus = db.query(models.DimProduct.sku_id).filter(
        models.DimProduct.shop_id == sid)
    latest_q = db.query(func.max(models.FactPrivateLabelIntelligence.run_date)).filter(
        models.FactPrivateLabelIntelligence.sku_id.in_(shop_skus))
    if sku_scope is not None:
        latest_q = latest_q.filter(
            models.FactPrivateLabelIntelligence.sku_id.in_(sku_scope))
    latest = latest_q.scalar()
    if not latest:
        return {"shop_id": sid, "shop_scope_applied": True, "data_available": False,
                "records": 0, "hierarchy_scope": hierarchy_scope, "items": []}
    q = db.query(models.FactPrivateLabelIntelligence).filter(
        models.FactPrivateLabelIntelligence.run_date == latest,
        models.FactPrivateLabelIntelligence.sku_id.in_(shop_skus),
    )
    if sku_scope is not None:
        q = q.filter(models.FactPrivateLabelIntelligence.sku_id.in_(sku_scope))
    rows = q.order_by(desc(models.FactPrivateLabelIntelligence.private_label_value_score)).limit(limit).all()
    return {
        "shop_id": sid, "shop_scope_applied": True, "run_date": str(latest),
        "hierarchy_scope": hierarchy_scope,
        "data_available": len(rows) > 0, "records": len(rows),
        "items": [{
            "sku_id": r.sku_id,
            "private_label_value_score": r.private_label_value_score,
            "private_label_class": r.private_label_class,
            "strategic_priority": r.strategic_priority,
            "internal_substitution_score": r.internal_substitution_score,
            "internal_margin_gap": r.internal_margin_gap,
            "a_brand_sku": r.a_brand_sku,
            "paired_sku_name": r.paired_sku_name,
        } for r in rows],
    }


def get_promotion_effectiveness(db: Session, user: models.User, limit: int = 20,
                                shop_id: Optional[int] = None,
                                hierarchy_node_ids: Optional[list] = None) -> dict:
    """Welke promotie werkte het best: gemeten promotie-effecten (§19)."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    sku_scope, hierarchy_scope = _hierarchy_scope(db, hierarchy_node_ids)
    latest = db.query(func.max(models.FactPromotionEffect.run_date)).filter(
        models.FactPromotionEffect.shop_id == sid).scalar()
    if not latest:
        return {"shop_id": sid, "shop_scope_applied": True, "data_available": False,
                "hierarchy_scope": hierarchy_scope, "promotions": []}
    q = db.query(models.FactPromotionEffect).filter(
        models.FactPromotionEffect.shop_id == sid,
        models.FactPromotionEffect.run_date == latest,
    )
    if sku_scope is not None:
        q = q.filter(models.FactPromotionEffect.sku_id.in_(sku_scope))
    rows = q.order_by(desc(models.FactPromotionEffect.incremental_margin)).limit(limit).all()
    return {
        "shop_id": sid, "shop_scope_applied": True, "run_date": str(latest),
        "hierarchy_scope": hierarchy_scope,
        "data_available": len(rows) > 0, "records": len(rows),
        "promotions": [{
            "promotion_id": r.promotion_id, "sku_id": r.sku_id,
            "period": f"{r.period_start} t/m {r.period_end}",
            "uplift_pct": r.uplift_pct, "net_uplift_pct": r.net_uplift_pct,
            "incremental_revenue": float(r.incremental_revenue) if r.incremental_revenue is not None else None,
            "incremental_margin": float(r.incremental_margin) if r.incremental_margin is not None else None,
            "cannibalization_pct": r.cannibalization_pct, "halo_pct": r.halo_pct,
            "control_group_used": r.control_group_used,
            "verdict": r.verdict, "confidence": r.confidence,
            "explanation": r.explanation_nl,
        } for r in rows],
    }


def get_supplier_risk(db: Session, user: models.User, limit: int = 20,
                      shop_id: Optional[int] = None,
                      hierarchy_node_ids: Optional[list] = None) -> dict:
    """Supplier-/inkooprisico: procurement-forecast met margedrukscores."""
    _check_access(user, ANALYST_UP)
    sid = _shop_scope(db, shop_id)
    sku_scope, hierarchy_scope = _hierarchy_scope(db, hierarchy_node_ids)
    # FactProcurementForecastDaily heeft geen shop_id; scope via de SKU's
    # van de shop (DimProduct) zodat geen cross-shop-data lekt.
    shop_skus = db.query(models.DimProduct.sku_id).filter(
        models.DimProduct.shop_id == sid)
    latest_q = db.query(func.max(models.FactProcurementForecastDaily.date)).filter(
        models.FactProcurementForecastDaily.sku_id.in_(shop_skus))
    if sku_scope is not None:
        latest_q = latest_q.filter(
            models.FactProcurementForecastDaily.sku_id.in_(sku_scope))
    latest = latest_q.scalar()
    if not latest:
        return {"shop_id": sid, "shop_scope_applied": True, "data_available": False,
                "records": 0, "hierarchy_scope": hierarchy_scope, "items": []}
    q = db.query(models.FactProcurementForecastDaily).filter(
        models.FactProcurementForecastDaily.date == latest,
        models.FactProcurementForecastDaily.sku_id.in_(shop_skus),
    )
    if sku_scope is not None:
        q = q.filter(models.FactProcurementForecastDaily.sku_id.in_(sku_scope))
    rows = q.order_by(desc(models.FactProcurementForecastDaily.future_margin_risk_score)).limit(limit).all()
    return {
        "shop_id": sid, "shop_scope_applied": True, "run_date": str(latest),
        "hierarchy_scope": hierarchy_scope,
        "data_available": len(rows) > 0, "records": len(rows),
        "items": [{
            "sku_id": r.sku_id, "sku_name": r.sku_name, "category": r.category,
            "future_margin_risk_score": r.future_margin_risk_score,
            "procurement_opportunity_score": r.procurement_opportunity_score,
            "price_change_pct_30d": r.price_change_pct_30d,
            "price_change_pct_90d": r.price_change_pct_90d,
            "lead_time_days": r.lead_time_days,
            "current_stock_days": r.current_stock_days,
            "signal_code": r.signal_code,
            "recommended_action": r.recommended_action_nl,
        } for r in rows],
    }


def get_opportunities(db: Session, user: models.User, limit: int = 20,
                      shop_id: Optional[int] = None,
                      hierarchy_node_ids: Optional[list] = None) -> dict:
    """Top-opportunities uit de centrale Opportunity Engine (§24)."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    sku_scope, hierarchy_scope = _hierarchy_scope(db, hierarchy_node_ids)
    q = db.query(models.Opportunity).filter(
        models.Opportunity.shop_id == sid,
        models.Opportunity.status == "open",
    )
    if sku_scope is not None:
        q = q.filter(models.Opportunity.entity_id.in_(sku_scope))
    rows = q.order_by(desc(models.Opportunity.priority_score)).limit(limit).all()
    return {
        "shop_id": sid, "shop_scope_applied": True,
        "hierarchy_scope": hierarchy_scope,
        "data_available": len(rows) > 0, "records": len(rows),
        "opportunities": [{
            "id": r.id, "type": r.opportunity_type, "source_engine": r.source_engine,
            "entity_id": r.entity_id, "entity_name": r.entity_name,
            "title": r.title_nl, "explanation": r.explanation_nl,
            "expected_value_eur": float(r.expected_value_eur) if r.expected_value_eur is not None else None,
            "confidence": r.confidence, "urgency": r.urgency,
            "effort": r.effort, "risk": r.risk,
            "priority_score": r.priority_score,
        } for r in rows],
    }


def simulate_price_change(db: Session, user: models.User, sku_id: str,
                          change_pct: float, shop_id: Optional[int] = None) -> dict:
    """
    What-if: geschatte impact van een prijswijziging (bv. +3% = 0.03) op
    units/omzet/marge via de Decision Engine-impactlogica en elasticiteit.
    Alleen een simulatie — voert NOOIT een prijswijziging uit (§64.7).
    """
    _check_access(user, ANALYST_UP)
    sid = _shop_scope(db, shop_id)
    if change_pct is None or abs(change_pct) > 0.5:
        raise HTTPException(status_code=400, detail="change_pct moet tussen -0.5 en 0.5 liggen")
    product = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == sku_id,
        models.DimProduct.shop_id == sid,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found in shop {sid}")

    from engine.decision_engine import _build_context, _impact_for_price_change, IMPACT_HORIZON_DAYS
    ctx, gaps = _build_context(db, sid, sku_id, [], product)
    units, revenue, margin, calcs, assumptions = _impact_for_price_change(ctx, change_pct)

    base_units = ctx.get("base_units")
    base_revenue = ctx.get("base_revenue")
    base_margin = ctx.get("base_margin")
    return {
        "sku_id": sku_id, "product_name": product.product_name,
        "shop_id": sid, "shop_scope_applied": True,
        "change_pct": change_pct,
        "horizon_days": IMPACT_HORIZON_DAYS,
        "data_available": units is not None,
        "records": ctx.get("sales_days") or 0,
        "current_price": ctx.get("current_price"),
        "new_price": round(ctx["current_price"] * (1 + change_pct), 4) if ctx.get("current_price") else None,
        "elasticity_used": ctx.get("elasticity"),
        "baseline": {"units": base_units, "revenue": base_revenue, "margin": base_margin},
        "simulated": {
            "units": round(units, 1) if units is not None else None,
            "revenue": round(revenue, 2) if revenue is not None else None,
            "margin": round(margin, 2) if margin is not None else None,
        },
        "delta": {
            "units": round(units - base_units, 1) if units is not None and base_units is not None else None,
            "revenue": round(revenue - base_revenue, 2) if revenue is not None and base_revenue is not None else None,
            "margin": round(margin - base_margin, 2) if margin is not None and base_margin is not None else None,
        },
        "calculations": calcs,
        "assumptions": assumptions,
        "data_gaps": gaps,
        "note": "Simulatie — er wordt geen prijswijziging uitgevoerd of klaargezet.",
    }


def simulate_competitor_scenario(db: Session, user: models.User, sku_id: str,
                                 change_pct: float,
                                 assume_follow: Optional[list] = None,
                                 assume_no_follow: Optional[list] = None,
                                 shop_id: Optional[int] = None) -> dict:
    """
    Multi-concurrent what-if: eigen prijswijziging met per-concurrent volgkans
    (op basis van herkende strategie), effect op prijsindex/afzet/marge.
    Alleen simulatie — voert NOOIT een prijswijziging uit.
    """
    _check_access(user, ANALYST_UP)
    sid = _shop_scope(db, shop_id)
    product = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == sku_id,
        models.DimProduct.shop_id == sid,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found in shop {sid}")
    from engine.competition_simulation import simulate_competitor_scenario as _sim
    out = _sim(db, sku_id, change_pct,
               assume_follow=assume_follow, assume_no_follow=assume_no_follow,
               shop_id=sid)
    out["shop_id"] = sid
    out["shop_scope_applied"] = True
    return out


def signal_to_dict(s: models.IntelligenceSignal) -> dict:
    return {
        "id": s.id,
        "shop_id": s.shop_id,
        "engine": s.engine,
        "signal_type": s.signal_type,
        "severity": s.severity,
        "direction": s.direction,
        "entity_type": s.entity_type,
        "entity_id": s.entity_id,
        "entity_name": s.entity_name,
        "metric": s.metric,
        "current_value": s.current_value,
        "previous_value": s.previous_value,
        "expected_value": s.expected_value,
        "change_pct": s.change_pct,
        "confidence": s.confidence,
        "explanation": s.explanation,
        "evidence": s.evidence,
        "sources": s.sources,
        "suggested_action": s.suggested_action,
        "observed_at": str(s.observed_at) if s.observed_at else None,
        "valid_until": str(s.valid_until) if s.valid_until else None,
        "model_version": s.model_version,
        "status": s.status,
    }


# Concurrentprofiel-functies (taak #249): implementaties in
# semantic_layer_competitor.py; registratie in hetzelfde gesloten register.
from semantic_layer_competitor import (  # noqa: E402
    get_competitor_business_profile, get_competitor_company_size,
    get_competitor_geographic_presence, get_competitor_fulfilment_profile,
    get_competitor_financial_health, get_competitor_procurement_power,
    get_competitor_market_roles, get_competitor_corporate_structure,
    get_competitor_evolution, compare_competitor_profiles,
    get_competitor_future_threats, get_competitor_profile_quality,
)

# Register van goedgekeurde functies. De AI Gateway (latere taak) gebruikt dit
# register als de volledige, gesloten lijst van toegestane data-toegangen.
SEMANTIC_FUNCTIONS: dict[str, SemanticFunction] = {
    f.name: f for f in [
        SemanticFunction(
            "get_product_performance",
            "Omzet, afzet, marge, ASP en voorraad voor één SKU over een periode.",
            ALL_ROLES, get_product_performance),
        SemanticFunction(
            "get_category_performance",
            "Omzet, marge en afzet per categorie over een periode.",
            ALL_ROLES, get_category_performance),
        SemanticFunction(
            "get_competitor_ranking",
            "Ranking van concurrenten op invloedscore (CIS), totaal of per SKU.",
            ALL_ROLES, get_competitor_ranking),
        SemanticFunction(
            "get_price_position",
            "Prijspositie van een SKU t.o.v. de concurrentie (PCIS, prijsindex).",
            ALL_ROLES, get_price_position),
        SemanticFunction(
            "get_customer_switching",
            "Interne overstapanalyse A-merk naar huismerk (ISV).",
            ANALYST_UP, get_customer_switching),
        SemanticFunction(
            "get_traffic_summary",
            "Traffic- en conversiesamenvatting (sessies, pageviews, orders).",
            ALL_ROLES, get_traffic_summary),
        SemanticFunction(
            "get_active_signals",
            "Actieve Intelligence Signals, gefilterd op engine/severity/entiteit.",
            ALL_ROLES, get_active_signals),
        SemanticFunction(
            "get_margin_erosion",
            "Waar verliezen we marge: grootste margedalers t.o.v. de vorige periode.",
            ALL_ROLES, get_margin_erosion),
        SemanticFunction(
            "get_private_label_potential",
            "Huismerkpotentie per SKU (PLSV, klasse, strategische prioriteit).",
            ALL_ROLES, get_private_label_potential),
        SemanticFunction(
            "get_promotion_effectiveness",
            "Gemeten promotie-effecten: uplift, incrementele marge, verdict.",
            ALL_ROLES, get_promotion_effectiveness),
        SemanticFunction(
            "get_supplier_risk",
            "Supplier-/inkooprisico: margedruk en inkoopkansen per SKU.",
            ANALYST_UP, get_supplier_risk),
        SemanticFunction(
            "get_opportunities",
            "Top-opportunities uit de centrale Opportunity Engine.",
            ALL_ROLES, get_opportunities),
        SemanticFunction(
            "simulate_price_change",
            "What-if-simulatie: impact van een prijswijziging op units/omzet/marge.",
            ANALYST_UP, simulate_price_change),
        SemanticFunction(
            "simulate_competitor_scenario",
            "Multi-concurrent what-if: prijswijziging met volgkans per concurrent "
            "(op basis van strategie), effect op prijsindex, afzet en marge.",
            ANALYST_UP, simulate_competitor_scenario),
        # ── Concurrentprofiel (taak #249) ──────────────────────────────
        SemanticFunction(
            "get_competitor_business_profile",
            "Volledig bedrijfsprofiel van één concurrent (juridische naam, KvK, "
            "oprichtingsjaar, size class, ranges, ownership, HQ) met per veld "
            "informatielaag, confidence en bron.",
            ALL_ROLES, get_competitor_business_profile),
        SemanticFunction(
            "get_competitor_company_size",
            "Bedrijfsomvang per concurrent (size class, employee-/revenue-range, "
            "geografische schaal), filterbaar — bv. grote internationale spelers.",
            ALL_ROLES, get_competitor_company_size),
        SemanticFunction(
            "get_competitor_geographic_presence",
            "Actieve landen per concurrent (webshop/operationeel), filterbaar op "
            "land, met informatielaag en confidence.",
            ALL_ROLES, get_competitor_geographic_presence),
        SemanticFunction(
            "get_competitor_fulfilment_profile",
            "Fulfilmentprofiel per concurrent (voorraadmodel, dropship-aandeel, "
            "levertijd); met dropship_only alleen dropshipspelers.",
            ALL_ROLES, get_competitor_fulfilment_profile),
        SemanticFunction(
            "get_competitor_financial_health",
            "Financiële gezondheid per concurrent: score/status + onderliggende "
            "observaties per boekjaar, incl. relevantie voor ons.",
            ANALYST_UP, get_competitor_financial_health),
        SemanticFunction(
            "get_competitor_procurement_power",
            "Procurement Power-ranking van concurrenten uit de laatste "
            "scoringsrun; NULL-scores zijn expliciet unknown.",
            ANALYST_UP, get_competitor_procurement_power),
        SemanticFunction(
            "get_competitor_market_roles",
            "Actieve marktrollen (Competition DNA) per concurrent, filterbaar "
            "op rol, met validatiestatus.",
            ALL_ROLES, get_competitor_market_roles),
        SemanticFunction(
            "get_competitor_corporate_structure",
            "Corporate relaties per concurrent en groepsvorming: welke "
            "concurrenten delen dezelfde (ultimate) parent.",
            ALL_ROLES, get_competitor_corporate_structure),
        SemanticFunction(
            "get_competitor_evolution",
            "Evolution-timeline van één concurrent: profielwijzigingen met "
            "datum, bron en oud/nieuw.",
            ALL_ROLES, get_competitor_evolution),
        SemanticFunction(
            "compare_competitor_profiles",
            "Vergelijk 2–5 concurrenten zij-aan-zij op omvang, fulfilment, "
            "financiën, procurement power, threat, rollen en relevantie.",
            ALL_ROLES, compare_competitor_profiles),
        SemanticFunction(
            "get_competitor_future_threats",
            "Future-threat-ranking (afgeleid signaal) van concurrenten met "
            "onderliggende factoren.",
            ANALYST_UP, get_competitor_future_threats),
        SemanticFunction(
            "get_competitor_profile_quality",
            "Betrouwbaarheid van concurrentprofielen: kwaliteitsvlaggen, "
            "freshness, lage confidence, ontbrekende bronnen en welke "
            "profielen opnieuw gecontroleerd moeten worden.",
            ALL_ROLES, get_competitor_profile_quality),
    ]
}
