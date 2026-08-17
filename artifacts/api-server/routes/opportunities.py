"""Opportunity Engine API — centraal kansenoverzicht (§24)."""
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models
from engine.opportunity_engine import run_opportunity_engine, get_opportunity_dashboard

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

VALID_STATUSES = ("open", "in_progress", "done", "dismissed")


@router.get("")
def opportunity_dashboard(
    status: str = Query("open"),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    return get_opportunity_dashboard(db, status=status, shop_id=shop_id)


@router.post("/run")
def trigger_opportunity_run(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    result = run_opportunity_engine(db, shop_id=shop_id)
    db.add(models.AuditLog(
        entity_type="engine", entity_id="opportunity", action="run",
        performed_by=current_user.username,
        details=f"Opportunity engine: {result.get('opportunities', 0)} kansen",
    ))
    db.commit()
    return result


@router.post("/{opportunity_id}/status")
def update_opportunity_status(
    opportunity_id: int,
    status: str = Query(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager", "analyst")),
) -> Any:
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"Ongeldige status. Geldig: {VALID_STATUSES}")
    from engine.signal_publisher import resolve_shop_id
    sid = resolve_shop_id(db, shop_id)
    opp = db.query(models.Opportunity).filter(
        models.Opportunity.id == opportunity_id,
        models.Opportunity.shop_id == sid,
    ).first()
    if not opp:
        raise HTTPException(404, "Opportunity niet gevonden")
    old = opp.status
    opp.status = status
    db.add(models.AuditLog(
        entity_type="opportunity", entity_id=str(opportunity_id), action="status_change",
        performed_by=current_user.username,
        details=f"Status: {old} → {status}",
    ))
    db.commit()
    return {"id": opp.id, "status": opp.status}
