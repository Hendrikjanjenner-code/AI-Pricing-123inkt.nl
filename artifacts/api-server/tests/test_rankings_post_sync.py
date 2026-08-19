"""
Tests voor de rankings-refresh die automatisch na een feed-sync meedraait
(services.refresh.run_rankings_refresh) én voor de versheids-/wijzigingsvelden
in GET /api/competition/rankings.

Kernpunten:
- Een geslaagde refresh schrijft ranking-rijen (shop-gescoped) én een
  zichtbare EngineRun-rij (engine_name="rankings", status success).
- Een falende refresh gooit NOOIT door (de feed-sync mag er niet op falen),
  maar registreert wel een failed EngineRun-rij.
- GET /rankings geeft computed_at / last_feed_sync_at / stale / changed terug.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from database import SessionLocal  # noqa: E402
import models  # noqa: E402

ADMIN_LOGIN = {"username": "admin", "password": "admin123"}
PFX = "RPSYNC"
CAT = f"{PFX}-cat"
COMP_1 = f"{PFX}-alpha.nl"
COMP_2 = f"{PFX}-beta.nl"


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


@pytest.fixture()
def shop():
    """Geïsoleerde test-shop met een profiel + categoriescores voor 2 concurrenten."""
    db = SessionLocal()
    shop_id = None
    try:
        s = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop", active=True)
        db.add(s)
        db.flush()
        shop_id = s.id
        db.add(models.DimProduct(
            sku_id=f"{PFX}-SKU", product_name=f"{PFX} product", category=CAT,
            current_price=20.0, cost_price=12.0, stock_quantity=10, shop_id=shop_id,
        ))
        for name, rel in [(COMP_1, 80.0), (COMP_2, 40.0)]:
            db.add(models.CompetitorProfile(
                shop_id=shop_id, competitor_name=name,
                functional_overlap_score=rel, price_change_frequency=20.0,
            ))
            db.add(models.CategoryCompetitorRelevance(
                shop_id=shop_id, category=CAT, competitor_name=name,
                relevance_score=rel, coverage_index=rel,
                pricing_relevance_score=rel,
            ))
        db.commit()
        yield shop_id
    finally:
        for model in (models.CompetitorRanking, models.EngineRun,
                      models.CategoryCompetitorRelevance, models.CompetitorProfile,
                      models.CompetitorInfluenceScore):
            try:
                if model is models.EngineRun:
                    db.query(model).filter(model.shop_id == shop_id).delete(
                        synchronize_session=False)
                elif hasattr(model, "shop_id"):
                    db.query(model).filter(model.shop_id == shop_id).delete(
                        synchronize_session=False)
            except Exception:
                db.rollback()
        try:
            db.query(models.CompetitorInfluenceScore).filter(
                models.CompetitorInfluenceScore.sku_id == f"{PFX}-SKU").delete(
                synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == shop_id).delete(synchronize_session=False)
        except Exception:
            db.rollback()
        try:
            db.query(models.DimProduct).filter(
                models.DimProduct.shop_id == shop_id).delete(synchronize_session=False)
            db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(
                synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def test_refresh_success_writes_rankings_and_engine_run(shop):
    """Geslaagde refresh: rankings voor de shop + EngineRun success-rij."""
    from services.refresh import run_rankings_refresh
    db = SessionLocal()
    try:
        result = run_rankings_refresh(db, shop_id=shop, trigger="test")
        assert result is not None, "run_rankings_refresh gaf None bij succes"
        assert result["rankings"] > 0

        rows = db.query(models.CompetitorRanking).filter(
            models.CompetitorRanking.shop_id == shop).all()
        assert rows, "Geen ranking-rijen geschreven voor de test-shop"
        assert all(r.shop_id == shop for r in rows)

        run = (db.query(models.EngineRun)
               .filter(models.EngineRun.engine_name == "rankings",
                       models.EngineRun.shop_id == shop)
               .order_by(models.EngineRun.id.desc()).first())
        assert run is not None, "Geen EngineRun-rij voor de rankings-refresh"
        assert run.status == "success"
    finally:
        db.close()


def test_refresh_failure_is_visible_but_never_raises(shop, monkeypatch):
    """Falende refresh: geen exception naar de sync, wel een failed EngineRun."""
    import engine.competitor_influence as cis_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("kapotte CIS-engine (test)")

    monkeypatch.setattr(cis_mod, "run_cis_engine", _boom)
    from services.refresh import run_rankings_refresh
    db = SessionLocal()
    try:
        result = run_rankings_refresh(db, shop_id=shop, trigger="test")
        assert result is None, "Falende refresh moet None retourneren, niet gooien"
        run = (db.query(models.EngineRun)
               .filter(models.EngineRun.engine_name == "rankings",
                       models.EngineRun.shop_id == shop)
               .order_by(models.EngineRun.id.desc()).first())
        assert run is not None and run.status == "failed"
        assert "kapotte CIS-engine" in (run.error_message or "")
    finally:
        db.close()


def test_rankings_endpoint_reports_freshness_and_changes(client, admin_headers, shop):
    """GET /rankings geeft computed_at/stale/changed; delta tussen twee runs zichtbaar."""
    from engine.competition_rankings import run_competitor_rankings
    db = SessionLocal()
    try:
        # Run 1: vandaag (COMP_1 sterkste — rel 80 vs 40). Run 2 draait óók
        # vandaag: precies het productiepad waarin meerdere feed-syncs per dag
        # elk een rerun triggeren — de delta moet dan t.o.v. de zojuist
        # vervangen snapshot zijn, niet t.o.v. gisteren.
        run_competitor_rankings(db, shop_id=shop)
        # Wissel de krachtsverhouding om, run 2: zelfde dag → ranks wisselen
        for prof in db.query(models.CompetitorProfile).filter(
                models.CompetitorProfile.shop_id == shop).all():
            prof.functional_overlap_score = 40.0 if prof.competitor_name == COMP_1 else 90.0
        for row in db.query(models.CategoryCompetitorRelevance).filter(
                models.CategoryCompetitorRelevance.shop_id == shop).all():
            new = 40.0 if row.competitor_name == COMP_1 else 90.0
            row.relevance_score = new
            row.coverage_index = new
            row.pricing_relevance_score = new
        db.commit()
        run_competitor_rankings(db, shop_id=shop)
    finally:
        db.close()

    resp = client.get(f"/api/competition/rankings?scope=overall&shop_id={shop}",
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["computed_at"], "computed_at ontbreekt"
    assert "stale" in body and "changed" in body and "last_feed_sync_at" in body
    assert body["changed"] is True, f"Rankwissel niet gedetecteerd: {body['rankings']}"

    by_name = {r["competitor_name"]: r for r in body["rankings"]
               if r["competitor_name"].startswith(PFX)}
    assert by_name[COMP_2]["trend"] == "up" and by_name[COMP_2]["previous_rank"] == 2
    assert by_name[COMP_1]["trend"] == "down" and by_name[COMP_1]["previous_rank"] == 1
