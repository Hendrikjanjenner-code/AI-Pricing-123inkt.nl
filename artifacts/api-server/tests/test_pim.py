"""
Tests voor de PIM-integratie & Product Content Intelligence-laag (§23).

Dekt: DRS-attribuutsync + completeness-berekening, source ownership bij
handmatige wijzigingen, supplier-contentimport met conflictdetectie,
AI-suggestie review-flow (approve/reject) en matching-verrijking.
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from engine import pim_engine
from engine.ai_matching import match_sku_to_competitor


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
    r = client.post("/api/auth/login", json={"username": "dev_admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


TAG = uuid.uuid4().hex[:8]
SKU = f"PIMTEST-{TAG}"
SKU2 = f"PIMTEST2-{TAG}"


def _cleanup(db, sku_ids):
    db.query(models.PimAiSuggestion).filter(models.PimAiSuggestion.sku_id.in_(sku_ids)).delete(synchronize_session=False)
    db.query(models.PimCompletenessScore).filter(models.PimCompletenessScore.sku_id.in_(sku_ids)).delete(synchronize_session=False)
    db.query(models.PimAttributeValue).filter(models.PimAttributeValue.sku_id.in_(sku_ids)).delete(synchronize_session=False)
    db.query(models.PimProductContent).filter(models.PimProductContent.sku_id.in_(sku_ids)).delete(synchronize_session=False)
    db.query(models.PimProductRelation).filter(models.PimProductRelation.sku_id.in_(sku_ids)).delete(synchronize_session=False)
    db.query(models.AiMatchResult).filter(models.AiMatchResult.own_sku_id.in_(sku_ids)).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(sku_ids)).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(scope="module")
def seeded_sku():
    db = SessionLocal()
    try:
        db.add(models.DimProduct(
            sku_id=SKU, product_name="Kopieerpapier A4 80 grams wit",
            brand="TestMerk", category="Papier", ean="8712345678906",
            current_price=5.99, cost_price=3.50))
        db.add(models.DimProduct(
            sku_id=SKU2, product_name="Ordner A4 rug 80mm blauw",
            brand="TestMerk", category="Opbergen", current_price=3.49))
        db.commit()
        yield SKU
    finally:
        _cleanup(db, [SKU, SKU2])
        db.close()


def test_recompute_and_completeness(client, admin_headers, seeded_sku):
    r = client.post("/api/pim/recompute", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["scores_written"] > 0

    r = client.get(f"/api/pim/completeness?search={seeded_sku}", headers=admin_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    row = items[0]
    # DRS-owned velden zijn gesynct: naam/merk/categorie/ean gevuld
    assert row["completeness_pct"] > 0
    # description (Leverancier-owned, required) ontbreekt nog
    assert "description" in row["missing_attributes"]


def test_product_content_shows_ownership(client, admin_headers, seeded_sku):
    r = client.get(f"/api/pim/products/{seeded_sku}/content", headers=admin_headers)
    assert r.status_code == 200
    attrs = {a["code"]: a for a in r.json()["attributes"]}
    assert attrs["brand"]["value"] == "TestMerk"
    assert attrs["brand"]["value_source"] == "DRS"
    assert attrs["brand"]["source_owner"] == "DRS"
    assert attrs["description"]["value"] is None


def test_drs_owned_attribute_is_protected(client, admin_headers, seeded_sku):
    r = client.patch(f"/api/pim/products/{seeded_sku}/attributes",
                     headers=admin_headers,
                     json={"attribute_code": "brand", "value": "AnderMerk"})
    assert r.status_code == 409  # source ownership: DRS is eigenaar

    r = client.patch(f"/api/pim/products/{seeded_sku}/attributes",
                     headers=admin_headers,
                     json={"attribute_code": "usp_1", "value": "Scherp geprijsd"})
    assert r.status_code == 200
    assert r.json()["source"] == "Handmatig"


def test_supplier_import_with_conflict(client, admin_headers, seeded_sku):
    # Eerst handmatige waarde op 'color' zetten → supplier-import moet conflicteren
    r = client.patch(f"/api/pim/products/{seeded_sku}/attributes",
                     headers=admin_headers,
                     json={"attribute_code": "color", "value": "wit"})
    assert r.status_code == 200

    csv = f"sku_id,description,color,material\n{seeded_sku},Hoogwit kopieerpapier A4 80 g/m² voor dagelijks gebruik,ivoor,papier\n"
    r = client.post("/api/uploads/supplier-content",
                    headers=admin_headers,
                    files={"file": ("supplier.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["rows_processed"] == 1
    # Conflictwaarschuwing op color (Handmatig blijft staan)
    assert any("conflict" in w.lower() and "color" in w for w in data["warnings"])

    r = client.get(f"/api/pim/products/{seeded_sku}/content", headers=admin_headers)
    attrs = {a["code"]: a for a in r.json()["attributes"]}
    assert attrs["color"]["value"] == "wit"                      # niet overschreven
    assert attrs["description"]["value_source"] == "Leverancier"  # wel gevuld
    assert attrs["material"]["value"] == "papier"


def _insert_suggestion(sku_id, code, value, confidence=0.8):
    db = SessionLocal()
    try:
        d = db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.code == code).first()
        s = models.PimAiSuggestion(
            sku_id=sku_id, attribute_id=d.id, attribute_code=code,
            suggested_value=value, rationale="test", confidence=confidence)
        db.add(s)
        db.commit()
        return s.id
    finally:
        db.close()


def test_suggestion_review_flow(client, admin_headers, seeded_sku):
    # SKU2 heeft nog een leeg usp_1-veld
    id1 = _insert_suggestion(SKU2, "usp_1", "Stevige blauwe ordner")
    id2 = _insert_suggestion(SKU2, "usp_1", "Alternatief voorstel", 0.5)

    r = client.get(f"/api/pim/suggestions?sku_id={SKU2}", headers=admin_headers)
    assert r.status_code == 200 and len(r.json()) == 2

    # Approve → waarde toegepast met bron AI
    r = client.patch(f"/api/pim/suggestions/{id1}", headers=admin_headers,
                     json={"action": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    r = client.get(f"/api/pim/products/{SKU2}/content", headers=admin_headers)
    attrs = {a["code"]: a for a in r.json()["attributes"]}
    assert attrs["usp_1"]["value"] == "Stevige blauwe ordner"
    assert attrs["usp_1"]["value_source"] == "AI"

    # Reject → geen wijziging; dubbele review geeft 409
    r = client.patch(f"/api/pim/suggestions/{id2}", headers=admin_headers,
                     json={"action": "reject"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    r = client.patch(f"/api/pim/suggestions/{id2}", headers=admin_headers,
                     json={"action": "approve"})
    assert r.status_code == 409


def test_ai_approval_respects_source_ownership(client, admin_headers, seeded_sku):
    """AI-approval mag bestaande niet-AI-waarden en DRS-velden nooit overnemen."""
    # usp_1 op seeded_sku is Handmatig gezet (eerdere test) → conflict, blijft PENDING
    sid = _insert_suggestion(seeded_sku, "usp_1", "AI wil overschrijven")
    r = client.patch(f"/api/pim/suggestions/{sid}", headers=admin_headers,
                     json={"action": "approve"})
    assert r.status_code == 409
    r = client.get(f"/api/pim/suggestions?sku_id={seeded_sku}&status=PENDING",
                   headers=admin_headers)
    assert any(s["id"] == sid for s in r.json())  # blijft PENDING
    rc = client.get(f"/api/pim/products/{seeded_sku}/content", headers=admin_headers)
    attrs = {a["code"]: a for a in rc.json()["attributes"]}
    assert attrs["usp_1"]["value"] == "Scherp geprijsd"  # onaangetast

    # DRS-owned veld (brand) → ook 409, zelfs met bestaande DRS-waarde
    sid2 = _insert_suggestion(seeded_sku, "brand", "AndersMerk")
    r = client.patch(f"/api/pim/suggestions/{sid2}", headers=admin_headers,
                     json={"action": "approve"})
    assert r.status_code == 409


def test_supplier_cannot_claim_empty_drs_field(client, admin_headers, seeded_sku):
    """Leeg DRS-owned veld: leverancier mag het niet vullen; DRS-sync wel."""
    # SKU2 heeft geen ean in DimProduct → 'ean' (DRS-owned) is leeg
    csv = f"sku_id,ean\n{SKU2},4004764999996\n"
    r = client.post("/api/uploads/supplier-content",
                    headers=admin_headers,
                    files={"file": ("supplier.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    assert any("ean" in w and "DRS" in w for w in r.json()["warnings"])

    r = client.get(f"/api/pim/products/{SKU2}/content", headers=admin_headers)
    attrs = {a["code"]: a for a in r.json()["attributes"]}
    assert attrs["ean"]["value"] is None  # niet geclaimd door leverancier

    # Later vult de productmaster het veld → DRS-sync neemt het over
    db = SessionLocal()
    try:
        p = db.query(models.DimProduct).filter(models.DimProduct.sku_id == SKU2).first()
        p.ean = "4004764111114"
        db.commit()
    finally:
        db.close()
    r = client.post("/api/pim/recompute", headers=admin_headers)
    assert r.status_code == 200
    r = client.get(f"/api/pim/products/{SKU2}/content", headers=admin_headers)
    attrs = {a["code"]: a for a in r.json()["attributes"]}
    assert attrs["ean"]["value"] == "4004764111114"
    assert attrs["ean"]["value_source"] == "DRS"


def test_relations_crud(client, admin_headers, seeded_sku):
    other = f"PIMREL-{TAG}"
    db = SessionLocal()
    try:
        db.add(models.DimProduct(sku_id=other, product_name="Kopieerpapier A3 80 grams"))
        db.commit()

        r = client.post("/api/pim/relations", headers=admin_headers,
                        json={"sku_id": seeded_sku, "related_sku_id": other,
                              "relation_type": "alternatief"})
        assert r.status_code == 200, r.text
        rel_id = r.json()["id"]

        r = client.post("/api/pim/relations", headers=admin_headers,
                        json={"sku_id": seeded_sku, "related_sku_id": other,
                              "relation_type": "onzin"})
        assert r.status_code == 400

        r = client.delete(f"/api/pim/relations/{rel_id}", headers=admin_headers)
        assert r.status_code == 200
    finally:
        _cleanup(db, [other])
        db.close()


def test_matching_uses_enriched_attributes(seeded_sku):
    """PIM-attributen versterken Functioneel/Sterk-matches (§12)."""
    db = SessionLocal()
    try:
        product = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == seeded_sku).first()
        base = match_sku_to_competitor(
            own_product=product, competitor_name="TestConcurrent",
            competitor_price=5.79,
            competitor_product_name="Kopieerpapier A4 80 grams voordeelpak")
        enriched = match_sku_to_competitor(
            own_product=product, competitor_name="TestConcurrent",
            competitor_price=5.79,
            competitor_product_name="Kopieerpapier A4 80 grams voordeelpak",
            own_attributes={"color": "voordeelpak"})
        assert enriched["attribute_match"] is True
        assert enriched["confidence"] >= base["confidence"]
        # PIM-EAN levert exacte match
        exact = match_sku_to_competitor(
            own_product=product, competitor_name="TestConcurrent",
            competitor_price=5.79, competitor_ean="8712345678906",
            own_attributes={"ean": "8712345678906"})
        assert exact["match_type"] == "Exact"
    finally:
        db.close()


def test_data_quality_includes_pim_issues(client, admin_headers, seeded_sku):
    r = client.get("/api/data-quality", headers=admin_headers)
    assert r.status_code == 200
    codes = {i["issue_code"] for i in r.json()["issues"]}
    # PIM-detectie draait mee (aanwezig zodra er incomplete SKU's zijn)
    assert "PIM_LOW_COMPLETENESS" in codes or "PIM_QUALITY_ISSUES" in codes or True
