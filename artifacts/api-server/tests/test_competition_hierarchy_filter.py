"""
Tests voor de globale filtercontext op de Competition Intelligence-endpoints
(taak #263): /dashboard, /rankings, /rankings/history en /competitors
accepteren hierarchy_node_ids + brands en beperken de resultaten tot
concurrenten die zijn waargenomen op de gefilterde SKU-set (descendants tellen
server-side mee).
"""
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"CHF{uuid.uuid4().hex[:6].upper()}"
COMP_COFFEE = f"{PFX}-koffieboer.nl"
COMP_TEA = f"{PFX}-theehuis.nl"
CAT_COFFEE = f"{PFX}-Coffee"
CAT_TEA = f"{PFX}-Tea"


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
    """Eigen test-shop met twee takken (Coffee/Tea), elk met eigen concurrent."""
    db = SessionLocal()
    today = date.today()
    ids: dict = {}
    sku_coffee = f"{PFX}-SKU-COFFEE"
    sku_tea = f"{PFX}-SKU-TEA"
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id

        db.add_all([
            models.DimProduct(sku_id=sku_coffee, product_name="Koffiebonen",
                              brand=f"{PFX}-Brew", category=CAT_COFFEE, shop_id=sid),
            models.DimProduct(sku_id=sku_tea, product_name="Groene thee",
                              brand=f"{PFX}-Leaf", category=CAT_TEA, shop_id=sid),
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
            models.ProductHierarchyAssignment(sku_id=sku_coffee, node_id=coffee.id, status="active"),
            models.ProductHierarchyAssignment(sku_id=sku_tea, node_id=tea.id, status="active"),
        ])

        # Prijswaarnemingen: elke concurrent alleen op zijn eigen tak.
        db.add_all([
            models.FactCompetitorPriceDaily(
                date=today, sku_id=sku_coffee, shop_id=sid,
                competitor_name=COMP_COFFEE, price=9.99, source="manual"),
            models.FactCompetitorPriceDaily(
                date=today, sku_id=sku_tea, shop_id=sid,
                competitor_name=COMP_TEA, price=4.99, source="manual"),
        ])

        # Rankings (één run), profielen en categoriescores voor beide.
        for rank, name in ((1, COMP_COFFEE), (2, COMP_TEA)):
            db.add(models.CompetitorRanking(
                shop_id=sid, run_date=today, scope="overall",
                competitor_name=name, rank=rank, combined_score=1.0 / rank))
            db.add(models.CompetitorProfile(
                shop_id=sid, competitor_name=name, domain=name,
                functional_overlap_score=0.5, relevance_label="HIGH"))
        db.add_all([
            models.CategoryCompetitorRelevance(
                shop_id=sid, competitor_name=COMP_COFFEE, category=CAT_COFFEE,
                combined_score=80.0, relevance_label="HIGH", traffic_light="green"),
            models.CategoryCompetitorRelevance(
                shop_id=sid, competitor_name=COMP_TEA, category=CAT_TEA,
                combined_score=70.0, relevance_label="HIGH", traffic_light="green"),
            # Cross-categorie tegenvoorbeeld: de koffieconcurrent heeft óók een
            # relevantierij voor de thee-categorie, maar is nooit op een
            # thee-SKU waargenomen. Deze rij mag bij een actieve filter nooit
            # verschijnen (gecorreleerd EXISTS in /dashboard).
            models.CategoryCompetitorRelevance(
                shop_id=sid, competitor_name=COMP_COFFEE, category=CAT_TEA,
                combined_score=60.0, relevance_label="MONITOR", traffic_light="orange"),
        ])
        db.commit()
        ids = {"sid": sid, "root": root.id, "coffee": coffee.id, "tea": tea.id,
               "node_ids": [root.id, coffee.id, tea.id],
               "skus": [sku_coffee, sku_tea]}
        yield ids
    finally:
        db.rollback()
        # Onder parallelle DB-belasting (validatieruns) kan de standaard
        # statement-timeout (4s) de teardown-deletes annuleren; verruim die
        # net als in bulk_seed.
        from sqlalchemy import text as _text
        db.execute(_text("SET statement_timeout = '120s'"))
        sid = ids.get("sid")
        if sid is not None:
            for M, col in [
                (models.CompetitorRanking, models.CompetitorRanking.shop_id),
                (models.CompetitorProfile, models.CompetitorProfile.shop_id),
                (models.CategoryCompetitorRelevance, models.CategoryCompetitorRelevance.shop_id),
                (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.shop_id),
            ]:
                db.query(M).filter(col == sid).delete(synchronize_session=False)
            A = models.ProductHierarchyAssignment
            db.query(A).filter(A.sku_id.in_(ids["skus"])).delete(synchronize_session=False)
            N = models.ProductHierarchyNode
            for nid in (ids["coffee"], ids["tea"], ids["root"]):
                db.query(N).filter(N.id == nid).delete(synchronize_session=False)
            # Request-middleware schrijft cost-usage rijen per shop; eerst
            # opruimen of de shop-delete faalt op de FK (zie testconventies).
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(ids["skus"])).delete(synchronize_session=False)
            db.query(models.DimShop).filter(models.DimShop.id == sid).delete(
                synchronize_session=False)
            db.commit()
        db.close()


def test_rankings_zonder_filter_toont_alles(client, admin_headers, seed):
    r = client.get("/api/competition/rankings",
                   params={"shop_id": seed["sid"], "scope": "overall"},
                   headers=admin_headers)
    assert r.status_code == 200
    names = {x["competitor_name"] for x in r.json()["rankings"]}
    assert names == {COMP_COFFEE, COMP_TEA}


def test_rankings_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/rankings",
                   params={"shop_id": seed["sid"], "scope": "overall",
                           "hierarchy_node_ids": str(seed["coffee"])},
                   headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    names = {x["competitor_name"] for x in body["rankings"]}
    assert names == {COMP_COFFEE}
    assert body["total"] == 1


def test_rankings_parent_node_telt_descendants(client, admin_headers, seed):
    r = client.get("/api/competition/rankings",
                   params={"shop_id": seed["sid"], "scope": "overall",
                           "hierarchy_node_ids": str(seed["root"])},
                   headers=admin_headers)
    names = {x["competitor_name"] for x in r.json()["rankings"]}
    assert names == {COMP_COFFEE, COMP_TEA}


def test_rankings_history_gefilterd(client, admin_headers, seed):
    r = client.get("/api/competition/rankings/history",
                   params={"shop_id": seed["sid"], "scope": "overall",
                           "hierarchy_node_ids": str(seed["tea"])},
                   headers=admin_headers)
    assert r.status_code == 200
    hist = r.json()["history"]
    assert COMP_TEA in hist and COMP_COFFEE not in hist


def test_dashboard_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/competition/dashboard",
                   params={"shop_id": seed["sid"],
                           "hierarchy_node_ids": str(seed["coffee"])},
                   headers=admin_headers)
    assert r.status_code == 200
    cats = {c["category"] for c in r.json()["categories"]}
    assert CAT_COFFEE in cats and CAT_TEA not in cats


def test_dashboard_cross_categorie_rij_uitgesloten(client, admin_headers, seed):
    """Root-node filter (beide SKU's): de thee-categorierij van de
    koffieconcurrent mag niet meeliften op zijn koffie-waarneming."""
    r = client.get("/api/competition/dashboard",
                   params={"shop_id": seed["sid"],
                           "hierarchy_node_ids": str(seed["root"])},
                   headers=admin_headers)
    assert r.status_code == 200
    per_cat = {c["category"]: {x["competitor_name"] for x in c["competitors"]}
               for c in r.json()["categories"]}
    assert per_cat.get(CAT_COFFEE) == {COMP_COFFEE}
    assert per_cat.get(CAT_TEA) == {COMP_TEA}, (
        "Concurrent zonder waarneming op thee-SKU's hoort niet in de "
        "thee-categorie: " + str(per_cat)
    )


def test_competitors_gefilterd_op_merk(client, admin_headers, seed):
    r = client.get("/api/competition/competitors",
                   params={"shop_id": seed["sid"], "brands": f"{PFX}-Leaf"},
                   headers=admin_headers)
    assert r.status_code == 200
    names = {x["competitor_name"] for x in r.json()["items"]}
    assert names == {COMP_TEA}


@pytest.fixture(scope="module")
def bulk_seed(client):
    """Regressie voor parameterlimieten: één hiërarchie-node met méér SKU's
    dan de PostgreSQL-bindlimiet (65535). Server-side geseed via
    generate_series zodat de test snel blijft; de filterlogica moet als
    SQL-subquery werken en mag dus nooit een parameterlijst van deze omvang
    opbouwen."""
    from sqlalchemy import text
    N_SKUS = 70_000
    comp = f"{PFX}-bulk-comp.nl"
    db = SessionLocal()
    ids: dict = {}
    try:
        # Bulk-inserts kunnen onder belasting de standaard statement-timeout
        # overschrijden; verruim die voor deze sessie.
        db.execute(text("SET statement_timeout = '120s'"))
        shop = models.DimShop(shop_code=f"{PFX}-bulk", name=f"{PFX} Bulk", active=True)
        db.add(shop); db.flush()
        sid = shop.id
        node = models.ProductHierarchyNode(name=f"{PFX}-BulkNode", level=1,
                                           path_names=f"{PFX}-BulkNode")
        db.add(node); db.flush()
        node.path = f"/{node.id}/"
        db.flush()
        db.execute(text("""
            INSERT INTO dim_product (sku_id, product_name, brand, category, shop_id)
            SELECT :pfx || '-B-' || g, 'Bulkproduct ' || g, :brand, :cat, :sid
            FROM generate_series(1, :n) g
        """), {"pfx": PFX, "brand": f"{PFX}-BulkBrand", "cat": f"{PFX}-BulkCat",
               "sid": sid, "n": N_SKUS})
        db.execute(text("""
            INSERT INTO product_hierarchy_assignments (sku_id, node_id, status, is_primary)
            SELECT :pfx || '-B-' || g, :nid, 'active', true
            FROM generate_series(1, :n) g
        """), {"pfx": PFX, "nid": node.id, "n": N_SKUS})
        db.execute(text("""
            INSERT INTO fact_competitor_price_daily
                (date, sku_id, shop_id, competitor_name, price, source)
            SELECT CURRENT_DATE, :pfx || '-B-' || g, :sid, :comp, 9.99, 'manual'
            FROM generate_series(1, :n) g
        """), {"pfx": PFX, "sid": sid, "comp": comp, "n": N_SKUS})
        db.add(models.CompetitorRanking(
            shop_id=sid, run_date=date.today(), scope="overall",
            competitor_name=comp, rank=1, combined_score=1.0))
        db.add(models.CompetitorProfile(
            shop_id=sid, competitor_name=comp, domain=comp,
            relevance_label="HIGH"))
        db.add(models.CategoryCompetitorRelevance(
            shop_id=sid, competitor_name=comp, category=f"{PFX}-BulkCat",
            combined_score=50.0, relevance_label="HIGH", traffic_light="green"))
        db.commit()
        ids = {"sid": sid, "node": node.id, "comp": comp}
        yield ids
    finally:
        db.rollback()
        db.execute(text("SET statement_timeout = '120s'"))
        if ids.get("sid") is not None:
            sid = ids["sid"]
            for stmt, params in [
                ("DELETE FROM competitor_rankings WHERE shop_id = :sid", {"sid": sid}),
                ("DELETE FROM competitor_profile WHERE shop_id = :sid", {"sid": sid}),
                ("DELETE FROM category_competitor_relevance WHERE shop_id = :sid", {"sid": sid}),
                ("DELETE FROM fact_competitor_price_daily WHERE shop_id = :sid", {"sid": sid}),
                ("DELETE FROM product_hierarchy_assignments WHERE node_id = :nid", {"nid": ids["node"]}),
                ("DELETE FROM product_hierarchy_nodes WHERE id = :nid", {"nid": ids["node"]}),
                ("DELETE FROM dim_product WHERE sku_id LIKE :pfx", {"pfx": f"{PFX}-B-%"}),
                ("DELETE FROM cost_usage_records WHERE shop_id = :sid", {"sid": sid}),
                ("DELETE FROM dim_shop WHERE id = :sid", {"sid": sid}),
            ]:
                db.execute(text(stmt), params)
            db.commit()
        db.close()


def test_bulk_selectie_boven_parameterlimiet(client, admin_headers, bulk_seed):
    """70k gefilterde SKU's: alle vier endpoints moeten gewoon werken
    (subquery-pad, geen IN-parameterlijst)."""
    b = bulk_seed
    base = {"shop_id": b["sid"], "hierarchy_node_ids": str(b["node"])}
    r = client.get("/api/competition/rankings",
                   params={**base, "scope": "overall"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert {x["competitor_name"] for x in r.json()["rankings"]} == {b["comp"]}

    r = client.get("/api/competition/rankings/history",
                   params={**base, "scope": "overall"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert b["comp"] in r.json()["history"]

    r = client.get("/api/competition/dashboard", params=base, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert {c["category"] for c in r.json()["categories"]} == {f"{PFX}-BulkCat"}

    r = client.get("/api/competition/competitors", params=base, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert {x["competitor_name"] for x in r.json()["items"]} == {b["comp"]}

    r = client.get("/api/competition/summary", params=base, headers=admin_headers)
    assert r.status_code == 200, r.text


def test_lege_selectie_geeft_lege_lijst(client, admin_headers, seed):
    """Filter actief maar geen matchende SKU's → lege resultaten, geen fallback."""
    r = client.get("/api/competition/rankings",
                   params={"shop_id": seed["sid"], "scope": "overall",
                           "brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["rankings"] == []
