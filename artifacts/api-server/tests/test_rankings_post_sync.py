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
                      models.CompetitorInfluenceScore,
                      models.FactCompetitorPriceDaily):
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
        assert result["category_scores"] >= 0
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


def test_category_refresh_failure_is_visible_and_preserves_last_ranking(
    shop, monkeypatch
):
    """Falende categorystap: feed blijft geslaagd en laatste ranking blijft staan."""
    from engine.competition_rankings import run_competitor_rankings
    import engine.category_competition as category_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("kapotte categoriescores (test)")

    from services.refresh import run_rankings_refresh
    db = SessionLocal()
    try:
        run_competitor_rankings(db, shop_id=shop)
        before = {
            (r.scope, r.competitor_name): (r.rank, r.combined_score)
            for r in db.query(models.CompetitorRanking).filter(
                models.CompetitorRanking.shop_id == shop).all()
        }
        monkeypatch.setattr(category_mod, "calculate_all_category_scores", _boom)
        result = run_rankings_refresh(db, shop_id=shop, trigger="test")
        assert result is None, "Falende refresh moet None retourneren, niet gooien"
        after = {
            (r.scope, r.competitor_name): (r.rank, r.combined_score)
            for r in db.query(models.CompetitorRanking).filter(
                models.CompetitorRanking.shop_id == shop).all()
        }
        assert after == before
        run = (db.query(models.EngineRun)
               .filter(models.EngineRun.engine_name == "rankings",
                       models.EngineRun.shop_id == shop)
               .order_by(models.EngineRun.id.desc()).first())
        assert run is not None and run.status == "failed"
        assert "step=category_scores" in (run.error_message or "")
        assert "kapotte categoriescores" in (run.error_message or "")
        assert run.result_summary["failed_step"] == "category_scores"
    finally:
        db.close()


def test_refresh_runs_category_then_cis_then_rankings(shop):
    """De afhankelijkheidsvolgorde is expliciet en alle aantallen staan in de uitkomst."""
    from services.refresh import _do_rankings_refresh

    calls = []

    def categories(db, shop_id=None):
        calls.append(("category_scores", shop_id))
        return 4

    def cis(db, sku_ids=None):
        calls.append(("cis_scores", list(sku_ids or [])))
        return 3

    def rankings(db, shop_id=None):
        calls.append(("rankings", shop_id))
        return 2

    db = SessionLocal()
    try:
        result = _do_rankings_refresh(
            db,
            shop_id=shop,
            trigger="order_test",
            started=datetime.utcnow(),
            calculate_all_category_scores=categories,
            run_cis_engine=cis,
            run_competitor_rankings=rankings,
        )
        assert [name for name, _ in calls] == [
            "category_scores", "cis_scores", "rankings"]
        assert result == {
            "trigger": "order_test",
            "category_scores": 4,
            "cis_scores": 3,
            "rankings": 2,
        }
    finally:
        db.close()


def test_failed_cis_step_keeps_partial_counts_in_run_history(shop):
    """Een foutlog toont welke aantallen al succesvol waren vóór de falende stap."""
    from services.refresh import _do_rankings_refresh

    def broken_cis(db, sku_ids=None):
        raise RuntimeError("CIS stuk")

    db = SessionLocal()
    try:
        result = _do_rankings_refresh(
            db,
            shop_id=shop,
            trigger="partial_count_test",
            started=datetime.utcnow(),
            calculate_all_category_scores=lambda db, shop_id=None: 6,
            run_cis_engine=broken_cis,
            run_competitor_rankings=lambda db, shop_id=None: 99,
        )
        assert result is None
        run = db.query(models.EngineRun).filter(
            models.EngineRun.shop_id == shop,
            models.EngineRun.engine_name == "rankings",
        ).order_by(models.EngineRun.id.desc()).first()
        assert run.result_summary == {
            "trigger": "partial_count_test",
            "category_scores": 6,
            "cis_scores": None,
            "rankings": None,
            "failed_step": "cis_scores",
        }
    finally:
        db.close()


def test_lock_failure_records_step_and_empty_counts(shop, monkeypatch):
    """Ook een fout vóór de scoreketen heeft hetzelfde zichtbare runcontract."""
    from contextlib import contextmanager
    import services.refresh as refresh

    @contextmanager
    def unavailable_lock():
        yield False

    monkeypatch.setattr(refresh, "_feed_sync_lock", unavailable_lock)
    db = SessionLocal()
    try:
        assert refresh.run_rankings_refresh(
            db, shop_id=shop, trigger="lock_test") is None
        run = db.query(models.EngineRun).filter(
            models.EngineRun.shop_id == shop,
            models.EngineRun.engine_name == "rankings",
        ).order_by(models.EngineRun.id.desc()).first()
        assert run.result_summary == {
            "trigger": "lock_test",
            "category_scores": None,
            "cis_scores": None,
            "rankings": None,
            "failed_step": "feed_sync_lock",
        }
        assert "step=feed_sync_lock" in run.error_message
    finally:
        db.close()


def test_price_observations_populate_price_relevance_without_profile_data(shop):
    """Recente prijsdata blijft bruikbaar als alle relevante profielvelden leeg zijn."""
    from engine.category_competition import calculate_all_category_scores
    from engine.competition_rankings import run_competitor_rankings

    db = SessionLocal()
    try:
        profile = db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.shop_id == shop,
            models.CompetitorProfile.competitor_name == COMP_1,
        ).one()
        profile.functional_overlap_score = None
        profile.price_change_frequency = None
        profile.relevance_label = None
        profile.in_stock_rate = None
        db.add(models.FactCompetitorPriceDaily(
            date=date.today(),
            sku_id=f"{PFX}-SKU",
            competitor_name=COMP_1,
            price=19.0,
            source="test",
            shop_id=shop,
        ))
        db.commit()

        assert calculate_all_category_scores(db, shop_id=shop) == 1
        category_row = db.query(models.CategoryCompetitorRelevance).filter(
            models.CategoryCompetitorRelevance.shop_id == shop,
            models.CategoryCompetitorRelevance.competitor_name == COMP_1,
            models.CategoryCompetitorRelevance.category == CAT,
        ).one()
        assert category_row.pricing_relevance_score > 0

        run_competitor_rankings(db, shop_id=shop)
        ranking = db.query(models.CompetitorRanking).filter(
            models.CompetitorRanking.shop_id == shop,
            models.CompetitorRanking.scope == "overall",
            models.CompetitorRanking.competitor_name == COMP_1,
        ).one()
        assert ranking.price_relevance_score > 0
        components = ranking.evidence["components"]["price_relevance"]
        assert components["avg_pricing_relevance"]["available"] is True
        assert components["price_change_frequency"]["available"] is False
        assert ranking.price_relevance_score == pytest.approx(
            category_row.pricing_relevance_score / 100.0, abs=1e-4)
    finally:
        db.close()


def test_category_refresh_does_not_touch_another_shop(shop):
    """Een winkelgerichte categoriescore-run vervangt geen rijen van een andere shop."""
    from engine.category_competition import calculate_all_category_scores

    db = SessionLocal()
    other_shop_id = None
    other_sku = f"{PFX}-OTHER-SKU"
    other_comp = f"{PFX}-other-shop.nl"
    try:
        other = models.DimShop(
            shop_code=f"{PFX}-other-shop",
            name=f"{PFX} Other Shop",
            active=False,
        )
        db.add(other)
        db.flush()
        other_shop_id = other.id
        db.add(models.DimProduct(
            sku_id=other_sku,
            product_name=f"{PFX} other product",
            category=f"{CAT}-other",
            current_price=10.0,
            shop_id=other_shop_id,
        ))
        db.add(models.CategoryCompetitorRelevance(
            shop_id=other_shop_id,
            competitor_name=other_comp,
            category=f"{CAT}-other",
            relevance_score=77.0,
        ))
        db.commit()

        calculate_all_category_scores(db, shop_id=shop)
        untouched = db.query(models.CategoryCompetitorRelevance).filter(
            models.CategoryCompetitorRelevance.shop_id == other_shop_id,
            models.CategoryCompetitorRelevance.competitor_name == other_comp,
        ).one()
        assert untouched.relevance_score == 77.0
    finally:
        if other_shop_id is not None:
            db.query(models.CategoryCompetitorRelevance).filter(
                models.CategoryCompetitorRelevance.shop_id == other_shop_id
            ).delete(synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == other_shop_id
            ).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.shop_id == other_shop_id
            ).delete(synchronize_session=False)
            db.query(models.DimShop).filter(
                models.DimShop.id == other_shop_id
            ).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_unknown_scores_remain_null_in_storage_and_api(
    client, admin_headers, shop
):
    """Geen geldige brondata wordt niet als een kunstmatige nul gepubliceerd."""
    from engine.competition_rankings import run_competitor_rankings

    db = SessionLocal()
    try:
        profile = db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.shop_id == shop,
            models.CompetitorProfile.competitor_name == COMP_1,
        ).one()
        profile.functional_overlap_score = None
        profile.price_change_frequency = None
        profile.relevance_label = None
        profile.in_stock_rate = None
        db.query(models.CategoryCompetitorRelevance).filter(
            models.CategoryCompetitorRelevance.shop_id == shop,
            models.CategoryCompetitorRelevance.competitor_name == COMP_1,
        ).delete(synchronize_session=False)
        db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == f"{PFX}-SKU",
            models.CompetitorInfluenceScore.competitor_name == COMP_1,
        ).delete(synchronize_session=False)
        db.commit()

        run_competitor_rankings(db, shop_id=shop)
        ranking = db.query(models.CompetitorRanking).filter(
            models.CompetitorRanking.shop_id == shop,
            models.CompetitorRanking.scope == "overall",
            models.CompetitorRanking.competitor_name == COMP_1,
        ).one()
        assert ranking.competition_relevance_score is None
        assert ranking.price_relevance_score is None
        assert ranking.influence_score is None
        assert ranking.combined_score is None
    finally:
        db.close()

    response = client.get(
        f"/api/competition/rankings?scope=overall&shop_id={shop}",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    item = next(
        r for r in response.json()["rankings"]
        if r["competitor_name"] == COMP_1)
    assert item["competition_relevance_score"] is None
    assert item["price_relevance_score"] is None
    assert item["influence_score"] is None
    assert item["combined_score"] is None


def test_measured_zero_remains_a_real_zero(shop):
    """Een aanwezige nul telt wel mee en blijft onderscheidbaar van onbekend."""
    from engine.competition_rankings import run_competitor_rankings

    db = SessionLocal()
    try:
        profile = db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.shop_id == shop,
            models.CompetitorProfile.competitor_name == COMP_1,
        ).one()
        profile.functional_overlap_score = 0.0
        profile.price_change_frequency = 0.0
        db.query(models.CategoryCompetitorRelevance).filter(
            models.CategoryCompetitorRelevance.shop_id == shop,
            models.CategoryCompetitorRelevance.competitor_name == COMP_1,
        ).delete(synchronize_session=False)
        db.commit()

        run_competitor_rankings(db, shop_id=shop)
        ranking = db.query(models.CompetitorRanking).filter(
            models.CompetitorRanking.shop_id == shop,
            models.CompetitorRanking.scope == "overall",
            models.CompetitorRanking.competitor_name == COMP_1,
        ).one()
        assert ranking.competition_relevance_score == 0.0
        assert ranking.price_relevance_score == 0.0
        assert ranking.evidence["components"]["competition_relevance"][
            "functional_overlap_score"]["available"] is True
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
