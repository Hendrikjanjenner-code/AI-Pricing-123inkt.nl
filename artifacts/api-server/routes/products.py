"""Product/SKU management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from pydantic import BaseModel
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/products", tags=["products"])


class ProductOut(BaseModel):
    sku_id: str
    product_name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    product_group: Optional[str] = None
    is_private_label: bool
    is_a_brand: bool
    lifecycle_status: Optional[str] = None
    strategy_type: Optional[str] = None
    ean: Optional[str] = None
    oem_code: Optional[str] = None
    cost_price: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    current_price: Optional[float] = None
    stock_quantity: Optional[int] = None
    data_quality_score: Optional[float] = None

    class Config:
        from_attributes = True


class UpdateProductRequest(BaseModel):
    strategy_type: Optional[str] = None
    lifecycle_status: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    cost_price: Optional[float] = None


@router.get("")
def list_products(
    category: Optional[str] = Query(None),
    subcategory: Optional[str] = Query(None),
    is_private_label: Optional[bool] = Query(None),
    strategy_type: Optional[str] = Query(None),
    lifecycle_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    q = db.query(models.DimProduct)
    if category:
        q = q.filter(models.DimProduct.category == category)
    if subcategory:
        q = q.filter(models.DimProduct.subcategory == subcategory)
    if is_private_label is not None:
        q = q.filter(models.DimProduct.is_private_label == is_private_label)
    if strategy_type:
        q = q.filter(models.DimProduct.strategy_type == strategy_type)
    if lifecycle_status:
        q = q.filter(models.DimProduct.lifecycle_status == lifecycle_status)
    if search:
        q = q.filter(
            or_(
                models.DimProduct.sku_id.ilike(f"%{search}%"),
                models.DimProduct.product_name.ilike(f"%{search}%"),
                models.DimProduct.brand.ilike(f"%{search}%"),
            )
        )
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_product_out(p) for p in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{id}", response_model=ProductOut)
def get_product(
    id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    p = db.query(models.DimProduct).filter(models.DimProduct.sku_id == id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_out(p)


@router.patch("/{id}", response_model=ProductOut)
def update_product(
    id: str,
    req: UpdateProductRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    p = db.query(models.DimProduct).filter(models.DimProduct.sku_id == id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    if req.strategy_type is not None:
        p.strategy_type = req.strategy_type
    if req.lifecycle_status is not None:
        p.lifecycle_status = req.lifecycle_status
    if req.min_price is not None:
        p.min_price = req.min_price
    if req.max_price is not None:
        p.max_price = req.max_price
    if req.cost_price is not None:
        p.cost_price = req.cost_price
    db.commit()
    db.refresh(p)
    return _product_out(p)


def _product_out(p: models.DimProduct) -> dict:
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
        "ean": p.ean,
        "oem_code": p.oem_code,
        "cost_price": float(p.cost_price) if p.cost_price else None,
        "min_price": float(p.min_price) if p.min_price else None,
        "max_price": float(p.max_price) if p.max_price else None,
        "current_price": float(p.current_price) if p.current_price else None,
        "stock_quantity": p.stock_quantity,
        "data_quality_score": p.data_quality_score,
    }
