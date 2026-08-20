"""
Tests voor de globale filtercontext (hierarchy_node_ids + brands) op de
product-scoped endpoints uit taak #263-vervolg:

  - /api/ab-tests
  - /api/bcg-transities  en  /api/bcg-transities/alerts
  - /api/kostprijswijziging, /api/ppfs, /api/break-even,
    /api/marketing-vs-korting, /api/margebescherming
  - /api/monitoring/alerts
  - /api/kosten/marketing, /api/kosten/operationeel
  - /api/substitutions
  - /api/pim/overview, /api/pim/completeness, /api/pim/suggestions

Conventies (gedeelde Postgres-dev-DB!): eigen DimProduct-rijen met unieke
uuid-prefix, eigen hiërarchie (status='active', node.path als '/<id>/'),
volledige teardown, nooit aannemen dat de DB leeg is. Per endpoint testen we:
  (a) subtree-match geeft alléén de data van matchende producten terug,
  (b) een hierarchy_node_ids-waarde die niets matcht → leeg (filter actief),
  (c) zonder params → ongefilterd (beide producten zichtbaar).
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

PFX = f"PSF{uuid.uuid4().hex[:6].upper()}"
SKU_A = f"{PFX}-SKU-A"      # brand A, coffee-tak
SKU_B = f"{PFX}-SKU-B"      # brand B, tea-tak
BRAND_A = f"{PFX}-BrandA"
BRAND_B = f"{PFX}-BrandB"
CAT_A = f"{PFX}-CatA"
CAT_B = f"{PFX}-CatB"
NOMATCH = "-999999999"     # bestaat vrijwel zeker niet als node-id


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
    """Eigen shop met twee takken (A/B), elk één product + eigen fact-rijen."""
    db = SessionLocal()
    today = date.today()
    ids: dict = {}
    ab_test_id = None
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id

        db.add_all([
            models.DimProduct(sku_id=SKU_A, product_name="Product A", brand=BRAND_A,
                              category=CAT_A, shop_id=sid,
                              current_price=10.0, cost_price=6.0),
            models.DimProduct(sku_id=SKU_B, product_name="Product B", brand=BRAND_B,
                              category=CAT_B, shop_id=sid,
                              current_price=8.0, cost_price=5.0),
        ])
        db.flush()

        # Hiërarchie: root → node_a / node_b
        root = models.ProductHierarchyNode(name=f"{PFX}-Root", level=1,
                                           path_names=f"{PFX}-Root")
        db.add(root); db.flush()
        root.path = f"/{root.id}/"
        node_a = models.ProductHierarchyNode(
            name=f"{PFX}-NodeA", level=2, parent_id=root.id,
            path_names=f"{PFX}-Root > {PFX}-NodeA")
        node_b = models.ProductHierarchyNode(
            name=f"{PFX}-NodeB", level=2, parent_id=root.id,
            path_names=f"{PFX}-Root > {PFX}-NodeB")
        db.add_all([node_a, node_b]); db.flush()
        node_a.path = f"/{root.id}/{node_a.id}/"
        node_b.path = f"/{root.id}/{node_b.id}/"
        db.add_all([
            models.ProductHierarchyAssignment(sku_id=SKU_A, node_id=node_a.id, status="active"),
            models.ProductHierarchyAssignment(sku_id=SKU_B, node_id=node_b.id, status="active"),
        ])
        db.flush()

        # ── A/B test met resultaten per SKU ──────────────────────────────
        ab = models.AbTest(name=f"{PFX}-test", start_date=today, status="active")
        db.add(ab); db.flush()
        ab_test_id = ab.id
        db.add_all([
            models.AbTestResult(test_id=ab.id, sku_id=SKU_A, group_type="AI",
                                current_margin=5, baseline_margin=4),
            models.AbTestResult(test_id=ab.id, sku_id=SKU_B, group_type="AI",
                                current_margin=5, baseline_margin=4),
        ])

        # ── BCG transities (SKU-entiteiten) ──────────────────────────────
        db.add_all([
            models.FactBcgTransition(
                date=today, entity_type="SKU", entity_id=SKU_A,
                entity_name="Product A", category=CAT_A,
                from_classification="QUESTION_MARK", to_classification="STAR",
                revenue_impact_eur=100),
            models.FactBcgTransition(
                date=today, entity_type="SKU", entity_id=SKU_B,
                entity_name="Product B", category=CAT_B,
                from_classification="CASH_COW", to_classification="DOG",
                revenue_impact_eur=-50),
        ])

        # ── Cost-change / break-even / ppfs / meds ───────────────────────
        db.add_all([
            models.FactCostChangeDaily(date=today, sku_id=SKU_A, sku_name="Product A",
                                       category=CAT_A, ppfs_score=0.5, mps_score=0.6,
                                       net_margin=20, severity="LAAG"),
            models.FactCostChangeDaily(date=today, sku_id=SKU_B, sku_name="Product B",
                                       category=CAT_B, ppfs_score=0.4, mps_score=0.5,
                                       net_margin=15, severity="HOOG"),
        ])
        db.add_all([
            models.FactBreakEvenAnalysisDaily(date=today, sku_id=SKU_A, sku_name="Product A",
                                              category=CAT_A, scenario_type="PRICE_REDUCTION",
                                              break_even_difficulty_score=0.3, beds_label="HAALBAAR"),
            models.FactBreakEvenAnalysisDaily(date=today, sku_id=SKU_B, sku_name="Product B",
                                              category=CAT_B, scenario_type="PRICE_REDUCTION",
                                              break_even_difficulty_score=0.8, beds_label="ONMOGELIJK"),
        ])
        db.add_all([
            models.FactPricePassThroughDaily(date=today, sku_id=SKU_A, sku_name="Product A",
                                             category=CAT_A, ppfs_score=0.7, ppfs_label="STERK"),
            models.FactPricePassThroughDaily(date=today, sku_id=SKU_B, sku_name="Product B",
                                             category=CAT_B, ppfs_score=0.2, ppfs_label="RISICOVOL"),
        ])
        db.add_all([
            models.FactMarketingVsDiscountDaily(date=today, sku_id=SKU_A, sku_name="Product A",
                                                category=CAT_A, scenario_type="PRICE_REDUCTION",
                                                meds_score=0.6, recommended_strategy="REDUCE_PRICE"),
            models.FactMarketingVsDiscountDaily(date=today, sku_id=SKU_B, sku_name="Product B",
                                                category=CAT_B, scenario_type="PRICE_REDUCTION",
                                                meds_score=0.7, recommended_strategy="PUSH_SEO"),
        ])

        # ── Kosten: marketing + operationeel ─────────────────────────────
        db.add_all([
            models.FactMarketingCostDaily(date=today, sku_id=SKU_A, sku_name="Product A",
                                          category=CAT_A, roas=3.0, cac=5.0,
                                          total_marketing_cost=100),
            models.FactMarketingCostDaily(date=today, sku_id=SKU_B, sku_name="Product B",
                                          category=CAT_B, roas=2.0, cac=6.0,
                                          total_marketing_cost=80),
        ])
        db.add_all([
            models.FactOperationalComplexityDaily(date=today, sku_id=SKU_A, sku_name="Product A",
                                                  category=CAT_A,
                                                  operational_complexity_score=0.3, ocs_label="LAAG"),
            models.FactOperationalComplexityDaily(date=today, sku_id=SKU_B, sku_name="Product B",
                                                  category=CAT_B,
                                                  operational_complexity_score=0.9, ocs_label="KRITIEK"),
        ])

        # ── Monitoring alerts (own_sku_id) ───────────────────────────────
        db.add_all([
            models.FactMonitoringAlert(date=today, own_sku_id=SKU_A,
                                       alert_type="PRICE_DROP", severity="HOOG",
                                       message="A", resolved=False),
            models.FactMonitoringAlert(date=today, own_sku_id=SKU_B,
                                       alert_type="OUT_OF_STOCK", severity="LAAG",
                                       message="B", resolved=False),
        ])

        # ── Substituties (primaire SKU = a_brand_sku) ────────────────────
        db.add_all([
            models.MapSubstitution(a_brand_sku=SKU_A, private_label_sku=SKU_B),
            models.MapSubstitution(a_brand_sku=SKU_B, private_label_sku=SKU_A),
        ])

        # ── PIM: completeness-scores + AI-suggesties ─────────────────────
        db.add_all([
            models.PimCompletenessScore(sku_id=SKU_A, channel_code=None,
                                        completeness_pct=80.0, quality_score=90.0,
                                        run_date=today),
            models.PimCompletenessScore(sku_id=SKU_B, channel_code=None,
                                        completeness_pct=40.0, quality_score=50.0,
                                        run_date=today),
        ])
        db.add_all([
            models.PimAiSuggestion(sku_id=SKU_A, attribute_code="kleur",
                                   suggested_value="rood", status="PENDING"),
            models.PimAiSuggestion(sku_id=SKU_B, attribute_code="kleur",
                                   suggested_value="blauw", status="PENDING"),
        ])

        db.commit()
        ids = {"sid": sid, "root": root.id, "node_a": node_a.id, "node_b": node_b.id,
               "ab_test_id": ab_test_id, "skus": [SKU_A, SKU_B]}
        yield ids
    finally:
        db.rollback()
        sid = ids.get("sid")
        skus = ids.get("skus", [SKU_A, SKU_B])
        # AB-test resultaten + test
        if ab_test_id is not None:
            db.query(models.AbTestResult).filter(
                models.AbTestResult.test_id == ab_test_id).delete(synchronize_session=False)
            db.query(models.AbTest).filter(
                models.AbTest.id == ab_test_id).delete(synchronize_session=False)
        for M, col in [
            (models.FactBcgTransition, models.FactBcgTransition.entity_id),
            (models.FactCostChangeDaily, models.FactCostChangeDaily.sku_id),
            (models.FactBreakEvenAnalysisDaily, models.FactBreakEvenAnalysisDaily.sku_id),
            (models.FactPricePassThroughDaily, models.FactPricePassThroughDaily.sku_id),
            (models.FactMarketingVsDiscountDaily, models.FactMarketingVsDiscountDaily.sku_id),
            (models.FactMarketingCostDaily, models.FactMarketingCostDaily.sku_id),
            (models.FactOperationalComplexityDaily, models.FactOperationalComplexityDaily.sku_id),
            (models.FactMonitoringAlert, models.FactMonitoringAlert.own_sku_id),
            (models.PimCompletenessScore, models.PimCompletenessScore.sku_id),
            (models.PimAiSuggestion, models.PimAiSuggestion.sku_id),
        ]:
            db.query(M).filter(col.in_(skus)).delete(synchronize_session=False)
        db.query(models.MapSubstitution).filter(
            models.MapSubstitution.a_brand_sku.in_(skus)).delete(synchronize_session=False)
        A = models.ProductHierarchyAssignment
        db.query(A).filter(A.sku_id.in_(skus)).delete(synchronize_session=False)
        N = models.ProductHierarchyNode
        for key in ("node_a", "node_b", "root"):
            nid = ids.get(key)
            if nid is not None:
                db.query(N).filter(N.id == nid).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
        if sid is not None:
            db.query(models.DimShop).filter(
                models.DimShop.id == sid).delete(synchronize_session=False)
        db.commit()
        db.close()


# ── A/B tests ────────────────────────────────────────────────────────────────

def test_ab_tests_ongefilterd_bevat_test(client, admin_headers, seed):
    r = client.get("/api/ab-tests", headers=admin_headers)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert seed["ab_test_id"] in ids


def test_ab_tests_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/ab-tests",
                   params={"hierarchy_node_ids": str(seed["node_a"])},
                   headers=admin_headers)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    # SKU_A zit in node_a → test heeft een matchend resultaat → zichtbaar.
    assert seed["ab_test_id"] in ids


def test_ab_test_detail_gefilterd_op_subnode(client, admin_headers, seed):
    """Eén A/B-test met SKU's in twee hiërarchie-takken: het detail-endpoint
    moet met een subtree-filter alleen de resultaten van die tak meetellen."""
    tid = seed["ab_test_id"]
    r = client.get(f"/api/ab-tests/{tid}", headers=admin_headers)
    assert r.status_code == 200
    ongefilterd = r.json()
    alle_skus = {s["sku_id"] for s in ongefilterd["sku_results"]}
    assert {SKU_A, SKU_B} <= alle_skus

    r = client.get(f"/api/ab-tests/{tid}",
                   params={"hierarchy_node_ids": str(seed["node_a"])},
                   headers=admin_headers)
    assert r.status_code == 200
    d = r.json()
    # Alleen de node_a-tak (SKU_A) telt mee — de andere tak is uitgesloten.
    skus = {s["sku_id"] for s in d["sku_results"]}
    assert SKU_A in skus and SKU_B not in skus
    assert d["summary"]["ai_sku_count"] == 1
    cats = {c["category"] for c in d["category_breakdown"]}
    assert CAT_B not in cats


def test_ab_test_detail_leeg_filter(client, admin_headers, seed):
    """Lege selectie = nul resultaten, niet 'geen filter'."""
    tid = seed["ab_test_id"]
    r = client.get(f"/api/ab-tests/{tid}",
                   params={"brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["summary"]["ai_sku_count"] == 0
    assert d["sku_results"] == []
    assert d["category_breakdown"] == []


def test_ab_tests_leeg_filter(client, admin_headers, seed):
    r = client.get("/api/ab-tests",
                   params={"brands": f"{PFX}-BestaatNiet"},
                   headers=admin_headers)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert seed["ab_test_id"] not in ids


# ── BCG transities ───────────────────────────────────────────────────────────

def _bcg_ids(body):
    return {t["entiteit_id"] for t in body["transities"]}


def test_bcg_ongefilterd(client, admin_headers, seed):
    r = client.get("/api/bcg-transities", headers=admin_headers)
    assert r.status_code == 200
    ids = _bcg_ids(r.json())
    assert SKU_A in ids and SKU_B in ids


def test_bcg_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/bcg-transities",
                   params={"hierarchy_node_ids": str(seed["node_a"])},
                   headers=admin_headers)
    assert r.status_code == 200
    ids = _bcg_ids(r.json())
    assert SKU_A in ids and SKU_B not in ids


def test_bcg_leeg_filter(client, admin_headers, seed):
    r = client.get("/api/bcg-transities",
                   params={"hierarchy_node_ids": NOMATCH},
                   headers=admin_headers)
    assert r.status_code == 200
    ids = _bcg_ids(r.json())
    assert SKU_A not in ids and SKU_B not in ids


def test_bcg_alerts_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/bcg-transities/alerts",
                   params={"hierarchy_node_ids": str(seed["node_b"])},
                   headers=admin_headers)
    assert r.status_code == 200
    ents = {a["entiteit"] for a in r.json()["alerts"]}
    # entity_name = "Product B" voor SKU_B
    assert "Product B" in ents and "Product A" not in ents


def test_bcg_alerts_leeg_filter(client, admin_headers, seed):
    r = client.get("/api/bcg-transities/alerts",
                   params={"hierarchy_node_ids": NOMATCH},
                   headers=admin_headers)
    assert r.status_code == 200
    ents = {a["entiteit"] for a in r.json()["alerts"]}
    assert "Product A" not in ents and "Product B" not in ents


# ── Break-even familie ───────────────────────────────────────────────────────

BREAK_EVEN_ENDPOINTS = [
    "/api/kostprijswijziging",
    "/api/ppfs",
    "/api/break-even",
    "/api/marketing-vs-korting",
    "/api/margebescherming",
]


@pytest.mark.parametrize("path", BREAK_EVEN_ENDPOINTS)
def test_break_even_ongefilterd(client, admin_headers, seed, path):
    r = client.get(path, headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {s["sku_id"] for s in r.json()["skus"]}
    assert SKU_A in skus and SKU_B in skus


@pytest.mark.parametrize("path", BREAK_EVEN_ENDPOINTS)
def test_break_even_gefilterd_op_subnode(client, admin_headers, seed, path):
    r = client.get(path, params={"hierarchy_node_ids": str(seed["node_a"])},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {s["sku_id"] for s in r.json()["skus"]}
    assert SKU_A in skus and SKU_B not in skus


@pytest.mark.parametrize("path", BREAK_EVEN_ENDPOINTS)
def test_break_even_leeg_filter(client, admin_headers, seed, path):
    r = client.get(path, params={"hierarchy_node_ids": NOMATCH}, headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {s["sku_id"] for s in r.json()["skus"]}
    assert SKU_A not in skus and SKU_B not in skus


@pytest.mark.parametrize("path", BREAK_EVEN_ENDPOINTS)
def test_break_even_gefilterd_op_merk(client, admin_headers, seed, path):
    r = client.get(path, params={"brands": BRAND_B}, headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {s["sku_id"] for s in r.json()["skus"]}
    assert SKU_B in skus and SKU_A not in skus


# ── Monitoring alerts ────────────────────────────────────────────────────────

def test_monitoring_ongefilterd(client, admin_headers, seed):
    r = client.get("/api/monitoring/alerts", headers=admin_headers)
    assert r.status_code == 200
    skus = {a["own_sku_id"] for a in r.json()["alerts"]}
    assert SKU_A in skus and SKU_B in skus


def test_monitoring_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/monitoring/alerts",
                   params={"hierarchy_node_ids": str(seed["node_a"])},
                   headers=admin_headers)
    assert r.status_code == 200
    skus = {a["own_sku_id"] for a in r.json()["alerts"]}
    assert SKU_A in skus and SKU_B not in skus


def test_monitoring_leeg_filter(client, admin_headers, seed):
    r = client.get("/api/monitoring/alerts",
                   params={"hierarchy_node_ids": NOMATCH},
                   headers=admin_headers)
    assert r.status_code == 200
    skus = {a["own_sku_id"] for a in r.json()["alerts"]}
    assert SKU_A not in skus and SKU_B not in skus


# ── Kosten: marketing + operationeel ─────────────────────────────────────────

COST_ENDPOINTS = ["/api/kosten/marketing", "/api/kosten/operationeel"]


@pytest.mark.parametrize("path", COST_ENDPOINTS)
def test_kosten_ongefilterd(client, admin_headers, seed, path):
    r = client.get(path, headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {s["sku_id"] for s in r.json()["skus"]}
    assert SKU_A in skus and SKU_B in skus


@pytest.mark.parametrize("path", COST_ENDPOINTS)
def test_kosten_gefilterd_op_subnode(client, admin_headers, seed, path):
    r = client.get(path, params={"hierarchy_node_ids": str(seed["node_b"])},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {s["sku_id"] for s in r.json()["skus"]}
    assert SKU_B in skus and SKU_A not in skus


@pytest.mark.parametrize("path", COST_ENDPOINTS)
def test_kosten_leeg_filter(client, admin_headers, seed, path):
    r = client.get(path, params={"hierarchy_node_ids": NOMATCH}, headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {s["sku_id"] for s in r.json()["skus"]}
    assert SKU_A not in skus and SKU_B not in skus


# ── Substituties ─────────────────────────────────────────────────────────────

def test_substituties_ongefilterd(client, admin_headers, seed):
    r = client.get("/api/substitutions", headers=admin_headers)
    assert r.status_code == 200
    primaries = {p["a_brand_sku"] for p in r.json()}
    assert SKU_A in primaries and SKU_B in primaries


def test_substituties_gefilterd_op_primaire_sku(client, admin_headers, seed):
    # node_a bevat SKU_A → alleen het paar met a_brand_sku == SKU_A blijft.
    r = client.get("/api/substitutions",
                   params={"hierarchy_node_ids": str(seed["node_a"])},
                   headers=admin_headers)
    assert r.status_code == 200
    primaries = {p["a_brand_sku"] for p in r.json()}
    assert primaries == {SKU_A} or (SKU_A in primaries and SKU_B not in primaries)


def test_substituties_leeg_filter(client, admin_headers, seed):
    r = client.get("/api/substitutions",
                   params={"hierarchy_node_ids": NOMATCH},
                   headers=admin_headers)
    assert r.status_code == 200
    primaries = {p["a_brand_sku"] for p in r.json()}
    assert SKU_A not in primaries and SKU_B not in primaries


# ── PIM ──────────────────────────────────────────────────────────────────────

def test_pim_completeness_ongefilterd(client, admin_headers, seed):
    r = client.get("/api/pim/completeness", headers=admin_headers)
    assert r.status_code == 200
    skus = {i["sku_id"] for i in r.json()["items"]}
    assert SKU_A in skus and SKU_B in skus


def test_pim_completeness_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/pim/completeness",
                   params={"hierarchy_node_ids": str(seed["node_a"])},
                   headers=admin_headers)
    assert r.status_code == 200
    skus = {i["sku_id"] for i in r.json()["items"]}
    assert SKU_A in skus and SKU_B not in skus


def test_pim_completeness_leeg_filter(client, admin_headers, seed):
    r = client.get("/api/pim/completeness",
                   params={"hierarchy_node_ids": NOMATCH},
                   headers=admin_headers)
    assert r.status_code == 200
    skus = {i["sku_id"] for i in r.json()["items"]}
    assert SKU_A not in skus and SKU_B not in skus


def test_pim_suggestions_gefilterd_op_subnode(client, admin_headers, seed):
    r = client.get("/api/pim/suggestions",
                   params={"hierarchy_node_ids": str(seed["node_b"])},
                   headers=admin_headers)
    assert r.status_code == 200
    skus = {s["sku_id"] for s in r.json()}
    assert SKU_B in skus and SKU_A not in skus


def test_pim_suggestions_leeg_filter(client, admin_headers, seed):
    r = client.get("/api/pim/suggestions",
                   params={"hierarchy_node_ids": NOMATCH},
                   headers=admin_headers)
    assert r.status_code == 200
    skus = {s["sku_id"] for s in r.json()}
    assert SKU_A not in skus and SKU_B not in skus


def test_pim_overview_gefilterd_vs_ongefilterd(client, admin_headers, seed):
    """Overview-aggregaten schalen mee met de filter: subnode → 1 SKU,
    root → 2 SKU's, niet-matchende node → 0 van onze SKU's."""
    r_sub = client.get("/api/pim/overview",
                       params={"hierarchy_node_ids": str(seed["node_a"])},
                       headers=admin_headers)
    r_root = client.get("/api/pim/overview",
                        params={"hierarchy_node_ids": str(seed["root"])},
                        headers=admin_headers)
    r_none = client.get("/api/pim/overview",
                        params={"hierarchy_node_ids": NOMATCH},
                        headers=admin_headers)
    assert r_sub.status_code == 200 and r_root.status_code == 200
    assert r_none.status_code == 200
    # Onze twee producten hebben elk één overall completeness-score.
    assert r_root.json()["skus_scored"] - r_sub.json()["skus_scored"] == 1
    assert r_sub.json()["skus_scored"] >= 1
    assert r_none.json()["skus_scored"] == 0
    assert r_none.json()["total_skus"] == 0
