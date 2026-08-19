"""
Taak 219 — Departments, granulaire permissies en afdelingsworkspaces.

Dekt:
- Seeding: afdelingen + rollenmatrix bestaan; migratie zonder toegangsverlies.
- /api/auth/me levert permissions/departments/workspace per gebruiker.
- Workspace per afdeling toont de juiste domeinen.
- Backend-enforcement: gebruiker zonder supplier.view krijgt 403 op
  supplier-endpoints — ook via directe URL (middleware, geen menu-UX).
- Rollen & Rechten-matrix is bewerkbaar en wijzigingen werken direct door,
  met audittrail.
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
import authz as authz_mod

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


@pytest.fixture()
def make_user(client, admin_headers):
    """Factory: maakt een gebruiker met rol + optionele afdelingen; ruimt op."""
    created: list[int] = []

    def _make(role: str, departments: list[str] | None = None):
        username = f"authz_{role}_{uuid.uuid4().hex[:8]}"
        password = f"Pw!{uuid.uuid4().hex[:12]}"
        body = {"username": username, "email": f"{username}@test.local",
                "full_name": f"Authz {role}", "password": password, "role": role}
        if departments is not None:
            body["departments"] = departments
        r = client.post("/api/users", headers=admin_headers, json=body)
        assert r.status_code in (200, 201), r.text
        uid = r.json()["id"]
        created.append(uid)
        lr = client.post("/api/auth/login", json={"username": username, "password": password})
        assert lr.status_code == 200, lr.text
        return uid, {"Authorization": f"Bearer {lr.json()['token']}"}

    yield _make

    db = SessionLocal()
    try:
        if created:
            db.query(models.User).filter(models.User.id.in_(created)).delete(
                synchronize_session=False)
            db.commit()
    finally:
        db.close()


# ── Seeding & migratie ──────────────────────────────────────────────────────

def test_departments_seeded(client, admin_headers):
    r = client.get("/api/authz/departments", headers=admin_headers)
    assert r.status_code == 200
    codes = {d["code"] for d in r.json()["departments"]}
    assert {"catman", "pricing", "inkoop", "supply_chain", "seo",
            "management", "finance", "data_bi", "admin"} <= codes


def test_roles_matrix_seeded(client, admin_headers):
    r = client.get("/api/authz/roles-matrix", headers=admin_headers)
    assert r.status_code == 200
    matrix = r.json()["matrix"]
    assert "admin.manage" in matrix["admin"]
    assert "admin.manage" not in matrix["viewer"]
    assert r.json()["permissions"], "permissiecatalogus hoort mee te komen"


def test_migrated_seed_users_keep_access(client):
    """Bestaande (geseedde) gebruikers zijn gemigreerd zonder toegangsverlies:
    de demo-viewer kon vroeger alle GET-endpoints zien en kan dat nog."""
    lr = client.post("/api/auth/login", json={"username": "viewer", "password": "viewer123"})
    if lr.status_code != 200:
        pytest.skip("demo-viewer niet aanwezig in deze database")
    hdr = {"Authorization": f"Bearer {lr.json()['token']}"}
    for url in ("/api/products", "/api/procurement/forecast", "/api/traffic"):
        resp = client.get(url, headers=hdr)
        assert resp.status_code not in (401, 403), f"{url}: {resp.status_code}"


# ── /api/auth/me en workspaces ──────────────────────────────────────────────

def test_me_contains_authz_payload(client, admin_headers):
    r = client.get("/api/auth/me", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "permissions" in body and "workspace" in body and "departments" in body
    assert "admin.manage" in body["permissions"]


def test_workspace_domains_per_department(client, make_user):
    """Elke workspace ziet de juiste domeinen (afdelingsgericht)."""
    _, inkoop_hdr = make_user("viewer", departments=["inkoop"])
    me = client.get("/api/auth/me", headers=inkoop_hdr).json()
    assert "inkoop" in me["workspace"]["domains"]
    assert "supplier.view" in me["permissions"]
    assert me["workspace"]["default_route"] == "/kostprijswijziging"
    # Geen pricing-permissies → pricing-domein niet in de workspace
    assert "pricing.view" not in me["permissions"]

    _, seo_hdr = make_user("viewer", departments=["seo"])
    me2 = client.get("/api/auth/me", headers=seo_hdr).json()
    assert "search-digital" in me2["workspace"]["domains"]
    assert "seo.view" in me2["permissions"]
    assert "supplier.view" not in me2["permissions"]


# ── Enforcement: 403 ook via directe URL ────────────────────────────────────

def test_user_without_supplier_permission_gets_403(client, make_user):
    """SEO-medewerker zonder supplier.view kan supplier-endpoints niet openen."""
    _, seo_hdr = make_user("viewer", departments=["seo"])
    for url in ("/api/procurement/forecast", "/api/kostprijswijziging"):
        resp = client.get(url, headers=seo_hdr)
        assert resp.status_code == 403, f"{url}: {resp.status_code}"
        assert resp.json().get("required_permission") == "supplier.view"
    # Eigen domein blijft gewoon bereikbaar
    ok = client.get("/api/traffic", headers=seo_hdr)
    assert ok.status_code not in (401, 403)


def test_hidden_menu_items_not_accessible_via_url(client, make_user):
    """Verborgen menu-items (beheer) zijn via directe URL niet toegankelijk."""
    _, hdr = make_user("viewer", departments=["seo"])
    for url in ("/api/users", "/api/admin/clear-data/preview", "/api/audit-log"):
        resp = client.get(url, headers=hdr)
        assert resp.status_code == 403, f"{url}: {resp.status_code}"


def test_cross_department_access_via_extra_permission(client, admin_headers, make_user):
    """Extra permissie geeft cross-department toegang zonder apart accounttype."""
    uid, hdr = make_user("viewer", departments=["seo"])
    assert client.get("/api/procurement/forecast", headers=hdr).status_code == 403
    r = client.put(f"/api/authz/users/{uid}", headers=admin_headers,
                   json={"extra_permissions": ["supplier.view"]})
    assert r.status_code == 200, r.text
    resp = client.get("/api/procurement/forecast", headers=hdr)
    assert resp.status_code not in (401, 403)
    me = client.get("/api/auth/me", headers=hdr).json()
    assert "inkoop" in me["workspace"]["domains"]


# ── Rollen & Rechten-matrix ─────────────────────────────────────────────────

def test_matrix_edit_applies_and_audits(client, admin_headers, make_user):
    get0 = client.get("/api/authz/roles-matrix", headers=admin_headers)
    original_viewer = get0.json()["matrix"]["viewer"]
    try:
        # Geef viewer-rol tijdelijk supplier.view via de matrix
        r = client.put("/api/authz/roles-matrix", headers=admin_headers, json={
            "matrix": {"viewer": sorted(set(original_viewer) | {"supplier.view"})},
        })
        assert r.status_code == 200, r.text
        _, hdr = make_user("viewer", departments=["management"])
        resp = client.get("/api/procurement/forecast", headers=hdr)
        assert resp.status_code not in (401, 403)
    finally:
        client.put("/api/authz/roles-matrix", headers=admin_headers,
                   json={"matrix": {"viewer": original_viewer}})
    # Audittrail aanwezig
    audit = client.get("/api/audit-log", headers=admin_headers,
                       params={"action": "roles_matrix_updated"})
    assert audit.status_code == 200
    items = audit.json().get("items") or audit.json().get("entries") or audit.json()
    assert items, "matrixwijziging hoort in de audittrail te staan"


def test_admin_role_cannot_lose_admin_manage(client, admin_headers):
    r = client.put("/api/authz/roles-matrix", headers=admin_headers,
                   json={"matrix": {"admin": ["management.view"]}})
    assert r.status_code == 400


def test_non_admin_cannot_edit_authz(client, make_user):
    _, hdr = make_user("viewer", departments=["seo"])
    assert client.put("/api/authz/roles-matrix", headers=hdr,
                      json={"matrix": {"viewer": []}}).status_code == 403
    assert client.patch("/api/authz/departments/1", headers=hdr,
                        json={"name": "X"}).status_code == 403


# ── Actie-permissies (methode-bewust) ───────────────────────────────────────

def test_revoking_approve_blocks_pricing_manager(client, admin_headers, make_user):
    """Intrekken van pricing.approve in de matrix blokkeert goedkeuren,
    ook voor een pricing_manager die het via het oude rollenmodel mocht."""
    get0 = client.get("/api/authz/roles-matrix", headers=admin_headers)
    original_pm = get0.json()["matrix"]["pricing_manager"]
    _, pm_hdr = make_user("pricing_manager")
    try:
        r = client.put("/api/authz/roles-matrix", headers=admin_headers, json={
            "matrix": {"pricing_manager": [c for c in original_pm if c != "pricing.approve"]},
        })
        assert r.status_code == 200, r.text
        for url in ("/api/recommendations/999999/approve",
                    "/api/recommendations/999999/reject"):
            resp = client.post(url, headers=pm_hdr)
            assert resp.status_code == 403, f"{url}: {resp.status_code}"
    finally:
        client.put("/api/authz/roles-matrix", headers=admin_headers,
                   json={"matrix": {"pricing_manager": original_pm}})


def test_granting_approve_gives_capability(client, admin_headers, make_user):
    """Toekennen van pricing.approve als extra recht geeft de capability aan
    een gebruiker die het via het oude rollenmodel niet had."""
    uid, hdr = make_user("viewer", departments=["pricing"])
    resp = client.post("/api/recommendations/999999/approve", headers=hdr)
    assert resp.status_code == 403
    r = client.put(f"/api/authz/users/{uid}", headers=admin_headers,
                   json={"extra_permissions": ["pricing.view", "pricing.approve"]})
    assert r.status_code == 200, r.text
    resp = client.post("/api/recommendations/999999/approve", headers=hdr)
    # 404: door de autorisatie heen; het advies bestaat niet.
    assert resp.status_code == 404, resp.status_code


def test_competition_edit_action_permission(client, admin_headers, make_user):
    """Zonder competition.edit geen concurrentie-mutaties; met wel."""
    uid, hdr = make_user("viewer", departments=["seo"])
    resp = client.put("/api/competition/settings", headers=hdr, json={})
    assert resp.status_code == 403
    r = client.put(f"/api/authz/users/{uid}", headers=admin_headers,
                   json={"extra_permissions": ["competition.view", "competition.edit"]})
    assert r.status_code == 200, r.text
    resp = client.put("/api/competition/settings", headers=hdr, json={})
    assert resp.status_code != 403


# ── Scopes ──────────────────────────────────────────────────────────────────

def test_user_scopes_roundtrip(client, admin_headers, make_user):
    uid, _ = make_user("viewer", departments=["management"])
    r = client.put(f"/api/authz/users/{uid}", headers=admin_headers, json={
        "scopes": [{"scope_type": "shop", "scope_value": "1"},
                   {"scope_type": "country", "scope_value": "NL"}],
    })
    assert r.status_code == 200, r.text
    body = client.get(f"/api/authz/users/{uid}", headers=admin_headers).json()
    assert {s["scope_type"] for s in body["scopes"]} == {"shop", "country"}
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == uid).first()
        allowed = authz_mod.user_allowed_shop_ids(db, user)
        assert allowed is not None and 1 in allowed
    finally:
        db.close()


def test_shop_scope_rejects_non_numeric_value(client, admin_headers, make_user):
    """Task #227-regressie: shop-scopes zijn numerieke DimShop-ids.

    Een shop_code (of typefout) als scope_value zou door user_allowed_shop_ids
    genegeerd worden en de gebruiker stilletjes van álle shop-data afsnijden;
    de API moet zo'n waarde daarom expliciet weigeren.
    """
    uid, _ = make_user("viewer", departments=["management"])
    # Niet-numerieke waarde (zoals een shop_code) → 400, scopes onaangetast.
    r = client.put(f"/api/authz/users/{uid}", headers=admin_headers, json={
        "scopes": [{"scope_type": "shop", "scope_value": "main"}],
    })
    assert r.status_code == 400, r.text
    assert "winkel" in r.json()["detail"].lower()
    # Numeriek maar onbestaand id → eveneens 400.
    r = client.put(f"/api/authz/users/{uid}", headers=admin_headers, json={
        "scopes": [{"scope_type": "shop", "scope_value": "999999999"}],
    })
    assert r.status_code == 400, r.text
    body = client.get(f"/api/authz/users/{uid}", headers=admin_headers).json()
    assert body["scopes"] == []
    # Geldig bestaand id blijft gewoon werken en geeft toegang tot die winkel.
    r = client.put(f"/api/authz/users/{uid}", headers=admin_headers, json={
        "scopes": [{"scope_type": "shop", "scope_value": "1"}],
    })
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == uid).first()
        allowed = authz_mod.user_allowed_shop_ids(db, user)
        assert allowed == {1}
    finally:
        db.close()
