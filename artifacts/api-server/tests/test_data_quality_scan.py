"""
Tests voor de automatische datakwaliteits-scan (services/data_quality_scan.py
+ services/data_quality_scheduler.py) — taak: scheduler + signalen/notificaties
voor nieuwe of verergerende error-issues, en zichtbare "laatste scan" in de UI.
"""
import os
import sys
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal, Base, engine
import models

# Zorg dat nieuwe tabellen (data_quality_scan_run) ook bestaan wanneer deze
# module vóór de app-lifespan draait (bijv. losse pytest-aanroep).
Base.metadata.create_all(bind=engine)
from services.data_quality_scan import (
    _classify_change, run_quality_scan, last_scan_info, SIGNAL_ENGINE,
)

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
PFX = f"DQSCAN-{uuid.uuid4().hex[:8]}"


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
    s.rollback()
    s.close()


def _fake_issue(code: str, severity: str = "error", count: int = 5) -> dict:
    return {
        "issue_code": code, "issue_type": code, "severity": severity,
        "title": f"Test issue {code}", "message": "testbericht",
        "affected_count": count, "source": "Systeem", "module": "Test",
        "business_impact": "testimpact", "suggested_action": "testactie",
        "sku_id": None,
    }


import routes.data_quality as dq_module

_REAL_DETECT = dq_module._detect_issues


def _detect_plus(issues: list[dict], seen_real_codes: set | None = None):
    """Wrap de ECHTE detecties en voeg synthetische test-issues toe.

    Nooit een kale synthetische lijst aan _sync_issue_registry geven: die
    auto-resolvet alles wat niet in de lijst zit en zou zo echte issues in de
    gedeelde database stilletjes op 'opgelost' zetten.
    """
    def detect(db, total_skus):
        real = _REAL_DETECT(db, total_skus)
        if seen_real_codes is not None:
            seen_real_codes.update(d["issue_code"] for d in real)
        return real + issues
    return detect


def _cleanup(code: str):
    s = SessionLocal()
    try:
        s.query(models.DataQualityIssue).filter(
            models.DataQualityIssue.issue_code == code).delete()
        s.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.engine == SIGNAL_ENGINE,
            models.IntelligenceSignal.entity_id == code).delete()
        s.commit()
    finally:
        s.close()


# ─── _classify_change ────────────────────────────────────────────────────────

def test_classify_new_error():
    d = _fake_issue("X", "error", 5)
    assert _classify_change("X", d, {}) == "nieuw"


def test_classify_reopened_error():
    d = _fake_issue("X", "error", 5)
    prev = {"X": {"status": "opgelost", "severity": "error", "affected_count": 5}}
    assert _classify_change("X", d, prev) == "heropend"


def test_classify_reopened_warning_alerts_too():
    """Een heropend issue alerteert ongeacht severity (terugkeer-detectie)."""
    d = _fake_issue("X", "warning", 5)
    prev = {"X": {"status": "opgelost", "severity": "warning", "affected_count": 5}}
    assert _classify_change("X", d, prev) == "heropend"


def test_classify_worsened_count():
    d = _fake_issue("X", "error", 10)
    prev = {"X": {"status": "open", "severity": "error", "affected_count": 5}}
    assert _classify_change("X", d, prev) == "verergerd"


def test_classify_escalated_severity():
    d = _fake_issue("X", "error", 5)
    prev = {"X": {"status": "open", "severity": "warning", "affected_count": 5}}
    assert _classify_change("X", d, prev) == "verergerd"


def test_classify_unchanged_error_is_quiet():
    d = _fake_issue("X", "error", 5)
    prev = {"X": {"status": "open", "severity": "error", "affected_count": 5}}
    assert _classify_change("X", d, prev) is None


def test_classify_new_warning_signals_too():
    """Ook nieuwe warning/info-issues waarschuwen de eigenaar."""
    d = _fake_issue("X", "warning", 99)
    assert _classify_change("X", d, {}) == "nieuw"


def test_classify_unchanged_open_warning_stays_silent():
    d = _fake_issue("X", "warning", 5)
    prev = {"X": {"status": "open", "severity": "warning", "affected_count": 5}}
    assert _classify_change("X", d, prev) is None


# ─── run_quality_scan ────────────────────────────────────────────────────────

def test_scan_publishes_signal_and_records_run(db):
    code = f"{PFX}_NEW_ERR"
    snapshot_before = {
        r.issue_code: (r.status, r.owner)
        for r in db.query(models.DataQualityIssue).all()
    }
    try:
        real_codes: set = set()
        with patch.object(dq_module, "_detect_issues",
                          side_effect=_detect_plus([_fake_issue(code, "error", 7)],
                                                   real_codes)), \
             patch("services.data_quality_scan_scheduler._notify_issue") as mock_alert:
            result = run_quality_scan(db, triggered_by="scheduler")
        run = result["scan_run"]
        assert run.status == "geslaagd"
        assert run.triggered_by == "scheduler"
        assert run.new_or_worse_errors >= 1
        assert run.signals_published >= 1
        assert result["changes"].get(code) == "new"
        own_calls = [c for c in mock_alert.call_args_list
                     if c.args[1].issue_code == code]
        assert len(own_calls) == 1
        assert own_calls[0].args[2] == "new"

        sig = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.engine == SIGNAL_ENGINE,
            models.IntelligenceSignal.entity_id == code,
            models.IntelligenceSignal.status == "active").first()
        assert sig is not None
        assert sig.severity == "high"
        assert sig.explanation
        assert sig.evidence["issue_code"] == code
    finally:
        _cleanup(code)
    # Integriteit: de test zelf mag bestaande registry-rijen niet wijzigen.
    # De echte detector mag verouderde rijen legitiem auto-resolven; daarom
    # controleren we alleen rijen die de echte detectie nog steeds oplevert
    # (die moeten open + ongewijzigd blijven) en dat eigenaren nooit wijzigen.
    s = SessionLocal()
    try:
        after = {r.issue_code: (r.status, r.owner)
                 for r in s.query(models.DataQualityIssue).all()}
    finally:
        s.close()
    for k, v in snapshot_before.items():
        if k in real_codes:
            assert after.get(k) == v, f"testrun wijzigde actief registry-item {k}"
        elif k in after:
            assert after[k][1] == v[1], f"testrun wijzigde eigenaar van {k}"


def test_scan_no_duplicate_signal_when_unchanged(db):
    code = f"{PFX}_STABLE"
    try:
        issue = _fake_issue(code, "error", 3)
        with patch.object(dq_module, "_detect_issues",
                          side_effect=_detect_plus([issue])), \
             patch("services.data_quality_scan_scheduler._notify_issue"):
            r1 = run_quality_scan(db, triggered_by="scheduler")
            r2 = run_quality_scan(db, triggered_by="scheduler")
        assert r1["scan_run"].signals_published >= 1
        assert code not in r2["changes"], \
            "Onveranderd issue mag in run 2 geen nieuw signaal geven"
    finally:
        _cleanup(code)


def test_scan_failure_recorded(db):
    with patch("routes.data_quality._detect_issues", side_effect=RuntimeError("kapot")):
        with pytest.raises(RuntimeError):
            run_quality_scan(db, triggered_by="scheduler")
    info = last_scan_info(db)
    assert info is not None
    assert info["status"] == "fout"
    assert "kapot" in (info["error_message"] or "")


# ─── API / dashboard ─────────────────────────────────────────────────────────

def test_dashboard_report_includes_last_scan(client, auth):
    resp = client.get("/api/data-quality", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["last_scan"] is not None
    assert body["last_scan"]["triggered_by"] == "dashboard"
    assert body["last_scan"]["status"] == "geslaagd"
    assert body["last_scan"]["finished_at"]


# ─── Scheduler helpers ───────────────────────────────────────────────────────

def test_run_scan_once_never_raises_and_reports_failure():
    from services import data_quality_scheduler as sched
    with patch("services.data_quality_scan.run_quality_scan",
               side_effect=RuntimeError("boem")):
        assert sched.run_scan_once() is False  # gooit nooit, meldt wél falen


def test_oneshot_exit_codes():
    """One-shot mode (Scheduled Deployment): 0 bij succes, 1 bij falen."""
    from services import data_quality_scheduler as sched
    with patch.object(sched, "ensure_schema") as mock_schema, \
         patch.object(sched, "run_scan_once", return_value=True):
        assert sched.main_oneshot() == 0
        assert mock_schema.called  # schema-bootstrap vóór de scan
    with patch.object(sched, "ensure_schema"), \
         patch.object(sched, "run_scan_once", return_value=False):
        assert sched.main_oneshot() == 1
    with patch.object(sched, "ensure_schema", side_effect=RuntimeError("db weg")):
        assert sched.main_oneshot() == 1


def test_ensure_schema_creates_scan_table():
    """Schema-bootstrap maakt data_quality_scan_run aan (idempotent)."""
    from sqlalchemy import inspect as sa_inspect
    from services.data_quality_scheduler import ensure_schema
    ensure_schema()
    assert "data_quality_scan_run" in sa_inspect(engine).get_table_names()


def test_int_env_parsing():
    from services.data_quality_scheduler import _int_env
    with patch.dict(os.environ, {"DQ_TEST_X": "3600"}):
        assert _int_env("DQ_TEST_X", 10) == 3600
    with patch.dict(os.environ, {"DQ_TEST_X": "-5"}):
        assert _int_env("DQ_TEST_X", 10) == 10
    with patch.dict(os.environ, {"DQ_TEST_X": "abc"}):
        assert _int_env("DQ_TEST_X", 10) == 10
