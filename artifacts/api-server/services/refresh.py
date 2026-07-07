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


def run_model_refresh(db, model_version: str = "autosync-v1.0.0") -> tuple[int, int]:
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
    feed_ingest.score_competition(db)

    logger.info("Modelrun: AI-matches opbouwen ...")
    feed_ingest.build_ai_matches(db)

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

    return processed, skipped
