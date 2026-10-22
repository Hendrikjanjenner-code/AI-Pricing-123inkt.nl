"""Versioned, shop-scoped configuration only; activation never dispatches feeds."""
from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import get_current_user
from authz import effective_permissions, user_allowed_shop_ids
from database import get_db
from models import DimShop, CostPriorityVersion, CostPriorityPreview, AuditLog
from services.cost_priority import Rules, Draft, PreviewInput, Activation, evaluate, workbook_rows, SOURCES

router = APIRouter(prefix="/api/cost-priority", tags=["cost-priority"])


@router.get("/shops/available")
def available_shops(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if "pricing.view" not in effective_permissions(db, user):
        raise HTTPException(403, "Pricing permission required")
    allowed = user_allowed_shop_ids(db, user)
    query = db.query(DimShop).filter(DimShop.active.is_(True))
    if allowed is not None:
        query = query.filter(DimShop.id.in_(allowed))
    return {"shops": [dict(id=shop.id, name=shop.name, is_default=shop.is_default, active=shop.active)
                      for shop in query.order_by(DimShop.id)]}


def access(db, user, shop_id, action=None, sensitive=False):
    permissions = effective_permissions(db, user)
    if "pricing.view" not in permissions or (action and action not in permissions):
        raise HTTPException(403, "Pricing permission required")
    if sensitive and user.role not in ("admin", "pricing_manager"):
        raise HTTPException(403, "Supplier values require pricing_manager or admin")
    allowed = user_allowed_shop_ids(db, user)
    if allowed is not None and shop_id not in allowed:
        raise HTTPException(403, "Shop access denied")
    if not db.get(DimShop, shop_id):
        raise HTTPException(404, "Shop not found")


def active(db, shop_id):
    version = db.query(CostPriorityVersion).filter_by(shop_id=shop_id).order_by(CostPriorityVersion.revision.desc()).first()
    return (version.revision, Rules.model_validate(version.rules)) if version else (0, Rules())


def configuration(db, user, shop_id):
    revision, rules = active(db, shop_id)
    return dict(shop_id=shop_id, revision=revision, rules=rules.model_dump(),
                sources=SOURCES + ([rules.custom_source] if rules.custom_source else []),
                can_edit=user.role in ("admin", "pricing_manager") and
                {"pricing.propose", "pricing.approve"} <= effective_permissions(db, user),
                scope="configuration_only")


@router.get("/{shop_id}")
def get_configuration(shop_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id)
    return configuration(db, user, shop_id)


def preview(db, user, shop_id, draft, rows, kind):
    revision, current = active(db, shop_id)
    if revision != draft.base_revision:
        raise HTTPException(409, "Configuration changed; reload and preview again")
    results = evaluate(rows, current, draft.rules)
    errors = [f"{r['row_id']}: {e}" for r in results for e in r["errors"]]
    token = secrets.token_hex(32)
    expiry = datetime.utcnow() + timedelta(minutes=30)
    snapshot = dict(preview_token=token, shop_id=shop_id, base_revision=revision,
                    rules=draft.rules.model_dump(), input_kind=kind, rows=results,
                    errors=errors, can_activate=not errors, expires_at=expiry.isoformat() + "Z")
    # Bound outstanding snapshots per user/shop. Consumed snapshots are retained as evidence.
    db.query(CostPriorityPreview).filter(
        CostPriorityPreview.shop_id == shop_id, CostPriorityPreview.user_id == user.id,
        CostPriorityPreview.consumed.is_(False)).delete(synchronize_session=False)
    db.add(CostPriorityPreview(token=token, shop_id=shop_id, user_id=user.id,
                              base_revision=revision, snapshot=snapshot, expires_at=expiry))
    db.commit()
    return snapshot


@router.post("/{shop_id}/preview")
def preview_manual(shop_id: int, body: PreviewInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose", True)
    return preview(db, user, shop_id, body, body.rows, "manual")


@router.post("/{shop_id}/preview-workbook")
async def preview_workbook(shop_id: int, draft: str = Form(...), file: UploadFile = File(...),
                           db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose", True)
    try:
        parsed = Draft.model_validate_json(draft)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    data = await file.read(2 * 1024 * 1024 + 1)
    return preview(db, user, shop_id, parsed, workbook_rows(data, parsed.rules), "workbook")


@router.post("/{shop_id}/activate")
def activate(shop_id: int, body: Activation, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve", True)
    try:
        # Lock the existing parent, including first activation. PostgreSQL serializes
        # all writers per shop; unique revision + conditional token consumption backstop SQLite.
        db.query(DimShop).filter_by(id=shop_id).with_for_update().one()
        record = db.query(CostPriorityPreview).filter_by(token=body.preview_token, shop_id=shop_id, user_id=user.id).first()
        revision, previous = active(db, shop_id)
        if (not record or record.consumed or record.expires_at < datetime.utcnow() or
                record.base_revision != revision or body.base_revision != revision):
            raise HTTPException(409, "Preview stale, expired, consumed or unavailable; preview again")
        if not record.snapshot["can_activate"]:
            raise HTTPException(422, "Resolve all input errors before activation")
        claimed = db.execute(update(CostPriorityPreview).where(
            CostPriorityPreview.token == record.token, CostPriorityPreview.consumed.is_(False)
        ).values(consumed=True)).rowcount
        if claimed != 1:
            raise HTTPException(409, "Preview already consumed")
        version = CostPriorityVersion(shop_id=shop_id, revision=revision + 1,
                                      rules=record.snapshot["rules"], activated_by=user.username,
                                      input_kind=record.snapshot["input_kind"], row_count=len(record.snapshot["rows"]))
        db.add(version)
        db.add(AuditLog(entity_type="cost_priority", entity_id=str(shop_id), action="activate",
                        performed_by=user.username, old_value=previous.model_dump(),
                        new_value=version.rules, details=f"Configuration only; revision {revision + 1}; preview {record.token}"))
        db.flush()
        version_id = version.id
        db.commit()
        return {**configuration(db, user, shop_id), "version_id": version_id}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Concurrent activation; reload and preview again") from exc
    except HTTPException:
        db.rollback()
        raise


@router.get("/{shop_id}/history")
def history(shop_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, sensitive=True)
    versions = db.query(CostPriorityVersion).filter_by(shop_id=shop_id).order_by(CostPriorityVersion.revision.desc()).limit(100)
    return {"versions": [dict(version_id=v.id, revision=v.revision, rules=v.rules,
                              activated_by=v.activated_by, activated_at=v.activated_at.isoformat() + "Z",
                              input_kind=v.input_kind, row_count=v.row_count) for v in versions]}
