"""Category listing and category-strategy mapping endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api", tags=["categories"])


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    rows = (
        db.query(
            models.DimProduct.category,
            func.count(models.DimProduct.sku_id).label("sku_count"),
        )
        .group_by(models.DimProduct.category)
        .all()
    )
    categories_from_db = db.query(models.DimCategory).all()
    cat_map = {c.name: c for c in categories_from_db}
    result = []
    for idx, row in enumerate(rows):
        cat_name = row.category or "Uncategorized"
        cat = cat_map.get(cat_name)
        result.append({
            "id": idx + 1,
            "name": cat_name,
            "parent_category": cat.parent_category if cat else None,
            "default_strategy": cat.default_strategy if cat else None,
            "sku_count": row.sku_count,
        })
    return result


@router.get("/category-strategies")
def list_category_strategies(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    mappings = db.query(models.CategoryStrategyMapping).all()
    return [
        {
            "id": m.id,
            "category": m.category,
            "subcategory": m.subcategory,
            "strategy_type": m.strategy_type,
            "notes": m.notes,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            "updated_by": m.updated_by,
        }
        for m in mappings
    ]


class UpdateCategoryStrategyRequest(BaseModel):
    strategy_type: str
    notes: Optional[str] = None


@router.put("/category-strategies/{id}")
def update_category_strategy(
    id: int,
    req: UpdateCategoryStrategyRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    mapping = db.query(models.CategoryStrategyMapping).filter(models.CategoryStrategyMapping.id == id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Category strategy not found")
    mapping.strategy_type = req.strategy_type
    mapping.notes = req.notes
    mapping.updated_by = current_user.username
    db.commit()
    db.refresh(mapping)
    return {
        "id": mapping.id,
        "category": mapping.category,
        "subcategory": mapping.subcategory,
        "strategy_type": mapping.strategy_type,
        "notes": mapping.notes,
        "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
        "updated_by": mapping.updated_by,
    }
