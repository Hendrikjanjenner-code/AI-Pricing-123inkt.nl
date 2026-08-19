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

Mislukt de scan zélf meerdere keren op rij, dan gaat er één alert naar de
standaard alert-ontvangers (zelfde kanalen: SMTP/webhook/log). De teller is
gebaseerd op de ImportJob-historie (aantal opeenvolgende 'fout'-runs), dus
robuust tegen herstarts; er wordt alleen gealarmeerd op het moment dat de
drempel exact wordt bereikt (geen herhaling elke nacht) en een geslaagde run
reset de teller vanzelf.

Omgevingsvariabelen:
  DISABLE_DQ_SCAN          — zet op true om de nachtelijke scan uit te schakelen
  DQ_SCAN_INTERVAL         — interval in seconden (standaard 86400 = 24 uur)
  DQ_SCAN_STARTUP_DELAY    — aanloopvertraging in seconden (standaard 120)
  DQ_SCAN_FAILURE_ALERT_THRESHOLD — aantal opeenvolgende mislukte runs waarna
                             een alert uitgaat (standaard 2)
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
DEFAULT_FAILURE_ALERT_THRESHOLD = 2


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


def _inapp_recipients(db, owner: str | None) -> list[str]:
    """Usernames die een in-app melding krijgen: de actieve eigenaar, of —
    zonder (actieve) eigenaar — alle actieve beheerders."""
    import models
    if owner:
        user = (
            db.query(models.User)
            .filter(models.User.username == owner, models.User.is_active == True)  # noqa: E712
            .first()
        )
        if user:
            return [user.username]
    admins = (
        db.query(models.User)
        .filter(models.User.role == "admin", models.User.is_active == True)  # noqa: E712
        .all()
    )
    return [u.username for u in admins]


def _create_inapp_notifications(db, row, kind: str) -> int:
    """Maak in-app meldingen aan voor een nieuw/heropend issue.

    Werkt onafhankelijk van SMTP/webhook zodat eigenaren de alerts altijd in
    de app zien. Fouten worden gelogd en breken de scan niet.
    """
    import models
    try:
        recipients = _inapp_recipients(db, row.owner)
        if not recipients:
            return 0
        label = {"reopened": "heropend", "worsened": "verergerd"}.get(kind, "nieuw")
        for username in recipients:
            db.add(models.InAppNotification(
                username=username,
                type="data_quality_issue",
                kind=kind,
                title=f"Datakwaliteitsissue {label}: {row.title or row.issue_code}",
                message=row.message or row.business_impact or "",
                severity=row.severity or "warning",
                link="/datakwaliteit",
                reference=row.issue_code,
            ))
        db.commit()
        return len(recipients)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("DQ-scan: in-app melding voor issue %s mislukt: %s", row.issue_code, exc)
        return 0


def _notify_issue(db, row, kind: str) -> None:
    """Stuur een alert voor een nieuw of heropend issue (in-app + e-mail/webhook/log)."""
    from services.health_notifier import get_alert_recipients, _send_email, _send_webhook

    # In-app melding: altijd, ook zonder SMTP/webhook-configuratie.
    _create_inapp_notifications(db, row, kind)

    recipients = _owner_recipients(db, row.owner)
    if not recipients:
        recipients = get_alert_recipients(db)

    label = {"reopened": "HEROPEND", "worsened": "VERERGERD"}.get(kind, "NIEUW")
    subject = f"[AI Pricing] Datakwaliteitsissue {label}: {row.title or row.issue_code}"
    body = (
        f"De nachtelijke datakwaliteits-scan heeft een {label.lower()} "
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

def _consecutive_failed_scans(db) -> int:
    """Tel het aantal meest recente, opeenvolgende 'fout'-scanruns.

    Loopt door de ImportJob-historie (nieuwste eerst) en stopt bij de eerste
    run die niet 'fout' is. Persistente teller: overleeft herstarts en reset
    automatisch zodra een run slaagt.
    """
    import models
    count = 0
    q = (
        db.query(models.ImportJob.status)
        .filter(models.ImportJob.upload_type == SCAN_JOB_TYPE)
        .order_by(models.ImportJob.id.desc())
    )
    for (status,) in q.yield_per(50):
        if status == "fout":
            count += 1
        else:
            break
    return count
def run_scan_once() -> dict:
    """
    Voer één datakwaliteits-scan uit (blokkerend — bedoeld voor asyncio.to_thread
    of de one-shot mode van services.data_quality_scheduler).

    Delegeert de eigenlijke scan aan services.data_quality_scan.run_quality_scan
    (detecties + registry-sync + IntelligenceSignals + notificaties via
    _notify_issue in deze module) en registreert daarnaast een ImportJob zodat
    de scan ook in de importgeschiedenis zichtbaar is. Geeft een klein
    samenvattingsdict terug.
    """
    from database import BackgroundSessionLocal
    import models
    from services.data_quality_scan import run_quality_scan

    db = BackgroundSessionLocal()
    job = models.ImportJob(
        upload_type=SCAN_JOB_TYPE,
        filename="nachtelijke datakwaliteits-scan",
        status="processing",
        uploaded_by="system-dq-scan",
        source="Systeem",
    )
    try:
        result = run_quality_scan(db, triggered_by="scheduler")
        changes = result["changes"]  # issue_code -> "new"|"reopened"|"worsened"
        new_codes = [c for c, k in changes.items() if k == "new"]
        reopened_codes = [c for c, k in changes.items() if k == "reopened"]

        job.status = "geimporteerd"
        job.rows_processed = len(result["detected"])
        job.completed_at = datetime.utcnow()
        job.warnings_json = {
            "new_issues": new_codes,
            "reopened_issues": reopened_codes,
        }
        db.add(job)
        db.commit()
        summary = {
            "detected": len(result["detected"]),
            "new": new_codes,
            "reopened": reopened_codes,
        }
        logger.info(
            "DQ-scan voltooid: %d issues gedetecteerd, %d nieuw, %d heropend.",
            len(result["detected"]), len(new_codes), len(reopened_codes),
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

            # Herhaaldelijk mislukte scans: alarmeer beheerders precies één
            # keer, op het moment dat de drempel wordt bereikt. Een geslaagde
            # run onderbreekt de reeks en reset de teller automatisch.
            threshold = _int_env(
                "DQ_SCAN_FAILURE_ALERT_THRESHOLD", DEFAULT_FAILURE_ALERT_THRESHOLD
            )
            consecutive = _consecutive_failed_scans(db)
            if consecutive == threshold:
                try:
                    _notify_scan_failure(db, consecutive, job.error_message or "")
                except Exception as exc:  # noqa: BLE001
                    logger.error("DQ-scan: falen-alert versturen mislukte: %s", exc)
        except Exception:  # noqa: BLE001
            db.rollback()
        raise
    finally:
        db.close()

def _notify_scan_failure(db, consecutive: int, error_message: str) -> None:
    """Alarmeer de standaard ontvangers dat de nachtscan herhaaldelijk faalt."""
    from services.health_notifier import get_alert_recipients, _send_email, _send_webhook

    recipients = get_alert_recipients(db)
    subject = (
        f"[AI Pricing] Nachtelijke datakwaliteits-scan is {consecutive}x op rij mislukt"
    )
    body = (
        f"De nachtelijke datakwaliteits-scan is {consecutive} keer op rij mislukt.\n\n"
        f"Zolang de scan faalt, worden nieuwe datakwaliteitsissues NIET gedetecteerd\n"
        f"en gaan er geen issue-alerts uit.\n\n"
        f"Laatste foutmelding:\n{(error_message or '-')[:1500]}\n\n"
        f"Controleer de serverlogs en het Data Quality Center. Na een geslaagde run\n"
        f"reset de teller vanzelf.\n"
    )
    payload = {
        "type": "data_quality_scan_failure",
        "consecutive_failures": consecutive,
        "error": (error_message or "")[:500],
    }
    emailed = _send_email(recipients, subject, body)
    hooked = _send_webhook(subject, body, payload)
    if not emailed and not hooked:
        logger.warning(
            "DQ-scan: %d opeenvolgende mislukte runs, maar er is geen meldingskanaal "
            "geconfigureerd (SMTP_HOST / ALERT_WEBHOOK_URL). Fout: %s",
            consecutive, (error_message or "")[:500],
        )
