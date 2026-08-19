"""
Tests voor taak: sluit concurrenten met onwerkbaar lange levertijd uit van de
referentieprijs (COMPETITOR_IGNORED_BAD_DELIVERY).

Dekking:
- services.import_settings: max_delivery_days configureerbaar (persistente
  opslag, validatie, None = geen limiet) + delivery_excluded-helper.
- /api/competition/skus/{sku_id}: concurrent met delivery_days > drempel wordt
  uitgesloten met reden COMPETITOR_IGNORED_BAD_DELIVERY; onbekende levertijd
  (None) blijft opgenomen.
- /api/concurrentie/sku/{sku_id}: gewogen referentieprijs telt concurrenten
  met te lange levertijd niet mee; uitsluitingsreden zichtbaar per concurrent.
"""
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from services import import_settings as imps

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"BADDEL{uuid.uuid4().hex[:6]}"
SKU = f"{PFX}-sku"
COMP_FAST = f"{PFX}-fast.nl"        # levertijd 2 dagen → meenemen
COMP_SLOW = f"{PFX}-slow.nl"        # levertijd 45 dagen → uitsluiten
COMP_UNKNOWN = f"{PFX}-unknown.nl"  # levertijd onbekend → meenemen


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
def seed(client):
    db = SessionLocal()
    today = date.today()
    shop_id = None
    fact_ids = []
    cis_ids = []
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} BadDel Shop", active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id

        db.add(models.DimProduct(
            sku_id=SKU, product_name="BadDelivery Ref Test Product", category=f"{PFX}-cat",
            current_price=20.0, cost_price=12.0, stock_quantity=5, shop_id=shop_id,
        ))
        db.flush()

        def fact(comp, delivery_days, price):
            row = models.FactCompetitorPriceDaily(
                date=today, sku_id=SKU, shop_id=shop_id,
                competitor_name=comp, price=price, in_stock=True,
                delivery_days=delivery_days,
            )
            db.add(row)
            db.flush()
            fact_ids.append(row.id)

        fact(COMP_FAST, 2, 20.0)
        fact(COMP_SLOW, 45, 10.0)      # zou de referentie flink drukken
        fact(COMP_UNKNOWN, None, 20.0)

        for comp, price in ((COMP_FAST, 20.0), (COMP_SLOW, 10.0), (COMP_UNKNOWN, 20.0)):
            s = models.CompetitorInfluenceScore(
                sku_id=SKU, competitor_name=comp, run_date=today,
                cis_score=0.7, csrs_score=0.6, css_score=0.6,
                cis_class="Sterke concurrent", status="Actief",
                competitor_price=price, competitor_weight=1.0,
            )
            db.add(s)
            db.flush()
            cis_ids.append(s.id)

        db.commit()
        yield shop_id
    finally:
        db.rollback()
        try:
            if cis_ids:
                db.query(models.CompetitorInfluenceScore).filter(
                    models.CompetitorInfluenceScore.id.in_(cis_ids)).delete(synchronize_session=False)
            if fact_ids:
                db.query(models.FactCompetitorPriceDaily).filter(
                    models.FactCompetitorPriceDaily.id.in_(fact_ids)).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(models.DimProduct.sku_id == SKU).delete(synchronize_session=False)
            if shop_id:
                cost_model = getattr(models, "CostUsageRecord", None)
                if cost_model is not None and hasattr(cost_model, "shop_id"):
                    db.query(cost_model).filter(cost_model.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def _by_name(items, key):
    return {c[key]: c for c in items}


# ── Unit: helper & instellingen ─────────────────────────────────────────────

def test_delivery_excluded_helper():
    s = {"max_delivery_days": 30}
    assert imps.delivery_excluded(s, 31) is True
    assert imps.delivery_excluded(s, 30) is False       # drempel zelf telt mee
    assert imps.delivery_excluded(s, None) is False     # onbekend telt mee
    assert imps.delivery_excluded({"max_delivery_days": None}, 999) is False  # geen limiet
    # Zonder key: standaarddrempel
    assert imps.delivery_excluded({}, imps.DEFAULT_MAX_DELIVERY_DAYS + 1) is True


def test_max_delivery_days_persistent_and_validated():
    db = SessionLocal()
    conn = f"{PFX}-conn"
    try:
        # Standaardwaarde zonder opgeslagen rij
        assert imps.get_settings(db, conn)["max_delivery_days"] == imps.DEFAULT_MAX_DELIVERY_DAYS

        out = imps.save_settings(db, {}, [], "tester", conn, max_delivery_days=14)
        assert out["max_delivery_days"] == 14
        # Niet meegeven = bestaande waarde behouden
        out = imps.save_settings(db, {"own_prices": False}, [], "tester", conn)
        assert out["max_delivery_days"] == 14
        # None = geen limiet
        out = imps.save_settings(db, {}, [], "tester", conn, max_delivery_days=None)
        assert out["max_delivery_days"] is None

        with pytest.raises(ValueError):
            imps.save_settings(db, {}, [], "tester", conn, max_delivery_days=0)
        with pytest.raises(ValueError):
            imps.save_settings(db, {}, [], "tester", conn, max_delivery_days="veel")
    finally:
        db.query(models.FeedImportSetting).filter(
            models.FeedImportSetting.connector_name == conn).delete(synchronize_session=False)
        db.commit()
        db.close()


# ── API: competition-detail ─────────────────────────────────────────────────

def test_competition_detail_excludes_bad_delivery(client, admin_headers, seed):
    r = client.get(f"/api/competition/skus/{SKU}", headers=admin_headers)
    assert r.status_code == 200, r.text
    detail = _by_name(r.json()["competitor_detail"], "competitor_name")

    c = detail[COMP_SLOW]
    assert c["is_excluded"] is True
    assert c["exclusion_reason"] == "COMPETITOR_IGNORED_BAD_DELIVERY"

    # snelle levertijd en onbekende levertijd blijven opgenomen
    assert detail[COMP_FAST]["is_excluded"] is False
    assert detail[COMP_UNKNOWN]["is_excluded"] is False
    assert detail[COMP_UNKNOWN]["exclusion_reason"] is None


def test_weighted_reference_excludes_bad_delivery(client, admin_headers, seed):
    r = client.get(f"/api/concurrentie/sku/{SKU}", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    # Zonder uitsluiting zou de referentie (20+10+20)/3 = 16.67 zijn;
    # met uitsluiting van de trage concurrent: (20+20)/2 = 20.0
    assert body["gewogen_referentieprijs"] == pytest.approx(20.0)

    conc = _by_name(body["concurrenten"], "concurrent")
    assert conc[COMP_SLOW]["uitgesloten_van_referentie"] is True
    assert conc[COMP_SLOW]["uitsluitingsreden"] == "COMPETITOR_IGNORED_BAD_DELIVERY"
    assert conc[COMP_FAST]["uitgesloten_van_referentie"] is False
    assert conc[COMP_UNKNOWN]["uitgesloten_van_referentie"] is False
    assert conc[COMP_UNKNOWN]["uitsluitingsreden"] is None


def test_import_settings_api_roundtrip(client, admin_headers):
    r = client.get("/api/uploads/priceshape/import-settings", headers=admin_headers)
    assert r.status_code == 200, r.text
    original = r.json().get("max_delivery_days", imps.DEFAULT_MAX_DELIVERY_DAYS)
    try:
        r = client.put("/api/uploads/priceshape/import-settings", headers=admin_headers,
                       json={"components": {}, "disabled_competitors": [],
                             "max_delivery_days": 21})
        assert r.status_code == 200, r.text
        assert r.json()["max_delivery_days"] == 21

        # Ongeldige waarde → 400
        r = client.put("/api/uploads/priceshape/import-settings", headers=admin_headers,
                       json={"components": {}, "disabled_competitors": [],
                             "max_delivery_days": -3})
        assert r.status_code == 400
    finally:
        client.put("/api/uploads/priceshape/import-settings", headers=admin_headers,
                   json={"components": {}, "disabled_competitors": [],
                         "max_delivery_days": original})
