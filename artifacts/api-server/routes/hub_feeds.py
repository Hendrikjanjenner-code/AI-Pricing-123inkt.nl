"""Scoped private feed lifecycle. URL tests stage only; every activation is explicit."""
import hashlib
import json
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from auth import get_current_user, bearer_scheme
from database import get_db
from feed_models import HubFeedProfile, HubFeedVersion
from routes.cost_priority import access
from services import hub_feeds as svc
from services import hub_feeds_storage as storage

router = APIRouter(prefix="/api/hub-feeds", tags=["hub-feeds"])


def scoped(db, user, shop_id, profile_id, action=None):
    # Every feed can expose sensitive prices/reference data, so use the strict cost permission.
    access(db, user, shop_id, action, True)
    p = db.query(HubFeedProfile).filter_by(id=profile_id, shop_id=shop_id).with_for_update().first()
    if not p:
        raise HTTPException(404, "Feed profile not found")
    return p


@router.get("/{shop_id}/profiles")
def profiles(shop_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, sensitive=True)
    return {"profiles": [svc.profile_json(p) for p in db.query(HubFeedProfile).filter_by(shop_id=shop_id).order_by(HubFeedProfile.id)]}


@router.post("/{shop_id}/profiles")
def create(shop_id: int, body: svc.ProfileInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose", True)
    config, credentials = svc.config_input(body.config)
    p = HubFeedProfile(shop_id=shop_id, name=body.name, purpose=body.purpose, config=config,
                       credentials=credentials, created_by=user.username, active=False)
    db.add(p)
    db.flush()
    svc.audit(db, p, user.username, "feed_created")
    db.commit()
    return svc.profile_json(p)


@router.put("/{shop_id}/profiles/{profile_id}")
def update(shop_id: int, profile_id: int, body: svc.ProfileInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id, "pricing.propose")
    if body.base_revision != p.revision:
        raise HTTPException(409, "Configuration changed; reload")
    if body.purpose != p.purpose:
        raise HTTPException(422, "Purpose is immutable; create a separate profile")
    config, credentials = svc.config_input(body.config, p.credentials)
    p.name, p.config, p.credentials = body.name, config, credentials
    p.revision += 1
    p.active = False
    p.validated_version_id = p.current_version_id = p.released_version_id = None
    p.token_hash = None
    svc.audit(db, p, user.username, "feed_configuration_changed")
    db.commit()
    return svc.profile_json(p)


def test_stage(db, p, actor, data=None):
    if p.purpose == "cost_output":
        raise HTTPException(422, "Build an output snapshot from an active cost source")
    p.last_attempt = datetime.utcnow()
    try:
        v = svc.stage(db, p, svc.fetch(p) if data is None else data, actor)
        if v.status == "valid":
            p.validated_version_id = v.id
            p.last_error = None
        else:
            p.validated_version_id = None
            p.last_error = "; ".join(v.report["errors"])[:2000]
        # Explicit test is staging, even when a profile is active.
        svc.audit(db, p, actor, "feed_tested", {"version_id": v.id})
        db.commit()
        return svc.version_json(v)
    except HTTPException as exc:
        p.last_error = str(exc.detail)[:2000]
        svc.audit(db, p, actor, "feed_test_failed", {"error": p.last_error})
        db.commit()
        raise


@router.post("/{shop_id}/profiles/{profile_id}/upload")
def upload(shop_id: int, profile_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id, "pricing.propose")
    data = file.file.read(storage.MAX_BYTES + 1)
    if len(data) > storage.MAX_BYTES:
        raise HTTPException(413, "Upload exceeds 64 MB")
    return test_stage(db, p, user.username, data)


@router.post("/{shop_id}/profiles/{profile_id}/test")
def test_url(shop_id: int, profile_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id, "pricing.propose")
    if p.last_attempt and (datetime.utcnow() - p.last_attempt).total_seconds() < 10:
        raise HTTPException(429, "Wait 10 seconds between URL tests")
    return test_stage(db, p, user.username)


@router.post("/{shop_id}/profiles/{profile_id}/activate")
def activate(shop_id: int, profile_id: int, body: svc.VersionInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id, "pricing.approve")
    v = svc.valid_version(db, p, body.version_id)
    if p.purpose == "cost_output":
        svc.check_output_source(db, p, v)
    elif p.validated_version_id != v.id:
        raise HTTPException(409, "Activate the most recently validated snapshot")
    p.active = True
    p.current_version_id = v.id
    p.validated_version_id = v.id
    p.last_success = datetime.utcnow()
    p.last_error = None
    p.created_by = user.username  # explicit scheduler authority owner
    svc.audit(db, p, user.username, "feed_activated", {"version_id": v.id})
    db.commit()
    return svc.profile_json(p)


@router.post("/{shop_id}/profiles/{profile_id}/pause")
def pause(shop_id: int, profile_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id, "pricing.propose")
    p.active = False
    svc.audit(db, p, user.username, "feed_paused")
    db.commit()
    return svc.profile_json(p)


@router.get("/{shop_id}/profiles/{profile_id}/versions")
def versions(shop_id: int, profile_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id)
    return {"versions": [svc.version_json(v) for v in db.query(HubFeedVersion).filter_by(profile_id=p.id).order_by(HubFeedVersion.id.desc())]}


@router.get("/{shop_id}/profiles/{profile_id}/versions/{version_id}")
def version(shop_id: int, profile_id: int, version_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id)
    v = svc.ensure_version(db, p, version_id)
    return {**svc.version_json(v), "records": json.loads(storage.get(v.records_key))[:100]}


def attachment(db, p, v, actor):
    data = storage.get(v.object_key)
    if hashlib.sha256(data).hexdigest() != v.sha256:
        raise HTTPException(503, "Stored snapshot failed integrity verification")
    svc.audit(db, p, actor, "feed_downloaded", {"version_id": v.id})
    db.commit()
    return Response(data, media_type="text/csv", headers={"Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Disposition": f'attachment; filename="hub-{p.purpose}-{p.id}-v{v.id}.csv"'})


@router.get("/{shop_id}/profiles/{profile_id}/versions/{version_id}/download")
def download(shop_id: int, profile_id: int, version_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id)
    v = svc.ensure_version(db, p, version_id)
    return attachment(db, p, v, user.username)


@router.post("/{shop_id}/profiles/{profile_id}/build")
def build(shop_id: int, profile_id: int, body: svc.BuildInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id, "pricing.propose")
    v = svc.build(db, p, body, user.username)
    p.validated_version_id = v.id
    db.commit()
    return svc.version_json(v)


@router.post("/{shop_id}/profiles/{profile_id}/release")
def release(shop_id: int, profile_id: int, body: svc.VersionInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id, "pricing.approve")
    if not p.active or p.purpose != "cost_output":
        raise HTTPException(409, "Activate the cost_output profile first")
    v = svc.valid_version(db, p, body.version_id)
    svc.check_output_source(db, p, v)
    p.released_version_id = v.id
    svc.audit(db, p, user.username, "cost_output_released", {"version_id": v.id})
    db.commit()
    return svc.profile_json(p)


@router.post("/{shop_id}/profiles/{profile_id}/token")
def rotate_token(shop_id: int, profile_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = scoped(db, user, shop_id, profile_id, "pricing.approve")
    if p.purpose != "cost_output":
        raise HTTPException(422, "Machine read tokens are for cost_output only")
    if p.token_rotated_at and (datetime.utcnow() - p.token_rotated_at).total_seconds() < 60:
        raise HTTPException(429, "Token rotation is limited to once per minute")
    token = "hf_" + secrets.token_urlsafe(48)
    p.token_hash = hashlib.sha256(token.encode()).hexdigest()
    p.token_rotated_at = datetime.utcnow()
    svc.audit(db, p, user.username, "feed_token_rotated")
    db.commit()
    return {"token": token, "feed_path": f"/api/hub-feeds/{shop_id}/profiles/{profile_id}/feed",
            "authentication": "Authorization: Bearer <token>", "shown_once": True}


@router.get("/{shop_id}/profiles/{profile_id}/feed")
def feed(shop_id: int, profile_id: int, db: Session = Depends(get_db), credentials=Depends(bearer_scheme)):
    token = credentials.credentials if credentials else ""
    if token.startswith("hf_"):
        p = db.query(HubFeedProfile).filter_by(id=profile_id, shop_id=shop_id).with_for_update().first()
        if not p or not p.token_hash or not secrets.compare_digest(p.token_hash, hashlib.sha256(token.encode()).hexdigest()):
            raise HTTPException(401, "Invalid feed token")
        actor = "feed_token"
    else:
        user = get_current_user(credentials, db)
        p = scoped(db, user, shop_id, profile_id)
        actor = user.username
    if not p.active or p.purpose != "cost_output" or not p.released_version_id:
        raise HTTPException(403, "Feed is inactive or no snapshot explicitly released")
    if p.last_feed_access and (datetime.utcnow() - p.last_feed_access).total_seconds() < 5:
        raise HTTPException(429, "Feed access is limited to once per five seconds")
    v = svc.valid_version(db, p, p.released_version_id)
    # Released snapshots remain available on ordinary source fetch errors, not on source pause/config changes.
    svc.check_output_source(db, p, v, require_current=False)
    p.last_feed_access = datetime.utcnow()
    return attachment(db, p, v, actor)


@router.get("/{shop_id}/compare")
def compare(shop_id: int, cost_profile_id: int, products_profile_id: int,
            db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, sensitive=True)
    return svc.compare_sources(db, shop_id, cost_profile_id, products_profile_id)
