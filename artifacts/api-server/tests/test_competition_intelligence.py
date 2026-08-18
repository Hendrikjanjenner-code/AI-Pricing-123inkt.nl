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

# Constanten voor de warn_suspicious_matches-testfixtures
WM_PFX = f"WMTEST{uuid.uuid4().hex[:6]}"
WM_SKU = f"{WM_PFX}-SKU"
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
    """Synthetische data: 2 SKU's, 2 concurrenten, 30 dagen historie
    met een duidelijke prijswijziging vandaag en een promo-dip."""
    db = SessionLocal()
    today = date.today()
    try:
        db.add_all([
            models.DimProduct(sku_id=SKU_A, product_name="CI Test Product A",
                              category=f"{PFX}-cat", current_price=20.0,
                              cost_price=12.0, stock_quantity=50),
            models.DimProduct(sku_id=SKU_B, product_name="CI Test Product B",
                              category=f"{PFX}-cat", current_price=10.0,
                              cost_price=6.0, stock_quantity=10),
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
                date=d, sku_id=SKU_A, competitor_name=COMP_1, price=p1))
            # COMP_2 op SKU_A: promo-dip dag 10..6 (-20%), daarna herstel
            p2 = 16.0 if 6 <= i <= 10 else 20.0
            db.add(models.FactCompetitorPriceDaily(
                date=d, sku_id=SKU_A, competitor_name=COMP_2, price=p2))
            # COMP_1 op SKU_B (wordt straks REJECTED)
            db.add(models.FactCompetitorPriceDaily(
                date=d, sku_id=SKU_B, competitor_name=COMP_1, price=9.5))
            # Eigen prijs + verkoop met variatie voor elasticiteit
            own_p = 20.0 + (0.5 if i % 7 < 3 else -0.5) + (i % 5) * 0.1
            units = max(1, int(60 - 2 * own_p + (0.8 * p1) + (i % 3)))
            db.add(models.FactPriceDaily(date=d, sku_id=SKU_A, price=own_p))
            db.add(models.FactSalesDaily(date=d, sku_id=SKU_A, units_sold=units,
                                         revenue=units * own_p))
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
            competitor_name=COMP_1, run_date=today,
            strategy_type="PRICE_FOLLOWER", strategy_label_nl="Prijsvolger",
            confidence=0.8)
        db.add(strat)
        db.commit()
        yield
    finally:
        # Opruimen (FK: eerst signals/kostenrijen niet nodig — geen aparte shop)
        for model, col in [
            (models.IntelligenceSignal, models.IntelligenceSignal.entity_id),
            (models.CompetitorPriceEvent, models.CompetitorPriceEvent.sku_id),
            (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.sku_id),
            (models.FactPriceDaily, models.FactPriceDaily.sku_id),
            (models.FactSalesDaily, models.FactSalesDaily.sku_id),
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
        db.commit()
        db.close()


@pytest.fixture(scope="module")
def run_engines(client, admin_headers, seed):
    resp = client.post("/api/competition/intelligence/run", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_run_summary(run_engines):
    assert run_engines["status"] == "voltooid"
    assert run_engines["coverage_rows"] >= 2       # totaal + categorie per concurrent
    assert run_engines["price_events"] >= 1
    assert run_engines["promo_events"] >= 2        # PROMO_START + PROMO_END
    assert run_engines["elasticity_skus"] >= 1


def test_price_change_event_and_signal(client, admin_headers, run_engines):
    resp = client.get(f"/api/competition/events?event_type=PRICE_CHANGE&sku_id={SKU_A}",
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


def test_promo_events_detected(client, admin_headers, run_engines):
    resp = client.get(f"/api/competition/events?sku_id={SKU_A}&event_type=PROMO_START",
                      headers=admin_headers)
    starts = [e for e in resp.json()["items"] if e["competitor_name"] == COMP_2]
    assert starts and starts[0]["promo_depth_pct"] >= 15
    resp = client.get(f"/api/competition/events?sku_id={SKU_A}&event_type=PROMO_END",
                      headers=admin_headers)
    ends = [e for e in resp.json()["items"] if e["competitor_name"] == COMP_2]
    assert ends and ends[0]["promo_duration_days"] >= 3


def test_coverage_excludes_rejected(client, admin_headers, run_engines):
    resp = client.get("/api/competition/coverage", headers=admin_headers)
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


def test_availability_and_trend_api(client, admin_headers, run_engines):
    resp = client.get(f"/api/competition/availability?competitor={COMP_1}",
                      headers=admin_headers)
    assert resp.status_code == 200
    series = resp.json()["competitors"].get(COMP_1)
    assert series and series[-1]["in_stock_rate"] == 0.0  # vandaag OOS
    resp = client.get("/api/competition/trends/price-index?days=30",
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


def test_match_quality_kpis(client, admin_headers, run_engines):
    resp = client.get("/api/competition/match-quality", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["total"] >= 3
    assert body["totals"]["rejected"] >= 1
    assert "Exact" in body["by_match_type"]


def test_simulation(client, admin_headers, run_engines):
    resp = client.post("/api/competition/simulate", headers=admin_headers,
                       json={"sku_id": SKU_A, "change_pct": -0.05})
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
                              "assume_no_follow": [COMP_1, COMP_2]})
    b2 = resp2.json()
    assert all(c["follow_probability"] == 0.0 for c in b2["competitors"])
    assert b2["scenario_expected"]["units"] >= body["scenario_expected"]["units"]


def test_simulation_validation(client, admin_headers, seed):
    resp = client.post("/api/competition/simulate", headers=admin_headers,
                       json={"sku_id": SKU_A, "change_pct": 0.9})
    assert resp.status_code == 400


def test_rejection_survives_match_rebuild(client, admin_headers, run_engines):
    """build_ai_matches herbouwt de matches uit de feed, maar mag een
    analistenbeoordeling (REJECTED/APPROVED) niet wissen."""
    import feed_ingest
    db = SessionLocal()
    try:
        feed_ingest.build_ai_matches(db)
        db.commit()
        m = db.query(models.AiMatchResult).filter(
            models.AiMatchResult.own_sku_id == SKU_B,
            models.AiMatchResult.competitor_name == COMP_1,
        ).order_by(models.AiMatchResult.run_date.desc()).first()
        assert m is not None
        assert m.status == "REJECTED"
    finally:
        db.close()


def test_signals_idempotent_on_rerun(client, admin_headers, run_engines):
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
        resp = client.post("/api/competition/intelligence/run", headers=admin_headers)
        assert resp.status_code == 200
        db.expire_all()
        assert count() == before
    finally:
        db.close()


def test_price_index_uses_historical_own_price(client, admin_headers, run_engines):
    """De trend gebruikt fact_price_daily van die dag; een latere wijziging
    van current_price mag de historie niet herschrijven."""
    db = SessionLocal()
    try:
        prod = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_A).first()
        original = float(prod.current_price)
        prod.current_price = original * 10  # extreme wijziging
        db.commit()
        resp = client.get("/api/competition/trends/price-index?days=30",
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
                competitor_name=COMP_1, price=25.0 if i else 20.0,
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


def test_viewer_cannot_run_engines(client, seed):
    resp = client.post("/api/auth/login",
                       json={"username": "dev_viewer", "password": "viewer123"})
    if resp.status_code != 200:
        pytest.skip("geen viewer-account beschikbaar")
    h = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert client.post("/api/competition/intelligence/run", headers=h).status_code == 403

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

def test_warn_suspicious_matches_idempotent(suspicious_seed):
    """Tweede aanroep op dezelfde run_date mag geen extra signaal aanmaken.
    Vereist dat test_warn_suspicious_matches_publishes_signal al eerder is gedraaid."""
    from engine.competition_intelligence import warn_suspicious_matches
    sid, _skus = suspicious_seed
    db = SessionLocal()
    try:
        rd = date.today()
        # Eerste aanroep is al gedaan in test_warn_suspicious_matches_publishes_signal;
        # een tweede aanroep mag het signaal niet verdubbelen.
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
        result = run_all(db2, date.today())
        assert "suspicious_match_signals" in result
        assert isinstance(result["suspicious_match_signals"], int)
    finally:
        db2.close()
