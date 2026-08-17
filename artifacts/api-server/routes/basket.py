"""Basket Intelligence API — associaties, FBT, cross-sell, fillers (§16)."""
from typing import Any
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models
from engine.basket_engine import (
    run_basket_engine,
    get_basket_association_dashboard,
    get_frequently_bought_together,
)

router = APIRouter(prefix="/api/basket", tags=["basket-intelligence"])


@router.get("/associations")
def basket_associations(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    """Dashboard: associaties, per type, gemiddelde mandmarge."""
    return get_basket_association_dashboard(db, shop_id=shop_id)


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
    """Herbereken alle basket-associaties en publiceer signalen."""
    result = run_basket_engine(db, shop_id=shop_id)
    db.add(models.AuditLog(
        entity_type="engine", entity_id="basket", action="run",
        performed_by=current_user.username,
        details=f"Basket engine: {result.get('associations', 0)} associaties",
    ))
    db.commit()
    return result
