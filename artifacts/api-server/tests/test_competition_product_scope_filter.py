"""
Tests voor de globale filtercontext (hiërarchie + merk) op de product-scoped
Competition Intelligence-endpoints (taak #263-uitbreiding):

- GET /categories
- GET /assortment-gap
- GET /strategies
- GET /trends/price-index
- GET /trends/coverage
- GET /coverage
- GET /events
- GET /availability
- GET /landscape

Elk endpoint accepteert hierarchy_node_ids + brands en beperkt de resultaten
tot facts/afgeleiden van eigen SKU's in de gefilterde set (descendants tellen
server-side mee). Een selectie die niets matcht levert een lege lijst op
(filter actief, geen fallback); het weglaten van de params levert de
ongefilterde resultaten.

Conventies (gedeelde Postgres dev-DB!): eigen DimProduct-rijen met uniek
uuid-prefix, eigen hiërarchie (status='active', path '/<id>/'), shop_id
expliciet, en volledige teardown. Nooit aannemen dat de DB leeg is.
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

PFX = f"CPS{uuid.uuid4().hex[:6].upper()}"
COMP_COFFEE = f"{PFX}-koffieboer.nl"
COMP_TEA = f"{PFX}-theehuis.nl"
CAT_COFFEE = f"{PFX}-Coffee"
CAT_TEA = f"{PFX}-Tea"
BRAND_COFFEE = f"{PFX}-Brew"
BRAND_TEA = f"{PFX}-Leaf"

SKU_COFFEE = f"{PFX}-SKU-COFFEE"
SKU_TEA = f"{PFX}-SKU-TEA"


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
    """Eigen test-shop met twee takken (Coffee/Tea), elk met eigen concurrent.

    Elke concurrent is uitsluitend op zijn eigen tak (SKU + categorie)
    waargenomen, zodat een subnode-filter aantoonbaar de andere tak uitsluit.
    """
    db = SessionLocal()
    today = date.today()
    ids: dict = {}
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id

        db.add_all([
            models.DimProduct(sku_id=SKU_COFFEE, product_name="Koffiebonen",
                              brand=BRAND_COFFEE, category=CAT_COFFEE,
                              current_price=12.0, shop_id=sid),
            models.DimProduct(sku_id=SKU_TEA, product_name="Groene thee",
                              brand=BRAND_TEA, category=CAT_TEA,
                              current_price=6.0, shop_id=sid),
        ])
        db.flush()

        root = models.ProductHierarchyNode(name=f"{PFX}-Drinks", level=1,
                                           path_names=f"{PFX}-Drinks")
        db.add(root); db.flush()
        root.path = f"/{root.id}/"
        coffee = models.ProductHierarchyNode(
            name=f"{PFX}-CoffeeNode", level=2, parent_id=root.id,
            path_names=f"{PFX}-Drinks > {PFX}-CoffeeNode")
        tea = models.ProductHierarchyNode(
            name=f"{PFX}-TeaNode", level=2, parent_id=root.id,
            path_names=f"{PFX}-Drinks > {PFX}-TeaNode")
        db.add_all([coffee, tea]); db.flush()
        coffee.path = f"/{root.id}/{coffee.id}/"
        tea.path = f"/{root.id}/{tea.id}/"
        db.add_all([
            models.ProductHierarchyAssignment(sku_id=SKU_COFFEE, node_id=coffee.id, status="active"),
            models.ProductHierarchyAssignment(sku_id=SKU_TEA, node_id=tea.id, status="active"),
        ])

        # Concurrentprijs-feed: elke concurrent alleen op zijn eigen tak, over
        # meerdere dagen zodat /strategies en /trends/price-index werken.
        for offset in range(6):
            d = today - timedelta(days=offset)
            db.add_all([
                models.FactCompetitorPriceDaily(
                    date=d, sku_id=SKU_COFFEE, shop_id=sid,
                    competitor_name=COMP_COFFEE, price=9.99 + offset * 0.1,
                    source="manual"),
                models.FactCompetitorPriceDaily(
                    date=d, sku_id=SKU_TEA, shop_id=sid,
                    competitor_name=COMP_TEA, price=4.99 + offset * 0.1,
                    source="manual"),
            ])
            # Eigen prijshistorie voor /trends/price-index
            db.add_all([
                models.FactPriceDaily(date=d, sku_id=SKU_COFFEE, price=12.0),
                models.FactPriceDaily(date=d, sku_id=SKU_TEA, price=6.0),
            ])

        # Profielen + rankings + market roles per concurrent.
        for rank, name in ((1, COMP_COFFEE), (2, COMP_TEA)):
            db.add(models.CompetitorProfile(
                shop_id=sid, competitor_name=name, domain=name,
                functional_overlap_score=0.5, relevance_label="HIGH"))
            db.add(models.CompetitorRanking(
                shop_id=sid, run_date=today, scope="overall",
                competitor_name=name, rank=rank, combined_score=1.0 / rank,
                competition_relevance_score=0.8 / rank))
            db.add(models.CompetitorMarketRole(
                shop_id=sid, competitor_name=name, role="challenger",
                valid_to=None))

        # Categoriescores incl. cross-categorie tegenvoorbeeld: de
        # koffieconcurrent heeft óók een rij voor de thee-categorie, maar is
        # nooit op een thee-SKU waargenomen — die mag bij een filter nooit
        # verschijnen (gecorreleerd EXISTS in /categories).
        db.add_all([
            models.CategoryCompetitorRelevance(
                shop_id=sid, competitor_name=COMP_COFFEE, category=CAT_COFFEE,
                combined_score=80.0, relevance_label="HIGH", traffic_light="green"),
            models.CategoryCompetitorRelevance(
                shop_id=sid, competitor_name=COMP_TEA, category=CAT_TEA,
                combined_score=70.0, relevance_label="HIGH", traffic_light="green"),
            models.CategoryCompetitorRelevance(
                shop_id=sid, competitor_name=COMP_COFFEE, category=CAT_TEA,
                combined_score=60.0, relevance_label="MONITOR", traffic_light="orange"),
        ])

        # Assortment gaps per categorie/concurrent (geen shop_id op dit model).
        db.add_all([
            models.AssortmentGap(
                category=CAT_COFFEE, competitor_name=COMP_COFFEE,
                gap_type="MERK", gap_value=f"{PFX}-GapBrandCoffee",
                opportunity_score=90.0, run_date=today),
            models.AssortmentGap(
                category=CAT_TEA, competitor_name=COMP_TEA,
                gap_type="MERK", gap_value=f"{PFX}-GapBrandTea",
                opportunity_score=85.0, run_date=today),
            # Cross-categorie tegenvoorbeeld voor /assortment-gap.
            models.AssortmentGap(
                category=CAT_TEA, competitor_name=COMP_COFFEE,
                gap_type="MERK", gap_value=f"{PFX}-GapCross",
                opportunity_score=50.0, run_date=today),
        ])

        # Dekkingsresultaten (totaal, category=None) per concurrent.
        db.add_all([
            models.CompetitorCoverageResult(
                shop_id=sid, run_date=today, competitor_name=COMP_COFFEE,
                category=None, own_products=1, matched_products=1,
                coverage_pct=100.0),
            models.CompetitorCoverageResult(
                shop_id=sid, run_date=today, competitor_name=COMP_TEA,
                category=None, own_products=1, matched_products=1,
                coverage_pct=100.0),
        ])

        # Prijs-events per SKU.
        db.add_all([
            models.CompetitorPriceEvent(
                shop_id=sid, event_date=today, sku_id=SKU_COFFEE,
                competitor_name=COMP_COFFEE, event_type="PRICE_CHANGE",
                old_price=10.0, new_price=9.5, change_pct=-5.0, direction="down"),
            models.CompetitorPriceEvent(
                shop_id=sid, event_date=today, sku_id=SKU_TEA,
                competitor_name=COMP_TEA, event_type="PRICE_CHANGE",
                old_price=5.0, new_price=4.5, change_pct=-10.0, direction="down"),
        ])

        # Beschikbaarheid per concurrent.
        db.add_all([
            models.CompetitorAvailabilityDaily(
                shop_id=sid, date=today, competitor_name=COMP_COFFEE,
                offers_total=10, offers_in_stock=9, in_stock_rate=0.9,
                avg_delivery_days=1.0),
            models.CompetitorAvailabilityDaily(
                shop_id=sid, date=today, competitor_name=COMP_TEA,
                offers_total=8, offers_in_stock=6, in_stock_rate=0.75,
                avg_delivery_days=2.0),
        ])

        db.commit()
        ids = {"sid": sid, "root": root.id, "coffee": coffee.id, "tea": tea.id,
               "skus": [SKU_COFFEE, SKU_TEA]}
        yield ids
    finally:
        db.rollback()
        sid = ids.get("sid")
        if sid is not None:
            for M, col in [
                (models.CompetitorProfile, models.CompetitorProfile.shop_id),
                (models.CompetitorRanking, models.CompetitorRanking.shop_id),
                (models.CompetitorMarketRole, models.CompetitorMarketRole.shop_id),
                (models.CategoryCompetitorRelevance, models.CategoryCompetitorRelevance.shop_id),
                (models.CompetitorCoverageResult, models.CompetitorCoverageResult.shop_id),
                (models.CompetitorPriceEvent, models.CompetitorPriceEvent.shop_id),
                (models.CompetitorAvailabilityDaily, models.CompetitorAvailabilityDaily.shop_id),
                (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.shop_id),
            ]:
                db.query(M).filter(col == sid).delete(synchronize_session=False)
            db.query(models.AssortmentGap).filter(
                models.AssortmentGap.category.in_([CAT_COFFEE, CAT_TEA])
            ).delete(synchronize_session=False)
            db.query(models.FactPriceDaily).filter(
                models.FactPriceDaily.sku_id.in_(ids["skus"])
            ).delete(synchronize_session=False)
            A = models.ProductHierarchyAssignment
            db.query(A).filter(A.sku_id.in_(ids["skus"])).delete(synchronize_session=False)
            N = models.ProductHierarchyNode
            for nid in (ids["coffee"], ids["tea"], ids["root"]):
                db.query(N).filter(N.id == nid).delete(synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(ids["skus"])).delete(synchronize_session=False)
            db.query(models.DimShop).filter(models.DimShop.id == sid).delete(
                synchronize_session=False)
            db.commit()
        db.close()


# ── /categories ───────────────────────────────────────────────────────────────

def test_categories_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/categories",
                   params={"shop_id": seed["sid"], "page_size": 500},
                   headers=admin_headers)
    assert r.status_code == 200
    cats = {i["category"] for i in r.json()["items"]}
    assert CAT_COFFEE in cats and CAT_TEA in cats


def test_categories_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/categories",
                   params={"shop_id": seed["sid"], "page_size": 500,
                           "hierarchy_node_ids": str(seed["coffee"])},
                   headers=admin_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    cats = {i["category"] for i in items}
    assert cats == {CAT_COFFEE}, items
    # Cross-categorie rij (koffieconcurrent in thee-categorie) mag niet mee.
    assert all(not (i["competitor_name"] == COMP_COFFEE and i["category"] == CAT_TEA)
               for i in items)


def test_categories_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/categories",
                   params={"shop_id": seed["sid"], "page_size": 500,
                           "hierarchy_node_ids": "999999999"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


# ── /assortment-gap ───────────────────────────────────────────────────────────

def test_assortment_gap_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/assortment-gap",
                   params={"category": CAT_TEA, "page_size": 200},
                   headers=admin_headers)
    assert r.status_code == 200
    comps = {i["competitor_name"] for i in r.json()["items"]}
    # Ongefilterd bevat de thee-categorie ook de cross-rij van de koffieconcurrent.
    assert COMP_COFFEE in comps and COMP_TEA in comps


def test_assortment_gap_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/assortment-gap",
                   params={"page_size": 200,
                           "hierarchy_node_ids": str(seed["tea"])},
                   headers=admin_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    cats = {i["category"] for i in items}
    assert cats == {CAT_TEA}, items
    # De cross-rij (koffieconcurrent in thee-categorie) is niet waargenomen op
    # een thee-SKU en mag dus verdwijnen.
    comps = {i["competitor_name"] for i in items}
    assert comps == {COMP_TEA}, items


def test_assortment_gap_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/assortment-gap",
                   params={"page_size": 200,
                           "brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    # Filter actief maar niets matcht → geen van onze eigen gaps.
    cats = {i["category"] for i in r.json()["items"]}
    assert CAT_COFFEE not in cats and CAT_TEA not in cats


# ── /strategies ───────────────────────────────────────────────────────────────

def test_strategies_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/strategies",
                   params={"shop_id": seed["sid"], "lookback_days": 30},
                   headers=admin_headers)
    assert r.status_code == 200
    names = {s.get("naam") or s.get("competitor_name") or s.get("concurrent")
             for s in r.json()["strategieen"]}
    assert COMP_COFFEE in names and COMP_TEA in names


def test_strategies_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/strategies",
                   params={"shop_id": seed["sid"], "lookback_days": 30,
                           "hierarchy_node_ids": str(seed["coffee"])},
                   headers=admin_headers)
    assert r.status_code == 200
    names = {s.get("naam") or s.get("competitor_name") or s.get("concurrent")
             for s in r.json()["strategieen"]}
    assert COMP_COFFEE in names and COMP_TEA not in names


def test_strategies_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/strategies",
                   params={"shop_id": seed["sid"], "lookback_days": 30,
                           "brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["strategieen"] == []
    assert r.json()["totaal_concurrenten"] == 0


# ── /trends/price-index ───────────────────────────────────────────────────────

def test_price_index_trend_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/trends/price-index",
                   params={"shop_id": seed["sid"], "days": 30},
                   headers=admin_headers)
    assert r.status_code == 200
    series = r.json()["series"]
    assert series, "verwacht datapunten zonder filter"
    total_obs = sum(p["observations"] for p in series)
    assert total_obs >= 2


def test_price_index_trend_gefilterd_op_subnode(client, admin_headers, seed):
    r_all = client.get("/api/competition/trends/price-index",
                       params={"shop_id": seed["sid"], "days": 30},
                       headers=admin_headers)
    r_cof = client.get("/api/competition/trends/price-index",
                       params={"shop_id": seed["sid"], "days": 30,
                               "hierarchy_node_ids": str(seed["coffee"])},
                       headers=admin_headers)
    assert r_cof.status_code == 200
    obs_all = sum(p["observations"] for p in r_all.json()["series"])
    obs_cof = sum(p["observations"] for p in r_cof.json()["series"])
    # Subnode-filter laat maar één tak over → strikt minder waarnemingen.
    assert obs_cof > 0
    assert obs_cof < obs_all


def test_price_index_trend_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/trends/price-index",
                   params={"shop_id": seed["sid"], "days": 30,
                           "hierarchy_node_ids": "999999999"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["series"] == []


# ── /trends/coverage & /coverage ──────────────────────────────────────────────

def test_trends_coverage_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/trends/coverage",
                   params={"shop_id": seed["sid"], "days": 90},
                   headers=admin_headers)
    assert r.status_code == 200
    comps = set(r.json()["competitors"].keys())
    assert COMP_COFFEE in comps and COMP_TEA in comps


def test_trends_coverage_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/trends/coverage",
                   params={"shop_id": seed["sid"], "days": 90,
                           "hierarchy_node_ids": str(seed["tea"])},
                   headers=admin_headers)
    assert r.status_code == 200
    comps = set(r.json()["competitors"].keys())
    assert comps == {COMP_TEA}, comps


def test_trends_coverage_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/trends/coverage",
                   params={"shop_id": seed["sid"], "days": 90,
                           "brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["competitors"] == {}


def test_coverage_latest_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/coverage",
                   params={"shop_id": seed["sid"]}, headers=admin_headers)
    assert r.status_code == 200
    comps = {i["competitor_name"] for i in r.json()["items"]}
    assert COMP_COFFEE in comps and COMP_TEA in comps


def test_coverage_latest_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/coverage",
                   params={"shop_id": seed["sid"],
                           "hierarchy_node_ids": str(seed["coffee"])},
                   headers=admin_headers)
    assert r.status_code == 200
    comps = {i["competitor_name"] for i in r.json()["items"]}
    assert comps == {COMP_COFFEE}, comps


def test_coverage_latest_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/coverage",
                   params={"shop_id": seed["sid"],
                           "brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []


# ── /events ───────────────────────────────────────────────────────────────────

def test_events_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/events",
                   params={"shop_id": seed["sid"], "days": 30, "page_size": 200},
                   headers=admin_headers)
    assert r.status_code == 200
    skus = {i["sku_id"] for i in r.json()["items"]}
    assert SKU_COFFEE in skus and SKU_TEA in skus


def test_events_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/events",
                   params={"shop_id": seed["sid"], "days": 30, "page_size": 200,
                           "hierarchy_node_ids": str(seed["tea"])},
                   headers=admin_headers)
    assert r.status_code == 200
    skus = {i["sku_id"] for i in r.json()["items"]}
    assert skus == {SKU_TEA}, skus


def test_events_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/events",
                   params={"shop_id": seed["sid"], "days": 30, "page_size": 200,
                           "hierarchy_node_ids": "999999999"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


# ── /availability ─────────────────────────────────────────────────────────────

def test_availability_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/availability",
                   params={"shop_id": seed["sid"], "days": 30},
                   headers=admin_headers)
    assert r.status_code == 200
    comps = set(r.json()["competitors"].keys())
    assert COMP_COFFEE in comps and COMP_TEA in comps


def test_availability_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/availability",
                   params={"shop_id": seed["sid"], "days": 30,
                           "hierarchy_node_ids": str(seed["coffee"])},
                   headers=admin_headers)
    assert r.status_code == 200
    comps = set(r.json()["competitors"].keys())
    assert comps == {COMP_COFFEE}, comps


def test_availability_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/availability",
                   params={"shop_id": seed["sid"], "days": 30,
                           "brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["competitors"] == {}


# ── /landscape ────────────────────────────────────────────────────────────────

def test_landscape_zonder_filter(client, admin_headers, seed):
    r = client.get("/api/competition/landscape",
                   params={"shop_id": seed["sid"]}, headers=admin_headers)
    assert r.status_code == 200
    comps = {i["competitor_name"] for i in r.json()["items"]}
    assert COMP_COFFEE in comps and COMP_TEA in comps


def test_landscape_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/landscape",
                   params={"shop_id": seed["sid"],
                           "hierarchy_node_ids": str(seed["tea"])},
                   headers=admin_headers)
    assert r.status_code == 200
    comps = {i["competitor_name"] for i in r.json()["items"]}
    assert comps == {COMP_TEA}, comps


def test_landscape_lege_selectie(client, admin_headers, seed):
    r = client.get("/api/competition/landscape",
                   params={"shop_id": seed["sid"],
                           "brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []
