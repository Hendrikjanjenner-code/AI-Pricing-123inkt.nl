"""
Tests voor voorraad/levertijd van concurrenten in de concurrentie-endpoints
(taak: toon voorraad en levertijd in de concurrentieschermen).

Dekking:
- /api/competition/skus/{sku_id}: in_stock/delivery_days/currency/observed_at
  per concurrent; NULL komt door als None (= onbekend), nooit als True/0.
- /api/concurrentie/sku/{sku_id}: op_voorraad/levertijd_dagen/waargenomen_op
  uit de meest recente feed-waarneming per concurrent.
- Deterministische selectie bij meerdere records op dezelfde dag:
  date desc, daarna observed_at desc (nulls last), daarna id desc.
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"AVTEST{uuid.uuid4().hex[:6]}"
SKU = f"{PFX}-sku"
COMP_STOCK = f"{PFX}-instock.nl"       # op voorraad + levertijd
COMP_OOS = f"{PFX}-oos.nl"             # niet op voorraad, wél levertijd
COMP_UNKNOWN = f"{PFX}-unknown.nl"     # alles NULL → onbekend
COMP_MULTI = f"{PFX}-multi.nl"         # meerdere records op dezelfde dag


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
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} AV Shop", active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id

        db.add(models.DimProduct(
            sku_id=SKU, product_name="AV Test Product", category=f"{PFX}-cat",
            current_price=20.0, cost_price=12.0, stock_quantity=5, shop_id=shop_id,
        ))
        db.flush()

        def fact(comp, **kw):
            row = models.FactCompetitorPriceDaily(
                date=kw.pop("date", today), sku_id=SKU, shop_id=shop_id,
                competitor_name=comp, price=kw.pop("price", 19.5), **kw,
            )
            db.add(row)
            db.flush()
            fact_ids.append(row.id)
            return row

        # 1) op voorraad + levertijd + valuta + observed_at
        fact(COMP_STOCK, in_stock=True, delivery_days=2.0, currency="EUR",
             observed_at=datetime(2026, 8, 19, 6, 0))
        # 2) niet op voorraad, wél levertijd bekend
        fact(COMP_OOS, in_stock=False, delivery_days=7.0)
        # 3) alles onbekend (NULL)
        fact(COMP_UNKNOWN)
        # 4) meerdere records op dezelfde dag: recentste observed_at moet winnen
        fact(COMP_MULTI, in_stock=False, delivery_days=9.0,
             observed_at=datetime.combine(today, datetime.min.time()).replace(hour=3),
             source="scraper", price=18.0)
        fact(COMP_MULTI, in_stock=True, delivery_days=1.0,
             observed_at=datetime.combine(today, datetime.min.time()).replace(hour=8),
             source="priceshape", price=18.5)
        # record zonder observed_at op dezelfde dag mag nooit boven records mét
        # observed_at uitkomen (nulls last)
        fact(COMP_MULTI, in_stock=None, delivery_days=None, price=17.0)
        # ouder record van gisteren mag nooit winnen
        fact(COMP_MULTI, date=today - timedelta(days=1), in_stock=False,
             delivery_days=14.0, observed_at=datetime.combine(today, datetime.min.time()))

        # CIS-scores zodat /api/concurrentie/sku/{sku} concurrenten teruggeeft
        for comp in (COMP_STOCK, COMP_OOS, COMP_UNKNOWN, COMP_MULTI):
            s = models.CompetitorInfluenceScore(
                sku_id=SKU, competitor_name=comp, run_date=today,
                cis_score=0.7, csrs_score=0.6, css_score=0.6,
                cis_class="Sterke concurrent", status="Actief",
                competitor_price=19.5,
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
                # request-middleware kan cost-usage rijen per shop schrijven; eerst opruimen (FK)
                cost_model = getattr(models, "CostUsageRecord", None)
                if cost_model is not None and hasattr(cost_model, "shop_id"):
                    db.query(cost_model).filter(cost_model.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def _detail_by_name(items, key="competitor_name"):
    return {c[key]: c for c in items}


def test_competition_detail_exposes_availability_fields(client, admin_headers, seed):
    r = client.get(f"/api/competition/skus/{SKU}", headers=admin_headers)
    assert r.status_code == 200, r.text
    detail = _detail_by_name(r.json()["competitor_detail"])

    c = detail[COMP_STOCK]
    assert c["in_stock"] is True
    assert c["delivery_days"] == 2.0
    assert c["currency"] == "EUR"
    assert c["observed_at"] is not None

    c = detail[COMP_OOS]
    assert c["in_stock"] is False
    assert c["delivery_days"] == 7.0


def test_competition_detail_null_means_unknown_not_in_stock(client, admin_headers, seed):
    r = client.get(f"/api/competition/skus/{SKU}", headers=admin_headers)
    c = _detail_by_name(r.json()["competitor_detail"])[COMP_UNKNOWN]
    assert c["in_stock"] is None          # onbekend, niet True/False
    assert c["delivery_days"] is None
    assert c["currency"] is None
    assert c["observed_at"] is None


def test_competition_detail_same_day_multi_source_is_deterministic(client, admin_headers, seed):
    """Bij meerdere records op dezelfde dag wint de recentste observed_at."""
    r = client.get(f"/api/competition/skus/{SKU}", headers=admin_headers)
    c = _detail_by_name(r.json()["competitor_detail"])[COMP_MULTI]
    assert c["in_stock"] is True
    assert c["delivery_days"] == 1.0
    assert c["price"] == 18.5


def test_concurrentie_sku_exposes_availability_per_competitor(client, admin_headers, seed):
    r = client.get(f"/api/concurrentie/sku/{SKU}", headers=admin_headers)
    assert r.status_code == 200, r.text
    conc = _detail_by_name(r.json()["concurrenten"], key="concurrent")

    assert conc[COMP_STOCK]["op_voorraad"] is True
    assert conc[COMP_STOCK]["levertijd_dagen"] == 2.0
    assert conc[COMP_STOCK]["waargenomen_op"] is not None

    # out-of-stock met bekende levertijd: beide onafhankelijk zichtbaar
    assert conc[COMP_OOS]["op_voorraad"] is False
    assert conc[COMP_OOS]["levertijd_dagen"] == 7.0

    # onbekend blijft None, wordt nooit als op voorraad gepresenteerd
    assert conc[COMP_UNKNOWN]["op_voorraad"] is None
    assert conc[COMP_UNKNOWN]["levertijd_dagen"] is None

    # deterministische keuze bij same-day multi-source
    assert conc[COMP_MULTI]["op_voorraad"] is True
    assert conc[COMP_MULTI]["levertijd_dagen"] == 1.0
