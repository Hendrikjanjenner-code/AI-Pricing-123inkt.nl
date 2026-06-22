"""Pricing recommendation endpoints: list, detail, approve, reject, override, bulk approve."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _rec_out(r: models.FactPricingRecommendationDaily, product: Optional[models.DimProduct] = None) -> dict:
    return {
        "id": r.id,
        "date": r.date.isoformat() if r.date else None,
        "sku_id": r.sku_id,
        "product_name": product.product_name if product else r.sku_id,
        "category": product.category if product else None,
        "strategy_type": r.strategy_type,
        "current_price": float(r.current_price) if r.current_price else None,
        "recommended_price": float(r.override_price or r.recommended_price) if (r.override_price or r.recommended_price) else None,
        "recommended_change_pct": float(r.recommended_change_pct) if r.recommended_change_pct else None,
        "expected_units": float(r.expected_units) if r.expected_units else None,
        "expected_revenue": float(r.expected_revenue) if r.expected_revenue else None,
        "expected_margin": float(r.expected_margin) if r.expected_margin else None,
        "expected_margin_uplift": float(r.expected_margin_uplift) if r.expected_margin_uplift else None,
        "confidence_score": float(r.confidence_score) if r.confidence_score else None,
        "reason_code": r.reason_code,
        "safety_status": r.safety_status,
        "approval_status": r.approval_status,
        "approved_by": r.approved_by,
        "exported": r.exported,
        "model_version": r.model_version,
    }


@router.get("")
def list_recommendations(
    date_filter: Optional[str] = Query(None, alias="date"),
    category: Optional[str] = Query(None),
    strategy_type: Optional[str] = Query(None),
    approval_status: Optional[str] = Query(None),
    safety_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort_by: Optional[str] = Query(None),
    sort_dir: Optional[str] = Query("desc"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    q = db.query(models.FactPricingRecommendationDaily)
    if date_filter:
        try:
            d = date.fromisoformat(date_filter)
            q = q.filter(models.FactPricingRecommendationDaily.date == d)
        except ValueError:
            pass
    if strategy_type:
        q = q.filter(models.FactPricingRecommendationDaily.strategy_type == strategy_type)
    if approval_status:
        q = q.filter(models.FactPricingRecommendationDaily.approval_status == approval_status)
    if safety_status:
        q = q.filter(models.FactPricingRecommendationDaily.safety_status == safety_status)
    if search:
        q = q.filter(
            or_(
                models.FactPricingRecommendationDaily.sku_id.ilike(f"%{search}%"),
            )
        )
    if category:
        sku_ids = [
            p.sku_id for p in db.query(models.DimProduct).filter(models.DimProduct.category == category).all()
        ]
        q = q.filter(models.FactPricingRecommendationDaily.sku_id.in_(sku_ids))

    total = q.count()
    pending_count = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.approval_status == "pending"
    ).count()
    approved_count = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.approval_status == "approved"
    ).count()
    rejected_count = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.approval_status == "rejected"
    ).count()

    # Sorting
    sort_col = models.FactPricingRecommendationDaily.id
    if sort_by == "expected_margin_uplift":
        sort_col = models.FactPricingRecommendationDaily.expected_margin_uplift
    elif sort_by == "confidence_score":
        sort_col = models.FactPricingRecommendationDaily.confidence_score
    elif sort_by == "recommended_change_pct":
        sort_col = models.FactPricingRecommendationDaily.recommended_change_pct

    if sort_dir == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    items = q.offset((page - 1) * page_size).limit(page_size).all()

    # Fetch product names in batch
    sku_ids = [r.sku_id for r in items]
    products = {p.sku_id: p for p in db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(sku_ids)).all()}

    return {
        "items": [_rec_out(r, products.get(r.sku_id)) for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
    }


@router.get("/bulk-approve")
def bulk_approve_get(db: Session = Depends(get_db)):
    # Prevent GET confusion
    raise HTTPException(status_code=405, detail="Use POST")


@router.post("/bulk-approve")
def bulk_approve(
    req: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    ids = req.get("ids", [])
    affected = 0
    for rec_id in ids:
        r = db.query(models.FactPricingRecommendationDaily).filter(
            models.FactPricingRecommendationDaily.id == rec_id
        ).first()
        if r and r.approval_status == "pending":
            r.approval_status = "approved"
            r.approved_by = current_user.username
            r.approved_at = datetime.utcnow()
            _log_audit(db, "recommendation", str(rec_id), "approved", current_user.username)
            affected += 1
    db.commit()
    return {"affected": affected, "message": f"Approved {affected} recommendations"}


@router.get("/{id}")
def get_recommendation(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    r = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.id == id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == r.sku_id).first()

    # Competitor prices
    comp_prices = db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.sku_id == r.sku_id,
        models.FactCompetitorPriceDaily.date == r.date,
    ).all()

    competitor_prices = [
        {
            "competitor_name": c.competitor_name,
            "price": float(c.price) if c.price else None,
            "date": c.date.isoformat() if c.date else None,
            "url": c.url,
        }
        for c in comp_prices
    ]

    # Safety rules that were applied
    safety_rules = []
    if r.reason_code in ("MIN_PRICE_GUARDRAIL_APPLIED", "MAX_PRICE_GUARDRAIL_APPLIED"):
        safety_rules.append(r.reason_code)
    if r.safety_status == "blocked":
        safety_rules.append("PRICE_BLOCKED_BY_SAFETY_RULES")
    if r.safety_status == "warning":
        safety_rules.append("LOW_CONFIDENCE_FLAG")

    # Audit trail
    audit_entries = db.query(models.AuditLog).filter(
        models.AuditLog.entity_type == "recommendation",
        models.AuditLog.entity_id == str(id),
    ).order_by(models.AuditLog.timestamp.desc()).all()

    audit_trail = [
        {
            "id": a.id,
            "action": a.action,
            "performed_by": a.performed_by,
            "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            "details": a.details,
        }
        for a in audit_entries
    ]

    # Input factors derived from the recommendation
    input_factors = {
        "strategy_type": r.strategy_type,
        "confidence_score": float(r.confidence_score) if r.confidence_score else None,
        "expected_margin_uplift": float(r.expected_margin_uplift) if r.expected_margin_uplift else None,
        "expected_units": float(r.expected_units) if r.expected_units else None,
        "model_version": r.model_version,
    }
    if product:
        input_factors["cost_price"] = float(product.cost_price) if product.cost_price else None
        input_factors["min_price"] = float(product.min_price) if product.min_price else None
        input_factors["max_price"] = float(product.max_price) if product.max_price else None

    return {
        "recommendation": _rec_out(r, product),
        "product": _product_brief(product),
        "competitor_prices": competitor_prices,
        "input_factors": input_factors,
        "safety_rules_applied": safety_rules,
        "audit_trail": audit_trail,
    }


@router.post("/{id}/approve")
def approve_recommendation(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    r = _get_rec_or_404(id, db)
    r.approval_status = "approved"
    r.approved_by = current_user.username
    r.approved_at = datetime.utcnow()
    _log_audit(db, "recommendation", str(id), "approved", current_user.username)
    db.commit()
    db.refresh(r)
    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == r.sku_id).first()
    return _rec_out(r, product)


@router.post("/{id}/reject")
def reject_recommendation(
    id: int,
    req: dict = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    r = _get_rec_or_404(id, db)
    r.approval_status = "rejected"
    reason = (req or {}).get("reason", "")
    _log_audit(db, "recommendation", str(id), "rejected", current_user.username, reason)
    db.commit()
    db.refresh(r)
    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == r.sku_id).first()
    return _rec_out(r, product)


@router.patch("/{id}/override")
def override_recommendation(
    id: int,
    req: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    r = _get_rec_or_404(id, db)
    override_price = req.get("override_price")
    if override_price is None:
        raise HTTPException(status_code=400, detail="override_price is required")
    r.override_price = override_price
    r.approval_status = "overridden"
    r.approved_by = current_user.username
    r.approved_at = datetime.utcnow()
    reason = req.get("reason", "Manual override")
    r.override_reason = reason
    _log_audit(db, "recommendation", str(id), f"overridden to {override_price}", current_user.username, reason)
    db.commit()
    db.refresh(r)
    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == r.sku_id).first()
    return _rec_out(r, product)


def _get_rec_or_404(id: int, db: Session) -> models.FactPricingRecommendationDaily:
    r = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.id == id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return r


def _log_audit(db: Session, entity_type: str, entity_id: str, action: str, user: str, details: str = ""):
    entry = models.AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        performed_by=user,
        details=details,
    )
    db.add(entry)


def _product_brief(p: Optional[models.DimProduct]) -> dict:
    if not p:
        return {}
    return {
        "sku_id": p.sku_id,
        "product_name": p.product_name,
        "brand": p.brand,
        "category": p.category,
        "subcategory": p.subcategory,
        "product_group": p.product_group,
        "is_private_label": p.is_private_label,
        "is_a_brand": p.is_a_brand,
        "lifecycle_status": p.lifecycle_status,
        "strategy_type": p.strategy_type,
        "cost_price": float(p.cost_price) if p.cost_price else None,
        "min_price": float(p.min_price) if p.min_price else None,
        "max_price": float(p.max_price) if p.max_price else None,
        "current_price": float(p.current_price) if p.current_price else None,
        "stock_quantity": p.stock_quantity,
        "data_quality_score": p.data_quality_score,
    }
