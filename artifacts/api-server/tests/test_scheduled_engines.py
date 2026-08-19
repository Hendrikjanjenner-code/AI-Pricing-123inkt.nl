"""
Tests voor scheduled_engines.py — de nachtelijke engine-run.

Borgt dat een crash in de CIS-engine of de competitor rankings de
nachtrun zichtbaar laat falen (exit-code 1) zonder de overige stappen
te blokkeren, en dat het aantal geschreven CIS-rijen bij succes in de
log verschijnt. Zonder deze tests zou een refactor het faal-signaal
stilletjes kunnen wegnemen.
"""
import logging
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import models
from database import SessionLocal
import scheduled_engines

PFX = f"SCHEDENG{uuid.uuid4().hex[:6]}"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def active_shop():
    """Zorg dat er minstens één actieve shop is, anders slaat main() alles over."""
    from database import engine as db_engine
    models.Base.metadata.create_all(bind=db_engine)
    db = SessionLocal()
    shop = models.DimShop(
        shop_code=f"{PFX}-shop", name=f"{PFX} Shop", active=True,
    )
    db.add(shop)
    db.commit()
    shop_id = shop.id
    yield shop_id
    # Teardown: eventuele per-shop usage-rijen eerst weg (FK), dan de shop.
    for table in ("ai_cost_usage",):
        try:
            db.execute(
                models.Base.metadata.tables[table].delete().where(
                    models.Base.metadata.tables[table].c.shop_id == shop_id
                )
            )
        except KeyError:
            pass
    db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete()
    db.commit()
    db.close()


@pytest.fixture()
def stub_shop_engines(monkeypatch):
    """Vervang de vier per-shop engines door no-ops zodat de test snel en
    deterministisch is; deze tests gaan over CIS/rankings-foutafhandeling."""
    noop = lambda db, run_date=None, shop_id=None: {"stub": True}  # noqa: E731
    monkeypatch.setattr("engine.basket_engine.run_basket_engine", noop)
    monkeypatch.setattr("engine.promotion_engine.run_promotion_engine", noop)
    monkeypatch.setattr("engine.forecast_engine.run_forecast_engine", noop)
    monkeypatch.setattr("engine.opportunity_engine.run_opportunity_engine", noop)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_cis_crash_fails_run_but_rankings_still_execute(
    active_shop, stub_shop_engines, monkeypatch, caplog
):
    calls = {"rankings": 0}

    def broken_cis(db):
        raise RuntimeError("CIS kapot (testfout)")

    def fake_rankings(db):
        calls["rankings"] += 1
        return 7

    monkeypatch.setattr("engine.competitor_influence.run_cis_engine", broken_cis)
    monkeypatch.setattr("engine.competition_rankings.run_competitor_rankings", fake_rankings)

    with caplog.at_level(logging.INFO, logger="scheduled_engines"):
        exit_code = scheduled_engines.main()

    assert exit_code == 1, "Een CIS-crash moet de nachtrun met exit-code 1 laten falen"
    assert calls["rankings"] == 1, "Rankings moeten alsnog draaien na een CIS-crash"
    assert any(
        "[cis] mislukt" in r.message for r in caplog.records
    ), "De CIS-fout moet in de log staan"
    # De exception zelf (traceback) hoort via logger.exception in de log te staan.
    assert any(
        r.exc_info and "CIS kapot" in str(r.exc_info[1]) for r in caplog.records
    )
    # Rankings-succes gewoon gelogd.
    assert any("[rankings] klaar: 7" in r.getMessage() for r in caplog.records)


def test_rankings_crash_fails_run(active_shop, stub_shop_engines, monkeypatch, caplog):
    def fake_cis(db):
        return 3

    def broken_rankings(db):
        raise RuntimeError("Rankings kapot (testfout)")

    monkeypatch.setattr("engine.competitor_influence.run_cis_engine", fake_cis)
    monkeypatch.setattr("engine.competition_rankings.run_competitor_rankings", broken_rankings)

    with caplog.at_level(logging.INFO, logger="scheduled_engines"):
        exit_code = scheduled_engines.main()

    assert exit_code == 1, "Een rankings-crash moet de nachtrun met exit-code 1 laten falen"
    assert any("[rankings] mislukt" in r.message for r in caplog.records)
    assert any(
        r.exc_info and "Rankings kapot" in str(r.exc_info[1]) for r in caplog.records
    )
    # CIS draaide succesvol vóór de crash en logde zijn rijenaantal.
    assert any("[cis] klaar: 3 CIS-rijen geschreven" in r.getMessage() for r in caplog.records)


def test_successful_run_logs_cis_row_count_and_exits_zero(
    active_shop, stub_shop_engines, monkeypatch, caplog
):
    monkeypatch.setattr("engine.competitor_influence.run_cis_engine", lambda db: 42)
    monkeypatch.setattr(
        "engine.competition_rankings.run_competitor_rankings", lambda db: 5
    )

    with caplog.at_level(logging.INFO, logger="scheduled_engines"):
        exit_code = scheduled_engines.main()

    assert exit_code == 0
    assert any(
        "[cis] klaar: 42 CIS-rijen geschreven" in r.getMessage() for r in caplog.records
    ), "Het aantal geschreven CIS-rijen moet bij succes in de log staan"
    assert any(
        "volledig succesvol" in r.getMessage() for r in caplog.records
    )
