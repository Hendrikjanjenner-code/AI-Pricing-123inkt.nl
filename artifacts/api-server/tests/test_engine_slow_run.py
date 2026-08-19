"""
Trage-run-bewaking voor de overige nachtelijke engines.

Analoog aan de slow-run-tests in tests/test_competition_intelligence.py:
- een run boven de drempel publiceert een engine_slow_run-signaal met
  per-stap timings als evidence;
- forecast/decision draaien in productie per shop (scheduled_engines.py),
  dus juist de shop-gescopeerde run publiceert een shop-gescopeerd signaal;
- drempel <= 0 schakelt de bewaking uit.

De zware datastappen worden vervangen door lege queries (FastDB) zodat de
tests snel en niet-destructief zijn; de orchestratie + bewaking zelf draait
tegen de echte database.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models


@pytest.fixture(scope="module", autouse=True)
def _app_lifespan():
    """Start de app-lifespan zodat tabellen/seed bestaan (conventie suite)."""
    c = TestClient(app)
    c.__enter__()
    yield
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass

TINY = 1e-9  # drempel praktisch nul: elke run is dan "te traag"


class _EmptyQuery:
    """Query-stub: elke chain-methode geeft zichzelf terug, resultaten leeg."""

    def __getattr__(self, name):
        def chain(*a, **k):
            return self
        return chain

    def all(self):
        return []

    def first(self):
        return None

    def count(self):
        return 0

    def delete(self, *a, **k):
        return 0

    def update(self, *a, **k):
        return 0

    def __iter__(self):
        return iter([])


class FastDB:
    """Wrapper om een echte sessie die queries op 'zware' modellen leeg maakt,
    zodat engine-runs snel en niet-destructief zijn. Alle andere calls
    (publish_signal, governance, commit) gaan naar de echte sessie."""

    def __init__(self, real, intercept):
        self._real = real
        self._intercept = tuple(intercept)

    def query(self, *entities):
        if entities and any(entities[0] is m for m in self._intercept):
            return _EmptyQuery()
        return self._real.query(*entities)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _slow_signals(db, engine):
    return (db.query(models.IntelligenceSignal)
            .filter(models.IntelligenceSignal.engine == engine,
                    models.IntelligenceSignal.signal_type == "engine_slow_run")
            .order_by(models.IntelligenceSignal.id.desc()))


def _cleanup(db, engine):
    db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.engine == engine,
        models.IntelligenceSignal.signal_type == "engine_slow_run",
    ).delete(synchronize_session=False)
    db.commit()
    db.close()


def _assert_slow_signal(db, engine):
    sig = _slow_signals(db, engine).filter(
        models.IntelligenceSignal.status == "active").first()
    assert sig is not None, f"geen actief engine_slow_run-signaal voor '{engine}'"
    assert sig.evidence["threshold_seconds"] == pytest.approx(TINY)
    assert "timings_seconds" in sig.evidence
    assert sig.evidence["timings_seconds"], "per-stap timings ontbreken in evidence"
    assert sig.explanation
    return sig


def _default_shop_id(db) -> int:
    row = db.query(models.DimShop.id).filter(models.DimShop.is_default == True).first()  # noqa: E712
    return row[0] if row else 1


# ── Pricing engine ───────────────────────────────────────────────────────────

def test_slow_pricing_run_publishes_engine_slow_run_signal(monkeypatch):
    from engine import pricing_engine as pe

    monkeypatch.setattr(pe, "_cfg", lambda db: {"slow_run_threshold_seconds": TINY})
    real = SessionLocal()
    db = FastDB(real, [models.DimProduct, models.FactSalesDaily,
                       models.FactPriceDaily, models.FactCompetitorPriceDaily,
                       models.FactInventoryDaily, models.FactBasketAffinity,
                       models.MapSubstitution,
                       models.FactPricingRecommendationDaily])
    try:
        processed, skipped = pe.run_pricing_engine(db)
        sig = _assert_slow_signal(real, "pricing")
        assert "load_sales" in sig.evidence["timings_seconds"]
        assert "recommendations" in sig.evidence["timings_seconds"]
    finally:
        _cleanup(real, "pricing")


# ── Traffic engine ───────────────────────────────────────────────────────────

def test_slow_traffic_run_publishes_engine_slow_run_signal(monkeypatch):
    from engine import traffic_engine as te

    monkeypatch.setattr(te, "get_active_config",
                        lambda db, name, defaults: {"slow_run_threshold_seconds": TINY})
    real = SessionLocal()
    db = FastDB(real, [models.DimProduct, models.FactTrafficDaily,
                       models.FactSearchDemandDaily, models.SkuCompetitionScore,
                       models.FactInventoryDaily,
                       models.FactTrafficIntelligenceDaily])
    try:
        te.run_traffic_engine(db)
        sig = _assert_slow_signal(real, "traffic")
        assert "load_data" in sig.evidence["timings_seconds"]
        assert "scores" in sig.evidence["timings_seconds"]
    finally:
        _cleanup(real, "traffic")


# ── Decision engine ──────────────────────────────────────────────────────────

def _decision_fastdb(real):
    return FastDB(real, [models.Decision, models.DecisionScenario,
                         models.DecisionEvent, models.DimProduct])


def test_slow_full_decision_run_publishes_engine_slow_run_signal(monkeypatch):
    from engine import decision_engine as de

    monkeypatch.setattr(de, "get_active_config",
                        lambda db, name, defaults: {"slow_run_threshold_seconds": TINY})
    real = SessionLocal()
    # Ook IntelligenceSignal-loads leeg (geen echte beslissingen genereren);
    # publish_signal schrijft via db.add en blijft dus gewoon werken.
    db = FastDB(real, [models.Decision, models.DecisionScenario,
                       models.DecisionEvent, models.DimProduct,
                       models.IntelligenceSignal])
    try:
        result = de.run_decision_engine(db, shop_id=None)
        assert result.get("slow_run_signal") is True
        assert "timings_seconds" in result and "total_seconds" in result
        for step in ("load_signals", "sku_decisions", "category_decisions"):
            assert step in result["timings_seconds"], result["timings_seconds"]
        _assert_slow_signal(real, "decision")
    finally:
        _cleanup(real, "decision")


def test_scoped_decision_run_publishes_shop_scoped_signal(monkeypatch):
    """De decision-run is effectief altijd shop-gescopeerd; het signaal moet
    dan ook aan de betreffende shop hangen (dedupe per shop)."""
    from engine import decision_engine as de

    monkeypatch.setattr(de, "get_active_config",
                        lambda db, name, defaults: {"slow_run_threshold_seconds": TINY})
    real = SessionLocal()
    sid = _default_shop_id(real)
    db = FastDB(real, [models.Decision, models.DecisionScenario,
                       models.DecisionEvent, models.DimProduct,
                       models.IntelligenceSignal])
    try:
        result = de.run_decision_engine(db, shop_id=sid)
        assert result.get("slow_run_signal") is True
        sig = _assert_slow_signal(real, "decision")
        assert sig.shop_id == sid
        assert sig.entity_id == str(sid)
    finally:
        _cleanup(real, "decision")


def test_decision_slow_run_monitor_disabled_with_nonpositive_threshold(monkeypatch):
    from engine import decision_engine as de

    monkeypatch.setattr(de, "get_active_config",
                        lambda db, name, defaults: {"slow_run_threshold_seconds": 0})
    real = SessionLocal()
    db = FastDB(real, [models.Decision, models.DecisionScenario,
                       models.DecisionEvent, models.DimProduct,
                       models.IntelligenceSignal])
    try:
        result = de.run_decision_engine(db, shop_id=None)
        assert "slow_run_signal" not in result
        assert "timings_seconds" in result  # timings blijven wel gerapporteerd
        assert _slow_signals(real, "decision").filter(
            models.IntelligenceSignal.status == "active").count() == 0
    finally:
        _cleanup(real, "decision")


# ── Forecast engine ──────────────────────────────────────────────────────────

def _forecast_cfg(db, name, defaults):
    from engine.forecast_engine import FORECAST_DEFAULT_CONFIG
    return dict(FORECAST_DEFAULT_CONFIG, slow_run_threshold_seconds=TINY)


def test_slow_forecast_run_publishes_engine_slow_run_signal(monkeypatch):
    from engine import forecast_engine as fe

    monkeypatch.setattr(fe, "get_active_config", _forecast_cfg)
    real = SessionLocal()
    db = FastDB(real, [models.FactSalesDaily, models.DimProduct,
                       models.FactForecastDaily])
    try:
        result = fe.run_forecast_engine(db, run_date=date.today(), shop_id=None)
        assert result.get("slow_run_signal") is True
        for step in ("load_sales", "load_products", "forecasts"):
            assert step in result["timings_seconds"], result["timings_seconds"]
        _assert_slow_signal(real, "forecast_risk")
    finally:
        _cleanup(real, "forecast_risk")


def test_scheduler_style_per_shop_forecast_run_publishes_shop_scoped_signal(monkeypatch):
    """De nachtelijke scheduler (scheduled_engines.py) draait de forecast-engine
    per shop met een expliciete shop_id; ook dat productiepad moet bij een
    trage run een (shop-gescopeerd) engine_slow_run-signaal opleveren."""
    from engine import forecast_engine as fe

    monkeypatch.setattr(fe, "get_active_config", _forecast_cfg)
    real = SessionLocal()
    sid = _default_shop_id(real)
    db = FastDB(real, [models.FactSalesDaily, models.DimProduct,
                       models.FactForecastDaily])
    try:
        result = fe.run_forecast_engine(db, run_date=date.today(), shop_id=sid)
        assert result.get("slow_run_signal") is True
        sig = _assert_slow_signal(real, "forecast_risk")
        assert sig.shop_id == sid
        assert sig.entity_id == str(sid)
        assert "load_sales" in sig.evidence["timings_seconds"]
    finally:
        _cleanup(real, "forecast_risk")


def test_forecast_slow_run_monitor_disabled_with_nonpositive_threshold(monkeypatch):
    from engine import forecast_engine as fe

    monkeypatch.setattr(fe, "get_active_config", lambda db, name, defaults: dict(
        fe.FORECAST_DEFAULT_CONFIG, slow_run_threshold_seconds=0))
    real = SessionLocal()
    sid = _default_shop_id(real)
    db = FastDB(real, [models.FactSalesDaily, models.DimProduct,
                       models.FactForecastDaily])
    try:
        result = fe.run_forecast_engine(db, run_date=date.today(), shop_id=sid)
        assert "slow_run_signal" not in result
        assert "timings_seconds" in result
        assert _slow_signals(real, "forecast_risk").filter(
            models.IntelligenceSignal.status == "active").count() == 0
    finally:
        _cleanup(real, "forecast_risk")
