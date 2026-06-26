"""
Scrape Scheduler — achtergrondtaak die concurrent-scrapes automatisch
uitvoert volgens het ingestelde rooster (scrape_schedule tijdsloten).

Geïmplementeerd als een asyncio-taak die in de FastAPI-lifespan wordt gestart.
De blokkerende scrape-logica draait in een thread (asyncio.to_thread) zodat de
event loop niet wordt geblokkeerd. De taak vangt alle fouten af en crasht nooit.
"""
import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("uvicorn.error")

# Hoe vaak (in seconden) we controleren of er een tijdslot 'due' is.
CHECK_INTERVAL_SECONDS = 30

# Onthoud welke (datum, tijdslot) al gedraaid zijn, zodat één slot per dag
# precies één keer afgaat — ook al checken we elke 30 seconden.
_already_ran: set[tuple[str, str]] = set()


def _get_timezone():
    """Bepaal de tijdzone voor het rooster (standaard Europe/Amsterdam)."""
    import os
    tz_name = os.environ.get("SCRAPE_TZ", "Europe/Amsterdam")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 — val terug op systeemtijd bij ontbrekende tzdata
        logger.warning("Tijdzone '%s' niet beschikbaar; gebruik systeemtijd.", tz_name)
        return None


def _now(tz):
    return datetime.now(tz) if tz else datetime.now()


def get_active_slots(db) -> list[str]:
    """Geef de actieve tijdsloten (HH:MM) gesorteerd terug."""
    from models import ScrapeSchedule
    slots = (
        db.query(ScrapeSchedule)
        .filter(ScrapeSchedule.active == True)
        .order_by(ScrapeSchedule.time_slot)
        .all()
    )
    return [s.time_slot for s in slots]


def compute_next_run(db, tz=None) -> str | None:
    """
    Bereken het eerstvolgende geplande rooster-tijdstip (ISO-string) op basis
    van de actieve tijdsloten. Geeft None als er geen actieve sloten zijn.
    """
    if tz is None:
        tz = _get_timezone()
    slots = get_active_slots(db)
    if not slots:
        return None
    now = _now(tz)
    kandidaten: list[datetime] = []
    for slot in slots:
        try:
            uur, minuut = (int(x) for x in slot.split(":"))
        except (ValueError, AttributeError):
            continue
        vandaag = now.replace(hour=uur, minute=minuut, second=0, microsecond=0)
        if vandaag <= now:
            vandaag = vandaag + timedelta(days=1)
        kandidaten.append(vandaag)
    if not kandidaten:
        return None
    return min(kandidaten).isoformat()


def get_last_automatic_run(db) -> str | None:
    """Geef het tijdstip van de laatste automatische (geplande) scrape terug."""
    from sqlalchemy import desc
    from models import FactScrapeResult
    laatste = (
        db.query(FactScrapeResult)
        .filter(FactScrapeResult.triggered_by == "scheduled")
        .order_by(desc(FactScrapeResult.scraped_at))
        .first()
    )
    return str(laatste.scraped_at) if laatste else None


def _run_due_slot(slot: str) -> None:
    """
    Draai alle scrape-enabled concurrenten voor een tijdslot. Blokkerend —
    bedoeld om via asyncio.to_thread te worden aangeroepen.
    """
    from database import SessionLocal
    from models import DimCompetitor
    from services.scraping_engine import (
        check_scraping_dependencies, run_scrape_for_competitor,
    )

    deps = check_scraping_dependencies()
    if not deps["ok"]:
        logger.warning(
            "Geplande scrape (%s) overgeslagen: %s", slot, deps["message"]
        )
        return

    db = SessionLocal()
    try:
        concurrenten = (
            db.query(DimCompetitor)
            .filter(DimCompetitor.active == True, DimCompetitor.scraping_enabled == True)
            .all()
        )
        if not concurrenten:
            logger.info("Geplande scrape (%s): geen actieve concurrenten.", slot)
            return

        logger.info(
            "Geplande scrape (%s) gestart voor %d concurrent(en).",
            slot, len(concurrenten),
        )
        for c in concurrenten:
            try:
                samenvatting = run_scrape_for_competitor(db, c, triggered_by="scheduled")
                logger.info(
                    "Geplande scrape (%s) — %s: %s",
                    slot, c.competitor_name,
                    ", ".join(samenvatting.get("statussen", [])) or samenvatting.get("status"),
                )
            except Exception as exc:  # noqa: BLE001 — één concurrent mag de rest niet stoppen
                logger.exception(
                    "Geplande scrape (%s) voor '%s' mislukte: %s",
                    slot, c.competitor_name, exc,
                )
    finally:
        db.close()


async def _scheduler_loop() -> None:
    """Hoofdlus: controleer elke CHECK_INTERVAL_SECONDS of een tijdslot due is."""
    from database import SessionLocal

    tz = _get_timezone()
    logger.info(
        "Scrape-scheduler gestart (tijdzone=%s, interval=%ds).",
        getattr(tz, "key", "systeem"), CHECK_INTERVAL_SECONDS,
    )

    while True:
        try:
            now = _now(tz)
            huidige = now.strftime("%H:%M")
            datum = now.strftime("%Y-%m-%d")

            db = SessionLocal()
            try:
                actieve_slots = get_active_slots(db)
            finally:
                db.close()

            for slot in actieve_slots:
                sleutel = (datum, slot)
                if slot == huidige and sleutel not in _already_ran:
                    _already_ran.add(sleutel)
                    # Blokkerende scrape in thread zodat de event loop vrij blijft
                    await asyncio.to_thread(_run_due_slot, slot)

            # Houd de set klein: verwijder oude dagen
            for d, s in list(_already_ran):
                if d != datum:
                    _already_ran.discard((d, s))

        except asyncio.CancelledError:
            logger.info("Scrape-scheduler gestopt.")
            raise
        except Exception as exc:  # noqa: BLE001 — scheduler mag nooit crashen
            logger.exception("Scrape-scheduler lus-fout (genegeerd): %s", exc)

        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Scrape-scheduler gestopt.")
            raise


def start_scheduler() -> asyncio.Task:
    """Start de scheduler als achtergrond-asyncio-taak en geef de Task terug."""
    return asyncio.create_task(_scheduler_loop())
