"""Substitution monitor endpoint."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/substitutions", tags=["substitutions"])


@router.get("")
def list_substitutions(
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    q = db.query(models.MapSubstitution)
    # Globale filtercontext (hiërarchie + merk): filter op de primaire SKU
    # (a_brand_sku). Lege selectie ≠ geen filter.
    from routes.global_filters import sku_filter_query
    sku_q = sku_filter_query(db, hierarchy_node_ids, brands, statuses, sku_query)
    if sku_q is not None:
        q = q.filter(models.MapSubstitution.a_brand_sku.in_(sku_q.scalar_subquery()))
    pairs = q.all()
    result = []
    for pair in pairs:
        a_product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == pair.a_brand_sku).first()
        pl_product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == pair.private_label_sku).first()

        a_price = float(a_product.current_price) if a_product and a_product.current_price else None
        pl_price = float(pl_product.current_price) if pl_product and pl_product.current_price else None

        price_gap_pct = None
        if a_price and pl_price and a_price > 0:
            price_gap_pct = round(((a_price - pl_price) / a_price) * 100, 2)

        # Simulate sales shift and opportunity score from available data
        a_sales = db.query(func.sum(models.FactSalesDaily.units_sold)).filter(
            models.FactSalesDaily.sku_id == pair.a_brand_sku
        ).scalar() or 0
        pl_sales = db.query(func.sum(models.FactSalesDaily.units_sold)).filter(
            models.FactSalesDaily.sku_id == pair.private_label_sku
        ).scalar() or 0

        total_sales = a_sales + pl_sales
        sales_shift_pct = round((pl_sales / total_sales * 100), 2) if total_sales > 0 else None

        # Opportunity score: higher gap + private label share = opportunity
        opportunity_score = None
        if price_gap_pct is not None and sales_shift_pct is not None:
            opportunity_score = round(min(1.0, (price_gap_pct / 50) * 0.6 + (sales_shift_pct / 100) * 0.4), 2)

        result.append({
            "id": pair.id,
            "a_brand_sku": pair.a_brand_sku,
            "a_brand_name": a_product.product_name if a_product else pair.a_brand_sku,
            "private_label_sku": pair.private_label_sku,
            "private_label_name": pl_product.product_name if pl_product else pair.private_label_sku,
            "a_brand_price": a_price,
            "private_label_price": pl_price,
            "price_gap_pct": price_gap_pct,
            "sales_shift_pct": sales_shift_pct,
            "margin_shift_pct": None,
            "opportunity_score": opportunity_score,
        })

    return result
