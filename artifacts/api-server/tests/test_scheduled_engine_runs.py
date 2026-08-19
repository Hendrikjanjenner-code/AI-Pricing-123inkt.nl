"""
Tests voor taak 51: mislukte nachtrun mag de volgende dag niet opnieuw
mislukken door verouderde data.

- scheduled_engines registreert per engine de uitkomst in scheduled_engine_runs
- Een herstart dezelfde dag slaat combinaties met een succesvolle run over
- De opportunity-engine waarschuwt als de forecast van vandaag ontbreekt

De tests draaien tegen de dev-database met een dedicated test-shop en ruimen
hun eigen data op.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from database import SessionLocal, engine as db_engine
import models
import scheduled_engines
from engine.opportunity_engine import _warn_if_forecast_stale

models.Base.metadata.create_all(bind=db_engine)


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    try:
        s.rollback()
        s.close()
    except Exception:
        pass


@pytest.fixture()
def shop(db):
    code = f"T51-{uuid.uuid4().hex[:8]}"
    shop = models.DimShop(shop_code=code, name=f"Test51 {code}", active=False)
    db.add(shop)
    db.commit()
    yield shop
    db.rollback()
    db.query(models.ScheduledEngineRun).filter(
        models.ScheduledEngineRun.shop_id == shop.id).delete()
    db.query(models.FactForecastDaily).filter(
        models.FactForecastDaily.shop_id == shop.id).delete()
    db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == shop.id).delete()
    db.query(models.DimShop).filter(models.DimShop.id == shop.id).delete()
    db.commit()


def test_main_entrypoint_draait_met_actieve_shop(db, shop, monkeypatch):
    """
    Black-box: de echte script-entrypoint main() draait zonder NameError e.d.
    met een actieve shop, registreert uitkomsten en is idempotent bij een
    tweede aanroep (alles wordt dan overgeslagen).
    """
    import engine.basket_engine, engine.promotion_engine
    import engine.forecast_engine, engine.opportunity_engine
    import engine.competitor_influence, engine.competition_rankings
    import engine.competitor_scores

    calls: list[str] = []

    def make_fn(name):
        def fn(session, run_date=None, shop_id=None):
            calls.append(f"{name}:{shop_id}")
            return {"ok": True}
        return fn

    monkeypatch.setattr(engine.basket_engine, "run_basket_engine", make_fn("basket"))
    monkeypatch.setattr(engine.promotion_engine, "run_promotion_engine", make_fn("promotion"))
    monkeypatch.setattr(engine.forecast_engine, "run_forecast_engine", make_fn("forecast"))
    monkeypatch.setattr(engine.opportunity_engine, "run_opportunity_engine", make_fn("opportunity"))
    monkeypatch.setattr(engine.competitor_scores, "run_competitor_scores",
                        make_fn("competitor_scores"))
    monkeypatch.setattr(engine.competitor_influence, "run_cis_engine", lambda d: 0)
    monkeypatch.setattr(engine.competition_rankings, "run_competitor_rankings", lambda d: 0)

    today = date.today()
    # Maak de test-shop actief zodat main() hem meeneemt.
    shop.active = True
    db.commit()
    try:
        assert scheduled_engines.main() == 0
        # Beperk de asserties tot de eigen test-shop: de gedeelde dev-DB kan
        # tegelijk door andere (parallelle) suites van actieve shops en
        # run-registraties worden voorzien.
        own = [c for c in calls if c.endswith(f":{shop.id}")]
        assert own == [f"{n}:{shop.id}" for n in
                       ("basket", "promotion", "forecast", "opportunity",
                        "competitor_scores")]
        # Tweede aanroep dezelfde dag: idempotent, geen nieuwe engine-runs
        # voor deze shop.
        assert scheduled_engines.main() == 0
        assert [c for c in calls if c.endswith(f":{shop.id}")] == own
        recs = db.query(models.ScheduledEngineRun).filter(
            models.ScheduledEngineRun.shop_id == shop.id,
            models.ScheduledEngineRun.run_date == today).all()
        assert {r.engine_name for r in recs} == {
            "basket", "promotion", "forecast", "opportunity",
            "competitor_scores"}
        assert all(r.status == "success" for r in recs)
    finally:
        shop.active = False
        # Strikt test-gebonden cleanup: alleen de rijen van de eigen shop
        # (de fixture ruimt die ook op); records van andere shops kunnen door
        # parallel draaiende suites zijn aangemaakt en blijven van hen.
        db.query(models.ScheduledEngineRun).filter(
            models.ScheduledEngineRun.shop_id == shop.id).delete(
            synchronize_session=False)
        db.commit()


def test_laatste_poging_telt_niet_oude_succesrij(db, shop):
    """
    Regressie (failure-then-retry): forecast faalt 's nachts, opportunity
    'slaagt' op stale data. Retry 1: forecast herstelt, de geforceerde
    opportunity-rerun faalt. Retry 2 mag opportunity dan NIET overslaan op
    basis van de oude succes-rij: de meest recente poging telt.
    """
    today = date.today()

    def run_pass(results: dict[str, bool]) -> list[str]:
        """Eén herstart-lus zoals main(); results bepaalt slagen/falen."""
        executed = []
        upstream_reran = False
        for name in ("basket", "promotion", "forecast", "opportunity"):
            if not upstream_reran and scheduled_engines._has_successful_run(
                    db, models, today, shop.id, name):
                continue
            upstream_reran = True
            executed.append(name)

            def fn(session, run_date, shop_id, _ok=results.get(name, True)):
                if not _ok:
                    raise RuntimeError(f"{name} gefaald")
                return {"ok": True}

            scheduled_engines._run_engine(name, fn, db, models, shop.id, today)
        return executed

    # Nachtrun: forecast faalt; opportunity draait daarna (stale) en 'slaagt'.
    assert run_pass({"forecast": False}) == [
        "basket", "promotion", "forecast", "opportunity"]
    # Retry 1: forecast herstelt, geforceerde opportunity-rerun faalt.
    assert run_pass({"opportunity": False}) == ["forecast", "opportunity"]
    assert scheduled_engines._has_successful_run(
        db, models, today, shop.id, "opportunity") is False
    # Retry 2: opportunity wordt opnieuw geprobeerd, niet overgeslagen.
    assert run_pass({}) == ["opportunity"]
    assert scheduled_engines._has_successful_run(
        db, models, today, shop.id, "opportunity") is True


def test_run_engine_registreert_succes(db, shop):
    today = date.today()

    def ok_engine(session, run_date, shop_id):
        return {"ok": True}

    assert scheduled_engines._run_engine("basket", ok_engine, db, models, shop.id, today) is True
    rec = db.query(models.ScheduledEngineRun).filter_by(
        shop_id=shop.id, engine_name="basket", run_date=today).one()
    assert rec.status == "success"
    assert rec.completed_at is not None
    assert rec.result_summary == {"ok": True}


def test_run_engine_registreert_fout(db, shop):
    today = date.today()

    def broken_engine(session, run_date, shop_id):
        raise RuntimeError("DB-timeout gesimuleerd")

    assert scheduled_engines._run_engine("forecast", broken_engine, db, models, shop.id, today) is False
    rec = db.query(models.ScheduledEngineRun).filter_by(
        shop_id=shop.id, engine_name="forecast", run_date=today).one()
    assert rec.status == "failed"
    assert "DB-timeout" in (rec.error_message or "")


def test_herstart_slaat_succesvolle_run_over(db, shop):
    today = date.today()
    db.add(models.ScheduledEngineRun(
        run_date=today, shop_id=shop.id, engine_name="basket", status="success"))
    db.add(models.ScheduledEngineRun(
        run_date=today, shop_id=shop.id, engine_name="forecast", status="failed"))
    db.commit()

    assert scheduled_engines._has_successful_run(db, models, today, shop.id, "basket") is True
    assert scheduled_engines._has_successful_run(db, models, today, shop.id, "forecast") is False
    # Een run van gisteren telt niet als 'vandaag al gedraaid'.
    assert scheduled_engines._has_successful_run(
        db, models, today - timedelta(days=1), shop.id, "basket") is False


def test_herstart_draait_downstream_opnieuw_na_upstream_retry(db, shop):
    """
    E2E-herstart (dependency-bewust): forecast faalde vannacht, opportunity
    'slaagde' (op verouderde data) en publiceerde een stale-alert. Bij de
    herstart draait forecast opnieuw; opportunity mag dan NIET worden
    overgeslagen en het stale-signaal wordt opgelost.
    """
    today = date.today()
    # Nachtresultaat: basket/promotion ok, forecast gefaald, opportunity 'ok'.
    for name, status in [("basket", "success"), ("promotion", "success"),
                         ("forecast", "failed"), ("opportunity", "success")]:
        db.add(models.ScheduledEngineRun(
            run_date=today, shop_id=shop.id, engine_name=name, status=status))
    db.commit()
    # De nachtrun liet een actief stale-signaal achter.
    assert _warn_if_forecast_stale(db, today, shop.id, "test-v1") is True
    db.commit()

    executed: list[str] = []

    def make_engine(name):
        def fn(session, run_date, shop_id):
            executed.append(name)
            if name == "forecast":
                session.add(models.FactForecastDaily(
                    shop_id=shop_id, run_date=run_date, sku_id="SKU-T51",
                    forecast_type="units", horizon_days=30, forecast_value=1.0))
            if name == "opportunity":
                return {"forecast_stale": _warn_if_forecast_stale(
                    session, run_date, shop_id, "test-v1")}
            return {"ok": True}
        return fn

    engines = [(n, make_engine(n)) for n in ("basket", "promotion", "forecast", "opportunity")]

    # Herstart-lus zoals in scheduled_engines.main().
    upstream_reran = False
    for engine_name, engine_fn in engines:
        if not upstream_reran and scheduled_engines._has_successful_run(
                db, models, today, shop.id, engine_name):
            continue
        upstream_reran = True
        assert scheduled_engines._run_engine(
            engine_name, engine_fn, db, models, shop.id, today) is True

    # basket/promotion overgeslagen; forecast én opportunity opnieuw gedraaid.
    assert executed == ["forecast", "opportunity"]
    # Het stale-signaal is opgelost na de herstelde forecast.
    active = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == shop.id,
        models.IntelligenceSignal.signal_type == "forecast_data_stale",
        models.IntelligenceSignal.status == "active",
    ).count()
    assert active == 0


def test_opportunity_waarschuwt_bij_verouderde_forecast(db, shop):
    today = date.today()
    db.add(models.FactForecastDaily(
        shop_id=shop.id, run_date=today - timedelta(days=2), sku_id="SKU-T51",
        forecast_type="units", horizon_days=30, forecast_value=1.0))
    db.commit()

    assert _warn_if_forecast_stale(db, today, shop.id, "test-v1") is True
    db.commit()
    sig = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == shop.id,
        models.IntelligenceSignal.signal_type == "forecast_data_stale",
        models.IntelligenceSignal.status == "active",
    ).one()
    assert sig.severity == "critical"  # 2 dagen oud
    assert sig.evidence["lag_days"] == 2


def test_opportunity_waarschuwt_bij_een_dag_vertraging(db, shop):
    today = date.today()
    db.add(models.FactForecastDaily(
        shop_id=shop.id, run_date=today - timedelta(days=1), sku_id="SKU-T51",
        forecast_type="units", horizon_days=30, forecast_value=1.0))
    db.commit()

    assert _warn_if_forecast_stale(db, today, shop.id, "test-v1") is True
    db.commit()
    sig = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == shop.id,
        models.IntelligenceSignal.signal_type == "forecast_data_stale",
        models.IntelligenceSignal.status == "active",
    ).one()
    # 'high' is een geldige severity voor publish_signal (geen stille
    # terugval naar 'info'), zodat de 1-dag-lag echt als waarschuwing telt.
    assert sig.severity == "high"
    assert sig.evidence["lag_days"] == 1


def test_opportunity_waarschuwt_zonder_enige_forecast(db, shop):
    today = date.today()
    assert _warn_if_forecast_stale(db, today, shop.id, "test-v1") is True
    db.commit()
    sig = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == shop.id,
        models.IntelligenceSignal.signal_type == "forecast_data_stale",
        models.IntelligenceSignal.status == "active",
    ).one()
    assert sig.severity == "critical"
    assert sig.evidence["lag_days"] is None


def test_opportunity_herstel_lost_stale_signaal_op(db, shop):
    """E2E-herstel: stale alert → verse forecast → geen actief stale-signaal."""
    today = date.today()
    db.add(models.FactForecastDaily(
        shop_id=shop.id, run_date=today - timedelta(days=1), sku_id="SKU-T51",
        forecast_type="units", horizon_days=30, forecast_value=1.0))
    db.commit()
    assert _warn_if_forecast_stale(db, today, shop.id, "test-v1") is True
    db.commit()

    # Herstel: de forecast-run van vandaag draait alsnog succesvol.
    db.add(models.FactForecastDaily(
        shop_id=shop.id, run_date=today, sku_id="SKU-T51",
        forecast_type="units", horizon_days=30, forecast_value=1.0))
    db.commit()

    assert _warn_if_forecast_stale(db, today, shop.id, "test-v1") is False
    db.commit()
    active = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == shop.id,
        models.IntelligenceSignal.signal_type == "forecast_data_stale",
        models.IntelligenceSignal.status == "active",
    ).count()
    assert active == 0
