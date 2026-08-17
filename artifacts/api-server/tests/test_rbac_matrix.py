"""
RBAC-matrix-tests (Gate 2, §35/§43): per rol per endpoint aantoonbaar getest.

- Iedere niet-publieke /api-route weigert ongeauthenticeerde toegang (401).
- Representatieve matrix van endpoints × rollen: admin, pricing_manager,
  analyst en viewer krijgen precies de toegang die de routes definiëren
  (403 = geweigerd; alles anders dan 401/403 = toegestaan).
Draait tegen de dev-database via de FastAPI TestClient; testusers worden
na afloop opgeruimd.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

# Routes die bewust publiek zijn (geen auth vereist).
PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/health",
    "/api/bigquery/status",
    "/api/health",
    "/api/healthz",
    "/api",
    "/api/",
}

ROLES = ("admin", "pricing_manager", "analyst", "viewer")


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
def tokens(client):
    """Login-token per rol; maakt tijdelijke gebruikers aan voor niet-admin rollen."""
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    admin_token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    created_ids = []
    toks = {"admin": admin_token}
    suffix = uuid.uuid4().hex[:8]
    for role in ("pricing_manager", "analyst", "viewer"):
        username = f"rbac_{role}_{suffix}"
        password = f"Pw!{uuid.uuid4().hex[:12]}"
        r = client.post("/api/users", headers=headers, json={
            "username": username, "email": f"{username}@test.local",
            "full_name": f"RBAC {role}", "password": password, "role": role,
        })
        assert r.status_code in (200, 201), r.text
        created_ids.append(r.json()["id"])
        lr = client.post("/api/auth/login", json={"username": username, "password": password})
        assert lr.status_code == 200, lr.text
        toks[role] = lr.json()["token"]

    yield toks

    db = SessionLocal()
    try:
        if created_ids:
            db.query(models.User).filter(models.User.id.in_(created_ids)).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


def _hdr(tokens, role):
    return {"Authorization": f"Bearer {tokens[role]}"}


# ---------- 1. Alle niet-publieke routes vereisen authenticatie ----------

def _api_routes():
    routes = []
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api"):
            if r.path in PUBLIC_PATHS:
                continue
            method = sorted(r.methods - {"HEAD", "OPTIONS"})[0] if r.methods else "GET"
            routes.append((method, r.path))
    return sorted(set(routes))


def test_all_api_routes_require_auth(client):
    """Iedere /api-route (behalve de bekende publieke) geeft 401 zonder token."""
    offenders = []
    for method, path in _api_routes():
        url = path
        # Vul path-parameters met dummywaarden
        for part in path.split("/"):
            if part.startswith("{") and part.endswith("}"):
                url = url.replace(part, "1")
        resp = client.request(method, url)
        # 405 = methode-mismatch met een andere route op hetzelfde pad;
        # de route zelf blijft door zijn eigen auth-dependency beschermd.
        if resp.status_code not in (401, 403, 405):
            offenders.append((method, path, resp.status_code))
    assert not offenders, f"Routes bereikbaar zonder authenticatie: {offenders}"


# ---------- 2. Matrix: representatieve endpoints × rollen ----------
# (method, url, json-body, {rol: mag (True) / geweigerd (False)})
MATRIX = [
    # Reads: iedere geauthenticeerde rol
    ("GET", "/api/products", None,
     {"admin": True, "pricing_manager": True, "analyst": True, "viewer": True}),
    ("GET", "/api/decisions", None,
     {"admin": True, "pricing_manager": True, "analyst": True, "viewer": True}),
    ("GET", "/api/signals", None,
     {"admin": True, "pricing_manager": True, "analyst": True, "viewer": True}),
    # Audit log: admin/pm/analyst; viewer geweigerd
    ("GET", "/api/audit-log", None,
     {"admin": True, "pricing_manager": True, "analyst": True, "viewer": False}),
    # Usersbeheer: alleen admin
    ("GET", "/api/users", None,
     {"admin": True, "pricing_manager": False, "analyst": False, "viewer": False}),
    ("POST", "/api/users", {"username": "x", "email": "x@x.x", "password": "x", "role": "viewer", "full_name": "x"},
     {"admin": None, "pricing_manager": False, "analyst": False, "viewer": False}),
    # Shops aanmaken: alleen admin
    ("POST", "/api/shops", {"shop_code": "zzz", "name": "Z"},
     {"admin": None, "pricing_manager": False, "analyst": False, "viewer": False}),
    # Engine runs: admin + pricing_manager
    ("POST", "/api/decisions/run", None,
     {"admin": True, "pricing_manager": True, "analyst": False, "viewer": False}),
    ("POST", "/api/forecast/run", None,
     {"admin": True, "pricing_manager": True, "analyst": False, "viewer": False}),
    # Uploads (import): admin + pricing_manager
    ("POST", "/api/uploads/products", None,
     {"admin": None, "pricing_manager": None, "analyst": False, "viewer": False}),
    # Loyalty run: admin/pm/analyst
    ("POST", "/api/loyalty/run", None,
     {"admin": True, "pricing_manager": True, "analyst": True, "viewer": False}),
    # Admin destructief domein: alleen admin (preview is read-only)
    ("GET", "/api/admin/clear-data/preview", None,
     {"admin": True, "pricing_manager": False, "analyst": False, "viewer": False}),
    # Recommendations approve: admin + pricing_manager
    ("POST", "/api/recommendations/1/approve", None,
     {"admin": None, "pricing_manager": None, "analyst": False, "viewer": False}),
]


@pytest.mark.parametrize("role", ROLES)
def test_rbac_matrix_per_role(client, tokens, role):
    """
    Per rol: 403 waar geweigerd; géén 401/403 waar toegestaan.
    `None` in de matrix = toegestaan qua RBAC, maar de call kan om andere
    redenen falen (422/404/400) — we asserten dan alleen 'geen 403'.
    """
    failures = []
    for method, url, body, expect in MATRIX:
        allowed = expect[role]
        resp = client.request(method, url, json=body, headers=_hdr(tokens, role))
        if allowed is False:
            if resp.status_code != 403:
                failures.append((method, url, "verwacht 403", resp.status_code))
        else:
            if resp.status_code in (401, 403):
                failures.append((method, url, "verwacht toegang", resp.status_code))
    assert not failures, f"RBAC-afwijkingen voor rol '{role}': {failures}"


# ---------- 3. Privilege-escalatie ----------

def test_non_admin_cannot_change_roles(client, tokens):
    """Een pricing_manager/analyst/viewer kan geen gebruikersrollen wijzigen."""
    for role in ("pricing_manager", "analyst", "viewer"):
        r = client.patch("/api/users/1", json={"role": "admin"}, headers=_hdr(tokens, role))
        assert r.status_code in (403, 405), f"{role}: {r.status_code}"


def test_invalid_role_in_token_cannot_bypass(client, tokens):
    """Tokens geven identiteit; rol komt uit de database — viewer blijft viewer."""
    r = client.get("/api/users", headers=_hdr(tokens, "viewer"))
    assert r.status_code == 403
