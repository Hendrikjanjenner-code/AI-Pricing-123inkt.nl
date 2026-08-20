"""
Gedeelde "volledige modelrun"-logica na een PriceShape-ingest.

Na het inlezen van de feed (concurrentprijzen + producten) moet ook de rest
worden herberekend zodat de hele app meevernieuwt:
  - de pricing engine (aanbevelingen),
  - de concurrentie-scores / PCIS (CI Dashboard, `sku_competition_score`),
  - de AI-matches (GTIN/EAN concurrent-matching),
en er wordt een `ModelRun` geregistreerd zodat /model-health de refresh toont.

Deze functie wordt gebruikt door zowel:
  - de in-process feed-sync scheduler (`services/feed_sync_scheduler.py`), die
    op een Reserved VM ("altijd aan") elke FEED_SYNC_INTERVAL draait, als
  - het standalone `scheduled_sync.py`-script (voor een Scheduled Deployment).

Zo doen beide paden gegarandeerd exact dezelfde refresh.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("uvicorn.error")


def run_model_refresh(db, model_version: str = "autosync-v1.0.0",
                      shop_id: int = 1) -> tuple[int, int]:
    """
    Draai de volledige modelrun op een reeds-geopende sessie en registreer een
    ModelRun. Geeft (verwerkt, overgeslagen) terug.

    Gooit door bij een fout (de aanroeper beslist over rollback/retry). De
    voorafgaande ingest is non-destructief, dus opnieuw proberen is veilig.
    """
    from engine.pricing_engine import run_pricing_engine
    import feed_ingest
    import models

    started = datetime.now(timezone.utc)

    logger.info("Modelrun: pricing engine draaien ...")
    processed, skipped = run_pricing_engine(db)
    logger.info("Pricing engine klaar: %d verwerkt, %d overgeslagen.", processed, skipped)

    logger.info("Modelrun: concurrentie-scores (PCIS) berekenen ...")
    feed_ingest.score_competition(db, shop_id=shop_id)

    logger.info("Modelrun: AI-matches opbouwen ...")
    feed_ingest.build_ai_matches(db, shop_id=shop_id)

    db.add(
        models.ModelRun(
            started_at=started,
            completed_at=datetime.now(timezone.utc),
            status="completed",
            skus_processed=processed,
            skus_skipped=skipped,
            model_version=model_version,
        )
    )
    db.commit()

    # Automatische hiërarchie uit feed-categorieën actueel houden (taak #274).
    # In een EIGEN sessie ná de ModelRun-commit: een fout of rollback hier kan
    # de zojuist vastgelegde modelrun-resultaten nooit meer raken, en de
    # modelrun wordt niet ten onrechte als geslaagd geregistreerd terwijl zijn
    # werk is teruggedraaid.
    try:
        from services.hierarchy_autobuild import autobuild_hierarchy
        from database import SessionLocal
        hdb = SessionLocal()
        try:
            autobuild_hierarchy(hdb)
        finally:
            hdb.close()
    except Exception:
        logger.exception("Automatische hiërarchie-opbouw na sync mislukt "
                         "(modelrun zelf blijft geslaagd).")

    return processed, skipped


def run_rankings_refresh(db, shop_id: int | None = None,
                         trigger: str = "feed_sync") -> dict | None:
    """
    Herbereken CIS-scores + concurrent-rankings direct na een feed-sync, zodat
    het CI Dashboard altijd rankings toont die bij de laatste feed horen.

    Fout-tolerant: gooit NOOIT door (de feed-sync zelf mag hier niet op falen),
    maar registreert de uitkomst wel zichtbaar als EngineRun-rij
    (engine_name="rankings", status success/failed) zodat een mislukking niet
    stil verdwijnt. Retourneert een resultaat-dict bij succes, anders None.
    """
    import models
    from datetime import datetime as _dt

    started = _dt.utcnow()
    try:
        from engine.competitor_influence import run_cis_engine
        from engine.competition_rankings import run_competitor_rankings

        # Serialiseer met de feed-ingest: dezelfde advisory lock als _run_sync,
        # zodat de rankings nooit lezen terwijl een tweede sync de feed-data
        # aan het vervangen is (delete-then-insert → gemengd snapshot).
        with _feed_sync_lock() as got:
            if not got:
                raise RuntimeError(
                    "Kon de feed-sync-lock niet verkrijgen binnen de wachttijd; "
                    "rankings-refresh overgeslagen om een gemengd snapshot te voorkomen."
                )
            return _do_rankings_refresh(
                db, shop_id=shop_id, trigger=trigger, started=started,
                run_cis_engine=run_cis_engine,
                run_competitor_rankings=run_competitor_rankings)
    except Exception as exc:
        db.rollback()
        logger.exception("Rankings-refresh na %s mislukt — de feed-sync zelf blijft geslaagd.", trigger)
        _log_engine_run(db, shop_id=shop_id, started_at=started, status="failed",
                        error_message=f"{type(exc).__name__}: {exc}"[:4000])
        return None


def _feed_sync_lock():
    """Blokkerende variant van de PriceShape-sync-lock (zelfde advisory key).

    Wacht maximaal LOCK_TIMEOUT op een lopende ingest i.p.v. direct op te geven;
    levert True/False (verkregen of niet) op een eigen verbinding."""
    from contextlib import contextmanager

    @contextmanager
    def _lock():
        from sqlalchemy import text
        from database import engine
        from routes.connectors import _advisory_key
        key = _advisory_key("priceshape")
        conn = engine.connect()
        got = False
        try:
            conn.execute(text("SET lock_timeout = '600s'"))
            try:
                conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
                got = True
            except Exception:
                got = False
            yield got
        finally:
            try:
                if got:
                    conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                    conn.commit()
            except Exception:
                try:
                    conn.invalidate()
                except Exception:
                    pass
            finally:
                conn.close()

    return _lock()


def _do_rankings_refresh(db, *, shop_id, trigger, started,
                         run_cis_engine, run_competitor_rankings) -> dict:
    import models
    try:
        if shop_id is not None:
            sku_ids = [p.sku_id for p in
                       db.query(models.DimProduct.sku_id).filter(
                           models.DimProduct.shop_id == shop_id).all()]
            cis_written = run_cis_engine(db, sku_ids=sku_ids) if sku_ids else 0
        else:
            cis_written = run_cis_engine(db)
        rankings_written = run_competitor_rankings(db, shop_id=shop_id)
        result = {"trigger": trigger, "cis_scores": cis_written,
                  "rankings": rankings_written}
        logger.info("Rankings-refresh na %s klaar: %d CIS-rijen, %d ranking-rijen.",
                    trigger, cis_written, rankings_written)
        _log_engine_run(db, shop_id=shop_id, started_at=started,
                        status="success", result_summary=result)
        return result
    except Exception as exc:
        db.rollback()
        logger.exception("Rankings-refresh na %s mislukt — de feed-sync zelf blijft geslaagd.", trigger)
        _log_engine_run(db, shop_id=shop_id, started_at=started, status="failed",
                        error_message=f"{type(exc).__name__}: {exc}"[:4000])
        return None


def _log_engine_run(db, *, shop_id, started_at, status,
                    error_message=None, result_summary=None) -> None:
    """EngineRun-rij voor de rankings-refresh; logging faalt zelf nooit."""
    import models
    from datetime import datetime as _dt
    try:
        db.add(models.EngineRun(
            engine_name="rankings",
            shop_id=shop_id,
            started_at=started_at,
            completed_at=_dt.utcnow(),
            status=status,
            error_message=error_message,
            result_summary=result_summary,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Rankings-refresh: run-log kon niet worden weggeschreven.")
