"""
Tests voor de volledige-sync-opschoning in feed-modus: concurrenten die
volledig uit de PriceShape-feed verdwenen zijn, verliezen bij een volledige
sync hun historische concurrentprijsrijen (taak: laat de wekelijkse volledige
sync ook in feed-modus verdwenen concurrenten opruimen).

Gedekt:
- Verdwenen concurrent → historische rijen (vóór vandaag) worden verwijderd,
  aanwezige concurrenten en andere winkels blijven ongemoeid.
- Uitgevinkte concurrent (importinstellingen) telt niet als verdwenen.
- Lege snapshot van vandaag → geen opschoning (last-known-good).
- De laatste volledige feed-sync is terugvindbaar via de importgeschiedenis.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import feed_ingest
import models
from database import SessionLocal


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _make_shop(db, code, name):
    shop = models.DimShop(shop_code=code, name=name)
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop


def _drop_shop(db, shop_id):
    db.rollback()
    db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.shop_id == shop_id).delete()
    # Kostenregistratie-rijen per shop eerst weg (FK, zie testconventies).
    db.query(models.CostUsageRecord).filter(
        models.CostUsageRecord.shop_id == shop_id).delete()
    db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete()
    db.commit()


@pytest.fixture()
def shop(db):
    shop = _make_shop(db, "FEEDCLEAN-TST", "Feed-cleanup-testshop")
    yield shop
    _drop_shop(db, shop.id)


def _row(day, competitor, shop_id, source="priceshape", sku="CLEANUP-SKU-1"):
    return models.FactCompetitorPriceDaily(
        date=day, sku_id=sku, shop_id=shop_id,
        competitor_name=competitor, price=10.0, source=source,
    )


def test_vanished_competitor_history_is_removed(db, shop):
    today = date.today()
    yesterday = today - timedelta(days=1)
    db.add_all([
        # Vandaag nog aanwezig:
        _row(today, "BlijvendeShop", shop.id),
        _row(yesterday, "BlijvendeShop", shop.id),
        # Volledig verdwenen (alleen historie):
        _row(yesterday, "VerdwenenShop", shop.id),
        _row(yesterday - timedelta(days=5), "VerdwenenShop", shop.id),
        # Andere bron: nooit aanraken.
        _row(yesterday, "ScraperShop", shop.id, source="scraper"),
    ])
    db.commit()

    res = feed_ingest.cleanup_vanished_competitors(db, shop_id=shop.id)

    assert res["removed_competitors"] == ["VerdwenenShop"]
    assert res["removed_rows"] == 2
    remaining = {
        (r.competitor_name, r.source)
        for r in db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.shop_id == shop.id).all()
    }
    assert ("VerdwenenShop", "priceshape") not in remaining
    assert ("BlijvendeShop", "priceshape") in remaining
    assert ("ScraperShop", "scraper") in remaining


def test_other_shop_history_is_untouched(db, shop):
    today = date.today()
    yesterday = today - timedelta(days=1)
    other = _make_shop(db, "FEEDCLEAN-TST2", "Feed-cleanup-andere-shop")
    try:
        db.add_all([
            _row(today, "BlijvendeShop", shop.id),
            _row(yesterday, "VerdwenenShop", shop.id),
            # Zelfde naam, andere winkel: moet blijven staan.
            _row(yesterday, "VerdwenenShop", other.id),
        ])
        db.commit()

        feed_ingest.cleanup_vanished_competitors(db, shop_id=shop.id)

        other_rows = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.shop_id == other.id).count()
        assert other_rows == 1
    finally:
        _drop_shop(db, other.id)


def test_disabled_competitor_is_not_treated_as_vanished(db, shop, monkeypatch):
    today = date.today()
    yesterday = today - timedelta(days=1)
    db.add_all([
        _row(today, "BlijvendeShop", shop.id),
        _row(yesterday, "UitgevinkteShop", shop.id),
    ])
    db.commit()

    from services import import_settings as imps
    real = imps.get_settings

    def fake_settings(db_, source):
        s = dict(real(db_, source))
        s["disabled_competitors"] = {"uitgevinkteshop"}
        return s

    monkeypatch.setattr(imps, "get_settings", fake_settings)

    res = feed_ingest.cleanup_vanished_competitors(db, shop_id=shop.id)
    assert res["removed_rows"] == 0
    assert res["removed_competitors"] == []


def test_empty_today_snapshot_skips_cleanup(db, shop):
    yesterday = date.today() - timedelta(days=1)
    db.add(_row(yesterday, "VerdwenenShop", shop.id))
    db.commit()

    res = feed_ingest.cleanup_vanished_competitors(db, shop_id=shop.id)
    assert res == {"removed_rows": 0, "removed_competitors": []}
    assert db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.shop_id == shop.id).count() == 1


def test_last_full_feed_sync_lookup(db):
    from routes import connectors as rc
    from engine.import_engine import new_batch_id

    assert rc._last_full_feed_sync_at(db) is None or True  # bestaat en crasht niet

    ts = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    job = models.ImportJob(
        batch_id=new_batch_id(),
        upload_type="api_sync_priceshape",
        filename=rc.FEED_SYNC_FULL_FILENAME,
        source="API-Sync",
        status="geimporteerd",
        rows_processed=0, rows_failed=0, rows_duplicates=0,
        uploaded_by="test",
        created_at=ts,
        completed_at=ts,
    )
    db.add(job)
    db.commit()
    try:
        found = rc._last_full_feed_sync_at(db)
        assert found is not None
        assert found.tzinfo is not None
    finally:
        db.delete(job)
        db.commit()
