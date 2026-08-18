"""
AI-sleutel bereikbaarheidsmonitor — achtergrondtaak die periodiek controleert
of de geconfigureerde LLM-provider (OpenAI/Replit AI Integrations) bereikbaar
is en beheerders actief waarschuwt bij statuswijzigingen.

Ontwerp (gelijk aan connector_health_monitor):
  - asyncio-taak gestart vanuit de FastAPI-lifespan
  - Blokkerende probe draait in asyncio.to_thread (event loop blokkeert nooit)
  - Crasht nooit: alle fouten worden afgevangen en gelogd
  - Anti-spam: waarschuwing alleen bij transitie gezond→ongezond (en herstel)
    via een gedemarkeerd BacklogItem (marker "[ai-key-monitor]")

Omgevingsvariabelen:
  DISABLE_AI_KEY_MONITOR     — zet op true om de monitor uit te schakelen
  AI_KEY_MONITOR_INTERVAL    — controle-interval in seconden (standaard 600 = 10 min)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("uvicorn.error")

DEFAULT_INTERVAL_SECONDS = 5 * 60  # 5 minuten
_ALERT_MARKER = "[ai-key-monitor]"
_MODULE_KEY = "ai_gateway"


def _interval_seconds() -> int:
    raw = os.environ.get("AI_KEY_MONITOR_INTERVAL", "").strip()
    if not raw:
        return DEFAULT_INTERVAL_SECONDS
    try:
        val = int(raw)
        return val if val > 0 else DEFAULT_INTERVAL_SECONDS
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS


def _emit_alert(reachable: bool, error: str | None) -> None:
    """Schrijf een BacklogItem-alert voor beheerders (idempotent via marker).

    Bij herstel (reachable=True) wordt een eerder open alert gesloten.
    """
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        existing = (
            db.query(models.BacklogItem)
            .filter(
                models.BacklogItem.module_key == _MODULE_KEY,
                models.BacklogItem.description.like(f"%{_ALERT_MARKER}%"),
                models.BacklogItem.status == "open",
            )
            .first()
        )

        if reachable:
            # Herstel: sluit een eventueel open alert
            if existing:
                existing.status = "done"
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info("AI-sleutel monitor: open alert gesloten (herstel).")
            return

        # Onbereikbaar: maak een nieuw alert aan als er nog geen open is
        if existing:
            logger.debug("AI-sleutel monitor: alert al open, geen duplicate.")
            return

        db.add(
            models.BacklogItem(
                module_key=_MODULE_KEY,
                title="⚠ AI-provider onbereikbaar — Copilot valt terug op fail-safe modus",
                description=(
                    f"{_ALERT_MARKER} Automatisch aangemaakt door de AI-sleutel monitor.\n\n"
                    f"De geconfigureerde LLM-provider is niet bereikbaar.\n\n"
                    f"Foutmelding: {error or '(onbekend)'}\n\n"
                    "Controleer de OPENAI_API_KEY of AI_INTEGRATIONS_OPENAI_API_KEY/BASE_URL "
                    "in de omgevingsvariabelen en pas de sleutel aan indien verlopen of ongeldig. "
                    "De Copilot geeft zolang een gestructureerd foutantwoord (fail-safe modus §56) — "
                    "de rest van de applicatie is niet beïnvloed.\n\n"
                    f"Gedetecteerd op: {datetime.now(timezone.utc).isoformat()}"
                ),
                item_type="bug",
                status="open",
                priority="high",
                created_by="ai_key_monitor",
            )
        )
        db.commit()
        logger.warning("AI-sleutel monitor: beheerder-alert aangemaakt (provider onbereikbaar).")
    except Exception as exc:
        logger.error("AI-sleutel monitor: alert aanmaken mislukt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _run_probe_cycle(previous_reachable: list[bool | None]) -> None:
    """Voer één probe-cyclus uit en schrijf een alert bij statuswijziging."""
    import ai_gateway

    reachable, error = ai_gateway.probe_provider(force=True)
    prev = previous_reachable[0]

    if prev == reachable:
        # Geen statuswijziging — niets te doen
        return

    # Statuswijziging gedetecteerd
    if reachable:
        logger.info(
            "AI-sleutel monitor: provider hersteld (was: %s → nu: bereikbaar).", prev
        )
    else:
        logger.warning(
            "AI-sleutel monitor: provider ONBEREIKBAAR (was: %s → nu: onbereikbaar). "
            "Fout: %s",
            prev,
            error,
        )

    _emit_alert(reachable, error)
    previous_reachable[0] = reachable


async def _monitor_loop() -> None:
    """Hoofdlus van de achtergrondtaak."""
    interval = _interval_seconds()
    logger.info(
        "AI-sleutel monitor gestart (interval=%ds).", interval
    )

    # Bijhouden van de vorige status voor transitie-detectie.
    # Gebruik een lijst zodat de inner-functie de waarde kan muteren.
    # Altijd starten vanuit None: de eerste cyclus vergelijkt altijd None→(resultaat)
    # en roept _emit_alert aan bij elke uitkomst. Bij een gezonde sleutel is
    # _emit_alert(True) idempotent (sluit alleen een open alert als die er is).
    # Bij een ongeldige sleutel is _emit_alert(False) idempotent (geen duplicaten
    # als de startup-probe al een alert heeft aangemaakt).
    previous_reachable: list[bool | None] = [None]

    try:
        await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("AI-sleutel monitor gestopt.")
        raise

    while True:
        try:
            await asyncio.to_thread(_run_probe_cycle, previous_reachable)
        except asyncio.CancelledError:
            logger.info("AI-sleutel monitor gestopt.")
            raise
        except Exception as exc:  # noqa: BLE001 — monitor mag nooit crashen
            logger.exception("AI-sleutel monitor lus-fout (genegeerd): %s", exc)

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("AI-sleutel monitor gestopt.")
            raise


def start_ai_key_monitor() -> asyncio.Task:
    """Start de AI-sleutel monitor als achtergrond-asyncio-taak."""
    return asyncio.create_task(_monitor_loop())
