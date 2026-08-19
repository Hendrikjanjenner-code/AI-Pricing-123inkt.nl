"""Basket Intelligence API — associaties, FBT, cross-sell, fillers (§16)."""
from typing import Any
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
from routes.global_filters import resolve_sku_filter
import models
from services.engine_jobs import start_engine_job
from engine.basket_engine import (
    run_basket_engine,
    get_basket_association_dashboard,
    get_frequently_bought_together,
)

router = APIRouter(prefix="/api/basket", tags=["basket-intelligence"])


@router.get("/associations")
def basket_associations(
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    """Dashboard: associaties, per type, gemiddelde mandmarge.

    Globale filtercontext: we nemen een associatie-paar alleen mee wanneer het
    anker (antecedent_sku / sku_id_a) in de filterset zit — het ankerproduct
    bepaalt de selectie. None = geen filter; een lege set matcht niets."""
    _gf = resolve_sku_filter(db, hierarchy_node_ids, brands)
    return get_basket_association_dashboard(db, shop_id=shop_id, sku_filter=_gf)


@router.get("/fbt/{sku_id}")
def frequently_bought_together(
    sku_id: str,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    """Frequently bought together voor één SKU."""
    return {"sku_id": sku_id, "items": get_frequently_bought_together(db, sku_id, shop_id=shop_id)}


@router.post("/run")
def trigger_basket_run(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    """Start herberekening van basket-associaties op de achtergrond; retourneert een job-id."""
    return start_engine_job(
        "basket", run_basket_engine,
        shop_id=shop_id, username=current_user.username,
        audit_entity_id="basket",
        audit_details=lambda r: f"Basket engine: {r.get('associations', 0)} associaties",
    )
