"""SKU Deep Dive endpoint — historical price, sales, margin, stock, competitor prices, recommendations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/skus", tags=["skus"])


@router.get("/{id}/history")
def get_sku_history(
    id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == id).first()
    if not product:
        raise HTTPException(status_code=404, detail="SKU not found")
    from services.product_identity import authorize_shop
    authorize_shop(db, current_user, product.shop_id)

    # Price history
    price_rows = db.query(models.FactPriceDaily).filter(
        models.FactPriceDaily.sku_id == id
    ).order_by(models.FactPriceDaily.date).all()
    price_history = [{"date": r.date.isoformat(), "value": float(r.price)} for r in price_rows if r.price]

    # Sales history (daily units)
    sales_rows = db.query(models.FactSalesDaily).filter(
        models.FactSalesDaily.sku_id == id
    ).order_by(models.FactSalesDaily.date).all()
    sales_history = [{"date": r.date.isoformat(), "value": float(r.units_sold or 0)} for r in sales_rows]

    # Margin history (daily margin %)
    margin_history = [
        {"date": r.date.isoformat(), "value": round(float(r.margin_pct or 0), 3)}
        for r in sales_rows if r.margin_pct is not None
    ]

    # Stock history
    stock_rows = db.query(models.FactInventoryDaily).filter(
        models.FactInventoryDaily.sku_id == id
    ).order_by(models.FactInventoryDaily.date).all()
    stock_history = [{"date": r.date.isoformat(), "value": float(r.stock_quantity or 0)} for r in stock_rows]

    # Competitor price history (multi-competitor)
    comp_rows = db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.sku_id == id
    ).order_by(models.FactCompetitorPriceDaily.date).all()
    comp_history = [
        {
            "date": r.date.isoformat(),
            "competitor_name": r.competitor_name,
            "value": float(r.price) if r.price else None,
        }
        for r in comp_rows
    ]

    # Recommendation history
    rec_rows = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.sku_id == id
    ).order_by(models.FactPricingRecommendationDaily.date.desc()).limit(30).all()
    rec_history = [
        {
            "id": r.id,
            "date": r.date.isoformat() if r.date else None,
            "sku_id": r.sku_id,
            "product_name": product.product_name,
            "category": product.category,
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
        for r in rec_rows
    ]

    return {
        "sku_id": id,
        "product_name": product.product_name,
        "ean": product.ean,
        "business_sku": product.business_sku,
        "source_aliases": [{"source": a.source, "code": a.code, "shop_id": a.shop_id}
                           for a in db.query(models.ProductSourceAlias).filter_by(
                               shop_id=product.shop_id, sku_id=product.sku_id)],
        "oem_code": product.oem_code,
        "price_history": price_history,
        "sales_history": sales_history,
        "margin_history": margin_history,
        "stock_history": stock_history,
        "competitor_price_history": comp_history,
        "recommendation_history": rec_history,
    }
