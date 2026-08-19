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
    from authz_helpers import grant_legacy_views
    grant_legacy_views(username)
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
        """NULL-callimiet valt per veld terug op globaal/env-standaard;
        de tokenlimiet uit de gebruikersrij geldt wél."""
        import ai_gateway
        db = SessionLocal()
        try:
            db.add(models.AiBudgetConfig(
                username=ctx["username"],
                max_calls_per_day=None, max_tokens_per_day=10_000,
            ))
            db.commit()
            glob = (db.query(models.AiBudgetConfig)
                    .filter(models.AiBudgetConfig.username.is_(None)).first())
            expected_calls = (
                glob.max_calls_per_day
                if glob is not None and glob.max_calls_per_day is not None
                else ai_gateway.DEFAULT_MAX_CALLS_PER_DAY)
        finally:
            db.close()
        try:
            r = client.get("/api/copilot/budget/me", headers=ctx["user"])
            assert r.status_code == 200, r.text
            body = r.json()
            # NULL betekent nooit 'onbeperkt': per veld terugval op de
            # globale rij, anders op de omgevingsstandaard.
            assert body["max_calls_per_day"] == expected_calls
            assert body["calls_pct"] is not None
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

    def test_exhausted_when_headroom_below_upfront_reservation(self, client, ctx):
        """Task #159: resterend tokensaldo kleiner dan de upfront-reservering
        betekent dat de volgende call server-side geweigerd wordt; het
        `exhausted`-veld moet dat dan al melden, ook al is tokens_reserved
        nog onder de limiet. Na een limietverhoging (polling) herstelt het."""
        import ai_gateway
        upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION
        # Slot uit eerdere test: 3000 gereserveerde tokens, 12 calls.
        db = SessionLocal()
        try:
            db.add(models.AiBudgetConfig(
                username=ctx["username"],
                max_calls_per_day=50,
                max_tokens_per_day=3_000 + upfront - 1,  # headroom < upfront
            ))
            db.commit()
        finally:
            db.close()
        try:
            r = client.get("/api/copilot/budget/me", headers=ctx["user"])
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["tokens_reserved"] == 3000
            assert body["tokens_reserved"] < body["max_tokens_per_day"]
            assert body["exhausted"] is True

            # Verhoogde limiet: dezelfde poll geeft het veld weer vrij.
            db = SessionLocal()
            try:
                cfg = db.query(models.AiBudgetConfig).filter(
                    models.AiBudgetConfig.username == ctx["username"]).one()
                cfg.max_tokens_per_day = 3_000 + upfront
                db.commit()
            finally:
                db.close()
            r = client.get("/api/copilot/budget/me", headers=ctx["user"])
            assert r.status_code == 200, r.text
            assert r.json()["exhausted"] is False
        finally:
            db = SessionLocal()
            try:
                db.query(models.AiBudgetConfig).filter(
                    models.AiBudgetConfig.username == ctx["username"]).delete()
                db.commit()
            finally:
                db.close()

    def test_exhausted_on_call_limit(self, client, ctx):
        """Calllimiet bereikt => exhausted, ongeacht tokenruimte."""
        db = SessionLocal()
        try:
            db.add(models.AiBudgetConfig(
                username=ctx["username"],
                max_calls_per_day=12, max_tokens_per_day=1_000_000,
            ))
            db.commit()
        finally:
            db.close()
        try:
            r = client.get("/api/copilot/budget/me", headers=ctx["user"])
            assert r.status_code == 200, r.text
            assert r.json()["exhausted"] is True
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
