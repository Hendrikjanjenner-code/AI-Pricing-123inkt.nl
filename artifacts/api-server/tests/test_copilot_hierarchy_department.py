"""
Taak 220 — Copilot: hiërarchiebegrip en department-awareness.

Dekt:
- Hierarchy-resolver: categorienaam → centrale hierarchy-node-ids
  (exact, case-insensitief, substring, fuzzy) — geen tekstmatching.
- Semantic functions accepteren hierarchy-filters (incl. descendants) en
  rapporteren de gebruikte hiërarchie-context (hierarchy_scope).
- Department-permissies in de gateway: functie-allowlist per afdeling,
  adversariële tool-calls worden geweigerd; argument-injectie (shop_id,
  hierarchy_node_ids) wordt verworpen.
- Department-aware prioritering van get_active_signals.
- Global Filter Context als default scope voor tool-calls.
"""
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
import ai_gateway
import models
import semantic_layer
from database import SessionLocal

PFX = f"CHD{uuid.uuid4().hex[:6].upper()}"


@pytest.fixture(scope="module")
def client():
    """Lifespan-start zorgt voor authz-seeding (afdelingen) en DDL."""
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass


@pytest.fixture(scope="module")
def db(client):
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture(scope="module")
def data(db):
    """Eigen testshop met hiërarchie (Koffie > Espresso, los: Thee),
    producten, salesfeiten en signalen."""
    shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} shop")
    db.add(shop)
    db.flush()
    sid = shop.id

    skus = [f"{PFX}-KOF-1", f"{PFX}-ESP-1", f"{PFX}-THE-1"]
    db.add_all([
        models.DimProduct(sku_id=skus[0], product_name="Koffiebonen huis",
                          brand=f"{PFX}-Merk", category="Koffie", shop_id=sid),
        models.DimProduct(sku_id=skus[1], product_name="Espresso cups",
                          brand=f"{PFX}-Merk", category="Espresso", shop_id=sid),
        models.DimProduct(sku_id=skus[2], product_name="Groene thee",
                          brand=f"{PFX}-Merk", category="Thee", shop_id=sid),
    ])
    db.flush()

    N = models.ProductHierarchyNode
    koffie = N(name=f"{PFX}-Koffie", level=1, path_names=f"{PFX}-Koffie", is_active=True)
    db.add(koffie); db.flush()
    koffie.path = f"/{koffie.id}/"
    espresso = N(name=f"{PFX}-Espresso", level=2, parent_id=koffie.id,
                 path_names=f"{PFX}-Koffie > {PFX}-Espresso", is_active=True)
    db.add(espresso); db.flush()
    espresso.path = f"/{koffie.id}/{espresso.id}/"
    thee = N(name=f"{PFX}-Thee", level=1, path_names=f"{PFX}-Thee", is_active=True)
    db.add(thee); db.flush()
    thee.path = f"/{thee.id}/"

    db.add_all([
        models.ProductHierarchyAssignment(sku_id=skus[0], node_id=koffie.id, status="active"),
        models.ProductHierarchyAssignment(sku_id=skus[1], node_id=espresso.id, status="active"),
        models.ProductHierarchyAssignment(sku_id=skus[2], node_id=thee.id, status="active"),
    ])

    d = date.today() - timedelta(days=3)
    for sku, rev in ((skus[0], 100), (skus[1], 50), (skus[2], 200)):
        db.add(models.FactSalesDaily(date=d, sku_id=sku, shop_id=sid,
                                     units_sold=10, revenue=rev, cost=rev / 2,
                                     margin=rev / 2))

    db.add_all([
        models.IntelligenceSignal(
            shop_id=sid, engine="procurement_forecast", signal_type="supplier_price_risk",
            severity="high", entity_type="sku", entity_id=skus[0],
            explanation="test inkoopsignaal", status="active"),
        models.IntelligenceSignal(
            shop_id=sid, engine="pricing_engine", signal_type="price_position_drift",
            severity="high", entity_type="sku", entity_id=skus[1],
            explanation="test pricingsignaal", status="active"),
        models.IntelligenceSignal(
            shop_id=sid, engine="traffic", signal_type="conversion_drop",
            severity="high", entity_type="sku", entity_id=skus[2],
            explanation="test seo-signaal", status="active"),
        # Node-signaal op een DESCENDANT-categorie (Espresso): moet meetellen
        # wanneer de parent (Koffie) geselecteerd is.
        models.IntelligenceSignal(
            shop_id=sid, engine="assortment", signal_type="category_gap",
            severity="medium", entity_type="category",
            entity_id=f"{PFX}-cat-espresso", hierarchy_node_id=espresso.id,
            explanation="test categoriesignaal", status="active"),
    ])
    db.commit()

    yield {"shop_id": sid, "skus": skus, "koffie": koffie.id,
           "espresso": espresso.id, "thee": thee.id}

    db.rollback()
    A = models.ProductHierarchyAssignment
    db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == sid).delete(synchronize_session=False)
    db.query(models.FactSalesDaily).filter(
        models.FactSalesDaily.shop_id == sid).delete(synchronize_session=False)
    db.query(A).filter(A.sku_id.in_(skus)).delete(synchronize_session=False)
    for nid in (espresso.id, koffie.id, thee.id):
        db.query(N).filter(N.id == nid).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
    if hasattr(models, "CostUsageRecord"):
        # Request-middleware kan kostenrijen per shop schrijven; eerst opruimen
        # anders faalt de FK op dim_shop alleen in volledige suite-runs.
        db.query(models.CostUsageRecord).filter(
            models.CostUsageRecord.shop_id == sid).delete(synchronize_session=False)
    db.query(models.DimShop).filter(models.DimShop.id == sid).delete(
        synchronize_session=False)
    db.commit()


def _make_user(db, role: str, department_code: str | None = None) -> models.User:
    user = models.User(
        username=f"{PFX}_{role}_{uuid.uuid4().hex[:6]}",
        email=f"{PFX}_{uuid.uuid4().hex[:8]}@test.local",
        full_name="Copilot testgebruiker", hashed_password="x", role=role)
    db.add(user)
    db.flush()
    if department_code:
        dept = db.query(models.Department).filter(
            models.Department.code == department_code).first()
        assert dept is not None, f"afdeling {department_code} niet geseed"
        db.add(models.UserDepartment(user_id=user.id, department_id=dept.id,
                                     is_primary=True))
    db.commit()
    return user


@pytest.fixture(scope="module")
def users(db, data):
    made = {
        "admin": _make_user(db, "admin", "admin"),
        "seo_viewer": _make_user(db, "viewer", "seo"),
        "pricing": _make_user(db, "pricing_manager", "pricing"),
        "inkoop": _make_user(db, "viewer", "inkoop"),
    }
    yield made
    ids = [u.id for u in made.values()]
    db.rollback()
    db.query(models.UserDepartment).filter(
        models.UserDepartment.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(models.UserPermission).filter(
        models.UserPermission.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.id.in_(ids)).delete(
        synchronize_session=False)
    db.commit()


# ── 1. Hierarchy-resolver ───────────────────────────────────────────────────

def test_resolver_exacte_naam(db, data):
    r = ai_gateway.resolve_hierarchy_name(db, f"{PFX}-Koffie")
    assert r is not None and r["match_type"] == "exact"
    assert r["node_ids"] == [data["koffie"]]


def test_resolver_case_insensitief(db, data):
    r = ai_gateway.resolve_hierarchy_name(db, f"{PFX}-koffie".lower())
    assert r is not None and data["koffie"] in r["node_ids"]


def test_resolver_substring(db, data):
    r = ai_gateway.resolve_hierarchy_name(db, f"{PFX}-Espres")
    assert r is not None and data["espresso"] in r["node_ids"]


def test_resolver_fuzzy_typefout(db, data):
    # 'Kofie' i.p.v. 'Koffie' — fuzzy matching, geen substring.
    r = ai_gateway.resolve_hierarchy_name(db, f"{PFX}-Kofie")
    assert r is not None, "fuzzy match verwacht voor typefout"
    assert data["koffie"] in r["node_ids"]


def test_resolver_geen_match(db, data):
    assert ai_gateway.resolve_hierarchy_name(db, "VolstrektOnbekendeCategorieXYZ") is None


def test_resolver_snoeit_descendants(db, data):
    # Substring matcht parent én child; alleen de parent blijft over.
    r = ai_gateway.resolve_hierarchy_name(db, PFX)
    assert r is not None
    assert data["koffie"] in r["node_ids"]
    assert data["espresso"] not in r["node_ids"]


# ── 2. Semantic functions met hierarchy-scope ──────────────────────────────

def test_category_performance_hierarchy_scope(db, data, users):
    out = semantic_layer.get_category_performance(
        db, users["admin"], shop_id=data["shop_id"],
        hierarchy_node_ids=[data["koffie"]])
    cats = {c["category"] for c in out["categories"]}
    assert cats == {"Koffie", "Espresso"}  # descendants tellen mee
    assert out["hierarchy_scope"] is not None
    assert data["koffie"] in out["hierarchy_scope"]["node_ids"]
    total = sum(c["revenue"] for c in out["categories"])
    assert total == pytest.approx(150.0)


def test_category_performance_zonder_scope(db, data, users):
    out = semantic_layer.get_category_performance(
        db, users["admin"], shop_id=data["shop_id"])
    assert out["hierarchy_scope"] is None
    cats = {c["category"] for c in out["categories"]}
    assert {"Koffie", "Espresso", "Thee"} <= cats


def test_active_signals_hierarchy_scope(db, data, users):
    out = semantic_layer.get_active_signals(
        db, users["admin"], shop_id=data["shop_id"],
        hierarchy_node_ids=[data["koffie"]])
    entiteiten = {s["entity_id"] for s in out["signals"]}
    # SKU-signalen binnen de scope én het categoriesignaal op de
    # descendant-node (Espresso) tellen mee onder parent Koffie.
    assert entiteiten == {data["skus"][0], data["skus"][1],
                          f"{PFX}-cat-espresso"}
    assert out["hierarchy_scope"]["includes_descendants"] is True
    assert data["espresso"] in out["hierarchy_scope"]["descendant_node_ids"]


def test_active_signals_node_signaal_buiten_scope(db, data, users):
    # Onder Thee valt het Espresso-categoriesignaal juist NIET.
    out = semantic_layer.get_active_signals(
        db, users["admin"], shop_id=data["shop_id"],
        hierarchy_node_ids=[data["thee"]])
    entiteiten = {s["entity_id"] for s in out["signals"]}
    assert entiteiten == {data["skus"][2]}


# ── 3. Department-permissies in de gateway ─────────────────────────────────

def test_allowlist_seo_gebruiker(db, users):
    allowed = ai_gateway.allowed_function_names(db, users["seo_viewer"])
    assert "get_traffic_summary" in allowed          # seo.view
    assert "get_promotion_effectiveness" in allowed  # promotions.view
    assert "get_supplier_risk" not in allowed        # geen supplier.view
    assert "get_margin_erosion" not in allowed       # geen pricing.view


def test_allowlist_admin_alles(db, users):
    assert ai_gateway.allowed_function_names(db, users["admin"]) == set(
        ai_gateway.SEMANTIC_FUNCTIONS)


def test_build_tools_gefilterd(db, users):
    allowed = ai_gateway.allowed_function_names(db, users["seo_viewer"])
    names = {t["function"]["name"] for t in ai_gateway.build_tools(allowed)}
    assert names == allowed
    assert "get_supplier_risk" not in names


def test_adversariele_toolcall_geweigerd(db, data, users):
    """SEO-gebruiker vraagt (via het model) toch supplier-contractdata op."""
    allowed = ai_gateway.allowed_function_names(db, users["seo_viewer"])
    result, meta = ai_gateway._execute_tool(
        db, users["seo_viewer"], "get_supplier_risk", {"limit": 5},
        shop_id=data["shop_id"], allowed_functions=allowed)
    assert result.get("data_available") is False
    assert "Geen toegang" in result.get("error", "")
    assert meta.get("denied") == "department_permission"
    assert "items" not in result


def test_argument_injectie_wordt_verworpen(db, data, users):
    """Model-geïnjecteerde shop_id/hierarchy_node_ids worden gedropt."""
    allowed = ai_gateway.allowed_function_names(db, users["admin"])
    result, meta = ai_gateway._execute_tool(
        db, users["admin"], "get_active_signals",
        {"shop_id": 999999, "hierarchy_node_ids": [data["thee"]], "limit": 10},
        shop_id=data["shop_id"], allowed_functions=allowed)
    assert set(meta.get("dropped_arguments", [])) == {"shop_id", "hierarchy_node_ids"}
    assert result.get("shop_id") == data["shop_id"]
    assert result.get("hierarchy_scope") is None


# ── 4. Hierarchy-scope via tool-call en Global Filter Context ──────────────

def test_toolcall_hierarchy_naam_resolved(db, data, users):
    allowed = ai_gateway.allowed_function_names(db, users["admin"])
    result, meta = ai_gateway._execute_tool(
        db, users["admin"], "get_active_signals",
        {"hierarchy": f"{PFX}-Koffie"},
        shop_id=data["shop_id"], allowed_functions=allowed)
    assert meta["hierarchy"]["resolved"] is True
    assert meta["hierarchy"]["source"] == "vraag"
    entiteiten = {s["entity_id"] for s in result["signals"]}
    assert entiteiten == {data["skus"][0], data["skus"][1],
                          f"{PFX}-cat-espresso"}


def test_toolcall_onbekende_hierarchy_geeft_fout(db, data, users):
    allowed = ai_gateway.allowed_function_names(db, users["admin"])
    result, meta = ai_gateway._execute_tool(
        db, users["admin"], "get_active_signals",
        {"hierarchy": "BestaatEchtNietXYZ123"},
        shop_id=data["shop_id"], allowed_functions=allowed)
    assert result.get("data_available") is False
    assert meta["hierarchy"]["resolved"] is False


def test_global_filter_context_als_default_scope(db, data, users):
    """Zonder hierarchy-argument geldt de Global Filter Context als default."""
    allowed = ai_gateway.allowed_function_names(db, users["admin"])
    result, meta = ai_gateway._execute_tool(
        db, users["admin"], "get_active_signals", {},
        shop_id=data["shop_id"], allowed_functions=allowed,
        default_hierarchy_node_ids=[data["thee"]])
    assert meta["hierarchy"]["source"] == "global_filter"
    entiteiten = {s["entity_id"] for s in result["signals"]}
    assert entiteiten == {data["skus"][2]}
    assert result["hierarchy_scope"] is not None


def test_expliciete_naam_wint_van_context(db, data, users):
    allowed = ai_gateway.allowed_function_names(db, users["admin"])
    result, meta = ai_gateway._execute_tool(
        db, users["admin"], "get_active_signals",
        {"hierarchy": f"{PFX}-Thee"},
        shop_id=data["shop_id"], allowed_functions=allowed,
        default_hierarchy_node_ids=[data["koffie"]])
    assert meta["hierarchy"]["source"] == "vraag"
    entiteiten = {s["entity_id"] for s in result["signals"]}
    assert entiteiten == {data["skus"][2]}


# ── 5. Department-aware prioritering ────────────────────────────────────────

def test_signalen_prioriteit_per_afdeling(db, data, users):
    inkoop = semantic_layer.get_active_signals(
        db, users["admin"], shop_id=data["shop_id"], department="inkoop")
    assert inkoop["department_priority_applied"] == "inkoop"
    assert inkoop["signals"][0]["engine"] == "procurement_forecast"

    pricing = semantic_layer.get_active_signals(
        db, users["admin"], shop_id=data["shop_id"], department="pricing")
    assert pricing["signals"][0]["engine"] == "pricing_engine"

    seo = semantic_layer.get_active_signals(
        db, users["admin"], shop_id=data["shop_id"], department="seo")
    assert seo["signals"][0]["engine"] == "traffic"


def test_geen_afdeling_geen_herordening(db, data, users):
    out = semantic_layer.get_active_signals(
        db, users["admin"], shop_id=data["shop_id"])
    assert out["department_priority_applied"] is None


def test_department_injectie_in_toolcall(db, data, users):
    """De gateway injecteert de primaire afdeling server-side."""
    dept = ai_gateway.primary_department_code(db, users["inkoop"])
    assert dept == "inkoop"
    allowed = ai_gateway.allowed_function_names(db, users["inkoop"])
    result, _meta = ai_gateway._execute_tool(
        db, users["inkoop"], "get_active_signals", {},
        shop_id=data["shop_id"], allowed_functions=allowed, department=dept)
    assert result["department_priority_applied"] == "inkoop"
    assert result["signals"][0]["engine"] == "procurement_forecast"
