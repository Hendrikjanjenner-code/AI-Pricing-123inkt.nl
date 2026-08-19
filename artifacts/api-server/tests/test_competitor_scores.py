"""
Tests voor de concurrentscore-laag (taak #247): company size (multi-signaal),
geographic scale (webshop vs operationeel), fulfilment-classificatie,
financial health (unknown vs voldoende data), business strength (financiële
demping), procurement power, future threat, feature-dependency-guard,
ranking-integratie (ondersteunend, nooit dominant) en het E2E-scenario dat
Business Profile gelijk blijft terwijl Competition Relevance per categorie
verschilt (Office Food vs Markers).
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
from engine import competitor_scores as engine_cs

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"CSTEST{uuid.uuid4().hex[:6]}"
COMP_BIG = f"{PFX}-groot.nl"          # veel signalen, groei-historie
COMP_DROP = f"{PFX}-dropship.nl"      # dropship, weinig financiële data
COMP_EMPTY = f"{PFX}-leeg.nl"         # alleen legacy-profiel, alles unknown
CAT_FOOD = f"{PFX}-Office Food"
CAT_MARKERS = f"{PFX}-Markers"


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
    """Geïsoleerde test-shop met drie concurrenten en volledige profieldata."""
    db = SessionLocal()
    shop_id = None
    today = date.today()
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop",
                              active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id

        ev = models.CompetitionEvidence(
            shop_id=shop_id, competitor_name=COMP_BIG,
            source_type="jaarrekening", title="Jaarrekening",
            reliability="high", confidence=0.9)
        db.add(ev)
        db.flush()

        # COMP_BIG: groot bedrijf, eigen voorraad, groei-historie
        db.add_all([
            models.CompetitorBusinessProfile(
                shop_id=shop_id, competitor_name=COMP_BIG,
                employee_range_min=300, employee_range_max=500,
                revenue_range_min=60_000_000, revenue_range_max=80_000_000,
                ownership_type="private_equity",
                field_meta={}),
            models.CompetitorFulfilmentProfile(
                shop_id=shop_id, competitor_name=COMP_BIG,
                inventory_model="eigen_voorraad", warehouse_count=6,
                own_stock_share_pct=90.0, dropship_share_pct=10.0,
                next_day_delivery=True, field_meta={}),
            # Geografie: operationeel in 4 landen, verzendt naar 9
            *[models.CompetitorGeographicPresence(
                shop_id=shop_id, competitor_name=COMP_BIG,
                country_code=cc, presence_type="operationeel",
                valid_from=today - timedelta(days=400))
              for cc in ("NL", "BE", "DE", "FR")],
            *[models.CompetitorGeographicPresence(
                shop_id=shop_id, competitor_name=COMP_BIG,
                country_code=cc, presence_type="webshop",
                valid_from=today - timedelta(days=400))
              for cc in ("NL", "BE", "DE", "FR", "ES", "IT", "PL", "AT", "DK")],
            # Financials: 2 boekjaren met sterke omzetgroei + winst
            models.CompetitorFinancialObservation(
                shop_id=shop_id, competitor_name=COMP_BIG,
                fiscal_year=2024, metric="revenue",
                value_min=50_000_000, value_max=50_000_000,
                information_layer="feit", confidence=0.9, evidence_id=ev.id),
            models.CompetitorFinancialObservation(
                shop_id=shop_id, competitor_name=COMP_BIG,
                fiscal_year=2025, metric="revenue",
                value_min=70_000_000, value_max=70_000_000,
                information_layer="feit", confidence=0.9, evidence_id=ev.id),
            models.CompetitorFinancialObservation(
                shop_id=shop_id, competitor_name=COMP_BIG,
                fiscal_year=2025, metric="profit",
                value_min=4_000_000, value_max=4_000_000,
                information_layer="feit", confidence=0.9, evidence_id=ev.id),
            # Corporate: moederbedrijf + recente dochter (overname)
            models.CompetitorCorporateRelation(
                shop_id=shop_id, competitor_name=COMP_BIG,
                relation_type="parent", related_entity="Holding BV",
                confidence=0.8, valid_from=today - timedelta(days=800)),
            models.CompetitorCorporateRelation(
                shop_id=shop_id, competitor_name=COMP_BIG,
                relation_type="subsidiary", related_entity="Overname BV",
                confidence=0.7, valid_from=today - timedelta(days=30)),
            # Rollen: private label
            models.CompetitorMarketRole(
                shop_id=shop_id, competitor_name=COMP_BIG,
                role="private_label", confidence=0.8,
                valid_from=today - timedelta(days=60)),
            # Evolution-historie: landenuitbreiding + nieuw magazijn
            models.CompetitorEvolutionEvent(
                shop_id=shop_id, competitor_name=COMP_BIG,
                section="geography", field_name="country", event_type="created",
                new_value="PL", occurred_at=datetime.utcnow() - timedelta(days=20)),
            models.CompetitorEvolutionEvent(
                shop_id=shop_id, competitor_name=COMP_BIG,
                section="fulfilment", field_name="warehouse_count",
                event_type="changed", old_value=5, new_value=6,
                occurred_at=datetime.utcnow() - timedelta(days=15)),
            models.CompetitorProfile(
                shop_id=shop_id, competitor_name=COMP_BIG,
                assortment_size=1200, category_breadth=8,
                avg_delivery_days=1.0, in_stock_rate=0.95,
                functional_overlap_score=0.8, run_date=today),
        ])

        # COMP_DROP: dropshipper, model bekend maar verdeling onbekend,
        # geen financiële data
        db.add_all([
            models.CompetitorFulfilmentProfile(
                shop_id=shop_id, competitor_name=COMP_DROP,
                inventory_model="dropship", field_meta={
                    "inventory_model": {"status": "known",
                                        "confidence": 0.8,
                                        "source": "site-analyse"}}),
            models.CompetitorGeographicPresence(
                shop_id=shop_id, competitor_name=COMP_DROP,
                country_code="NL", presence_type="webshop"),
            models.CompetitorProfile(
                shop_id=shop_id, competitor_name=COMP_DROP,
                assortment_size=100, category_breadth=2,
                functional_overlap_score=0.4, run_date=today),
        ])

        # COMP_EMPTY: alleen legacy-profiel zonder bruikbare velden
        db.add(models.CompetitorProfile(
            shop_id=shop_id, competitor_name=COMP_EMPTY, run_date=today))

        # Categorie-relevantie: zelfde concurrent, sterk verschillende
        # relevantie per categorie (Office Food vs Markers)
        db.add_all([
            models.CategoryCompetitorRelevance(
                shop_id=shop_id, competitor_name=COMP_BIG,
                category=CAT_FOOD, relevance_score=90.0, coverage_index=85.0,
                pricing_relevance_score=80.0),
            models.CategoryCompetitorRelevance(
                shop_id=shop_id, competitor_name=COMP_BIG,
                category=CAT_MARKERS, relevance_score=10.0, coverage_index=5.0,
                pricing_relevance_score=15.0),
            models.CategoryCompetitorRelevance(
                shop_id=shop_id, competitor_name=COMP_DROP,
                category=CAT_MARKERS, relevance_score=70.0, coverage_index=60.0,
                pricing_relevance_score=65.0),
        ])
        db.commit()
        yield {"shop_id": shop_id}
    finally:
        for model in [models.CompetitorScoreResult,
                      models.CompetitorRanking,
                      models.CategoryCompetitorRelevance,
                      models.CompetitorBusinessProfile,
                      models.CompetitorFulfilmentProfile,
                      models.CompetitorFinancialObservation,
                      models.CompetitorMarketRole,
                      models.CompetitorGeographicPresence,
                      models.CompetitorCorporateRelation,
                      models.CompetitorEvolutionEvent,
                      models.CompetitionEvidence,
                      models.CompetitorProfile,
                      models.IntelligenceSignal,
                      models.CompetitionSetting,
                      models.CostUsageRecord]:
            if shop_id is not None and hasattr(model, "shop_id"):
                db.query(model).filter(model.shop_id == shop_id).delete(
                    synchronize_session=False)
        if shop_id is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == shop_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.fixture(scope="module")
def run(seed):
    """Scoped engine-run voor de test-shop; retourneert de score-rijen."""
    db = SessionLocal()
    try:
        result = engine_cs.run_competitor_scores(db, shop_id=seed["shop_id"])
        assert result["rows_written"] >= 3
        rows = engine_cs.latest_scores_by_competitor(db, seed["shop_id"])
        # Detacheer alles zodat latere sessies niet nodig zijn
        db.expunge_all()
        return rows
    finally:
        db.close()


# ── Classificaties ───────────────────────────────────────────────────────────

def test_company_size_multi_signal(run):
    r = run[COMP_BIG]
    assert r.company_size_class in ("groot", "enterprise")
    cs = r.details["company_size"]
    assert len(cs["signals"]) >= 3          # omzet, medewerkers, dekking, magazijnen
    assert cs["confidence"] > 0.5
    assert "mediaan" in cs["explanation"]


def test_company_size_single_outlier_cannot_dominate():
    """Eén afwijkend datapunt (enorme omzet) mag de klasse niet alleen
    bepalen als andere signalen dat tegenspreken."""
    from services.competition_settings import DEFAULTS

    class _B:  # klein bedrijf volgens medewerkers, absurd hoge omzetclaim
        employee_range_min = 5
        employee_range_max = 8
        revenue_range_min = 500_000_000
        revenue_range_max = 500_000_000

    class _F:
        warehouse_count = 1
        field_meta = {}

    ledger = engine_cs._FeatureLedger()
    out = engine_cs.classify_company_size(
        business=_B(), financials=[], geo_rows=[], fulfilment=_F(),
        cfg=DEFAULTS["strength_config"], ledger=ledger)
    # Mediaan van [omzet=enterprise(4), medewerkers=micro(0), magazijn=klein(1)]
    # = klein — de omzet-uitschieter wint niet.
    assert out["class"] in ("micro", "klein")
    assert out["class"] != "enterprise"
    # En de spreiding drukt de confidence
    assert out["confidence"] < 0.6


def test_company_size_unknown_without_signals(run):
    r = run[COMP_EMPTY]
    assert r.company_size_class is None
    assert "Unknown" in r.details["company_size"]["explanation"]


def test_geographic_scale_operational_vs_webshop(run):
    r = run[COMP_BIG]
    g = r.details["geographic_scale"]
    # Operationeel actief in 4 landen (regionaal), verzendt naar 9
    assert r.geographic_scale_class == "regionaal"
    assert g["basis"] == "operationeel"
    assert len(g["operational_countries"]) == 4
    assert len(g["ships_to_countries"]) == 9

    d = run[COMP_DROP].details["geographic_scale"]
    # Alleen verzendlanden bekend: basis expliciet webshop + lagere confidence
    assert d["basis"] == "webshop_verzendlanden"
    assert d["confidence"] < g["confidence"]


def test_fulfilment_classification(run):
    big = run[COMP_BIG]
    assert big.fulfilment_model_class == "eigen_voorraad"
    assert big.details["fulfilment_model"]["distribution_known"] is True

    drop = run[COMP_DROP]
    f = drop.details["fulfilment_model"]
    assert drop.fulfilment_model_class == "dropship"
    # Geen betrouwbare percentages → geen fictieve percentages
    assert f["distribution_known"] is False
    assert f["distribution"] is None
    assert f["distribution_label"] == "Bevestigd / Verdeling onbekend"

    assert run[COMP_EMPTY].fulfilment_model_class is None


def test_fulfilment_hybrid_classification():
    class _F:
        inventory_model = "hybride"
        marketplace_role = None
        dropship_share_pct = 45.0
        own_stock_share_pct = 55.0
        field_meta = {}

    out = engine_cs.classify_fulfilment_model(
        fulfilment=_F(), ledger=engine_cs._FeatureLedger())
    assert out["class"] == "hybride"
    assert out["distribution_known"] is True


# ── Scores & unknown-beleid ──────────────────────────────────────────────────

def test_financial_health_sufficient_data(run):
    r = run[COMP_BIG]
    f = r.details["financial_health"]
    assert r.financial_health_status == "gezond"
    assert r.financial_health_score >= 65
    assert r.financial_data_confidence > 0.6   # jaarrekening-bron, recent
    factors = {x["factor"] for x in f["factors"]}
    assert "winstgevendheid" in factors and "omzettrend" in factors
    for x in f["factors"]:
        assert x.get("source")


def test_financial_unknown_never_zero(run):
    r = run[COMP_DROP]
    assert r.financial_health_status == "unknown"
    assert r.financial_health_score is None    # NULL, niet 0
    assert r.financial_data_confidence is None
    assert r.data_completeness_pct < 100.0


def test_operational_strength_and_unknown(run):
    big = run[COMP_BIG]
    assert big.operational_strength_score is not None
    assert big.operational_strength_score > 70
    ops = big.details["operational_strength"]
    assert set(ops["weights_used"]) >= {"fulfilment_control", "delivery"}

    empty = run[COMP_EMPTY]
    assert empty.operational_strength_score is None


def test_business_strength_with_financial_damping(run):
    r = run[COMP_BIG]
    assert r.business_strength_score is not None and r.business_strength_score > 60
    bs = r.details["business_strength"]
    fin = [f for f in bs["factors"] if f["factor"] == "financial_health"]
    assert fin and fin[0]["weight"] < fin[0]["weight_before_damping"] or \
        fin[0]["weight"] == pytest.approx(
            fin[0]["weight_before_damping"] * fin[0]["confidence"], abs=0.01)


def test_procurement_power(run):
    r = run[COMP_BIG]
    assert r.procurement_power_score is not None and r.procurement_power_score > 60
    factors = {f["factor"] for f in r.details["procurement_power"]["factors"]}
    assert {"company_size", "corporate_backing", "private_label"} <= factors
    # Weinig data → unknown, geen 0
    assert run[COMP_EMPTY].procurement_power_score is None


def test_future_threat_signals(run):
    r = run[COMP_BIG]
    assert r.future_threat_score is not None and r.future_threat_score > 40
    t = r.details["future_threat"]
    comps = set(t["components"])
    assert "growth" in comps          # 40% omzetgroei
    assert "expansion" in comps       # geografie-event
    assert "acquisitions" in comps    # recente dochter + relations
    assert "capability_investments" in comps  # magazijn + private label
    assert t["signals"], "signalen moeten altijd zichtbaar zijn"

    # Geen historie → Unknown
    assert run[COMP_EMPTY].future_threat_score is None


def test_feature_dependency_guard():
    ledger = engine_cs._FeatureLedger()
    with pytest.raises(engine_cs.FeatureDependencyError):
        ledger.use("countries_operational", "procurement_power")


def test_feature_usage_documented(run):
    usage = run[COMP_BIG].details["feature_usage"]
    for feature, consumers in usage.items():
        allowed = engine_cs.FEATURE_DEPENDENCIES[feature]
        assert set(consumers) <= allowed


# ── API ──────────────────────────────────────────────────────────────────────

def test_api_list_and_detail(client, admin_headers, seed, run):
    sid = seed["shop_id"]
    resp = client.get(f"/api/competition/competitor-scores?shop_id={sid}",
                      headers=admin_headers)
    assert resp.status_code == 200
    names = {s["competitor_name"] for s in resp.json()["scores"]}
    assert {COMP_BIG, COMP_DROP, COMP_EMPTY} <= names

    resp = client.get(
        f"/api/competition/competitor-scores/{COMP_BIG}?shop_id={sid}",
        headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["details"]["business_strength"]["factors"]

    # Shop-scoping: andere (default) shop kent deze concurrent niet
    resp = client.get(
        f"/api/competition/competitor-scores/{COMP_BIG}",
        headers=admin_headers)
    assert resp.status_code == 404


def test_api_score_rankings(client, admin_headers, seed, run):
    sid = seed["shop_id"]
    for dim in ("procurement_power", "future_threat"):
        resp = client.get(
            f"/api/competition/competitor-scores/rankings?dimension={dim}&shop_id={sid}",
            headers=admin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ranked = [r["competitor_name"] for r in body["rankings"]]
        assert COMP_BIG in ranked
        # Unknown-concurrenten staan apart, niet impliciet als 0 onderaan
        unknown_names = {u["competitor_name"] for u in body["unknown"]}
        assert COMP_EMPTY in unknown_names

    resp = client.get(
        f"/api/competition/competitor-scores/rankings?dimension=bestaat_niet&shop_id={sid}",
        headers=admin_headers)
    assert resp.status_code == 422


# ── Ranking-integratie & E2E-scenario ────────────────────────────────────────

@pytest.fixture(scope="module")
def rankings(seed, run):
    from engine.competition_rankings import run_competitor_rankings
    db = SessionLocal()
    try:
        run_competitor_rankings(db, shop_id=seed["shop_id"])
        rows = db.query(models.CompetitorRanking).filter(
            models.CompetitorRanking.shop_id == seed["shop_id"]).all()
        db.expunge_all()
        return rows
    finally:
        db.close()


def test_business_strength_supports_but_never_dominates(rankings, run):
    from engine.competition_rankings import W_BUSINESS_STRENGTH_SUPPORT
    assert W_BUSINESS_STRENGTH_SUPPORT < 0.30  # onder elk primair gewicht
    overall = {r.competitor_name: r for r in rankings if r.scope == "overall"}
    big = overall[COMP_BIG]
    sup = big.evidence["business_strength_support"]
    base = sup["base_combined"]
    bs_norm = sup["business_strength_score"] / 100.0
    expected = round((1 - W_BUSINESS_STRENGTH_SUPPORT) * base
                     + W_BUSINESS_STRENGTH_SUPPORT * bs_norm, 4)
    assert big.combined_score == pytest.approx(expected, abs=0.001)
    # Zonder business strength-score verandert er niets
    empty = overall[COMP_EMPTY]
    assert "business_strength_support" not in (empty.evidence or {})


def test_e2e_same_profile_different_category_relevance(rankings, run):
    """Office Food vs Markers: zelfde Business Profile / Business Strength,
    maar sterk verschillende Competition Relevance per categorie."""
    food = [r for r in rankings
            if r.scope == CAT_FOOD and r.competitor_name == COMP_BIG][0]
    markers = [r for r in rankings
               if r.scope == CAT_MARKERS and r.competitor_name == COMP_BIG][0]
    # Business Strength (profielniveau) is identiek in beide scopes...
    assert run[COMP_BIG].business_strength_score > 60
    # ...maar de categorie-relevantie verschilt sterk
    assert food.competition_relevance_score > markers.competition_relevance_score + 0.2
    # En in de Markers-categorie wint de dropshipper op relevantie
    markers_drop = [r for r in rankings
                    if r.scope == CAT_MARKERS and r.competitor_name == COMP_DROP][0]
    assert markers_drop.competition_relevance_score > markers.competition_relevance_score


def test_settings_strength_config_validation(client, admin_headers, seed):
    sid = seed["shop_id"]
    # Ongeldige gewichten (som ≠ 100) worden geweigerd
    resp = client.put(f"/api/competition/settings?shop_id={sid}",
                      headers=admin_headers, json={
                          "strength_config": {"business_weights": {
                              "company_size": 90, "geographic_scale": 90,
                              "assortment_breadth": 10, "financial_health": 10}}})
    assert resp.status_code == 422
    # Geldige aanpassing wordt gemerged met defaults
    resp = client.put(f"/api/competition/settings?shop_id={sid}",
                      headers=admin_headers, json={
                          "strength_config": {
                              "size_employee_bounds": [5, 25, 100, 500]}})
    assert resp.status_code == 200, resp.text
    sc = resp.json()["settings"]["strength_config"]
    assert sc["size_employee_bounds"] == [5, 25, 100, 500]
    assert sc["business_weights"]["company_size"] == 30  # default behouden
