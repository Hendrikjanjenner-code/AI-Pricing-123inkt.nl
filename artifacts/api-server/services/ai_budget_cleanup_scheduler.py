"""
AI-budgetslot opruim-scheduler (§34) — verwijdert periodiek AiBudgetSlot-rijen
ouder dan de bewaartermijn (AI_BUDGET_SLOT_RETENTION_DAYS, default 90 dagen)
zodat de ai_budget_slots-tabel niet onbegrensd groeit. Recente slots blijven
bewaard voor budgetbewaking en de verbruiksrapportage in het beheerderspaneel.

Ontwerp (net als feed_sync_scheduler / data_quality_scan_scheduler): een
asyncio-taak gestart in de FastAPI-lifespan, onafhankelijk van andere
schedulers — het uitschakelen van bv. de DQ-scan raakt deze taak niet.
De blokkerende opruimstap draait in een thread (asyncio.to_thread), vangt
alle fouten af en crasht nooit.

Omgevingsvariabelen:
  DISABLE_AI_BUDGET_CLEANUP        — zet op true om de opruiming uit te schakelen
  AI_BUDGET_CLEANUP_INTERVAL       — interval in seconden (standaard 86400 = 24 uur)
  AI_BUDGET_CLEANUP_STARTUP_DELAY  — aanloopvertraging in seconden (standaard 180)
  AI_BUDGET_SLOT_RETENTION_DAYS    — bewaartermijn in dagen (standaard 90,
                                     gelezen in ai_gateway.cleanup_old_budget_slots)
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("uvicorn.error")

DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60
DEFAULT_STARTUP_DELAY = 180


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        return val if val > 0 else default
    except ValueError:
        return default


def run_cleanup_once() -> int:
    """
    Voer één opruimronde uit (blokkerend — bedoeld voor asyncio.to_thread).
    Geeft het aantal verwijderde rijen terug.
    """
    from ai_gateway import cleanup_old_budget_slots
    return cleanup_old_budget_slots()


async def _cleanup_loop() -> None:
    interval = _int_env("AI_BUDGET_CLEANUP_INTERVAL", DEFAULT_INTERVAL_SECONDS)
    startup_delay = _int_env("AI_BUDGET_CLEANUP_STARTUP_DELAY", DEFAULT_STARTUP_DELAY)
    logger.info(
        "AI-budgetslot opruim-scheduler actief (interval %ds, startvertraging %ds).",
        interval, startup_delay,
    )
    await asyncio.sleep(startup_delay)
    while True:
        try:
            await asyncio.to_thread(run_cleanup_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Opruimen van oude AI-budgetslots mislukt "
                "(volgende poging bij het volgende interval): %s", exc,
            )
        await asyncio.sleep(interval)


def start_ai_budget_cleanup_scheduler() -> asyncio.Task:
    """Start de periodieke AI-budgetslot-opruiming als asyncio-achtergrondtaak."""
    return asyncio.get_event_loop().create_task(_cleanup_loop())
