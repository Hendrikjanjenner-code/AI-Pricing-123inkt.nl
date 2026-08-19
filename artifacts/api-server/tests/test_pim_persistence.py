"""
Tests dat PATCH-wijzigingen op PIM-referentiedata (attributen, channels,
families) correct persisteren én dat ensure_defaults() bestaande rijen
ongemoeid laat — zodat wijzigingen een herstart overleven (taak 56).

Elke test is zelfstandig uitvoerbaar: de PATCH-mutaties gebeuren in een
module-fixture, dus ook onder gerandomiseerde volgorde of losse selectie
gelden de restart-asserties.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from engine import pim_engine

TAG = uuid.uuid4().hex[:8]
ATTR_CODE = f"perstest_attr_{TAG}"
CHAN_CODE = f"perstest_chan_{TAG}"
FAM_CODE = f"perstest_fam_{TAG}"


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


@pytest.fixture(scope="module")
def seeded_refs(client):
    """Maak dedicated testrijen aan zodat we geen default-referentiedata muteren."""
    db = SessionLocal()
    try:
        # Zorg dat de defaults al geseed zijn vóór onze testrijen bestaan
        pim_engine.ensure_defaults(db)
        attr = models.PimAttributeDefinition(
            code=ATTR_CODE, name="Persistentietest attribuut", data_type="text",
            source_owner="Handmatig", is_required=False, weight=1.0)
        chan = models.PimChannel(
            code=CHAN_CODE, name="Persistentietest channel",
            required_attribute_codes=[], min_completeness_pct=50.0)
        fam = models.PimFamily(
            code=FAM_CODE, name="Persistentietest familie", category_patterns=["Test"])
        db.add_all([attr, chan, fam])
        db.commit()
        db.refresh(attr); db.refresh(chan); db.refresh(fam)
        yield {"attr_id": attr.id, "chan_id": chan.id, "fam_id": fam.id}
    finally:
        db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.code == ATTR_CODE).delete(synchronize_session=False)
        db.query(models.PimChannel).filter(
            models.PimChannel.code == CHAN_CODE).delete(synchronize_session=False)
        db.query(models.PimFamily).filter(
            models.PimFamily.code == FAM_CODE).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.fixture(scope="module")
def patched_refs(client, admin_headers, seeded_refs):
    """Voer de drie PATCHes uit; elke test die dit gebruikt is zelfstandig."""
    r = client.patch(f"/api/pim/attributes/{seeded_refs['attr_id']}", headers=admin_headers,
                     json={"name": "Aangepast attribuut", "is_required": True,
                           "weight": 2.5, "source_owner": "Leverancier"})
    assert r.status_code == 200, r.text
    attr_resp = r.json()

    r = client.patch(f"/api/pim/channels/{seeded_refs['chan_id']}", headers=admin_headers,
                     json={"required_attribute_codes": ["brand"],
                           "min_completeness_pct": 77.0, "name": "Kanaal aangepast"})
    assert r.status_code == 200, r.text
    chan_resp = r.json()

    r = client.patch(f"/api/pim/families/{seeded_refs['fam_id']}", headers=admin_headers,
                     json={"name": "Familie aangepast",
                           "category_patterns": ["Papier", " Opbergen "],
                           "active": False})
    assert r.status_code == 200, r.text
    fam_resp = r.json()

    return {**seeded_refs, "attr_resp": attr_resp, "chan_resp": chan_resp,
            "fam_resp": fam_resp}


# ─── PATCH persisteert ──────────────────────────────────────────────────────

def test_patch_attribute_persists(patched_refs):
    body = patched_refs["attr_resp"]
    assert body["is_required"] is True
    assert body["weight"] == 2.5
    assert body["source_owner"] == "Leverancier"

    # Verifieer via een verse sessie (geen request-cache)
    db = SessionLocal()
    try:
        d = db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.id == patched_refs["attr_id"]).one()
        assert d.name == "Aangepast attribuut"
        assert d.is_required is True
        assert d.weight == 2.5
        assert d.source_owner == "Leverancier"
    finally:
        db.close()


def test_patch_channel_persists(patched_refs):
    assert patched_refs["chan_resp"]["required_attribute_codes"] == ["brand"]

    db = SessionLocal()
    try:
        c = db.query(models.PimChannel).filter(
            models.PimChannel.id == patched_refs["chan_id"]).one()
        assert c.required_attribute_codes == ["brand"]
        assert c.min_completeness_pct == 77.0
        assert c.name == "Kanaal aangepast"
    finally:
        db.close()


def test_patch_family_persists(patched_refs):
    assert patched_refs["fam_resp"]["category_patterns"] == ["Papier", "Opbergen"]

    db = SessionLocal()
    try:
        f = db.query(models.PimFamily).filter(
            models.PimFamily.id == patched_refs["fam_id"]).one()
        assert f.name == "Familie aangepast"
        assert f.category_patterns == ["Papier", "Opbergen"]
        assert f.active is False
    finally:
        db.close()


def test_patch_validation_errors(client, admin_headers, seeded_refs):
    aid = seeded_refs["attr_id"]
    assert client.patch(f"/api/pim/attributes/{aid}", headers=admin_headers,
                        json={"weight": -1}).status_code == 400
    assert client.patch(f"/api/pim/attributes/{aid}", headers=admin_headers,
                        json={"source_owner": "Onzin"}).status_code == 400
    cid = seeded_refs["chan_id"]
    assert client.patch(f"/api/pim/channels/{cid}", headers=admin_headers,
                        json={"required_attribute_codes": ["bestaat_niet_xyz"]}).status_code == 400
    assert client.patch(f"/api/pim/channels/{cid}", headers=admin_headers,
                        json={"min_completeness_pct": 150}).status_code == 400
    assert client.patch("/api/pim/attributes/999999999", headers=admin_headers,
                        json={"name": "x"}).status_code == 404


# ─── ensure_defaults laat bestaande rijen ongemoeid ─────────────────────────

def test_ensure_defaults_preserves_existing_rows(patched_refs):
    """Simuleer een herstart: ensure_defaults() mag gepatchte rijen niet
    overschrijven of resetten naar de seed-waarden."""
    db = SessionLocal()
    try:
        before_attrs = db.query(models.PimAttributeDefinition).count()
        before_chans = db.query(models.PimChannel).count()
        before_fams = db.query(models.PimFamily).count()

        pim_engine.ensure_defaults(db)

        assert db.query(models.PimAttributeDefinition).count() == before_attrs
        assert db.query(models.PimChannel).count() == before_chans
        assert db.query(models.PimFamily).count() == before_fams

        # De eerder gepatchte waarden staan er nog exact zo in
        d = db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.id == patched_refs["attr_id"]).one()
        assert d.name == "Aangepast attribuut"
        assert d.is_required is True and d.weight == 2.5
        assert d.source_owner == "Leverancier"

        c = db.query(models.PimChannel).filter(
            models.PimChannel.id == patched_refs["chan_id"]).one()
        assert c.required_attribute_codes == ["brand"] and c.min_completeness_pct == 77.0

        f = db.query(models.PimFamily).filter(
            models.PimFamily.id == patched_refs["fam_id"]).one()
        assert f.name == "Familie aangepast" and f.active is False
    finally:
        db.close()


def test_ensure_defaults_survives_endpoint_calls(client, admin_headers, patched_refs):
    """De list-endpoints roepen ensure_defaults() zelf aan; ook dat pad mag
    gepatchte rijen niet resetten."""
    r = client.get("/api/pim/attributes", headers=admin_headers)
    assert r.status_code == 200
    a = {x["id"]: x for x in r.json()}[patched_refs["attr_id"]]
    assert a["name"] == "Aangepast attribuut" and a["is_required"] is True

    r = client.get("/api/pim/channels", headers=admin_headers)
    assert r.status_code == 200
    c = {x["id"]: x for x in r.json()}[patched_refs["chan_id"]]
    assert c["required_attribute_codes"] == ["brand"]
    assert c["min_completeness_pct"] == 77.0

    r = client.get("/api/pim/families", headers=admin_headers)
    assert r.status_code == 200
    f = {x["id"]: x for x in r.json()}[patched_refs["fam_id"]]
    assert f["name"] == "Familie aangepast" and f["active"] is False
