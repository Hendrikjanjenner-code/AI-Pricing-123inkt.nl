"""
PriceShape feed-sync scheduler — achtergrondtaak die de PriceShape output-feed
periodiek automatisch inleest, zodat de app onafgebroken over verse
concurrentdata beschikt zonder dat een analist handmatig hoeft te synchroniseren.

Ontwerp (net als connector_health_monitor): een asyncio-taak die in de
FastAPI-lifespan wordt gestart. De blokkerende sync draait in een thread
(asyncio.to_thread) zodat de event loop nooit blokkeert. De taak vangt alle
fouten af en crasht nooit.

"Never break" / "zonder onderbreking":
  - Elke cyclus doet meerdere pogingen met exponentiële backoff (transient
    netwerk-/serverfouten worden zo vanzelf opgevangen).
  - De onderliggende ingest (`feed_ingest.ingest_feed`) haalt de feed eerst op
    vóór welke delete dan ook, en breekt af op een lege feed. Een mislukte of
    lege sync laat de laatst-goede data dus altijd intact — de app blijft draaien.
  - Faalt een hele cyclus toch, dan wordt dit gelogd en probeert de scheduler
    het gewoon opnieuw bij het volgende interval; hij stopt nooit.

Omgevingsvariabelen:
  DISABLE_FEED_SYNC      — zet op true om de auto-sync uit te schakelen
  FEED_SYNC_INTERVAL     — sync-interval in seconden (standaard 21600 = 6 uur)
  FEED_SYNC_MAX_RETRIES  — pogingen per cyclus (standaard 3)
  FEED_SYNC_STARTUP_DELAY— aanloopvertraging in seconden (standaard 45)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace

logger = logging.getLogger("uvicorn.error")

DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_STARTUP_DELAY = 45

# Systeem-"gebruiker" voor de ImportJob-audit (heeft alleen een .username nodig).
_SYSTEM_USER = SimpleNamespace(username="system-autosync")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        return val if val > 0 else default
    except ValueError:
        return default


def _is_priceshape_configured(db) -> bool:
    """True als PriceShape via DB-credentials of omgevingsvariabelen is ingesteld."""
    from routes.connectors import _get_config, _check_env_configured
    cfg = _get_config(db, "priceshape")
    has_db_creds = bool(cfg and cfg.encrypted_credentials)
    return has_db_creds or _check_env_configured("priceshape")


def _run_sync_once() -> dict | None:
    """
    Voer één PriceShape-sync uit (blokkerend — bedoeld voor asyncio.to_thread).
    Geeft het sync-resultaat terug, of None als PriceShape niet is geconfigureerd.
    """
    from database import SessionLocal
    from routes.connectors import _run_sync, touch_last_synced

    db = SessionLocal()
    try:
        if not _is_priceshape_configured(db):
            logger.debug("Feed-sync: PriceShape niet geconfigureerd — overgeslagen.")
            return None
        result = _run_sync("priceshape", db, _SYSTEM_USER)
        # Na een geslaagde ingest óók de volledige modelrun draaien, zodat niet
        # alleen de concurrentprijzen maar ook de aanbevelingen én de
        # concurrentie-scores (CI Dashboard, sku_competition_score) en AI-matches
        # meevernieuwen. Zonder deze stap zou "altijd aan" wel verse feed-data
        # ophalen maar het CI Dashboard leeg laten.
        if result.get("status") == "ok":
            from services.refresh import run_model_refresh
            processed, skipped = run_model_refresh(db)
            # Pas NA de geslaagde volledige modelrun de "laatste sync"-tijd zetten.
            # Anders zou de UI een verse tijd tonen terwijl de modelrun faalde en
            # het CI Dashboard leeg bleef — precies het symptoom dat we oplossen.
            touch_last_synced(db, "priceshape")
            logger.info(
                "Feed-sync modelrun klaar: %d verwerkt, %d overgeslagen.",
                processed, skipped,
            )
        return result
    finally:
        db.close()


def _run_sync_with_retries(max_retries: int) -> None:
    """
    Probeer de sync tot `max_retries` keer met exponentiële backoff. Een mislukte
    sync laat de bestaande data altijd intact (zie feed_ingest), dus opnieuw
    proberen is veilig. Deze functie gooit nooit.
    """
    import time

    for attempt in range(1, max_retries + 1):
        try:
            result = _run_sync_once()
            if result is None:
                return  # niet geconfigureerd — niets te doen
            status = result.get("status")
            if status == "ok":
                counts = result.get("counts", {})
                logger.info(
                    "Feed-sync geslaagd (poging %d/%d): %s concurrentprijzen, %s producten.",
                    attempt, max_retries,
                    counts.get("concurrentprijzen", "?"),
                    counts.get("producten_nieuw", 0) + counts.get("producten_bijgewerkt", 0),
                )
                return
            # not_configured of error → loggen en (bij error) opnieuw proberen
            logger.warning(
                "Feed-sync poging %d/%d gaf status '%s': %s",
                attempt, max_retries, status, result.get("message", ""),
            )
            if status == "not_configured":
                return  # opnieuw proberen heeft geen zin
        except Exception as exc:  # noqa: BLE001 — scheduler mag nooit crashen
            logger.exception("Feed-sync poging %d/%d gooide een fout: %s", attempt, max_retries, exc)

        if attempt < max_retries:
            backoff = min(300, 10 * (2 ** (attempt - 1)))  # 10s, 20s, 40s … max 5 min
            time.sleep(backoff)

    logger.error(
        "Feed-sync: alle %d pogingen mislukt. Laatst-goede data blijft actief; "
        "volgende poging bij het volgende interval.", max_retries,
    )


async def _scheduler_loop() -> None:
    """Hoofdlus: sync de PriceShape-feed elke FEED_SYNC_INTERVAL seconden."""
    interval = _int_env("FEED_SYNC_INTERVAL", DEFAULT_INTERVAL_SECONDS)
    max_retries = _int_env("FEED_SYNC_MAX_RETRIES", DEFAULT_MAX_RETRIES)
    startup_delay = _int_env("FEED_SYNC_STARTUP_DELAY", DEFAULT_STARTUP_DELAY)

    logger.info(
        "PriceShape feed-sync scheduler gestart (interval=%ds, retries=%d).",
        interval, max_retries,
    )

    # Aanloopvertraging zodat de rest van de startup rustig kan afronden.
    try:
        await asyncio.sleep(min(startup_delay, interval))
    except asyncio.CancelledError:
        logger.info("Feed-sync scheduler gestopt.")
        raise

    while True:
        try:
            await asyncio.to_thread(_run_sync_with_retries, max_retries)
        except asyncio.CancelledError:
            logger.info("Feed-sync scheduler gestopt.")
            raise
        except Exception as exc:  # noqa: BLE001 — scheduler mag nooit crashen
            logger.exception("Feed-sync scheduler lus-fout (genegeerd): %s", exc)

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Feed-sync scheduler gestopt.")
            raise


def start_feed_sync_scheduler() -> asyncio.Task:
    """Start de feed-sync scheduler als achtergrond-asyncio-taak."""
    return asyncio.create_task(_scheduler_loop())
