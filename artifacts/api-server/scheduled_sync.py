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
from datetime import datetime, timezone
from types import SimpleNamespace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s scheduled_sync: %(message)s",
)
logger = logging.getLogger("scheduled_sync")

_SYSTEM_USER = SimpleNamespace(username="system-scheduled")


def main() -> int:
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

        # last_synced_at atomisch bijwerken zodat de UI "laatste sync" toont,
        # ook bij env-only configuratie (dan bestaat er nog geen config-rij).
        touch_last_synced(db, "priceshape")

        now = datetime.now(timezone.utc)
        logger.info("Stap 2/4: pricing engine draaien ...")
        from engine.pricing_engine import run_pricing_engine
        processed, skipped = run_pricing_engine(db)
        logger.info("Pricing engine klaar: %d verwerkt, %d overgeslagen.", processed, skipped)

        import feed_ingest
        logger.info("Stap 3/4: concurrentie-scores (PCIS) berekenen ...")
        feed_ingest.score_competition(db)
        logger.info("Stap 4/4: AI-matches opbouwen ...")
        feed_ingest.build_ai_matches(db)

        # Registreer een ModelRun zodat /model-health de geplande refresh toont.
        run = models.ModelRun(
            started_at=now,
            completed_at=datetime.now(timezone.utc),
            status="completed",
            skus_processed=processed,
            skus_skipped=skipped,
            model_version="scheduled-v1.0.0",
        )
        db.add(run)
        db.commit()

        logger.info("Geplande PriceShape-refresh volledig voltooid.")
        return 0
    except Exception:
        db.rollback()
        logger.exception("Geplande PriceShape-refresh mislukt — bestaande data blijft intact.")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
