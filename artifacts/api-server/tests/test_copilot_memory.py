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
        db.expire_all()
        # Soft-delete: tombstone blijft in de DB, item verdwijnt uit de lijst
        tomb = db.query(models.AiUserMemory).filter(
            models.AiUserMemory.id == row.id).first()
        assert tomb is not None and tomb.status == "deleted"
        r = client.get("/api/copilot/memory", headers=ctx["viewer"])
        assert row.id not in {i["id"] for i in r.json()}
        # Een tombstone is voor de gebruiker "niet gevonden"
        assert client.delete(f"/api/copilot/memory/{row.id}",
                             headers=ctx["viewer"]).status_code == 404
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
        # Soft-delete: rij blijft bestaan als tombstone (status="deleted"),
        # maar verdwijnt uit de lijst.
        tomb = db.query(models.AiUserMemory).filter(
            models.AiUserMemory.id == org_id).first()
        assert tomb is not None and tomb.status == "deleted"
        r = client.get("/api/copilot/memory", headers=ctx["admin"])
        assert org_id not in {i["id"] for i in r.json()}
    finally:
        _cleanup(db, org_id)


def test_unknown_id_is_404(client, ctx):
    assert client.delete("/api/copilot/memory/99999999",
                         headers=ctx["admin"]).status_code == 404


# ---------------------------------------------------------------------------
# Task #135: verwijderde/gecorrigeerde voorkeuren mogen niet stilletjes
# terugkeren of overschreven worden door automatische extractie.
# ---------------------------------------------------------------------------
import ai_gateway


class _FakeResp:
    def __init__(self, content):
        self.usage = None
        msg = type("M", (), {"content": content})()
        self.choices = [type("C", (), {"message": msg})()]


class _FakeClient:
    def __init__(self, content):
        completions = type("Comp", (), {})()
        completions.create = lambda **kw: _FakeResp(content)
        self.chat = type("Chat", (), {"completions": completions})()


def _run_extraction(db, monkeypatch, user_id, extracted_items):
    """Simuleer maybe_extract_memory met een gefakete LLM-respons."""
    import json as _json
    from datetime import date

    user = db.query(models.User).filter(models.User.id == user_id).first()
    conv = models.AiConversation(user_id=user_id, title="test")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    msg_ids = []
    for i in range(ai_gateway.MEMORY_EXTRACT_EVERY):
        m = models.AiMessage(conversation_id=conv.id, role="user",
                             content=f"vraag {i}")
        db.add(m)
        db.commit()
        msg_ids.append(m.id)

    monkeypatch.setattr(ai_gateway, "_try_reserve_auxiliary_budget",
                        lambda *a, **k: date.today())
    monkeypatch.setattr(ai_gateway, "_log_call", lambda *a, **k: None)
    monkeypatch.setattr(ai_gateway, "_make_client",
                        lambda: (_FakeClient(_json.dumps(extracted_items)), "test"))
    try:
        ai_gateway.maybe_extract_memory(db, user, conv.id)
    finally:
        db.query(models.AiMessage).filter(
            models.AiMessage.id.in_(msg_ids)).delete(synchronize_session=False)
        db.query(models.AiConversation).filter(
            models.AiConversation.id == conv.id).delete(synchronize_session=False)
        db.commit()


def test_deleted_memory_does_not_return_after_extraction(client, ctx, db, monkeypatch):
    viewer_id = ctx["_user_ids"][1]
    key = f"test_tomb_{uuid.uuid4().hex[:8]}"
    row = _add_memory(db, viewer_id, key=key, value="Dranken")
    try:
        # Gebruiker verwijdert het item
        assert client.delete(f"/api/copilot/memory/{row.id}",
                             headers=ctx["viewer"]).status_code == 200
        # Extractie probeert dezelfde key opnieuw op te slaan
        _run_extraction(db, monkeypatch, viewer_id,
                        [{"key": key, "value": "Dranken"}])
        db.expire_all()
        rows = db.query(models.AiUserMemory).filter(
            models.AiUserMemory.user_id == viewer_id,
            models.AiUserMemory.key == key).all()
        assert len(rows) == 1
        assert rows[0].status == "deleted"
        assert rows[0].value == "Dranken"
        # En dus onzichtbaar in lijst en context
        r = client.get("/api/copilot/memory", headers=ctx["viewer"])
        assert key not in {i["key"] for i in r.json()}
        block = ai_gateway.get_memory_block(
            db, db.query(models.User).get(viewer_id))
        assert block is None or key not in block
    finally:
        _cleanup(db, row.id)


def test_manual_correction_wins_over_extraction(client, ctx, db, monkeypatch):
    viewer_id = ctx["_user_ids"][1]
    key = f"test_manual_{uuid.uuid4().hex[:8]}"
    row = _add_memory(db, viewer_id, key=key, value="Dranken")
    try:
        # Gebruiker corrigeert handmatig
        r = client.put(f"/api/copilot/memory/{row.id}", headers=ctx["viewer"],
                       json={"value": "Papier"})
        assert r.status_code == 200 and r.json()["source"] == "manual"
        # Extractie probeert de oude waarde terug te zetten
        _run_extraction(db, monkeypatch, viewer_id,
                        [{"key": key, "value": "Dranken"}])
        db.expire_all()
        fresh = db.query(models.AiUserMemory).filter(
            models.AiUserMemory.id == row.id).first()
        assert fresh.value == "Papier"
        assert fresh.source == "manual"
    finally:
        _cleanup(db, row.id)


def test_extraction_still_updates_extracted_rows(client, ctx, db, monkeypatch):
    viewer_id = ctx["_user_ids"][1]
    key = f"test_upd_{uuid.uuid4().hex[:8]}"
    row = _add_memory(db, viewer_id, key=key, value="Dranken")
    try:
        _run_extraction(db, monkeypatch, viewer_id,
                        [{"key": key, "value": "Koffie"}])
        db.expire_all()
        fresh = db.query(models.AiUserMemory).filter(
            models.AiUserMemory.id == row.id).first()
        assert fresh.value == "Koffie"
        assert fresh.status == "active"
    finally:
        _cleanup(db, row.id)
