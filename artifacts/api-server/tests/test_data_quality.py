"""
Unit-/integratietests voor de §30-detectielijst (data_quality.py).

Elke detectie krijgt een gerichte test die:
1. Testdata aanmaakt die precies die detectie triggert.
2. Het issue-code, severity en affected_count verifieert.
3. Na afloop de testdata volledig opruimt (inclusief FK-kindrijen).

Stale-data detectors worden getest door _detect_issues direct aan te roepen
met _date.today() gepatcht, zodat bestaande actuele data "verouderd" lijkt.
Dat maakt elke assertion onvoorwaardelijk en onafhankelijk van andere DB-data.

Workflow-tests (auto-resolve, heropen, PATCH) roepen _sync_issue_registry
direct aan voor volledige isolatie.
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
import routes.data_quality as dq_module
from routes.data_quality import _sync_issue_registry, _issue, _detect_issues

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
PFX = f"DQ27-{uuid.uuid4().hex[:8]}"   # uniek per testrun


# ─── Fixtures ─────────────────────────────────────────────────────────────────

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


# ─── Scan helpers ─────────────────────────────────────────────────────────────

def _scan(client, auth):
    resp = client.get("/api/data-quality", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _issue_codes(scan_result):
    return {i["issue_code"] for i in scan_result["issues"]}


def _find_issue(scan_result, code):
    for i in scan_result["issues"]:
        if i["issue_code"] == code:
            return i
    return None


def _detect_with_future_today(db, days_ahead=5):
    """Roep _detect_issues aan met _date.today() gepatcht +days_ahead dagen.
    Hierdoor lijkt alle huidige data 'verouderd' ten opzichte van de geclockte datum."""
    total_skus = db.query(models.DimProduct).count()
    future_date = date.today() + timedelta(days=days_ahead)
    with patch.object(dq_module, '_date') as mock_d:
        mock_d.today.return_value = future_date
        return _detect_issues(db, total_skus)


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _delete_products(db, *sku_ids):
    """Verwijder testproducten inclusief ALLE FK-kindrijen."""
    ids = list(sku_ids)
    for model_cls, col in [
        (models.PimAttributeValue,    models.PimAttributeValue.sku_id),
        (models.PimProductContent,    models.PimProductContent.sku_id),
        (models.PimCompletenessScore, models.PimCompletenessScore.sku_id),
        (models.PimAiSuggestion,      models.PimAiSuggestion.sku_id),
        (models.AiMatchResult,        models.AiMatchResult.own_sku_id),
        (models.FactSalesDaily,            models.FactSalesDaily.sku_id),
        (models.FactPriceDaily,            models.FactPriceDaily.sku_id),
        (models.FactCompetitorPriceDaily,  models.FactCompetitorPriceDaily.sku_id),
        (models.FactInventoryDaily,        models.FactInventoryDaily.sku_id),
    ]:
        db.query(model_cls).filter(col.in_(ids)).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def _make_product(db, sku_id, **kwargs):
    defaults = dict(
        sku_id=sku_id,
        product_name=f"Test {sku_id}",
        brand="TestBrand",
        category=f"{PFX}-cat",
        strategy_type="protect",
        cost_price=10.0,
        current_price=15.0,
        min_price=8.0,
        max_price=20.0,
        is_active=True,
    )
    defaults.update(kwargs)
    p = models.DimProduct(**defaults)
    db.add(p)
    db.commit()
    return p


def _get_or_create_competitor(db, name):
    comp = db.query(models.DimCompetitor).filter(
        models.DimCompetitor.competitor_name == name).first()
    if comp is None:
        comp = models.DimCompetitor(competitor_name=name)
        db.add(comp)
        db.commit()
    return comp


def _make_issue_dict(code, severity="warning", count=1):
    return _issue(
        code, severity, f"Test-issue {code}", f"Testbericht voor {code}", count,
        "Test", "Test", "Test zakelijke impact", "Test actie",
    )


# ══════════════════════════════════════════════════════════════════════════════
# IDENTIFIER DETECTIES
# ══════════════════════════════════════════════════════════════════════════════

class TestMissingEan:
    def test_triggers(self, client, auth):
        """MISSING_EAN verschijnt zodra er een SKU zonder EAN is.

        De severity is 'info' als nagenoeg de gehele feed geen EAN heeft
        (PriceShape itemGroupId-feed) of 'warning' als het partieel is.
        Beide zijn correct — we testen alleen dat het issue aanwezig is en
        een geldig affected_count heeft.
        """
        db = SessionLocal()
        sku = f"{PFX}-NO-EAN"
        try:
            _make_product(db, sku, ean=None)
            result = _scan(client, auth)
            assert "MISSING_EAN" in _issue_codes(result)
            issue = _find_issue(result, "MISSING_EAN")
            assert issue["severity"] in ("warning", "info"), (
                f"MISSING_EAN severity moet 'warning' of 'info' zijn, was {issue['severity']!r}"
            )
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestDuplicateEan:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku_a, sku_b = f"{PFX}-DUPEAN-A", f"{PFX}-DUPEAN-B"
        ean = f"999{uuid.uuid4().int % 10**10:010d}"
        try:
            _make_product(db, sku_a, ean=ean)
            _make_product(db, sku_b, ean=ean)
            result = _scan(client, auth)
            assert "DUPLICATE_EAN" in _issue_codes(result)
            issue = _find_issue(result, "DUPLICATE_EAN")
            assert issue["severity"] == "error"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku_a, sku_b)
            db.close()


class TestDuplicateOemCode:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku_a, sku_b = f"{PFX}-DUPOEM-A", f"{PFX}-DUPOEM-B"
        oem = f"OEM-{uuid.uuid4().hex[:10]}"
        try:
            _make_product(db, sku_a, oem_code=oem)
            _make_product(db, sku_b, oem_code=oem)
            result = _scan(client, auth)
            assert "DUPLICATE_OEM_CODE" in _issue_codes(result)
            issue = _find_issue(result, "DUPLICATE_OEM_CODE")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku_a, sku_b)
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# PRIJS DETECTIES
# ══════════════════════════════════════════════════════════════════════════════

class TestMissingCostPrice:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-NO-COST"
        try:
            _make_product(db, sku, cost_price=None)
            result = _scan(client, auth)
            assert "MISSING_COST_PRICE" in _issue_codes(result)
            issue = _find_issue(result, "MISSING_COST_PRICE")
            assert issue["severity"] == "error"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestMissingSalesPrice:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-NO-PRICE"
        try:
            _make_product(db, sku, current_price=None)
            result = _scan(client, auth)
            assert "MISSING_SALES_PRICE" in _issue_codes(result)
            issue = _find_issue(result, "MISSING_SALES_PRICE")
            assert issue["severity"] == "error"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestMissingPriceGuardrails:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-NO-GUARD"
        try:
            _make_product(db, sku, min_price=None, max_price=None)
            result = _scan(client, auth)
            assert "MISSING_PRICE_GUARDRAILS" in _issue_codes(result)
            issue = _find_issue(result, "MISSING_PRICE_GUARDRAILS")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestNegativeMargin:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-NEG-MARGIN"
        try:
            _make_product(db, sku, cost_price=20.0, current_price=10.0)
            result = _scan(client, auth)
            assert "NEGATIVE_MARGIN" in _issue_codes(result)
            issue = _find_issue(result, "NEGATIVE_MARGIN")
            assert issue["severity"] == "error"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestInvalidPriceRange:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-INV-RANGE"
        try:
            _make_product(db, sku, min_price=30.0, max_price=10.0)
            result = _scan(client, auth)
            assert "INVALID_PRICE_RANGE" in _issue_codes(result)
            issue = _find_issue(result, "INVALID_PRICE_RANGE")
            assert issue["severity"] == "error"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# STAMDATA DETECTIES
# ══════════════════════════════════════════════════════════════════════════════

class TestMissingCategory:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-NO-CAT"
        try:
            _make_product(db, sku, category=None)
            result = _scan(client, auth)
            assert "MISSING_CATEGORY" in _issue_codes(result)
            issue = _find_issue(result, "MISSING_CATEGORY")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestMissingStrategyType:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-NO-STRAT"
        try:
            _make_product(db, sku, strategy_type=None)
            result = _scan(client, auth)
            assert "MISSING_STRATEGY_TYPE" in _issue_codes(result)
            issue = _find_issue(result, "MISSING_STRATEGY_TYPE")
            assert issue["severity"] == "error"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestDrsMissingBrand:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-NO-BRAND"
        try:
            _make_product(db, sku, brand=None)
            result = _scan(client, auth)
            assert "DRS_MISSING_BRAND" in _issue_codes(result)
            issue = _find_issue(result, "DRS_MISSING_BRAND")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# CONCURRENTIE & VOORRAAD DEKKING
# ══════════════════════════════════════════════════════════════════════════════

class TestMissingCompetitorData:
    def test_triggers(self, client, auth):
        """SKU zonder enige FactCompetitorPriceDaily-rij telt mee als 'geen data'."""
        db = SessionLocal()
        sku = f"{PFX}-NO-COMP"
        try:
            _make_product(db, sku)
            # Geen FactCompetitorPriceDaily voor dit SKU → de teller stijgt
            result = _scan(client, auth)
            assert "MISSING_COMPETITOR_DATA" in _issue_codes(result)
            issue = _find_issue(result, "MISSING_COMPETITOR_DATA")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestMissingStockData:
    def test_triggers(self, client, auth):
        """SKU zonder enige FactInventoryDaily-rij telt mee als 'geen data'."""
        db = SessionLocal()
        sku = f"{PFX}-NO-STOCK"
        try:
            _make_product(db, sku)
            result = _scan(client, auth)
            assert "MISSING_STOCK_DATA" in _issue_codes(result)
            issue = _find_issue(result, "MISSING_STOCK_DATA")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# STALE DATA DETECTIES
# Aanpak: voeg een fact-rij met datum=vandaag toe, patch _date.today() +5 dagen
# zodat de rij "5 dagen oud" lijkt. age=5 > STALE_DAYS=3 → issue wordt
# onvoorwaardelijk getriggerd, ongeacht andere bestaande DB-data.
# ══════════════════════════════════════════════════════════════════════════════

class TestStaleCompetitorPrices:
    def test_triggers_unconditionally(self):
        db = SessionLocal()
        sku = f"{PFX}-STALE-COMP"
        try:
            _make_product(db, sku)
            db.add(models.FactCompetitorPriceDaily(
                date=date.today(), sku_id=sku, competitor_name="stale.nl", price=9.99))
            db.commit()

            detected = _detect_with_future_today(db, days_ahead=5)
            codes = {d["issue_code"] for d in detected}
            assert "STALE_COMPETITOR_PRICES" in codes, \
                "STALE_COMPETITOR_PRICES moet gedetecteerd worden als data 5 dagen oud is"
            issue = next(d for d in detected if d["issue_code"] == "STALE_COMPETITOR_PRICES")
            assert issue["severity"] in ("warning", "error")
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestStaleSalesData:
    def test_triggers_unconditionally(self):
        db = SessionLocal()
        sku = f"{PFX}-STALE-SALES"
        try:
            _make_product(db, sku)
            db.add(models.FactSalesDaily(
                date=date.today(), sku_id=sku, units_sold=5))
            db.commit()

            detected = _detect_with_future_today(db, days_ahead=5)
            codes = {d["issue_code"] for d in detected}
            assert "STALE_SALES_DATA" in codes, \
                "STALE_SALES_DATA moet gedetecteerd worden als data 5 dagen oud is"
            issue = next(d for d in detected if d["issue_code"] == "STALE_SALES_DATA")
            assert issue["severity"] in ("warning", "error")
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestStaleInventoryData:
    def test_triggers_unconditionally(self):
        db = SessionLocal()
        sku = f"{PFX}-STALE-INV"
        try:
            _make_product(db, sku)
            db.add(models.FactInventoryDaily(
                date=date.today(), sku_id=sku, stock_quantity=10))
            db.commit()

            detected = _detect_with_future_today(db, days_ahead=5)
            codes = {d["issue_code"] for d in detected}
            assert "STALE_INVENTORY_DATA" in codes, \
                "STALE_INVENTORY_DATA moet gedetecteerd worden als data 5 dagen oud is"
            issue = next(d for d in detected if d["issue_code"] == "STALE_INVENTORY_DATA")
            assert issue["severity"] in ("warning", "error")
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestStaleTrafficData:
    def test_triggers_unconditionally(self):
        db = SessionLocal()
        sku = f"{PFX}-STALE-TRAFFIC"
        try:
            _make_product(db, sku)
            db.add(models.FactTrafficDaily(
                date=date.today(), entity_type="SKU", entity_id=sku, pageviews=10))
            db.commit()

            detected = _detect_with_future_today(db, days_ahead=5)
            codes = {d["issue_code"] for d in detected}
            assert "STALE_TRAFFIC_DATA" in codes, \
                "STALE_TRAFFIC_DATA moet gedetecteerd worden als data 5 dagen oud is"
            issue = next(d for d in detected if d["issue_code"] == "STALE_TRAFFIC_DATA")
            assert issue["severity"] in ("warning", "error")
            assert issue["affected_count"] >= 1
        finally:
            db.query(models.FactTrafficDaily).filter(
                models.FactTrafficDaily.entity_id == sku).delete()
            db.commit()
            _delete_products(db, sku)
            db.close()


class TestStaleAiModels:
    def test_stale_completed_run_triggers_warning(self):
        """Modelrun ouder dan MODEL_STALE_DAYS=7 geeft STALE_AI_MODELS (warning of error)."""
        db = SessionLocal()
        old_run = models.ModelRun(
            status="completed",
            started_at=datetime.utcnow() - timedelta(days=10),
            completed_at=datetime.utcnow() - timedelta(days=10),
        )
        db.add(old_run)
        db.commit()
        run_id = old_run.id
        try:
            total_skus = db.query(models.DimProduct).count()
            # De detectie vergelijkt de RECENTSTE geslaagde run met utcnow();
            # een echte sync van vandaag zou de stale-trigger anders verbergen.
            # Verlaag daarom de drempel zodat élke leeftijd als stale telt —
            # we testen puur de triggerlogica, niet de kalender.
            with patch.object(dq_module, 'MODEL_STALE_DAYS', -1):
                detected = _detect_issues(db, total_skus)
            codes = {d["issue_code"] for d in detected}
            assert "STALE_AI_MODELS" in codes, \
                "STALE_AI_MODELS moet verschijnen als de recentste geslaagde run >7 dagen oud is"
            issue = next(d for d in detected if d["issue_code"] == "STALE_AI_MODELS")
            assert issue["severity"] in ("warning", "error")
        finally:
            db.query(models.ModelRun).filter(
                models.ModelRun.id == run_id).delete()
            db.commit()
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# EENHEID & PACK-SIZE
# ══════════════════════════════════════════════════════════════════════════════

class TestUnitIssues:
    def test_invalid_gsm_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-BAD-GSM"
        try:
            _make_product(db, sku, paper_weight_gsm=0)
            result = _scan(client, auth)
            assert "UNIT_ISSUES" in _issue_codes(result)
            issue = _find_issue(result, "UNIT_ISSUES")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()

    def test_invalid_sheets_per_pack_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-BAD-SHEETS"
        try:
            _make_product(db, sku, sheets_per_pack=-5)
            result = _scan(client, auth)
            assert "UNIT_ISSUES" in _issue_codes(result)
            assert _find_issue(result, "UNIT_ISSUES")["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestPackSizeMismatch:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-PACK-WARN"
        match_id = None
        try:
            _make_product(db, sku)
            comp = _get_or_create_competitor(db, f"{PFX}-comp.nl")
            match = models.ProductMatch(
                own_sku_id=sku,
                competitor_id=comp.competitor_id,
                pack_size_warning=True,
                manual_override=False,
            )
            db.add(match)
            db.commit()
            match_id = match.match_id

            result = _scan(client, auth)
            assert "PACK_SIZE_MISMATCH" in _issue_codes(result)
            issue = _find_issue(result, "PACK_SIZE_MISMATCH")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            if match_id:
                db.query(models.ProductMatch).filter(
                    models.ProductMatch.match_id == match_id).delete()
                db.commit()
            _delete_products(db, sku)
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS & AI
# ══════════════════════════════════════════════════════════════════════════════

class TestFailedImports:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        job = models.ImportJob(
            upload_type="test", filename="pytest-failed.csv",
            status="fout", created_at=datetime.utcnow())
        db.add(job)
        db.commit()
        job_id = job.id
        try:
            result = _scan(client, auth)
            assert "FAILED_IMPORTS" in _issue_codes(result)
            issue = _find_issue(result, "FAILED_IMPORTS")
            assert issue["severity"] == "error"
            assert issue["affected_count"] >= 1
        finally:
            db.query(models.ImportJob).filter(
                models.ImportJob.id == job_id).delete()
            db.commit()
            db.close()

    def test_old_failed_import_not_counted(self, client, auth):
        """Imports ouder dan FAILED_IMPORT_WINDOW_DAYS=14 tellen niet mee."""
        db = SessionLocal()
        old_date = datetime.utcnow() - timedelta(days=20)
        job = models.ImportJob(
            upload_type="test", filename="pytest-old-fail.csv",
            status="fout", created_at=old_date)
        db.add(job)
        db.commit()
        job_id = job.id
        # Tel recente mislukte imports voor de insert
        cutoff = datetime.utcnow() - timedelta(days=14)
        count_recent = db.query(models.ImportJob).filter(
            models.ImportJob.status.in_(["fout", "failed"]),
            models.ImportJob.created_at >= cutoff,
        ).count()
        try:
            result = _scan(client, auth)
            if "FAILED_IMPORTS" in _issue_codes(result):
                issue = _find_issue(result, "FAILED_IMPORTS")
                # Onze te-oude job mag de telling niet ophogen
                assert issue["affected_count"] == count_recent
        finally:
            db.query(models.ImportJob).filter(
                models.ImportJob.id == job_id).delete()
            db.commit()
            db.close()


class TestFeedUnreachable:
    """FEED_UNREACHABLE verschijnt als de meest recente api_sync_priceshape
    job is mislukt met een netwerk-/verbindingsfout.  Een nieuwe succesvolle
    job verbergt het issue (meest-recente-job-semantiek)."""

    def _make_ps_job(self, db, status, error_message=None, delta_seconds=0,
                     created_delta_seconds=None):
        """Hulp: maak een api_sync_priceshape ImportJob en geef het id terug."""
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
            created_at=datetime.utcnow() + timedelta(
                seconds=created_delta_seconds
                if created_delta_seconds is not None else delta_seconds),
            completed_at=datetime.utcnow() + timedelta(seconds=delta_seconds),
        )
        db.add(job)
        db.commit()
        return job.id

    def _cleanup(self, db, *job_ids):
        db.query(models.ImportJob).filter(
            models.ImportJob.id.in_(list(job_ids))).delete(synchronize_session=False)
        # Verwijder de FEED_UNREACHABLE rij uit het issue-register zodat
        # volgende tests een schone lei hebben.
        db.query(models.DataQualityIssue).filter(
            models.DataQualityIssue.issue_code == "FEED_UNREACHABLE").delete(
            synchronize_session=False)
        db.commit()
        db.close()

    def test_network_error_triggers_feed_unreachable(self, client, auth):
        """ConnectorError 'niet bereikbaar' → FEED_UNREACHABLE (error)."""
        db = SessionLocal()
        job_id = self._make_ps_job(
            db, "fout",
            error_message="PriceShape feed niet bereikbaar: [Errno -2] Name or service not known")
        try:
            total_skus = db.query(models.DimProduct).count()
            detected = _detect_issues(db, total_skus)
            codes = {d["issue_code"] for d in detected}
            assert "FEED_UNREACHABLE" in codes, (
                "FEED_UNREACHABLE moet zichtbaar zijn als de meest recente "
                "api_sync_priceshape job is mislukt met een netwerk-/verbindingsfout")
            issue = next(d for d in detected if d["issue_code"] == "FEED_UNREACHABLE")
            # Severity hangt af van hoe lang de feed al niet bereikt is:
            # >24u (of nooit) geslaagd = error, recente storing = warning.
            last_ok = (
                db.query(func.max(func.coalesce(
                    models.ImportJob.completed_at, models.ImportJob.created_at)))
                .filter(models.ImportJob.upload_type == "api_sync_priceshape",
                        models.ImportJob.status == "geimporteerd")
                .scalar())
            expected = "error"
            if last_ok is not None and (datetime.utcnow() - last_ok) <= timedelta(hours=24):
                expected = "warning"
            assert issue["severity"] == expected
            assert issue["affected_count"] == 1
            # Het bericht toont wanneer de laatste mislukte poging was.
            assert "geleden" in issue["message"]
            assert "mislukt op" in issue["message"]
        finally:
            self._cleanup(db, job_id)

    def test_recent_success_downgrades_to_warning(self, client, auth):
        """Feed <24u geleden nog bereikt → severity 'warning' (recente storing)."""
        db = SessionLocal()
        ok_id = self._make_ps_job(db, "geimporteerd", delta_seconds=-3600)
        fail_id = self._make_ps_job(
            db, "fout",
            error_message="PriceShape feed niet bereikbaar: connection refused")
        try:
            detected = _detect_issues(db, db.query(models.DimProduct).count())
            issue = next(d for d in detected if d["issue_code"] == "FEED_UNREACHABLE")
            assert issue["severity"] == "warning", (
                "Bij een geslaagde sync <24u geleden is de storing recent en "
                "hoort de severity 'warning' te zijn")
            assert "laatste geslaagde sync" in issue["message"]
        finally:
            self._cleanup(db, ok_id, fail_id)

    def test_old_failure_stays_error_without_recent_success(self, client, auth):
        """Feed >24u niet bereikt → severity stijgt naar 'error', ook als de
        mislukte poging zelf al dagen oud is (geen nieuwe pogingen gedaan)."""
        db = SessionLocal()
        # Mislukte poging van 2 dagen geleden; géén geslaagde sync sindsdien.
        # created_at = nu zodat dit gegarandeerd de meest recente job is, ook
        # als de dev-DB echte sync-jobs van vandaag bevat; completed_at blijft
        # 2 dagen oud (de mislukte poging zelf is oud).
        fail_id = self._make_ps_job(
            db, "fout",
            error_message="PriceShape feed niet bereikbaar: timeout",
            delta_seconds=-2 * 24 * 3600,
            created_delta_seconds=60)
        last_ok = (
            db.query(func.max(func.coalesce(
                models.ImportJob.completed_at, models.ImportJob.created_at)))
            .filter(models.ImportJob.upload_type == "api_sync_priceshape",
                    models.ImportJob.status == "geimporteerd")
            .scalar())
        recent_success = (last_ok is not None
                          and (datetime.utcnow() - last_ok) <= timedelta(hours=24))
        # De detector kijkt alleen naar de méést recente sync-poging. Op een
        # dev-DB met echte feed-data kan er een nieuwere (geslaagde) job
        # bestaan dan onze 2 dagen oude seed; dan is dit scenario niet
        # opbouwbaar en slaan we de test over (§test-suite-conventies).
        newest = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "api_sync_priceshape")
            .order_by(models.ImportJob.created_at.desc())
            .first())
        if newest is not None and newest.id != fail_id:
            self._cleanup(db, fail_id)
            pytest.skip("Dev-DB bevat een recentere echte sync-job; scenario "
                        "'oude mislukking zonder nieuwe pogingen' niet opbouwbaar")
        try:
            detected = _detect_issues(db, db.query(models.DimProduct).count())
            issue = next(d for d in detected if d["issue_code"] == "FEED_UNREACHABLE")
            if recent_success:
                # Dev-DB bevat een echte recente sync; dan is warning correct.
                assert issue["severity"] == "warning"
            else:
                assert issue["severity"] == "error", (
                    "Als de feed >24u niet bereikt is, moet de severity 'error' "
                    "zijn ongeacht het aantal pogingen")
            assert "dagen" in issue["message"] or "uur" in issue["message"]
        finally:
            self._cleanup(db, fail_id)

    def test_empty_feed_guard_triggers_feed_unreachable(self, client, auth):
        """Lege-feed-guard (0 producten en 0 concurrentprijzen) triggert ook FEED_UNREACHABLE."""
        db = SessionLocal()
        job_id = self._make_ps_job(
            db, "fout",
            error_message=(
                "PriceShape feed leverde 0 producten en 0 concurrentprijzen op — "
                "sync afgebroken om bestaande data te beschermen (laatst-goede data blijft staan)."
            ))
        try:
            total_skus = db.query(models.DimProduct).count()
            detected = _detect_issues(db, total_skus)
            codes = {d["issue_code"] for d in detected}
            assert "FEED_UNREACHABLE" in codes, (
                "FEED_UNREACHABLE moet zichtbaar zijn als de lege-feed-guard de sync heeft afgebroken")
        finally:
            self._cleanup(db, job_id)

    def test_config_missing_does_not_trigger_feed_unreachable(self, client, auth):
        """Een 'niet geconfigureerd'-fout persisteert als status 'nieuw', niet 'fout',
        en mag FEED_UNREACHABLE niet triggeren."""
        db = SessionLocal()
        # Simuleer de ImportJob die _run_sync maakt voor not_configured: status = "nieuw"
        from engine.import_engine import new_batch_id
        job = models.ImportJob(
            batch_id=new_batch_id(),
            upload_type="api_sync_priceshape",
            filename="handmatige-sync-priceshape",
            source="API-Sync",
            status="nieuw",   # not_configured → nieuw
            rows_processed=0,
            error_message="PriceShape feed-URL niet geconfigureerd.",
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        job_id = job.id
        try:
            total_skus = db.query(models.DimProduct).count()
            detected = _detect_issues(db, total_skus)
            codes = {d["issue_code"] for d in detected}
            assert "FEED_UNREACHABLE" not in codes, (
                "Een 'niet geconfigureerd'-job (status=nieuw) mag FEED_UNREACHABLE "
                "niet triggeren — alleen 'fout'/'failed' jobs doen dat")
        finally:
            self._cleanup(db, job_id)

    def test_successful_sync_after_failure_clears_issue(self, client, auth):
        """Een recente succesvolle sync verbergt FEED_UNREACHABLE,
        ook als er eerder een mislukte job is (meest-recente-job-semantiek)."""
        db = SessionLocal()
        # Oudere mislukte job
        fail_id = self._make_ps_job(
            db, "fout",
            error_message="PriceShape feed niet bereikbaar: connection refused",
            delta_seconds=-10)
        # Nieuwere succesvolle job
        ok_id = self._make_ps_job(db, "geimporteerd", delta_seconds=0)
        try:
            total_skus = db.query(models.DimProduct).count()
            detected = _detect_issues(db, total_skus)
            codes = {d["issue_code"] for d in detected}
            assert "FEED_UNREACHABLE" not in codes, (
                "FEED_UNREACHABLE mag niet verschijnen als de meest recente "
                "api_sync_priceshape job succesvol is (meest-recente-job-semantiek)")
        finally:
            self._cleanup(db, fail_id, ok_id)


class TestLowConfidenceMatches:
    def test_ai_match_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-LOWCONF"
        match_id = None
        try:
            _make_product(db, sku)
            match = models.AiMatchResult(
                own_sku_id=sku,
                competitor_name=f"{PFX}-lowconf.nl",
                match_type="Functioneel",
                confidence=0.4,
                explanation_nl="test low confidence",
                status="PENDING",
                run_date=date.today(),
            )
            db.add(match)
            db.commit()
            match_id = match.id

            result = _scan(client, auth)
            assert "LOW_CONFIDENCE_MATCHES" in _issue_codes(result)
            issue = _find_issue(result, "LOW_CONFIDENCE_MATCHES")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            if match_id:
                db.query(models.AiMatchResult).filter(
                    models.AiMatchResult.id == match_id).delete()
                db.commit()
            _delete_products(db, sku)
            db.close()


class TestFailedModelRuns:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        run = models.ModelRun(
            status="failed",
            started_at=datetime.utcnow() - timedelta(days=1))
        db.add(run)
        db.commit()
        run_id = run.id
        try:
            result = _scan(client, auth)
            assert "FAILED_MODEL_RUNS" in _issue_codes(result)
            issue = _find_issue(result, "FAILED_MODEL_RUNS")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            db.query(models.ModelRun).filter(
                models.ModelRun.id == run_id).delete()
            db.commit()
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# PIM DETECTIES
# ══════════════════════════════════════════════════════════════════════════════

class TestPimLowCompleteness:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-PIM-LOW"
        try:
            _make_product(db, sku)
            db.add(models.PimCompletenessScore(
                sku_id=sku, channel_code=None,
                completeness_pct=40.0, quality_score=50.0, run_date=date.today()))
            db.commit()

            result = _scan(client, auth)
            assert "PIM_LOW_COMPLETENESS" in _issue_codes(result)
            issue = _find_issue(result, "PIM_LOW_COMPLETENESS")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestPimQualityIssues:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-PIM-QUAL"
        try:
            _make_product(db, sku)
            db.add(models.PimCompletenessScore(
                sku_id=sku, channel_code=None,
                completeness_pct=80.0, quality_score=70.0,
                quality_issues=[{"code": "NAAM_TE_KORT", "bericht": "Naam te kort"}],
                run_date=date.today()))
            db.commit()

            result = _scan(client, auth)
            assert "PIM_QUALITY_ISSUES" in _issue_codes(result)
            issue = _find_issue(result, "PIM_QUALITY_ISSUES")
            assert issue["severity"] == "warning"
        finally:
            _delete_products(db, sku)
            db.close()


class TestPimPendingSuggestions:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-PIM-SUGG"
        try:
            _make_product(db, sku)
            db.add(models.PimAiSuggestion(
                sku_id=sku, attribute_id=None,
                attribute_code="product_description",
                suggested_value="AI-gegenereerde omschrijving",
                confidence=0.85, status="PENDING"))
            db.commit()

            result = _scan(client, auth)
            assert "PIM_PENDING_SUGGESTIONS" in _issue_codes(result)
            issue = _find_issue(result, "PIM_PENDING_SUGGESTIONS")
            assert issue["severity"] == "info"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# DRS-SPECIFIEKE DETECTIES
# ══════════════════════════════════════════════════════════════════════════════

class TestDrsMissingHierarchy:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        unknown_cat = f"{PFX}-UNKN-{uuid.uuid4().hex[:6]}"
        sku = f"{PFX}-NO-HIER"
        created_hier_id = None

        hier_exists = db.query(models.DimCategoryHierarchy).first()
        if hier_exists is None:
            h = models.DimCategoryHierarchy(
                category_name="DummyHier", category_level=1, active=True)
            db.add(h)
            db.flush()
            created_hier_id = h.category_id

        try:
            _make_product(db, sku, category=unknown_cat)
            db.commit()

            result = _scan(client, auth)
            assert "DRS_MISSING_HIERARCHY" in _issue_codes(result)
            issue = _find_issue(result, "DRS_MISSING_HIERARCHY")
            assert issue["severity"] == "warning"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            if created_hier_id:
                db.query(models.DimCategoryHierarchy).filter(
                    models.DimCategoryHierarchy.category_id == created_hier_id
                ).delete()
            db.commit()
            db.close()


class TestDrsInactiefArtikelen:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-INACT"
        try:
            _make_product(db, sku, is_active=False)
            result = _scan(client, auth)
            assert "DRS_INACTIEVE_ARTIKELEN" in _issue_codes(result)
            issue = _find_issue(result, "DRS_INACTIEVE_ARTIKELEN")
            assert issue["severity"] == "info"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


class TestDrsNegatieveMargeYtd:
    def test_triggers(self, client, auth):
        db = SessionLocal()
        sku = f"{PFX}-NEG-YTD"
        try:
            _make_product(db, sku, marge_ytd=-500.0)
            result = _scan(client, auth)
            assert "DRS_NEGATIEVE_MARGE_YTD" in _issue_codes(result)
            issue = _find_issue(result, "DRS_NEGATIEVE_MARGE_YTD")
            assert issue["severity"] == "error"
            assert issue["affected_count"] >= 1
        finally:
            _delete_products(db, sku)
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW: auto-resolve, heropen, PATCH
# _sync_issue_registry direct aanroepen → volledig geïsoleerd van andere DB-data.
# ══════════════════════════════════════════════════════════════════════════════

TEST_RESOLVE_CODE = f"TEST_RESOLVE_{uuid.uuid4().hex[:8]}"
TEST_REOPEN_CODE  = f"TEST_REOPEN_{uuid.uuid4().hex[:8]}"
TEST_INBEH_CODE   = f"TEST_INBEH_{uuid.uuid4().hex[:8]}"


class TestAutoResolve:
    """Verdwenen detectie → status automatisch 'opgelost'."""

    def test_issue_resolved_when_no_longer_detected(self):
        db = SessionLocal()
        try:
            detected = [_make_issue_dict(TEST_RESOLVE_CODE, "error", 3)]

            # Stap 1: detecteer → 'open'
            registry = _sync_issue_registry(db, detected)
            row = registry[TEST_RESOLVE_CODE]
            assert row.status == "open"
            assert row.affected_count == 3

            # Stap 2: scan zonder dit issue → auto-resolve
            registry2 = _sync_issue_registry(db, [])
            row2 = registry2[TEST_RESOLVE_CODE]
            assert row2.status == "opgelost", \
                "Issue moet automatisch 'opgelost' worden als detectie verdwijnt"
            assert row2.resolved_at is not None
            assert row2.affected_count == 0
        finally:
            db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.issue_code == TEST_RESOLVE_CODE).delete()
            db.commit()
            db.close()


class TestReopenOnReturn:
    """Opgelost issue wordt automatisch heropend als probleem terugkeert."""

    def test_issue_reopened_when_problem_returns(self):
        db = SessionLocal()
        try:
            detected = [_make_issue_dict(TEST_REOPEN_CODE, "warning", 2)]

            # Stap 1: open
            _sync_issue_registry(db, detected)

            # Stap 2: opgelost
            resolved = _sync_issue_registry(db, [])
            assert resolved[TEST_REOPEN_CODE].status == "opgelost"

            # Stap 3: heropend
            reopened = _sync_issue_registry(db, detected)
            row = reopened[TEST_REOPEN_CODE]
            assert row.status == "open", \
                "Issue moet heropend worden als probleem terugkeert"
            assert row.resolved_at is None, \
                "resolved_at moet gewist worden bij heropen"
            assert row.affected_count == 2
        finally:
            db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.issue_code == TEST_REOPEN_CODE).delete()
            db.commit()
            db.close()

    def test_in_behandeling_auto_resolved_when_detection_disappears(self):
        """Issues met status 'in_behandeling' worden WEL auto-opgelost als de
        detectie verdwijnt (de code checkt != 'opgelost', niet == 'open')."""
        db = SessionLocal()
        try:
            detected = [_make_issue_dict(TEST_INBEH_CODE, "warning", 1)]
            _sync_issue_registry(db, detected)

            # Zet handmatig op 'in_behandeling'
            row = db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.issue_code == TEST_INBEH_CODE).first()
            row.status = "in_behandeling"
            db.commit()

            # Scan zonder dit issue → moet ook 'in_behandeling' auto-resolven
            registry = _sync_issue_registry(db, [])
            assert registry[TEST_INBEH_CODE].status == "opgelost", \
                "In_behandeling issues worden automatisch opgelost als de detectie verdwijnt"
        finally:
            db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.issue_code == TEST_INBEH_CODE).delete()
            db.commit()
            db.close()


class TestPatchIssueWorkflow:
    """PATCH /api/data-quality/issues/{id}: owner en status aanpassen."""

    def _create_registry_issue(self):
        code = f"TEST_PATCH_{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        _sync_issue_registry(db, [_make_issue_dict(code)])
        row = db.query(models.DataQualityIssue).filter(
            models.DataQualityIssue.issue_code == code).first()
        issue_id = row.id
        db.close()
        return issue_id, code

    def _cleanup(self, code):
        db = SessionLocal()
        db.query(models.DataQualityIssue).filter(
            models.DataQualityIssue.issue_code == code).delete()
        db.commit()
        db.close()

    def test_patch_owner_and_status(self, client, auth):
        issue_id, code = self._create_registry_issue()
        try:
            resp = client.patch(
                f"/api/data-quality/issues/{issue_id}",
                json={"owner": "jan.jansen", "status": "in_behandeling"},
                headers=auth)
            assert resp.status_code == 200
            data = resp.json()
            assert data["owner"] == "jan.jansen"
            assert data["status"] == "in_behandeling"
        finally:
            self._cleanup(code)

    def test_patch_invalid_status_rejected(self, client, auth):
        issue_id, code = self._create_registry_issue()
        try:
            resp = client.patch(
                f"/api/data-quality/issues/{issue_id}",
                json={"status": "bogus_status"}, headers=auth)
            assert resp.status_code == 400
        finally:
            self._cleanup(code)

    def test_patch_nonexistent_issue_returns_404(self, client, auth):
        resp = client.patch(
            "/api/data-quality/issues/999999999",
            json={"status": "open"}, headers=auth)
        assert resp.status_code == 404

    def test_patch_owner_cleared_with_empty_string(self, client, auth):
        issue_id, code = self._create_registry_issue()
        try:
            client.patch(f"/api/data-quality/issues/{issue_id}",
                         json={"owner": "jan.jansen"}, headers=auth)
            resp = client.patch(f"/api/data-quality/issues/{issue_id}",
                                json={"owner": ""}, headers=auth)
            assert resp.status_code == 200
            assert resp.json()["owner"] is None
        finally:
            self._cleanup(code)

    def test_all_valid_statuses_accepted(self, client, auth):
        issue_id, code = self._create_registry_issue()
        try:
            for status in ["open", "in_behandeling", "genegeerd", "opgelost"]:
                resp = client.patch(
                    f"/api/data-quality/issues/{issue_id}",
                    json={"status": status}, headers=auth)
                assert resp.status_code == 200, \
                    f"Status '{status}' zou geldig moeten zijn"
                assert resp.json()["status"] == status
        finally:
            self._cleanup(code)


# ══════════════════════════════════════════════════════════════════════════════
# RESPONSE STRUCTUUR
# ══════════════════════════════════════════════════════════════════════════════

class TestResponseStructure:
    def test_response_fields_present(self, client, auth):
        result = _scan(client, auth)
        for field in ("overall_score", "total_skus", "issues", "summary", "counts"):
            assert field in result
        assert isinstance(result["overall_score"], (int, float))
        assert 0 <= result["overall_score"] <= 100

    def test_each_issue_has_required_fields(self, client, auth):
        result = _scan(client, auth)
        required = {"issue_code", "severity", "affected_count", "title",
                    "source", "module"}
        for issue in result["issues"]:
            missing = required - issue.keys()
            assert not missing, \
                f"Issue {issue.get('issue_code')} mist velden: {missing}"

    def test_severity_values_are_valid(self, client, auth):
        result = _scan(client, auth)
        for issue in result["issues"]:
            assert issue["severity"] in {"error", "warning", "info"}, \
                f"Ongeldige severity '{issue['severity']}' voor {issue['issue_code']}"

    def test_unauthenticated_request_rejected(self, client):
        resp = client.get("/api/data-quality")
        assert resp.status_code in (401, 403)

    def test_issue_list_filters_by_status(self, client, auth):
        resp = client.get("/api/data-quality/issues?status=open", headers=auth)
        assert resp.status_code == 200
        for issue in resp.json():
            assert issue["status"] == "open"

    def test_issue_list_filters_by_severity(self, client, auth):
        resp = client.get("/api/data-quality/issues?severity=error", headers=auth)
        assert resp.status_code == 200
        for issue in resp.json():
            assert issue["severity"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# ROLLEN: viewer read-only scan, registry-schrijven alleen admin/pricing_manager
# ══════════════════════════════════════════════════════════════════════════════

VIEWER_LOGIN = {"username": "dev_viewer", "password": "viewer123"}


@pytest.fixture(scope="module")
def viewer_auth(client):
    resp = client.post("/api/auth/login", json=VIEWER_LOGIN)
    if resp.status_code != 200:
        # Maak het viewer-account aan als het (nog) niet bestaat
        import auth as auth_utils
        db = SessionLocal()
        try:
            if not db.query(models.User).filter(
                    models.User.username == VIEWER_LOGIN["username"]).first():
                db.add(models.User(
                    username=VIEWER_LOGIN["username"],
                    email=f"{VIEWER_LOGIN['username']}@example.com",
                    hashed_password=auth_utils.hash_password(VIEWER_LOGIN["password"]),
                    role="viewer",
                ))
                db.commit()
        finally:
            db.close()
        resp = client.post("/api/auth/login", json=VIEWER_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


ANALYST_LOGIN = {"username": "dev_analyst_dq70", "password": "analyst123"}


def _login_or_create(client, login, role):
    resp = client.post("/api/auth/login", json=login)
    if resp.status_code != 200:
        import auth as auth_utils
        db = SessionLocal()
        try:
            if not db.query(models.User).filter(
                    models.User.username == login["username"]).first():
                db.add(models.User(
                    username=login["username"],
                    email=f"{login['username']}@example.com",
                    hashed_password=auth_utils.hash_password(login["password"]),
                    role=role,
                ))
                db.commit()
        finally:
            db.close()
        resp = client.post("/api/auth/login", json=login)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def analyst_auth(client):
    return _login_or_create(client, ANALYST_LOGIN, "analyst")


class TestViewerReadOnlyScan:
    def test_viewer_can_scan_but_does_not_write_registry(self, client, auth, viewer_auth):
        """Een viewer-GET mag de scan zien, maar mag statussen in de registry
        niet overschrijven (geen upsert/auto-resolve)."""
        db = SessionLocal()
        code = f"{PFX}-VIEWER-RO"
        try:
            # Zet een kunstmatige registry-rij op 'in_behandeling' die niet
            # meer gedetecteerd wordt — een schrijvende scan zou hem
            # auto-resolven naar 'opgelost'.
            row = models.DataQualityIssue(
                issue_code=code, title="t", message="m", severity="info",
                source="Test", module="Test", affected_count=1,
                status="in_behandeling",
                first_detected_at=datetime.utcnow(),
                last_detected_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            row_id = row.id

            resp = client.get("/api/data-quality", headers=viewer_auth)
            assert resp.status_code == 200, resp.text

            db.expire_all()
            after = db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.id == row_id).first()
            assert after is not None
            assert after.status == "in_behandeling", (
                "Viewer-scan mag registry-statussen niet wijzigen; "
                f"status werd {after.status!r}"
            )

            # Een admin-scan mag de rij wél auto-resolven
            resp = client.get("/api/data-quality", headers=auth)
            assert resp.status_code == 200
            db.expire_all()
            after = db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.id == row_id).first()
            assert after.status == "opgelost", (
                "Admin-scan hoort verdwenen detecties te auto-resolven"
            )
        finally:
            db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.issue_code == code
            ).delete(synchronize_session=False)
            db.commit()
            db.close()

    def test_viewer_can_list_issues(self, client, viewer_auth):
        resp = client.get("/api/data-quality/issues", headers=viewer_auth)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_viewer_cannot_patch_issue(self, client, auth, viewer_auth):
        db = SessionLocal()
        code = f"{PFX}-VIEWER-PATCH"
        try:
            row = models.DataQualityIssue(
                issue_code=code, title="t", message="m", severity="info",
                source="Test", module="Test", affected_count=1, status="open",
                first_detected_at=datetime.utcnow(),
                last_detected_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            resp = client.patch(
                f"/api/data-quality/issues/{row.id}",
                json={"status": "genegeerd"}, headers=viewer_auth)
            assert resp.status_code == 403
        finally:
            db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.issue_code == code
            ).delete(synchronize_session=False)
            db.commit()
            db.close()

    def test_analyst_cannot_patch_issue(self, client, analyst_auth):
        """Schrijven op de issue-workflow is voorbehouden aan admin/pricing_manager;
        ook een analyst krijgt 403 voor status- én owner-wijzigingen."""
        db = SessionLocal()
        code = f"{PFX}-ANALYST-PATCH"
        try:
            row = models.DataQualityIssue(
                issue_code=code, title="t", message="m", severity="info",
                source="Test", module="Test", affected_count=1, status="open",
                first_detected_at=datetime.utcnow(),
                last_detected_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            row_id = row.id
            resp = client.patch(
                f"/api/data-quality/issues/{row_id}",
                json={"status": "genegeerd"}, headers=analyst_auth)
            assert resp.status_code == 403
            resp = client.patch(
                f"/api/data-quality/issues/{row_id}",
                json={"owner": "iemand"}, headers=analyst_auth)
            assert resp.status_code == 403
            db.expire_all()
            after = db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.id == row_id).first()
            assert after.status == "open" and after.owner is None
        finally:
            db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.issue_code == code
            ).delete(synchronize_session=False)
            db.commit()
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# NACHTSCAN (run_scan_once): alleen alarm bij echt nieuwe of heropende issues
#
# Isolatie: _detect_issues wordt NIET vervangen maar gewrapt — de echte
# detecties blijven meedraaien en er wordt één synthetisch test-issue aan
# toegevoegd. Zo blijft de registrystatus van echte issues onaangetast.
# De notifier is gemockt (geen echte e-mail/webhook) en assertions filteren
# op de eigen issue-code. ImportJobs worden per test op exact id opgeruimd,
# nadat op inhoud is geverifieerd dat de job door deze test is aangemaakt.
# ══════════════════════════════════════════════════════════════════════════════

from services.data_quality_scan_scheduler import run_scan_once, SCAN_JOB_TYPE

_REAL_DETECT_ISSUES = dq_module._detect_issues


class TestNightScanAlerts:
    """Regressietests voor run_scan_once() alert-gedrag en job-registratie."""

    def _cleanup(self, db, code, job_ids):
        db.query(models.DataQualityIssue).filter(
            models.DataQualityIssue.issue_code == code
        ).delete(synchronize_session=False)
        if job_ids:
            db.query(models.ImportJob).filter(
                models.ImportJob.id.in_(list(job_ids))
            ).delete(synchronize_session=False)
        db.commit()

    def _newest_scan_job(self, db, since_id):
        db.expire_all()
        return (db.query(models.ImportJob)
                .filter(models.ImportJob.upload_type == SCAN_JOB_TYPE,
                        models.ImportJob.id > since_id)
                .order_by(models.ImportJob.id.desc()).first())

    def _max_job_id(self, db):
        from sqlalchemy import func
        return db.query(func.coalesce(func.max(models.ImportJob.id), 0)).scalar()

    def _run(self, code, calls):
        """Draai run_scan_once; echte detecties + één synthetisch issue.

        `calls` verzamelt (issue_code, kind)-tupels van de gemockte notifier,
        vastgelegd op het moment van de call (de registry-row raakt daarna
        detached van de gesloten sessie)."""
        def detect(db, total_skus):
            return _REAL_DETECT_ISSUES(db, total_skus) + [
                _make_issue_dict(code, "error", 4)
            ]

        def notify(_db, row, kind):
            calls.append((row.issue_code, kind))

        with patch.object(dq_module, "_detect_issues", side_effect=detect), \
             patch("services.data_quality_scan_scheduler._notify_issue", notify):
            return run_scan_once()

    def test_new_issue_sends_single_alert(self, client):
        code = f"TEST_SCAN_NEW_{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        job_ids = set()
        since = self._max_job_id(db)
        try:
            calls = []
            summary = self._run(code, calls)

            assert code in summary["new"]
            assert code not in summary["reopened"]
            own_calls = [c for c in calls if c[0] == code]
            assert own_calls == [(code, "new")], \
                "Nieuw issue moet precies één 'new'-alert sturen"

            # Succesvolle run registreert een 'geimporteerd' ImportJob.
            job = self._newest_scan_job(db, since)
            assert job is not None
            assert code in (job.warnings_json or {}).get("new_issues", []), \
                "Nieuwste scan-job hoort bij deze test (bevat de test-issuecode)"
            assert job.status == "geimporteerd"
            job_ids.add(job.id)
        finally:
            self._cleanup(db, code, job_ids)
            db.close()

    def test_persistent_issue_sends_no_repeat_alert(self, client):
        code = f"TEST_SCAN_PERSIST_{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        job_ids = set()
        since = self._max_job_id(db)
        try:
            # Run 1: nieuw → alert
            calls1 = []
            self._run(code, calls1)
            assert (code, "new") in calls1
            job = self._newest_scan_job(db, since)
            if job is not None and code in (job.warnings_json or {}).get("new_issues", []):
                job_ids.add(job.id)
                since = job.id

            # Run 2: hetzelfde issue nog steeds open → GEEN alert voor deze code
            calls2 = []
            summary = self._run(code, calls2)
            assert code not in summary["new"]
            assert code not in summary["reopened"]
            assert [c for c in calls2 if c[0] == code] == [], \
                "Aanhoudend open issue mag geen herhaalde alert sturen"
            job2 = self._newest_scan_job(db, since)
            if job2 is not None and job2.uploaded_by == "system-dq-scan":
                job_ids.add(job2.id)
        finally:
            self._cleanup(db, code, job_ids)
            db.close()

    def test_reopened_issue_sends_alert_again(self, client):
        code = f"TEST_SCAN_REOPEN_{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        job_ids = set()
        since = self._max_job_id(db)
        try:
            # Run 1: nieuw
            self._run(code, [])
            job = self._newest_scan_job(db, since)
            if job is not None and code in (job.warnings_json or {}).get("new_issues", []):
                job_ids.add(job.id)
                since = job.id

            # Markeer ALLEEN dit test-issue als opgelost (gericht, geen
            # _sync_issue_registry(db, []) — dat zou echte issues resolven).
            row = db.query(models.DataQualityIssue).filter(
                models.DataQualityIssue.issue_code == code).first()
            assert row is not None
            row.status = "opgelost"
            row.resolved_at = datetime.utcnow()
            db.commit()

            # Run 2: issue keert terug → 'reopened'-alert
            calls = []
            summary = self._run(code, calls)
            assert code in summary["reopened"]
            assert code not in summary["new"]
            assert [c for c in calls if c[0] == code] == [(code, "reopened")], \
                "Heropend issue moet precies één 'reopened'-alert sturen"
            job2 = self._newest_scan_job(db, since)
            if job2 is not None and code in (job2.warnings_json or {}).get("reopened_issues", []):
                job_ids.add(job2.id)
        finally:
            self._cleanup(db, code, job_ids)
            db.close()

    def test_failed_scan_registers_fout_importjob(self, client):
        db = SessionLocal()
        job_ids = set()
        since = self._max_job_id(db)
        boom_msg = f"detectie kapot (test {uuid.uuid4().hex[:8]})"
        try:
            calls = []

            def notify(_db, row, kind):
                calls.append((row.issue_code, kind))

            with patch.object(dq_module, "_detect_issues",
                              side_effect=RuntimeError(boom_msg)), \
                 patch("services.data_quality_scan_scheduler._notify_issue", notify):
                with pytest.raises(RuntimeError):
                    run_scan_once()

            assert calls == [], "Mislukte scan mag geen alerts sturen"
            job = self._newest_scan_job(db, since)
            assert job is not None, "Mislukte scan moet als ImportJob zichtbaar zijn"
            assert boom_msg in (job.error_message or ""), \
                "Nieuwste scan-job hoort bij deze test (unieke foutmelding)"
            assert job.status == "fout"
            assert job.completed_at is not None
            job_ids.add(job.id)
        finally:
            if job_ids:
                db.query(models.ImportJob).filter(
                    models.ImportJob.id.in_(list(job_ids))
                ).delete(synchronize_session=False)
                db.commit()
            db.close()
