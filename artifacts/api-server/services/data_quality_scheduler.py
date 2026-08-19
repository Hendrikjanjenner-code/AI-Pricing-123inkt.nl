"""
Datakwaliteits-scan scheduler — draait de §30-detecties periodiek (standaard
dagelijks) op de achtergrond, zodat het issue-register actueel blijft zonder
dat iemand het Data Quality Center hoeft te openen. Nieuwe of verergerende
error-issues publiceren een IntelligenceSignal en notificeren de toegewezen
eigenaar (zie services/data_quality_scan.py).

Ontwerp (zelfde patroon als feed_sync_scheduler): een asyncio-taak die in de
FastAPI-lifespan wordt gestart; de blokkerende scan draait in een thread
(asyncio.to_thread). De taak vangt alle fouten af en crasht nooit.

Productie/autoscale: op autoscale-deployments (die tussen requests slapen)
kan een in-process scheduler niet betrouwbaar draaien. Zet daar
DISABLE_DATA_QUALITY_SCAN=true en laat een Scheduled Deployment
`python -m services.data_quality_scheduler` (one-shot mode) aanroepen —
dezelfde scanlogica, zonder proces dat wakker moet blijven. Op een Reserved
VM (huidige deploy) werkt de in-process variant gewoon.

Omgevingsvariabelen:
  DISABLE_DATA_QUALITY_SCAN     — true om de periodieke scan uit te schakelen
  DATA_QUALITY_SCAN_INTERVAL    — interval in seconden (standaard 86400 = 24 uur)
  DATA_QUALITY_SCAN_STARTUP_DELAY — aanloopvertraging (standaard 90 s)
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("uvicorn.error")

DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60
DEFAULT_STARTUP_DELAY = 90


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        return val if val > 0 else default
    except ValueError:
        return default


def ensure_schema() -> None:
    """
    Zorg dat de benodigde tabellen (o.a. data_quality_scan_run) bestaan.

    Nodig voor de one-shot mode op een Scheduled Deployment: die draait
    buiten de FastAPI-lifespan om, dus create_all/migraties zijn daar nog
    niet gebeurd (bijv. de allereerste run na een deploy).
    """
    from database import Base, engine
    from migrate import run_migrations
    import models  # noqa: F401 — registreert alle ORM-tabellen op Base.metadata

    Base.metadata.create_all(bind=engine)
    run_migrations(engine, Base.metadata)


def run_scan_once() -> bool:
    """
    Voer één datakwaliteits-scan uit (blokkerend — voor asyncio.to_thread of
    als one-shot vanuit een Scheduled Deployment).

    Geeft True bij succes en False bij een mislukte scan; gooit zelf nooit,
    zodat de in-process lus veilig kan blijven draaien. De one-shot mode
    vertaalt False naar een exitcode ≠ 0 zodat een Scheduled Deployment de
    mislukking zichtbaar rapporteert.
    """
    from services.data_quality_scan_scheduler import run_scan_once as scan_with_job

    try:
        summary = scan_with_job()
        logger.info(
            "Datakwaliteits-scan klaar: %d issues, %d nieuw, %d heropend.",
            summary["detected"], len(summary["new"]), len(summary["reopened"]),
        )
        return True
    except Exception as exc:  # noqa: BLE001 — in-process lus mag nooit crashen
        logger.exception("Datakwaliteits-scan mislukt (volgende interval opnieuw): %s", exc)
        return False


def main_oneshot() -> int:
    """
    One-shot entrypoint voor een Scheduled Deployment: schema-bootstrap,
    één scan, exitcode 0 bij succes en 1 bij een mislukking (zodat de
    geplande taak zichtbaar faalt in plaats van stilletjes 'geslaagd').
    """
    try:
        ensure_schema()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Datakwaliteits-scan: schema-bootstrap mislukt: %s", exc)
        return 1
    return 0 if run_scan_once() else 1


async def _scheduler_loop() -> None:
    interval = _int_env("DATA_QUALITY_SCAN_INTERVAL", DEFAULT_INTERVAL_SECONDS)
    startup_delay = _int_env("DATA_QUALITY_SCAN_STARTUP_DELAY", DEFAULT_STARTUP_DELAY)

    logger.info("Datakwaliteits-scan scheduler gestart (interval=%ds).", interval)

    try:
        await asyncio.sleep(min(startup_delay, interval))
    except asyncio.CancelledError:
        logger.info("Datakwaliteits-scan scheduler gestopt.")
        raise

    while True:
        try:
            await asyncio.to_thread(run_scan_once)
        except asyncio.CancelledError:
            logger.info("Datakwaliteits-scan scheduler gestopt.")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Datakwaliteits-scan scheduler lus-fout (genegeerd): %s", exc)

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Datakwaliteits-scan scheduler gestopt.")
            raise


def start_data_quality_scheduler() -> asyncio.Task:
    """Start de datakwaliteits-scan scheduler als achtergrond-asyncio-taak."""
    return asyncio.create_task(_scheduler_loop())


if __name__ == "__main__":
    # One-shot mode voor een Scheduled Deployment (autoscale-vriendelijk):
    # draait één scan en stopt met exitcode 0/1.
    # Gebruik: python -m services.data_quality_scheduler
    import sys
    logging.basicConfig(level=logging.INFO)
    sys.exit(main_oneshot())
