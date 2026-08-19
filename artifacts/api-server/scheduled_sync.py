"""
Standalone PriceShape refresh job for a Replit **Scheduled Deployment**.

Why this exists
---------------
The web app is published as *autoscale*, which suspends the server between
requests. The in-process background feed-sync scheduler
(`services/feed_sync_scheduler.py`) therefore never gets to run in production.
This script runs the full refresh to completion in one shot, so it can be wired
up as a separate cron-style Scheduled Deployment while the web app stays on
cost-effective autoscale.

What it does (one full refresh)
-------------------------------
  1. Ingest the PriceShape feed        -> products + competitor prices
  2. Run the pricing engine            -> recommendations
  3. Score competition (PCIS)          -> CI dashboard / competition scores
  4. Build AI matches                  -> GTIN/EAN competitor matching
  5. Record last_synced_at + a ModelRun so the UI reflects the refresh

Safety
------
Idempotent and non-destructive: `feed_ingest.ingest_feed` fetches the feed
*before* any delete and aborts on an empty feed, so a failed run never wipes
last-good data. Any error exits non-zero (so the Scheduled Deployment is marked
failed) without corrupting existing data.

Run command (Scheduled Deployment):
    cd artifacts/api-server && python scheduled_sync.py
"""
from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s scheduled_sync: %(message)s",
)
logger = logging.getLogger("scheduled_sync")

_SYSTEM_USER = SimpleNamespace(username="system-scheduled")


def _run_priceshape_refresh() -> int:
    """Stap 1-4: PriceShape-feed + modelrun. Geeft exit-code terug (0/1)."""
    from sqlalchemy import text
    from database import SessionLocal, engine
    import models

    # Ensure tables exist (no-op when already present).
    models.Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))

        from routes.connectors import (
            _get_config,
            _check_env_configured,
            _run_sync,
            touch_last_synced,
        )

        cfg = _get_config(db, "priceshape")
        env_configured = _check_env_configured("priceshape")
        if not (cfg and cfg.encrypted_credentials) and not env_configured:
            logger.warning("PriceShape is niet geconfigureerd — refresh overgeslagen.")
            return 0

        logger.info("Stap 1/4: PriceShape-feed inlezen ...")
        res = _run_sync("priceshape", db, _SYSTEM_USER)
        if res.get("status") == "skipped":
            logger.warning("Sync overgeslagen: %s", res.get("message", ""))
            return 0
        if res.get("status") != "ok":
            logger.error("Feed-sync mislukt: %s", res.get("message", ""))
            return 1
        logger.info("Feed ingelezen: %s", res.get("message", ""))

        logger.info("Stappen 2-4: modelrun (pricing engine, PCIS, AI-matches) ...")
        from services.refresh import run_model_refresh
        processed, skipped = run_model_refresh(db, model_version="scheduled-v1.0.0")
        logger.info("Modelrun klaar: %d verwerkt, %d overgeslagen.", processed, skipped)

        # Pas NA een geslaagde volledige refresh de "laatste sync"-tijd zetten,
        # zodat de UI nooit een verse tijd toont terwijl de modelrun faalde.
        # (Env-only config heeft geen config-rij; de upsert werkt dan alsnog.)
        touch_last_synced(db, "priceshape")

        # Rankings (CIS + drie-scoremodel) direct meevernieuwen zodat het
        # CI Dashboard na de nachtelijke sync actuele rankings toont.
        # Fout-tolerant: een mislukking is zichtbaar (EngineRun-rij + log)
        # maar laat de feed-refresh zelf niet falen.
        logger.info("Stap 4b: concurrent-rankings herberekenen ...")
        from services.refresh import run_rankings_refresh
        run_rankings_refresh(db, trigger="scheduled_sync")

        logger.info("Geplande PriceShape-refresh volledig voltooid.")
        return 0
    except Exception:
        db.rollback()
        logger.exception("Geplande PriceShape-refresh mislukt — bestaande data blijft intact.")
        return 1
    finally:
        db.close()


def main() -> int:
    """
    Nachtelijke run: (1) PriceShape-refresh + modelrun, (2) BigQuery-sync.

    De BigQuery-stap draait ALTIJD — ook als PriceShape niet geconfigureerd is,
    overgeslagen wordt of faalt — omdat de BigQuery-export een onafhankelijke
    nachtelijke vereiste is. Fouten per tabel worden als ImportJob
    (source='bigquery') geregistreerd (zichtbaar via /api/bigquery/sync/history).
    De exit-code is 1 zodra één van beide stappen faalt, zodat de Scheduled
    Deployment als mislukt wordt gemarkeerd.
    """
    feed_rc = _run_priceshape_refresh()

    logger.info("Stap 5: BigQuery-sync (incrementeel) ...")
    from bigquery.sync import run_nightly_sync
    bq_rc = run_nightly_sync()

    return 1 if (feed_rc != 0 or bq_rc != 0) else 0


if __name__ == "__main__":
    sys.exit(main())
