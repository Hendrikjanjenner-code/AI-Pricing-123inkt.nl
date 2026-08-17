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

Foutafhandeling
---------------
Een fout in één engine wordt gelogd maar blokkeert de andere engines niet.
Het script sluit met exit-code 1 als minstens één engine mislukt is, zodat
de Scheduled Deployment als 'mislukt' wordt gemarkeerd.

Run-commando (Scheduled Deployment, uitvoeren NA scheduled_sync.py):
    cd artifacts/api-server && python scheduled_engines.py
"""
from __future__ import annotations

import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s scheduled_engines: %(message)s",
)
logger = logging.getLogger("scheduled_engines")


def _run_engine(name: str, fn, db, shop_id: int) -> bool:
    """Voer één engine uit en retourneer True bij succes, False bij fout."""
    try:
        result = fn(db, run_date=date.today(), shop_id=shop_id)
        db.commit()
        logger.info("[%s] shop=%d klaar: %s", name, shop_id, result)
        return True
    except Exception:
        db.rollback()
        logger.exception("[%s] shop=%d mislukt — overige engines gaan door.", name, shop_id)
        return False


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

        logger.info("Nachtelijke engine-run gestart voor %d shop(s): %s",
                    len(shops), [s.shop_code for s in shops])

        from engine.basket_engine import run_basket_engine
        from engine.promotion_engine import run_promotion_engine
        from engine.forecast_engine import run_forecast_engine
        from engine.opportunity_engine import run_opportunity_engine

        engines = [
            ("basket",    run_basket_engine),
            ("promotion", run_promotion_engine),
            ("forecast",  run_forecast_engine),
            ("opportunity", run_opportunity_engine),
        ]

        failures = 0
        for shop in shops:
            logger.info("=== Shop %s (id=%d) ===", shop.shop_code, shop.id)
            for engine_name, engine_fn in engines:
                ok = _run_engine(engine_name, engine_fn, db, shop.id)
                if not ok:
                    failures += 1

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


if __name__ == "__main__":
    sys.exit(main())
