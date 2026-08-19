"""In-memory job-registry voor zware engine-herberekeningen.

De run-endpoints (basket/promotion/forecast/opportunity) starten hiermee een
achtergrond-thread en retourneren direct een job-id; de frontend pollt
GET /api/engine-jobs/{job_id} tot de run klaar is. Zo blijft er geen
langlopende HTTP-verbinding open die op een proxy-timeout kan stranden.

Bewust in-memory: de dev/prod-server draait als één proces en het pollen
zelf houdt de instance wakker. Bij een herstart verdwijnen jobs; de
frontend behandelt een onbekende job-id als "verlopen".
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}
_MAX_JOBS = 200  # eenvoudige bounded store; oudste afgeronde jobs worden opgeruimd


def _prune_locked() -> None:
    if len(_JOBS) <= _MAX_JOBS:
        return
    finished = sorted(
        (j for j in _JOBS.values() if j["status"] in ("completed", "failed")),
        key=lambda j: j["started_at"],
    )
    for job in finished[: len(_JOBS) - _MAX_JOBS]:
        _JOBS.pop(job["job_id"], None)


def start_engine_job(
    engine: str,
    runner: Callable[..., Dict[str, Any]],
    *,
    shop_id: Optional[int],
    username: str,
    audit_entity_id: str,
    audit_details: Callable[[Dict[str, Any]], str],
) -> Dict[str, Any]:
    """Start `runner(db, shop_id=...)` in een achtergrond-thread.

    Schrijft bij succes zelf de AuditLog-regel (met eigen sessie) en
    retourneert direct de job-record (status "running").
    """
    job_id = uuid.uuid4().hex
    job: Dict[str, Any] = {
        "job_id": job_id,
        "engine": engine,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result": None,
        "error": None,
    }
    with _LOCK:
        _JOBS[job_id] = job
        _prune_locked()

    def _work() -> None:
        from database import BackgroundSessionLocal
        import models

        db = BackgroundSessionLocal()
        try:
            result = runner(db, shop_id=shop_id)
            db.add(models.AuditLog(
                entity_type="engine", entity_id=audit_entity_id, action="run",
                performed_by=username,
                details=audit_details(result),
            ))
            db.commit()
            with _LOCK:
                job["status"] = "completed"
                job["result"] = result
                job["finished_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:  # noqa: BLE001 — job-status moet de fout tonen
            logger.exception("Engine-job %s (%s) mislukt", job_id, engine)
            try:
                db.rollback()
            except Exception:  # pragma: no cover
                pass
            with _LOCK:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["finished_at"] = datetime.now(timezone.utc).isoformat()
        finally:
            db.close()

    threading.Thread(target=_work, name=f"engine-job-{engine}", daemon=True).start()
    return dict(job)


def get_engine_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None
