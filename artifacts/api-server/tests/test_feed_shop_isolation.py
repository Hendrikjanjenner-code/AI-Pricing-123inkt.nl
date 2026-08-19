"""
Twee-winkel-isolatietest voor de feed-sync (taak 85): bewijst dat een
PriceShape-sync voor winkel A NOOIT rijen van winkel B wist of overschrijft.

Dekt specifiek de replace-deletes in `feed_ingest.ingest_feed`
(fact_price_daily, fact_competitor_price_daily) en `_persist_offers`
(fact_competitor_offer_daily), plus de product-upsert (dim_product).
"""
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal
import models
import feed_ingest

PFX = f"T85-{uuid.uuid4().hex[:6]}"
SKU_A = f"{PFX}-A1"
SKU_B = f"{PFX}-B1"
COMP = f"{PFX.lower()}-comp.nl"  # zelfde concurrent in beide winkels

# Feed voor winkel A: één product met één vendor mét voorraaddata, zodat ook
# het offers-pad (_persist_offers) daadwerkelijk draait.
FEED_A = [{
    "gtin": SKU_A,
    "productTitle": "Shop A Product",
    "priceInclVat": "19.99",
    "costPriceExclVat": "9.00",
    "vendors": [{
        "domain": COMP, "price": "18.50",
        "productUrl": "https://a.example/p", "inStock": "true",
        "deliveryDays": "2",
    }],
}]


@pytest.fixture(scope="module")
def seeded():
    """Shop B met eigen product, dagprijs, concurrentprijs (source=priceshape)
    en beschikbaarheidsrij — alles wat een sync voor A zou kunnen raken."""
    db = SessionLocal()
    today = date.today()
    shop_b = models.DimShop(shop_code=f"{PFX}-b", name=f"{PFX} Shop B")
    db.add(shop_b)
    db.flush()
    sid_b = shop_b.id

    db.add(models.DimProduct(sku_id=SKU_B, product_name="Shop B Product",
                             current_price=50.0, cost_price=25.0,
                             price_incl_vat=50.0, shop_id=sid_b,
                             import_source="seed-b"))
    db.add(models.FactPriceDaily(date=today, sku_id=SKU_B, price=50.0,
                                 cost_price=25.0, shop_id=sid_b))
    db.add(models.FactCompetitorPriceDaily(
        date=today, sku_id=SKU_B, competitor_name=COMP, price=48.0,
        source="priceshape", in_stock=True, shop_id=sid_b))
    comp = db.query(models.DimCompetitor).filter(
        models.DimCompetitor.competitor_name == COMP).first()
    if comp is None:
        comp = models.DimCompetitor(competitor_name=COMP)
        db.add(comp)
        db.flush()
    db.add(models.FactCompetitorOfferDaily(
        date=today, own_sku_id=SKU_B, competitor_id=comp.competitor_id,
        competitor_price_inc_vat=48.0, in_stock=True, delivery_days=3,
        match_type="Exact", source="priceshape"))
    db.commit()
    yield sid_b, comp.competitor_id

    db.query(models.FactCompetitorOfferDaily).filter(
        models.FactCompetitorOfferDaily.own_sku_id.like(f"{PFX}%")).delete(
        synchronize_session=False)
    db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.sku_id.like(f"{PFX}%")).delete(
        synchronize_session=False)
    db.query(models.FactPriceDaily).filter(
        models.FactPriceDaily.sku_id.like(f"{PFX}%")).delete(synchronize_session=False)
    db.query(models.SkuCompetitionScore).filter(
        models.SkuCompetitionScore.sku_id.like(f"{PFX}%")).delete(
        synchronize_session=False)
    db.query(models.AiMatchResult).filter(
        models.AiMatchResult.own_sku_id.like(f"{PFX}%")).delete(
        synchronize_session=False)
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.like(f"{PFX}%")).delete(synchronize_session=False)
    db.query(models.DimCompetitor).filter(
        models.DimCompetitor.competitor_name == COMP).delete(synchronize_session=False)
    b = db.query(models.DimShop).filter(models.DimShop.shop_code == f"{PFX}-b").first()
    if b:
        db.query(models.CostUsageRecord).filter(
            models.CostUsageRecord.shop_id == b.id).delete(synchronize_session=False)
        db.query(models.DimShop).filter(models.DimShop.id == b.id).delete(
            synchronize_session=False)
    db.commit()
    db.close()


def _snapshot_b(db, sid_b, comp_id):
    today = date.today()
    prod = db.query(models.DimProduct).filter(models.DimProduct.sku_id == SKU_B).first()
    price = db.query(models.FactPriceDaily).filter(
        models.FactPriceDaily.sku_id == SKU_B,
        models.FactPriceDaily.date == today).all()
    comp = db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.sku_id == SKU_B,
        models.FactCompetitorPriceDaily.date == today).all()
    offers = db.query(models.FactCompetitorOfferDaily).filter(
        models.FactCompetitorOfferDaily.own_sku_id == SKU_B,
        models.FactCompetitorOfferDaily.date == today).all()
    return prod, price, comp, offers


def test_sync_for_shop_a_leaves_shop_b_untouched(seeded, monkeypatch):
    sid_b, comp_id = seeded
    db = SessionLocal()
    try:
        monkeypatch.setattr(
            feed_ingest, "_read_feed",
            lambda *a, **k: feed_ingest._normalize(iter(FEED_A)))
        res = feed_ingest.ingest_feed(db, source="priceshape", shop_id=1)
        assert res["products_total"] == 1
        assert res["competitor_rows"] == 1
        assert res["offer_rows"] == 1
        db.expire_all()

        # Winkel B: product onaangeroerd (naam, prijzen, bron, shop_id).
        prod_b, price_b, comp_b, offers_b = _snapshot_b(db, sid_b, comp_id)
        assert prod_b is not None
        assert prod_b.shop_id == sid_b
        assert prod_b.product_name == "Shop B Product"
        assert float(prod_b.current_price) == 50.0
        assert prod_b.import_source == "seed-b"

        # Dagprijs van B blijft staan ondanks de replace-delete van vandaag.
        assert len(price_b) == 1 and float(price_b[0].price) == 50.0
        assert price_b[0].shop_id == sid_b

        # Concurrentprijs van B (zelfde datum, zelfde bron, zelfde concurrent!)
        # blijft staan.
        assert len(comp_b) == 1 and float(comp_b[0].price) == 48.0
        assert comp_b[0].shop_id == sid_b

        # Beschikbaarheidsrij van B (zelfde datum/bron/concurrent) blijft staan.
        assert len(offers_b) == 1 and offers_b[0].delivery_days == 3

        # En de A-rijen zijn wél geschreven, in winkel 1.
        prod_a = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_A).first()
        assert prod_a is not None and prod_a.shop_id == 1
        row_a = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == SKU_A).first()
        assert row_a is not None and row_a.shop_id == 1
        daily_a = db.query(models.FactPriceDaily).filter(
            models.FactPriceDaily.sku_id == SKU_A,
            models.FactPriceDaily.date == date.today()).first()
        assert daily_a is not None and daily_a.shop_id == 1
    finally:
        db.close()


def test_sync_never_overwrites_foreign_shop_sku(seeded, monkeypatch):
    """Als de feed (per ongeluk) een sku van winkel B bevat, mag de sync voor
    winkel A dat product niet overschrijven of claimen."""
    sid_b, _ = seeded
    feed_with_b = FEED_A + [{
        "gtin": SKU_B,
        "productTitle": "KAPING vanuit shop A",
        "priceInclVat": "1.00",
        "vendors": [{"domain": COMP, "price": "0.99"}],
    }]
    db = SessionLocal()
    try:
        monkeypatch.setattr(
            feed_ingest, "_read_feed",
            lambda *a, **k: feed_ingest._normalize(iter(feed_with_b)))
        res = feed_ingest.ingest_feed(db, source="priceshape", shop_id=1)
        assert res["products_total"] == 1  # B-sku is overgeslagen
        db.expire_all()
        prod_b = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_B).first()
        assert prod_b.shop_id == sid_b
        assert prod_b.product_name == "Shop B Product"
        assert float(prod_b.current_price) == 50.0
        # Geen concurrentrij voor B's sku in winkel 1 geschreven.
        assert db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == SKU_B,
            models.FactCompetitorPriceDaily.shop_id == 1).count() == 0
    finally:
        db.close()
