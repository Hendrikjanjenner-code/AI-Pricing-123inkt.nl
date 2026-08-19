"""Opportunity Engine API — centraal kansenoverzicht (§24)."""
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models
from services.engine_jobs import start_engine_job
from engine.opportunity_engine import run_opportunity_engine, get_opportunity_dashboard

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

VALID_STATUSES = ("open", "in_progress", "done", "dismissed")


@router.get("")
def opportunity_dashboard(
    status: str = Query("open"),
    shop_id: Optional[int] = Query(None),
    hierarchy_node_ids: Optional[str] = Query(None),
    brands: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    # Globale filtercontext (taak #217): alleen kansen binnen de selectie.
    from routes.global_filters import resolve_sku_filter
    sku_filter = resolve_sku_filter(db, hierarchy_node_ids, brands)
    return get_opportunity_dashboard(db, status=status, shop_id=shop_id, sku_filter=sku_filter)


@router.post("/run")
def trigger_opportunity_run(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    return start_engine_job(
        "opportunity", run_opportunity_engine,
        shop_id=shop_id, username=current_user.username,
        audit_entity_id="opportunity",
        audit_details=lambda r: f"Opportunity engine: {r.get('opportunities', 0)} kansen",
    )


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
