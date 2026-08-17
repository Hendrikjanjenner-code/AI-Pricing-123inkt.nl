"""
Shops API — /api/shops
Canonieke shop-dimensie (multi-shop voorbereid, masterprompt §36).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models

router = APIRouter(prefix="/api/shops", tags=["shops"])


def _shop_out(s: models.DimShop) -> dict:
    return {
        "id": s.id,
        "shop_code": s.shop_code,
        "name": s.name,
        "country": s.country,
        "currency": s.currency,
        "legal_entity": s.legal_entity,
        "channel": s.channel,
        "is_default": s.is_default,
        "active": s.active,
    }


class ShopCreate(BaseModel):
    shop_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    country: str = Field("NL", min_length=2, max_length=2)
    currency: str = Field("EUR", min_length=3, max_length=3)
    legal_entity: Optional[str] = None
    channel: str = "online"


@router.get("")
def list_shops(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    shops = db.query(models.DimShop).order_by(models.DimShop.id).all()
    return {"shops": [_shop_out(s) for s in shops]}


@router.post("", status_code=201)
def create_shop(
    req: ShopCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    existing = db.query(models.DimShop).filter(
        models.DimShop.shop_code == req.shop_code
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Shop code '{req.shop_code}' already exists")
    shop = models.DimShop(
        shop_code=req.shop_code,
        name=req.name,
        country=req.country.upper(),
        currency=req.currency.upper(),
        legal_entity=req.legal_entity,
        channel=req.channel,
        is_default=False,
        active=True,
    )
    db.add(shop)
    db.add(models.AuditLog(
        entity_type="shop",
        entity_id=req.shop_code,
        action="create",
        performed_by=current_user.username,
        details=f"Shop '{req.name}' aangemaakt",
    ))
    db.commit()
    db.refresh(shop)
    return _shop_out(shop)
