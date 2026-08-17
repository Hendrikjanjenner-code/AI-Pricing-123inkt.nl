"""
Tests voor taak Data Integration & Data Quality Center:
- connector-syncpaden (search_console, google_ads, microsoft_ads) falen netjes
  wanneer niet geconfigureerd en registreren geen valse successen;
- /api/data-sources geeft voor elke bron dezelfde uniforme statusvelden;
- /api/data-quality detecteert issues, persisteert het register en ondersteunt
  de owner/status-workflow;
- importbatches krijgen batch-ID + duplicaten/foutlog-velden;
- Microsoft Ads persistentie is idempotent (herhaalde run dupliceert geen rijen).
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
NEW_CONNECTORS = ["search_console", "google_ads", "microsoft_ads"]
EXPECTED_SOURCE_KEYS = {
    "priceshape", "drs", "ga4", "search_console", "google_ads",
    "microsoft_ads", "handmatig", "paper_copy",
}
UNIFORM_FIELDS = [
    "connection_status", "configured", "last_sync_at", "next_sync_at",
    "sync_schedule", "records", "records_label", "newest_data_date",
    "freshness_days", "warnings_recent", "failed_jobs_recent",
    "quality_score", "open_issues",
]


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


# ── Connector-syncpaden ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name", NEW_CONNECTORS)
def test_new_connector_listed(client, admin_headers, name):
    resp = client.get("/api/connectors", headers=admin_headers)
    assert resp.status_code == 200
    payload = resp.json()
    items = payload if isinstance(payload, list) else payload.get("connectors", [])
    assert name in [c["name"] for c in items]


@pytest.mark.parametrize("name", NEW_CONNECTORS)
def test_unconfigured_connector_test_is_graceful(client, admin_headers, name):
    resp = client.post(f"/api/connectors/{name}/test", json={"credentials": {}},
                       headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "not_configured"
    assert body["message"]


@pytest.mark.parametrize("name", NEW_CONNECTORS)
def test_unconfigured_connector_sync_does_not_fake_success(client, admin_headers, name):
    before = _count_ok_sync_jobs(name)
    resp = client.post(f"/api/connectors/{name}/sync", headers=admin_headers)
    # Niet geconfigureerd → nette 4xx, geen 500 en geen geslaagde sync-job erbij.
    assert 400 <= resp.status_code < 500, resp.text
    assert _count_ok_sync_jobs(name) == before


def _count_ok_sync_jobs(name: str) -> int:
    db = SessionLocal()
    try:
        return db.query(models.ImportJob).filter(
            models.ImportJob.upload_type == f"api_sync_{name}",
            models.ImportJob.status.notin_(["fout", "failed"]),
        ).count()
    finally:
        db.close()


# ── Uniforme bronregistratie ────────────────────────────────────────────────

def test_data_sources_uniform_fields(client, admin_headers):
    resp = client.get("/api/data-sources", headers=admin_headers)
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    keys = {s["key"] for s in sources}
    assert EXPECTED_SOURCE_KEYS <= keys, f"ontbrekende bronnen: {EXPECTED_SOURCE_KEYS - keys}"
    for s in sources:
        for field in UNIFORM_FIELDS:
            assert field in s, f"bron {s['key']} mist veld {field}"
        assert isinstance(s["records"], int)
        assert 0 <= s["quality_score"] <= 100


# ── Data Quality Center: detecties + workflow ──────────────────────────────

def test_data_quality_report_shape_and_registry(client, admin_headers):
    resp = client.get("/api/data-quality", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in ("overall_score", "total_skus", "issues", "summary",
                "drs_summary", "drs_issues", "hierarchy_node_count", "counts"):
        assert key in body
    for issue in body["issues"]:
        for field in ("issue_code", "severity", "message", "affected_count",
                      "source", "module", "business_impact", "suggested_action"):
            assert field in issue, f"issue {issue.get('issue_code')} mist {field}"
    # Elke gedetecteerde issue staat in het persistente register
    reg = client.get("/api/data-quality/issues", headers=admin_headers)
    assert reg.status_code == 200
    reg_codes = {r["issue_code"] for r in reg.json()}
    assert {i["issue_code"] for i in body["issues"]} <= reg_codes


def test_issue_owner_status_workflow(client, admin_headers):
    db = SessionLocal()
    try:
        row = models.DataQualityIssue(
            issue_code="TEST_WORKFLOW_ISSUE", title="Test", message="Testissue",
            severity="warning", source="Test", module="Test", affected_count=1,
            status="open",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        issue_id = row.id
    finally:
        db.close()
    try:
        patch = client.patch(f"/api/data-quality/issues/{issue_id}",
                             json={"owner": "analistA", "status": "in_behandeling"},
                             headers=admin_headers)
        assert patch.status_code == 200
        body = patch.json()
        assert body["owner"] == "analistA"
        assert body["status"] == "in_behandeling"
        assert body["updated_by"] == "dev_admin"
        # Ongeldige status wordt geweigerd
        bad = client.patch(f"/api/data-quality/issues/{issue_id}",
                           json={"status": "kapot"}, headers=admin_headers)
        assert bad.status_code == 400
        # Oplossen zet resolved_at
        done = client.patch(f"/api/data-quality/issues/{issue_id}",
                            json={"status": "opgelost"}, headers=admin_headers)
        assert done.status_code == 200
        assert done.json()["resolved_at"] is not None
    finally:
        db = SessionLocal()
        try:
            db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.id == issue_id).delete()
            db.commit()
        finally:
            db.close()


# ── Importbatch-verrijking ──────────────────────────────────────────────────

def test_upload_gets_batch_id_and_duplicate_count(client, admin_headers):
    import uuid as _uuid
    sku = f"TST-{_uuid.uuid4().hex[:8].upper()}"
    csv = f"sku_id,name,cost_price\n{sku},Batchtest,1.00\n".encode()
    resp = client.post("/api/uploads/products",
                       files={"file": ("batchtest.csv", csv, "text/csv")},
                       headers=admin_headers)
    try:
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["batch_id"]
        assert body["rows_duplicates"] == 0
        listing = client.get("/api/uploads?limit=5", headers=admin_headers).json()
        job = next(j for j in listing if j.get("batch_id") == body["batch_id"])
        assert "rows_duplicates" in job and "error_log" in job
    finally:
        db = SessionLocal()
        try:
            db.query(models.DimProduct).filter(models.DimProduct.sku_id == sku).delete()
            db.commit()
        finally:
            db.close()


# ── Microsoft Ads: idempotente persistentie ─────────────────────────────────

def test_ms_ads_persist_rows_idempotent():
    from connectors import microsoft_ads_connector as ms
    rows = [
        {"TimePeriod": "2026-01-05", "CampaignId": "999001", "CampaignName": "Test A",
         "Spend": "12.50", "Impressions": "100", "Clicks": "10", "Conversions": "1", "Revenue": "40"},
        {"TimePeriod": "2026-01-05", "CampaignId": "999002", "CampaignName": "Test B",
         "Spend": "5.00", "Impressions": "50", "Clicks": "2", "Conversions": "0", "Revenue": "0"},
    ]
    db = SessionLocal()
    try:
        n1 = ms._persist_rows(db, rows)
        n2 = ms._persist_rows(db, rows)  # herhaalde run mag niet dupliceren
        assert n1 == n2 == 2
        count = db.query(models.FactMarketingCostDaily).filter(
            models.FactMarketingCostDaily.sku_id.in_(["MSCAMPAGNE:999001", "MSCAMPAGNE:999002"]),
            models.FactMarketingCostDaily.date == date(2026, 1, 5),
        ).count()
        assert count == 2, f"verwacht 2 rijen na dubbele run, kreeg {count}"
        row = db.query(models.FactMarketingCostDaily).filter(
            models.FactMarketingCostDaily.sku_id == "MSCAMPAGNE:999001").first()
        assert row.category == "Microsoft Ads"
        assert row.sea_cost == pytest.approx(12.5)
    finally:
        db.query(models.FactMarketingCostDaily).filter(
            models.FactMarketingCostDaily.sku_id.in_(["MSCAMPAGNE:999001", "MSCAMPAGNE:999002"]),
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


# ── PriceShape: batch-audit-velden op validatie- en afgekeurde imports ──────

def test_priceshape_validate_job_has_audit_fields(client, admin_headers):
    csv = (b"sku,competitor,competitor_price\n"
           b"NIET-BESTAAND-1,ShopX,9.99\n"
           b"NIET-BESTAAND-1,ShopX,10.49\n"   # duplicaat sku+concurrent
           b",ShopY,abc\n")                    # ongeldige rij
    resp = client.post("/api/uploads/priceshape/validate",
                       files={"file": ("audit.csv", csv, "text/csv")},
                       headers=admin_headers)
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    db = SessionLocal()
    try:
        job = db.query(models.ImportJob).get(job_id)
        assert job.batch_id
        assert job.rows_duplicates == 1
        assert isinstance(job.error_log, list) and len(job.error_log) >= 1
        assert all("bericht" in e for e in job.error_log)
    finally:
        db.query(models.ImportJob).filter(models.ImportJob.id == job_id).delete()
        db.commit()
        db.close()


def test_connector_sync_failure_job_has_error_log(client, admin_headers):
    # Sync van een niet-geconfigureerde connector: als er een job wordt
    # geregistreerd, moet die batch_id + gestructureerde error_log hebben.
    before_ids = _job_ids("api_sync_google_ads")
    client.post("/api/connectors/google_ads/sync", headers=admin_headers)
    new_ids = _job_ids("api_sync_google_ads") - before_ids
    db = SessionLocal()
    try:
        for jid in new_ids:
            job = db.query(models.ImportJob).get(jid)
            assert job.batch_id
            assert job.rows_duplicates == 0
            if job.status in ("fout", "failed"):
                assert isinstance(job.error_log, list) and job.error_log
    finally:
        for jid in new_ids:
            db.query(models.ImportJob).filter(models.ImportJob.id == jid).delete()
        db.commit()
        db.close()


def _job_ids(upload_type: str) -> set:
    db = SessionLocal()
    try:
        return {j.id for j in db.query(models.ImportJob.id).filter(
            models.ImportJob.upload_type == upload_type)}
    finally:
        db.close()


# ── BigQuery: _upsert_rows moet MERGE op pk gebruiken (geen append) ────────

def _install_fake_bigquery_module():
    """Stub google.cloud.bigquery zodat de MERGE-logica zonder SDK testbaar is."""
    import sys, types
    mod = types.ModuleType("google.cloud.bigquery")

    class SchemaField:
        def __init__(self, name, field_type, mode="NULLABLE"):
            self.name, self.field_type, self.mode = name, field_type, mode

    class LoadJobConfig:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class SourceFormat:
        NEWLINE_DELIMITED_JSON = "NEWLINE_DELIMITED_JSON"

    class WriteDisposition:
        WRITE_TRUNCATE = "WRITE_TRUNCATE"
        WRITE_APPEND = "WRITE_APPEND"

    mod.SchemaField = SchemaField
    mod.LoadJobConfig = LoadJobConfig
    mod.SourceFormat = SourceFormat
    mod.WriteDisposition = WriteDisposition
    import google.cloud as gc
    sys.modules["google.cloud.bigquery"] = mod
    gc.bigquery = mod


class _FakeLoadJob:
    def result(self):
        return None


class _FakeQueryJob:
    def result(self):
        return None


class _FakeBQClient:
    """Vangt de gegenereerde MERGE-SQL en tabellen op zonder echte BigQuery."""
    def __init__(self):
        self.queries: list[str] = []
        self.loaded_tables: list[str] = []
        self.deleted_tables: list[str] = []

    def load_table_from_file(self, fh, table_id, job_config=None):
        self.loaded_tables.append(table_id)
        assert job_config.write_disposition == "WRITE_TRUNCATE"
        return _FakeLoadJob()

    def query(self, sql):
        self.queries.append(sql)
        return _FakeQueryJob()

    def delete_table(self, table_id, not_found_ok=False):
        self.deleted_tables.append(table_id)


def test_bq_upsert_rows_merges_on_pk_and_cleans_staging():
    _install_fake_bigquery_module()
    from bigquery import sync as bq_sync
    from bigquery.schema import BY_PG_TABLE

    tdef = BY_PG_TABLE["dim_product"]
    fake = _FakeBQClient()
    rows = [{"sku_id": "SKU-1", "product_name": "A"},
            {"sku_id": "SKU-2", "product_name": "B"}]
    n, err = bq_sync._upsert_rows(fake, "proj", tdef, rows, pk_col="sku_id")
    assert err is None and n == 2
    # Staging geladen (WRITE_TRUNCATE) en na afloop opgeruimd
    assert len(fake.loaded_tables) == 1 and "__staging_" in fake.loaded_tables[0]
    assert fake.deleted_tables == fake.loaded_tables
    # MERGE op de primaire sleutel, met UPDATE- en INSERT-takken
    assert len(fake.queries) == 1
    sql = fake.queries[0]
    assert sql.startswith("MERGE ")
    assert "ON T.`sku_id` = S.`sku_id`" in sql
    assert "WHEN MATCHED THEN UPDATE SET" in sql
    assert "WHEN NOT MATCHED THEN INSERT" in sql


def test_bq_upsert_rows_repeat_run_still_merges_not_appends():
    _install_fake_bigquery_module()
    from bigquery import sync as bq_sync
    from bigquery.schema import BY_PG_TABLE

    tdef = BY_PG_TABLE["fact_sales_daily"]
    fake = _FakeBQClient()
    rows = [{"id": 1, "sku_id": "SKU-1"}]
    for _ in range(2):  # herhaalde run: elke run MERGEt, nooit een kale append
        n, err = bq_sync._upsert_rows(fake, "proj", tdef, rows, pk_col="id")
        assert err is None and n == 1
    assert len(fake.queries) == 2
    assert all("ON T.`id` = S.`id`" in q for q in fake.queries)
    assert all("WRITE" not in q for q in fake.queries)  # geen append-disposition in SQL


# ── BigQuery sync: paginatie, watermerk en meta-tabel-exclusie ──────────────

def test_bq_fetch_pg_rows_paginates_without_gaps_or_dupes(monkeypatch):
    """Keyset-paginatie: pagina's van 2 rijen dekken de hele tabel exact één keer."""
    from bigquery import sync as bq_sync
    monkeypatch.setattr(bq_sync, "BATCH_SIZE", 2)
    db = SessionLocal()
    try:
        expected = {r[0] for r in db.execute(
            __import__("sqlalchemy").text("SELECT id FROM dim_shop"))}
        seen: list = []
        last_key = None
        while True:
            rows = bq_sync._fetch_pg_rows(db, "dim_shop", since=None, last_key=last_key)
            if not rows:
                break
            seen.extend(r["id"] for r in rows)
            last = rows[-1]
            wm = last.get(bq_sync.WATERMARK_COLUMN["dim_shop"])
            from datetime import datetime as _dt
            if wm is not None and not isinstance(wm, _dt):
                wm = _dt.combine(wm, _dt.min.time())
            last_key = (wm, last["id"])
            if len(rows) < bq_sync.BATCH_SIZE:
                break
        assert len(seen) == len(set(seen)), "paginatie leverde duplicaten op"
        assert set(seen) == expected, "paginatie miste rijen"
    finally:
        db.close()


def test_bq_watermark_roundtrip_and_inclusive_filter():
    """Watermerk = max geëxporteerd bron-watermerk; filter is inclusief (>=)
    zodat updates op dezelfde datum bij een volgende run opnieuw meegaan."""
    from bigquery import sync as bq_sync
    from datetime import datetime as _dt
    db = SessionLocal()
    try:
        wm = _dt(2026, 2, 1, 12, 0, 0)
        job = bq_sync._save_import_job(db, "dim_shop", 5, "geimporteerd", watermark=wm)
        try:
            read_back = bq_sync._get_last_watermark(db, "dim_shop")
            assert read_back == wm, "watermerk moet het bron-maximum zijn, niet completed_at"
            # Inclusief filter: rijen met watermerk == since worden meegenomen
            max_created = db.execute(__import__("sqlalchemy").text(
                "SELECT MAX(created_at) FROM dim_shop")).scalar()
            rows = bq_sync._fetch_pg_rows(db, "dim_shop", since=max_created)
            assert rows, ">= filter moet rijen met exact het watermerk teruggeven"
        finally:
            db.query(models.ImportJob).filter(models.ImportJob.id == job.id).delete()
            db.commit()
    finally:
        db.close()


def test_bq_sync_all_skips_meta_tables(monkeypatch):
    """sync_all_tables slaat bq_sync_batches en interne _-tabellen over."""
    from bigquery import sync as bq_sync
    synced: list[str] = []
    monkeypatch.setattr(bq_sync, "sync_table",
                        lambda t, full_refresh=False: synced.append(t) or {"pg_table": t})
    bq_sync.sync_all_tables()
    assert "import_jobs" not in synced, "bq_sync_batches (import_jobs) mag niet generiek gesynct worden"
    assert not any(t.startswith("_") for t in synced)
    assert "dim_product" in synced and "fact_sales_daily" in synced


def test_bq_sdk_dependency_importable():
    """Niet-gemockte smoke check: de gedeclareerde runtime-dependency
    google-cloud-bigquery is daadwerkelijk installeerbaar/importeerbaar,
    zodat de syncpaden beschikbaar worden zodra credentials aanwezig zijn."""
    import importlib, sys
    sys.modules.pop("google.cloud.bigquery", None)  # verwijder evt. test-stub
    mod = importlib.import_module("google.cloud.bigquery")
    assert hasattr(mod, "Client") and hasattr(mod, "LoadJobConfig")


def test_bq_save_import_job_has_full_audit_fields():
    """BigQuery-syncbatches krijgen dezelfde auditvelden als andere importpaden."""
    from bigquery import sync as bq_sync
    db = SessionLocal()
    try:
        ok = bq_sync._save_import_job(db, "dim_shop", 3, "geimporteerd")
        bad = bq_sync._save_import_job(db, "dim_shop", 0, "fout", error="BQ onbereikbaar")
        try:
            assert ok.batch_id and len(ok.batch_id) == 36
            assert ok.rows_duplicates == 0 and ok.error_log == []
            assert bad.batch_id and bad.batch_id != ok.batch_id
            assert isinstance(bad.error_log, list) and bad.error_log[0]["bericht"] == "BQ onbereikbaar"
        finally:
            db.query(models.ImportJob).filter(
                models.ImportJob.id.in_([ok.id, bad.id])).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


def test_bq_dim_product_merge_uses_composite_shop_sku_key():
    """dim_product MERGEt op (shop_id, sku_id): gelijknamige SKU's in andere
    shops overschrijven elkaar niet in BigQuery."""
    _install_fake_bigquery_module()
    from bigquery import sync as bq_sync
    from bigquery.schema import BY_PG_TABLE

    assert bq_sync.PK_COLUMN["dim_product"] == ["shop_id", "sku_id"]
    tdef = BY_PG_TABLE["dim_product"]
    fake = _FakeBQClient()
    rows = [{"shop_id": 1, "sku_id": "SKU-1"}, {"shop_id": 2, "sku_id": "SKU-1"}]
    n, err = bq_sync._upsert_rows(fake, "proj", tdef, rows,
                                  pk_col=bq_sync.PK_COLUMN["dim_product"])
    assert err is None and n == 2
    sql = fake.queries[0]
    assert "ON T.`shop_id` = S.`shop_id` AND T.`sku_id` = S.`sku_id`" in sql
    assert "T.`shop_id` = S.`shop_id`," not in sql.split("UPDATE SET")[1]  # pk niet in UPDATE
