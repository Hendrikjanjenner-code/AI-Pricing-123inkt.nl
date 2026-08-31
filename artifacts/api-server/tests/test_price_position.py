"""
Tests voor taak #318: prijspositie per aanbieder & veilige verhogingsruimte.

- GET /api/competition/price-position — eigen shop in dezelfde ranglijst,
  gedeelde posities bij gelijke prijzen, sortering 1→20 en 20→1,
  uitgesloten/geblokkeerde prijzen tellen niet mee, productscope,
  item_detail bij exact één product.
- GET /api/competition/price-increase-room — voorstel blijft strikt onder
  nummer 2, gedeelde positie 1 geeft geen ruimte, max_price cap,
  geen totaalbedrag zonder afzetdata (en wél met afzetdata).
- GET /api/competition/rankings — limit kapt server-side af; total blijft
  het volledige aantal.

Conventies (gedeelde dev-test-DB): eigen DimShop, uuid-prefix, shop_id
expliciet, volledige teardown incl. CostUsageRecord.
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

PFX = f"PPOS{uuid.uuid4().hex[:6].upper()}"
SKU_A = f"{PFX}-SKU-A"   # eigen shop strikt goedkoopste (ruimte)
SKU_B = f"{PFX}-SKU-B"   # gedeelde positie 1 met concurrent
SKU_C = f"{PFX}-SKU-C"   # eigen shop duurste
COMP_1 = f"{PFX}-alfa.nl"
COMP_2 = f"{PFX}-beta.nl"
COMP_OUT = f"{PFX}-uitbijter.nl"
BRAND = f"{PFX}-Brand"


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
    ids: dict = {}
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop",
                              active=True)
        db.add(shop)
        db.flush()
        sid = shop.id
        db.add_all([
            models.DimProduct(sku_id=SKU_A, product_name=f"{PFX} Product A",
                              brand=BRAND, current_price=10.00,
                              max_price=14.00, shop_id=sid),
            models.DimProduct(sku_id=SKU_B, product_name=f"{PFX} Product B",
                              brand=BRAND, current_price=8.00, shop_id=sid),
            models.DimProduct(sku_id=SKU_C, product_name=f"{PFX} Product C",
                              brand=BRAND, current_price=20.00, shop_id=sid),
        ])
        rows = [
            # SKU_A: wij 10.00, nr2 = COMP_1 12.00, COMP_2 13.00 → ruimte
            (SKU_A, COMP_1, 12.00, None),
            (SKU_A, COMP_2, 13.00, None),
            # uitgesloten uitbijter: mag nooit meetellen (anders geen positie 1)
            (SKU_A, COMP_OUT, 1.00, "COMPETITOR_IGNORED_OUTLIER"),
            # SKU_B: gedeelde positie 1 (wij 8.00, COMP_1 8.00), COMP_2 9.00
            (SKU_B, COMP_1, 8.00, None),
            (SKU_B, COMP_2, 9.00, None),
            # SKU_C: wij duurste (20.00 vs 15.00/16.00)
            (SKU_C, COMP_1, 15.00, None),
            (SKU_C, COMP_2, 16.00, None),
        ]
        for sku, comp, price, excl in rows:
            db.add(models.FactCompetitorPriceDaily(
                date=today, sku_id=sku, shop_id=sid, competitor_name=comp,
                price=price, source="manual", excluded_reason=excl))
        # Oudere (goedkopere) waarneming die NIET mag meetellen: alleen de
        # meest recente dag per SKU geldt.
        db.add(models.FactCompetitorPriceDaily(
            date=today - timedelta(days=3), sku_id=SKU_A, shop_id=sid,
            competitor_name=COMP_1, price=5.00, source="manual"))
        # Rankings voor de limit-test.
        for rank, name in ((1, COMP_1), (2, COMP_2), (3, COMP_OUT)):
            db.add(models.CompetitorRanking(
                shop_id=sid, run_date=today, scope="overall",
                competitor_name=name, rank=rank, combined_score=1.0 / rank))
        db.commit()
        ids = {"sid": sid}
        yield ids
    finally:
        db.rollback()
        sid = ids.get("sid")
        if sid is not None:
            for M, col in [
                (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.shop_id),
                (models.FactSalesDaily, models.FactSalesDaily.shop_id),
                (models.CompetitorRanking, models.CompetitorRanking.shop_id),
                (models.CostUsageRecord, models.CostUsageRecord.shop_id),
            ]:
                db.query(M).filter(col == sid).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_([SKU_A, SKU_B, SKU_C])
            ).delete(synchronize_session=False)
            db.query(models.DimShop).filter(models.DimShop.id == sid).delete(
                synchronize_session=False)
            db.commit()
        db.close()


def _pos(client, headers, sid, **extra):
    params = {"shop_id": sid, "brands": BRAND}
    params.update(extra)
    r = client.get("/api/competition/price-position", params=params,
                   headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ── price-position ────────────────────────────────────────────────────────────

def test_eigen_shop_in_ranglijst_met_gedeelde_posities(client, admin_headers, seed):
    data = _pos(client, admin_headers, seed["sid"])
    assert data["items_compared"] == 3
    own = next(p for p in data["providers"] if p["is_own"])
    # Eigen posities: A=1 (strikt), B=1 (gedeeld), C=3 → pos1=2 waarvan 1 gedeeld
    assert own["items_compared"] == 3
    assert own["pos1_count"] == 2
    assert own["pos1_shared_count"] == 1
    # COMP_1: positie 1 gedeeld op SKU_B én strikt op SKU_C (goedkoopste daar)
    c1 = next(p for p in data["providers"] if p["name"] == COMP_1)
    assert c1["pos1_count"] == 2 and c1["pos1_shared_count"] == 1
    # Uitgesloten uitbijter komt niet voor als aanbieder; wel in de uitlegteller.
    assert all(p["name"] != COMP_OUT for p in data["providers"])
    assert data["excluded_by_reason"].get("COMPETITOR_IGNORED_OUTLIER") == 1


def test_sortering_beide_richtingen_en_limit(client, admin_headers, seed):
    asc = _pos(client, admin_headers, seed["sid"], sort="position_asc")
    desc = _pos(client, admin_headers, seed["sid"], sort="position_desc")
    meds_asc = [p["median_position"] for p in asc["providers"]]
    assert meds_asc == sorted(meds_asc)
    meds_desc = [p["median_position"] for p in desc["providers"]]
    assert meds_desc == sorted(meds_desc, reverse=True)
    # limit=1: één concurrent + de eigen shop blijft altijd zichtbaar
    lim = _pos(client, admin_headers, seed["sid"], limit=1)
    assert lim["total_providers"] == 3
    assert len(lim["providers"]) == 2
    assert any(p["is_own"] for p in lim["providers"])


def test_exact_product_geeft_item_detail(client, admin_headers, seed):
    data = _pos(client, admin_headers, seed["sid"], sku_query=f"sku:{SKU_A}")
    det = data["item_detail"]
    assert det is not None and det["sku_id"] == SKU_A
    by_pos = [(p["position"], p["is_own"], p["price"]) for p in det["providers"]]
    # wij 10.00 op 1 (oude 5.00-waarneming telt niet), dan 12.00 en 13.00
    assert by_pos[0] == (1, True, 10.00)
    assert [p[0] for p in by_pos] == [1, 2, 3]


def test_scope_zonder_match_is_leeg(client, admin_headers, seed):
    data = _pos(client, admin_headers, seed["sid"],
                brands=f"{PFX}-BestaatNiet")
    assert data["items_compared"] == 0
    assert data["providers"] == []


# ── price-increase-room ───────────────────────────────────────────────────────

def _room(client, headers, sid, **extra):
    params = {"shop_id": sid, "brands": BRAND}
    params.update(extra)
    r = client.get("/api/competition/price-increase-room", params=params,
                   headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_verhoging_blijft_onder_nummer_twee(client, admin_headers, seed):
    data = _room(client, admin_headers, seed["sid"], safety_margin_pct=1.0)
    assert data["items_at_pos1_strict"] == 1
    assert data["items_pos1_shared"] == 1        # SKU_B: gedeeld → geen ruimte
    assert data["items_with_room"] == 1
    item = data["items"][0]
    assert item["sku_id"] == SKU_A
    assert item["pos2_competitor"] == COMP_1
    assert item["pos2_price"] == 12.00
    # 12.00 × 0.99 = 11.88 → strikt onder nr. 2, boven eigen prijs
    assert item["own_price"] < item["proposed_price"] < item["pos2_price"]
    assert item["proposed_price"] == 11.88
    assert item["extra_margin_per_unit"] == 1.88
    assert data["boundary_competitors"][0]["name"] == COMP_1
    # Geen afzetdata → geen verzonnen totaalbedrag
    assert data["volume_known"] is False
    assert data["total_uplift_estimate_30d"] is None


def test_max_price_cap(client, admin_headers, seed):
    db = SessionLocal()
    try:
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_A).update(
            {"max_price": 11.00}, synchronize_session=False)
        db.commit()
        data = _room(client, admin_headers, seed["sid"])
        item = data["items"][0]
        assert item["proposed_price"] == 11.00
        assert item["capped_by_max_price"] is True
    finally:
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_A).update(
            {"max_price": 14.00}, synchronize_session=False)
        db.commit()
        db.close()


def test_totaalbedrag_alleen_met_afzetdata(client, admin_headers, seed):
    db = SessionLocal()
    try:
        db.add(models.FactSalesDaily(
            date=date.today() - timedelta(days=2), sku_id=SKU_A,
            shop_id=seed["sid"], units_sold=10))
        db.commit()
        data = _room(client, admin_headers, seed["sid"], safety_margin_pct=1.0)
        assert data["volume_known"] is True
        assert data["total_uplift_estimate_30d"] == pytest.approx(18.80)
    finally:
        db.query(models.FactSalesDaily).filter(
            models.FactSalesDaily.shop_id == seed["sid"]).delete(
            synchronize_session=False)
        db.commit()
        db.close()


# ── rankings limit ────────────────────────────────────────────────────────────

def test_rankings_limit_topn(client, admin_headers, seed):
    r = client.get("/api/competition/rankings",
                   params={"shop_id": seed["sid"], "limit": 2},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 3
    assert data["shown"] == 2
    assert [x["rank"] for x in data["rankings"]] == [1, 2]


# ── shop-authorisatie ─────────────────────────────────────────────────────────

def test_shop_scoped_gebruiker_krijgt_403_op_andere_shop(client, admin_headers, seed):
    """Een gebruiker beperkt tot shop A mag geen prijspositie/verhogings-
    ruimte/rankings van een andere shop opvragen (tenant-isolatie)."""
    uname = f"ppos_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/users", json={
        "username": uname, "email": f"{uname}@test.local",
        "password": "Wachtwoord123!", "role": "analyst", "full_name": uname,
    }, headers=admin_headers)
    assert resp.status_code in (200, 201), resp.text
    uid = resp.json().get("id") or resp.json().get("user", {}).get("id")
    db = SessionLocal()
    try:
        db.add(models.UserScope(user_id=uid, scope_type="shop",
                                scope_value=str(seed["sid"])))
        db.commit()
    finally:
        db.close()
    try:
        login = client.post("/api/auth/login", json={
            "username": uname, "password": "Wachtwoord123!"})
        assert login.status_code == 200, login.text
        h = {"Authorization": f"Bearer {login.json()['token']}"}
        other = 1 if seed["sid"] != 1 else 2
        for path in ("/api/competition/price-position",
                     "/api/competition/price-increase-room",
                     "/api/competition/rankings"):
            r = client.get(path, params={"shop_id": other}, headers=h)
            assert r.status_code == 403, f"{path}: {r.status_code} {r.text}"
            r_own = client.get(path, params={"shop_id": seed["sid"]}, headers=h)
            assert r_own.status_code == 200, f"{path}: {r_own.status_code} {r_own.text}"
    finally:
        db = SessionLocal()
        try:
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.username == uname).delete(
                synchronize_session=False)
            db.query(models.UserScope).filter(
                models.UserScope.user_id == uid).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id == uid).delete(
                synchronize_session=False)
            db.commit()
        finally:
            db.close()
