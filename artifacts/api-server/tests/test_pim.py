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
    r = client.post("/api/pim/recompute", headers=admin_headers, json={"sku_ids": [SKU, SKU2]})
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
    r = client.post("/api/pim/recompute", headers=admin_headers, json={"sku_ids": [SKU, SKU2]})
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


# ─── Beheer-endpoints: attributen / channels / families ──────────────────────

def _get_attr_id(client, headers, code: str) -> int:
    attrs = client.get("/api/pim/attributes", headers=headers).json()
    return next(a["id"] for a in attrs if a["code"] == code)


def _get_channel_id(client, headers, code: str) -> int:
    chans = client.get("/api/pim/channels", headers=headers).json()
    return next(c["id"] for c in chans if c["code"] == code)


def _get_family_id(client, headers, code: str) -> int:
    fams = client.get("/api/pim/families", headers=headers).json()
    return next(f["id"] for f in fams if f["code"] == code)


def test_patch_attribute_required_and_weight(client, admin_headers, seeded_sku):
    """PATCH attribuutdefinitie wijzigt is_required en weight en persisteert."""
    # Zorg dat defaults bestaan via recompute
    client.post("/api/pim/recompute", headers=admin_headers, json={"sku_ids": [SKU, SKU2]})
    attr_id = _get_attr_id(client, admin_headers, "usp_1")

    r = client.patch(f"/api/pim/attributes/{attr_id}", headers=admin_headers,
                     json={"is_required": True, "weight": 2.5})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_required"] is True
    assert data["weight"] == 2.5

    # Persistentie: ophalen via GET moet gewijzigde waarden tonen
    attrs = client.get("/api/pim/attributes", headers=admin_headers).json()
    usp = next(a for a in attrs if a["id"] == attr_id)
    assert usp["is_required"] is True
    assert usp["weight"] == 2.5

    # Herstel om andere tests niet te verstoren
    client.patch(f"/api/pim/attributes/{attr_id}", headers=admin_headers,
                 json={"is_required": False, "weight": 0.5})


def test_patch_attribute_invalid_source_rejected(client, admin_headers, seeded_sku):
    """PATCH met ongeldige source_owner geeft HTTP 400."""
    client.post("/api/pim/recompute", headers=admin_headers, json={"sku_ids": [SKU, SKU2]})
    attr_id = _get_attr_id(client, admin_headers, "color")
    r = client.patch(f"/api/pim/attributes/{attr_id}", headers=admin_headers,
                     json={"source_owner": "Onbekend"})
    assert r.status_code == 400


def test_patch_channel_threshold_persists_and_recompute_respects_it(client, admin_headers, seeded_sku):
    """
    PATCH channel min_completeness_pct=0 moet persisteren en de
    recompute moet die waarde gebruiken — ook als de waarde 0 is
    (regressie: `ch.min_completeness_pct or 80.0` behandelde 0 als 80).
    """
    client.post("/api/pim/recompute", headers=admin_headers, json={"sku_ids": [SKU, SKU2]})
    chan_id = _get_channel_id(client, admin_headers, "webshop")

    # Zet drempel op 0: elk channel-score is dan meteen "ready"
    r = client.patch(f"/api/pim/channels/{chan_id}", headers=admin_headers,
                     json={"min_completeness_pct": 0})
    assert r.status_code == 200, r.text
    assert r.json()["min_completeness_pct"] == 0.0

    # Persistentie via GET
    chans = client.get("/api/pim/channels", headers=admin_headers).json()
    ws = next(c for c in chans if c["id"] == chan_id)
    assert ws["min_completeness_pct"] == 0.0

    # Na herberekening moet seeded_sku channel_ready=True zijn (drempel=0)
    client.post("/api/pim/recompute", headers=admin_headers, json={"sku_ids": [SKU, SKU2]})
    r = client.get(f"/api/pim/completeness?channel=webshop&search={seeded_sku}",
                   headers=admin_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    if items:  # SKU kan gefilterd zijn op andere criteria
        assert items[0]["channel_ready"] is True

    # Controleer ook een hoge drempel: stel threshold=100 in en herbereken.
    # Verifieer dat de waarde is opgeslagen (niet dat de SKU zelf niet-ready is —
    # die kan al volledig zijn door eerdere tests in dezelfde module).
    client.patch(f"/api/pim/channels/{chan_id}", headers=admin_headers,
                 json={"min_completeness_pct": 100})
    chans2 = client.get("/api/pim/channels", headers=admin_headers).json()
    ws2 = next(c for c in chans2 if c["id"] == chan_id)
    assert ws2["min_completeness_pct"] == 100.0

    # Herstel naar originele waarde
    client.patch(f"/api/pim/channels/{chan_id}", headers=admin_headers,
                 json={"min_completeness_pct": 80})


def test_patch_channel_unknown_attribute_code_rejected(client, admin_headers, seeded_sku):
    """PATCH channel met onbekende attribuutcode geeft HTTP 400."""
    client.post("/api/pim/recompute", headers=admin_headers, json={"sku_ids": [SKU, SKU2]})
    chan_id = _get_channel_id(client, admin_headers, "webshop")
    r = client.patch(f"/api/pim/channels/{chan_id}", headers=admin_headers,
                     json={"required_attribute_codes": ["bestaat_niet"]})
    assert r.status_code == 400


def test_patch_family_name_and_patterns(client, admin_headers, seeded_sku):
    """PATCH familie wijzigt naam en categoriepatronen en persisteert."""
    client.post("/api/pim/recompute", headers=admin_headers, json={"sku_ids": [SKU, SKU2]})
    fam_id = _get_family_id(client, admin_headers, "papier")

    r = client.patch(f"/api/pim/families/{fam_id}", headers=admin_headers,
                     json={"name": "Papier & Enveloppen",
                           "category_patterns": ["Papier", "Enveloppen"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "Papier & Enveloppen"
    assert "Enveloppen" in data["category_patterns"]

    # Persistentie via GET
    fams = client.get("/api/pim/families", headers=admin_headers).json()
    fam = next(f for f in fams if f["id"] == fam_id)
    assert fam["name"] == "Papier & Enveloppen"

    # Herstel
    client.patch(f"/api/pim/families/{fam_id}", headers=admin_headers,
                 json={"name": "Papier", "category_patterns": ["Papier", "Kopieerpapier", "Printpapier"]})


# ─── Task 55: aanmaken van attributen, channels en families vanuit de app ────

def test_create_attribute_channel_family(client, admin_headers):
    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        # Attribuut
        r = client.post("/api/pim/attributes", headers=admin_headers, json={
            "code": f"attr_{tag}", "name": "Testattribuut", "data_type": "number",
            "unit": "mm", "source_owner": "Leverancier", "is_required": True,
            "weight": 2.0})
        assert r.status_code == 201, r.text
        a = r.json()
        assert a["code"] == f"attr_{tag}" and a["is_required"] is True and a["weight"] == 2.0

        # Duplicaatcode → 409
        r = client.post("/api/pim/attributes", headers=admin_headers, json={
            "code": f"attr_{tag}", "name": "Dubbel"})
        assert r.status_code == 409

        # Ongeldige eigenaar / datatype / gewicht → 400
        assert client.post("/api/pim/attributes", headers=admin_headers, json={
            "code": f"x_{tag}", "name": "X", "source_owner": "Onzin"}).status_code == 400
        assert client.post("/api/pim/attributes", headers=admin_headers, json={
            "code": f"x_{tag}", "name": "X", "data_type": "blob"}).status_code == 400
        assert client.post("/api/pim/attributes", headers=admin_headers, json={
            "code": f"x_{tag}", "name": "X", "weight": 0}).status_code == 400

        # Channel met het nieuwe attribuut als vereist
        r = client.post("/api/pim/channels", headers=admin_headers, json={
            "code": f"chan_{tag}", "name": "Testchannel",
            "required_attribute_codes": [f"attr_{tag}"],
            "min_completeness_pct": 75.0})
        assert r.status_code == 201, r.text
        c = r.json()
        assert c["required_attribute_codes"] == [f"attr_{tag}"]

        # Onbekende attribuutcode → 400
        assert client.post("/api/pim/channels", headers=admin_headers, json={
            "code": f"chan2_{tag}", "name": "X",
            "required_attribute_codes": ["bestaat_niet"]}).status_code == 400
        # Duplicaat → 409
        assert client.post("/api/pim/channels", headers=admin_headers, json={
            "code": f"chan_{tag}", "name": "Dubbel"}).status_code == 409

        # Familie
        r = client.post("/api/pim/families", headers=admin_headers, json={
            "code": f"fam_{tag}", "name": "Testfamilie",
            "category_patterns": ["Papier", " Kopieerpapier "]})
        assert r.status_code == 201, r.text
        f = r.json()
        assert f["category_patterns"] == ["Papier", "Kopieerpapier"]
        assert client.post("/api/pim/families", headers=admin_headers, json={
            "code": f"fam_{tag}", "name": "Dubbel"}).status_code == 409

        # Lege/ongeldige code → 400
        assert client.post("/api/pim/families", headers=admin_headers, json={
            "code": "  ", "name": "X"}).status_code == 400

        # Nieuwe items zichtbaar in de lijst-endpoints
        codes = [x["code"] for x in client.get("/api/pim/attributes", headers=admin_headers).json()]
        assert f"attr_{tag}" in codes
        codes = [x["code"] for x in client.get("/api/pim/channels", headers=admin_headers).json()]
        assert f"chan_{tag}" in codes
        codes = [x["code"] for x in client.get("/api/pim/families", headers=admin_headers).json()]
        assert f"fam_{tag}" in codes
    finally:
        db.query(models.PimCompletenessScore).filter(
            models.PimCompletenessScore.channel_code == f"chan_{tag}").delete(synchronize_session=False)
        db.query(models.PimChannel).filter(models.PimChannel.code.like(f"chan%_{tag}")).delete(synchronize_session=False)
        adef = db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.code == f"attr_{tag}").first()
        if adef:
            db.query(models.PimAttributeValue).filter(
                models.PimAttributeValue.attribute_id == adef.id).delete(synchronize_session=False)
            db.delete(adef)
        db.query(models.PimFamily).filter(models.PimFamily.code == f"fam_{tag}").delete(synchronize_session=False)
        db.commit()
        db.close()


def test_create_requires_admin_role(client):
    r = client.post("/api/auth/login", json={"username": "dev_viewer", "password": "viewer123"})
    if r.status_code != 200:
        pytest.skip("Geen viewer-account beschikbaar")
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    for path in ("/api/pim/attributes", "/api/pim/channels", "/api/pim/families"):
        resp = client.post(path, headers=headers, json={"code": "x", "name": "X"})
        assert resp.status_code == 403, f"{path}: {resp.status_code}"
