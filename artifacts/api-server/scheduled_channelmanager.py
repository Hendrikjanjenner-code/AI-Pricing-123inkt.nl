"""Opt-in reserved-VM worker: CHANNELMANAGER_SCHEDULER_ENABLED=true python scheduled_channelmanager.py.

UTC hourly setting, polls once per minute; durable daily claims prevent duplicate
work across workers. No network publication, automatic approvals or exports.
"""
import os
import sys
import time
import logging
import asyncio
import threading
from datetime import datetime, timezone
from database import BackgroundSessionLocal as SessionLocal
from models import User
from channel_models import ChannelSnapshot
from routes.channelmanager import latest, daily_run, access, add, lock

logger = logging.getLogger(__name__)
runtime = {"running": False, "last_poll_at": None, "last_error": None}


def disabled():
    return ("pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST")) or
            os.environ.get("DISABLE_CHANNELMANAGER_SCHEDULER", "").lower() in ("1", "true", "yes"))


def scheduler_status():
    off = disabled()
    return {**runtime, "available": runtime["running"] and not off, "disabled": off,
            "mode": "in_process_reserved_vm", "poll_interval_seconds": 60,
            "timezone": "UTC",
            "reason": "disabled_by_environment_or_tests" if off else
                      None if runtime["running"] else "application_scheduler_not_started"}


async def scheduler_loop():
    """Lifecycle-managed loop. Cancellation drains its thread, never leaves an orphan worker."""
    if disabled():
        return
    stop = threading.Event()
    runtime["running"] = True
    try:
        while not stop.is_set():
            worker = asyncio.create_task(asyncio.to_thread(tick, stop))
            try:
                await asyncio.shield(worker)
                runtime["last_poll_at"] = datetime.now(timezone.utc).isoformat()
                runtime["last_error"] = None
            except asyncio.CancelledError:
                stop.set()
                await worker
                raise
            except Exception as exc:
                runtime["last_error"] = str(exc)[:2000]
                logger.exception("Channelmanager scheduled preview poll failed")
            await asyncio.sleep(60)
    finally:
        stop.set()
        runtime["running"] = False


def tick(stop=None):
    with SessionLocal() as db:
        shops = db.query(ChannelSnapshot.shop_id).filter_by(kind="config").distinct().all()
    for (shop_id,) in shops:
        if stop is not None and stop.is_set():
            break
        with SessionLocal() as db:
            config = latest(db, shop_id, "config")
            settings = config.data["config"]
            if not settings["schedule_enabled"] or datetime.now(timezone.utc).hour < settings["schedule_hour_utc"]:
                continue
            actor = db.query(User).filter_by(username=config.created_by).first()
            try:
                if actor is None:
                    raise ValueError("Schedule owner no longer exists")
                access(db, actor, shop_id, "pricing.propose")
                daily_run(db, actor, shop_id)
            except Exception as exc:
                db.rollback()
                # Record permission/source failures too, with the same durable daily claim.
                from types import SimpleNamespace
                actor = SimpleNamespace(username=config.created_by)
                lock(db, shop_id)
                claim = f"daily:{datetime.now(timezone.utc).date().isoformat()}"
                if not db.query(ChannelSnapshot).filter_by(shop_id=shop_id, claim=claim).first():
                    add(db, actor, shop_id, "run", {"error": str(getattr(exc, "detail", exc))[:2000],
                        "timezone": "UTC", "finished_at": datetime.now(timezone.utc).isoformat()},
                        "failed", claim)
                    db.commit()
                logger.warning("Channelmanager shop %s preview failed: %s", shop_id, exc)


if __name__ == "__main__":
    if (disabled() or
            os.environ.get("CHANNELMANAGER_SCHEDULER_ENABLED", "").lower() != "true"):
        raise SystemExit("Channelmanager scheduler disabled (explicit opt-in required; never enabled in tests)")
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            tick()
        except Exception:
            logger.exception("Channelmanager scheduler tick failed")
        time.sleep(60)
