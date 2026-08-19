"""
Tests voor de Competition Intelligence-laag (taak: concurrentiebeeld compleet):
dekking uit AI-matches, prijs/promo-events + signalen, beschikbaarheid,
elasticiteit, match-review-doorwerking en de multi-concurrent simulatie.
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

PFX = f"CITEST{uuid.uuid4().hex[:6]}"
SKU_A = f"{PFX}-A"
SKU_B = f"{PFX}-B"
COMP_1 = f"{PFX}-shop1.nl"
COMP_2 = f"{PFX}-shop2.nl"

# Constanten voor warn_suspicious_matches-tests (taak 47)
WM_PFX = f"WMTEST{uuid.uuid4().hex[:6]}"
WM_SKU = f"{WM_PFX}-sku"
WM_COMP = f"{WM_PFX}-comp.nl"

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
    """Synthetische data in een geïsoleerde test-shop: 2 SKU's, 2 concurrenten,
    30 dagen historie met een duidelijke prijswijziging en promo-dip.

    Eigen test-shop zorgt ervoor dat engine-runs gefocust kunnen worden op
    alleen deze SKU's, ongeacht hoeveel echte feed-data in de DB staat.
    """
    db = SessionLocal()
    today = date.today()
    shop_id = None
    try:
        # Eigen test-shop aanmaken zodat de engine-run gefocust kan worden
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} CI Shop",
                               active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id

        db.add_all([
            models.DimProduct(sku_id=SKU_A, product_name="CI Test Product A",
                              category=f"{PFX}-cat", current_price=20.0,
                              cost_price=12.0, stock_quantity=50,
                              shop_id=shop_id),
            models.DimProduct(sku_id=SKU_B, product_name="CI Test Product B",
                              category=f"{PFX}-cat", current_price=10.0,
                              cost_price=6.0, stock_quantity=10,
                              shop_id=shop_id),
        ])
        comp1 = models.DimCompetitor(competitor_name=COMP_1)
        comp2 = models.DimCompetitor(competitor_name=COMP_2)
        db.add_all([comp1, comp2])
        db.flush()

        for i in range(30, -1, -1):
            d = today - timedelta(days=i)
            # COMP_1 op SKU_A: stabiel 21.00, vandaag -10% → 18.90 (price event)
            p1 = 18.90 if i == 0 else 21.0
            db.add(models.FactCompetitorPriceDaily(
                date=d, sku_id=SKU_A, competitor_name=COMP_1, price=p1,
                shop_id=shop_id))
            # COMP_2 op SKU_A: promo-dip dag 10..6 (-20%), daarna herstel
            p2 = 16.0 if 6 <= i <= 10 else 20.0
            db.add(models.FactCompetitorPriceDaily(
                date=d, sku_id=SKU_A, competitor_name=COMP_2, price=p2,
                shop_id=shop_id))
            # COMP_1 op SKU_B (wordt straks REJECTED)
            db.add(models.FactCompetitorPriceDaily(
                date=d, sku_id=SKU_B, competitor_name=COMP_1, price=9.5,
                shop_id=shop_id))
            # Eigen prijs + verkoop met variatie voor elasticiteit
            own_p = 20.0 + (0.5 if i % 7 < 3 else -0.5) + (i % 5) * 0.1
            units = max(1, int(60 - 2 * own_p + (0.8 * p1) + (i % 3)))
            db.add(models.FactPriceDaily(date=d, sku_id=SKU_A, price=own_p,
                                          shop_id=shop_id))
            db.add(models.FactSalesDaily(date=d, sku_id=SKU_A, units_sold=units,
                                          revenue=units * own_p, shop_id=shop_id))
            # Aanbod/voorraad: COMP_1 vandaag uit voorraad op SKU_A
            db.add(models.FactCompetitorOfferDaily(
                date=d, own_sku_id=SKU_A, competitor_id=comp1.competitor_id,
                competitor_price_inc_vat=p1, in_stock=(i != 0), delivery_days=2))

        # AI-matches van vandaag
        db.add_all([
            models.AiMatchResult(own_sku_id=SKU_A, competitor_name=COMP_1,
                                 match_type="Exact", confidence=1.0,
                                 explanation_nl="test", status="PENDING",
                                 run_date=today, own_price=20.0,
                                 competitor_price=18.9, price_diff_pct=5.8),
            models.AiMatchResult(own_sku_id=SKU_A, competitor_name=COMP_2,
                                 match_type="Exact", confidence=1.0,
                                 explanation_nl="test", status="PENDING",
                                 run_date=today),
            models.AiMatchResult(own_sku_id=SKU_B, competitor_name=COMP_1,
                                 match_type="Exact", confidence=1.0,
                                 explanation_nl="test", status="REJECTED",
                                 run_date=today),
        ])
        strat = models.CompetitorStrategyResult(
            competitor_name=COMP_1, run_date=today, shop_id=shop_id,
            strategy_type="PRICE_FOLLOWER", strategy_label_nl="Prijsvolger",
            confidence=0.8)
        db.add(strat)
        db.commit()
        yield {"shop_id": shop_id}
    finally:
        # Opruimen: eerst shop-scoped rijen, dan SKU-scoped, dan global
        for model, col in [
            (models.IntelligenceSignal, models.IntelligenceSignal.shop_id),
            (models.CompetitorPriceEvent, models.CompetitorPriceEvent.shop_id),
            (models.CompetitorCoverageResult, models.CompetitorCoverageResult.shop_id),
            (models.CompetitorAvailabilityDaily, models.CompetitorAvailabilityDaily.shop_id),
            (models.CompetitorStrategyResult, models.CompetitorStrategyResult.shop_id),
            (models.CompetitorProfile, models.CompetitorProfile.shop_id),
            (models.CompetitorRanking, models.CompetitorRanking.shop_id),
            (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.shop_id),
            (models.FactSalesDaily, models.FactSalesDaily.shop_id),
            (models.FactPriceDaily, models.FactPriceDaily.shop_id),
            (models.CostUsageRecord, models.CostUsageRecord.shop_id),
        ]:
            if shop_id is not None:
                db.query(model).filter(col == shop_id).delete(
                    synchronize_session=False)
        for model, col in [
            (models.IntelligenceSignal, models.IntelligenceSignal.entity_id),
            (models.CompetitorPriceEvent, models.CompetitorPriceEvent.sku_id),
            (models.FactCompetitorOfferDaily, models.FactCompetitorOfferDaily.own_sku_id),
            (models.AiMatchResult, models.AiMatchResult.own_sku_id),
            (models.SkuElasticity, models.SkuElasticity.sku_id),
            (models.SkuCompetitionScore, models.SkuCompetitionScore.sku_id),
        ]:
            db.query(model).filter(col.in_([SKU_A, SKU_B])).delete(
                synchronize_session=False)
        db.query(models.CompetitorCoverageResult).filter(
            models.CompetitorCoverageResult.competitor_name.in_([COMP_1, COMP_2])
        ).delete(synchronize_session=False)
        db.query(models.CompetitorAvailabilityDaily).filter(
            models.CompetitorAvailabilityDaily.competitor_name.in_([COMP_1, COMP_2])
        ).delete(synchronize_session=False)
        db.query(models.CompetitorStrategyResult).filter(
            models.CompetitorStrategyResult.competitor_name.in_([COMP_1, COMP_2])
        ).delete(synchronize_session=False)
        db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.competitor_name.in_([COMP_1, COMP_2])
        ).delete(synchronize_session=False)
        db.query(models.DimCompetitor).filter(
            models.DimCompetitor.competitor_name.in_([COMP_1, COMP_2])
        ).delete(synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_([SKU_A, SKU_B])).delete(
            synchronize_session=False)
        if shop_id is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == shop_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.fixture(scope="module")
def run_engines(client, admin_headers, seed):
    # Scope de engine-run tot de test-shop zodat de run snel blijft
    # ongeacht hoeveel echte data er in de DB staat (3k+ producten).
    resp = client.post("/api/competition/intelligence/run",
                       json={"shop_id": seed["shop_id"]},
                       headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_run_summary(run_engines):
    assert run_engines["status"] == "voltooid"
    assert run_engines["coverage_rows"] >= 2       # totaal + categorie per concurrent
    assert run_engines["price_events"] >= 1
    assert run_engines["promo_events"] >= 2        # PROMO_START + PROMO_END
    assert run_engines["elasticity_skus"] >= 1


def test_price_change_event_and_signal(client, admin_headers, run_engines, seed):
    sid = seed["shop_id"]
    resp = client.get(f"/api/competition/events?event_type=PRICE_CHANGE&sku_id={SKU_A}&shop_id={sid}",
                      headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    ev = [e for e in items if e["competitor_name"] == COMP_1]
    assert ev, items
    assert ev[0]["change_pct"] == pytest.approx(-10.0, abs=0.2)
    # Signaal boven drempel (10% > 5%)
    db = SessionLocal()
    try:
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "competitor_price_change",
            models.IntelligenceSignal.entity_id == SKU_A,
            models.IntelligenceSignal.status == "active").first()
        assert sig is not None
        assert sig.evidence and sig.sources and sig.explanation
    finally:
        db.close()


def test_promo_events_detected(client, admin_headers, run_engines, seed):
    sid = seed["shop_id"]
    resp = client.get(f"/api/competition/events?sku_id={SKU_A}&event_type=PROMO_START&shop_id={sid}",
                      headers=admin_headers)
    starts = [e for e in resp.json()["items"] if e["competitor_name"] == COMP_2]
    assert starts and starts[0]["promo_depth_pct"] >= 15
    resp = client.get(f"/api/competition/events?sku_id={SKU_A}&event_type=PROMO_END&shop_id={sid}",
                      headers=admin_headers)
    ends = [e for e in resp.json()["items"] if e["competitor_name"] == COMP_2]
    assert ends and ends[0]["promo_duration_days"] >= 3


def test_coverage_excludes_rejected(client, admin_headers, run_engines, seed):
    sid = seed["shop_id"]
    resp = client.get(f"/api/competition/coverage?shop_id={sid}", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    tot_c1 = [i for i in items if i["competitor_name"] == COMP_1 and i["category"] is None]
    assert tot_c1
    # COMP_1 matcht alleen SKU_A (SKU_B is REJECTED)
    assert tot_c1[0]["matched_products"] == 1


def test_profile_real_values(run_engines):
    db = SessionLocal()
    try:
        prof = db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.competitor_name == COMP_1).first()
        assert prof is not None
        # Geen hard-coded placeholders meer
        assert prof.in_stock_rate is not None and prof.in_stock_rate < 1.0
        assert prof.avg_delivery_days == pytest.approx(2.0, abs=0.01)
        assert prof.avg_price_index is not None and prof.avg_price_index != 1.0
    finally:
        db.close()


def test_availability_and_trend_api(client, admin_headers, run_engines, seed):
    sid = seed["shop_id"]
    resp = client.get(f"/api/competition/availability?competitor={COMP_1}&shop_id={sid}",
                      headers=admin_headers)
    assert resp.status_code == 200
    series = resp.json()["competitors"].get(COMP_1)
    assert series and series[-1]["in_stock_rate"] == 0.0  # vandaag OOS
    resp = client.get(f"/api/competition/trends/price-index?days=30&shop_id={sid}",
                      headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()["series"]) >= 5


def test_elasticity_persisted(run_engines):
    db = SessionLocal()
    try:
        e = db.query(models.SkuElasticity).filter(
            models.SkuElasticity.sku_id == SKU_A).order_by(
            models.SkuElasticity.run_date.desc()).first()
        assert e is not None
        assert e.own_price_elasticity is not None and e.own_price_elasticity < 0
        assert e.competitive_elasticity is not None and e.competitive_elasticity >= 0
        assert e.cross_elasticity is not None
    finally:
        db.close()


def test_match_quality_kpis(client, admin_headers, run_engines, seed):
    sid = seed["shop_id"]
    resp = client.get(f"/api/competition/match-quality?shop_id={sid}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["total"] >= 3
    assert body["totals"]["rejected"] >= 1
    assert "Exact" in body["by_match_type"]


def test_simulation(client, admin_headers, run_engines, seed):
    sid = seed["shop_id"]
    resp = client.post("/api/competition/simulate", headers=admin_headers,
                       json={"sku_id": SKU_A, "change_pct": -0.05, "shop_id": sid})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data_available"] is True
    comps = {c["competitor"] for c in body["competitors"]}
    assert COMP_1 in comps and COMP_2 in comps
    assert body["price_index"]["if_nobody_follows"] < body["price_index"]["before"]
    assert body["scenario_expected"]["units"] > body["baseline_30d"]["units"]
    # Forceer niet-volgen
    resp2 = client.post("/api/competition/simulate", headers=admin_headers,
                        json={"sku_id": SKU_A, "change_pct": -0.05,
                              "shop_id": sid, "assume_no_follow": [COMP_1, COMP_2]})
    b2 = resp2.json()
    assert all(c["follow_probability"] == 0.0 for c in b2["competitors"])
    assert b2["scenario_expected"]["units"] >= body["scenario_expected"]["units"]


def test_simulation_validation(client, admin_headers, seed):
    resp = client.post("/api/competition/simulate", headers=admin_headers,
                       json={"sku_id": SKU_A, "change_pct": 0.9, "shop_id": seed["shop_id"]})
    assert resp.status_code == 400


def test_rejection_survives_match_rebuild(client, admin_headers, run_engines, seed):
    """build_ai_matches herbouwt de matches uit de feed, maar mag een
    analistenbeoordeling (REJECTED/APPROVED) niet wissen."""
    import feed_ingest
    db = SessionLocal()
    try:
        feed_ingest.build_ai_matches(db, shop_id=seed["shop_id"])
        db.commit()
        m = db.query(models.AiMatchResult).filter(
            models.AiMatchResult.own_sku_id == SKU_B,
            models.AiMatchResult.competitor_name == COMP_1,
        ).order_by(models.AiMatchResult.run_date.desc()).first()
        assert m is not None
        assert m.status == "REJECTED"
    finally:
        db.close()


def test_signals_idempotent_on_rerun(client, admin_headers, run_engines, seed):
    """Een tweede run op dezelfde dag mag geen extra signalen creëren."""
    db = SessionLocal()
    try:
        def count():
            return db.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.entity_id == SKU_A,
                models.IntelligenceSignal.signal_type.in_(
                    ["competitor_price_change", "competitor_promo_detected",
                     "competitor_oos_opportunity"])).count()
        before = count()
        # Scope de herrun tot de test-shop (idempotentie-check voor onze data)
        resp = client.post("/api/competition/intelligence/run",
                           json={"shop_id": seed["shop_id"]},
                           headers=admin_headers)
        assert resp.status_code == 200
        db.expire_all()
        assert count() == before
    finally:
        db.close()


def test_price_index_uses_historical_own_price(client, admin_headers, run_engines, seed):
    """De trend gebruikt fact_price_daily van die dag; een latere wijziging
    van current_price mag de historie niet herschrijven."""
    sid = seed["shop_id"]
    db = SessionLocal()
    try:
        prod = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_A).first()
        original = float(prod.current_price)
        prod.current_price = original * 10  # extreme wijziging
        db.commit()
        resp = client.get(f"/api/competition/trends/price-index?days=30&shop_id={sid}",
                          headers=admin_headers)
        assert resp.status_code == 200
        series = resp.json()["series"]
        # Historische punten blijven rond ~1.0 (eigen dagprijs / concurrent),
        # niet rond ~10 zoals bij gebruik van current_price.
        older = [p for p in series[:-1]]
        assert older and all(p["avg_price_index"] < 3 for p in older), series
        prod = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_A).first()
        prod.current_price = original
        db.commit()
    finally:
        db.close()


def test_multi_shop_isolation(client, admin_headers, run_engines):
    """Data van een tweede shop mag dekking/events van de default shop niet
    vervuilen, en de endpoints filteren op shop-scope."""
    import uuid as _uuid
    code = f"citest-{_uuid.uuid4().hex[:8]}"
    resp = client.post("/api/shops", json={"shop_code": code, "name": "CI Shop B"},
                       headers=admin_headers)
    assert resp.status_code == 201, resp.text
    shop_b = resp.json()["id"]
    sku_b2 = f"{PFX}-SHOPB"
    db = SessionLocal()
    try:
        db.add(models.DimProduct(sku_id=sku_b2, product_name="Shop B product",
                                 category=f"{PFX}-cat-b", current_price=30.0,
                                 shop_id=shop_b))
        today = date.today()
        for i in (1, 0):
            db.add(models.FactCompetitorPriceDaily(
                date=today - timedelta(days=i), sku_id=sku_b2,
                # Prijzen dicht bij de eigen prijs (30.0) houden: een groot
                # verschil zou de match als 'verdacht' kunnen classificeren
                # en dan telt hij niet mee in de dekking.
                competitor_name=COMP_1, price=29.0 if i else 27.0,
                shop_id=shop_b))
        db.add(models.AiMatchResult(own_sku_id=sku_b2, competitor_name=COMP_1,
                                    match_type="Exact", confidence=1.0,
                                    explanation_nl="test", status="PENDING",
                                    run_date=today))
        db.commit()

        resp = client.post("/api/competition/intelligence/run", headers=admin_headers)
        assert resp.status_code == 200

        # Default-shop views bevatten geen shop-B data
        resp = client.get("/api/competition/events?days=7", headers=admin_headers)
        assert all(e["sku_id"] != sku_b2 for e in resp.json()["items"])
        resp = client.get("/api/competition/coverage", headers=admin_headers)
        assert all(i["category"] != f"{PFX}-cat-b" for i in resp.json()["items"])
        # Shop-B scope ziet zijn eigen event wél
        resp = client.get(f"/api/competition/events?days=7&shop_id={shop_b}",
                          headers=admin_headers)
        assert any(e["sku_id"] == sku_b2 for e in resp.json()["items"])
        # Coverage-rijen van shop B tellen alleen shop-B producten
        cov_b = client.get(f"/api/competition/coverage?shop_id={shop_b}",
                           headers=admin_headers).json()["items"]
        tot = [i for i in cov_b if i["category"] is None]
        assert tot and tot[0]["own_products"] == 1

        # AI-matching isolatie: default shop ziet shop-B match niet
        resp = client.get("/api/competition/ai-matching", headers=admin_headers)
        assert resp.status_code == 200
        match_skus = [m["own_sku_id"] for m in resp.json()["items"]]
        assert sku_b2 not in match_skus, "Default shop ziet shop-B match"

        # Shop-B scope ziet zijn eigen match wél
        resp = client.get(f"/api/competition/ai-matching?shop_id={shop_b}",
                          headers=admin_headers)
        assert resp.status_code == 200
        match_skus_b = [m["own_sku_id"] for m in resp.json()["items"]]
        assert sku_b2 in match_skus_b, "Shop-B scope ziet eigen match niet"

        # IDOR-check: approve via default-shop scope geeft 404 voor shop-B match
        match_b = db.query(models.AiMatchResult).filter(
            models.AiMatchResult.own_sku_id == sku_b2).first()
        if match_b:
            resp_idor = client.post(
                f"/api/competition/ai-matching/{match_b.id}/approve",
                headers=admin_headers)
            assert resp_idor.status_code == 404, (
                f"IDOR: approve van shop-B match via default shop gaf {resp_idor.status_code}")

        # Summary en skus: default shop geeft 200 (kan leeg zijn, maar bevat geen shop-B producten)
        resp = client.get("/api/competition/summary", headers=admin_headers)
        assert resp.status_code == 200
        resp = client.get("/api/competition/skus", headers=admin_headers)
        assert resp.status_code == 200
        assert all(m["sku_id"] != sku_b2 for m in resp.json()["items"])

        # Strategies en rankings: shop-B scope geeft 200 (data afhankelijk van run)
        resp = client.get(f"/api/competition/strategies?shop_id={shop_b}",
                          headers=admin_headers)
        assert resp.status_code == 200
        resp = client.get(f"/api/competition/rankings?shop_id={shop_b}",
                          headers=admin_headers)
        assert resp.status_code == 200
    finally:
        for model, col in [
            (models.IntelligenceSignal, models.IntelligenceSignal.shop_id),
            (models.CompetitorPriceEvent, models.CompetitorPriceEvent.shop_id),
            (models.CompetitorCoverageResult, models.CompetitorCoverageResult.shop_id),
            (models.CompetitorAvailabilityDaily, models.CompetitorAvailabilityDaily.shop_id),
            (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.shop_id),
            (models.DimProduct, models.DimProduct.shop_id),
            (models.CostUsageRecord, models.CostUsageRecord.shop_id),
            (models.CompetitorProfile, models.CompetitorProfile.shop_id),
            (models.CompetitorStrategyResult, models.CompetitorStrategyResult.shop_id),
            (models.CompetitorRanking, models.CompetitorRanking.shop_id),
        ]:
            db.query(model).filter(col == shop_b).delete(synchronize_session=False)
        db.query(models.AiMatchResult).filter(
            models.AiMatchResult.own_sku_id == sku_b2).delete(synchronize_session=False)
        db.query(models.SkuElasticity).filter(
            models.SkuElasticity.sku_id == sku_b2).delete(synchronize_session=False)
        db.query(models.DimShop).filter(models.DimShop.id == shop_b).delete(
            synchronize_session=False)
        db.commit()
        db.close()

def test_multi_shop_dashboard_profile_strategy_simulation(client, admin_headers, run_engines, seed):
    """Dashboard, CompetitorProfile, CompetitorStrategyResult en simulatie mogen
    nooit data van een andere shop laten lekken of op schrijven."""
    import uuid as _uuid
    code2 = f"citest2-{_uuid.uuid4().hex[:8]}"
    resp = client.post("/api/shops", json={"shop_code": code2, "name": "CI Shop C"},
                       headers=admin_headers)
    assert resp.status_code == 201, resp.text
    shop_c = resp.json()["id"]
    sku_c = f"{PFX}-SHOPC"
    comp_c = f"{PFX}-shopc-comp.nl"
    db = SessionLocal()
    today = date.today()
    try:
        db.add(models.DimProduct(sku_id=sku_c, product_name="Shop C product",
                                 category=f"{PFX}-cat-c", current_price=50.0,
                                 shop_id=shop_c))
        # Concurrentprijzen voor shop C (eigen concurrent, eigen SKU)
        for i in range(5, -1, -1):
            db.add(models.FactCompetitorPriceDaily(
                date=today - timedelta(days=i), sku_id=sku_c,
                competitor_name=comp_c, price=45.0,
                shop_id=shop_c))
        # Profiel + strategie voor shop C concurrent
        db.add(models.CompetitorProfile(
            competitor_name=comp_c, shop_id=shop_c,
            assortment_size=99, price_segment="BUDGET",
            relevance_label="HIGH", traffic_light="green",
            run_date=today,
        ))
        db.add(models.CompetitorStrategyResult(
            competitor_name=comp_c, shop_id=shop_c,
            strategy_type="SHOPC_STRAT", run_date=today, confidence=0.9,
        ))
        # CategoryCompetitorRelevance voor shop C
        db.add(models.CategoryCompetitorRelevance(
            competitor_name=comp_c, shop_id=shop_c,
            category=f"{PFX}-cat-c", combined_score=0.95,
        ))
        db.commit()

        # 1. Dashboard voor de default shop mag geen shop-C-concurrent bevatten
        resp = client.get("/api/competition/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        all_names_default = [
            item["competitor_name"]
            for cat in resp.json().get("categories", [])
            for item in cat.get("competitors", [])
        ]
        assert comp_c not in all_names_default, (
            "Dashboard default shop bevat concurrent van shop C"
        )

        # 2. Dashboard voor shop C bevat wél de shop-C-concurrent
        resp_c = client.get(f"/api/competition/dashboard?shop_id={shop_c}",
                            headers=admin_headers)
        assert resp_c.status_code == 200
        all_names_c = [
            item["competitor_name"]
            for cat in resp_c.json().get("categories", [])
            for item in cat.get("competitors", [])
        ]
        assert comp_c in all_names_c, (
            "Dashboard shop C toont niet de eigen concurrent"
        )

        # 3. /competitors voor default shop bevat comp_c NIET
        resp_prof = client.get("/api/competition/competitors", headers=admin_headers)
        assert resp_prof.status_code == 200
        names_default = [p["competitor_name"] for p in resp_prof.json().get("items", [])]
        assert comp_c not in names_default, (
            "/competitors default-shop toont concurrent van shop C"
        )

        # 4. /competitors voor shop C bevat comp_c wél
        resp_prof_c = client.get(f"/api/competition/competitors?shop_id={shop_c}",
                                 headers=admin_headers)
        assert resp_prof_c.status_code == 200
        names_c = [p["competitor_name"] for p in resp_prof_c.json().get("items", [])]
        assert comp_c in names_c, (
            "/competitors shop C toont niet de eigen concurrent"
        )

        # 5. Strategies voor de default shop bevatten comp_c NIET
        resp_strat = client.get("/api/competition/strategies", headers=admin_headers)
        assert resp_strat.status_code == 200
        # Strategies haalt live fact-data op; comp_c heeft alleen shop-C fact-rijen
        # dus strategieen default-shop mag comp_c niet tonen
        strat_names = [s.get("competitor") for s in resp_strat.json().get("strategieen", [])]
        assert comp_c not in strat_names, (
            "/strategies default-shop bevat strategie van shop-C-concurrent"
        )

        # 6. Simulatie voor SKU_A (onze test-shop) mag geen shop-C fact-rijen gebruiken
        resp_sim = client.post("/api/competition/simulate",
                               json={"sku_id": SKU_A, "change_pct": -0.05,
                                     "shop_id": seed["shop_id"]},
                               headers=admin_headers)
        assert resp_sim.status_code == 200
        sim = resp_sim.json()
        if sim.get("data_available"):
            comp_names_sim = [c["competitor"] for c in sim.get("per_competitor", [])]
            assert comp_c not in comp_names_sim, (
                "Simulatie voor SKU_A bevat concurrent van shop C"
            )

    finally:
        for model, col in [
            (models.CategoryCompetitorRelevance, models.CategoryCompetitorRelevance.shop_id),
            (models.CompetitorProfile, models.CompetitorProfile.shop_id),
            (models.CompetitorStrategyResult, models.CompetitorStrategyResult.shop_id),
            (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.shop_id),
            (models.DimProduct, models.DimProduct.shop_id),
            (models.CostUsageRecord, models.CostUsageRecord.shop_id),
        ]:
            db.query(model).filter(col == shop_c).delete(synchronize_session=False)
        db.query(models.DimShop).filter(models.DimShop.id == shop_c).delete(
            synchronize_session=False)
        db.commit()
        db.close()
def test_viewer_cannot_run_engines(client, seed):
    resp = client.post("/api/auth/login",
                       json={"username": "dev_viewer", "password": "viewer123"})
    if resp.status_code != 200:
        pytest.skip("geen viewer-account beschikbaar")
    h = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert client.post("/api/competition/intelligence/run", headers=h).status_code == 403

def test_ols_returns_r2():
    """_ols_two_vars retourneert nu (b, c, r2) in plaats van (b, c)."""
    import math
    from engine.competition_intelligence import _ols_two_vars

    # Perfecte lineaire relatie → R² ≈ 1.0
    # x1 en x2 mogen NIET perfect gecorreleerd zijn (singuliere matrix)
    x1 = [float(i) for i in range(10)]
    x2 = [float(i % 3) + 0.1 * i for i in range(10)]  # niet-collineair
    y  = [2.0 + 3.0 * x1[i] - 1.0 * x2[i] for i in range(10)]
    res = _ols_two_vars(y, x1, x2)
    assert res is not None
    b, c, r2 = res
    assert abs(b - 3.0) < 1e-6
    assert abs(c - (-1.0)) < 1e-6
    assert abs(r2 - 1.0) < 1e-6
@pytest.fixture(scope="module")
def suspicious_seed():
    """Seed: 6 PENDING AI-matches met |price_diff_pct| > 40 zodat de drempel
    (standaard 5) gehaald wordt, plus 1 match met klein verschil als controle."""
    db = SessionLocal()
    today = date.today()
    sid = None
    skus = []
    try:
        shop = models.DimShop(shop_code=f"{WM_PFX}", name=f"{WM_PFX}-shop",
                              active=True)
        db.add(shop)
        db.flush()
        sid = shop.id

        for i in range(7):
            sku_id = f"{WM_SKU}-{i}"
            db.add(models.DimProduct(
                sku_id=sku_id, product_name=f"WM Product {i}",
                current_price=10.0, shop_id=sid))
            skus.append(sku_id)
        db.flush()

        # 6 verdachte matches (|price_diff_pct| > 40)
        for i in range(6):
            db.add(models.AiMatchResult(
                own_sku_id=skus[i], competitor_name=WM_COMP,
                match_type="Exact", confidence=0.9,
                explanation_nl="test", status="PENDING",
                run_date=today, own_price=10.0,
                competitor_price=17.0, price_diff_pct=70.0,
            ))
        # 1 match met klein verschil — telt NIET mee
        db.add(models.AiMatchResult(
            own_sku_id=skus[6], competitor_name=WM_COMP,
            match_type="Exact", confidence=0.9,
            explanation_nl="test", status="PENDING",
            run_date=today, own_price=10.0,
            competitor_price=10.5, price_diff_pct=5.0,
        ))
        db.commit()
        yield sid, skus
    finally:
        if sid is not None:
            db.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.entity_id == "ai-matching",
                models.IntelligenceSignal.signal_type == "suspicious_ai_matches",
                models.IntelligenceSignal.shop_id == sid,
            ).delete(synchronize_session=False)
        if skus:
            for sku_id in skus:
                db.query(models.AiMatchResult).filter(
                    models.AiMatchResult.own_sku_id == sku_id,
                ).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(skus),
            ).delete(synchronize_session=False)
        if sid is not None:
            for model, col in [
                (models.IntelligenceSignal, models.IntelligenceSignal.shop_id),
                (models.CompetitorCoverageResult, models.CompetitorCoverageResult.shop_id),
                (models.CompetitorAvailabilityDaily, models.CompetitorAvailabilityDaily.shop_id),
                (models.CompetitorStrategyResult, models.CompetitorStrategyResult.shop_id),
                (models.CompetitorProfile, models.CompetitorProfile.shop_id),
                (models.CategoryCompetitorRelevance, models.CategoryCompetitorRelevance.shop_id),
                (models.CompetitorRanking, models.CompetitorRanking.shop_id),
                (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.shop_id),
                (models.CostUsageRecord, models.CostUsageRecord.shop_id),
            ]:
                db.query(model).filter(col == sid).delete(synchronize_session=False)
        if skus:
            for sku_id in skus:
                db.query(models.AiMatchResult).filter(
                    models.AiMatchResult.own_sku_id == sku_id,
                ).delete(synchronize_session=False)
                db.query(models.CompetitorPriceEvent).filter(
                    models.CompetitorPriceEvent.sku_id == sku_id,
                ).delete(synchronize_session=False)
                db.query(models.SkuElasticity).filter(
                    models.SkuElasticity.sku_id == sku_id,
                ).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(skus),
            ).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == sid,
            ).delete(synchronize_session=False)
        db.commit()
        db.close()

def test_warn_suspicious_matches_publishes_signal(suspicious_seed):
    """Als het aantal verdachte matches >= drempel, moet er een signaal worden gepubliceerd."""
    from engine.competition_intelligence import warn_suspicious_matches
    sid, _skus = suspicious_seed
    db = SessionLocal()
    try:
        n = warn_suspicious_matches(db, date.today())
        assert n >= 1, "Verwacht minstens 1 signaal boven de drempel"
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "suspicious_ai_matches",
            models.IntelligenceSignal.entity_id == "ai-matching",
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).first()
        assert sig is not None, "Geen actief signaal gevonden"
        assert sig.explanation and "verdachte" in sig.explanation.lower()
        ev = sig.evidence or {}
        assert ev.get("suspicious_count") >= 6
        assert ev.get("link") == "/competition/ai-matching"
        assert sig.sources and "ai_match_result" in sig.sources
    finally:
        db.close()

def test_ai_matching_suspect_filter(client, admin_headers, suspicious_seed):
    """suspect=true filtert de lijst tot PENDING matches met |price_diff_pct| > 40."""
    sid, skus = suspicious_seed
    # Zonder filter: alle 7 matches van deze shop
    resp = client.get(f"/api/competition/ai-matching?shop_id={sid}&page_size=100",
                      headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 7
    # Met suspect=true: alleen de 6 verdachte
    resp = client.get(f"/api/competition/ai-matching?shop_id={sid}&suspect=true&page_size=100",
                      headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 6
    for item in data["items"]:
        assert item["status"] == "PENDING"
        assert abs(item["price_diff_pct"]) > 40
    # suspect=false gedraagt zich als geen filter
    resp = client.get(f"/api/competition/ai-matching?shop_id={sid}&suspect=false&page_size=100",
                      headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 7
def test_warn_suspicious_matches_idempotent(suspicious_seed):
    """Tweede aanroep op dezelfde run_date mag geen extra signaal aanmaken
    (test_warn_suspicious_matches_publishes_signal heeft al één signaal aangemaakt)."""
    from engine.competition_intelligence import warn_suspicious_matches
    sid, _skus = suspicious_seed
    db = SessionLocal()
    try:
        rd = date.today()
        n = warn_suspicious_matches(db, rd)
        assert n == 0, f"Idempotentie geschonden: {n} extra signalen aangemaakt"
        count = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "suspicious_ai_matches",
            models.IntelligenceSignal.entity_id == "ai-matching",
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).count()
        assert count == 1, f"Verwacht 1 actief signaal, kreeg {count}"
    finally:
        db.close()


def test_warn_suspicious_matches_below_threshold():
    """Als het aantal verdachte matches voor een shop kleiner is dan de drempel,
    mag er geen signaal worden gepubliceerd voor die shop."""
    from engine.competition_intelligence import warn_suspicious_matches
    db = SessionLocal()
    pfx = f"WMLOW{uuid.uuid4().hex[:6]}"
    sid = None
    skus: list[str] = []
    try:
        shop = models.DimShop(shop_code=pfx, name=f"{pfx}-shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        # 4 verdachte matches — onder de standaard drempel van 5
        for i in range(4):
            sku_id = f"{pfx}-SKU-{i}"
            db.add(models.DimProduct(
                sku_id=sku_id, product_name=f"Low {i}",
                current_price=10.0, shop_id=sid))
            skus.append(sku_id)
        db.flush()
        for sku_id in skus:
            db.add(models.AiMatchResult(
                own_sku_id=sku_id, competitor_name=f"{pfx}-comp",
                match_type="Exact", confidence=0.9,
                explanation_nl="test", status="PENDING",
                run_date=date.today(), own_price=10.0,
                competitor_price=17.0, price_diff_pct=70.0,
            ))
        db.commit()

        warn_suspicious_matches(db, date.today())

        # Onze specifieke shop heeft te weinig verdachte matches → geen signaal
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "suspicious_ai_matches",
            models.IntelligenceSignal.entity_id == "ai-matching",
            models.IntelligenceSignal.shop_id == sid,
        ).first()
        assert sig is None, (
            f"Onverwacht signaal voor shop met slechts {len(skus)} verdachte matches "
            f"(drempel = 5)")
    finally:
        if skus:
            for sku_id in skus:
                db.query(models.AiMatchResult).filter(
                    models.AiMatchResult.own_sku_id == sku_id,
                ).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(skus),
            ).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.shop_id == sid,
            ).delete(synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid,
            ).delete(synchronize_session=False)
            db.query(models.DimShop).filter(
                models.DimShop.id == sid,
            ).delete(synchronize_session=False)
        db.commit()
        db.close()

def test_warn_suspicious_matches_auto_resolves_after_review(client):
    """Zodra alle verdachte matches beoordeeld zijn (geen PENDING meer boven de
    drempel), moet een actief suspicious_ai_matches-signaal automatisch op
    'resolved' gezet worden. Idempotent: een tweede run publiceert niet opnieuw."""
    from engine.competition_intelligence import warn_suspicious_matches
    db = SessionLocal()
    pfx = f"WMRES{uuid.uuid4().hex[:6]}"
    sid = None
    skus: list[str] = []
    try:
        shop = models.DimShop(shop_code=pfx, name=f"{pfx}-shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        for i in range(6):
            sku_id = f"{pfx}-SKU-{i}"
            db.add(models.DimProduct(
                sku_id=sku_id, product_name=f"Res {i}",
                current_price=10.0, shop_id=sid))
            skus.append(sku_id)
        db.flush()
        for sku_id in skus:
            db.add(models.AiMatchResult(
                own_sku_id=sku_id, competitor_name=f"{pfx}-comp",
                match_type="Exact", confidence=0.9,
                explanation_nl="test", status="PENDING",
                run_date=date.today(), own_price=10.0,
                competitor_price=17.0, price_diff_pct=70.0,
            ))
        db.commit()

        # Run 1: signaal wordt gepubliceerd
        n = warn_suspicious_matches(db, date.today(), shop_id=sid)
        assert n == 1
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "suspicious_ai_matches",
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).one()

        # Analist beoordeelt alle verdachte matches
        db.query(models.AiMatchResult).filter(
            models.AiMatchResult.own_sku_id.in_(skus),
        ).update({"status": "APPROVED"}, synchronize_session=False)
        db.commit()

        # Run 2: signaal wordt automatisch resolved, geen nieuw signaal
        n = warn_suspicious_matches(db, date.today(), shop_id=sid)
        assert n == 0
        db.refresh(sig)
        assert sig.status == "resolved"

        # Run 3: idempotent — resolved signaal blijft resolved, niets nieuws
        n = warn_suspicious_matches(db, date.today(), shop_id=sid)
        assert n == 0
        statuses = [s.status for s in db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "suspicious_ai_matches",
            models.IntelligenceSignal.shop_id == sid,
        ).all()]
        assert statuses == ["resolved"], f"Verwacht exact één resolved signaal, kreeg {statuses}"
    finally:
        if skus:
            for sku_id in skus:
                db.query(models.AiMatchResult).filter(
                    models.AiMatchResult.own_sku_id == sku_id,
                ).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(skus),
            ).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.shop_id == sid,
            ).delete(synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid,
            ).delete(synchronize_session=False)
            db.query(models.DimShop).filter(
                models.DimShop.id == sid,
            ).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_run_all_includes_suspicious_match_signals(suspicious_seed):
    """run_all retourneert suspicious_match_signals in de samenvatting."""
    sid, _skus = suspicious_seed
    # Ruim vorige signalen op zodat we een verse meting krijgen
    db = SessionLocal()
    try:
        db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "suspicious_ai_matches",
            models.IntelligenceSignal.entity_id == "ai-matching",
            models.IntelligenceSignal.shop_id == sid,
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    from engine.competition_intelligence import run_all
    db2 = SessionLocal()
    try:
        # Scope de run tot de test-shop van suspicious_seed (snel)
        result = run_all(db2, date.today(), shop_id=sid)
        assert "suspicious_match_signals" in result
        assert isinstance(result["suspicious_match_signals"], int)
    finally:
        db2.close()

def _seed_elast_sku(db, sku, n_days=20, own_prices=None, comp_prices=None,
                    sales_fn=None):
    """Zaai een SKU met factrijen voor elasticiteitstests.
    sales_fn(i, price) -> units_sold; standaard: 100.
    """
    if own_prices is None:
        own_prices = ([10.0, 10.5, 11.0, 11.5, 12.0] * 10)[:n_days]
    if comp_prices is None:
        comp_prices = [10.8, 11.3, 11.8]
    if sales_fn is None:
        sales_fn = lambda i, p: 100
    db.add(models.DimProduct(sku_id=sku, product_name=f"ElastTest {sku}",
                             current_price=10.0, cost_price=6.0, stock_quantity=20))
    db.flush()
    today = date.today()
    for i in range(n_days):
        d = today - timedelta(days=i + 1)
        p = own_prices[i]
        units = max(1, sales_fn(i, p))
        db.add(models.FactPriceDaily(date=d, sku_id=sku, price=p))
        db.add(models.FactSalesDaily(date=d, sku_id=sku,
                                      units_sold=units, revenue=units * p))
        db.add(models.FactCompetitorPriceDaily(
            date=d, sku_id=sku, competitor_name="tc.nl",
            price=comp_prices[i % len(comp_prices)]))
    db.commit()

def test_ols_noisy_data_low_r2():
    """Bij ruisige data geeft _ols_two_vars een lage R²."""
    import random
    from engine.competition_intelligence import _ols_two_vars
    random.seed(42)
    n = 20
    # Zorg voor niet-collineaire predictors
    x1 = [float(i) for i in range(n)]
    x2 = [float(i % 4) + 0.7 * (i // 4) for i in range(n)]  # niet-collineair
    # Pure ruis als y → R² dicht bij 0
    y = [random.uniform(-5, 5) for _ in range(n)]
    res = _ols_two_vars(y, x1, x2)
    assert res is not None
    _, _, r2 = res
    assert r2 < 0.5  # ruis → lage fit

def test_elasticity_heuristic_low_confidence_when_few_data():
    """Bij te weinig datapunten (< elasticity_min_days) gebruikt de engine
    de heuristiek met lage of middelhoge confidence (nooit regressie-niveau)."""
    db = SessionLocal()
    today = date.today()
    sku = f"ELAST-FEW-{uuid.uuid4().hex[:6]}"
    try:
        db.add(models.DimProduct(sku_id=sku, product_name="Few-data SKU",
                                 current_price=15.0, cost_price=8.0, stock_quantity=5))
        db.flush()
        # Voeg slechts 3 datadagen toe (onder elasticity_min_days=14)
        for i in range(3):
            d = today - timedelta(days=i)
            db.add(models.FactPriceDaily(date=d, sku_id=sku, price=15.0))
            db.add(models.FactSalesDaily(date=d, sku_id=sku, units_sold=10,
                                         revenue=150.0))
            db.add(models.FactCompetitorPriceDaily(
                date=d, sku_id=sku, competitor_name="test-comp.nl", price=16.0))
        db.commit()

        from engine.competition_intelligence import run_elasticity
        run_elasticity(db, run_date=today)
        db.expire_all()

        e = (db.query(models.SkuElasticity)
             .filter(models.SkuElasticity.sku_id == sku,
                     models.SkuElasticity.run_date == today)
             .first())
        assert e is not None
        assert e.method_label == "heuristiek", (
            f"Verwacht heuristiek bij 3 datapunten, kreeg: {e.method_label!r}"
        )
        assert e.regression_r2 is None
        # Confidence mag niet in de regressie-range vallen (≥ 0.5 + 14/100)
        assert e.elasticity_confidence_score < 0.65
    finally:
        db.query(models.SkuElasticity).filter(
            models.SkuElasticity.sku_id == sku).delete()
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id == sku).delete()
        db.query(models.FactSalesDaily).filter(
            models.FactSalesDaily.sku_id == sku).delete()
        db.query(models.FactPriceDaily).filter(
            models.FactPriceDaily.sku_id == sku).delete()
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == sku).delete()
        db.commit()
        db.close()

def test_simulation_exposes_method_label(client, admin_headers, run_engines, seed):
    """De simulatie toont het methodeniveau van de gebruikte elasticiteit."""
    resp = client.post("/api/competition/simulate", headers=admin_headers,
                       json={"sku_id": SKU_A, "change_pct": -0.05, "shop_id": seed["shop_id"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    eu = body.get("elasticity_used", {})
    assert "method" in eu, f"'method' ontbreekt in elasticity_used: {eu}"
    assert eu["method"] in ("regressie", "heuristiek", "default"), eu["method"]
    # regression_r2 is None bij heuristiek, float bij regressie
    assert "regression_r2" in eu
    # betrouwbaarheidsklasse wordt meegegeven zodat het dashboard kan waarschuwen
    assert "confidence_class" in eu, f"'confidence_class' ontbreekt: {eu}"
    assert eu["confidence_class"] in (
        "hoog_betrouwbaar", "bruikbaar", "laag_betrouwbaar", None), eu["confidence_class"]
    if eu["method"] == "default":
        assert eu["confidence_class"] is None

def test_simulation_is_shop_scoped(client, admin_headers, run_engines, seed):
    """Een sku_id uit een andere shop mag nooit gesimuleerd worden (404),
    en de gerapporteerde method/R²/confidence horen bij de eigen shop."""
    db = SessionLocal()
    other_id = None
    try:
        other = models.DimShop(shop_code=f"{PFX}-other",
                               name=f"{PFX} Other Shop", active=True)
        db.add(other)
        db.commit()
        other_id = other.id
        # Zelfde SKU opvragen binnen de verkeerde shop-scope → 404, geen data-lek
        resp = client.post("/api/competition/simulate", headers=admin_headers,
                           json={"sku_id": SKU_A, "change_pct": -0.05,
                                 "shop_id": other_id})
        assert resp.status_code == 404, resp.text
        # Juiste shop: simulatie levert elasticiteitsmetadata voor déze shop
        resp2 = client.post("/api/competition/simulate", headers=admin_headers,
                            json={"sku_id": SKU_A, "change_pct": -0.05,
                                  "shop_id": seed["shop_id"]})
        assert resp2.status_code == 200, resp2.text
        body = resp2.json()
        assert body.get("shop_id") == seed["shop_id"]
        eu = body.get("elasticity_used", {})
        assert "method" in eu and "regression_r2" in eu and "confidence_class" in eu
    finally:
        if other_id is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == other_id).delete()
            db.commit()
        db.close()
def test_elasticity_r2_gate_forces_heuristic_despite_negative_b():
    """R²-drempel (DETERMINISTISCH): engine kiest 'heuristiek' als R² < drempel,
    ook als b < 0 (correct negatief teken — de sign-check zou dus door mogen gaan).

    We patchen _ols_two_vars zodat het deterministisch (-1.5, 0.3, 0.05) retourneert:
    b=-1.5 heeft het juiste economische teken, maar R²=0.05 < min_r2=0.10.
    Zonder de R²-check zou de engine de regressie accepteren; MET de check moet
    hij terugvallen op 'heuristiek' met regression_r2=None.
    Dit bewijst dat de R²-check niet verwijderbaar is zonder de test te breken.
    """
    from unittest.mock import patch
    from engine import competition_intelligence as ci
    from engine.competition_intelligence import run_elasticity, DEFAULTS

    db = SessionLocal()
    today = date.today()
    sku = f"ELAST-GATE-{uuid.uuid4().hex[:6]}"
    try:
        # 20 dagen, 5 unieke prijzen (voldoet aan min_days=14 en min_unique=5)
        _seed_elast_sku(db, sku, n_days=20,
                        own_prices=([10.0, 10.5, 11.0, 11.5, 12.0] * 4),
                        sales_fn=lambda i, p: int(110 - 4 * p))  # negatief verband

        min_r2 = DEFAULTS["elasticity_min_r2"]  # 0.10
        assert min_r2 > 0.05, "Testwaarde R²=0.05 moet echte drempel onderschrijden"

        # OLS-stub: correct teken, slechte fit → engine MOET heuristiek kiezen
        with patch.object(ci, '_ols_two_vars', return_value=(-1.5, 0.3, 0.05)):
            run_elasticity(db, run_date=today)

        db.expire_all()
        e = (db.query(models.SkuElasticity)
             .filter(models.SkuElasticity.sku_id == sku,
                     models.SkuElasticity.run_date == today)
             .first())
        assert e is not None, "Geen SkuElasticity-record aangemaakt"
        assert e.method_label == "heuristiek", (
            f"b=-1.5 maar R²=0.05 < {min_r2}: verwacht 'heuristiek', "
            f"maar method_label='{e.method_label}'"
        )
        assert e.regression_r2 is None, (
            f"regression_r2 moet None zijn bij heuristiek, is {e.regression_r2}"
        )
    finally:
        _cleanup_elast_sku(db, sku)
        db.close()

def test_elasticity_method_label_persisted(run_engines):
    """Na een engine-run heeft elk SkuElasticity-record een method_label."""
    db = SessionLocal()
    try:
        e = (db.query(models.SkuElasticity)
             .filter(models.SkuElasticity.sku_id == SKU_A)
             .order_by(models.SkuElasticity.run_date.desc())
             .first())
        assert e is not None, "Geen SkuElasticity voor SKU_A na engine-run"
        assert e.method_label in ("regressie", "heuristiek"), (
            f"Onverwachte method_label: {e.method_label!r}"
        )
        # Als methode regressie is, moet regression_r2 ingevuld zijn
        if e.method_label == "regressie":
            assert e.regression_r2 is not None and 0.0 <= e.regression_r2 <= 1.0
        # Als methode heuristiek is, moet regression_r2 None zijn
        else:
            assert e.regression_r2 is None
    finally:
        db.close()

def _cleanup_elast_sku(db, sku):
    db.query(models.SkuElasticity).filter(
        models.SkuElasticity.sku_id == sku).delete(synchronize_session=False)
    db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.sku_id == sku).delete(synchronize_session=False)
    db.query(models.FactSalesDaily).filter(
        models.FactSalesDaily.sku_id == sku).delete(synchronize_session=False)
    db.query(models.FactPriceDaily).filter(
        models.FactPriceDaily.sku_id == sku).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == sku).delete(synchronize_session=False)
    db.commit()

def test_elasticity_unique_price_gate_forces_heuristic():
    """Unieke-prijspuntdrempel (DETERMINISTISCH): < 5 unieke eigen prijzen → altijd
    heuristiek, ongeacht R² of teken van b. Onafhankelijke test van deze gate.
    """
    from engine.competition_intelligence import run_elasticity, DEFAULTS

    db = SessionLocal()
    today = date.today()
    sku = f"ELAST-UNQ-{uuid.uuid4().hex[:6]}"
    min_unique = DEFAULTS["elasticity_min_unique_prices"]  # 5
    try:
        # Slechts 3 unieke prijzen (< min_unique=5), genoeg datapunten (21 > 14)
        own_prices = ([10.0, 11.0, 12.0] * 7)  # 21 rijen, 3 unieke waarden
        _seed_elast_sku(db, sku, n_days=21, own_prices=own_prices,
                        sales_fn=lambda i, p: int(120 - 5 * p))  # negatief verband

        run_elasticity(db, run_date=today)
        db.expire_all()

        e = (db.query(models.SkuElasticity)
             .filter(models.SkuElasticity.sku_id == sku,
                     models.SkuElasticity.run_date == today)
             .first())
        assert e is not None, "Geen SkuElasticity-record aangemaakt"
        assert e.method_label == "heuristiek", (
            f"3 unieke prijzen < {min_unique}: verwacht 'heuristiek', "
            f"maar method_label='{e.method_label}'"
        )
        assert e.regression_r2 is None
    finally:
        _cleanup_elast_sku(db, sku)
        db.close()


# ── Trage-run-bewaking (taak 100) ────────────────────────────────────────────

def test_run_all_reports_timings_and_scoped_run_has_no_slow_signal(run_engines, seed):
    """Gescopeerde runs rapporteren per-stap-timings maar zijn uitgezonderd
    van de slow-run-drempel."""
    assert "timings_seconds" in run_engines
    assert "total_seconds" in run_engines
    timings = run_engines["timings_seconds"]
    for step in ("profiles", "coverage", "price_events", "promo_events",
                 "availability", "elasticity", "strategies",
                 "suspicious_matches"):
        assert step in timings, timings
    assert "slow_run_signal" not in run_engines

    db = SessionLocal()
    try:
        n = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "engine_slow_run",
            models.IntelligenceSignal.shop_id == seed["shop_id"],
        ).count()
        assert n == 0
    finally:
        db.close()


def test_slow_full_run_publishes_engine_slow_run_signal(monkeypatch):
    """Een volledige (niet-gescopeerde) run boven de drempel publiceert een
    engine_slow_run-signaal met timings als evidence."""
    from engine import competition_intelligence as ci
    from engine import competitor_profiling

    monkeypatch.setattr(ci, "run_coverage", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(ci, "detect_price_events", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(ci, "detect_promo_events", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(ci, "update_availability", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(ci, "run_elasticity", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(ci, "run_strategies", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(ci, "warn_suspicious_matches", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(ci, "warn_elasticity_degradation", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(ci, "warn_heuristic_share_spike", lambda db, rd, shop_id=None: 0)
    monkeypatch.setattr(competitor_profiling, "build_all_profiles",
                        lambda db, shop_id=None: [])
    # Drempel praktisch op nul: elke run is dan "te traag"
    monkeypatch.setattr(ci, "_cfg", lambda db: dict(
        ci.DEFAULTS, slow_run_threshold_seconds=0.000001))

    db = SessionLocal()
    try:
        result = ci.run_all(db, shop_id=None)
        assert result.get("slow_run_signal") is True
        sig = (db.query(models.IntelligenceSignal)
               .filter(models.IntelligenceSignal.signal_type == "engine_slow_run",
                       models.IntelligenceSignal.status == "active")
               .order_by(models.IntelligenceSignal.id.desc())
               .first())
        assert sig is not None
        assert sig.evidence["threshold_seconds"] == pytest.approx(0.000001)
        assert "timings_seconds" in sig.evidence
        assert sig.explanation
    finally:
        db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "engine_slow_run",
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


# Uniek prefix voor de elasticiteit-degradatietests (eigen test-shop + SKU's)
ED_PFX = f"ED-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def elast_degradation_seed(client):
    """Seed SkuElasticity-historie in een eigen test-shop:

    - SKU-FALL: 2 oudere regressie-runs, daarna 3 opeenvolgende heuristiek-runs
      (laatste = vandaag) → methode-terugvalsignaal verwacht.
    - SKU-R2:   gisteren regressie R²=0.80, vandaag regressie R²=0.50
      (daling 0.30 > drempel 0.15) → R²-dalingssignaal verwacht.
    - SKU-OK:   altijd heuristiek (nooit regressie) → geen signaal.
    - SKU-STAB: regressie met stabiele R² → geen signaal.
    """
    db = SessionLocal()
    today = date.today()
    sid = None
    skus = [f"{ED_PFX}-FALL", f"{ED_PFX}-R2", f"{ED_PFX}-OK", f"{ED_PFX}-STAB"]
    try:
        shop = models.DimShop(shop_code=ED_PFX, name=f"{ED_PFX}-shop",
                              active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        for s in skus:
            db.add(models.DimProduct(sku_id=s, product_name=f"ED {s}",
                                     current_price=10.0, shop_id=sid))
        db.flush()

        def add(sku, days_ago, method, r2):
            db.add(models.SkuElasticity(
                sku_id=sku, run_date=today - timedelta(days=days_ago),
                own_price_elasticity=-1.2, cross_elasticity=0.3,
                competitive_elasticity=0.5,
                internal_substitution_elasticity=0.2,
                elasticity_confidence_score=0.7,
                confidence_class="bruikbaar",
                method_label=method, regression_r2=r2))

        # SKU-FALL: regressie (dag 4, 3) → heuristiek (dag 2, 1, 0)
        add(skus[0], 4, "regressie", 0.62)
        add(skus[0], 3, "regressie", 0.58)
        add(skus[0], 2, "heuristiek", None)
        add(skus[0], 1, "heuristiek", None)
        add(skus[0], 0, "heuristiek", None)

        # SKU-R2: regressie met sterke R²-daling
        add(skus[1], 1, "regressie", 0.80)
        add(skus[1], 0, "regressie", 0.50)

        # SKU-OK: altijd heuristiek — nooit regressie geweest
        for d in (3, 2, 1, 0):
            add(skus[2], d, "heuristiek", None)

        # SKU-STAB: regressie met stabiele R²
        add(skus[3], 1, "regressie", 0.70)
        add(skus[3], 0, "regressie", 0.68)

        db.commit()
        yield sid, skus
    finally:
        if skus:
            db.query(models.SkuElasticity).filter(
                models.SkuElasticity.sku_id.in_(skus),
            ).delete(synchronize_session=False)
        if sid is not None:
            for model, col in [
                (models.IntelligenceSignal, models.IntelligenceSignal.shop_id),
                (models.CostUsageRecord, models.CostUsageRecord.shop_id),
            ]:
                db.query(model).filter(col == sid).delete(
                    synchronize_session=False)
        if skus:
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(skus),
            ).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == sid).delete(synchronize_session=False)
        db.commit()
        db.close()

def test_elasticity_method_degraded_signal(elast_degradation_seed):
    """3 opeenvolgende heuristiek-runs na eerdere regressie → signaal."""
    from engine.competition_intelligence import warn_elasticity_degradation
    sid, skus = elast_degradation_seed
    db = SessionLocal()
    try:
        n = warn_elasticity_degradation(db, date.today(), shop_id=sid)
        assert n >= 2, f"Verwacht >= 2 signalen (methode + R²), kreeg {n}"
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "elasticity_method_degraded",
            models.IntelligenceSignal.entity_id == skus[0],
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).first()
        assert sig is not None, "Geen methode-terugvalsignaal voor SKU-FALL"
        assert sig.explanation and "heuristi" in sig.explanation.lower()
        ev = sig.evidence or {}
        assert ev.get("consecutive_heuristic_runs") == 3
        assert ev.get("last_regression_run_date")
        assert sig.sources and "sku_elasticity" in sig.sources
    finally:
        db.close()

def test_elasticity_r2_drop_signal(elast_degradation_seed):
    """R²-daling van 0.80 → 0.50 (> drempel 0.15) → signaal met waarden."""
    from engine.competition_intelligence import warn_elasticity_degradation
    sid, skus = elast_degradation_seed
    db = SessionLocal()
    try:
        warn_elasticity_degradation(db, date.today(), shop_id=sid)
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "elasticity_r2_dropped",
            models.IntelligenceSignal.entity_id == skus[1],
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).first()
        assert sig is not None, "Geen R²-dalingssignaal voor SKU-R2"
        assert sig.current_value == pytest.approx(0.50)
        assert sig.previous_value == pytest.approx(0.80)
        ev = sig.evidence or {}
        assert ev.get("r2_drop") == pytest.approx(0.30)
        assert ev.get("r2_drop_threshold") == pytest.approx(0.15)
    finally:
        db.close()

def test_elasticity_r2_drop_detected_across_intermediate_heuristic_runs(client):
    """Regressie (R² 0.80) → heuristiek → regressie (R² 0.50): de daling wordt
    vergeleken met de VORIGE regressie-run, ook met tussenliggende
    heuristiek-runs — en zelfstandig gedetecteerd door de detector."""
    from engine.competition_intelligence import warn_elasticity_degradation

    pfx = f"EDGAP{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    today = date.today()
    sid = None
    sku = f"{pfx}-SKU"
    try:
        shop = models.DimShop(shop_code=pfx, name=f"{pfx}-shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        db.add(models.DimProduct(sku_id=sku, product_name="ED gap",
                                 current_price=10.0, shop_id=sid))
        db.flush()
        for d, m, r2 in [(2, "regressie", 0.80), (1, "heuristiek", None),
                         (0, "regressie", 0.50)]:
            db.add(models.SkuElasticity(
                sku_id=sku, run_date=today - timedelta(days=d),
                own_price_elasticity=-1.0, cross_elasticity=0.2,
                competitive_elasticity=0.4,
                internal_substitution_elasticity=0.1,
                elasticity_confidence_score=0.6,
                confidence_class="bruikbaar",
                method_label=m, regression_r2=r2))
        db.commit()

        n = warn_elasticity_degradation(db, today, shop_id=sid)
        assert n == 1, f"Verwacht precies 1 R²-dalingssignaal, kreeg {n}"
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "elasticity_r2_dropped",
            models.IntelligenceSignal.entity_id == sku,
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).first()
        assert sig is not None
        assert sig.previous_value == pytest.approx(0.80)
        assert sig.current_value == pytest.approx(0.50)
        ev = sig.evidence or {}
        assert ev.get("previous_run_date") == str(today - timedelta(days=2))
        assert ev.get("r2_drop") == pytest.approx(0.30)
    finally:
        db.query(models.SkuElasticity).filter(
            models.SkuElasticity.sku_id == sku).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.shop_id == sid).delete(
                synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(
                synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == sku).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == sid).delete(synchronize_session=False)
        db.commit()
        db.close()

def test_elasticity_degradation_threshold_configurable(monkeypatch, client):
    """Drempels komen uit de model_governance-config: met een hogere
    fallback-drempel (5) triggeren 3 heuristiek-runs géén signaal."""
    from engine import competition_intelligence as ci

    pfx = f"EDCFG{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    today = date.today()
    sid = None
    sku = f"{pfx}-SKU"
    try:
        shop = models.DimShop(shop_code=pfx, name=f"{pfx}-shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        db.add(models.DimProduct(sku_id=sku, product_name="ED cfg",
                                 current_price=10.0, shop_id=sid))
        db.flush()
        for d, m, r2 in [(4, "regressie", 0.6), (3, "regressie", 0.55),
                         (2, "heuristiek", None), (1, "heuristiek", None),
                         (0, "heuristiek", None)]:
            db.add(models.SkuElasticity(
                sku_id=sku, run_date=today - timedelta(days=d),
                own_price_elasticity=-1.0, cross_elasticity=0.2,
                competitive_elasticity=0.4,
                internal_substitution_elasticity=0.1,
                elasticity_confidence_score=0.6,
                confidence_class="bruikbaar",
                method_label=m, regression_r2=r2))
        db.commit()

        monkeypatch.setattr(ci, "_cfg", lambda db: dict(
            ci.DEFAULTS, elasticity_fallback_runs_threshold=5))
        n = ci.warn_elasticity_degradation(db, today, shop_id=sid)
        assert n == 0, "Signaal ondanks hogere geconfigureerde drempel"
    finally:
        db.query(models.SkuElasticity).filter(
            models.SkuElasticity.sku_id == sku).delete(synchronize_session=False)
        db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == sid).delete(
            synchronize_session=False)
        db.query(models.CostUsageRecord).filter(
            models.CostUsageRecord.shop_id == sid).delete(
            synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == sku).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == sid).delete(synchronize_session=False)
        db.commit()
        db.close()

def test_elasticity_degradation_no_signal_for_stable_skus(elast_degradation_seed):
    """Geen signalen voor SKU's zonder eerdere regressie of met stabiele R²."""
    from engine.competition_intelligence import warn_elasticity_degradation
    sid, skus = elast_degradation_seed
    db = SessionLocal()
    try:
        warn_elasticity_degradation(db, date.today(), shop_id=sid)
        n = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.entity_id.in_([skus[2], skus[3]]),
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.signal_type.in_(
                ["elasticity_method_degraded", "elasticity_r2_dropped"]),
        ).count()
        assert n == 0, f"Onterecht {n} signalen voor stabiele SKU's"
    finally:
        db.close()

def test_run_all_includes_elasticity_degradation(run_engines):
    """run_all rapporteert de degradatiestap in het resultaat."""
    assert "elasticity_degradation_signals" in run_engines

def test_elasticity_degradation_idempotent(elast_degradation_seed):
    """Herhaalde aanroep op dezelfde run_date maakt geen extra signalen aan."""
    from engine.competition_intelligence import warn_elasticity_degradation
    sid, skus = elast_degradation_seed
    db = SessionLocal()
    try:
        n = warn_elasticity_degradation(db, date.today(), shop_id=sid)
        assert n == 0, f"Idempotentie geschonden: {n} extra signalen"
        count = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "elasticity_method_degraded",
            models.IntelligenceSignal.entity_id == skus[0],
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).count()
        assert count == 1, f"Verwacht 1 actief signaal, kreeg {count}"
    finally:
        db.close()


# ── Winkelbrede heuristiek-aandeel-spike ─────────────────────────────────────

@pytest.fixture()
def heuristic_share_seed(client):
    """Shop met 10 SKU's: vorige run 20% heuristiek, huidige run 80% —
    een stijging van 60pp, ruim boven de default-drempel van 15pp."""
    pfx = f"HSS{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    today = date.today()
    sid = None
    skus = []
    try:
        shop = models.DimShop(shop_code=pfx, name=f"{pfx}-shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        for i in range(10):
            sku = f"{pfx}-SKU{i}"
            skus.append(sku)
            db.add(models.DimProduct(sku_id=sku, product_name=f"HSS {i}",
                                     current_price=10.0, shop_id=sid))
        db.flush()

        def add(sku, days_ago, method):
            db.add(models.SkuElasticity(
                sku_id=sku, run_date=today - timedelta(days=days_ago),
                own_price_elasticity=-1.0, cross_elasticity=0.2,
                competitive_elasticity=0.4,
                internal_substitution_elasticity=0.1,
                elasticity_confidence_score=0.6,
                confidence_class="bruikbaar",
                method_label=method,
                regression_r2=0.5 if method == "regressie" else None))

        # Vorige run: 2/10 heuristiek (20%)
        for i, sku in enumerate(skus):
            add(sku, 1, "heuristiek" if i < 2 else "regressie")
        # Huidige run: 8/10 heuristiek (80%)
        for i, sku in enumerate(skus):
            add(sku, 0, "heuristiek" if i < 8 else "regressie")
        db.commit()
        yield sid, skus
    finally:
        if skus:
            db.query(models.SkuElasticity).filter(
                models.SkuElasticity.sku_id.in_(skus),
            ).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.shop_id == sid).delete(
                synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(
                synchronize_session=False)
        if skus:
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(skus),
            ).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == sid).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_heuristic_share_spike_signal(heuristic_share_seed):
    """Stijging 20% → 80% heuristiek → precies één shop-niveau signaal."""
    from engine.competition_intelligence import warn_heuristic_share_spike
    sid, _skus = heuristic_share_seed
    db = SessionLocal()
    try:
        n = warn_heuristic_share_spike(db, date.today(), shop_id=sid)
        assert n == 1, f"Verwacht 1 signaal, kreeg {n}"
        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "elasticity_heuristic_share_spiked",
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).one()
        assert sig.entity_type == "shop"
        assert sig.entity_id == "elasticity-method-mix"
        assert sig.current_value == pytest.approx(80.0)
        assert sig.previous_value == pytest.approx(20.0)
        ev = sig.evidence or {}
        assert ev.get("increase_pp") == pytest.approx(60.0)
        assert ev.get("spike_threshold_pp") == pytest.approx(15.0)
        assert ev.get("current_sku_count") == 10
        assert sig.sources and "sku_elasticity" in sig.sources
        assert sig.explanation and "heuristi" in sig.explanation.lower()
    finally:
        db.close()


def test_heuristic_share_spike_idempotent(heuristic_share_seed):
    """Rerun op dezelfde run_date maakt geen tweede signaal aan."""
    from engine.competition_intelligence import warn_heuristic_share_spike
    sid, _skus = heuristic_share_seed
    db = SessionLocal()
    try:
        assert warn_heuristic_share_spike(db, date.today(), shop_id=sid) == 1
        assert warn_heuristic_share_spike(db, date.today(), shop_id=sid) == 0
        count = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.signal_type == "elasticity_heuristic_share_spiked",
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).count()
        assert count == 1
    finally:
        db.close()


def test_heuristic_share_spike_threshold_configurable(monkeypatch, heuristic_share_seed):
    """Met een geconfigureerde drempel van 70pp triggert een stijging van
    60pp géén signaal."""
    from engine import competition_intelligence as ci
    sid, _skus = heuristic_share_seed
    db = SessionLocal()
    try:
        monkeypatch.setattr(ci, "_cfg", lambda db: dict(
            ci.DEFAULTS, heuristic_share_spike_pp=70.0))
        n = ci.warn_heuristic_share_spike(db, date.today(), shop_id=sid)
        assert n == 0, "Signaal ondanks hogere geconfigureerde drempel"
    finally:
        db.close()


def test_heuristic_share_no_signal_without_previous_run(client):
    """Eerste run ooit (geen vorige run om mee te vergelijken) → geen signaal."""
    from engine.competition_intelligence import warn_heuristic_share_spike
    pfx = f"HSF{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    today = date.today()
    sid = None
    skus = []
    try:
        shop = models.DimShop(shop_code=pfx, name=f"{pfx}-shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        for i in range(12):
            sku = f"{pfx}-SKU{i}"
            skus.append(sku)
            db.add(models.DimProduct(sku_id=sku, product_name=f"HSF {i}",
                                     current_price=10.0, shop_id=sid))
        db.flush()
        for sku in skus:
            db.add(models.SkuElasticity(
                sku_id=sku, run_date=today,
                own_price_elasticity=-1.0, cross_elasticity=0.2,
                competitive_elasticity=0.4,
                internal_substitution_elasticity=0.1,
                elasticity_confidence_score=0.6,
                confidence_class="bruikbaar",
                method_label="heuristiek", regression_r2=None))
        db.commit()

        n = warn_heuristic_share_spike(db, today, shop_id=sid)
        assert n == 0, "Signaal zonder vorige run om mee te vergelijken"
    finally:
        db.query(models.SkuElasticity).filter(
            models.SkuElasticity.sku_id.in_(skus)).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.shop_id == sid).delete(
                synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(
                synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == sid).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_heuristic_share_min_skus_guard(monkeypatch, client):
    """Onder heuristic_share_min_skus SKU's in de huidige run → geen signaal."""
    from engine import competition_intelligence as ci
    pfx = f"HSM{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    today = date.today()
    sid = None
    skus = []
    try:
        shop = models.DimShop(shop_code=pfx, name=f"{pfx}-shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        for i in range(3):
            sku = f"{pfx}-SKU{i}"
            skus.append(sku)
            db.add(models.DimProduct(sku_id=sku, product_name=f"HSM {i}",
                                     current_price=10.0, shop_id=sid))
        db.flush()
        for days_ago, method_by_i in [(1, {0: "regressie", 1: "regressie", 2: "regressie"}),
                                      (0, {0: "heuristiek", 1: "heuristiek", 2: "heuristiek"})]:
            for i, sku in enumerate(skus):
                db.add(models.SkuElasticity(
                    sku_id=sku, run_date=today - timedelta(days=days_ago),
                    own_price_elasticity=-1.0, cross_elasticity=0.2,
                    competitive_elasticity=0.4,
                    internal_substitution_elasticity=0.1,
                    elasticity_confidence_score=0.6,
                    confidence_class="bruikbaar",
                    method_label=method_by_i[i],
                    regression_r2=0.5 if method_by_i[i] == "regressie" else None))
        db.commit()

        n = ci.warn_heuristic_share_spike(db, today, shop_id=sid)
        assert n == 0, "Signaal ondanks te weinig SKU's voor betekenisvol aandeel"

        # Met verlaagde min_skus triggert dezelfde data wél
        monkeypatch.setattr(ci, "_cfg", lambda db: dict(
            ci.DEFAULTS, heuristic_share_min_skus=3))
        n = ci.warn_heuristic_share_spike(db, today, shop_id=sid)
        assert n == 1
    finally:
        db.query(models.SkuElasticity).filter(
            models.SkuElasticity.sku_id.in_(skus)).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.shop_id == sid).delete(
                synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(
                synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == sid).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_run_all_includes_heuristic_share_spike(run_engines):
    """run_all rapporteert de winkelbrede spike-stap in het resultaat."""
    assert "heuristic_share_spike_signals" in run_engines
