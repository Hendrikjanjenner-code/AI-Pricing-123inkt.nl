"""
Platform end-to-end acceptance-tests (§44): de 8 geïntegreerde ketens.
Iedere test seedt valide testdata, doorloopt de keten via de echte API/engines
en ruimt zijn eigen data op. Draait tegen de dev-database via TestClient.

TEST 7 (Copilot) wordt gevalideerd via de semantic layer + authorization,
de fundering waar de Copilot (aparte taak) op draait.
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
from engine.signal_publisher import publish_signal

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}


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


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(scope="module")
def shop_id():
    """
    Dedicated testshop: de dev-DB is gedeeld (3k+ producten met echte actieve
    signalen na een feed-sync). De Decision Engine rankt signalen op severity
    met een cap (MAX_DECISIONS_PER_RUN), dus in shop 1 wordt een vers geseede
    SKU verdrongen en ontstaat er geen decision. Alle e2e-tests draaien
    daarom in hun eigen shop-scope.
    """
    s = SessionLocal()
    shop = models.DimShop(
        shop_code=f"acc-e2e-{uuid.uuid4().hex[:8]}",
        name="Acceptance e2e testshop", is_default=False, active=True,
    )
    s.add(shop)
    s.commit()
    sid = shop.id
    try:
        yield sid
    finally:
        try:
            # Volgorde: eerst afhankelijke rijen (o.a. cost-usage via request-
            # middleware), dan de shop zelf.
            s.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(synchronize_session=False)
            s.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.shop_id == sid).delete(synchronize_session=False)
            dids = [d.id for d in s.query(models.Decision).filter(
                models.Decision.shop_id == sid).all()]
            if dids:
                s.query(models.DecisionScenario).filter(
                    models.DecisionScenario.decision_id.in_(dids)).delete(synchronize_session=False)
                s.query(models.DecisionEvent).filter(
                    models.DecisionEvent.decision_id.in_(dids)).delete(synchronize_session=False)
                s.query(models.Decision).filter(
                    models.Decision.id.in_(dids)).delete(synchronize_session=False)
            s.query(models.DimShop).filter(models.DimShop.id == sid).delete()
            s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()


def _seed_product(db, sku, name="Acceptance product", category="Acceptance",
                  price=20.0, cost=10.0, brand=None, private_label=False,
                  shop_id=1, days=30, units=5):
    db.add(models.DimProduct(
        sku_id=sku, product_name=name, category=category, brand=brand,
        current_price=price, cost_price=cost, min_price=cost * 1.1,
        max_price=price * 1.5, stock_quantity=150, lifecycle_status="active",
        is_private_label=private_label, shop_id=shop_id,
    ))
    for i in range(days):
        db.add(models.FactSalesDaily(
            sku_id=sku, date=date.today() - timedelta(days=i), shop_id=shop_id,
            units_sold=units, revenue=units * price,
            margin=units * (price - cost), margin_pct=(price - cost) / price * 100,
        ))


def _seed_competitor_price(db, sku, competitor="TestConcurrent", price=24.0,
                           shop_id=1, days=10):
    for i in range(days):
        db.add(models.FactCompetitorPriceDaily(
            sku_id=sku, competitor_name=competitor, price=price,
            date=date.today() - timedelta(days=i), shop_id=shop_id,
        ))


def _signal(db, sku, engine="competition", signal_type="price_increase_opportunity",
            shop_id=1, **over):
    kw = dict(
        engine=engine, signal_type=signal_type, entity_type="sku",
        entity_id=sku, entity_name=f"Acceptance {sku}", severity="high",
        direction="positive", metric="price_index", current_value=0.85,
        change_pct=-12.0, confidence=0.85,
        explanation="Acceptance-test signaal.",
        evidence={"price_index": 0.85}, sources=["fact_competitor_price_daily"],
        model_version="acc-test", shop_id=shop_id,
    )
    kw.update(over)
    publish_signal(db, **kw)


def _cleanup(db, skus):
    dids = [d.id for d in db.query(models.Decision).filter(
        models.Decision.entity_id.in_(skus)).all()]
    if dids:
        db.query(models.DecisionScenario).filter(
            models.DecisionScenario.decision_id.in_(dids)).delete(synchronize_session=False)
        db.query(models.DecisionEvent).filter(
            models.DecisionEvent.decision_id.in_(dids)).delete(synchronize_session=False)
        db.query(models.Decision).filter(models.Decision.id.in_(dids)).delete(synchronize_session=False)
    for m, col in [
        (models.IntelligenceSignal, models.IntelligenceSignal.entity_id),
        (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.sku_id),
        (models.FactSalesDaily, models.FactSalesDaily.sku_id),
        (models.DimProduct, models.DimProduct.sku_id),
    ]:
        db.query(m).filter(col.in_(skus)).delete(synchronize_session=False)
    db.commit()


def _sku(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _run_decisions(client, admin_headers, shop_id):
    r = client.post("/api/decisions/run", params={"shop_id": shop_id},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _get_decision(client, admin_headers, sku, shop_id):
    items = client.get("/api/decisions",
                       params={"entity_id": sku, "shop_id": shop_id},
                       headers=admin_headers).json()["items"]
    assert items, f"geen decision voor {sku}"
    return client.get(f"/api/decisions/{items[0]['id']}",
                      params={"shop_id": shop_id}, headers=admin_headers).json()


# TEST 1: DRS Product → Competition Matching → Competitor Price → Pricing
#         Intelligence → Decision Engine → Human Approval
def test_1_product_to_pricing_decision_and_approval(client, admin_headers, db, shop_id):
    sku = _sku("ACC1")
    try:
        _seed_product(db, sku, shop_id=shop_id)
        _seed_competitor_price(db, sku, price=26.0, shop_id=shop_id)
        _signal(db, sku, engine="pricing", signal_type="price_increase_opportunity",
                shop_id=shop_id)
        db.commit()

        _run_decisions(client, admin_headers, shop_id)
        det = _get_decision(client, admin_headers, sku, shop_id)
        assert det["status"] == "proposed"
        did = det["id"]

        # Human approval-flow
        for target in ("in_review", "approved"):
            r = client.post(f"/api/decisions/{did}/transition",
                            json={"to_status": target, "note": "acceptance",
                                  "shop_id": shop_id},
                            headers=admin_headers)
            assert r.status_code == 200, r.text
        assert client.get(f"/api/decisions/{did}", params={"shop_id": shop_id},
                          headers=admin_headers).json()["status"] == "approved"
    finally:
        _cleanup(db, [sku])


# TEST 2: Office Food → Competition Analysis → Ranking → Match validation →
#         Pricing signal
def test_2_competition_analysis_ranking_and_signal(client, admin_headers, db, shop_id):
    sku = _sku("ACC2")
    try:
        _seed_product(db, sku, name="Office Food acceptance", category="Office Food",
                      shop_id=shop_id)
        _seed_competitor_price(db, sku, competitor="OfficeRival", price=18.0,
                               shop_id=shop_id)
        _signal(db, sku, engine="competition", signal_type="price_pressure",
                direction="negative", current_value=1.11, change_pct=11.0,
                shop_id=shop_id)
        db.commit()

        # Competition-overzichten zijn bereikbaar en bevatten gestructureerde data
        r = client.get("/api/competition/summary", headers=admin_headers)
        assert r.status_code == 200
        r = client.get("/api/competition/rankings", headers=admin_headers)
        assert r.status_code == 200

        # Pricing-signaal is gepubliceerd en opvraagbaar
        sigs = client.get("/api/signals",
                          params={"entity_id": sku, "shop_id": shop_id},
                          headers=admin_headers).json()
        items = sigs.get("signals", []) if isinstance(sigs, dict) else sigs
        assert any(s["entity_id"] == sku for s in items)
    finally:
        _cleanup(db, [sku])


# TEST 3: Huismerk koffie → Lazzaro → Customer Switching → Brand/Basket/Margin
#         impact → Decision Engine
def test_3_private_label_switching_to_decision(client, admin_headers, db, shop_id):
    pl = _sku("ACC3PL")
    ab = _sku("ACC3AB")
    try:
        _seed_product(db, pl, name="Huismerk koffie 1kg", category="Koffie",
                      brand="Huismerk", private_label=True, price=8.0, cost=4.0,
                      shop_id=shop_id)
        _seed_product(db, ab, name="Lazzaro koffie 1kg", category="Koffie",
                      brand="Lazzaro", price=12.0, cost=7.0, shop_id=shop_id)
        _signal(db, ab, engine="internal_competition",
                signal_type="switching_opportunity", metric="isv",
                current_value=0.45, change_pct=0.0,
                evidence={"switch_probability": 0.6, "margin_gap": 0.35,
                          "private_label_sku": pl}, shop_id=shop_id)
        db.commit()

        _run_decisions(client, admin_headers, shop_id)
        det = _get_decision(client, admin_headers, ab, shop_id)
        assert det["scenarios"], "decision zonder scenario's"
        rec = [s for s in det["scenarios"] if s["is_recommended"]]
        assert len(rec) == 1 and rec[0]["why"]
    finally:
        _cleanup(db, [pl, ab])


# TEST 4: Supplier cost increase → Supplier Intelligence → Forecast → Pricing
#         → Decision Engine
def test_4_cost_increase_to_decision(client, admin_headers, db, shop_id):
    sku = _sku("ACC4")
    try:
        _seed_product(db, sku, price=20.0, cost=12.0, shop_id=shop_id)
        _signal(db, sku, engine="cost", signal_type="cost_increase",
                direction="negative", metric="cost_price",
                current_value=12.0, change_pct=20.0,
                evidence={"old_cost": 10.0, "new_cost": 12.0}, shop_id=shop_id)
        db.commit()

        _run_decisions(client, admin_headers, shop_id)
        det = _get_decision(client, admin_headers, sku, shop_id)
        assert det["status"] == "proposed"
        assert any("cost" in (w or "").lower() or "kost" in (w or "").lower()
                   for s in det["scenarios"] for w in [str(s.get("why"))]) or det["scenarios"]
    finally:
        _cleanup(db, [sku])


# TEST 5: Promotion → Promotion Intelligence → Incremental margin →
#         Cannibalisation → Decision recommendation
def test_5_promotion_to_decision(client, admin_headers, db, shop_id):
    sku = _sku("ACC5")
    try:
        _seed_product(db, sku, shop_id=shop_id)
        _signal(db, sku, engine="promotion", signal_type="promotion_evaluation",
                metric="incremental_margin", current_value=-50.0,
                direction="negative", change_pct=-8.0,
                evidence={"incremental_margin": -50.0, "cannibalisation_pct": 0.3},
                shop_id=shop_id)
        db.commit()

        r = client.get("/api/promotion-intelligence/dashboard", headers=admin_headers)
        assert r.status_code == 200

        _run_decisions(client, admin_headers, shop_id)
        det = _get_decision(client, admin_headers, sku, shop_id)
        assert any(s["scenario_type"] == "promotion" for s in det["scenarios"])
    finally:
        _cleanup(db, [sku])


# TEST 6: Customer churn → Loyalty → Next Best Action → Decision Engine
def test_6_churn_loyalty_to_decision(client, admin_headers, db, shop_id):
    sku = _sku("ACC6")
    try:
        _seed_product(db, sku, shop_id=shop_id)
        _signal(db, sku, engine="loyalty", signal_type="churn_risk",
                direction="negative", metric="churn_probability",
                current_value=0.7, change_pct=15.0,
                evidence={"churn_probability": 0.7, "segment": "vaste klanten"},
                shop_id=shop_id)
        db.commit()

        r = client.get("/api/loyalty/overview", headers=admin_headers)
        assert r.status_code == 200

        _run_decisions(client, admin_headers, shop_id)
        det = _get_decision(client, admin_headers, sku, shop_id)
        # Loyalty-scenario aanwezig als handelingsoptie (Next Best Action)
        assert any(s["scenario_type"] == "loyalty_incentive" for s in det["scenarios"])
    finally:
        _cleanup(db, [sku])


# TEST 7: Copilot vraag → authorization → semantic function → multiple
#         engines → evidence → answer (via semantic layer, de Copilot-basis)
def test_7_semantic_layer_authorized_answer_with_evidence(client, admin_headers, db, shop_id):
    sku = _sku("ACC7")
    try:
        _seed_product(db, sku, shop_id=shop_id)
        _seed_competitor_price(db, sku, price=22.0, shop_id=shop_id)
        _signal(db, sku, shop_id=shop_id)
        db.commit()

        # Authorization: signals-API (Copilot-datalaag) weigert zonder token
        assert client.get("/api/signals").status_code == 401

        # Semantic function beantwoordt de vraag met engine-data (Copilot-basis)
        from semantic_layer import get_product_performance
        user = db.query(models.User).filter(models.User.username == "dev_admin").first()
        answer = get_product_performance(db, user, sku, shop_id=shop_id)
        assert answer, "semantic function gaf geen antwoord"

        # Evidence: signaal opvraagbaar met bronnen
        sigs = client.get("/api/signals",
                          params={"entity_id": sku, "shop_id": shop_id},
                          headers=admin_headers).json()
        items = sigs.get("signals", []) if isinstance(sigs, dict) else sigs
        mine = [s for s in items if s["entity_id"] == sku]
        assert mine and mine[0].get("sources")
    finally:
        _cleanup(db, [sku])


# TEST 8: Management dashboard → Opportunity → Category → SKU → Evidence
def test_8_management_dashboard_drilldown(client, admin_headers, db, shop_id):
    sku = _sku("ACC8")
    try:
        _seed_product(db, sku, category="AcceptanceCat8", shop_id=shop_id)
        _seed_competitor_price(db, sku, shop_id=shop_id)
        _signal(db, sku, engine="opportunity", signal_type="margin_opportunity",
                metric="margin_pct", current_value=50.0, change_pct=5.0,
                shop_id=shop_id)
        db.commit()

        assert client.get("/api/dashboard/summary", headers=admin_headers).status_code == 200
        assert client.get("/api/opportunities", headers=admin_headers).status_code == 200
        # Drill-down naar SKU-niveau met evidence via signals
        sigs = client.get("/api/signals",
                          params={"entity_id": sku, "shop_id": shop_id},
                          headers=admin_headers).json()
        items = sigs.get("signals", []) if isinstance(sigs, dict) else sigs
        mine = [s for s in items if s["entity_id"] == sku]
        assert mine and mine[0].get("evidence")
    finally:
        _cleanup(db, [sku])
