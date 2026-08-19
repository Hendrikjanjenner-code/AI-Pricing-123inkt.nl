"""
Tests voor taak: toon in het prijsdashboard hoeveel concurrenten wegens
levertijd (en andere redenen) zijn uitgesloten.

Dekking:
- /api/competition/summary bevat `excluded_by_reason` (som van de
  excluded_reasons-JSON per SKU, alleen over de laatste scoring-run)
  en `last_run_date`.
- Oudere run-datums tellen niet mee in de breakdown.
- Lege staat: geen scores → lege breakdown, last_run_date None.
"""
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from engine import competition_engine as ce

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"EXCLSUM{uuid.uuid4().hex[:6]}"
SKU_A = f"{PFX}-sku-a"
SKU_B = f"{PFX}-sku-b"


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


@pytest.fixture(scope="module")
def seed(client):
    db = SessionLocal()
    today = date.today()
    yesterday = today - timedelta(days=1)
    shop_id = None
    score_ids = []
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} ExclSum Shop", active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id

        for sku in (SKU_A, SKU_B):
            db.add(models.DimProduct(
                sku_id=sku, product_name=f"ExclSum {sku}", category=f"{PFX}-cat",
                current_price=20.0, cost_price=12.0, stock_quantity=5, shop_id=shop_id,
            ))
        db.flush()

        def score(sku, run_date, reasons, excluded):
            s = models.SkuCompetitionScore(
                shop_id=shop_id, sku_id=sku, run_date=run_date,
                pcis_score=0.5, competition_class="Monitor",
                competitors_used=3, competitors_excluded=excluded,
                excluded_reasons=reasons,
            )
            db.add(s)
            db.flush()
            score_ids.append(s.id)

        # Laatste run (vandaag): telt mee
        score(SKU_A, today, {ce.EXCLUSION_BAD_DELIVERY: 2, ce.EXCLUSION_OUT_OF_STOCK: 1}, 3)
        score(SKU_B, today, {ce.EXCLUSION_BAD_DELIVERY: 1, ce.EXCLUSION_OUTLIER: 4}, 5)
        # Oudere run: mag NIET meetellen in de breakdown
        score(SKU_A, yesterday, {ce.EXCLUSION_BAD_DELIVERY: 99}, 99)

        db.commit()
        yield shop_id
    finally:
        db.rollback()
        try:
            if score_ids:
                db.query(models.SkuCompetitionScore).filter(
                    models.SkuCompetitionScore.id.in_(score_ids)).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_([SKU_A, SKU_B])).delete(synchronize_session=False)
            if shop_id:
                cost_model = getattr(models, "CostUsageRecord", None)
                if cost_model is not None and hasattr(cost_model, "shop_id"):
                    db.query(cost_model).filter(cost_model.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def test_summary_excluded_by_reason_last_run_only(client, admin_headers, seed):
    r = client.get("/api/competition/summary", params={"shop_id": seed}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["last_run_date"] == date.today().isoformat()
    breakdown = body["excluded_by_reason"]
    assert breakdown[ce.EXCLUSION_BAD_DELIVERY] == 3      # 2 + 1, zonder de 99 van gisteren
    assert breakdown[ce.EXCLUSION_OUT_OF_STOCK] == 1
    assert breakdown[ce.EXCLUSION_OUTLIER] == 4


def test_score_competition_counts_fully_excluded_sku(client, admin_headers):
    """Integratie: een SKU waarvan álle concurrentprijzen wegens levertijd
    worden afgewezen krijgt tóch een score-rij met de levertijdtelling,
    zodat de summary-breakdown deze uitsluitingen meetelt."""
    import feed_ingest
    from services import import_settings as imps

    pfx = f"EXCLFULL{uuid.uuid4().hex[:6]}"
    sku = f"{pfx}-sku"
    db = SessionLocal()
    shop_id = None
    fact_ids = []
    today = date.today()
    try:
        shop = models.DimShop(shop_code=f"{pfx}-shop", name=f"{pfx} Full Excl Shop", active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id
        db.add(models.DimProduct(
            sku_id=sku, product_name="Fully excluded product", category=f"{pfx}-cat",
            current_price=20.0, cost_price=12.0, stock_quantity=5, shop_id=shop_id,
        ))
        db.flush()
        threshold = imps.get_settings(db).get(
            "max_delivery_days", imps.DEFAULT_MAX_DELIVERY_DAYS
        ) or imps.DEFAULT_MAX_DELIVERY_DAYS
        for comp in (f"{pfx}-slow1.nl", f"{pfx}-slow2.nl"):
            row = models.FactCompetitorPriceDaily(
                date=today, sku_id=sku, shop_id=shop_id,
                competitor_name=comp, price=15.0, in_stock=True,
                delivery_days=threshold + 10,
            )
            db.add(row)
            db.flush()
            fact_ids.append(row.id)
        db.commit()

        feed_ingest.score_competition(db, shop_id=shop_id)

        score = db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.sku_id == sku,
            models.SkuCompetitionScore.shop_id == shop_id,
        ).one()
        assert score.competitors_used == 0
        assert score.competitors_excluded == 2
        assert score.reference_price is None
        assert (score.excluded_reasons or {})[ce.EXCLUSION_BAD_DELIVERY] == 2

        r = client.get("/api/competition/summary", params={"shop_id": shop_id}, headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["excluded_by_reason"][ce.EXCLUSION_BAD_DELIVERY] == 2
    finally:
        db.rollback()
        try:
            db.query(models.SkuCompetitionScore).filter(
                models.SkuCompetitionScore.sku_id == sku).delete(synchronize_session=False)
            if fact_ids:
                db.query(models.FactCompetitorPriceDaily).filter(
                    models.FactCompetitorPriceDaily.id.in_(fact_ids)).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id == sku).delete(synchronize_session=False)
            if shop_id:
                cost_model = getattr(models, "CostUsageRecord", None)
                if cost_model is not None and hasattr(cost_model, "shop_id"):
                    db.query(cost_model).filter(cost_model.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def test_summary_empty_shop_has_empty_breakdown(client, admin_headers):
    db = SessionLocal()
    shop_id = None
    try:
        shop = models.DimShop(shop_code=f"{PFX}-empty", name=f"{PFX} Empty Shop", active=True)
        db.add(shop)
        db.commit()
        shop_id = shop.id

        r = client.get("/api/competition/summary", params={"shop_id": shop_id}, headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["excluded_by_reason"] == {}
        assert body["last_run_date"] is None
    finally:
        try:
            if shop_id:
                cost_model = getattr(models, "CostUsageRecord", None)
                if cost_model is not None and hasattr(cost_model, "shop_id"):
                    db.query(cost_model).filter(cost_model.shop_id == shop_id).delete(synchronize_session=False)
                db.query(models.DimShop).filter(models.DimShop.id == shop_id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()
