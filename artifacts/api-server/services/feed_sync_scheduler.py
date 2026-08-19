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
  FEED_SYNC_RETRY_BACKOFF— basis-backoff tussen pogingen in seconden
                           (standaard 60; verdubbelt per poging, max 10 min).
                           Ruim gespreid zodat een export-regeneratie (die de
                           feed tijdelijk leeg maakt) binnen één cyclus
                           vanzelf overleefd wordt.
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
DEFAULT_RETRY_BACKOFF = 60          # basis-wachttijd tussen pogingen (seconden)
MAX_RETRY_BACKOFF = 600             # bovengrens: 10 minuten


def _backoff_seconds(attempt: int, base: int = DEFAULT_RETRY_BACKOFF) -> int:
    """Exponentiële backoff: base, 2×base, 4×base … gemaximeerd op 10 minuten.

    Bewust ruim gespreid (minuten i.p.v. seconden): een PriceShape-export die
    net regenereert kan enkele minuten leeg zijn — drie pogingen binnen 40
    seconden vallen dan alle drie in hetzelfde gat."""
    return min(MAX_RETRY_BACKOFF, base * (2 ** (attempt - 1)))

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
    """
    True als PriceShape is ingesteld. Dat is tegenwoordig ALTIJD het geval:
    zonder DB-credentials of omgevingsvariabelen valt de connector terug op de
    ingebouwde standaard-feed-URL (DEFAULT_FEED_URL) — de geplande sync mag die
    dus nooit overslaan.
    """
    return True


def _run_sync_once() -> dict | None:
    """
    Voer één PriceShape-sync uit (blokkerend — bedoeld voor asyncio.to_thread).
    Geeft het sync-resultaat terug, of None als PriceShape niet is geconfigureerd.
    """
    from database import BackgroundSessionLocal
    from routes.connectors import _run_sync, touch_last_synced

    # Ruime statement-timeout: de sync verwerkt honderdduizenden rijen per
    # DELETE/INSERT, wat de 4s request-timeout ver overschrijdt.
    db = BackgroundSessionLocal()
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
            # Rankings direct meevernieuwen zodat het CI Dashboard nooit
            # verouderde rankings toont na een sync. Fout-tolerant: een
            # mislukking wordt zichtbaar gelogd maar faalt de sync niet.
            from services.refresh import run_rankings_refresh
            run_rankings_refresh(db, trigger="geplande feed-sync")
        return result
    finally:
        db.close()

def _redacted_exc(exc: Exception) -> str:
    """Foutbericht zonder tokens/URL-credentials — veilig voor logs en UI."""
    try:
        from connectors.priceshape_connector import _redact
        return f"{type(exc).__name__}: {_redact(str(exc))[:500]}"
    except Exception:
        return type(exc).__name__
def _record_scheduler_failure(exc: Exception) -> None:
    """Persisteer een scheduler-fout zichtbaar voor de UI: een fout-ImportJob
    (waarop de connector-kaart 'laatste sync'-status baseert) én de
    connector-statusvelden. Gooit zelf nooit."""
    try:
        from connectors.priceshape_connector import _redact
        message = f"Geplande sync mislukt: {_redact(str(exc))[:500]}"
    except Exception:
        message = "Geplande sync mislukt."

    try:
        import models
        from database import SessionLocal
        from engine.import_engine import new_batch_id
        db_local = SessionLocal()
        try:
            db_local.add(models.ImportJob(
                batch_id=new_batch_id(),
                upload_type="api_sync_priceshape",
                filename="geplande-sync-priceshape",
                source="API-Sync",
                status="fout",
                rows_processed=0,
                rows_failed=0,
                rows_duplicates=0,
                error_log=[{"rij": None, "veld": None, "bericht": message}],
                error_message=message,
                uploaded_by=_SYSTEM_USER.username,
                created_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            ))
            db_local.commit()
        finally:
            db_local.close()
    except Exception:
        logger.warning("Feed-sync: fout-ImportJob niet kunnen opslaan.", exc_info=True)

    try:
        from routes.connectors import record_sync_status
        record_sync_status("priceshape", "error", message)
    except Exception:
        logger.warning("Feed-sync: fout-status niet kunnen registreren.", exc_info=True)
def _run_sync_with_retries(max_retries: int,
                           backoff_base: int = DEFAULT_RETRY_BACKOFF) -> None:
    """
    Probeer de sync tot `max_retries` keer met exponentiële backoff. Een mislukte
    sync laat de bestaande data altijd intact (zie feed_ingest), dus opnieuw
    proberen is veilig. Deze functie gooit nooit.

    LET OP: retries bij een tijdelijke verbindingsfout (ConnectorError) worden
    tegenwoordig door de sync ZELF gedaan (routes/connectors.py,
    `_ingest_feed_with_retry`): status 'error' is dus al het eindresultaat ná
    de interne retries. Hier niet nogmaals retryen — dat zou de pogingen
    vermenigvuldigen (12 i.p.v. 4), per poging een extra fout-ImportJob
    schrijven en de nachtsync ruim een uur laten hangen. De backoff-lus hier
    vangt alleen ONVERWACHTE exceptions uit de cyclus zelf op.
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
            logger.warning(
                "Feed-sync poging %d/%d gaf status '%s': %s",
                attempt, max_retries, status, result.get("message", ""),
            )
            if status == "not_configured":
                return  # opnieuw proberen heeft geen zin
            if status == "error":
                # De sync heeft transient fouten intern al geretried
                # (_ingest_feed_with_retry) en pas de LAATSTE mislukking als
                # ImportJob 'fout' gepersisteerd. Hier nogmaals proberen zou
                # de pogingen stapelen en extra fout-jobs schrijven.
                logger.error(
                    "Feed-sync definitief mislukt (interne retries uitgeput). "
                    "Laatst-goede data blijft actief; volgende poging bij het "
                    "volgende interval."
                )
                return
        except Exception as exc:  # noqa: BLE001 — scheduler mag nooit crashen
            # Geen logger.exception: het bericht (en de traceback) kan de
            # feed-URL incl. token bevatten. Log geredigeerd, zonder traceback.
            logger.error("Feed-sync poging %d/%d gooide een fout: %s",
                         attempt, max_retries, _redacted_exc(exc))
            # Maak de mislukking óók zichtbaar op de connector-kaart. Normaal
            # registreert _run_sync dit zelf, maar een fout die daarbuiten
            # optreedt (bijv. in de modelrun ná een geslaagde ingest) zou
            # anders stil blijven — en de kaart zou zelfs "geslaagd" tonen,
            # want die leest de nieuwste ImportJob. Bericht wordt geredigeerd
            # (geen tokens/URL's lekken).
            _record_scheduler_failure(exc)

        if attempt < max_retries:
            backoff = _backoff_seconds(attempt, backoff_base)  # 60s, 120s, 240s … max 10 min
            logger.info("Feed-sync: volgende poging over %ds.", backoff)
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
    backoff_base = _int_env("FEED_SYNC_RETRY_BACKOFF", DEFAULT_RETRY_BACKOFF)

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
            await asyncio.to_thread(_run_sync_with_retries, max_retries, backoff_base)
        except asyncio.CancelledError:
            logger.info("Feed-sync scheduler gestopt.")
            raise
        except Exception as exc:  # noqa: BLE001 — scheduler mag nooit crashen
            logger.error("Feed-sync scheduler lus-fout (genegeerd): %s", _redacted_exc(exc))

        # BigQuery-export draait elke cyclus mee, onafhankelijk van het
        # feed-sync-resultaat: analisten moeten ook historische data zien als
        # de feed een keer faalt. run_nightly_sync gooit nooit, slaat over als
        # BigQuery niet is geconfigureerd en registreert fouten per tabel als
        # ImportJob (source='bigquery', zichtbaar in /api/bigquery/sync/history).
        try:
            from bigquery.sync import run_nightly_sync
            await asyncio.to_thread(run_nightly_sync)
        except asyncio.CancelledError:
            logger.info("Feed-sync scheduler gestopt.")
            raise
        except Exception as exc:  # noqa: BLE001 — scheduler mag nooit crashen
            logger.exception("BigQuery-sync lus-fout (genegeerd): %s", exc)

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Feed-sync scheduler gestopt.")
            raise


def start_feed_sync_scheduler() -> asyncio.Task:
    """Start de feed-sync scheduler als achtergrond-asyncio-taak."""
    return asyncio.create_task(_scheduler_loop())
