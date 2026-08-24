"""Promotion Intelligence API — promo-effectmeting (§19)."""
from typing import Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
from routes.global_filters import resolve_sku_filter
import models
from services.engine_jobs import start_engine_job
from engine.promotion_engine import run_promotion_engine, get_promotion_dashboard

router = APIRouter(prefix="/api/promotion-intelligence", tags=["promotion-intelligence"])


@router.get("/dashboard")
def promotion_dashboard(
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    """Historische promo-analyse: uplift, incrementaliteit, break-even, cannibalisatie/halo."""
    # Globale filtercontext: None = geen filter; een lege set matcht niets.
    _gf = resolve_sku_filter(db, hierarchy_node_ids, brands, statuses, sku_query)
    return get_promotion_dashboard(db, shop_id=shop_id, sku_filter=_gf)


@router.get("/promotions")
def list_promotions(
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None),
    sku_query: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    from engine.signal_publisher import resolve_shop_id
    sid = resolve_shop_id(db, shop_id)
    # Promotion heeft (nog) geen shop_id-kolom: eigenaarschap loopt via DimProduct.
    q = (
        db.query(models.Promotion)
        .join(models.DimProduct, models.DimProduct.sku_id == models.Promotion.sku_id)
        .filter(models.DimProduct.shop_id == sid)
    )
    # Globale filtercontext: filter promoties op hun SKU. Lege set matcht niets.
    _gf = resolve_sku_filter(db, hierarchy_node_ids, brands, statuses, sku_query)
    if _gf is not None:
        q = q.filter(models.Promotion.sku_id.in_(_gf))
    promos = (
        q.order_by(models.Promotion.start_date.desc())
        .limit(200)
        .all()
    )
    return {"shop_id": sid, "promoties": [
        {
            "id": p.id, "sku_id": p.sku_id, "type": p.promotion_type,
            "korting": float(p.discount_value or 0),
            "start": str(p.start_date), "eind": str(p.end_date) if p.end_date else None,
            "kanaal": p.channel, "omschrijving": p.description,
        }
        for p in promos
    ]}


@router.post("/run")
def trigger_promotion_run(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    return start_engine_job(
        "promotion", run_promotion_engine,
        shop_id=shop_id, username=current_user.username,
        audit_entity_id="promotion",
        audit_details=lambda r: f"Promotion engine: {r.get('analyzed', 0)} promoties geanalyseerd",
    )
