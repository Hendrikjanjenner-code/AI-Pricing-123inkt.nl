"""
Competition Intelligence endpoints.

Exposes PCIS scores, competition classes, reference prices and
competitor exclusion data per SKU.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/competition", tags=["competition"])


# ── Summary ──────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_competition_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    scores = db.query(models.SkuCompetitionScore).all()
    if not scores:
        return {
            "total_skus_scored": 0,
            "avg_pcis": 0,
            "critical_count": 0,
            "strong_count": 0,
            "influence_count": 0,
            "monitor_count": 0,
            "ignore_count": 0,
            "avg_price_index": 1.0,
            "total_competitors_excluded": 0,
            "downward_pressure_count": 0,
            "upward_opportunity_count": 0,
        }

    avg_pcis = sum(s.pcis_score or 0 for s in scores) / len(scores)
    class_counts: dict = {}
    for s in scores:
        c = s.competition_class or "Ignore"
        class_counts[c] = class_counts.get(c, 0) + 1

    price_indexed = [s for s in scores if s.price_index is not None]
    avg_pi = sum(s.price_index for s in price_indexed) / len(price_indexed) if price_indexed else 1.0
    total_excluded = sum(s.competitors_excluded or 0 for s in scores)

    # Price index < 0.97 = downward pressure; > 1.03 = upward opportunity
    downward = sum(1 for s in price_indexed if s.price_index < 0.97)
    upward = sum(1 for s in price_indexed if s.price_index > 1.03)

    return {
        "total_skus_scored": len(scores),
        "avg_pcis": round(avg_pcis, 4),
        "critical_count": class_counts.get("Critical", 0),
        "strong_count": class_counts.get("Strong", 0),
        "influence_count": class_counts.get("Influence", 0),
        "monitor_count": class_counts.get("Monitor", 0),
        "ignore_count": class_counts.get("Ignore", 0),
        "avg_price_index": round(avg_pi, 4),
        "total_competitors_excluded": total_excluded,
        "downward_pressure_count": downward,
        "upward_opportunity_count": upward,
    }


# ── SKU list ─────────────────────────────────────────────────────────────────

@router.get("/skus")
def list_competition_skus(
    competition_class: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("pcis_score"),
    sort_dir: Optional[str] = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    q = db.query(models.SkuCompetitionScore)
    if competition_class:
        q = q.filter(models.SkuCompetitionScore.competition_class == competition_class)
    if category:
        sku_ids = [
            p.sku_id
            for p in db.query(models.DimProduct).filter(models.DimProduct.category == category).all()
        ]
        q = q.filter(models.SkuCompetitionScore.sku_id.in_(sku_ids))

    total = q.count()

    col_map = {
        "pcis_score": models.SkuCompetitionScore.pcis_score,
        "price_index": models.SkuCompetitionScore.price_index,
        "product_comparability_score": models.SkuCompetitionScore.product_comparability_score,
        "price_sensitivity_score": models.SkuCompetitionScore.price_sensitivity_score,
    }
    sort_col = col_map.get(sort_by or "pcis_score", models.SkuCompetitionScore.pcis_score)
    q = q.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())

    items = q.offset((page - 1) * page_size).limit(page_size).all()
    sku_ids_page = [s.sku_id for s in items]
    products = {
        p.sku_id: p
        for p in db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(sku_ids_page)).all()
    }

    return {
        "items": [_score_out(s, products.get(s.sku_id)) for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── SKU detail ───────────────────────────────────────────────────────────────

@router.get("/skus/{sku_id}")
def get_sku_competition_detail(
    sku_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    score = (
        db.query(models.SkuCompetitionScore)
        .filter(models.SkuCompetitionScore.sku_id == sku_id)
        .order_by(models.SkuCompetitionScore.run_date.desc())
        .first()
    )
    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == sku_id).first()

    from datetime import date, timedelta
    recent_date = date.today() - timedelta(days=14)
    comp_prices = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(
            models.FactCompetitorPriceDaily.sku_id == sku_id,
            models.FactCompetitorPriceDaily.date >= recent_date,
        )
        .order_by(models.FactCompetitorPriceDaily.date.desc())
        .all()
    )

    # Build per-competitor summary (most recent price)
    seen: set = set()
    competitor_detail = []
    ref_price = float(score.reference_price) if score and score.reference_price else None
    for c in comp_prices:
        if c.competitor_name not in seen:
            seen.add(c.competitor_name)
            price = float(c.price) if c.price else None
            is_excluded = False
            exclusion_reason = None
            if ref_price and price:
                deviation = abs(price - ref_price) / (ref_price + 0.001)
                if deviation > 0.30:
                    is_excluded = True
                    exclusion_reason = "COMPETITOR_IGNORED_OUTLIER"
            competitor_detail.append({
                "competitor_name": c.competitor_name,
                "price": price,
                "date": c.date.isoformat() if c.date else None,
                "is_excluded": is_excluded,
                "exclusion_reason": exclusion_reason,
                "price_vs_own_pct": (
                    round((price / float(product.current_price) - 1) * 100, 2)
                    if price and product and product.current_price else None
                ),
                "price_vs_reference_pct": (
                    round((price / ref_price - 1) * 100, 2)
                    if price and ref_price else None
                ),
            })

    return {
        "sku_id": sku_id,
        "product": _product_brief(product),
        "competition_score": _score_out(score, product) if score else None,
        "competitor_detail": competitor_detail,
    }


# ── Charts ───────────────────────────────────────────────────────────────────

@router.get("/charts/pcis-distribution")
def get_pcis_distribution(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    classes = ["Critical", "Strong", "Influence", "Monitor", "Ignore"]
    result = []
    for cls in classes:
        count = db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.competition_class == cls
        ).count()
        result.append({"class": cls, "count": count})
    return result


@router.get("/charts/price-index-by-category")
def get_price_index_by_category(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    scores = db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.price_index.isnot(None)
    ).all()
    sku_ids = [s.sku_id for s in scores]
    products = {
        p.sku_id: p
        for p in db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(sku_ids)).all()
    }
    category_data: dict = {}
    for score in scores:
        p = products.get(score.sku_id)
        cat = p.category if p else "Unknown"
        category_data.setdefault(cat, []).append(float(score.price_index))

    return [
        {
            "category": cat,
            "avg_price_index": round(sum(indices) / len(indices), 4),
            "sku_count": len(indices),
        }
        for cat, indices in sorted(category_data.items())
    ]


@router.get("/charts/sub-scores-by-class")
def get_sub_scores_by_class(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Average sub-scores grouped by competition class (for radar charts)."""
    classes = ["Critical", "Strong", "Influence", "Monitor", "Ignore"]
    result = []
    for cls in classes:
        rows = db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.competition_class == cls
        ).all()
        if not rows:
            continue
        n = len(rows)
        result.append({
            "class": cls,
            "count": n,
            "avg_product_comparability": round(sum(r.product_comparability_score or 0 for r in rows) / n, 3),
            "avg_price_sensitivity": round(sum(r.price_sensitivity_score or 0 for r in rows) / n, 3),
            "avg_substitution": round(sum(r.substitution_score or 0 for r in rows) / n, 3),
            "avg_competitor_relevance": round(sum(r.competitor_relevance_score or 0 for r in rows) / n, 3),
            "avg_price_reliability": round(sum(r.competitor_price_reliability_score or 0 for r in rows) / n, 3),
            "avg_basket_dependency": round(sum(r.basket_dependency_score or 0 for r in rows) / n, 3),
            "avg_strategic_importance": round(sum(r.strategic_importance_score or 0 for r in rows) / n, 3),
        })
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_out(s: models.SkuCompetitionScore, product=None) -> dict:
    return {
        "id": s.id,
        "sku_id": s.sku_id,
        "product_name": product.product_name if product else s.sku_id,
        "category": product.category if product else None,
        "brand": product.brand if product else None,
        "run_date": s.run_date.isoformat() if s.run_date else None,
        "product_comparability_score": s.product_comparability_score,
        "price_sensitivity_score": s.price_sensitivity_score,
        "substitution_score": s.substitution_score,
        "competitor_relevance_score": s.competitor_relevance_score,
        "competitor_price_reliability_score": s.competitor_price_reliability_score,
        "basket_dependency_score": s.basket_dependency_score,
        "strategic_importance_score": s.strategic_importance_score,
        "pcis_score": s.pcis_score,
        "competition_class": s.competition_class,
        "reference_price": float(s.reference_price) if s.reference_price else None,
        "price_index": s.price_index,
        "current_price": float(product.current_price) if product and product.current_price else None,
        "competitors_used": s.competitors_used,
        "competitors_excluded": s.competitors_excluded,
        "excluded_reasons": s.excluded_reasons or {},
    }


def _product_brief(p) -> dict:
    if not p:
        return {}
    return {
        "sku_id": p.sku_id,
        "product_name": p.product_name,
        "brand": p.brand,
        "category": p.category,
        "subcategory": p.subcategory,
        "is_private_label": p.is_private_label,
        "is_a_brand": p.is_a_brand,
        "lifecycle_status": p.lifecycle_status,
        "current_price": float(p.current_price) if p.current_price else None,
        "cost_price": float(p.cost_price) if p.cost_price else None,
        "min_price": float(p.min_price) if p.min_price else None,
        "max_price": float(p.max_price) if p.max_price else None,
        "stock_quantity": p.stock_quantity,
    }
