"""
Tests voor taak: sluit concurrenten zonder voorraad uit van de referentieprijs.

Dekking:
- /api/competition/skus/{sku_id}: concurrent met in_stock=False wordt
  uitgesloten met reden COMPETITOR_IGNORED_OUT_OF_STOCK; onbekende voorraad
  (None) blijft opgenomen.
- /api/concurrentie/sku/{sku_id}: gewogen referentieprijs telt concurrenten
  met op_voorraad=False niet mee; onbekende voorraad telt wél mee; per
  concurrent zijn uitgesloten_van_referentie en uitsluitingsreden zichtbaar.
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

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"OOSREF{uuid.uuid4().hex[:6]}"
SKU = f"{PFX}-sku"
COMP_STOCK = f"{PFX}-instock.nl"     # op voorraad
COMP_OOS = f"{PFX}-oos.nl"           # niet op voorraad → uitsluiten
COMP_UNKNOWN = f"{PFX}-unknown.nl"   # voorraad onbekend → meenemen


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
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} OOS Shop", active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id

        db.add(models.DimProduct(
            sku_id=SKU, product_name="OOS Ref Test Product", category=f"{PFX}-cat",
            current_price=20.0, cost_price=12.0, stock_quantity=5, shop_id=shop_id,
        ))
        db.flush()

        def fact(comp, in_stock, price):
            row = models.FactCompetitorPriceDaily(
                date=today, sku_id=SKU, shop_id=shop_id,
                competitor_name=comp, price=price, in_stock=in_stock,
            )
            db.add(row)
            db.flush()
            fact_ids.append(row.id)

        fact(COMP_STOCK, True, 20.0)
        fact(COMP_OOS, False, 10.0)      # zou de referentie flink drukken
        fact(COMP_UNKNOWN, None, 20.0)

        # CIS-scores: alle drie Actief met gelijk gewicht en verschillende prijzen
        for comp, price in ((COMP_STOCK, 20.0), (COMP_OOS, 10.0), (COMP_UNKNOWN, 20.0)):
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


def test_competition_detail_excludes_out_of_stock(client, admin_headers, seed):
    r = client.get(f"/api/competition/skus/{SKU}?shop_id={seed}", headers=admin_headers)
    assert r.status_code == 200, r.text
    detail = _by_name(r.json()["competitor_detail"], "competitor_name")

    c = detail[COMP_OOS]
    assert c["is_excluded"] is True
    assert c["exclusion_reason"] == "COMPETITOR_IGNORED_OUT_OF_STOCK"

    # op voorraad en onbekende voorraad blijven opgenomen
    assert detail[COMP_STOCK]["is_excluded"] is False
    assert detail[COMP_UNKNOWN]["is_excluded"] is False
    assert detail[COMP_UNKNOWN]["exclusion_reason"] is None


def test_weighted_reference_excludes_out_of_stock(client, admin_headers, seed):
    r = client.get(f"/api/concurrentie/sku/{SKU}", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    # Zonder uitsluiting zou de referentie (20+10+20)/3 = 16.67 zijn;
    # met uitsluiting van de OOS-concurrent: (20+20)/2 = 20.0
    assert body["gewogen_referentieprijs"] == pytest.approx(20.0)

    conc = _by_name(body["concurrenten"], "concurrent")
    assert conc[COMP_OOS]["uitgesloten_van_referentie"] is True
    assert conc[COMP_OOS]["uitsluitingsreden"] == "COMPETITOR_IGNORED_OUT_OF_STOCK"
    assert conc[COMP_STOCK]["uitgesloten_van_referentie"] is False
    assert conc[COMP_UNKNOWN]["uitgesloten_van_referentie"] is False
    assert conc[COMP_UNKNOWN]["uitsluitingsreden"] is None
