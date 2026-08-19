"""
Tests voor de geplande (nachtelijke) BigQuery-sync.

Dekt:
  - run_nightly_sync: niet-geconfigureerd → overslaan, exit 0
  - run_nightly_sync: alle tabellen ok/skipped → exit 0
  - run_nightly_sync: één of meer tabelfouten → exit 1
  - run_nightly_sync: onverwachte exception → exit 1 (gooit nooit)
  - scheduled_sync.main: BigQuery-stap draait ALTIJD, ook als de
    PriceShape-refresh faalt of wordt overgeslagen; exit-code combineert beide
"""
from unittest.mock import patch

from bigquery import sync as bq_sync
import scheduled_sync


def _res(pg_table: str, status: str, rows: int = 0, error=None) -> dict:
    return {
        "pg_table": pg_table,
        "bq_table": f"analytics.{pg_table}",
        "rows_exported": rows,
        "status": status,
        "error": error,
    }


# ── run_nightly_sync ──────────────────────────────────────────────────────────

def test_nightly_sync_skips_when_bq_not_configured():
    with patch("bigquery.client.bq_available", return_value=False), \
         patch("bigquery.client.bq_configured", return_value=False), \
         patch.object(bq_sync, "sync_all_tables") as mock_sync:
        assert bq_sync.run_nightly_sync() == 0
        mock_sync.assert_not_called()


def test_nightly_sync_configured_but_broken_exit_one_and_import_job():
    """
    Geconfigureerde maar onbruikbare BigQuery-credentials mogen NOOIT als
    succesvolle overslag worden gemaskeerd: exit 1 + fout-ImportJob in de
    sync-history.
    """
    from database import SessionLocal
    from models import ImportJob

    err = "BigQuery client init mislukt: ongeldige service-account-JSON"
    with patch("bigquery.client.bq_available", return_value=False), \
         patch("bigquery.client.bq_configured", return_value=True), \
         patch("bigquery.client.bq_last_error", return_value=err), \
         patch.object(bq_sync, "sync_all_tables") as mock_sync:
        assert bq_sync.run_nightly_sync() == 1
        mock_sync.assert_not_called()

    db = SessionLocal()
    try:
        job = (
            db.query(ImportJob)
            .filter(
                ImportJob.source == "bigquery",
                ImportJob.upload_type == "bq_sync:verbinding",
            )
            .order_by(ImportJob.completed_at.desc())
            .first()
        )
        assert job is not None, "Geen fout-ImportJob geregistreerd voor kapotte BQ-config"
        assert job.status == "fout"
        assert err in (job.error_message or "")
        # Zichtbaar via /api/bigquery/sync/history
        history = bq_sync.get_sync_history(db, pg_table="verbinding", limit=5)
        assert any(h["status"] == "fout" and h["error"] == job.error_message for h in history)
        # Opruimen zodat andere tests geen residu zien
        db.delete(job)
        db.commit()
    finally:
        db.close()


def test_nightly_sync_ok_and_skipped_tables_exit_zero():
    results = [_res("dim_product", "ok", 10), _res("dim_shop", "skipped")]
    with patch("bigquery.client.bq_available", return_value=True), \
         patch.object(bq_sync, "sync_all_tables", return_value=results):
        assert bq_sync.run_nightly_sync() == 0


def test_nightly_sync_table_error_exit_one():
    results = [
        _res("dim_product", "ok", 10),
        _res("fact_sales_daily", "error", 0, "quota exceeded"),
    ]
    with patch("bigquery.client.bq_available", return_value=True), \
         patch.object(bq_sync, "sync_all_tables", return_value=results):
        assert bq_sync.run_nightly_sync() == 1


def test_nightly_sync_unexpected_exception_exit_one_never_raises():
    with patch("bigquery.client.bq_available", return_value=True), \
         patch.object(bq_sync, "sync_all_tables", side_effect=RuntimeError("boom")):
        assert bq_sync.run_nightly_sync() == 1


# ── scheduled_sync.main ───────────────────────────────────────────────────────

def test_main_runs_bq_even_when_feed_refresh_fails():
    with patch.object(scheduled_sync, "_run_priceshape_refresh", return_value=1), \
         patch("bigquery.sync.run_nightly_sync", return_value=0) as mock_bq:
        assert scheduled_sync.main() == 1
        mock_bq.assert_called_once()


def test_main_runs_bq_when_feed_refresh_skipped():
    # Overgeslagen feed-refresh (exit 0) mag de BQ-stap niet blokkeren.
    with patch.object(scheduled_sync, "_run_priceshape_refresh", return_value=0), \
         patch("bigquery.sync.run_nightly_sync", return_value=0) as mock_bq:
        assert scheduled_sync.main() == 0
        mock_bq.assert_called_once()


def test_main_bq_failure_marks_run_failed():
    with patch.object(scheduled_sync, "_run_priceshape_refresh", return_value=0), \
         patch("bigquery.sync.run_nightly_sync", return_value=1):
        assert scheduled_sync.main() == 1
