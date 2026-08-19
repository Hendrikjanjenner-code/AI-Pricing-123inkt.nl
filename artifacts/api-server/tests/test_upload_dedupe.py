"""
Tests voor taak: voorkom dat een dubbele rij een hele productupload laat mislukken.

- Een product-CSV met dubbele SKU-rijen importeert de unieke rijen,
  telt de duplicaten in rows_duplicates en logt welke rijen zijn overgeslagen.
- Zelfde gedrag voor prijzen-uploads (dedupe op SKU+datum).
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
SKU_A = "TEST-DEDUPE-A"
SKU_B = "TEST-DEDUPE-B"


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.__enter__()
    yield c
    # teardown: verwijder testdata
    db = SessionLocal()
    try:
        for m, col in ((models.FactPriceDaily, models.FactPriceDaily.sku_id),
                       (models.DimProduct, models.DimProduct.sku_id)):
            db.query(m).filter(col.in_([SKU_A, SKU_B])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass


@pytest.fixture(scope="module")
def admin_headers(client):
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _upload(client, headers, endpoint, csv_text, name="test.csv"):
    return client.post(
        f"/api/uploads/{endpoint}",
        headers=headers,
        files={"file": (name, io.BytesIO(csv_text.encode()), "text/csv")},
    )


def test_duplicate_sku_rows_do_not_fail_product_upload(client, admin_headers):
    csv_text = (
        "sku_id,product_name,cost_price,current_price\n"
        f"{SKU_A},Product A,1.00,2.00\n"
        f"{SKU_A},Product A duplicaat,1.00,2.00\n"
        f"{SKU_B},Product B,3.00,4.00\n"
    )
    resp = _upload(client, admin_headers, "products", csv_text)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows_processed"] == 2
    assert body["rows_duplicates"] == 1
    assert body["rows_failed"] == 0
    # foutlog/warnings vermelden de overgeslagen duplicaatrij
    assert any("duplicaat" in w.lower() and SKU_A in w for w in body["warnings"])

    # unieke rijen zijn daadwerkelijk geïmporteerd
    db = SessionLocal()
    try:
        assert db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_([SKU_A, SKU_B])).count() == 2
    finally:
        db.close()

    # job-record bevat de duplicaattelling én het foutlog
    jobs = client.get("/api/uploads?upload_type=products&limit=5",
                      headers=admin_headers).json()
    job = next(j for j in jobs if j["id"] == body["job_id"])
    assert job["rows_duplicates"] == 1
    assert any("duplicaat" in (e.get("bericht") or "").lower() for e in job["error_log"])


def test_duplicate_rows_deduped_in_price_upload(client, admin_headers):
    csv_text = (
        "date,sku_id,price\n"
        f"2026-08-01,{SKU_A},9.99\n"
        f"2026-08-01,{SKU_A},9.99\n"
        f"2026-08-02,{SKU_A},8.99\n"
    )
    resp = _upload(client, admin_headers, "prices", csv_text)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows_processed"] == 2
    assert body["rows_duplicates"] == 1
    assert any("duplicaat" in w.lower() for w in body["warnings"])
