"""Dashboard KPI summary and chart data endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    recs = db.query(models.FactPricingRecommendationDaily)

    total = recs.count()
    approved = recs.filter(models.FactPricingRecommendationDaily.approval_status == "approved").count()
    rejected = recs.filter(models.FactPricingRecommendationDaily.approval_status == "rejected").count()
    pending = recs.filter(models.FactPricingRecommendationDaily.approval_status == "pending").count()
    warnings = recs.filter(models.FactPricingRecommendationDaily.safety_status.in_(["warning", "blocked"])).count()

    margin_uplift = db.query(func.sum(models.FactPricingRecommendationDaily.expected_margin_uplift)).scalar() or 0
    revenue_impact = db.query(func.sum(models.FactPricingRecommendationDaily.expected_revenue)).scalar() or 0
    margin_impact = db.query(func.sum(models.FactPricingRecommendationDaily.expected_margin)).scalar() or 0
    avg_conf = db.query(func.avg(models.FactPricingRecommendationDaily.confidence_score)).scalar() or 0

    last_run = db.query(models.ModelRun).order_by(models.ModelRun.started_at.desc()).first()

    # Data quality: % of SKUs with cost_price
    total_skus = db.query(models.DimProduct).count()
    skus_with_cost = db.query(models.DimProduct).filter(models.DimProduct.cost_price.isnot(None)).count()
    dq_score = round(skus_with_cost / total_skus, 2) if total_skus > 0 else 1.0

    return {
        "total_margin_uplift": float(margin_uplift),
        "total_recommendations": total,
        "avg_confidence_score": round(float(avg_conf), 3),
        "safety_warnings_count": warnings,
        "approved_count": approved,
        "rejected_count": rejected,
        "pending_count": pending,
        "estimated_revenue_impact": float(revenue_impact),
        "estimated_margin_impact": float(margin_impact),
        "last_model_run": last_run.started_at.isoformat() if last_run else None,
        "model_version": last_run.model_version if last_run else "v1.0.0",
        "data_quality_score": dq_score,
    }


@router.get("/charts/margin-by-category")
def get_margin_by_category(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    rows = (
        db.query(
            models.DimProduct.category,
            func.sum(models.FactPricingRecommendationDaily.expected_margin_uplift).label("margin_uplift"),
            func.count(models.FactPricingRecommendationDaily.id).label("recommendation_count"),
        )
        .join(models.DimProduct, models.FactPricingRecommendationDaily.sku_id == models.DimProduct.sku_id)
        .group_by(models.DimProduct.category)
        .order_by(func.sum(models.FactPricingRecommendationDaily.expected_margin_uplift).desc())
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    rows = (
        db.query(
            models.FactPricingRecommendationDaily.strategy_type,
            func.count(models.FactPricingRecommendationDaily.id).label("count"),
            func.avg(models.FactPricingRecommendationDaily.confidence_score).label("avg_confidence"),
        )
        .group_by(models.FactPricingRecommendationDaily.strategy_type)
        .all()
    )
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    buckets = [
        ("0-20%", 0, 0.2),
        ("20-40%", 0.2, 0.4),
        ("40-60%", 0.4, 0.6),
        ("60-80%", 0.6, 0.8),
        ("80-100%", 0.8, 1.01),
    ]
    result = []
    for label, low, high in buckets:
        count = db.query(models.FactPricingRecommendationDaily).filter(
            models.FactPricingRecommendationDaily.confidence_score >= low,
            models.FactPricingRecommendationDaily.confidence_score < high,
        ).count()
        result.append({"bucket": label, "count": count})
    return result


@router.get("/charts/price-change-distribution")
def get_price_change_distribution(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
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
        q = db.query(models.FactPricingRecommendationDaily)
        if low is not None:
            q = q.filter(models.FactPricingRecommendationDaily.recommended_change_pct >= low)
        if high is not None:
            q = q.filter(models.FactPricingRecommendationDaily.recommended_change_pct < high)
        result.append({"bucket": label, "count": q.count()})
    return result
