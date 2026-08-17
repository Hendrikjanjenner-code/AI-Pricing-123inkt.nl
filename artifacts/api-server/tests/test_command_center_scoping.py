"""
Two-shop isolatietests voor het Commercial Command Center (taak 16):
bewijst dat /summary en /drilldown nooit cross-shop lekken.
"""
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
PFX = f"T16S-{uuid.uuid4().hex[:6]}"


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
    """Shop 1 (default) + tweede shop, elk met eigen sales/opps/signalen/recs."""
    db = SessionLocal()
    shop_b = models.DimShop(shop_code=f"{PFX}-b", name=f"{PFX} Shop B")
    db.add(shop_b)
    db.flush()
    sid_a, sid_b = 1, shop_b.id
    today = date.today()

    revenue = {sid_a: 1000.0, sid_b: 77.0}
    for sid in (sid_a, sid_b):
        tag = "A" if sid == sid_a else "B"
        sku = f"{PFX}-{tag}1"
        db.add(models.DimProduct(sku_id=sku, product_name=sku, category=f"{PFX}-cat-{tag}",
                                 brand=f"{PFX}-brand-{tag}", current_price=20.0,
                                 cost_price=5.0, shop_id=sid))
        db.add(models.FactSalesDaily(date=today - timedelta(days=1), sku_id=sku, shop_id=sid,
                                     revenue=revenue[sid], units_sold=10,
                                     margin=revenue[sid] / 2))
        db.add(models.Opportunity(run_date=today, shop_id=sid, source_engine="basket",
                                  opportunity_type="bundle", entity_type="sku",
                                  entity_id=sku, entity_name=sku,
                                  title_nl=f"{PFX}-{tag}", explanation_nl="t",
                                  expected_value_eur=100, expected_revenue_eur=100,
                                  expected_margin_eur=50, confidence=0.5, urgency="low",
                                  effort="low", risk="low", priority_score=99,
                                  status="open"))
        db.add(models.IntelligenceSignal(shop_id=sid, engine="basket",
                                         signal_type=f"{PFX.lower()}_risk", entity_type="sku",
                                         entity_id=sku, entity_name=sku,
                                         severity="critical", confidence=0.9,
                                         explanation="testrisico", status="active"))
    db.commit()
    yield sid_a, sid_b

    for model, col in ((models.IntelligenceSignal, models.IntelligenceSignal.entity_id),
                       (models.Opportunity, models.Opportunity.entity_id),
                       (models.FactSalesDaily, models.FactSalesDaily.sku_id),
                       (models.DimProduct, models.DimProduct.sku_id)):
        db.query(model).filter(col.like(f"{PFX}%")).delete(synchronize_session=False)
    # cost-usage middleware-rijen van shop B eerst weg i.v.m. FK
    db.query(models.CostUsageRecord).filter(
        models.CostUsageRecord.shop_id == sid_b).delete(synchronize_session=False)
    db.query(models.DimShop).filter(models.DimShop.id == sid_b).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_summary_is_shop_scoped(client, admin_headers, two_shops):
    sid_a, sid_b = two_shops
    sum_a = client.get(f"/api/command-center/summary?shop_id={sid_a}", headers=admin_headers).json()
    sum_b = client.get(f"/api/command-center/summary?shop_id={sid_b}", headers=admin_headers).json()
    assert sum_a["shop_id"] == sid_a and sum_b["shop_id"] == sid_b
    # Shop B heeft precies 1 opportunity/risico uit deze fixture; shop A-data lekt niet mee.
    titels_b = [o["titel"] for o in sum_b["deze_week"]["best_opportunities"]]
    assert f"{PFX}-B" in titels_b
    assert f"{PFX}-A" not in titels_b
    assert sum_b["vandaag"]["opportunities"] == 1
    assert sum_b["vandaag"]["risks"] == 1
    assert sum_b["financieel"]["sales_7d"] == 77.0
    assert sum_a["financieel"]["sales_7d"] >= 1000.0
    # Shop A-omzet zit niet in shop B-cijfers
    assert sum_b["financieel"]["sales_7d"] < 1000.0


def test_summary_defaults_to_default_shop(client, admin_headers, two_shops):
    _, sid_b = two_shops
    default = client.get("/api/command-center/summary", headers=admin_headers).json()
    assert default["shop_id"] != sid_b  # nooit stil de andere tenant


def test_summary_unknown_shop_404(client, admin_headers):
    r = client.get("/api/command-center/summary?shop_id=999999", headers=admin_headers)
    assert r.status_code == 404


def test_drilldown_is_shop_scoped(client, admin_headers, two_shops):
    sid_a, sid_b = two_shops
    for kpi in ("sales", "margin", "opportunities", "risks", "recommendations"):
        for level in ("category", "brand", "sku"):
            r = client.get(
                f"/api/command-center/drilldown?kpi={kpi}&level={level}&shop_id={sid_b}",
                headers=admin_headers)
            assert r.status_code == 200, r.text
            keys = [row["key"] for row in r.json()["rows"]]
            assert not any("-A" in str(k) and PFX in str(k) for k in keys), \
                f"shop A-data lekt in shop B drilldown ({kpi}/{level}): {keys}"
    # Positieve check: shop B ziet zijn eigen data wél
    r = client.get(
        f"/api/command-center/drilldown?kpi=sales&level=category&shop_id={sid_b}",
        headers=admin_headers).json()
    assert any(f"{PFX}-cat-B" == row["key"] for row in r["rows"])
    assert r["rows"][0]["value"] == 77.0


def test_drilldown_requires_auth(client):
    r = client.get("/api/command-center/drilldown?kpi=sales")
    assert r.status_code in (401, 403)
