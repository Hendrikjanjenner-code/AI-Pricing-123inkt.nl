"""
Tests voor taak PriceShape API-import volledig + aan/uitvinken (#82):
- alle feedvelden komen door (extra kolommen + raw_attributes verliesvrij);
- instellingen persist (nieuwe sessie = herstart-simulatie) en zijn RBAC-beveiligd;
- uitgevinkte concurrent wordt overgeslagen zonder bestaande data te wissen;
- uitgevinkt onderdeel (concurrentprijzen) slaat handmatige upload-rijen over;
- beschikbaarheidsdata voedt fact_competitor_offer_daily.
"""
import io
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
import feed_ingest
from services import import_settings as imps

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
VIEWER_LOGIN = {"username": "dev_viewer", "password": "viewer123"}

FEED = [
    {
        "gtin": "IMPSET-SKU-1",
        "productTitle": "TestMerk Wasmiddel 2L",
        "PPC_ProductType": "Huishouden > Wasmiddel",
        "itemGroupId": "GRP-1",
        "priceInclVat": "9.99",
        "costPriceExclVat": "5.50",
        "customField": "extra-waarde",
        "vendors": [
            {
                "domain": "compa.nl", "name": "Comp A", "price": "8.99",
                "productUrl": "https://compa.nl/p/1", "inStock": "true",
                "deliveryDays": "2", "currency": "EUR",
                "scrapedAt": "2026-08-18T06:00:00", "rating": "4.5",
            },
            {
                "domain": "compb.nl", "price": "10.49",
                "productUrl": "https://compb.nl/p/1", "inStock": "false",
            },
        ],
    },
]


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass


@pytest.fixture(scope="module")
def admin_headers(client):
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def viewer_headers(client):
    resp = client.post("/api/auth/login", json=VIEWER_LOGIN)
    if resp.status_code != 200:
        pytest.skip("Geen dev_viewer account beschikbaar")
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id.like("IMPSET-%")).delete(synchronize_session=False)
        db.query(models.FactCompetitorOfferDaily).filter(
            models.FactCompetitorOfferDaily.own_sku_id.like("IMPSET-%")).delete(synchronize_session=False)
        db.query(models.FactPriceDaily).filter(
            models.FactPriceDaily.sku_id.like("IMPSET-%")).delete(synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.like("IMPSET-%")).delete(synchronize_session=False)
        db.query(models.FeedImportSetting).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _ingest(db):
    catalog, comp_rows = feed_ingest._normalize(iter(FEED))
    return catalog, comp_rows


# ── Normalisatie: alle velden komen door ────────────────────────────────────

def test_normalize_captures_all_fields():
    catalog, comp_rows = _ingest(None)
    assert len(catalog) == 1
    prod = catalog[0]
    assert prod["cost_price"] == 5.50
    assert prod["raw_attributes"] and "customField" in prod["raw_attributes"]

    assert len(comp_rows) == 2
    a = next(r for r in comp_rows if r["competitor_name"] == "compa.nl")
    assert a["in_stock"] is True
    assert a["delivery_days"] == 2.0
    assert a["currency"] == "EUR"
    assert a["vendor_name"] == "Comp A"
    assert a["observed_at"] is not None
    assert a["raw_attributes"] and "rating" in a["raw_attributes"]
    b = next(r for r in comp_rows if r["competitor_name"] == "compb.nl")
    assert b["in_stock"] is False


def test_ingest_persists_extended_fields_and_offers(monkeypatch):
    db = SessionLocal()
    try:
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(FEED)))
        res = feed_ingest.ingest_feed(db, source="priceshape")
        assert res["competitor_rows"] == 2
        assert res["skipped_by_settings"] == 0
        row = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == "IMPSET-SKU-1",
            models.FactCompetitorPriceDaily.competitor_name == "compa.nl").first()
        assert row is not None
        assert row.in_stock is True and row.delivery_days == 2.0 and row.currency == "EUR"
        assert row.raw_attributes and "rating" in row.raw_attributes
        # Beschikbaarheid gevoed in het bestaande model
        assert res["offer_rows"] == 2
        offer = db.query(models.FactCompetitorOfferDaily).filter(
            models.FactCompetitorOfferDaily.own_sku_id == "IMPSET-SKU-1").all()
        assert len(offer) == 2
    finally:
        db.close()


# ── Instellingen: persist + RBAC ────────────────────────────────────────────

def test_settings_persist_across_sessions(client, admin_headers):
    resp = client.put("/api/uploads/priceshape/import-settings", json={
        "components": {"cost_prices": False},
        "disabled_competitors": ["CompB.nl"],
    }, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["components"]["cost_prices"] is False
    assert body["components"]["competitor_prices"] is True
    assert "compb.nl" in body["disabled_competitors"]

    # Nieuwe sessie = simulatie van herstart: instellingen komen uit de DB.
    fresh = SessionLocal()
    try:
        settings = imps.get_settings(fresh)
        assert settings["components"]["cost_prices"] is False
        assert "compb.nl" in settings["disabled_competitors"]
    finally:
        fresh.close()

    get = client.get("/api/uploads/priceshape/import-settings", headers=admin_headers)
    assert get.status_code == 200
    names = [c["name"] for c in get.json()["competitors"]]
    assert "compb.nl" in names  # uitgevinkte concurrent blijft zichtbaar


def test_settings_write_requires_admin(client, viewer_headers):
    resp = client.put("/api/uploads/priceshape/import-settings", json={
        "components": {"own_prices": False}, "disabled_competitors": [],
    }, headers=viewer_headers)
    assert resp.status_code == 403
    # Lezen mag wel voor viewers
    get = client.get("/api/uploads/priceshape/import-settings", headers=viewer_headers)
    assert get.status_code == 200


def test_settings_reject_unknown_component(client, admin_headers):
    resp = client.put("/api/uploads/priceshape/import-settings", json={
        "components": {"nonsense": True}, "disabled_competitors": [],
    }, headers=admin_headers)
    assert resp.status_code == 400


# ── Toepassing in feed-ingest ───────────────────────────────────────────────

def test_disabled_competitor_skipped_without_wiping_existing(monkeypatch):
    db = SessionLocal()
    try:
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(FEED)))
        # Eerste run: alles aan → 2 rijen.
        feed_ingest.ingest_feed(db, source="priceshape")
        # compb.nl uitvinken en opnieuw draaien.
        imps.save_settings(db, {}, ["compb.nl"], "test")
        res = feed_ingest.ingest_feed(db, source="priceshape")
        assert res["skipped_by_settings"] == 1
        assert res["competitor_rows"] == 1
        # Bestaande compb.nl-rij van vandaag is niet gewist? De last-known-good
        # delete is beperkt tot vervangen rijen — compb.nl werd niet aangeleverd,
        # dus de eerdere rij blijft staan.
        remaining = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == "IMPSET-SKU-1",
            models.FactCompetitorPriceDaily.competitor_name == "compb.nl").count()
        assert remaining == 1
    finally:
        db.close()


def test_cost_component_disabled_skips_cost(monkeypatch):
    db = SessionLocal()
    try:
        imps.save_settings(db, {"cost_prices": False}, [], "test")
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(FEED)))
        feed_ingest.ingest_feed(db, source="priceshape")
        prod = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == "IMPSET-SKU-1").first()
        assert prod is not None and prod.cost_price is None
    finally:
        db.close()


def test_disabled_components_preserve_existing_values(monkeypatch):
    """Uitgevinkt onderdeel is een no-op: bestaande waarden worden niet gewist."""
    db = SessionLocal()
    try:
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(FEED)))
        # Run 1: alles aan → cost, raw attrs en availability aanwezig.
        feed_ingest.ingest_feed(db, source="priceshape")
        # Run 2: cost, extra attrs en availability uit.
        imps.save_settings(db, {"cost_prices": False, "extra_attributes": False,
                                "availability": False}, [], "test")
        feed_ingest.ingest_feed(db, source="priceshape")
        db.expire_all()
        prod = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == "IMPSET-SKU-1").first()
        assert prod.cost_price == 5.50, "cost_price mag niet gewist worden"
        assert prod.raw_attributes and "customField" in prod.raw_attributes
        row = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == "IMPSET-SKU-1",
            models.FactCompetitorPriceDaily.competitor_name == "compa.nl").first()
        assert row.in_stock is True and row.delivery_days == 2.0
        assert row.raw_attributes and "rating" in row.raw_attributes
    finally:
        db.close()


def test_disabled_cost_preserves_daily_cost_and_own_price_writes_nothing(monkeypatch):
    """cost uit → FactPriceDaily.cost_price van vandaag blijft; own uit → geen prijswrites."""
    db = SessionLocal()
    try:
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(FEED)))
        # Run 1: alles aan → dagprijs met kostprijs 5.50, productprijs 9.99.
        feed_ingest.ingest_feed(db, source="priceshape")
        # Run 2: cost uit, feed met andere kostprijs → bestaande kost blijft.
        imps.save_settings(db, {"cost_prices": False}, [], "test")
        feed2 = [dict(FEED[0], costPriceExclVat="99.99")]
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(feed2)))
        feed_ingest.ingest_feed(db, source="priceshape")
        db.expire_all()
        daily = db.query(models.FactPriceDaily).filter(
            models.FactPriceDaily.sku_id == "IMPSET-SKU-1",
            models.FactPriceDaily.date == date.today()).first()
        assert daily is not None and float(daily.cost_price) == 5.50
        # Run 3: own_prices uit, feed met andere prijs → productprijs onveranderd.
        imps.save_settings(db, {"own_prices": False, "cost_prices": True}, [], "test")
        feed3 = [dict(FEED[0], priceInclVat="1.23")]
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(feed3)))
        feed_ingest.ingest_feed(db, source="priceshape")
        db.expire_all()
        prod = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == "IMPSET-SKU-1").first()
        assert float(prod.current_price) == 9.99, "own_prices uit mag productprijs niet wijzigen"
    finally:
        db.close()


def test_raw_attributes_lossless_nested_and_long():
    """Geneste structuren en lange waarden blijven verliesvrij in raw_attributes."""
    nested = {"specs": {"kleur": "blauw", "maten": [1, 2, 3]}, "tags": ["a", "b"]}
    long_val = "x" * 5000
    feed = [dict(FEED[0], nestedInfo=nested, longField=long_val)]
    catalog, _ = feed_ingest._normalize(iter(feed))
    raw = catalog[0]["raw_attributes"]
    assert raw["nestedInfo"] == nested
    assert raw["longField"] == long_val
    assert "vendors" not in raw  # apart genormaliseerd, niet dubbel opgeslagen


def test_disabled_competitor_keeps_offer_rows(monkeypatch):
    """Uitgevinkte concurrent behoudt óók zijn beschikbaarheidsrijen (offers)."""
    feed_both = [dict(FEED[0], vendors=[
        dict(FEED[0]["vendors"][0]),                     # compa.nl met voorraad
        dict(FEED[0]["vendors"][1], deliveryDays="5"),   # compb.nl met voorraaddata
    ])]
    db = SessionLocal()
    try:
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(feed_both)))
        feed_ingest.ingest_feed(db, source="priceshape")
        ids = {c.competitor_name: c.competitor_id for c in db.query(models.DimCompetitor)
               .filter(models.DimCompetitor.competitor_name.in_(["compa.nl", "compb.nl"])).all()}
        assert db.query(models.FactCompetitorOfferDaily).filter(
            models.FactCompetitorOfferDaily.own_sku_id == "IMPSET-SKU-1").count() == 2
        # compb.nl uitvinken en opnieuw syncen: zijn offer-rij mag niet verdwijnen.
        imps.save_settings(db, {}, ["compb.nl"], "test")
        feed_ingest.ingest_feed(db, source="priceshape")
        remaining_b = db.query(models.FactCompetitorOfferDaily).filter(
            models.FactCompetitorOfferDaily.own_sku_id == "IMPSET-SKU-1",
            models.FactCompetitorOfferDaily.competitor_id == ids["compb.nl"]).count()
        assert remaining_b == 1, "offer van uitgevinkte concurrent mag niet gewist worden"
        # compa.nl is wél gewoon ververst (1 rij, geen duplicaten).
        assert db.query(models.FactCompetitorOfferDaily).filter(
            models.FactCompetitorOfferDaily.own_sku_id == "IMPSET-SKU-1",
            models.FactCompetitorOfferDaily.competitor_id == ids["compa.nl"]).count() == 1
    finally:
        db.close()


def test_oversized_mapped_fields_recoverable_after_ingest(monkeypatch):
    """Afgekapte gemapte velden (titel, domein) blijven origineel opvraagbaar."""
    long_title = "T" * 600
    long_domain = "d" * 300 + ".nl"
    feed = [dict(FEED[0],
                 productTitle=long_title,
                 vendors=[dict(FEED[0]["vendors"][0], domain=long_domain)])]
    catalog, comp_rows = feed_ingest._normalize(iter(feed))
    assert catalog[0]["product_name"] == long_title[:500]
    assert catalog[0]["raw_attributes"]["_productTitle_full"] == long_title
    assert comp_rows[0]["competitor_name"] == long_domain[:255]
    assert comp_rows[0]["raw_attributes"]["_domain_full"] == long_domain

    db = SessionLocal()
    try:
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: (catalog, comp_rows))
        feed_ingest.ingest_feed(db, source="priceshape")
        prod = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == "IMPSET-SKU-1").first()
        assert prod.raw_attributes["_productTitle_full"] == long_title
        row = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == "IMPSET-SKU-1",
            models.FactCompetitorPriceDaily.competitor_name == long_domain[:255]).first()
        assert row is not None and row.raw_attributes["_domain_full"] == long_domain
    finally:
        db.close()


def test_full_replace_still_removes_absent_enabled_competitors(monkeypatch):
    """Normale pad: concurrent die uit de feed verdwijnt wordt wél vervangen."""
    db = SessionLocal()
    try:
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(FEED)))
        feed_ingest.ingest_feed(db, source="priceshape")
        # Volgende run zonder compb.nl in de feed (wel enabled) → rij verdwijnt.
        feed2 = [dict(FEED[0], vendors=[FEED[0]["vendors"][0]])]
        monkeypatch.setattr(feed_ingest, "_read_feed", lambda *a, **k: feed_ingest._normalize(iter(feed2)))
        feed_ingest.ingest_feed(db, source="priceshape")
        remaining = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == "IMPSET-SKU-1",
            models.FactCompetitorPriceDaily.competitor_name == "compb.nl").count()
        assert remaining == 0
    finally:
        db.close()


# ── Toepassing in handmatige upload ─────────────────────────────────────────

def test_manual_upload_respects_disabled_competitor(client, admin_headers):
    # Zorg dat het product bestaat.
    db = SessionLocal()
    try:
        if not db.query(models.DimProduct).filter(models.DimProduct.sku_id == "IMPSET-SKU-1").first():
            db.add(models.DimProduct(sku_id="IMPSET-SKU-1", product_name="Test", is_active=True))
            db.commit()
        imps.save_settings(db, {}, ["compb.nl"], "test")
    finally:
        db.close()

    csv = (
        "sku,concurrent,prijs\n"
        "IMPSET-SKU-1,compa.nl,8.99\n"
        "IMPSET-SKU-1,compb.nl,10.49\n"
    ).encode()
    resp = client.post(
        "/api/uploads/priceshape/import?mode=aanvullen",
        files={"file": ("test.csv", io.BytesIO(csv), "text/csv")},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped_by_settings"] == 1
    assert body["created"] == 1
    assert "importinstellingen" in body["message"]


def test_vervangen_mode_never_deletes_disabled_competitor_rows(client, admin_headers):
    """'Vervangen' mag rijen van uitgevinkte concurrenten niet opruimen."""
    db = SessionLocal()
    try:
        if not db.query(models.DimProduct).filter(models.DimProduct.sku_id == "IMPSET-SKU-1").first():
            db.add(models.DimProduct(sku_id="IMPSET-SKU-1", product_name="Test", is_active=True))
        db.add(models.FactCompetitorPriceDaily(
            date=date.today(), sku_id="IMPSET-SKU-1", competitor_name="compb.nl",
            price=10.49, source="PriceShape"))
        db.commit()
        imps.save_settings(db, {}, ["compb.nl"], "test")
    finally:
        db.close()

    csv = "sku,concurrent,prijs\nIMPSET-SKU-1,compa.nl,8.99\n".encode()
    resp = client.post(
        "/api/uploads/priceshape/import?mode=vervangen&confirm_phrase=VERVANG ALLE PRICESHAPE DATA",
        files={"file": ("test.csv", io.BytesIO(csv), "text/csv")},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    db = SessionLocal()
    try:
        remaining = db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == "IMPSET-SKU-1",
            models.FactCompetitorPriceDaily.competitor_name == "compb.nl").count()
        assert remaining == 1, "vervangen-modus mag uitgevinkte concurrent niet wissen"
    finally:
        db.close()


def test_rest_sync_respects_import_settings(monkeypatch):
    """REST-modus van de connector past dezelfde importinstellingen toe."""
    from routes import connectors as conn_routes
    from connectors import priceshape_connector

    monkeypatch.setattr(priceshape_connector, "_get_raw_config", lambda db=None: {"mode": "rest"})
    monkeypatch.setattr(priceshape_connector, "_get_mode", lambda raw: "rest")
    monkeypatch.setattr(priceshape_connector, "_get_credentials", lambda db=None: {})
    monkeypatch.setattr(priceshape_connector, "fetch_competitor_prices", lambda db=None: [
        {"sku_id": "IMPSET-SKU-1", "competitor_name": "compa.nl", "competitor_price": 8.99},
        {"sku_id": "IMPSET-SKU-1", "competitor_name": "compb.nl", "competitor_price": 10.49},
    ])

    class FakeUser:
        username = "test"

    db = SessionLocal()
    try:
        imps.save_settings(db, {}, ["compb.nl"], "test")
        res = conn_routes._run_sync("priceshape", db, FakeUser())
        assert res["status"] == "ok", res
        assert res["counts"]["price_records"] == 1
        assert res["counts"]["overgeslagen_door_instellingen"] == 1
        assert "importinstellingen" in res["message"]

        # Onderdeel volledig uit: alles overgeslagen.
        imps.save_settings(db, {"competitor_prices": False}, [], "test")
        res = conn_routes._run_sync("priceshape", db, FakeUser())
        assert res["counts"]["price_records"] == 0
        assert res["counts"]["overgeslagen_door_instellingen"] == 2

        # Herstel standaardinstellingen voor andere tests.
        imps.save_settings(db, {"competitor_prices": True}, [], "test")
    finally:
        db.close()
