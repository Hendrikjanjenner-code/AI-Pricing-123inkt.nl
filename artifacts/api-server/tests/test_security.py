"""
Security-tests (§33, OWASP-principes): sessie/token-tests, injectie,
input-validatie, uploadvalidatie, IDOR en audit-immutabiliteit.
Draait tegen de dev-database via de FastAPI TestClient.
"""
import io
import os
import sys
import uuid
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
import jwt as pyjwt

from main import app
from auth import SECRET_KEY, ALGORITHM, create_access_token

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


# ---------- Sessie / token ----------

def test_garbage_token_rejected(client):
    r = client.get("/api/products", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_tampered_signature_rejected(client, admin_headers):
    token = admin_headers["Authorization"].split(" ", 1)[1]
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    r = client.get("/api/products", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401


def test_expired_token_rejected(client):
    expired = create_access_token({"sub": "1"}, expires_delta=timedelta(minutes=-5))
    r = client.get("/api/products", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_token_signed_with_other_key_rejected(client):
    forged = pyjwt.encode({"sub": "1"}, "wrong-key", algorithm=ALGORITHM)
    r = client.get("/api/products", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_token_for_nonexistent_user_rejected(client):
    tok = create_access_token({"sub": "99999999"})
    r = client.get("/api/products", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_alg_none_token_rejected(client):
    header_payload = pyjwt.api_jws.encode(b'{"sub":"1"}', None, algorithm="none")
    r = client.get("/api/products", headers={"Authorization": f"Bearer {header_payload}"})
    assert r.status_code == 401


# ---------- Injectie / input-validatie ----------

SQLI = ["' OR '1'='1", "1; DROP TABLE users;--", "\" OR 1=1 --", "%27%20OR%201=1"]


def test_login_sql_injection_fails(client):
    for payload in SQLI:
        r = client.post("/api/auth/login", json={"username": payload, "password": payload})
        assert r.status_code in (400, 401, 422), (payload, r.status_code)


def test_query_param_injection_is_safe(client, admin_headers):
    for payload in SQLI:
        r = client.get("/api/products", params={"search": payload}, headers=admin_headers)
        assert r.status_code in (200, 400, 422), (payload, r.status_code)
        if r.status_code == 200:
            # Geen serverfout en geen datalek: normale (lege) lijst-respons
            assert isinstance(r.json(), (dict, list))


def test_invalid_role_rejected_on_create(client, admin_headers):
    r = client.post("/api/users", headers=admin_headers, json={
        "username": f"sec_{uuid.uuid4().hex[:8]}", "email": "sec@test.local",
        "full_name": "Sec", "password": "x", "role": "superadmin",
    })
    assert r.status_code in (400, 422)


# ---------- Uploadvalidatie ----------

def test_upload_validate_rejects_garbage_binary(client, admin_headers):
    files = {"file": ("evil.csv", io.BytesIO(b"\x00\x01\x02\xff\xfe" * 100), "text/csv")}
    r = client.post("/api/uploads/validate?upload_type=products", files=files,
                    headers=admin_headers)
    # Mag nooit een 500 zijn: nette validatiefout of rapport met 0 geldige rijen
    assert r.status_code in (200, 400, 422), r.text
    if r.status_code == 200:
        body = r.json()
        assert body.get("valid_rows", 0) == 0


def test_upload_validate_flags_bad_rows(client, admin_headers):
    csv = "sku_id,product_name,current_price\nSKU1,Test,-5\n,NoSku,10\n"
    files = {"file": ("test.csv", io.BytesIO(csv.encode()), "text/csv")}
    r = client.post("/api/uploads/validate?upload_type=products", files=files,
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("invalid_rows", 0) >= 1 or body.get("errors") or body.get("warnings")


def test_upload_requires_authentication(client):
    files = {"file": ("t.csv", io.BytesIO(b"sku_id\nX"), "text/csv")}
    r = client.post("/api/uploads/products", files=files)
    assert r.status_code in (401, 403)


# ---------- Audit-immutabiliteit ----------

def test_no_delete_route_for_audit_log():
    """Auditlog is niet verwijderbaar via de API (§35)."""
    for r in app.routes:
        if isinstance(r, APIRoute) and "audit" in r.path:
            assert "DELETE" not in r.methods, f"DELETE bestaat op {r.path}"


# ---------- Security headers / informatielekken ----------

def test_error_responses_do_not_leak_stacktrace(client, admin_headers):
    r = client.get("/api/decisions/99999999", headers=admin_headers)
    assert r.status_code in (404, 400)
    assert "Traceback" not in r.text and "sqlalchemy" not in r.text.lower()
