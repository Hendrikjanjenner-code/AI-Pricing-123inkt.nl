"""
Tests voor in-app meldingen (taak: DQ-alerts ook in de app tonen).

Dekt:
1. _create_inapp_notifications maakt meldingen aan voor de eigenaar,
   of voor alle actieve admins zonder (actieve) eigenaar.
2. GET /api/notifications geeft alleen eigen meldingen + unread_count.
3. Per-melding en alles-gelezen markeren.
"""
import os
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal, engine, Base
import models

# Zorg dat de notificatietabel bestaat, ook als de app-lifespan (create_all)
# nog niet gedraaid heeft — de eerste drie tests gebruiken de DB direct.
Base.metadata.create_all(bind=engine)
from services.data_quality_scan_scheduler import _create_inapp_notifications

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
PFX = f"NOTIF-{uuid.uuid4().hex[:8]}"


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
def auth(client):
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


def _cleanup(db):
    db.query(models.InAppNotification).filter(
        models.InAppNotification.reference.like(f"{PFX}%")
    ).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.username.like(f"{PFX}%")).delete(
        synchronize_session=False
    )
    db.commit()


def _fake_issue(code, owner=None):
    return SimpleNamespace(
        issue_code=code,
        title=f"Testissue {code}",
        message="testmelding",
        business_impact=None,
        severity="warning",
        owner=owner,
    )


def test_notify_owner_gets_notification(db):
    try:
        owner = models.User(
            username=f"{PFX}-owner",
            email=f"{PFX}-owner@example.com",
            hashed_password="x",
            role="analyst",
            is_active=True,
        )
        db.add(owner)
        db.commit()

        n = _create_inapp_notifications(db, _fake_issue(f"{PFX}-A", owner=owner.username), "new")
        assert n == 1

        rows = db.query(models.InAppNotification).filter(
            models.InAppNotification.reference == f"{PFX}-A"
        ).all()
        assert len(rows) == 1
        assert rows[0].username == owner.username
        assert rows[0].is_read is False
        assert rows[0].kind == "new"
        assert "NIEUW" in rows[0].title.upper()
    finally:
        _cleanup(db)


def test_notify_without_owner_goes_to_admins(db):
    try:
        n = _create_inapp_notifications(db, _fake_issue(f"{PFX}-B", owner=None), "reopened")
        admin_count = (
            db.query(models.User)
            .filter(models.User.role == "admin", models.User.is_active == True)  # noqa: E712
            .count()
        )
        assert n == admin_count >= 1

        rows = db.query(models.InAppNotification).filter(
            models.InAppNotification.reference == f"{PFX}-B"
        ).all()
        usernames = {r.username for r in rows}
        assert len(rows) == admin_count
        assert "dev_admin" in usernames
        assert all(r.kind == "reopened" for r in rows)
    finally:
        _cleanup(db)


def test_inactive_owner_falls_back_to_admins(db):
    try:
        owner = models.User(
            username=f"{PFX}-inactive",
            email=f"{PFX}-inactive@example.com",
            hashed_password="x",
            role="analyst",
            is_active=False,
        )
        db.add(owner)
        db.commit()

        _create_inapp_notifications(db, _fake_issue(f"{PFX}-C", owner=owner.username), "new")
        rows = db.query(models.InAppNotification).filter(
            models.InAppNotification.reference == f"{PFX}-C"
        ).all()
        assert rows, "verwacht fallback-meldingen naar admins"
        assert owner.username not in {r.username for r in rows}
    finally:
        _cleanup(db)


def test_list_and_mark_read_endpoints(client, auth, db):
    try:
        _create_inapp_notifications(db, _fake_issue(f"{PFX}-D", owner="dev_admin"), "new")
        _create_inapp_notifications(db, _fake_issue(f"{PFX}-E", owner="dev_admin"), "new")

        resp = client.get("/api/notifications", headers=auth)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        eigen = [n for n in data["notifications"] if (n["reference"] or "").startswith(PFX)]
        assert len(eigen) == 2
        assert data["unread_count"] >= 2

        # Eén melding als gelezen markeren
        target = eigen[0]
        resp = client.post(f"/api/notifications/{target['id']}/read", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["notification"]["is_read"] is True

        # Onbekende/andermans melding → 404
        resp = client.post("/api/notifications/999999999/read", headers=auth)
        assert resp.status_code == 404

        # Alles gelezen
        resp = client.post("/api/notifications/read-all", headers=auth)
        assert resp.status_code == 200
        resp = client.get("/api/notifications", headers=auth)
        assert resp.json()["unread_count"] == 0
    finally:
        _cleanup(db)


def test_notifications_require_auth(client):
    resp = client.get("/api/notifications")
    assert resp.status_code in (401, 403)
