"""
Two-shop isolatietests voor de engine-routes (taak 9): bewijst dat lijsten,
reads en mutaties nooit cross-shop lekken. Draait tegen de dev-database via
de FastAPI TestClient; alle testdata wordt na afloop opgeruimd.
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
PFX = f"T9S-{uuid.uuid4().hex[:6]}"


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
def two_shops(client, admin_headers):
    """Shop 1 (default) + een tweede shop met eigen data in elke engine-tabel."""
    db = SessionLocal()
    shop_b = models.DimShop(shop_code=f"{PFX}-b", name=f"{PFX} Shop B")
    db.add(shop_b)
    db.flush()
    sid_a, sid_b = 1, shop_b.id

    for sid in (sid_a, sid_b):
        tag = "A" if sid == sid_a else "B"
        for suffix, price in ((f"{PFX}-{tag}1", 20.0), (f"{PFX}-{tag}2", 10.0)):
            db.add(models.DimProduct(sku_id=suffix, product_name=suffix, category=PFX,
                                     current_price=price, cost_price=5.0, shop_id=sid))
        db.add(models.FactBasketAffinity(shop_id=sid, sku_id_a=f"{PFX}-{tag}1",
                                         sku_id_b=f"{PFX}-{tag}2",
                                         affinity_score=0.9, co_purchase_count=25))
        db.add(models.Promotion(sku_id=f"{PFX}-{tag}1", promotion_type="percentage_off",
                                discount_value=10, start_date=date(2026, 8, 1),
                                end_date=date(2026, 8, 7)))
        db.add(models.Opportunity(run_date=date.today(), shop_id=sid, source_engine="basket",
                                  opportunity_type="bundle", entity_type="sku",
                                  entity_id=f"{PFX}-{tag}1", entity_name=f"{PFX}-{tag}1",
                                  title_nl="t", explanation_nl="t", expected_value_eur=1,
                                  expected_revenue_eur=1, expected_margin_eur=1,
                                  confidence=0.5, urgency="low", effort="low", risk="low",
                                  priority_score=1, status="open"))
        db.add(models.IntelligenceSignal(shop_id=sid, engine="basket",
                                         signal_type=f"{PFX.lower()}_test", entity_type="sku",
                                         entity_id=f"{PFX}-{tag}1", entity_name=f"{PFX}-{tag}1",
                                         severity="info", confidence=0.5,
                                         explanation="testsignaal", status="active"))
    db.commit()
    yield sid_a, sid_b

    for model, col in ((models.FactPromotionEffect, models.FactPromotionEffect.sku_id),
                       (models.Promotion, models.Promotion.sku_id),
                       (models.BasketAssociation, models.BasketAssociation.antecedent_sku),
                       (models.Opportunity, models.Opportunity.entity_id),
                       (models.IntelligenceSignal, models.IntelligenceSignal.entity_id),
                       (models.FactBasketAffinity, models.FactBasketAffinity.sku_id_a),
                       (models.DimProduct, models.DimProduct.sku_id)):
        db.query(model).filter(col.like(f"{PFX}%")).delete(synchronize_session=False)
    shop_b = db.query(models.DimShop).filter(
        models.DimShop.shop_code == f"{PFX}-b").first()
    if shop_b:
        db.query(models.CostUsageRecord).filter(
            models.CostUsageRecord.shop_id == shop_b.id).delete(synchronize_session=False)
        db.query(models.DimShop).filter(models.DimShop.id == shop_b.id).delete(
            synchronize_session=False)
    db.commit()
    db.close()


def _own(rows, key, tag):
    return [r for r in rows if str(r.get(key, "")).startswith(f"{PFX}-{tag}")]


def test_basket_run_and_dashboard_isolated(client, admin_headers, two_shops):
    sid_a, sid_b = two_shops
    import time
    for sid in (sid_a, sid_b):
        r = client.post(f"/api/basket/run?shop_id={sid}", headers=admin_headers)
        assert r.status_code == 200, r.text
        job = r.json()
        assert job["status"] == "running" and job["job_id"]
        # Run draait nu async; poll de jobstatus tot afronding
        for _ in range(120):
            s = client.get(f"/api/engine-jobs/{job['job_id']}", headers=admin_headers)
            assert s.status_code == 200, s.text
            job = s.json()
            if job["status"] != "running":
                break
            time.sleep(0.25)
        assert job["status"] == "completed", job.get("error")
        assert job["result"]["shop_id"] == sid
    d = client.get(f"/api/basket/associations?shop_id={sid_b}", headers=admin_headers).json()
    assert d["shop_id"] == sid_b
    skus = [a["antecedent_sku"] for a in d["associaties"] if a["antecedent_sku"].startswith(PFX)]
    assert skus and all(s.startswith(f"{PFX}-B") for s in skus)


def test_promotions_list_isolated(client, admin_headers, two_shops):
    sid_a, sid_b = two_shops
    d = client.get(f"/api/promotion-intelligence/promotions?shop_id={sid_b}",
                   headers=admin_headers).json()
    assert d["shop_id"] == sid_b
    own = [p for p in d["promoties"] if str(p["sku_id"]).startswith(PFX)]
    assert own and all(p["sku_id"].startswith(f"{PFX}-B") for p in own)


def test_opportunity_status_cross_shop_404(client, admin_headers, two_shops):
    sid_a, sid_b = two_shops
    db = SessionLocal()
    opp_b = db.query(models.Opportunity).filter(
        models.Opportunity.shop_id == sid_b,
        models.Opportunity.entity_id.like(f"{PFX}%")).first()
    db.close()
    assert opp_b is not None
    # Mutatie via shop A-scope moet 404 geven
    r = client.post(f"/api/opportunities/{opp_b.id}/status?status=done&shop_id={sid_a}",
                    headers=admin_headers)
    assert r.status_code == 404
    # Binnen eigen scope wél toegestaan
    r = client.post(f"/api/opportunities/{opp_b.id}/status?status=in_progress&shop_id={sid_b}",
                    headers=admin_headers)
    assert r.status_code == 200, r.text


def test_signal_read_and_dismiss_cross_shop_404(client, admin_headers, two_shops):
    sid_a, sid_b = two_shops
    db = SessionLocal()
    sig_b = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == sid_b,
        models.IntelligenceSignal.entity_id.like(f"{PFX}%"),
        models.IntelligenceSignal.signal_type == f"{PFX.lower()}_test").first()
    db.close()
    assert sig_b is not None
    assert client.get(f"/api/signals/{sig_b.id}?shop_id={sid_a}",
                      headers=admin_headers).status_code == 404
    assert client.get(f"/api/signals/{sig_b.id}?shop_id={sid_b}",
                      headers=admin_headers).status_code == 200
    assert client.post(f"/api/signals/{sig_b.id}/dismiss?shop_id={sid_a}",
                       headers=admin_headers).status_code == 404
    assert client.post(f"/api/signals/{sig_b.id}/dismiss?shop_id={sid_b}",
                       headers=admin_headers).status_code == 200


def test_opportunity_dashboard_isolated(client, admin_headers, two_shops):
    sid_a, sid_b = two_shops
    d = client.get(f"/api/opportunities?status=all&shop_id={sid_b}", headers=admin_headers).json()
    assert d["shop_id"] == sid_b
    own = [o for o in d["opportunities"] if str(o["sku_id"]).startswith(PFX)]
    assert own and all(o["sku_id"].startswith(f"{PFX}-B") for o in own)
