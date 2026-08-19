"""
Tests voor het verwijderen van PIM-beheerentiteiten (taak: beheerders kunnen
attributen, channels en families ook weer verwijderen).

Dekt: verwijderen zonder gekoppelde data, weigering (409) bij gekoppelde
attribuutwaarden / completeness-scores / gekoppelde producten / channel-
referenties, en 404 voor onbekende id's.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models


TAG = uuid.uuid4().hex[:8]
SKU = f"PIMDEL-{TAG}"


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
def seeded_sku():
    db = SessionLocal()
    try:
        db.add(models.DimProduct(
            sku_id=SKU, product_name="Delete-test product",
            brand="TestMerk", category="Papier", current_price=1.99))
        db.commit()
        yield SKU
    finally:
        db.query(models.PimAttributeValue).filter(
            models.PimAttributeValue.sku_id == SKU).delete(synchronize_session=False)
        db.query(models.PimCompletenessScore).filter(
            models.PimCompletenessScore.sku_id == SKU).delete(synchronize_session=False)
        db.query(models.PimProductContent).filter(
            models.PimProductContent.sku_id == SKU).delete(synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU).delete(synchronize_session=False)
        db.commit()
        db.close()


def _mk_attribute(client, headers, code):
    r = client.post("/api/pim/attributes", headers=headers,
                    json={"code": code, "name": f"Attr {code}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_channel(client, headers, code, required=None):
    r = client.post("/api/pim/channels", headers=headers,
                    json={"code": code, "name": f"Chan {code}",
                          "required_attribute_codes": required or []})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_family(client, headers, code):
    r = client.post("/api/pim/families", headers=headers,
                    json={"code": code, "name": f"Fam {code}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_delete_unused_attribute_channel_family(client, admin_headers):
    aid = _mk_attribute(client, admin_headers, f"del_attr_{TAG}")
    cid = _mk_channel(client, admin_headers, f"del_chan_{TAG}")
    fid = _mk_family(client, admin_headers, f"del_fam_{TAG}")

    assert client.delete(f"/api/pim/attributes/{aid}", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/pim/channels/{cid}", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/pim/families/{fid}", headers=admin_headers).status_code == 200

    # Verdwenen uit de lijsten
    codes = {a["code"] for a in client.get("/api/pim/attributes", headers=admin_headers).json()}
    assert f"del_attr_{TAG}" not in codes


def test_delete_unknown_ids_404(client, admin_headers):
    assert client.delete("/api/pim/attributes/99999999", headers=admin_headers).status_code == 404
    assert client.delete("/api/pim/channels/99999999", headers=admin_headers).status_code == 404
    assert client.delete("/api/pim/families/99999999", headers=admin_headers).status_code == 404


def test_delete_attribute_with_values_refused(client, admin_headers, seeded_sku):
    aid = _mk_attribute(client, admin_headers, f"del_attr_val_{TAG}")
    db = SessionLocal()
    try:
        db.add(models.PimAttributeValue(
            sku_id=seeded_sku, attribute_id=aid, value="x", source="Handmatig"))
        db.commit()
        r = client.delete(f"/api/pim/attributes/{aid}", headers=admin_headers)
        assert r.status_code == 409
        assert "attribuutwaarde" in r.json()["detail"]
        # Na opruimen van de waarde lukt verwijderen wel
        db.query(models.PimAttributeValue).filter(
            models.PimAttributeValue.attribute_id == aid).delete(synchronize_session=False)
        db.commit()
        assert client.delete(f"/api/pim/attributes/{aid}", headers=admin_headers).status_code == 200
    finally:
        db.query(models.PimAttributeValue).filter(
            models.PimAttributeValue.attribute_id == aid).delete(synchronize_session=False)
        db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.id == aid).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_delete_attribute_required_by_channel_refused(client, admin_headers):
    code = f"del_attr_req_{TAG}"
    aid = _mk_attribute(client, admin_headers, code)
    cid = _mk_channel(client, admin_headers, f"del_chan_req_{TAG}", required=[code])
    try:
        r = client.delete(f"/api/pim/attributes/{aid}", headers=admin_headers)
        assert r.status_code == 409
        assert f"del_chan_req_{TAG}" in r.json()["detail"]
    finally:
        client.delete(f"/api/pim/channels/{cid}", headers=admin_headers)
        client.delete(f"/api/pim/attributes/{aid}", headers=admin_headers)


def test_delete_channel_with_scores_refused(client, admin_headers, seeded_sku):
    code = f"del_chan_sc_{TAG}"
    cid = _mk_channel(client, admin_headers, code)
    db = SessionLocal()
    try:
        db.add(models.PimCompletenessScore(
            sku_id=seeded_sku, channel_code=code, completeness_pct=50.0,
            run_date=date.today()))
        db.commit()
        r = client.delete(f"/api/pim/channels/{cid}", headers=admin_headers)
        assert r.status_code == 409
        assert "completeness-score" in r.json()["detail"]
        db.query(models.PimCompletenessScore).filter(
            models.PimCompletenessScore.channel_code == code).delete(synchronize_session=False)
        db.commit()
        assert client.delete(f"/api/pim/channels/{cid}", headers=admin_headers).status_code == 200
    finally:
        db.query(models.PimCompletenessScore).filter(
            models.PimCompletenessScore.channel_code == code).delete(synchronize_session=False)
        db.query(models.PimChannel).filter(
            models.PimChannel.id == cid).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_delete_family_with_products_refused(client, admin_headers, seeded_sku):
    fid = _mk_family(client, admin_headers, f"del_fam_prod_{TAG}")
    db = SessionLocal()
    try:
        db.add(models.PimProductContent(sku_id=seeded_sku, family_id=fid))
        db.commit()
        r = client.delete(f"/api/pim/families/{fid}", headers=admin_headers)
        assert r.status_code == 409
        assert "product" in r.json()["detail"]
        db.query(models.PimProductContent).filter(
            models.PimProductContent.family_id == fid).delete(synchronize_session=False)
        db.commit()
        assert client.delete(f"/api/pim/families/{fid}", headers=admin_headers).status_code == 200
    finally:
        db.query(models.PimProductContent).filter(
            models.PimProductContent.family_id == fid).delete(synchronize_session=False)
        db.query(models.PimFamily).filter(
            models.PimFamily.id == fid).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_defaults_not_reseeded_after_deleting_final_record(tmp_path):
    """
    Regressie: als een beheerder bewust het laatste attribuut/channel/familie
    verwijdert, mag ensure_defaults() bij de volgende lijst-refresh de
    defaults NIET opnieuw seeden (marker in audit_log = eenmalige seed).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base
    from engine import pim_engine

    engine = create_engine(f"sqlite:///{tmp_path}/pimdel.db")
    # Alleen de benodigde tabellen aanmaken: het volledige schema bevat
    # Postgres-specifieke kolommen (bijv. de TSVECTOR generated column op
    # ai_feedback) die sqlite niet kan renderen.
    needed = [models.PimAttributeDefinition.__table__,
              models.PimAttributeValue.__table__,
              models.PimChannel.__table__,
              models.PimFamily.__table__,
              models.PimProductContent.__table__,
              models.AuditLog.__table__]
    Base.metadata.create_all(engine, tables=needed)
    TestSession = sessionmaker(bind=engine)

    orig_flag = pim_engine._defaults_seeded
    pim_engine._defaults_seeded = False
    db = TestSession()
    try:
        # Eerste aanroep op lege DB: defaults worden geseed + marker gezet
        pim_engine.ensure_defaults(db)
        assert db.query(models.PimAttributeDefinition).count() > 0
        assert db.query(models.PimChannel).count() > 0
        assert db.query(models.PimFamily).count() > 0

        # Beheerder verwijdert alles (zoals via de DELETE-endpoints)
        db.query(models.PimAttributeValue).delete()
        db.query(models.PimAttributeDefinition).delete()
        db.query(models.PimChannel).delete()
        db.query(models.PimFamily).delete()
        db.commit()

        # Lijst-refresh (roept ensure_defaults aan) mag niets terugzetten,
        # ook niet in een vers proces (flag reset simuleert herstart).
        pim_engine._defaults_seeded = False
        pim_engine.ensure_defaults(db)
        assert db.query(models.PimAttributeDefinition).count() == 0
        assert db.query(models.PimChannel).count() == 0
        assert db.query(models.PimFamily).count() == 0
    finally:
        db.close()
        pim_engine._defaults_seeded = orig_flag

def test_deleted_record_stays_gone_after_list_refresh(client, admin_headers):
    """Na DELETE + GET-refresh komt het verwijderde record niet terug."""
    code = f"del_attr_refresh_{TAG}"
    aid = _mk_attribute(client, admin_headers, code)
    assert client.delete(f"/api/pim/attributes/{aid}", headers=admin_headers).status_code == 200
    for _ in range(2):
        codes = {a["code"] for a in client.get("/api/pim/attributes", headers=admin_headers).json()}
        assert code not in codes


def test_delete_requires_admin_role(client, admin_headers):
    aid = _mk_attribute(client, admin_headers, f"del_attr_role_{TAG}")
    try:
        r = client.post("/api/auth/login",
                        json={"username": "dev_viewer", "password": "viewer123"})
        if r.status_code != 200:
            pytest.skip("Geen viewer-account beschikbaar in deze omgeving")
        viewer_headers = {"Authorization": f"Bearer {r.json()['token']}"}
        assert client.delete(f"/api/pim/attributes/{aid}",
                             headers=viewer_headers).status_code == 403
    finally:
        client.delete(f"/api/pim/attributes/{aid}", headers=admin_headers)
