"""
Tests voor de concurrentprofiel-UI-API-uitbreidingen (taak #248):
volledige-profiel include-params, vergelijking (2–5), rankingfilters met
correcte totalen, Concurrent Landscape en validatie-RBAC.
"""
import os
import sys
import uuid
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"cpui{uuid.uuid4().hex[:6]}"
COMP_A = f"{PFX}-alfa.nl"
COMP_B = f"{PFX}-beta.nl"
COMP_C = f"{PFX}-gamma.nl"
COMP_OTHER = f"{PFX}-andershop.nl"
RUN = date.today()


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
    """Eigen test-shop met drie concurrenten, profielen, scores en rankings,
    plus een tweede shop voor scoping."""
    db = SessionLocal()
    shop_id = shop_b = None
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop")
        shop2 = models.DimShop(shop_code=f"{PFX}-shop-b", name=f"{PFX} Shop B")
        db.add_all([shop, shop2])
        db.flush()
        shop_id, shop_b = shop.id, shop2.id

        for n in (COMP_A, COMP_B, COMP_C):
            db.add(models.CompetitorProfile(
                competitor_name=n, shop_id=shop_id, run_date=RUN,
                assortment_size=100, price_segment="midden"))
        db.add(models.CompetitorProfile(
            competitor_name=COMP_OTHER, shop_id=shop_b, run_date=RUN))

        # Businessprofielen: A groot/B2C/NL, B klein/B2B
        db.add(models.CompetitorBusinessProfile(
            shop_id=shop_id, competitor_name=COMP_A, size_class="groot",
            customer_model="B2C", geographic_scale="europees",
            employee_range_min=500, employee_range_max=1000,
            field_meta={"size_class": {"information_layer": "feit",
                                       "source": "jaarrekening",
                                       "confidence": 0.9}}))
        db.add(models.CompetitorBusinessProfile(
            shop_id=shop_id, competitor_name=COMP_B, size_class="klein",
            customer_model="B2B", geographic_scale="nationaal"))

        db.add(models.CompetitorFulfilmentProfile(
            shop_id=shop_id, competitor_name=COMP_A, inventory_model="dropship"))
        db.add(models.CompetitorMarketRole(
            shop_id=shop_id, competitor_name=COMP_A, role="prijsagressor",
            valid_from=RUN))
        db.add(models.CompetitorGeographicPresence(
            shop_id=shop_id, competitor_name=COMP_A, country_code="DE",
            presence_type="webshop", valid_from=RUN))
        db.add(models.CompetitorCorporateRelation(
            shop_id=shop_id, competitor_name=COMP_A,
            relation_type="ultimate_parent", related_entity=f"{PFX} Holding BV",
            valid_from=RUN))
        db.add(models.CompetitorEvolutionEvent(
            shop_id=shop_id, competitor_name=COMP_A, section="business",
            field_name="size_class", event_type="value_changed",
            old_value="midden", new_value="groot",
            change_source="test", occurred_at=datetime.utcnow()))

        # Scores: A sterk & compleet, B zwakker; C bewust zonder scores
        db.add(models.CompetitorScoreResult(
            shop_id=shop_id, competitor_name=COMP_A, run_date=RUN,
            company_size_class="groot", geographic_scale_class="europees",
            fulfilment_model_class="dropship",
            business_strength_score=80.0, operational_strength_score=70.0,
            procurement_power_score=75.0, financial_health_score=85.0,
            financial_health_status="gezond", financial_data_confidence=0.9,
            future_threat_score=65.0, data_completeness_pct=90.0,
            model_version="test", details={"business_strength": {
                "score": 80.0, "factors": [{"factor": "omvang",
                                            "score": 80, "weight": 0.5}]}}))
        db.add(models.CompetitorScoreResult(
            shop_id=shop_id, competitor_name=COMP_B, run_date=RUN,
            company_size_class="klein",
            business_strength_score=30.0, procurement_power_score=20.0,
            financial_health_status="zwak",
            data_completeness_pct=40.0, model_version="test"))

        # Rankings (overall) voor A en B; C ontbreekt bewust
        for i, (n, rel) in enumerate([(COMP_A, 0.9), (COMP_B, 0.4)], start=1):
            db.add(models.CompetitorRanking(
                shop_id=shop_id, competitor_name=n, run_date=RUN,
                scope="overall", rank=i,
                competition_relevance_score=rel,
                price_relevance_score=rel - 0.1, influence_score=rel - 0.2))
        db.commit()
        yield {"shop_id": shop_id, "shop_b": shop_b}
    finally:
        for model in [models.CompetitorBusinessProfile,
                      models.CompetitorFulfilmentProfile,
                      models.CompetitorFinancialObservation,
                      models.CompetitorMarketRole,
                      models.CompetitorGeographicPresence,
                      models.CompetitorCorporateRelation,
                      models.CompetitorEvolutionEvent,
                      models.CompetitorFieldValidation,
                      models.CompetitorFreshnessRule,
                      models.CompetitorScoreResult,
                      models.CompetitorRanking,
                      models.CompetitionEvidence,
                      models.CompetitorProfile,
                      models.IntelligenceSignal,
                      models.CostUsageRecord]:
            if shop_id is not None and hasattr(model, "shop_id"):
                db.query(model).filter(
                    model.shop_id.in_([shop_id, shop_b])).delete(
                    synchronize_session=False)
        for sid in (shop_id, shop_b):
            if sid is not None:
                db.query(models.DimShop).filter(
                    models.DimShop.id == sid).delete(synchronize_session=False)
        db.commit()
        db.close()


def _q(seed, **extra):
    return "&".join([f"shop_id={seed['shop_id']}"] +
                    [f"{k}={v}" for k, v in extra.items()])


# ── Volledig profiel met include-params ─────────────────────────────────────

def test_full_profile_includes_scores_and_timeline(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/competitor-profile/{COMP_A}?{_q(seed)}"
        "&include_scores=true&include_timeline=true&include_evidence=true",
        headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scores"]["business_strength_score"] == 80.0
    assert body["scores"]["details"]["business_strength"]["factors"]
    assert body["ranking"]["rank"] == 1
    assert body["timeline"]["total"] >= 1
    assert body["evidence"]["total"] == 0
    assert body["completeness"]["business"]["completeness_pct"] > 0


def test_full_profile_without_includes_has_no_scores_key(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/competitor-profile/{COMP_A}?{_q(seed)}",
        headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "scores" not in body and "timeline" not in body


def test_full_profile_scores_null_when_never_scored(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/competitor-profile/{COMP_C}?{_q(seed)}"
        "&include_scores=true", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    # Onbekend blijft null — nooit 0
    assert body["scores"] is None
    assert body["ranking"] is None


# ── Vergelijking (2–5) ───────────────────────────────────────────────────────

def test_compare_two_competitors(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/competitor-profile/compare?{_q(seed)}"
        f"&names={COMP_A},{COMP_B}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    a, b = body["items"]
    assert a["competitor_name"] == COMP_A
    assert a["scores"]["business_strength_score"] == 80.0
    assert a["countries"] == ["DE"]
    assert a["ranking"]["rank"] == 1
    assert b["business"]["customer_model"] == "B2B"


def test_compare_rejects_wrong_counts(client, admin_headers, seed):
    r1 = client.get(
        f"/api/competition/competitor-profile/compare?{_q(seed)}&names={COMP_A}",
        headers=admin_headers)
    assert r1.status_code == 400
    six = ",".join([COMP_A, COMP_B, COMP_C] + [f"x{i}.nl" for i in range(3)])
    r2 = client.get(
        f"/api/competition/competitor-profile/compare?{_q(seed)}&names={six}",
        headers=admin_headers)
    assert r2.status_code == 400


def test_compare_404_on_foreign_shop_competitor(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/competitor-profile/compare?{_q(seed)}"
        f"&names={COMP_A},{COMP_OTHER}", headers=admin_headers)
    assert resp.status_code == 404


# ── Rankingfilters (server-side, correcte totalen) ──────────────────────────

def test_rankings_unfiltered_total(client, admin_headers, seed):
    resp = client.get(f"/api/competition/rankings?{_q(seed)}",
                      headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    names = {r["competitor_name"] for r in body["rankings"]}
    assert {COMP_A, COMP_B} <= names
    assert body["total"] == len(body["rankings"])


def test_rankings_filter_company_size(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/rankings?{_q(seed, company_size='groot')}",
        headers=admin_headers)
    body = resp.json()
    names = {r["competitor_name"] for r in body["rankings"]}
    assert COMP_A in names and COMP_B not in names
    assert body["total"] == len(body["rankings"])


def test_rankings_filter_combined(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/rankings?"
        f"{_q(seed, market_role='prijsagressor', fulfilment_model='dropship', country='DE')}",
        headers=admin_headers)
    body = resp.json()
    names = {r["competitor_name"] for r in body["rankings"]}
    assert names == {COMP_A} or (COMP_A in names and COMP_B not in names)


def test_rankings_filter_min_scores_and_health(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/rankings?"
        f"{_q(seed, min_business_strength=50, financial_health='gezond', min_data_completeness=80)}",
        headers=admin_headers)
    body = resp.json()
    names = {r["competitor_name"] for r in body["rankings"]}
    assert COMP_A in names and COMP_B not in names


def test_rankings_filter_customer_model_b2b(client, admin_headers, seed):
    resp = client.get(
        f"/api/competition/rankings?{_q(seed, customer_model='B2B')}",
        headers=admin_headers)
    body = resp.json()
    names = {r["competitor_name"] for r in body["rankings"]}
    assert COMP_B in names and COMP_A not in names


# ── Concurrent Landscape ─────────────────────────────────────────────────────

def test_landscape_points_and_unknowns(client, admin_headers, seed):
    resp = client.get(f"/api/competition/landscape?{_q(seed)}",
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_name = {i["competitor_name"]: i for i in body["items"]}
    a = by_name[COMP_A]
    assert a["competition_relevance_score"] == 0.9
    assert a["business_strength_score"] == 80.0
    assert a["future_threat_score"] == 65.0
    assert a["company_size_class"] == "groot"
    assert a["market_roles"] == ["prijsagressor"]
    b = by_name[COMP_B]
    # Onbekende as blijft null, nooit 0
    assert b["future_threat_score"] is None
    assert body["total"] == len(body["items"])


# ── Validatie-RBAC ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def viewer_headers(client, seed):
    uname = f"{PFX.lower()}_viewer"
    db = SessionLocal()
    try:
        import auth
        db.add(models.User(username=uname, hashed_password=auth.hash_password("test1234"),
                           role="viewer", email=f"{uname}@test.nl"))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login",
                       json={"username": uname, "password": "test1234"})
    assert resp.status_code == 200, resp.text
    yield {"Authorization": f"Bearer {resp.json()['token']}"}
    db = SessionLocal()
    try:
        db.query(models.User).filter(models.User.username == uname).delete()
        db.commit()
    finally:
        db.close()


def test_validate_forbidden_for_viewer(client, viewer_headers, seed):
    resp = client.post(
        f"/api/competition/competitor-profile/{COMP_A}/validate?{_q(seed)}",
        headers=viewer_headers,
        json={"section": "business", "field_name": "size_class",
              "action": "bevestigen"})
    assert resp.status_code == 403


def test_validate_allowed_for_admin(client, admin_headers, seed):
    resp = client.post(
        f"/api/competition/competitor-profile/{COMP_A}/validate?{_q(seed)}",
        headers=admin_headers,
        json={"section": "business", "field_name": "size_class",
              "action": "bevestigen", "reason": "klopt met jaarrekening"})
    assert resp.status_code in (200, 201), resp.text
