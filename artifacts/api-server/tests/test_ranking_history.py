"""
Tests voor GET /api/competition/rankings/history (taak: rank-verloop per
concurrent). Dekt: verloop over meerdere runs, scope-filter en shop-scoping.
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

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"RHTEST{uuid.uuid4().hex[:6]}"
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


@pytest.fixture(scope="module")
def seed(client):
    """Twee test-shops met elk eigen rankinghistorie over 3 runs."""
    db = SessionLocal()
    today = date.today()
    shop_a_id = shop_b_id = None
    try:
        shop_a = models.DimShop(shop_code=f"{PFX}-a", name=f"{PFX} Shop A", active=True)
        shop_b = models.DimShop(shop_code=f"{PFX}-b", name=f"{PFX} Shop B", active=True)
        db.add_all([shop_a, shop_b])
        db.flush()
        shop_a_id, shop_b_id = shop_a.id, shop_b.id

        rows = []
        # Shop A, scope overall: COMP_1 stijgt (3 -> 2 -> 1), COMP_2 daalt
        for i, (r1, r2) in enumerate([(3, 1), (2, 2), (1, 3)]):
            rd = today - timedelta(days=(2 - i) * 7)
            rows.append(models.CompetitorRanking(
                shop_id=shop_a_id, run_date=rd, scope="overall",
                competitor_name=COMP_1, rank=r1, combined_score=0.5))
            rows.append(models.CompetitorRanking(
                shop_id=shop_a_id, run_date=rd, scope="overall",
                competitor_name=COMP_2, rank=r2, combined_score=0.4))
        # Shop A, andere scope: alleen laatste run
        rows.append(models.CompetitorRanking(
            shop_id=shop_a_id, run_date=today, scope=f"{PFX}-cat",
            competitor_name=COMP_1, rank=1, combined_score=0.9))
        # Shop B: eigen historie die NIET in shop A mag lekken
        rows.append(models.CompetitorRanking(
            shop_id=shop_b_id, run_date=today, scope="overall",
            competitor_name=f"{PFX}-other.nl", rank=1, combined_score=0.7))
        db.add_all(rows)
        db.commit()
        yield {"shop_a": shop_a_id, "shop_b": shop_b_id}
    finally:
        db.rollback()
        for sid in (shop_a_id, shop_b_id):
            if sid is None:
                continue
            db.query(models.CompetitorRanking).filter(
                models.CompetitorRanking.shop_id == sid).delete()
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete()
            db.query(models.DimShop).filter(models.DimShop.id == sid).delete()
        db.commit()
        db.close()


def test_history_returns_full_rank_course(client, admin_headers, seed):
    r = client.get(
        f"/api/competition/rankings/history?scope=overall&shop_id={seed['shop_a']}",
        headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["run_dates"]) == 3
    hist = data["history"]
    assert [h["rank"] for h in hist[COMP_1]] == [3, 2, 1]
    assert [h["rank"] for h in hist[COMP_2]] == [1, 2, 3]
    # Oplopend gesorteerd op run_date
    dates = [h["run_date"] for h in hist[COMP_1]]
    assert dates == sorted(dates)


def test_history_is_scope_filtered(client, admin_headers, seed):
    r = client.get(
        f"/api/competition/rankings/history?scope={PFX}-cat&shop_id={seed['shop_a']}",
        headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert list(data["history"].keys()) == [COMP_1]
    assert len(data["history"][COMP_1]) == 1


def test_history_is_shop_scoped(client, admin_headers, seed):
    r = client.get(
        f"/api/competition/rankings/history?scope=overall&shop_id={seed['shop_b']}",
        headers=admin_headers)
    assert r.status_code == 200
    hist = r.json()["history"]
    assert COMP_1 not in hist and COMP_2 not in hist
    assert f"{PFX}-other.nl" in hist


def test_history_competitor_filter(client, admin_headers, seed):
    r = client.get(
        f"/api/competition/rankings/history?scope=overall&shop_id={seed['shop_a']}"
        f"&competitor={COMP_1}",
        headers=admin_headers)
    assert r.status_code == 200
    hist = r.json()["history"]
    assert list(hist.keys()) == [COMP_1]
