"""
Datakwaliteits-scan scheduler (§30) — draait de volledige detectielijst
(`_detect_issues` + `_sync_issue_registry`) automatisch nachtelijks, zodat
terugkerende issues (mislukte imports, stale data, …) niet onopgemerkt
blijven totdat iemand de Data Quality-pagina bezoekt.

Ontwerp (net als feed_sync_scheduler / connector_health_monitor): een
asyncio-taak gestart in de FastAPI-lifespan. De blokkerende scan draait in
een thread (asyncio.to_thread), vangt alle fouten af en crasht nooit.

Alerts: issues die NIEUW zijn of HEROPEND worden (eerder opgelost, nu terug)
sturen een notificatie naar de ingestelde eigenaar (e-mail van de user met
die username) en — als er geen eigenaar is of die geen e-mail heeft — naar de
standaard alert-ontvangers (analisten/admins + ALERT_EMAIL_TO). Bezorging
loopt via dezelfde kanalen als de connector-monitor (SMTP en/of webhook);
zonder configuratie wordt de alert alleen gelogd.

Elke run persisteert een ImportJob (upload_type="data_quality_scan") zodat
de scan-timestamp zichtbaar is op de Data Quality-pagina.

Omgevingsvariabelen:
  DISABLE_DQ_SCAN          — zet op true om de nachtelijke scan uit te schakelen
  DQ_SCAN_INTERVAL         — interval in seconden (standaard 86400 = 24 uur)
  DQ_SCAN_STARTUP_DELAY    — aanloopvertraging in seconden (standaard 120)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

logger = logging.getLogger("uvicorn.error")

DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60
DEFAULT_STARTUP_DELAY = 120

SCAN_JOB_TYPE = "data_quality_scan"


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        return val if val > 0 else default
    except ValueError:
        return default


def _owner_recipients(db, owner: str | None) -> list[str]:
    """E-mailadres(sen) van de ingestelde eigenaar; leeg als onbekend."""
    if not owner:
        return []
    try:
        import models
        user = (
            db.query(models.User)
            .filter(models.User.username == owner, models.User.is_active == True)  # noqa: E712
            .first()
        )
        if user and user.email and user.email.strip():
            return [user.email.strip()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("DQ-scan: kon eigenaar '%s' niet opzoeken: %s", owner, exc)
    return []


def _notify_issue(db, row, kind: str) -> None:
    """Stuur een alert voor een nieuw of heropend issue (e-mail/webhook/log)."""
    from services.health_notifier import get_alert_recipients, _send_email, _send_webhook

    recipients = _owner_recipients(db, row.owner)
    if not recipients:
        recipients = get_alert_recipients(db)

    label = "HEROPEND" if kind == "reopened" else "NIEUW"
    subject = f"[AI Pricing] Datakwaliteitsissue {label}: {row.title or row.issue_code}"
    body = (
        f"De nachtelijke datakwaliteits-scan heeft een {('heropend' if kind == 'reopened' else 'nieuw')} "
        f"issue gedetecteerd.\n\n"
        f"Issue    : {row.title or row.issue_code} ({row.issue_code})\n"
        f"Ernst    : {row.severity}\n"
        f"Bron     : {row.source or '-'} / {row.module or '-'}\n"
        f"Aantal   : {row.affected_count}\n"
        f"Details  : {row.message or '-'}\n"
        f"Impact   : {row.business_impact or '-'}\n"
        f"Actie    : {row.suggested_action or '-'}\n"
        f"Eigenaar : {row.owner or '(geen — algemene melding)'}\n\n"
        f"Open het Data Quality Center in het dashboard om dit issue op te pakken.\n"
    )
    payload = {
        "type": "data_quality_issue",
        "kind": kind,
        "issue_code": row.issue_code,
        "severity": row.severity,
        "affected_count": row.affected_count,
        "owner": row.owner,
    }
    emailed = _send_email(recipients, subject, body)
    hooked = _send_webhook(subject, body, payload)
    if not emailed and not hooked:
        logger.warning(
            "DQ-scan: issue %s is %s, maar er is geen meldingskanaal geconfigureerd "
            "(SMTP_HOST / ALERT_WEBHOOK_URL). Melding: %s",
            row.issue_code, label.lower(), row.message,
        )


def run_scan_once() -> dict:
    """
    Voer één datakwaliteits-scan uit (blokkerend — bedoeld voor asyncio.to_thread).

    Draait _detect_issues + _sync_issue_registry, bepaalt welke issues nieuw of
    heropend zijn, stuurt daarvoor alerts en registreert een ImportJob zodat de
    scan-timestamp zichtbaar is. Geeft een klein samenvattingsdict terug.
    """
    from database import BackgroundSessionLocal
    import models
    from routes.data_quality import _detect_issues, _sync_issue_registry

    db = BackgroundSessionLocal()
    job = models.ImportJob(
        upload_type=SCAN_JOB_TYPE,
        filename="nachtelijke datakwaliteits-scan",
        status="processing",
        uploaded_by="system-dq-scan",
        source="Systeem",
    )
    try:
        total_skus = db.query(models.DimProduct).count()

        # Status vóór de sync vastleggen zodat nieuw/heropend bepaald kan worden.
        before = {
            r.issue_code: r.status
            for r in db.query(models.DataQualityIssue).all()
        }

        detected = _detect_issues(db, total_skus)
        registry = _sync_issue_registry(db, detected)  # commit gebeurt hier

        new_codes: list[str] = []
        reopened_codes: list[str] = []
        for d in detected:
            code = d["issue_code"]
            prev = before.get(code)
            if prev is None:
                new_codes.append(code)
            elif prev == "opgelost":
                reopened_codes.append(code)

        for code in new_codes:
            row = registry.get(code)
            if row is not None:
                try:
                    _notify_issue(db, row, "new")
                except Exception as exc:  # noqa: BLE001
                    logger.error("DQ-scan: alert voor nieuw issue %s mislukt: %s", code, exc)
        for code in reopened_codes:
            row = registry.get(code)
            if row is not None:
                try:
                    _notify_issue(db, row, "reopened")
                except Exception as exc:  # noqa: BLE001
                    logger.error("DQ-scan: alert voor heropend issue %s mislukt: %s", code, exc)

        job.status = "geimporteerd"
        job.rows_processed = len(detected)
        job.completed_at = datetime.utcnow()
        job.warnings_json = {
            "new_issues": new_codes,
            "reopened_issues": reopened_codes,
        }
        db.add(job)
        db.commit()
        summary = {
            "detected": len(detected),
            "new": new_codes,
            "reopened": reopened_codes,
        }
        logger.info(
            "DQ-scan voltooid: %d issues gedetecteerd, %d nieuw, %d heropend.",
            len(detected), len(new_codes), len(reopened_codes),
        )
        return summary
    except Exception:
        # Mislukte scan óók zichtbaar registreren (rollback eerst, dan job-commit).
        db.rollback()
        try:
            import traceback
            job.status = "fout"
            job.error_message = traceback.format_exc()[-2000:]
            job.completed_at = datetime.utcnow()
            db.add(job)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise
    finally:
        db.close()


async def _scan_loop() -> None:
    interval = _int_env("DQ_SCAN_INTERVAL", DEFAULT_INTERVAL_SECONDS)
    startup_delay = _int_env("DQ_SCAN_STARTUP_DELAY", DEFAULT_STARTUP_DELAY)
    logger.info(
        "DQ-scan scheduler actief (interval %ds, startvertraging %ds).",
        interval, startup_delay,
    )
    await asyncio.sleep(startup_delay)
    while True:
        try:
            await asyncio.to_thread(run_scan_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("DQ-scan cyclus mislukt (volgende poging bij het volgende interval): %s", exc)
        await asyncio.sleep(interval)


def start_dq_scan_scheduler() -> asyncio.Task:
    """Start de nachtelijke datakwaliteits-scan als asyncio-achtergrondtaak."""
    return asyncio.get_event_loop().create_task(_scan_loop())
