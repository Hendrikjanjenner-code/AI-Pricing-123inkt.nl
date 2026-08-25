"""
Regressietests cascaderende productfilters (taak #301) — testscenario's
44–52 uit de bouwopdracht, op API-niveau:

  44. Geen filter → alle producten (geen onverwachte categoriebeperking).
  45. Hoofdcategorie → subcategorieën zijn uitsluitend children; resultaten
      zijn uitsluitend descendants (geen data uit een andere hoofdcategorie).
  46. Drilldown 3 niveaus → niveau 4 en Product tonen alleen de subtree.
  47. Hoofdcategorie wisselen → children van de nieuwe tak (frontend reset
      wordt hier op API-contract getoetst: subcategorieën van de nieuwe tak).
  48. Ongeldige combinatie (subcategorie uit een andere hoofdtak) → 422,
      nooit gemengde data.
  49. Productselectie → exacte SKU-scope in de globale filterlaag ("sku:").
  50. Navigatie/persistentie: scope-parameters geven op dataroutes dezelfde
      subtree terug (resolve_sku_filter-consistentie).
  51. Nieuwe categorie in de boom → verschijnt direct in de dropdown-data.
  52. Nieuw product onder een tak → zichtbaar in Product-dropdown van die
      tak, onzichtbaar onder de andere tak.

Conventies: gedeelde Postgres-dev-DB — eigen uuid-prefix, eigen (sub)boom,
volledige teardown, nooit aannemen dat de DB leeg is.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from routes.global_filters import resolve_sku_filter

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"PFC{uuid.uuid4().hex[:6].upper()}"
SKU_COFFEE = f"{PFX}-COF"
SKU_TEA = f"{PFX}-TEA"
SKU_PEN = f"{PFX}-PEN"


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
def headers(client):
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _mknode(db, name, level, parent=None):
    n = models.ProductHierarchyNode(
        name=name, level=level,
        parent_id=parent.id if parent is not None else None,
        path_names=name if parent is None else f"{parent.path_names} > {name}")
    db.add(n)
    db.flush()
    n.path = f"/{n.id}/" if parent is None else f"{parent.path}{n.id}/"
    return n


@pytest.fixture(scope="module")
def tree(client):
    """Office_Food → Drinks → Coffee/Tea (met producten) en Office_Writing
    → Pens (met product): twee hoofdtakken zoals in de testscenario's."""
    db = SessionLocal()
    try:
        food = _mknode(db, f"{PFX}-Office_Food", 1)
        drinks = _mknode(db, f"{PFX}-Drinks", 2, food)
        coffee = _mknode(db, f"{PFX}-Coffee", 3, drinks)
        tea = _mknode(db, f"{PFX}-Tea", 3, drinks)
        beans = _mknode(db, f"{PFX}-Beans", 4, coffee)
        writing = _mknode(db, f"{PFX}-Office_Writing", 1)
        pens = _mknode(db, f"{PFX}-Pens", 2, writing)

        db.add_all([
            models.DimProduct(sku_id=SKU_COFFEE, product_name=f"{PFX} Koffiebonen donker",
                              lifecycle_status="active"),
            models.DimProduct(sku_id=SKU_TEA, product_name=f"{PFX} Groene thee",
                              lifecycle_status="active"),
            models.DimProduct(sku_id=SKU_PEN, product_name=f"{PFX} Balpen blauw",
                              lifecycle_status="active"),
        ])
        db.flush()
        db.add_all([
            models.ProductHierarchyAssignment(sku_id=SKU_COFFEE, node_id=beans.id, status="active"),
            models.ProductHierarchyAssignment(sku_id=SKU_TEA, node_id=tea.id, status="active"),
            models.ProductHierarchyAssignment(sku_id=SKU_PEN, node_id=pens.id, status="active"),
        ])
        db.commit()
        ids = {"food": food.id, "drinks": drinks.id, "coffee": coffee.id,
               "tea": tea.id, "beans": beans.id, "writing": writing.id,
               "pens": pens.id}
        yield ids
    finally:
        db.rollback()
        A, N, P = (models.ProductHierarchyAssignment,
                   models.ProductHierarchyNode, models.DimProduct)
        skus = [SKU_COFFEE, SKU_TEA, SKU_PEN]
        db.query(A).filter(A.sku_id.in_(skus)).delete(synchronize_session=False)
        db.query(N).filter(N.name.like(f"{PFX}-%")).delete(synchronize_session=False)
        db.query(P).filter(P.sku_id.in_(skus)).delete(synchronize_session=False)
        db.commit()
        db.close()


def _items(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


# ── 44. Geen filter → geen scope ────────────────────────────────────────────

def test_44_no_filter_means_no_scope(tree):
    db = SessionLocal()
    try:
        assert resolve_sku_filter(db) is None
    finally:
        db.close()


def test_44_products_without_chain_contains_all_branches(client, headers):
    items = _items(client.get(f"/api/product-filters/products?search={PFX}",
                              headers=headers))
    skus = {i["sku_id"] for i in items}
    assert {SKU_COFFEE, SKU_TEA, SKU_PEN} <= skus


# ── 45. Hoofdcategorie: alleen children + alleen descendants ────────────────

def test_45_subcategories_are_children_only(client, headers, tree):
    items = _items(client.get(
        f"/api/product-filters/subcategories?main_category_id={tree['food']}",
        headers=headers))
    ids = {i["id"] for i in items}
    assert tree["drinks"] in ids
    assert tree["pens"] not in ids and tree["writing"] not in ids


def test_45_scope_excludes_other_main_category(tree):
    db = SessionLocal()
    try:
        skus = resolve_sku_filter(db, hierarchy_node_ids=str(tree["food"]))
        assert {SKU_COFFEE, SKU_TEA} <= skus
        assert SKU_PEN not in skus
    finally:
        db.close()


def test_45_main_categories_endpoint_lists_top_nodes(client, headers, tree):
    items = _items(client.get("/api/product-filters/main-categories", headers=headers))
    ids = {i["id"] for i in items}
    assert tree["food"] in ids and tree["writing"] in ids
    assert tree["drinks"] not in ids


# ── 46. Drilldown: subtree op niveau 3/4 + Product ──────────────────────────

def test_46_drilldown_level4_and_products(client, headers, tree):
    lvl4 = _items(client.get(
        f"/api/product-filters/sub-sub-subcategories?sub_subcategory_id={tree['coffee']}",
        headers=headers))
    assert {i["id"] for i in lvl4} == {tree["beans"]}

    prods = _items(client.get(
        "/api/product-filters/products"
        f"?main_category_id={tree['food']}&subcategory_id={tree['drinks']}"
        f"&sub_subcategory_id={tree['coffee']}",
        headers=headers))
    skus = {p["sku_id"] for p in prods}
    assert skus == {SKU_COFFEE}          # thee en pen vallen buiten Coffee

    # Dezelfde scope in de gedeelde dataquery-laag (alle modules).
    db = SessionLocal()
    try:
        scoped = resolve_sku_filter(db, hierarchy_node_ids=str(tree["coffee"]))
        assert scoped == {SKU_COFFEE}
    finally:
        db.close()


def test_46_product_label_format(client, headers, tree):
    prods = _items(client.get(
        f"/api/product-filters/products?sub_subcategory_id={tree['coffee']}"
        f"&main_category_id={tree['food']}&subcategory_id={tree['drinks']}",
        headers=headers))
    assert prods[0]["label"].startswith(f"SKU {SKU_COFFEE} – ")


# ── 47. Hoofdcategorie wisselen → children van de nieuwe tak ────────────────

def test_47_switch_main_category(client, headers, tree):
    items = _items(client.get(
        f"/api/product-filters/subcategories?main_category_id={tree['writing']}",
        headers=headers))
    ids = {i["id"] for i in items}
    assert tree["pens"] in ids
    assert tree["drinks"] not in ids


# ── 48. Ongeldige combinaties → 422, nooit gemengde data ────────────────────

def test_48_invalid_chain_rejected(client, headers, tree):
    r = client.get(
        "/api/product-filters/products"
        f"?main_category_id={tree['food']}&subcategory_id={tree['pens']}",
        headers=headers)
    assert r.status_code == 422
    assert "hoort niet bij" in r.json()["detail"]

    r2 = client.post("/api/product-filters/resolve-scope", headers=headers,
                     json={"main_category_id": tree["food"],
                           "subcategory_id": tree["pens"]})
    assert r2.status_code == 422


def test_48_gap_in_chain_rejected(client, headers, tree):
    r = client.get(
        f"/api/product-filters/products?subcategory_id={tree['drinks']}",
        headers=headers)
    assert r.status_code == 422
    assert "bovenliggend" in r.json()["detail"]


def test_48_wrong_level_rejected(client, headers, tree):
    r = client.get(
        f"/api/product-filters/subcategories?main_category_id={tree['drinks']}",
        headers=headers)
    assert r.status_code == 422


# ── 49. Productselectie → exacte SKU-scope ──────────────────────────────────

def test_49_product_selection_exact_scope(tree):
    db = SessionLocal()
    try:
        scoped = resolve_sku_filter(db, sku_query=f"sku:{SKU_COFFEE}")
        assert scoped == {SKU_COFFEE}
        # Substring-variant zou breder kunnen matchen; "sku:" is exact.
        assert resolve_sku_filter(db, sku_query=f"sku:{PFX}") == set()
    finally:
        db.close()


def test_49_resolve_scope_derives_levels_from_product(client, headers, tree):
    r = client.post("/api/product-filters/resolve-scope", headers=headers,
                    json={"sku_id": SKU_COFFEE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert [l["id"] for l in body["levels"]] == [
        tree["food"], tree["drinks"], tree["coffee"], tree["beans"]]
    assert body["product"]["sku_id"] == SKU_COFFEE
    assert body["breadcrumb"].endswith(body["product"]["label"])


def test_49_resolve_scope_rejects_conflicting_chain(client, headers, tree):
    r = client.post("/api/product-filters/resolve-scope", headers=headers,
                    json={"sku_id": SKU_COFFEE,
                          "main_category_id": tree["writing"]})
    assert r.status_code == 422


def test_49_resolve_scope_unknown_sku(client, headers):
    r = client.post("/api/product-filters/resolve-scope", headers=headers,
                    json={"sku_id": f"{PFX}-BESTAAT-NIET"})
    assert r.status_code == 422


# ── 50. Persistentie: zelfde scope-parameters → zelfde subtree ──────────────

def test_50_scope_is_stable_across_calls(tree):
    db = SessionLocal()
    try:
        a = resolve_sku_filter(db, hierarchy_node_ids=str(tree["drinks"]))
        b = resolve_sku_filter(db, hierarchy_node_ids=str(tree["drinks"]))
        assert a == b == {SKU_COFFEE, SKU_TEA}
    finally:
        db.close()


# ── 51. Nieuwe categorie verschijnt direct in dropdown-data ─────────────────

def test_51_new_category_appears_without_code_change(client, headers, tree):
    db = SessionLocal()
    node_id = None
    try:
        parent = db.get(models.ProductHierarchyNode, tree["drinks"])
        juice = _mknode(db, f"{PFX}-Juice", 3, parent)
        db.commit()
        node_id = juice.id
        items = _items(client.get(
            f"/api/product-filters/sub-subcategories?subcategory_id={tree['drinks']}",
            headers=headers))
        assert node_id in {i["id"] for i in items}
    finally:
        if node_id is not None:
            db.query(models.ProductHierarchyNode).filter(
                models.ProductHierarchyNode.id == node_id
            ).delete(synchronize_session=False)
            db.commit()
        db.close()


# ── 52. Nieuw product zichtbaar onder eigen tak, niet onder de andere ───────

def test_52_new_product_scoped_to_its_branch(client, headers, tree):
    db = SessionLocal()
    sku = f"{PFX}-NIEUW"
    try:
        db.add(models.DimProduct(sku_id=sku, product_name=f"{PFX} Espresso cups",
                                 lifecycle_status="active"))
        db.flush()
        db.add(models.ProductHierarchyAssignment(
            sku_id=sku, node_id=tree["coffee"], status="active"))
        db.commit()

        under_coffee = _items(client.get(
            "/api/product-filters/products"
            f"?main_category_id={tree['food']}&subcategory_id={tree['drinks']}"
            f"&sub_subcategory_id={tree['coffee']}",
            headers=headers))
        assert sku in {p["sku_id"] for p in under_coffee}

        under_writing = _items(client.get(
            f"/api/product-filters/products?main_category_id={tree['writing']}",
            headers=headers))
        assert sku not in {p["sku_id"] for p in under_writing}
    finally:
        db.rollback()
        db.query(models.ProductHierarchyAssignment).filter(
            models.ProductHierarchyAssignment.sku_id == sku
        ).delete(synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == sku
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


# ── Shop-autorisatie: geen productdata van andere winkels ───────────────────

@pytest.fixture(scope="module")
def scoped_setup(client, headers, tree):
    """Twee shops + een gebruiker die alleen shop A mag zien; het bestaande
    koffieproduct hoort bij shop A, het theeproduct bij shop B."""
    db = SessionLocal()
    created = {"user_id": None, "shop_ids": []}
    try:
        shop_a = models.DimShop(shop_code=f"{PFX}-A", name=f"{PFX} Shop A", active=True)
        shop_b = models.DimShop(shop_code=f"{PFX}-B", name=f"{PFX} Shop B", active=True)
        db.add_all([shop_a, shop_b]); db.flush()
        created["shop_ids"] = [shop_a.id, shop_b.id]
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_COFFEE).update({"shop_id": shop_a.id})
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == SKU_TEA).update({"shop_id": shop_b.id})
        db.commit()

        uname = f"pfc_{uuid.uuid4().hex[:8]}"
        resp = client.post("/api/users", headers=headers, json={
            "username": uname, "email": f"{uname}@test.local",
            "password": "Wachtwoord123!", "role": "analyst", "full_name": uname})
        assert resp.status_code in (200, 201), resp.text
        uid = resp.json().get("id") or resp.json().get("user", {}).get("id")
        created["user_id"] = uid
        db.add(models.UserScope(user_id=uid, scope_type="shop",
                                scope_value=str(shop_a.id)))
        db.commit()
        login = client.post("/api/auth/login",
                            json={"username": uname, "password": "Wachtwoord123!"})
        assert login.status_code == 200, login.text
        h = {"Authorization": f"Bearer {login.json()['token']}"}
        yield {"headers": h, "shop_a": shop_a.id, "shop_b": shop_b.id}
    finally:
        db.rollback()
        if created["user_id"]:
            db.query(models.UserScope).filter(
                models.UserScope.user_id == created["user_id"]
            ).delete(synchronize_session=False)
            db.query(models.User).filter(
                models.User.id == created["user_id"]
            ).delete(synchronize_session=False)
        db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(
            [SKU_COFFEE, SKU_TEA])).update({"shop_id": None},
                                           synchronize_session=False)
        if created["shop_ids"]:
            db.query(models.DimShop).filter(
                models.DimShop.id.in_(created["shop_ids"])
            ).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_authz_product_search_hides_other_shop(client, scoped_setup):
    items = _items(client.get(f"/api/product-filters/products?search={PFX}",
                              headers=scoped_setup["headers"]))
    skus = {i["sku_id"] for i in items}
    assert SKU_COFFEE in skus       # eigen shop wél
    assert SKU_TEA not in skus      # andere shop niet


def test_authz_resolve_scope_rejects_other_shop_sku(client, scoped_setup):
    r = client.post("/api/product-filters/resolve-scope",
                    headers=scoped_setup["headers"], json={"sku_id": SKU_TEA})
    assert r.status_code == 422
    assert SKU_TEA in r.json()["detail"]  # gedraagt zich als onbestaand
    # productnaam mag nooit lekken
    assert "Groene thee" not in r.json()["detail"]

    ok = client.post("/api/product-filters/resolve-scope",
                     headers=scoped_setup["headers"], json={"sku_id": SKU_COFFEE})
    assert ok.status_code == 200


def test_authz_copilot_ignores_other_shop_sku(scoped_setup):
    """Copilot-contextpad: get_scoped_product weigert andermans SKU."""
    from services.product_scope import get_scoped_product
    db = SessionLocal()
    try:
        allowed = {scoped_setup["shop_a"]}
        assert get_scoped_product(db, SKU_TEA, allowed) is None
        own = get_scoped_product(db, SKU_COFFEE, allowed)
        assert own is not None and own.sku_id == SKU_COFFEE
        # onbeperkte gebruiker (None) ziet beide
        assert get_scoped_product(db, SKU_TEA, None) is not None
    finally:
        db.close()
