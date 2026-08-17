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
                             limit: int = 50) -> dict:
    """
    Omzet/marge/afzet per categorie over de periode (alle of één categorie).

    Query-routing: periodes > BQ_HISTORICAL_THRESHOLD_DAYS worden transparant
    naar BigQuery gestuurd. Bij BQ-storing: fallback op PostgreSQL.
    """
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)

    # BigQuery-routing voor historische queries
    bq_cats = None
    bq_used = False
    if days > BQ_HISTORICAL_THRESHOLD_DAYS:
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
                        days: int = 30, shop_id: Optional[int] = None) -> dict:
    """Traffic/conversie (sessies, pageviews, orders, conversieratio)."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    since = date.today() - timedelta(days=days)
    q = db.query(
        func.coalesce(func.sum(models.FactTrafficDaily.sessions), 0),
        func.coalesce(func.sum(models.FactTrafficDaily.pageviews), 0),
        func.coalesce(func.sum(models.FactTrafficDaily.orders), 0),
        func.count(models.FactTrafficDaily.id),
    ).filter(models.FactTrafficDaily.date >= since)
    if entity_id:
        q = q.filter(models.FactTrafficDaily.entity_id == entity_id)
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
    }


def get_active_signals(db: Session, user: models.User, engine: Optional[str] = None,
                       severity: Optional[str] = None, entity_id: Optional[str] = None,
                       limit: int = 100, shop_id: Optional[int] = None) -> dict:
    """Actieve IntelligenceSignals, gefilterd op engine/severity/entiteit."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
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
    rows = q.order_by(desc(models.IntelligenceSignal.observed_at)).limit(limit).all()
    return {
        "shop_id": sid,
        "shop_scope_applied": True,
        "data_available": len(rows) > 0,
        "signals": [signal_to_dict(s) for s in rows],
    }


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
    ]
}
