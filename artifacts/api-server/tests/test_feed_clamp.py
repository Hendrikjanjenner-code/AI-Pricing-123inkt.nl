"""
Taak #260: de feed-import mag nooit crashen op te lange stringwaarden
("value too long for type character varying(N)").

Dekt:
  1. clamp_rows_to_model kapt te lange waarden af op de kolombreedte, bewaart
     het origineel in raw_attributes en levert een waarschuwing op.
  2. Een volledige ingest_feed-run met een te lange EAN-waarde slaagt: het
     product wordt opgeslagen (afgekapt), en de waarschuwing zit in het
     resultaat zodat _run_sync hem in het ImportJob-logboek zet.
"""
import uuid

import pytest

import feed_ingest
import models
from database import SessionLocal


def test_clamp_rows_to_model_truncates_and_warns():
    long_ean = "9" * 80  # dim_product.ean is varchar(50)
    rows = [{
        "sku_id": "SKU-CLAMP-1",
        "product_name": "Testproduct",
        "ean": long_ean,
        "raw_attributes": {"foo": "bar"},
    }]
    warnings: list[str] = []
    feed_ingest.clamp_rows_to_model(models.DimProduct, rows, warnings)

    assert rows[0]["ean"] == long_ean[:50]
    # Origineel verliesvrij bewaard
    assert rows[0]["raw_attributes"]["_ean_full"] == long_ean
    assert rows[0]["raw_attributes"]["foo"] == "bar"
    assert len(warnings) == 1
    assert "ean" in warnings[0] and "50" in warnings[0]


def test_clamp_covers_all_bounded_string_columns():
    # Structureel: elke begrensde stringkolom van het model wordt gedekt,
    # dus een toekomstige nieuwe varchar-kolom kan dit niet opnieuw breken.
    limits = feed_ingest._string_limits(models.DimProduct)
    assert "ean" in limits and limits["ean"] == 50
    assert "lifecycle_status" in limits
    row = {name: "x" * (limit + 10) for name, limit in limits.items()}
    warnings = feed_ingest.clamp_rows_to_model(models.DimProduct, [row])
    for name, limit in limits.items():
        assert len(row[name]) == limit, name
    assert len(warnings) == len(limits)


def test_ingest_feed_quarantines_oversized_sku_without_touching_others():
    """Identiteit wordt nooit afgekapt: twee verschillende >100-tekens sku's
    met identiek 100-tekens prefix worden overgeslagen (met waarschuwing) en
    mogen een bestaand product met datzelfde prefix niet overschrijven."""
    prefix = "7" * 100
    long_a, long_b = prefix + "111", prefix + "222"
    db = SessionLocal()
    try:
        # Bestaand product waarvan de sku exact het 100-tekens prefix is.
        db.add(models.DimProduct(sku_id=prefix, product_name="Bestaand product",
                                 current_price=9.99, shop_id=1))
        db.commit()

        csv = (
            "gtin,productTitle,priceInclVat,domain,price\n"
            f"{long_a},Kwarantaine A,10.00,concurrent-q.nl,9.00\n"
            f"{long_b},Kwarantaine B,11.00,concurrent-q.nl,10.00\n"
            "1234567890123,Geldig product,5.00,concurrent-q.nl,4.50\n"
        ).encode()
        res = feed_ingest.ingest_feed(db, content=csv, content_type="text/csv")

        # Alleen het geldige product is verwerkt; de import crasht niet.
        assert res["products_total"] == 1
        assert any("overgeslagen" in w and "sku" in w.lower()
                   for w in res["warnings"]), res["warnings"]

        # Het bestaande product met het prefix is NIET overschreven.
        db.expire_all()
        existing = db.get(models.DimProduct, prefix)
        assert existing.product_name == "Bestaand product"
        # En er zijn geen concurrentrijen aan het prefix-product gehangen.
        assert db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == prefix).count() == 0
    finally:
        db.rollback()
        for sku in (prefix, "1234567890123"):
            db.query(models.FactCompetitorPriceDaily).filter(
                models.FactCompetitorPriceDaily.sku_id == sku).delete()
            db.query(models.FactPriceDaily).filter(
                models.FactPriceDaily.sku_id == sku).delete()
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id == sku).delete()
        db.commit()
        db.close()


def test_ingest_feed_survives_too_long_values():
    """End-to-end: platte CSV-feed met een 80-tekens EAN → import slaagt,
    waarde afgekapt opgeslagen, waarschuwing in het resultaat."""
    long_ean = "8" * 80
    csv = (
        "gtin,productTitle,priceInclVat,domain,price\n"
        f"{long_ean},Clamp Testproduct,19.99,concurrent-a.nl,18.50\n"
    ).encode()

    db = SessionLocal()
    sku = long_ean[:100]  # sku_id is varchar(100)
    try:
        res = feed_ingest.ingest_feed(db, content=csv, content_type="text/csv")
        assert res["products_total"] == 1
        assert any("ean" in w for w in res["warnings"]), res["warnings"]

        prod = db.get(models.DimProduct, sku)
        assert prod is not None
        assert prod.ean == long_ean[:50]
        assert prod.raw_attributes["_ean_full"] == long_ean

        comp = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == sku).all()
        assert len(comp) == 1
        assert comp[0].competitor_name == "concurrent-a.nl"
    finally:
        # Teardown: alle rijen van dit synthetische product opruimen.
        db.rollback()
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == sku).delete()
        db.query(models.FactPriceDaily).filter(
            models.FactPriceDaily.sku_id == sku).delete()
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == sku).delete()
        db.commit()
        db.close()
