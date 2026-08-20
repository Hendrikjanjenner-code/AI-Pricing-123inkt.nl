"""
Tests voor het concurrentprofiel-datamodel & evidence-fundament (taak #246):
unknown-afhandeling, evidence-koppeling, historische versionering (timeline),
parent-mapping, actieve landen, validatie-workflow, freshness-config,
social-media-guard voor financiële data en RBAC/shop-scoping.
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

# Kleine letters: concurrentnamen zijn canonieke (lowercase) domeinen.
PFX = f"cptest{uuid.uuid4().hex[:6]}"
COMP = f"{PFX}-concurrent.nl"
COMP_B = f"{PFX}-andershop.nl"


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
    """Eigen test-shop met een bestaande concurrent-identiteit
    (CompetitorProfile), plus een tweede shop voor scoping-tests."""
    db = SessionLocal()
    shop_id = shop_b = None
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop")
        shop2 = models.DimShop(shop_code=f"{PFX}-shop-b", name=f"{PFX} Shop B")
        db.add_all([shop, shop2])
        db.flush()
        shop_id, shop_b = shop.id, shop2.id
        db.add(models.CompetitorProfile(competitor_name=COMP, shop_id=shop_id,
                                        run_date=date.today()))
        db.add(models.CompetitorProfile(competitor_name=COMP_B, shop_id=shop_b,
                                        run_date=date.today()))
        db.commit()
        yield {"shop_id": shop_id, "shop_b": shop_b}
    finally:
        # Volgorde: eerst tabellen die naar CompetitionEvidence verwijzen,
        # dan pas de evidence zelf (FK).
        for model in [models.CompetitorBusinessProfile,
                      models.CompetitorFulfilmentProfile,
                      models.CompetitorFinancialObservation,
                      models.CompetitorMarketRole,
                      models.CompetitorGeographicPresence,
                      models.CompetitorCorporateRelation,
                      models.CompetitorEvolutionEvent,
                      models.CompetitorFieldValidation,
                      models.CompetitorFreshnessRule,
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


def _url(path, seed, **extra):
    q = "&".join([f"shop_id={seed['shop_id']}"] +
                 [f"{k}={v}" for k, v in extra.items()])
    return f"/api/competition/competitor-profile/{COMP}{path}?{q}"


# ── Evidence-koppeling ───────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def evidence(client, admin_headers, seed):
    resp = client.post(_url("/evidence", seed), headers=admin_headers, json={
        "source_type": "jaarrekening",
        "source_url": "https://example.com/jaarrekening.pdf",
        "title": "Jaarrekening 2025", "observed_date": "2026-05-01",
        "reliability": "high", "confidence": 0.9,
        "extracted_fact": "Omzet 12,3 mln EUR",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Bronprioriteit: jaarrekening = hoogste prioriteit (1)
    assert body["source_priority"] == 1
    return body


def test_financial_observation_with_evidence(client, admin_headers, seed, evidence):
    resp = client.post(_url("/financials", seed), headers=admin_headers, json={
        "fiscal_year": 2025, "metric": "revenue",
        "value_min": 12000000, "value_max": 12500000, "currency": "EUR",
        "information_layer": "feit", "confidence": 0.9,
        "evidence_id": evidence["id"], "as_of_date": "2026-05-01",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["evidence_id"] == evidence["id"]


def test_social_media_never_sole_basis_for_strong_financial(client, admin_headers, seed):
    ev = client.post(_url("/evidence", seed), headers=admin_headers, json={
        "source_type": "social_media", "title": "LinkedIn-post"}).json()
    resp = client.post(_url("/financials", seed), headers=admin_headers, json={
        "fiscal_year": 2025, "metric": "profit", "value_min": 1000000,
        "information_layer": "feit", "confidence": 0.9, "evidence_id": ev["id"],
    })
    assert resp.status_code == 400
    assert "ociale media" in resp.json()["detail"]
    # Als schatting met lage confidence mag het wél
    resp = client.post(_url("/financials", seed), headers=admin_headers, json={
        "fiscal_year": 2025, "metric": "profit", "value_min": 1000000,
        "information_layer": "hypothese", "confidence": 0.3,
        "evidence_id": ev["id"]})
    assert resp.status_code == 201, resp.text
    # Sterke conclusie zonder enige evidence mag ook niet
    resp = client.post(_url("/financials", seed), headers=admin_headers, json={
        "fiscal_year": 2024, "metric": "profit", "value_min": 1,
        "information_layer": "feit", "confidence": 0.9})
    assert resp.status_code == 400


def test_evidence_scoping_rejected(client, admin_headers, seed):
    """Evidence-id's van een andere shop/concurrent of niet-bestaand → 400."""
    # Evidence aangemaakt voor de concurrent van shop B (via shop B-scope)
    resp = client.post(
        f"/api/competition/competitor-profile/{COMP_B}/evidence"
        f"?shop_id={seed['shop_b']}", headers=admin_headers,
        json={"source_type": "jaarrekening", "title": "Andermans bewijs"})
    assert resp.status_code == 201, resp.text
    foreign_ev = resp.json()["id"]

    # 1. Cross-shop evidence op een sterke financiële conclusie → geweigerd
    resp = client.post(_url("/financials", seed), headers=admin_headers, json={
        "fiscal_year": 2025, "metric": "ebitda", "value_min": 5,
        "information_layer": "feit", "confidence": 0.9,
        "evidence_id": foreign_ev})
    assert resp.status_code == 400, resp.text
    assert "bestaat niet" in resp.json()["detail"]

    # 2. Niet-bestaand evidence-id → geweigerd (ook bij zwakke conclusies)
    for path, body in [
        ("/financials", {"fiscal_year": 2025, "metric": "ebitda",
                         "information_layer": "hypothese", "confidence": 0.1,
                         "evidence_id": 99999999}),
        ("/roles", {"role": "nichespeler", "evidence_id": 99999999}),
        ("/geography", {"country_code": "FR", "presence_type": "webshop",
                        "evidence_id": 99999999}),
        ("/relations", {"relation_type": "parent", "related_entity": "X BV",
                        "evidence_id": 99999999}),
    ]:
        resp = client.post(_url(path, seed), headers=admin_headers, json=body)
        assert resp.status_code == 400, (path, resp.text)

    # 3. Ook field_meta van singleton-profielen weigert vreemde evidence
    resp = client.put(_url("/business", seed), headers=admin_headers, json={
        "fields": {"legal_name": {"value": "Test BV",
                                  "evidence_id": foreign_ev}}})
    assert resp.status_code == 400, resp.text


# ── Unknown-afhandeling ──────────────────────────────────────────────────────

def test_unknown_is_explicit_not_zero(client, admin_headers, seed):
    resp = client.post(_url("/financials", seed), headers=admin_headers, json={
        "fiscal_year": 2023, "metric": "employees", "is_unknown": True,
        "information_layer": "hypothese", "confidence": 0.0})
    assert resp.status_code == 201, resp.text
    row = resp.json()
    assert row["is_unknown"] is True
    assert row["value_min"] is None and row["value_max"] is None

    # Business-profiel: veld expliciet unknown zetten
    resp = client.put(_url("/business", seed), headers=admin_headers, json={
        "fields": {
            "size_class": {"value": "groot", "information_layer": "schatting",
                           "confidence": 0.6},
            "kvk_number": {"status": "unknown",
                           "information_layer": "hypothese"},
        }})
    assert resp.status_code == 200, resp.text
    biz = resp.json()["business"]
    assert biz["size_class"] == "groot"
    assert biz["kvk_number"] is None
    assert biz["field_meta"]["kvk_number"]["status"] == "unknown"


def test_completeness_counts_unknown_separately(client, admin_headers, seed):
    resp = client.get(_url("", seed), headers=admin_headers)
    assert resp.status_code == 200, resp.text
    comp = resp.json()["completeness"]["business"]
    assert comp["known"] >= 1
    assert comp["unknown_explicit"] >= 1
    assert comp["known"] + comp["unknown_explicit"] + comp["missing"] == comp["total_fields"]
    assert 0 < comp["completeness_pct"] < 100


# ── Historie / timeline ──────────────────────────────────────────────────────

def test_profile_changes_create_timeline_events(client, admin_headers, seed):
    r1 = client.put(_url("/business", seed), headers=admin_headers, json={
        "fields": {"employee_range_min": {"value": 50, "information_layer": "schatting",
                                          "confidence": 0.5}}})
    assert r1.status_code == 200
    r2 = client.put(_url("/business", seed), headers=admin_headers, json={
        "fields": {"employee_range_min": {"value": 80, "information_layer": "feit",
                                          "confidence": 0.9}}})
    assert r2.status_code == 200
    assert r2.json()["changed_fields"] == ["employee_range_min"]
    tl = client.get(_url("/timeline", seed, section="business"),
                    headers=admin_headers).json()
    ev = [e for e in tl["items"] if e["field_name"] == "employee_range_min"]
    assert len(ev) >= 2
    changed = [e for e in ev if e["old_value"] == 50 and e["new_value"] == 80]
    assert changed, ev


# ── Fulfilment, rollen, landen, relaties ────────────────────────────────────

def test_fulfilment_profile(client, admin_headers, seed):
    resp = client.put(_url("/fulfilment", seed), headers=admin_headers, json={
        "fields": {
            "inventory_model": {"value": "hybride", "information_layer": "afgeleid_signaal",
                                "confidence": 0.6},
            "next_day_delivery": {"value": True, "information_layer": "feit",
                                  "confidence": 0.9}}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["fulfilment"]["inventory_model"] == "hybride"


def test_multiple_market_roles(client, admin_headers, seed):
    for role, ai in [("prijsvechter", True), ("platform", False)]:
        resp = client.post(_url("/roles", seed), headers=admin_headers, json={
            "role": role, "ai_assigned": ai, "confidence": 0.7})
        assert resp.status_code == 201, resp.text
    roles = client.get(_url("/roles", seed, active_only="true"),
                       headers=admin_headers).json()
    names = {r["role"] for r in roles["items"]}
    assert {"prijsvechter", "platform"} <= names
    # Rol beëindigen laat historie intact
    rid = roles["items"][0]["id"]
    resp = client.delete(_url(f"/roles/{rid}", seed), headers=admin_headers)
    assert resp.status_code == 200
    all_roles = client.get(_url("/roles", seed), headers=admin_headers).json()
    assert any(r["valid_to"] for r in all_roles["items"])


def test_active_countries(client, admin_headers, seed):
    for cc, pt in [("NL", "operationeel"), ("DE", "webshop")]:
        resp = client.post(_url("/geography", seed), headers=admin_headers,
                           json={"country_code": cc, "presence_type": pt})
        assert resp.status_code == 201, resp.text
    # Ongeldig presence_type wordt geweigerd
    resp = client.post(_url("/geography", seed), headers=admin_headers,
                       json={"country_code": "BE", "presence_type": "belastingvoordeel"})
    assert resp.status_code == 400
    geo = client.get(_url("/geography", seed, active_only="true"),
                     headers=admin_headers).json()
    by_cc = {g["country_code"]: g["presence_type"] for g in geo["items"]}
    assert by_cc.get("NL") == "operationeel"
    assert by_cc.get("DE") == "webshop"


def test_parent_mapping(client, admin_headers, seed):
    resp = client.post(_url("/relations", seed), headers=admin_headers, json={
        "relation_type": "ultimate_parent", "related_entity": "Holding BV",
        "related_country": "US", "information_layer": "feit",
        "confidence": 0.9})
    assert resp.status_code == 201, resp.text
    resp = client.post(_url("/relations", seed), headers=admin_headers, json={
        "relation_type": "neefje", "related_entity": "X"})
    assert resp.status_code == 400
    rel = client.get(_url("/relations", seed), headers=admin_headers).json()
    assert any(r["relation_type"] == "ultimate_parent"
               and r["related_entity"] == "Holding BV" for r in rel["items"])


# ── Validatie-workflow ───────────────────────────────────────────────────────

def test_validation_correct_keeps_both_values(client, admin_headers, seed):
    client.put(_url("/business", seed), headers=admin_headers, json={
        "fields": {"founded_year": {"value": 1999, "information_layer": "schatting",
                                    "confidence": 0.4}}})
    resp = client.post(_url("/validate", seed), headers=admin_headers, json={
        "section": "business", "field_name": "founded_year",
        "action": "corrigeren", "human_value": 2001,
        "reason": "KvK-uittreksel gecheckt"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ai_value"] == 1999 and body["human_value"] == 2001
    assert body["reviewer"] == "dev_admin"
    # Menselijke correctie wint operationeel
    prof = client.get(_url("", seed), headers=admin_headers).json()
    assert prof["business"]["founded_year"] == 2001
    assert prof["business"]["field_meta"]["founded_year"]["human_validated"] is True
    # Historie opvraagbaar
    vals = client.get(_url("/validations", seed), headers=admin_headers).json()
    v = [x for x in vals["items"] if x["field_name"] == "founded_year"][0]
    assert v["reason"] == "KvK-uittreksel gecheckt" and v["is_current"]


def test_validation_unknown_and_reinvestigate(client, admin_headers, seed):
    resp = client.post(_url("/validate", seed), headers=admin_headers, json={
        "section": "business", "field_name": "revenue_currency",
        "action": "unknown", "reason": "Niet vast te stellen"})
    assert resp.status_code == 201
    prof = client.get(_url("", seed), headers=admin_headers).json()
    assert prof["business"]["revenue_currency"] is None
    assert prof["business"]["field_meta"]["revenue_currency"]["status"] == "unknown"
    resp = client.post(_url("/validate", seed), headers=admin_headers, json={
        "section": "business", "field_name": "geographic_scale",
        "action": "heronderzoek"})
    assert resp.status_code == 201
    prof = client.get(_url("", seed), headers=admin_headers).json()
    assert prof["business"]["field_meta"]["geographic_scale"]["status"] == "needs_review"


# ── Freshness ────────────────────────────────────────────────────────────────

def test_freshness_rules_configurable(client, admin_headers, seed):
    resp = client.get(f"/api/competition/competitor-profile/config/freshness"
                      f"?shop_id={seed['shop_id']}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["rules"]["revenue"] == 365
    resp = client.put(f"/api/competition/competitor-profile/config/freshness"
                      f"?shop_id={seed['shop_id']}", headers=admin_headers,
                      json={"rules": {"employees": 30, "revenue": 400}})
    assert resp.status_code == 200, resp.text
    rules = resp.json()["rules"]
    assert rules["employees"] == 30 and rules["revenue"] == 400
    # Ongeldig veldtype geweigerd
    resp = client.put(f"/api/competition/competitor-profile/config/freshness"
                      f"?shop_id={seed['shop_id']}", headers=admin_headers,
                      json={"rules": {"schoenmaat": 10}})
    assert resp.status_code == 400


def test_stale_field_detected(client, admin_headers, seed):
    # employees-regel is hierboven op 30 dagen gezet; maak het veld oud
    db = SessionLocal()
    try:
        prof = db.query(models.CompetitorBusinessProfile).filter(
            models.CompetitorBusinessProfile.shop_id == seed["shop_id"],
            models.CompetitorBusinessProfile.competitor_name == COMP).first()
        meta = dict(prof.field_meta or {})
        m = dict(meta.get("employee_range_min") or {})
        m["last_verified_at"] = (datetime.utcnow() - timedelta(days=90)).isoformat()
        meta["employee_range_min"] = m
        prof.field_meta = meta
        db.commit()
    finally:
        db.close()
    prof = client.get(_url("", seed), headers=admin_headers).json()
    assert "employee_range_min" in prof["completeness"]["business"]["stale_fields"]


# ── RBAC & shop-scoping ──────────────────────────────────────────────────────

def test_rbac_requires_auth_and_role(client, seed):
    resp = client.get(_url("", seed))
    assert resp.status_code in (401, 403)
    # Viewer mag lezen maar niet schrijven
    login = client.post("/api/auth/login",
                        json={"username": "dev_viewer", "password": "viewer123"})
    if login.status_code != 200:
        pytest.skip("geen viewer-testaccount beschikbaar")
    vh = {"Authorization": f"Bearer {login.json()['token']}"}
    resp = client.put(_url("/business", seed), headers=vh, json={
        "fields": {"size_class": {"value": "klein"}}})
    assert resp.status_code == 403


def test_shop_scoping_foreign_competitor_404(client, admin_headers, seed):
    # Concurrent van shop B is via shop A-scope onvindbaar
    resp = client.get(f"/api/competition/competitor-profile/{COMP_B}"
                      f"?shop_id={seed['shop_id']}", headers=admin_headers)
    assert resp.status_code == 404
    # En een volstrekt onbekende concurrent ook
    resp = client.get(f"/api/competition/competitor-profile/bestaat-niet.nl"
                      f"?shop_id={seed['shop_id']}", headers=admin_headers)
    assert resp.status_code == 404
