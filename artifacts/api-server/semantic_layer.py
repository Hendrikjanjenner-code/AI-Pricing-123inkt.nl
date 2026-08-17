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
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

import models
from metrics import gross_margin, gross_margin_pct, asp, safe_div

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
    """Omzet, afzet, marge, ASP en voorraad voor één SKU over de periode."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    product = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == sku_id,
        models.DimProduct.shop_id == sid,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found in shop {sid}")

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
    revenue, cost, units, records = (row or (0, 0, 0, 0))

    return {
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
        "gross_margin": gross_margin(revenue, cost),
        "gross_margin_pct": gross_margin_pct(revenue, cost),
        "asp": asp(revenue, units),
        "current_price": float(product.current_price) if product.current_price is not None else None,
        "cost_price": float(product.cost_price) if product.cost_price is not None else None,
        "stock_quantity": product.stock_quantity,
    }


def get_category_performance(db: Session, user: models.User, category: Optional[str] = None,
                             days: int = 30, shop_id: Optional[int] = None,
                             limit: int = 50) -> dict:
    """Omzet/marge/afzet per categorie over de periode (alle of één categorie)."""
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
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

    return {
        "shop_id": sid,
        "shop_scope_applied": True,
        "period_days": days,
        "data_available": len(rows) > 0,
        "categories": [
            {
                "category": r.category,
                "revenue": float(r.revenue),
                "units_sold": int(r.units),
                "gross_margin": gross_margin(r.revenue, r.cost),
                "gross_margin_pct": gross_margin_pct(r.revenue, r.cost),
            }
            for r in rows
        ],
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
