"""
Eigen budgetverbruik in het Copilot-scherm (Task #121):
GET /api/copilot/budget/me geeft voor de ingelogde gebruiker het
dagverbruik (calls/tokens) versus de effectieve limiet terug.
"""
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

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
def ctx(client):
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    admin_headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    suffix = uuid.uuid4().hex[:8]
    username = f"budgetme_{suffix}"
    password = f"Pw!{uuid.uuid4().hex[:12]}"
    r = client.post("/api/users", headers=admin_headers, json={
        "username": username, "email": f"{username}@test.local",
        "full_name": "Budget Me", "password": password, "role": "viewer",
    })
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["id"]
    lr = client.post("/api/auth/login", json={"username": username, "password": password})
    assert lr.status_code == 200, lr.text
    user_headers = {"Authorization": f"Bearer {lr.json()['token']}"}

    yield {"admin": admin_headers, "user": user_headers, "username": username}

    db = SessionLocal()
    try:
        db.query(models.AiBudgetSlot).filter(
            models.AiBudgetSlot.username == username).delete()
        db.query(models.AiModelCall).filter(
            models.AiModelCall.username == username).delete()
        db.query(models.CostUsageEvent).filter(
            models.CostUsageEvent.username == username).delete() \
            if hasattr(models, "CostUsageEvent") else None
        db.query(models.User).filter(models.User.id == user_id).delete()
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


class TestBudgetMe:
    def test_requires_auth(self, client):
        r = client.get("/api/copilot/budget/me")
        assert r.status_code in (401, 403)

    def test_zero_usage_without_slot(self, client, ctx):
        r = client.get("/api/copilot/budget/me", headers=ctx["user"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["date"] == date.today().isoformat()
        assert body["calls_used"] == 0
        assert body["tokens_used"] == 0
        assert body["max_calls_per_day"] is not None

    def test_reflects_existing_slot(self, client, ctx):
        db = SessionLocal()
        try:
            db.add(models.AiBudgetSlot(
                username=ctx["username"], slot_date=date.today(),
                calls_reserved=12, tokens_reserved=3000, tokens_actual=2500,
            ))
            db.commit()
        finally:
            db.close()

        r = client.get("/api/copilot/budget/me", headers=ctx["user"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["calls_used"] == 12
        assert body["tokens_used"] == 2500
        assert body["tokens_reserved"] == 3000
        if body["max_calls_per_day"]:
            assert body["calls_pct"] == round(12 / body["max_calls_per_day"] * 100, 1)

    def test_token_only_limit(self, client, ctx):
        """Ongelimiteerde calls maar wél een tokenlimiet: pct's kloppen."""
        db = SessionLocal()
        try:
            db.add(models.AiBudgetConfig(
                username=ctx["username"],
                max_calls_per_day=None, max_tokens_per_day=10_000,
            ))
            db.commit()
        finally:
            db.close()
        try:
            r = client.get("/api/copilot/budget/me", headers=ctx["user"])
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["max_calls_per_day"] is None
            assert body["calls_pct"] is None
            assert body["max_tokens_per_day"] == 10_000
            # Slot uit vorige test: 3000 gereserveerde tokens
            assert body["tokens_pct"] == 30.0
        finally:
            db = SessionLocal()
            try:
                db.query(models.AiBudgetConfig).filter(
                    models.AiBudgetConfig.username == ctx["username"]).delete()
                db.commit()
            finally:
                db.close()

    def test_token_limit_reached_before_call_limit(self, client, ctx):
        """Tokenlimiet eerder bereikt dan calllimiet: tokens_pct >= 100."""
        db = SessionLocal()
        try:
            db.add(models.AiBudgetConfig(
                username=ctx["username"],
                max_calls_per_day=50, max_tokens_per_day=2_000,
            ))
            db.commit()
        finally:
            db.close()
        try:
            r = client.get("/api/copilot/budget/me", headers=ctx["user"])
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["calls_pct"] == 24.0  # 12/50
            assert body["tokens_pct"] == 150.0  # 3000/2000
        finally:
            db = SessionLocal()
            try:
                db.query(models.AiBudgetConfig).filter(
                    models.AiBudgetConfig.username == ctx["username"]).delete()
                db.commit()
            finally:
                db.close()
