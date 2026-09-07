"""
Standalone nachtelijke engine-run voor een Replit **Scheduled Deployment**.

Waarom dit bestaat
------------------
De web-app draait op autoscale en wordt tussen requests gesuspend, waardoor
in-process schedulers niet werken in productie. Dit script draait de vier
commerciële engines in één keer door, zodat het als aparte Scheduled
Deployment kan worden geconfigureerd — nadat scheduled_sync.py de data
heeft ververst.

Volgorde (afhankelijkheidsvolgorde):
  1. Basket-engine      → basket-associaties
  2. Promotion-engine   → promotie-effecten
  3. Forecast/Risk-engine → dagelijkse forecasts en risicoklassen
  4. Opportunity-engine  → kansen (aggregeert signalen van bovenstaande)
  5. Categoriescores     → concurrent × categorie, vanuit recente waarnemingen
  6. CIS-engine          → Competitor Influence Scores per (SKU, concurrent)
  7. Competitor rankings → rankings op basis van verse categorie- en CIS-scores

De CIS-engine draait bewust VÓÓR de rankings: de Influence-score in de
rankings is het gemiddelde van de CIS-scores, dus verouderde CIS-rijen
zouden anders een verouderde ranking opleveren.

Foutafhandeling & idempotentie
------------------------------
Een fout in één engine wordt gelogd maar blokkeert de andere engines niet.
Het script sluit met exit-code 1 als minstens één engine mislukt is, zodat
de Scheduled Deployment als 'mislukt' wordt gemarkeerd.

Elke engine-run wordt per shop geregistreerd in scheduled_engine_runs
(succes/fout + tijdstip). Bij een herstart dezelfde dag worden shops/engines
met een succesvolle run van vandaag overgeslagen; alleen mislukte of nog
niet gedraaide combinaties worden (opnieuw) uitgevoerd. Zo herstelt een
retry na een nachtelijke fout de data zonder dubbele runs.

Run-commando (Scheduled Deployment, uitvoeren NA scheduled_sync.py):
    cd artifacts/api-server && python scheduled_engines.py
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import date, datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s scheduled_engines: %(message)s",
)
logger = logging.getLogger("scheduled_engines")


def _run_engine(name: str, fn, db, models, shop_id: int, run_date: date) -> bool:
    """
    Voer één engine uit, registreer de uitkomst in scheduled_engine_runs
    (idempotente herstart) én in engine_runs (dashboard-status), en
    retourneer True bij succes, False bij fout.
    """
    started_at = datetime.utcnow()
    record = models.ScheduledEngineRun(
        run_date=run_date, shop_id=shop_id, engine_name=name,
        status="running", started_at=started_at,
    )
    db.add(record)
    db.commit()

    t0 = time.monotonic()
    try:
        result = fn(db, run_date=run_date, shop_id=shop_id)
        db.commit()
        record.status = "success"
        summary = result if isinstance(result, (dict, list)) else {"result": str(result)}
        record.result_summary = summary if isinstance(summary, dict) else {"result": summary}
        logger.info("[%s] shop=%d klaar: %s", name, shop_id, result)
        _log_run(db, name=name, shop_id=shop_id, started_at=started_at,
                 status="success", result_summary=record.result_summary)
        ok = True
    except Exception as exc:
        db.rollback()
        record.status = "failed"
        record.error_message = f"{type(exc).__name__}: {exc}"[:4000]
        logger.exception("[%s] shop=%d mislukt — overige engines gaan door.", name, shop_id)
        _log_run(db, name=name, shop_id=shop_id, started_at=started_at,
                 status="failed", error_message=record.error_message)
        ok = False

    record.completed_at = datetime.utcnow()
    record.duration_seconds = round(time.monotonic() - t0, 2)
    try:
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[%s] shop=%d run-registratie kon niet worden opgeslagen.", name, shop_id)
    return ok


def main() -> int:
    from database import SessionLocal, engine as db_engine
    import models

    # Zorg dat alle tabellen bestaan (no-op als ze al aanwezig zijn).
    models.Base.metadata.create_all(bind=db_engine)

    db = SessionLocal()
    try:
        # Haal alle actieve shops op.
        shops = db.query(models.DimShop).filter(models.DimShop.active == True).all()  # noqa: E712
        if not shops:
            logger.warning("Geen actieve shops gevonden — engines overgeslagen.")
            return 0

        # Snapshot id/code als platte waardes: commits in de engine-loop
        # expiren ORM-instanties, en een tussentijds verwijderde shop-rij
        # zou anders de hele run met ObjectDeletedError afbreken.
        shop_infos = [(s.id, s.shop_code) for s in shops]

        logger.info("Nachtelijke engine-run gestart voor %d shop(s): %s",
                    len(shop_infos), [code for _, code in shop_infos])

        from engine.basket_engine import run_basket_engine
        from engine.promotion_engine import run_promotion_engine
        from engine.forecast_engine import run_forecast_engine
        from engine.opportunity_engine import run_opportunity_engine
        from engine.competitor_scores import run_competitor_scores
        from engine.category_competition import calculate_all_category_scores
        from engine.competitor_influence import run_cis_engine
        from engine.competition_rankings import run_competitor_rankings

        def _category_scores(db, run_date=None, shop_id=None):
            return {"category_scores": calculate_all_category_scores(db, shop_id=shop_id)}

        def _cis(db, run_date=None, shop_id=None):
            sku_ids = [sku for (sku,) in db.query(models.DimProduct.sku_id).filter(
                models.DimProduct.shop_id == shop_id).all()]
            return {"cis_scores": run_cis_engine(
                db, ref_date=run_date, sku_ids=sku_ids)}

        def _rankings(db, run_date=None, shop_id=None):
            return {"rankings": run_competitor_rankings(
                db, ref_date=run_date, shop_id=shop_id)}

        engines = [
            ("basket",    run_basket_engine),
            ("promotion", run_promotion_engine),
            ("forecast",  run_forecast_engine),
            ("opportunity", run_opportunity_engine),
            # Concurrentscores vóór de globale rankings-stap: de rankings
            # gebruiken Business Strength als ondersteunende dimensie.
            ("competitor_scores", run_competitor_scores),
            ("category_scores", _category_scores),
            ("cis", _cis),
            ("rankings", _rankings),
        ]

        run_date = date.today()
        failures = 0
        skipped = 0
        for shop_id, shop_code in shop_infos:
            logger.info("=== Shop %s (id=%d) ===", shop_code, shop_id)
            # Dependency-bewust: de engines staan in afhankelijkheidsvolgorde.
            # Zodra een upstream engine in DEZE aanroep (opnieuw) gedraaid
            # heeft, mogen downstream engines niet worden overgeslagen — hun
            # eerdere 'succes' was op verouderde upstream-data gebaseerd
            # (bv. opportunity op T-2 forecasts).
            upstream_reran = False
            competition_chain_failed = False
            for engine_name, engine_fn in engines:
                if competition_chain_failed and engine_name in ("cis", "rankings"):
                    logger.error("[%s] shop=%d overgeslagen door mislukte upstreamstap.",
                                 engine_name, shop_id)
                    continue
                if not upstream_reran and _has_successful_run(db, models, run_date, shop_id, engine_name):
                    logger.info("[%s] shop=%d overgeslagen: vandaag al succesvol gedraaid.",
                                engine_name, shop_id)
                    skipped += 1
                    continue
                upstream_reran = True
                ok = _run_engine(engine_name, engine_fn, db, models, shop_id, run_date)
                if not ok:
                    failures += 1
                    if engine_name in ("category_scores", "cis"):
                        competition_chain_failed = True

        if skipped:
            logger.info("%d engine-run(s) overgeslagen (idempotente herstart).", skipped)

        if failures:
            logger.error(
                "Nachtelijke engine-run voltooid met %d mislukte engine-run(s).", failures
            )
            return 1

        logger.info("Nachtelijke engine-run volledig succesvol afgerond.")
        return 0

    except Exception:
        db.rollback()
        logger.exception("Nachtelijke engine-run onverwacht afgebroken.")
        return 1
    finally:
        db.close()


def _has_successful_run(db, models, run_date: date, shop_id: int, name: str) -> bool:
    """True als de MEEST RECENTE poging van deze engine vandaag succesvol was.

    De laatste poging telt: een oude succes-rij mag een latere mislukking
    (bijv. een geforceerde downstream-rerun die faalde) niet maskeren, anders
    wordt een noodzakelijke herstart permanent overgeslagen.
    """
    latest = db.query(models.ScheduledEngineRun.status).filter(
        models.ScheduledEngineRun.run_date == run_date,
        models.ScheduledEngineRun.shop_id == shop_id,
        models.ScheduledEngineRun.engine_name == name,
    ).order_by(models.ScheduledEngineRun.id.desc()).first()
    return latest is not None and latest[0] == "success"


def _log_run(db, *, name: str, shop_id: int, started_at, status: str,
             error_message: str | None = None, result_summary=None) -> None:
    """Schrijf een EngineRun-rij weg zodat het dashboard de run-status kan tonen.

    Logging mag de run zelf nooit laten falen; fouten worden alleen gelogd.
    """
    import models
    try:
        db.add(models.EngineRun(
            engine_name=name,
            shop_id=shop_id,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            status=status,
            error_message=error_message,
            result_summary=result_summary,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[%s] shop=%d run-log kon niet worden weggeschreven.", name, shop_id)
