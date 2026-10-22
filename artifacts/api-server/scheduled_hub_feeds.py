"""Periodic active imports only. No automatic publication or advice approvals."""
import asyncio
import logging
import os
import sys
import threading
from datetime import datetime
from database import BackgroundSessionLocal
from feed_models import HubFeedProfile
from models import User
from routes.cost_priority import access
from services import hub_feeds as svc

logger = logging.getLogger(__name__)


def disabled():
    return ("pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST")) or
            os.environ.get("DISABLE_HUB_FEEDS_SCHEDULER", "").lower() in ("1", "true", "yes"))


def tick(stop=None):
    with BackgroundSessionLocal() as db:
        ids = [row[0] for row in db.query(HubFeedProfile.id).filter(HubFeedProfile.active.is_(True),
               HubFeedProfile.purpose != "cost_output", HubFeedProfile.credentials.isnot(None)).all()]
    for profile_id in ids:
        if stop is not None and stop.is_set():
            return
        with BackgroundSessionLocal() as db:
            # Durable row lock makes multiple workers serialize; second worker observes updated last_attempt.
            p = db.query(HubFeedProfile).filter_by(id=profile_id).with_for_update(skip_locked=True).first()
            if not p or not p.active:
                continue
            now = datetime.utcnow()
            if p.last_attempt and (now - p.last_attempt).total_seconds() < p.config.get("interval_minutes", 60) * 60:
                continue
            p.last_attempt = now
            try:
                user = db.query(User).filter_by(username=p.created_by, is_active=True).first()
                if not user:
                    raise ValueError("Feed activation owner is no longer active")
                access(db, user, p.shop_id, "pricing.approve", True)
                svc.valid_version(db, p, p.current_version_id)
                v = svc.stage(db, p, svc.fetch(p), p.created_by)
                if v.status != "valid":
                    raise ValueError("; ".join(v.report["errors"])[:2000])
                p.current_version_id = p.validated_version_id = v.id
                p.last_success, p.last_error = datetime.utcnow(), None
                svc.audit(db, p, p.created_by, "feed_periodic_import", {"version_id": v.id})
            except Exception as exc:
                detail = str(exc) if isinstance(exc, ValueError) else getattr(
                    exc, "detail", "Feed import failed; validation, permissions or storage unavailable")
                p.last_error = str(detail)[:2000]
                svc.audit(db, p, p.created_by, "feed_periodic_failed", {"error": p.last_error})
            db.commit()


async def scheduler_loop():
    if disabled():
        return
    stop = threading.Event()
    try:
        while not stop.is_set():
            worker = asyncio.create_task(asyncio.to_thread(tick, stop))
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                stop.set()
                await worker
                raise
            except Exception:
                logger.exception("Hub feed periodic worker failed")
            await asyncio.sleep(60)
    finally:
        stop.set()
