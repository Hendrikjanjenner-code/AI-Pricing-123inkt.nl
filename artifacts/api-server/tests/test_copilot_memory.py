"""
Copilot-geheugenbeheer (Task #44): gebruikers kunnen inzien en corrigeren wat
de Copilot over hen onthoudt (AiUserMemory).

RBAC:
- Eigen items: lijst/bewerk/verwijder voor iedere ingelogde gebruiker.
- Organisatie-items (user_id NULL): zichtbaar voor iedereen, maar alleen
  admin/pricing_manager mogen ze bewerken/verwijderen.
- Items van andere gebruikers: onzichtbaar en onbenaderbaar (404).
"""
import os
import sys
import uuid

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
    """Admin-, pricing_manager- en viewer-tokens + opruiming van testusers."""
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    admin_headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    created_ids = []
    toks = {"admin": admin_headers}
    suffix = uuid.uuid4().hex[:8]
    for role in ("pricing_manager", "viewer"):
        username = f"mem_{role}_{suffix}"
        password = f"Pw!{uuid.uuid4().hex[:12]}"
        r = client.post("/api/users", headers=admin_headers, json={
            "username": username, "email": f"{username}@test.local",
            "full_name": f"Mem {role}", "password": password, "role": role,
        })
        assert r.status_code in (200, 201), r.text
        created_ids.append(r.json()["id"])
        lr = client.post("/api/auth/login",
                         json={"username": username, "password": password})
        assert lr.status_code == 200, lr.text
        toks[role] = {"Authorization": f"Bearer {lr.json()['token']}"}
    toks["_user_ids"] = created_ids

    yield toks

    db = SessionLocal()
    try:
        if created_ids:
            db.query(models.AiUserMemory).filter(
                models.AiUserMemory.user_id.in_(created_ids)
            ).delete(synchronize_session=False)
            db.query(models.User).filter(
                models.User.id.in_(created_ids)
            ).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


def _add_memory(db, user_id, key=None, value="Dranken"):
    row = models.AiUserMemory(
        user_id=user_id,
        key=key or f"test_mem_{uuid.uuid4().hex[:8]}",
        value=value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _cleanup(db, *ids):
    db.query(models.AiUserMemory).filter(
        models.AiUserMemory.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def test_requires_auth(client):
    assert client.get("/api/copilot/memory").status_code == 401


def test_list_shows_own_and_org_items_with_editable_flag(client, ctx, db):
    viewer_id = ctx["_user_ids"][1]
    own = _add_memory(db, viewer_id, value="Papier")
    org = _add_memory(db, None, value="KPI = marge%")
    other = _add_memory(db, ctx["_user_ids"][0], value="geheim")
    try:
        r = client.get("/api/copilot/memory", headers=ctx["viewer"])
        assert r.status_code == 200
        by_id = {i["id"]: i for i in r.json()}
        assert own.id in by_id and by_id[own.id]["editable"] is True
        assert by_id[own.id]["scope"] == "persoonlijk"
        assert org.id in by_id and by_id[org.id]["editable"] is False
        assert by_id[org.id]["scope"] == "organisatie"
        # Items van andere gebruikers zijn onzichtbaar
        assert other.id not in by_id
    finally:
        _cleanup(db, own.id, org.id, other.id)


def test_user_can_edit_and_delete_own_item(client, ctx, db):
    viewer_id = ctx["_user_ids"][1]
    row = _add_memory(db, viewer_id, value="oud")
    try:
        r = client.put(f"/api/copilot/memory/{row.id}", headers=ctx["viewer"],
                       json={"value": "nieuw"})
        assert r.status_code == 200 and r.json()["value"] == "nieuw"

        r = client.put(f"/api/copilot/memory/{row.id}", headers=ctx["viewer"],
                       json={"value": "   "})
        assert r.status_code == 400

        r = client.delete(f"/api/copilot/memory/{row.id}", headers=ctx["viewer"])
        assert r.status_code == 200
        assert db.query(models.AiUserMemory).filter(
            models.AiUserMemory.id == row.id).first() is None
    finally:
        _cleanup(db, row.id)


def test_user_cannot_touch_someone_elses_item(client, ctx, db):
    pm_id = ctx["_user_ids"][0]
    row = _add_memory(db, pm_id, value="privé")
    try:
        assert client.put(f"/api/copilot/memory/{row.id}", headers=ctx["viewer"],
                          json={"value": "hack"}).status_code == 404
        assert client.delete(f"/api/copilot/memory/{row.id}",
                             headers=ctx["viewer"]).status_code == 404
        db.expire_all()
        assert db.query(models.AiUserMemory).filter(
            models.AiUserMemory.id == row.id).first() is not None
    finally:
        _cleanup(db, row.id)


def test_org_items_only_managed_by_admin_or_pm(client, ctx, db):
    org = _add_memory(db, None, value="org-context")
    org_id = org.id
    try:
        # Viewer: zichtbaar maar niet beheerbaar (403)
        assert client.put(f"/api/copilot/memory/{org_id}", headers=ctx["viewer"],
                          json={"value": "x"}).status_code == 403
        assert client.delete(f"/api/copilot/memory/{org_id}",
                             headers=ctx["viewer"]).status_code == 403

        # pricing_manager mag bewerken
        r = client.put(f"/api/copilot/memory/{org_id}",
                       headers=ctx["pricing_manager"], json={"value": "bijgewerkt"})
        assert r.status_code == 200 and r.json()["value"] == "bijgewerkt"

        # admin mag verwijderen
        assert client.delete(f"/api/copilot/memory/{org_id}",
                             headers=ctx["admin"]).status_code == 200
        db.expire_all()
        assert db.query(models.AiUserMemory).filter(
            models.AiUserMemory.id == org_id).first() is None
    finally:
        _cleanup(db, org_id)


def test_unknown_id_is_404(client, ctx):
    assert client.delete("/api/copilot/memory/99999999",
                         headers=ctx["admin"]).status_code == 404
