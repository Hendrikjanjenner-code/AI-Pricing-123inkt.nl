"""
Connector-gezondheidsmonitor — achtergrondtaak die periodiek de gezondheid van
elke geconfigureerde databron (connector) controleert en analisten per e-mail
(of webhook) waarschuwt zodra een bron uitvalt.

Ontwerp (net als scrape_scheduler): een asyncio-taak die in de FastAPI-lifespan
wordt gestart. De blokkerende verbindingschecks draaien in een thread
(asyncio.to_thread) zodat de event loop nooit blokkeert. De taak vangt alle
fouten af en crasht nooit.

Anti-spam: per connector wordt de laatst-gemelde status opgeslagen in
ConnectorConfig.last_alerted_status. Er wordt alleen een melding verstuurd
wanneer de status *wijzigt* naar een niet-ok toestand. Herhaalde identieke
fouten leveren dus geen nieuwe mails op.

Omgevingsvariabelen:
  DISABLE_HEALTH_MONITOR   — zet op true om de monitor uit te schakelen
  HEALTH_CHECK_INTERVAL    — controle-interval in seconden (standaard 900 = 15 min)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("uvicorn.error")

# Statussen die als "gezond" gelden. Alles daarbuiten is een uitval.
# 'not_configured' telt niet als uitval: een niet-ingestelde bron is geen
# bron die "onderuit ging".
OK_STATUS = "ok"

DEFAULT_INTERVAL_SECONDS = 15 * 60


def _interval_seconds() -> int:
    raw = os.environ.get("HEALTH_CHECK_INTERVAL", "").strip()
    if not raw:
        return DEFAULT_INTERVAL_SECONDS
    try:
        val = int(raw)
        return val if val > 0 else DEFAULT_INTERVAL_SECONDS
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS


def _configured_connectors(db) -> list[str]:
    """
    Geef de namen van connectors die daadwerkelijk zijn geconfigureerd
    (via DB-credentials of omgevingsvariabelen). Alleen die worden bewaakt.
    """
    from routes.connectors import (
        VALID_CONNECTORS, _get_config, _check_env_configured,
    )
    configured: list[str] = []
    for name in VALID_CONNECTORS:
        cfg = _get_config(db, name)
        has_db_creds = bool(cfg and cfg.encrypted_credentials)
        if has_db_creds or _check_env_configured(name):
            configured.append(name)
    return configured


def _ensure_config_row(db, name: str):
    """
    Haal (of maak) de ConnectorConfig-rij op voor deze connector, zodat de
    alarmstatus persistent kan worden bewaard — ook voor connectors die alleen
    via omgevingsvariabelen zijn geconfigureerd (die anders geen rij hebben).
    Een rij zonder encrypted_credentials wordt nergens als "db-geconfigureerd"
    beschouwd, dus dit verandert de bestaande semantiek niet.
    """
    import models
    from routes.connectors import _get_config
    cfg = _get_config(db, name)
    if cfg is None:
        now = datetime.now(timezone.utc)
        cfg = models.ConnectorConfig(
            connector_name=name,
            created_at=now,
            updated_at=now,
        )
        db.add(cfg)
        db.flush()
    return cfg


def _check_one(db, name: str) -> None:
    """
    Controleer één connector en verstuur bij een statuswijziging naar 'niet-ok'
    een melding. Werkt de opgeslagen alarmstatus bij.
    """
    from routes.connectors import _run_live_check, CONNECTOR_LABELS
    from services import health_notifier

    try:
        result = _run_live_check(name, db)
    except Exception as exc:  # noqa: BLE001 — één connector mag de rest niet stoppen
        logger.exception("Gezondheidscheck voor '%s' gooide een fout: %s", name, exc)
        result = {"status": "error", "message": str(exc)[:300]}

    status = result.get("status", "error")
    message = result.get("message", "")

    cfg = _ensure_config_row(db, name)
    previous = cfg.last_alerted_status

    is_down = status not in (OK_STATUS, "not_configured")
    changed = status != previous

    # Werk de laatst-waargenomen status altijd bij, zodat we transities kunnen
    # detecteren en herstel (terug naar ok) later ook een transitie is.
    cfg.last_alerted_status = status
    cfg.updated_at = datetime.now(timezone.utc)

    if is_down and changed:
        cfg.last_alerted_at = datetime.now(timezone.utc)
        label = CONNECTOR_LABELS.get(name, name)
        logger.warning(
            "Databron '%s' viel uit (status=%s, vorige=%s): %s",
            label, status, previous, message,
        )
        try:
            health_notifier.send_connector_alert(
                db,
                connector_name=name,
                connector_label=label,
                status=status,
                message=message,
                previous_status=previous,
            )
        except Exception as exc:  # noqa: BLE001 — meldingsfout mag niets stoppen
            logger.error("Versturen van uitval-melding voor '%s' mislukt: %s", name, exc)
    elif is_down:
        logger.info(
            "Databron '%s' blijft in status '%s' — geen nieuwe melding (anti-spam).",
            CONNECTOR_LABELS.get(name, name), status,
        )
    elif changed and previous not in (None, "not_configured"):
        logger.info(
            "Databron '%s' hersteld: status '%s' (was '%s').",
            CONNECTOR_LABELS.get(name, name), status, previous,
        )

    db.commit()


def _run_health_cycle() -> None:
    """
    Voer één volledige gezondheidsronde uit over alle geconfigureerde
    connectors. Blokkerend — bedoeld om via asyncio.to_thread te draaien.
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        namen = _configured_connectors(db)
        if not namen:
            logger.debug("Gezondheidsmonitor: geen geconfigureerde connectors.")
            return
        logger.info("Gezondheidsmonitor: %d connector(s) worden gecontroleerd.", len(namen))
        for name in namen:
            try:
                _check_one(db, name)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.exception("Gezondheidscheck voor '%s' mislukte: %s", name, exc)
    finally:
        db.close()


async def _monitor_loop() -> None:
    """Hoofdlus: controleer de connectors elke HEALTH_CHECK_INTERVAL seconden."""
    interval = _interval_seconds()
    logger.info("Connector-gezondheidsmonitor gestart (interval=%ds).", interval)

    # Korte aanloopvertraging zodat de rest van de startup rustig kan afronden.
    try:
        await asyncio.sleep(min(30, interval))
    except asyncio.CancelledError:
        logger.info("Connector-gezondheidsmonitor gestopt.")
        raise

    while True:
        try:
            await asyncio.to_thread(_run_health_cycle)
        except asyncio.CancelledError:
            logger.info("Connector-gezondheidsmonitor gestopt.")
            raise
        except Exception as exc:  # noqa: BLE001 — monitor mag nooit crashen
            logger.exception("Gezondheidsmonitor lus-fout (genegeerd): %s", exc)

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Connector-gezondheidsmonitor gestopt.")
            raise


def start_health_monitor() -> asyncio.Task:
    """Start de gezondheidsmonitor als achtergrond-asyncio-taak."""
    return asyncio.create_task(_monitor_loop())
