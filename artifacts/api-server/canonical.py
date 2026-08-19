"""
Canonical model bootstrap: default shop + shop_id backfill.

Het platform is multi-shop voorbereid (masterprompt §36). Deze module zorgt
idempotent bij elke start dat:
1. de default shop (id=1) bestaat;
2. bestaande rijen zonder shop_id worden ge-backfilled naar de default shop.

Backfill is puur additief (UPDATE ... WHERE shop_id IS NULL) en verwijdert
nooit data.
"""
import logging
from sqlalchemy import text
from database import SessionLocal
import models

logger = logging.getLogger("uvicorn.error")

DEFAULT_SHOP_CODE = "main"

# Tabellen met een shop_id kolom die ge-backfilled moeten worden.
_SHOP_SCOPED_TABLES = [
    "dim_product",
    "fact_sales_daily",
    "fact_price_daily",
    "fact_competitor_price_daily",
    "fact_inventory_daily",
    "fact_pricing_recommendation_daily",
    "intelligence_signals",
]


def ensure_default_shop() -> None:
    """Maak de default shop aan als die nog niet bestaat en backfill shop_id."""
    db = SessionLocal()
    try:
        shop = db.query(models.DimShop).filter(
            models.DimShop.shop_code == DEFAULT_SHOP_CODE
        ).first()
        if not shop:
            shop = models.DimShop(
                shop_code=DEFAULT_SHOP_CODE,
                name="Hoofdshop",
                country="NL",
                currency="EUR",
                legal_entity=None,
                channel="online",
                is_default=True,
                active=True,
            )
            db.add(shop)
            db.commit()
            db.refresh(shop)
            logger.info("Canonical: default shop aangemaakt (id=%s).", shop.id)

        # Er mag precies één default shop zijn.
        db.query(models.DimShop).filter(
            models.DimShop.id != shop.id,
            models.DimShop.is_default.is_(True),
        ).update({"is_default": False})
        if not shop.is_default:
            shop.is_default = True
        db.commit()

        # Dedupe-garantie op DB-niveau: maximaal één actief signaal per
        # dedupe_key per shop, ook bij gelijktijdige publishers.
        try:
            db.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_active_dedupe "
                "ON intelligence_signals (dedupe_key, shop_id) "
                "WHERE status = 'active'"
            ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Canonical: kon unieke signaal-index niet aanmaken: %s", exc)

        # Hiërarchie-backfill (taak #217): vul hierarchy_node_id/path/level op
        # bestaande SKU-signalen vanuit de actieve primaire assignment.
        # Idempotent: alleen rijen waar hierarchy_node_id nog NULL is.
        try:
            db.execute(text(
                "UPDATE intelligence_signals SET hierarchy_node_id = ("
                "  SELECT a.node_id FROM product_hierarchy_assignments a"
                "  WHERE a.sku_id = intelligence_signals.entity_id"
                "    AND a.status = 'active' AND a.is_primary = TRUE"
                "  ORDER BY a.id DESC LIMIT 1)"
                " WHERE entity_type = 'sku' AND hierarchy_node_id IS NULL"
            ))
            db.execute(text(
                "UPDATE intelligence_signals SET hierarchy_level = ("
                "  SELECT n.level FROM product_hierarchy_nodes n"
                "  WHERE n.id = intelligence_signals.hierarchy_node_id)"
                " WHERE hierarchy_node_id IS NOT NULL AND hierarchy_level IS NULL"
            ))
            db.execute(text(
                "UPDATE intelligence_signals SET hierarchy_path_id = ("
                "  SELECT p.id FROM product_hierarchy_paths p"
                "  WHERE p.leaf_node_id = intelligence_signals.hierarchy_node_id)"
                " WHERE hierarchy_node_id IS NOT NULL AND hierarchy_path_id IS NULL"
            ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Canonical: hiërarchie-backfill van signalen overgeslagen: %s", exc)

        backfilled_total = 0
        for table in _SHOP_SCOPED_TABLES:
            try:
                result = db.execute(text(
                    f'UPDATE "{table}" SET shop_id = :shop_id WHERE shop_id IS NULL'
                ), {"shop_id": shop.id})
                db.commit()
                if result.rowcount:
                    backfilled_total += result.rowcount
                    logger.info(
                        "Canonical: %d rijen in %s ge-backfilled naar shop %s.",
                        result.rowcount, table, shop.id,
                    )
            except Exception as exc:
                db.rollback()
                logger.warning("Canonical: backfill van %s overgeslagen: %s", table, exc)

        if backfilled_total:
            logger.info("Canonical: totaal %d rijen ge-backfilled.", backfilled_total)
    except Exception as exc:
        db.rollback()
        logger.error("Canonical: ensure_default_shop faalde (niet-fataal): %s", exc)
    finally:
        db.close()


def get_default_shop_id(db) -> int:
    """Geef het id van de default shop terug (fallback 1)."""
    shop = db.query(models.DimShop).filter(models.DimShop.is_default.is_(True)).first()
    return shop.id if shop else 1
