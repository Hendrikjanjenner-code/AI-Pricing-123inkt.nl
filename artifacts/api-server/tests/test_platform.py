"""
Regressietests voor het metering-/platform-fundament (taak 15):
- record_usage gebruikt de bewerkbare tarieven uit platform_assumptions
- actor (username/shop) wordt in API-metering gepropageerd
- marge-uplift van verwerkte adviezen is ESTIMATED (niet REALIZED)
- platformdata is beperkt tot bevoegde rollen
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
from services import metering

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}


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


def test_record_usage_uses_db_rates(client, admin_headers):
    """Een gewijzigd tarief in platform_assumptions verandert de gemeten kosten."""
    # Zorg dat aannames geseed zijn
    resp = client.get("/api/platform/assumptions", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    orig = next(a["value"] for a in resp.json() if a["key"] == "rate_api_request_eur")
    try:
        resp = client.put("/api/platform/assumptions/rate_api_request_eur",
                          json={"value": 0.5}, headers=admin_headers)
        assert resp.status_code == 200, resp.text
        # cache is geïnvalideerd door de PUT
        assert metering.current_rates()["rate_api_request_eur"] == 0.5
        cost = metering.estimate_cost_eur("api_request", rates=metering.current_rates())
        assert cost == 0.5
    finally:
        client.put("/api/platform/assumptions/rate_api_request_eur",
                   json={"value": orig}, headers=admin_headers)
        metering.invalidate_rates_cache()


def test_api_metering_propagates_actor(client, admin_headers):
    """Middleware-records bevatten de ingelogde gebruiker en shop uit X-Shop-ID."""
    db = SessionLocal()
    try:
        shop_id = db.query(models.DimShop.id).order_by(models.DimShop.id).first()[0]
    finally:
        db.close()
    resp = client.get("/api/platform/assumptions",
                      headers={**admin_headers, "X-Shop-ID": str(shop_id)})
    assert resp.status_code == 200
    metering.flush_usage_buffer()
    db = SessionLocal()
    try:
        row = db.query(models.CostUsageRecord).filter(
            models.CostUsageRecord.usage_type == "api_request",
            models.CostUsageRecord.endpoint == "/api/platform/assumptions",
        ).order_by(models.CostUsageRecord.id.desc()).first()
        assert row is not None
        assert row.username == "dev_admin"
        assert row.shop_id == shop_id
    finally:
        db.close()


def test_margin_uplift_labeled_estimated(client, admin_headers):
    """Verwachte marge-uplift van verwerkte adviezen mag nooit REALIZED heten."""
    resp = client.get("/api/platform/business-value/summary", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    metingen = {m["metric_key"]: m for m in resp.json()["automatische_metingen"]}
    assert metingen["marge_uplift_verwerkt"]["value_label"] == "ESTIMATED"
    # De telling van doorgevoerde wijzigingen mag wél REALIZED zijn
    assert metingen["adviezen_verwerkt"]["value_label"] == "REALIZED"


def test_platform_data_requires_privileged_role(client, admin_headers):
    """Viewer-rol heeft geen toegang tot health/usage/foutdrill-down."""
    uname = f"viewer_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/users", json={
        "username": uname, "password": "Testwachtwoord1!",
        "email": f"{uname}@test.local", "role": "viewer",
    }, headers=admin_headers)
    assert resp.status_code in (200, 201), resp.text
    login = client.post("/api/auth/login",
                        json={"username": uname, "password": "Testwachtwoord1!"})
    assert login.status_code == 200, login.text
    viewer_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    try:
        for path in ("/api/platform/health", "/api/platform/health/errors",
                     "/api/platform/usage", "/api/platform/costs/scenarios",
                     "/api/platform/business-value/summary"):
            r = client.get(path, headers=viewer_headers)
            assert r.status_code == 403, f"{path}: {r.status_code}"
        # Admin behoudt toegang
        assert client.get("/api/platform/health", headers=admin_headers).status_code == 200
    finally:
        db = SessionLocal()
        try:
            db.query(models.User).filter(models.User.username == uname).delete()
            db.commit()
        finally:
            db.close()
