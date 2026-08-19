"""
Tests voor de feed_outage-samenvatting op de PriceShape-connectorkaart
(routes/connectors.py::_priceshape_feed_outage).
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import models
from main import app
from database import SessionLocal
from routes.connectors import _priceshape_feed_outage


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass


def _make_ps_job(db, status, error_message=None, delta_seconds=0):
    from engine.import_engine import new_batch_id
    job = models.ImportJob(
        batch_id=new_batch_id(),
        upload_type="api_sync_priceshape",
        filename="handmatige-sync-priceshape",
        source="API-Sync",
        status=status,
        rows_processed=0,
        rows_failed=0,
        rows_duplicates=0,
        error_message=error_message,
        error_log=([{"rij": None, "veld": None, "bericht": error_message}]
                   if error_message else []),
        created_at=datetime.utcnow() + timedelta(seconds=delta_seconds),
        completed_at=datetime.utcnow() + timedelta(seconds=delta_seconds),
    )
    db.add(job)
    db.commit()
    return job.id


def _cleanup(db, *job_ids):
    db.query(models.ImportJob).filter(
        models.ImportJob.id.in_(list(job_ids))).delete(synchronize_session=False)
    db.commit()
    db.close()


class TestPriceshapeFeedOutage:

    def test_no_jobs_means_no_outage(self, client):
        db = SessionLocal()
        try:
            # Alleen geldig als er geen recentere mislukte job bestaat; maak
            # een verse succesvolle job zodat de meest recente job slaagt.
            ok_id = _make_ps_job(db, "geimporteerd", delta_seconds=10)
            assert _priceshape_feed_outage(db) is None
        finally:
            _cleanup(db, ok_id)

    def test_network_failure_reports_outage(self, client):
        db = SessionLocal()
        ok_id = _make_ps_job(db, "geimporteerd", delta_seconds=-3600)
        fail_id = _make_ps_job(
            db, "fout",
            error_message="PriceShape feed niet bereikbaar: connection refused",
            delta_seconds=20,
        )
        try:
            outage = _priceshape_feed_outage(db)
            assert outage is not None
            # Laatste geslaagde sync was ~1 uur geleden → warning (<24u).
            assert outage["severity"] == "warning"
            assert outage["unreached_hours"] is not None
            assert outage["unreached_hours"] < 24
            assert "niet bereikt" in outage["unreached_text"]
            assert outage["failed_at"] is not None
            assert outage["last_success_at"] is not None
            assert "connection refused" in outage["error_message"]
        finally:
            _cleanup(db, ok_id, fail_id)

    def test_never_succeeded_is_error(self, client):
        db = SessionLocal()
        # Verwijder tijdelijk niets: een fail als meest recente job zonder
        # eerdere succesjobs kan niet gegarandeerd worden in de gedeelde DB,
        # dus test in plaats daarvan de >24u-tak met een oude succesjob.
        ok_id = _make_ps_job(db, "geimporteerd",
                             delta_seconds=-3 * 24 * 3600)
        fail_id = _make_ps_job(
            db, "fout",
            error_message="PriceShape feed niet bereikbaar: timeout",
            delta_seconds=20,
        )
        try:
            outage = _priceshape_feed_outage(db)
            assert outage is not None
            # Bestaat er een recentere geslaagde sync (van een echte feed-sync
            # in de dev-DB), dan is warning correct; anders >24u → error.
            newest_ok = (
                db.query(models.ImportJob)
                .filter(models.ImportJob.upload_type == "api_sync_priceshape",
                        models.ImportJob.status == "geimporteerd")
                .order_by(models.ImportJob.created_at.desc())
                .first()
            )
            age_h = (datetime.utcnow() - (newest_ok.completed_at
                                          or newest_ok.created_at)
                     ).total_seconds() / 3600.0
            expected = "warning" if age_h <= 24 else "error"
            assert outage["severity"] == expected
        finally:
            _cleanup(db, ok_id, fail_id)

    def test_non_network_failure_is_ignored(self, client):
        db = SessionLocal()
        fail_id = _make_ps_job(
            db, "fout",
            error_message="Validatiefout: kolom ontbreekt",
            delta_seconds=20,
        )
        try:
            assert _priceshape_feed_outage(db) is None
        finally:
            _cleanup(db, fail_id)
