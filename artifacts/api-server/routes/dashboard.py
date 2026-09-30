"""Dashboard KPI summary and chart data endpoints.

Ondersteunt de Global Filter Bar (taak #216): optionele `hierarchy_node_ids`
en `brands` query-parameters; parent-selectie telt server-side automatisch
alle descendants mee (zie routes/global_filters.py).
"""
import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models
import auth as auth_utils
from routes.global_filters import resolve_sku_filter

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/margin-insight")
def get_margin_insight(
    shop_id: int = Query(...),
    hierarchy_node_ids: Optional[str] = Query(None), brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None), sku_query: Optional[str] = Query(None),
    period_start: Optional[date] = Query(None), period_end: Optional[date] = Query(None),
    comparison_start: Optional[date] = Query(None), comparison_end: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    from services.product_identity import authorize_shop
    from services.margin_insight import insight
    authorize_shop(db, current_user, shop_id)
    scope = resolve_sku_filter(db, hierarchy_node_ids, brands, statuses, sku_query)
    return insight(db, shop_id, scope, period_start, period_end, comparison_start, comparison_end)


@router.post("/margin-recalculate", status_code=202)
def recalculate_margin(
    shop_id: int = Query(...), db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    from services.product_identity import authorize_shop
    from services.margin_insight import start_recalculation
    authorize_shop(db, current_user, shop_id)
    return start_recalculation(db, shop_id, current_user.username)

def _apply_sku_filter(q, col, sku_filter: Optional[set]):
    if sku_filter is None:
        return q
    return q.filter(col.in_(sku_filter))


def _dashboard_scope(db, user, shop_id, hierarchy_node_ids, brands, statuses, sku_query):
    from services.product_identity import authorize_shop
    authorize_shop(db, user, shop_id)
    selected = resolve_sku_filter(db, hierarchy_node_ids, brands, statuses, sku_query)
    shop_skus = {r[0] for r in db.query(models.DimProduct.sku_id).filter(models.DimProduct.shop_id == shop_id)}
    return shop_skus if selected is None else shop_skus & selected


def _operational_recommendations(q, shop_id):
    """Existing shop recommendations include decisions and regular engine output.

    DRS run provenance restricts monetary evidence, not the operational backlog:
    a running/failed DRS attempt must never hide valid recommendations.
    """
    return q.filter(models.FactPricingRecommendationDaily.shop_id == shop_id)


def _margin_snapshot(q, db, shop_id):
    """Only one DRS evidence snapshot; caller must separately verify freshness."""
    from services.margin_insight import latest_run
    R = models.FactPricingRecommendationDaily
    run = latest_run(db, shop_id)
    q = q.filter(R.shop_id == shop_id)
    if run:
        return q.filter(R.model_version == run.model_version,
                        R.id.in_((run.run_metadata or {}).get("recommendation_ids", [])))
    return q.filter(R.id.in_([]))


@router.get("/summary")
def get_dashboard_summary(
    shop_id: int = Query(1),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    logger.info("dashboard API started: /summary user_id=%s", current_user.id)
    R = models.FactPricingRecommendationDaily
    sku_filter = _dashboard_scope(db, current_user, shop_id, hierarchy_node_ids, brands, statuses, sku_query)

    recs = _apply_sku_filter(_operational_recommendations(db.query(R), shop_id), R.sku_id, sku_filter)

    total = recs.count()
    approved = recs.filter(R.approval_status == "approved").count()
    rejected = recs.filter(R.approval_status == "rejected").count()
    pending = recs.filter(R.approval_status == "pending").count()
    warnings = recs.filter(R.safety_status.in_(["warning", "blocked"])).count()

    def _agg(fn, col):
        q = _apply_sku_filter(_operational_recommendations(db.query(fn(col)), shop_id), R.sku_id, sku_filter)
        return q.scalar() or 0

    from services.margin_insight import insight, latest_run
    margin_evidence = insight(db, shop_id, sku_filter)
    margin_uplift = margin_evidence["expected"]["margin_uplift"]
    revenue_impact = margin_evidence["expected"]["revenue"]
    margin_impact = margin_evidence["expected"]["margin"]
    avg_conf = _agg(func.avg, R.confidence_score)

    last_run = latest_run(db, shop_id)

    # Data quality: % of SKUs with cost_price (binnen de actieve filtercontext)
    P = models.DimProduct
    prod_q = _apply_sku_filter(db.query(P), P.sku_id, sku_filter)
    total_skus = prod_q.count()
    skus_with_cost = prod_q.filter(P.cost_price.isnot(None)).count()
    dq_score = round(skus_with_cost / total_skus, 2) if total_skus > 0 else 1.0
    C = models.FactCompetitorPriceDaily
    total_competitor_prices = _apply_sku_filter(db.query(C).filter(C.shop_id == shop_id), C.sku_id, sku_filter).count()

    logger.info("dashboard API completed: /summary user_id=%s total_recs=%s", current_user.id, total)
    return {
        "total_margin_uplift": margin_uplift,
        "total_recommendations": total,
        "avg_confidence_score": round(float(avg_conf), 3),
        "safety_warnings_count": warnings,
        "approved_count": approved,
        "rejected_count": rejected,
        "pending_count": pending,
        "estimated_revenue_impact": revenue_impact,
        "estimated_margin_impact": margin_impact,
        "last_model_run": last_run.started_at.isoformat() if last_run else None,
        "model_version": last_run.model_version if last_run else "v1.0.0",
        "data_quality_score": dq_score,
        "total_skus": total_skus,
        "total_competitor_prices": total_competitor_prices,
    }


@router.get("/charts/margin-by-category")
def get_margin_by_category(
    shop_id: int = Query(1),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    R = models.FactPricingRecommendationDaily
    sku_filter = _dashboard_scope(db, current_user, shop_id, hierarchy_node_ids, brands, statuses, sku_query)
    from services.margin_insight import insight
    if insight(db, shop_id, sku_filter)["expected"]["status"] not in ("fresh", "partial"):
        return []
    q = (
        db.query(
            models.DimProduct.category,
            func.sum(R.expected_margin_uplift).label("margin_uplift"),
            func.count(R.id).label("recommendation_count"),
        )
        .join(models.DimProduct, R.sku_id == models.DimProduct.sku_id)
    )
    q = _apply_sku_filter(_margin_snapshot(q, db, shop_id), R.sku_id, sku_filter)
    q = q.filter(R.expected_margin_uplift.isnot(None), R.approval_status != "rejected",
                 R.override_price.is_(None), R.safety_status != "blocked")
    rows = (
        q.group_by(models.DimProduct.category)
        .order_by(func.sum(R.expected_margin_uplift).desc())
        .all()
    )
    return [
        {
            "category": r.category or "Uncategorized",
            "margin_uplift": round(float(r.margin_uplift or 0), 2),
            "recommendation_count": r.recommendation_count,
        }
        for r in rows
    ]


@router.get("/charts/recs-by-strategy")
def get_recs_by_strategy(
    shop_id: int = Query(1),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    R = models.FactPricingRecommendationDaily
    sku_filter = _dashboard_scope(db, current_user, shop_id, hierarchy_node_ids, brands, statuses, sku_query)
    q = db.query(
        R.strategy_type,
        func.count(R.id).label("count"),
        func.avg(R.confidence_score).label("avg_confidence"),
    )
    q = _apply_sku_filter(_operational_recommendations(q, shop_id), R.sku_id, sku_filter)
    rows = q.group_by(R.strategy_type).all()
    return [
        {
            "strategy_type": r.strategy_type or "UNKNOWN",
            "count": r.count,
            "avg_confidence": round(float(r.avg_confidence or 0), 3),
        }
        for r in rows
    ]


@router.get("/charts/confidence-distribution")
def get_confidence_distribution(
    shop_id: int = Query(1),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    R = models.FactPricingRecommendationDaily
    sku_filter = _dashboard_scope(db, current_user, shop_id, hierarchy_node_ids, brands, statuses, sku_query)
    buckets = [
        ("0-20%", 0, 0.2),
        ("20-40%", 0.2, 0.4),
        ("40-60%", 0.4, 0.6),
        ("60-80%", 0.6, 0.8),
        ("80-100%", 0.8, 1.01),
    ]
    result = []
    for label, low, high in buckets:
        q = db.query(R).filter(
            R.confidence_score >= low,
            R.confidence_score < high,
        )
        q = _apply_sku_filter(_operational_recommendations(q, shop_id), R.sku_id, sku_filter)
        result.append({"bucket": label, "count": q.count()})
    return result


@router.get("/charts/price-change-distribution")
def get_price_change_distribution(
    shop_id: int = Query(1),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    R = models.FactPricingRecommendationDaily
    sku_filter = _dashboard_scope(db, current_user, shop_id, hierarchy_node_ids, brands, statuses, sku_query)
    buckets = [
        ("<-5%", None, -5),
        ("-5% to -2%", -5, -2),
        ("-2% to 0%", -2, 0),
        ("0% (no change)", 0, 0.0001),
        ("0% to +2%", 0.0001, 2),
        ("+2% to +5%", 2, 5),
        (">+5%", 5, None),
    ]
    result = []
    for label, low, high in buckets:
        q = db.query(R)
        if low is not None:
            q = q.filter(R.recommended_change_pct >= low)
        if high is not None:
            q = q.filter(R.recommended_change_pct < high)
        q = _apply_sku_filter(_operational_recommendations(q, shop_id), R.sku_id, sku_filter)
        result.append({"bucket": label, "count": q.count()})
    return result
