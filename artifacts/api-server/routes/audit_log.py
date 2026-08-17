"""
Audit Log routes — /api/audit-log
Wie heeft wat goedgekeurd, wanneer en waarom.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from auth import require_role
from models import AuditLog, User

router = APIRouter(prefix="/api/audit-log", tags=["audit"])


@router.get("")
def get_audit_log(
    gebruiker: str = Query(None),
    entiteit: str = Query(None),
    actie: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    # RBAC-aanscherping (masterprompt §35): het audit-log bevat gevoelige
    # informatie over wie wat heeft goedgekeurd — niet voor viewers.
    current_user: User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    """
    Haal audit log op, gefilterd op gebruiker, entiteit of actie.
    Gesorteerd op datum, meest recent eerst.
    """
    q = db.query(AuditLog)
    if gebruiker:
        q = q.filter(AuditLog.performed_by == gebruiker)
    if entiteit:
        q = q.filter(AuditLog.entity_type == entiteit)
    if actie:
        q = q.filter(AuditLog.action == actie)

    totaal = q.count()
    entries = (
        q.order_by(desc(AuditLog.timestamp))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Unieke gebruikers en acties voor filteropties
    alle_gebruikers = [r[0] for r in db.query(AuditLog.performed_by).distinct().all() if r[0]]
    alle_acties = [r[0] for r in db.query(AuditLog.action).distinct().all() if r[0]]
    alle_entiteiten = [r[0] for r in db.query(AuditLog.entity_type).distinct().all() if r[0]]

    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": str(e.timestamp),
                "gebruiker": e.performed_by,
                "actie": e.action,
                "entiteit": e.entity_type,
                "entiteit_id": e.entity_id,
                "details": e.details,
                "oude_waarde": e.old_value,
                "nieuwe_waarde": e.new_value,
            }
            for e in entries
        ],
        "totaal": totaal,
        "page": page,
        "page_size": page_size,
        "filter_opties": {
            "gebruikers": sorted(alle_gebruikers),
            "acties": sorted(alle_acties),
            "entiteiten": sorted(alle_entiteiten),
        },
    }
