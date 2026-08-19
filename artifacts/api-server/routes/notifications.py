"""
In-app meldingen — /api/notifications

Meldingscentrum (bel-icoon in de header). De nachtelijke datakwaliteits-scan
maakt per nieuw/heropend issue een melding aan voor de eigenaar, of — zonder
eigenaar — voor alle actieve beheerders. Gebruikers zien alleen hun eigen
meldingen en kunnen ze (per stuk of allemaal) als gelezen markeren.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
from auth import get_current_user
from models import InAppNotification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _serialize(n: InAppNotification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "kind": n.kind,
        "title": n.title,
        "message": n.message,
        "severity": n.severity,
        "link": n.link,
        "reference": n.reference,
        "is_read": bool(n.is_read),
        "created_at": str(n.created_at) if n.created_at else None,
        "read_at": str(n.read_at) if n.read_at else None,
    }


@router.get("")
def list_notifications(
    limit: int = Query(30, ge=1, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Eigen meldingen (meest recent eerst) + aantal ongelezen."""
    base = db.query(InAppNotification).filter(
        InAppNotification.username == current_user.username
    )
    unread_count = base.filter(InAppNotification.is_read == False).count()  # noqa: E712
    q = base
    if unread_only:
        q = q.filter(InAppNotification.is_read == False)  # noqa: E712
    items = q.order_by(desc(InAppNotification.created_at), desc(InAppNotification.id)).limit(limit).all()
    return {
        "notifications": [_serialize(n) for n in items],
        "unread_count": unread_count,
    }


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Markeer één eigen melding als gelezen."""
    n = (
        db.query(InAppNotification)
        .filter(
            InAppNotification.id == notification_id,
            InAppNotification.username == current_user.username,
        )
        .first()
    )
    if n is None:
        raise HTTPException(status_code=404, detail="Melding niet gevonden")
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.utcnow()
        db.commit()
    return {"ok": True, "notification": _serialize(n)}


@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Markeer alle eigen ongelezen meldingen als gelezen."""
    now = datetime.utcnow()
    updated = (
        db.query(InAppNotification)
        .filter(
            InAppNotification.username == current_user.username,
            InAppNotification.is_read == False,  # noqa: E712
        )
        .update({"is_read": True, "read_at": now}, synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "marked": updated}
