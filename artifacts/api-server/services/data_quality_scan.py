"""
Datakwaliteits-scan (§30) als herbruikbare service.

Voert de volledige detectielijst uit, synchroniseert het issue-register en
publiceert IntelligenceSignals + eigenaar-notificaties voor NIEUWE of
VERERGERENDE error-issues. Elke run wordt vastgelegd in
``data_quality_scan_run`` zodat het dashboard toont wanneer de laatste scan
liep — of die nu door de scheduler of door een dashboardbezoek is gestart.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

import models

logger = logging.getLogger("uvicorn.error")

SIGNAL_ENGINE = "data_quality"


def _snapshot_registry(db: Session) -> dict[str, dict]:
    return {
        r.issue_code: {
            "status": r.status,
            "severity": r.severity,
            "affected_count": r.affected_count or 0,
        }
        for r in db.query(models.DataQualityIssue).all()
    }


def _classify_change(code: str, detected: dict, prev: dict[str, dict]) -> str | None:
    """
    Geef "nieuw", "heropend" of "verergerd" terug wanneer er gealerteerd moet
    worden.

    - Elk nieuw issue alerteert, ongeacht severity — de taak belooft eigenaren
      te waarschuwen bij nieuwe issues, niet alleen bij errors.
    - Een eerder opgelost issue dat terugkeert (heropend) alerteert altijd.
    - Een bestaand open issue alerteert opnieuw als het verergert: severity
      ge-escaleerd naar error, of (bij errors) een gestegen affected_count.
      Onveranderde open issues alerteren niet opnieuw (geen alert-spam).
    """
    before = prev.get(code)
    if before is None:
        return "nieuw"
    if before["status"] == "opgelost":
        return "heropend"
    # Verergerd: was warning/info en is nu error, of (voor errors) het aantal
    # getroffen records is toegenomen.
    if detected["severity"] == "error":
        if before["severity"] != "error":
            return "verergerd"
        if detected["affected_count"] > before["affected_count"]:
            return "verergerd"
    return None


# NL-kind → EN-kind zoals de notificatielaag (data_quality_scan_scheduler)
# en de signal_type-suffix die verwachten.
KIND_EN = {"nieuw": "new", "heropend": "reopened", "verergerd": "worsened"}


def _publish_issue_signal(db: Session, d: dict, kind: str,
                          registry_row: models.DataQualityIssue | None) -> None:
    from engine.signal_publisher import publish_signal
    prev_count = None
    publish_signal(
        db,
        engine=SIGNAL_ENGINE,
        signal_type=f"data_quality_issue_{KIND_EN.get(kind, 'new')}",
        entity_type="shop",
        entity_id=d["issue_code"],
        entity_name=d["title"],
        severity="high",
        direction="negative",
        current_value=float(d["affected_count"]),
        previous_value=prev_count,
        confidence=1.0,
        explanation=(
            f"Datakwaliteits-scan: {kind} error-issue '{d['title']}' "
            f"({d['affected_count']} getroffen). {d['message']}"
        ),
        evidence={
            "issue_code": d["issue_code"],
            "affected_count": d["affected_count"],
            "source": d["source"],
            "module": d["module"],
            "business_impact": d["business_impact"],
            "owner": registry_row.owner if registry_row is not None else None,
        },
        sources=["data_quality_issue"],
        suggested_action=(d["suggested_action"] or "")[:255] or None,
        model_version="dq-scan-v1",
    )


def run_quality_scan(db: Session, triggered_by: str = "scheduler") -> dict:
    """
    Voer één volledige datakwaliteits-scan uit.

    Geeft een dict terug met detecties, register en scan-metadata. Fouten
    worden vastgelegd op de scan-run rij en opnieuw geraised zodat de caller
    (route of scheduler) zelf beslist hoe ermee om te gaan.
    """
    from routes.data_quality import _detect_issues, _sync_issue_registry
    # Notificatielaag (in-app + e-mail/webhook) — module-attribuut zodat
    # tests services.data_quality_scan_scheduler._notify_issue kunnen patchen.
    import services.data_quality_scan_scheduler as dq_alerts

    run = models.DataQualityScanRun(
        started_at=datetime.utcnow(), triggered_by=triggered_by, status="bezig")
    db.add(run)
    db.commit()

    try:
        prev = _snapshot_registry(db)
        total_skus = db.query(models.DimProduct).count()
        detected = _detect_issues(db, total_skus)
        registry = _sync_issue_registry(db, detected)

        # Signalen + notificaties voor nieuwe/heropende/verergerende issues
        signals_published = 0
        new_or_worse = 0
        changes: dict[str, str] = {}
        for d in detected:
            kind = _classify_change(d["issue_code"], d, prev)
            if kind is None:
                continue
            new_or_worse += 1
            changes[d["issue_code"]] = KIND_EN.get(kind, "new")
            row = registry.get(d["issue_code"])
            try:
                _publish_issue_signal(db, d, kind, row)
                signals_published += 1
            except Exception as exc:  # noqa: BLE001 — één signaalfout stopt de scan niet
                logger.exception("Signaal publiceren voor %s mislukt: %s", d["issue_code"], exc)
            if row is not None:
                try:
                    dq_alerts._notify_issue(db, row, KIND_EN.get(kind, "new"))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Notificatie voor %s mislukt: %s", d["issue_code"], exc)
        db.commit()

        run.finished_at = datetime.utcnow()
        run.status = "geslaagd"
        run.issues_total = len(detected)
        run.error_issues = sum(1 for d in detected if d["severity"] == "error")
        run.warning_issues = sum(1 for d in detected if d["severity"] == "warning")
        run.new_or_worse_errors = new_or_worse
        run.signals_published = signals_published
        db.commit()

        return {
            "detected": detected,
            "registry": registry,
            "total_skus": total_skus,
            "scan_run": run,
            "changes": changes,  # issue_code -> "new" | "reopened" | "worsened"
        }
    except Exception as exc:
        db.rollback()
        try:
            run.finished_at = datetime.utcnow()
            run.status = "fout"
            run.error_message = str(exc)[:2000]
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise


def _scan_run_dict(run: "models.DataQualityScanRun") -> dict:
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "triggered_by": run.triggered_by,
        "status": run.status,
        "issues_total": run.issues_total,
        "error_issues": run.error_issues,
        "warning_issues": run.warning_issues,
        "new_or_worse_errors": run.new_or_worse_errors,
        "signals_published": run.signals_published,
        "error_message": run.error_message,
    }


def recent_scan_runs(db: Session, limit: int = 30,
                     status: str | None = None) -> list[dict]:
    """Recente scan-runs (nieuwste eerst) voor de historie/trendweergave.

    Met ``status`` (bv. "geslaagd") wordt vóór de limit gefilterd, zodat de
    trend altijd de laatste N runs met díe status toont — mislukte runs
    verdringen de geslaagde datapoints dan niet.
    """
    q = db.query(models.DataQualityScanRun)
    if status:
        q = q.filter(models.DataQualityScanRun.status == status)
    runs = (q.order_by(models.DataQualityScanRun.started_at.desc(),
                       models.DataQualityScanRun.id.desc())
            .limit(limit)
            .all())
    return [_scan_run_dict(r) for r in runs]


def last_scan_info(db: Session) -> dict | None:
    """Metadata van de meest recente (afgeronde of lopende) scan voor de UI."""
    run = (db.query(models.DataQualityScanRun)
           .order_by(models.DataQualityScanRun.started_at.desc())
           .first())
    if run is None:
        return None
    return {
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "triggered_by": run.triggered_by,
        "status": run.status,
        "issues_total": run.issues_total,
        "error_issues": run.error_issues,
        "new_or_worse_errors": run.new_or_worse_errors,
        "signals_published": run.signals_published,
        "error_message": run.error_message,
    }
