"""
Tests voor de nachtelijke-engine-runstatus (taak 50): EngineRun-logging en
GET /api/engine-runs/status. Draait tegen de dev-database via TestClient;
alle testdata wordt na afloop opgeruimd.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
PFX = f"T50-{uuid.uuid4().hex[:6]}"


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
def headers(client):
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    shop_ids = [r.id for r in s.query(models.DimShop.id).filter(
        models.DimShop.shop_code.like(f"{PFX}%")).all()]
    if shop_ids:
        s.query(models.EngineRun).filter(models.EngineRun.shop_id.in_(shop_ids)).delete(
            synchronize_session=False)
        s.query(models.DimShop).filter(models.DimShop.id.in_(shop_ids)).delete(
            synchronize_session=False)
    s.commit()
    s.close()


def _make_shop(db, suffix, active=True):
    shop = models.DimShop(shop_code=f"{PFX}-{suffix}", name=f"{PFX} {suffix}", active=active)
    db.add(shop)
    db.commit()
    return shop


def _seed(db, engine_name, shop_id, status, started_at, error=None):
    db.add(models.EngineRun(
        engine_name=engine_name, shop_id=shop_id, started_at=started_at,
        completed_at=started_at, status=status, error_message=error,
    ))
    db.commit()


def _engine(payload, name):
    return next(e for e in payload["engines"] if e["engine"] == name)


def _shop_entry(engine_payload, shop_id):
    return next(s for s in engine_payload["shops"] if s["shop_id"] == shop_id)


def test_requires_auth(client):
    assert client.get("/api/engine-runs/status").status_code in (401, 403)


def test_all_four_engines_reported(client, headers):
    resp = client.get("/api/engine-runs/status", headers=headers)
    assert resp.status_code == 200, resp.text
    names = [e["engine"] for e in resp.json()["engines"]]
    assert names == ["basket", "promotion", "forecast", "opportunity"]


def test_success_failed_stale_per_shop(client, headers, db):
    now = datetime.utcnow()
    shop = _make_shop(db, "a")
    _seed(db, "basket", shop.id, "success", now - timedelta(hours=1))
    _seed(db, "promotion", shop.id, "failed", now - timedelta(hours=1), error="boom")
    _seed(db, "forecast", shop.id, "success", now - timedelta(hours=48))

    payload = client.get("/api/engine-runs/status", headers=headers).json()

    assert _shop_entry(_engine(payload, "basket"), shop.id)["status"] == "success"

    promo = _engine(payload, "promotion")
    assert promo["status"] == "failed"
    entry = _shop_entry(promo, shop.id)
    assert entry["status"] == "failed"
    assert entry["error_message"] == "boom"

    # Succesvolle run ouder dan 26u is verouderd — ook als andere shops recenter zijn.
    forecast = _engine(payload, "forecast")
    assert _shop_entry(forecast, shop.id)["status"] == "stale"
    assert forecast["status"] in ("stale", "failed", "missing")

    # Opportunity heeft voor deze shop nooit gedraaid → missing.
    opp = _engine(payload, "opportunity")
    assert _shop_entry(opp, shop.id)["status"] == "missing"
    assert opp["status"] in ("missing", "failed")

    assert payload["overall"] == "warning"


def test_recent_shop_does_not_mask_stale_or_missing_shop(client, headers, db):
    """Regressie: een recente run voor shop A mag shop B niet maskeren."""
    now = datetime.utcnow()
    shop_a = _make_shop(db, "recent")
    shop_b = _make_shop(db, "stale")
    shop_c = _make_shop(db, "never")
    _seed(db, "basket", shop_a.id, "success", now - timedelta(hours=1))
    _seed(db, "basket", shop_b.id, "success", now - timedelta(hours=48))
    # shop_c: geen enkele run

    payload = client.get("/api/engine-runs/status", headers=headers).json()
    basket = _engine(payload, "basket")
    assert _shop_entry(basket, shop_a.id)["status"] == "success"
    assert _shop_entry(basket, shop_b.id)["status"] == "stale"
    assert _shop_entry(basket, shop_c.id)["status"] == "missing"
    assert basket["status"] != "success"
    assert payload["overall"] == "warning"


def test_failed_then_success_recovers(client, headers, db):
    now = datetime.utcnow()
    shop = _make_shop(db, "recover")
    _seed(db, "basket", shop.id, "failed", now - timedelta(hours=25), error="oud")
    _seed(db, "basket", shop.id, "success", now - timedelta(hours=1))

    payload = client.get("/api/engine-runs/status", headers=headers).json()
    # Alleen de laatste run per shop telt.
    assert _shop_entry(_engine(payload, "basket"), shop.id)["status"] == "success"


def test_inactive_shop_is_ignored(client, headers, db):
    shop = _make_shop(db, "inactive", active=False)
    payload = client.get("/api/engine-runs/status", headers=headers).json()
    for e in payload["engines"]:
        assert all(s["shop_id"] != shop.id for s in e["shops"])


def test_run_engine_logs_success_and_failure(db):
    from scheduled_engines import _run_engine

    shop = _make_shop(db, "runlog")

    def ok_engine(session, run_date, shop_id):
        return {"rows": 5}

    def broken_engine(session, run_date, shop_id):
        raise RuntimeError("kapot")

    assert _run_engine("basket", ok_engine, db, shop.id) is True
    assert _run_engine("basket", broken_engine, db, shop.id) is False

    rows = (db.query(models.EngineRun)
            .filter(models.EngineRun.shop_id == shop.id,
                    models.EngineRun.engine_name == "basket")
            .order_by(models.EngineRun.started_at).all())
    assert [r.status for r in rows] == ["success", "failed"]
    assert rows[0].result_summary == {"rows": 5}
    assert "kapot" in rows[1].error_message
