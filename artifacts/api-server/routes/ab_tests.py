"""
A/B Test monitoring endpoints.

Exposes experiment results comparing AI-driven pricing (AI group) against
unchanged pricing (CONTROL group): margin uplift, revenue delta, conversion
lift, category breakdown and per-SKU detail.
"""
import numpy as np
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/ab-tests", tags=["ab-tests"])


@router.get("")
def list_ab_tests(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    q = db.query(models.AbTest)
    # Globale filtercontext (hiërarchie + merk): beperk tot A/B-tests die
    # ten minste één resultaat op een gefilterde SKU hebben. Lege selectie ≠
    # geen filter (dan blijven er simpelweg geen tests over).
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    if sku_q is not None:
        test_ids_sq = (
            db.query(models.AbTestResult.test_id)
            .filter(models.AbTestResult.sku_id.in_(sku_q.scalar_subquery()))
            .scalar_subquery()
        )
        q = q.filter(models.AbTest.id.in_(test_ids_sq))
    tests = q.order_by(models.AbTest.created_at.desc()).all()
    return [_test_out(t) for t in tests]


@router.get("/{test_id}")
def get_ab_test_detail(
    test_id: int,
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    test = db.query(models.AbTest).filter(models.AbTest.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="A/B test not found")

    results_q = db.query(models.AbTestResult).filter(
        models.AbTestResult.test_id == test_id)
    # Globale filtercontext (hiërarchie + merk): beperk alle detailberekeningen
    # (summary, categorie-breakdown, per-SKU) tot de gefilterde SKU-set.
    # Lege selectie ≠ geen filter (dan blijven er geen resultaten over).
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    if sku_q is not None:
        results_q = results_q.filter(
            models.AbTestResult.sku_id.in_(sku_q.scalar_subquery()))
    results = results_q.all()
    ai_results = [r for r in results if r.group_type == "AI"]
    ctrl_results = [r for r in results if r.group_type == "CONTROL"]

    # Fetch products for names/categories
    sku_ids = list({r.sku_id for r in results})
    products = {
        p.sku_id: p
        for p in db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(sku_ids)).all()
    }

    def _sum(rows, attr):
        return sum(float(getattr(r, attr) or 0) for r in rows)

    def _avg(rows, attr):
        vals = [float(getattr(r, attr)) for r in rows if getattr(r, attr) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    # Statistical confidence (simplified t-test proxy on per-SKU margin uplift)
    ai_uplifts = [float(r.current_margin or 0) - float(r.baseline_margin or 0) for r in ai_results]
    ctrl_uplifts = [float(r.current_margin or 0) - float(r.baseline_margin or 0) for r in ctrl_results]
    statistical_confidence = 0.0
    if len(ai_uplifts) >= 3 and len(ctrl_uplifts) >= 3:
        ai_std = float(np.std(ai_uplifts)) + 0.01
        ctrl_std = float(np.std(ctrl_uplifts)) + 0.01
        pooled_se = np.sqrt(
            (ai_std ** 2 / len(ai_uplifts)) + (ctrl_std ** 2 / len(ctrl_uplifts))
        )
        t_stat = abs(np.mean(ai_uplifts) - np.mean(ctrl_uplifts)) / pooled_se
        statistical_confidence = min(0.99, float(t_stat / (t_stat + 2)))

    # Category breakdown
    cat_groups: dict = {}
    for r in results:
        p = products.get(r.sku_id)
        cat = p.category if p else "Unknown"
        cat_groups.setdefault(cat, {"AI": [], "CONTROL": []})
        cat_groups[cat][r.group_type].append(r)

    category_breakdown = []
    for cat, groups in sorted(cat_groups.items()):
        ai_g = groups["AI"]
        ctrl_g = groups["CONTROL"]
        category_breakdown.append({
            "category": cat,
            "ai_sku_count": len(ai_g),
            "control_sku_count": len(ctrl_g),
            "ai_margin_uplift": round(_sum(ai_g, "current_margin") - _sum(ai_g, "baseline_margin"), 2),
            "control_margin_uplift": round(_sum(ctrl_g, "current_margin") - _sum(ctrl_g, "baseline_margin"), 2),
            "ai_revenue_uplift": round(_sum(ai_g, "current_revenue") - _sum(ai_g, "baseline_revenue"), 2),
            "control_revenue_uplift": round(_sum(ctrl_g, "current_revenue") - _sum(ctrl_g, "baseline_revenue"), 2),
        })

    ai_baseline_conv = _avg(ai_results, "baseline_conversion_rate")
    ai_current_conv = _avg(ai_results, "current_conversion_rate")
    ctrl_baseline_conv = _avg(ctrl_results, "baseline_conversion_rate")
    ctrl_current_conv = _avg(ctrl_results, "current_conversion_rate")

    return {
        "test": _test_out(test),
        "summary": {
            "ai_sku_count": len(ai_results),
            "control_sku_count": len(ctrl_results),
            "ai_revenue_uplift": round(_sum(ai_results, "current_revenue") - _sum(ai_results, "baseline_revenue"), 2),
            "control_revenue_uplift": round(_sum(ctrl_results, "current_revenue") - _sum(ctrl_results, "baseline_revenue"), 2),
            "ai_margin_uplift": round(_sum(ai_results, "current_margin") - _sum(ai_results, "baseline_margin"), 2),
            "control_margin_uplift": round(_sum(ctrl_results, "current_margin") - _sum(ctrl_results, "baseline_margin"), 2),
            "ai_conversion_lift_pct": round(
                (ai_current_conv - ai_baseline_conv) / (ai_baseline_conv + 0.001) * 100, 2
            ),
            "control_conversion_lift_pct": round(
                (ctrl_current_conv - ctrl_baseline_conv) / (ctrl_baseline_conv + 0.001) * 100, 2
            ),
            "statistical_confidence": round(statistical_confidence, 4),
        },
        "category_breakdown": category_breakdown,
        "sku_results": [_result_out(r, products.get(r.sku_id)) for r in results],
    }


def _test_out(t: models.AbTest) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "start_date": t.start_date.isoformat() if t.start_date else None,
        "end_date": t.end_date.isoformat() if t.end_date else None,
        "status": t.status,
        "ai_group_sku_count": t.ai_group_sku_count,
        "control_group_sku_count": t.control_group_sku_count,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _result_out(r: models.AbTestResult, product=None) -> dict:
    bl_margin = float(r.baseline_margin or 0)
    curr_margin = float(r.current_margin or 0)
    bl_revenue = float(r.baseline_revenue or 0)
    curr_revenue = float(r.current_revenue or 0)
    bl_conv = float(r.baseline_conversion_rate or 0)
    curr_conv = float(r.current_conversion_rate or 0)
    return {
        "id": r.id,
        "sku_id": r.sku_id,
        "product_name": product.product_name if product else r.sku_id,
        "category": product.category if product else None,
        "group_type": r.group_type,
        "baseline_price": float(r.baseline_price) if r.baseline_price else None,
        "current_price": float(r.current_price) if r.current_price else None,
        "baseline_margin": bl_margin,
        "current_margin": curr_margin,
        "margin_uplift": round(curr_margin - bl_margin, 2),
        "baseline_revenue": bl_revenue,
        "current_revenue": curr_revenue,
        "revenue_uplift": round(curr_revenue - bl_revenue, 2),
        "baseline_conversion_rate": bl_conv,
        "current_conversion_rate": curr_conv,
        "conversion_lift_pct": round((curr_conv - bl_conv) / (bl_conv + 0.001) * 100, 2),
    }
