"""
Integratietests voor het fundament (taak: canonical model, signals, semantic
layer, RBAC). Draait tegen de dev-database via de FastAPI TestClient; alle
aangemaakte testdata wordt na afloop opgeruimd.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}


@pytest.fixture(scope="module")
def client():
    # Context manager draait de volledige lifespan (migraties, default shop,
    # backfill, seed users) — precies wat we willen testen.
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        c.__exit__(None, None, None)
    except Exception:
        # App-shutdown kan een achtergrondtaak annuleren (CancelledError);
        # dat is geen testfout.
        pass


@pytest.fixture(scope="module")
def admin_headers(client):
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def test_shop(client, admin_headers):
    code = f"test-{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/shops", json={"shop_code": code, "name": "Testshop B"},
                       headers=admin_headers)
    assert resp.status_code == 201, resp.text
    shop = resp.json()
    yield shop
    db = SessionLocal()
    try:
        db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.shop_id == shop["id"]).delete()
        db.query(models.DimShop).filter(models.DimShop.id == shop["id"]).delete()
        db.commit()
    finally:
        db.close()


def _cleanup_signals(entity_id):
    db = SessionLocal()
    try:
        db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.entity_id == entity_id).delete()
        db.commit()
    finally:
        db.close()


def test_default_shop_exists_and_backfill_complete(client, admin_headers):
    resp = client.get("/api/shops", headers=admin_headers)
    assert resp.status_code == 200
    shops = resp.json()["shops"]
    defaults = [s for s in shops if s["is_default"]]
    assert len(defaults) == 1, "er moet precies één default shop zijn"

    db = SessionLocal()
    try:
        assert db.query(models.DimProduct).filter(
            models.DimProduct.shop_id.is_(None)).count() == 0
        assert db.query(models.FactSalesDaily).filter(
            models.FactSalesDaily.shop_id.is_(None)).count() == 0
    finally:
        db.close()


def test_signal_without_evidence_rejected(client, admin_headers):
    base = {"engine": "test", "signal_type": "t", "entity_type": "sku",
            "entity_id": "PYTEST-EV", "explanation": "test"}
    # evidence/sources ontbreken volledig -> validatiefout (de app mapt
    # RequestValidationError naar 400 via een custom handler)
    resp = client.post("/api/signals", json=base, headers=admin_headers)
    assert resp.status_code in (400, 422)
    # leeg evidence -> 400
    resp = client.post("/api/signals", json={**base, "evidence": {}, "sources": ["x"]},
                       headers=admin_headers)
    assert resp.status_code == 400
    # lege sources -> 400
    resp = client.post("/api/signals", json={**base, "evidence": {"a": 1}, "sources": []},
                       headers=admin_headers)
    assert resp.status_code == 400


def test_signal_invalid_metric_rejected(client, admin_headers):
    resp = client.post("/api/signals", json={
        "engine": "test", "signal_type": "t", "entity_type": "sku",
        "entity_id": "PYTEST-METRIC", "explanation": "test",
        "evidence": {"a": 1}, "sources": ["tabel"], "metric": "bestaat_niet",
    }, headers=admin_headers)
    assert resp.status_code == 400


def test_signal_dedupe_supersedes_previous(client, admin_headers):
    entity = f"PYTEST-DEDUPE-{uuid.uuid4().hex[:6]}"
    try:
        body = {"engine": "test", "signal_type": "dup", "entity_type": "sku",
                "entity_id": entity, "explanation": "eerste",
                "evidence": {"v": 1}, "sources": ["tabel"]}
        r1 = client.post("/api/signals", json=body, headers=admin_headers)
        assert r1.status_code == 201
        r2 = client.post("/api/signals", json={**body, "explanation": "tweede"},
                         headers=admin_headers)
        assert r2.status_code == 201

        resp = client.get(f"/api/signals?status=all&entity_id={entity}",
                          headers=admin_headers)
        statuses = sorted(s["status"] for s in resp.json()["signals"])
        assert statuses == ["active", "superseded"]
    finally:
        _cleanup_signals(entity)


def test_signal_shop_isolation(client, admin_headers, test_shop):
    entity = f"PYTEST-ISO-{uuid.uuid4().hex[:6]}"
    try:
        r = client.post("/api/signals", json={
            "engine": "test", "signal_type": "iso", "entity_type": "sku",
            "entity_id": entity, "explanation": "shop B signaal",
            "evidence": {"v": 1}, "sources": ["tabel"], "shop_id": test_shop["id"],
        }, headers=admin_headers)
        assert r.status_code == 201

        # Default shop-lijst mag dit signaal niet bevatten
        resp = client.get(f"/api/signals?entity_id={entity}", headers=admin_headers)
        assert resp.json()["total"] == 0
        # Shop B-lijst wel
        resp = client.get(f"/api/signals?entity_id={entity}&shop_id={test_shop['id']}",
                          headers=admin_headers)
        assert resp.json()["total"] == 1
    finally:
        _cleanup_signals(entity)


def test_viewer_cannot_publish_signal_or_read_audit_log(client):
    resp = client.post("/api/auth/login",
                       json={"username": "viewer", "password": "viewer123"})
    if resp.status_code != 200:
        pytest.skip("viewer demo-account niet beschikbaar")
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    r = client.post("/api/signals", json={
        "engine": "test", "signal_type": "t", "entity_type": "sku",
        "entity_id": "PYTEST-VIEWER", "explanation": "x",
        "evidence": {"a": 1}, "sources": ["t"],
    }, headers=headers)
    assert r.status_code == 403
    assert client.get("/api/audit-log", headers=headers).status_code == 403


def test_invalid_role_rejected(client, admin_headers):
    r = client.post("/api/users", json={
        "username": f"pytest-{uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:6]}@t.nl",
        "password": "x-Secret123", "role": "superuser",
    }, headers=admin_headers)
    assert r.status_code == 400
