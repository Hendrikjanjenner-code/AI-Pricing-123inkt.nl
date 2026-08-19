"""
End-to-end tests taak #217: alle Intelligence Engines filterbaar op de
centrale producthiërarchie.

Coffee-flow: dezelfde hiërarchie-selectie door Competition → Brand/BCG →
Switching → Pricing → Basket → Decision Engine geeft overal alleen data
binnen de selectie.

Marker-drilldown: een parent-selectie omvat automatisch alle descendants;
signalen zijn hierarchy-aware (kolommen + aggregatie per niveau).
"""
import os
import sys
import uuid
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from engine.signal_publisher import publish_signal

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}
PFX = f"T217-{uuid.uuid4().hex[:6]}"


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
def coffee_world(client, admin_headers):
    """Hiërarchie Koffie > Bonen (+ losse Thee-tak) met facts in elke engine.

    Alles in de default shop (id=1) zodat de default-scope endpoints het zien;
    teardown verwijdert alle testrijen expliciet.
    """
    db = SessionLocal()
    today = date.today()
    sku_coffee = f"{PFX}-KOFFIE"
    sku_tea = f"{PFX}-THEE"

    db.add_all([
        models.DimProduct(sku_id=sku_coffee, product_name=f"{PFX} Bonen 1kg",
                          brand=f"{PFX}-Marker", category=f"{PFX}-Koffie",
                          current_price=12.0, cost_price=6.0, shop_id=1,
                          is_a_brand=True),
        models.DimProduct(sku_id=sku_tea, product_name=f"{PFX} Thee",
                          brand=f"{PFX}-Ander", category=f"{PFX}-Thee",
                          current_price=4.0, cost_price=2.0, shop_id=1),
    ])
    db.flush()

    koffie = models.ProductHierarchyNode(name=f"{PFX}-Koffie", level=1,
                                         path_names=f"{PFX}-Koffie")
    db.add(koffie); db.flush()
    koffie.path = f"/{koffie.id}/"
    bonen = models.ProductHierarchyNode(name=f"{PFX}-Bonen", level=2,
                                        parent_id=koffie.id,
                                        path_names=f"{PFX}-Koffie > {PFX}-Bonen")
    db.add(bonen); db.flush()
    bonen.path = f"/{koffie.id}/{bonen.id}/"
    thee = models.ProductHierarchyNode(name=f"{PFX}-Thee", level=1,
                                       path_names=f"{PFX}-Thee")
    db.add(thee); db.flush()
    thee.path = f"/{thee.id}/"

    db.add_all([
        models.ProductHierarchyAssignment(sku_id=sku_coffee, node_id=bonen.id, status="active"),
        models.ProductHierarchyAssignment(sku_id=sku_tea, node_id=thee.id, status="active"),
    ])

    # Facts per engine (voor beide SKU's, zodat filteren zichtbaar verschil maakt)
    for sku in (sku_coffee, sku_tea):
        db.add(models.SkuCompetitionScore(sku_id=sku, run_date=today, shop_id=1,
                                          pcis_score=55.0, competition_class="Monitor",
                                          price_index=1.02))
        db.add(models.FactPricingRecommendationDaily(
            date=today, sku_id=sku, shop_id=1, current_price=10, recommended_price=11,
            approval_status="pending", confidence_score=0.7))
        db.add(models.InternalCompetitionScore(
            run_date=today, sku_id=sku, paired_sku_id=sku,
            internal_switch_probability=0.4, internal_margin_gap=1.0, isv=0.5,
            recommended_internal_action="monitor"))
        db.add(models.BasketAssociation(run_date=today, shop_id=1,
                                        antecedent_sku=sku, consequent_sku=sku,
                                        antecedent_name=sku, consequent_name=sku,
                                        support=0.1, confidence=0.5, lift=2.0,
                                        co_purchase_count=5))
        db.add(models.Decision(run_date=today, shop_id=1, entity_type="sku",
                               entity_id=sku, entity_name=sku, title=f"{PFX} besluit {sku}",
                               summary="t", status="proposed", confidence=0.6))
    db.commit()

    # Signalen via de publisher (moet hierarchy-kolommen automatisch vullen)
    sig_coffee = publish_signal(
        db, engine="competition", signal_type=f"{PFX.lower()}_pressure",
        entity_type="sku", entity_id=sku_coffee, severity="high",
        explanation="test", evidence={"t": 1}, sources=["test"], shop_id=1)
    publish_signal(
        db, engine="competition", signal_type=f"{PFX.lower()}_pressure",
        entity_type="sku", entity_id=sku_tea, severity="low",
        explanation="test", evidence={"t": 1}, sources=["test"], shop_id=1)
    db.commit()
    sig_ids = [sig_coffee.id]

    yield {
        "sku_coffee": sku_coffee, "sku_tea": sku_tea,
        "koffie": koffie.id, "bonen": bonen.id, "thee": thee.id,
    }

    db.rollback()
    skus = [sku_coffee, sku_tea]
    for model, col in [
        (models.IntelligenceSignal, models.IntelligenceSignal.entity_id),
        (models.Decision, models.Decision.entity_id),
        (models.SkuCompetitionScore, models.SkuCompetitionScore.sku_id),
        (models.FactPricingRecommendationDaily, models.FactPricingRecommendationDaily.sku_id),
        (models.InternalCompetitionScore, models.InternalCompetitionScore.sku_id),
        (models.BasketAssociation, models.BasketAssociation.antecedent_sku),
        (models.ProductHierarchyAssignment, models.ProductHierarchyAssignment.sku_id),
    ]:
        db.query(model).filter(col.in_(skus)).delete(synchronize_session=False)
    for nid in (bonen.id, thee.id, koffie.id):
        db.query(models.ProductHierarchyNode).filter(
            models.ProductHierarchyNode.id == nid).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
    db.commit()
    db.close()


def _hn(world):
    return f"hierarchy_node_ids={world['koffie']}"


def test_publisher_fills_hierarchy_columns(coffee_world):
    db = SessionLocal()
    try:
        s = db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.entity_id == coffee_world["sku_coffee"],
            models.IntelligenceSignal.status == "active",
        ).first()
        assert s is not None
        assert s.hierarchy_node_id == coffee_world["bonen"]
        assert s.hierarchy_level == 2
    finally:
        db.close()


def test_coffee_flow_competition(client, admin_headers, coffee_world):
    r = client.get(f"/api/competition/skus?{_hn(coffee_world)}&page_size=200",
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {row["sku_id"] for row in r.json().get("items", r.json().get("skus", []))}
    assert coffee_world["sku_coffee"] in skus
    assert coffee_world["sku_tea"] not in skus


def test_coffee_flow_switching(client, admin_headers, coffee_world):
    r = client.get(f"/api/huismerk-impact/overzicht?{_hn(coffee_world)}&page_size=200",
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    rows = body.get("items") or []
    skus = {row.get("a_merk_sku") for row in rows}
    assert coffee_world["sku_coffee"] in skus
    assert coffee_world["sku_tea"] not in skus


def test_coffee_flow_pricing(client, admin_headers, coffee_world):
    r = client.get(f"/api/recommendations?{_hn(coffee_world)}&page_size=500",
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    skus = {row["sku_id"] for row in r.json()["items"]}
    assert coffee_world["sku_coffee"] in skus
    assert coffee_world["sku_tea"] not in skus


def test_coffee_flow_basket(client, admin_headers, coffee_world):
    r = client.get(f"/api/basket/associations?{_hn(coffee_world)}", headers=admin_headers)
    assert r.status_code == 200, r.text
    text = r.text
    assert coffee_world["sku_coffee"] in text
    assert coffee_world["sku_tea"] not in text


def test_coffee_flow_decisions(client, admin_headers, coffee_world):
    r = client.get(f"/api/decisions?{_hn(coffee_world)}&page_size=100",
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    ids = {d["entity_id"] for d in r.json()["items"]}
    assert coffee_world["sku_coffee"] in ids
    assert coffee_world["sku_tea"] not in ids


def test_coffee_flow_signals(client, admin_headers, coffee_world):
    r = client.get(f"/api/signals?{_hn(coffee_world)}&page_size=200",
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    ids = {s["entity_id"] for s in r.json()["signals"]}
    assert coffee_world["sku_coffee"] in ids
    assert coffee_world["sku_tea"] not in ids


def test_marker_drilldown_parent_includes_descendants(client, admin_headers, coffee_world):
    # Selectie op parent (Koffie, level 1) omvat de SKU die aan het kind
    # (Bonen, level 2) is toegewezen — descendant-expansie server-side.
    r = client.get(f"/api/recommendations?hierarchy_node_ids={coffee_world['koffie']}&page_size=500",
                   headers=admin_headers)
    skus = {row["sku_id"] for row in r.json()["items"]}
    assert coffee_world["sku_coffee"] in skus
    # Kind-selectie geeft hetzelfde resultaat
    r2 = client.get(f"/api/recommendations?hierarchy_node_ids={coffee_world['bonen']}&page_size=500",
                    headers=admin_headers)
    assert coffee_world["sku_coffee"] in {row["sku_id"] for row in r2.json()["items"]}


def test_marker_drilldown_signal_aggregation(client, admin_headers, coffee_world):
    # Aggregatie op niveau 1 telt het koffiesignaal onder de Koffie-node
    r = client.get(f"/api/signals/aggregate?level=1&{_hn(coffee_world)}",
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    nodes = {n["node_id"]: n for n in r.json()["nodes"]}
    assert coffee_world["koffie"] in nodes
    assert nodes[coffee_world["koffie"]]["totaal"] >= 1
    # Niveau 2: onder de Bonen-node
    r2 = client.get(f"/api/signals/aggregate?level=2&{_hn(coffee_world)}",
                    headers=admin_headers)
    nodes2 = {n["node_id"]: n for n in r2.json()["nodes"]}
    assert coffee_world["bonen"] in nodes2


def test_empty_selection_matches_nothing(client, admin_headers, coffee_world):
    # Merk dat niet bestaat → lege set → niets matcht (nooit "geen filter")
    r = client.get(f"/api/recommendations?brands={PFX}-BestaatNiet&page_size=50",
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_bcg_categorie_matrix_filtered(client, admin_headers, coffee_world):
    """Categorie-matrix toont alleen categorieën met producten in de selectie."""
    db = SessionLocal()
    today = date.today()
    try:
        for cat in (f"{PFX}-Koffie", f"{PFX}-Thee"):
            db.add(models.FactBcgClassificationDaily(
                date=today, entity_type="CATEGORY", entity_id=cat,
                ibss_score=0.5, gps_score=0.5, css_external_score=0.3,
                mos_score=0.5, pricing_power_score=0.5))
        db.commit()
        r = client.get(f"/api/bcg/categorie-matrix?{_hn(coffee_world)}",
                       headers=admin_headers)
        assert r.status_code == 200, r.text
        cats = {i["categorie"] for i in r.json()["items"]}
        assert f"{PFX}-Koffie" in cats
        assert f"{PFX}-Thee" not in cats
        # Lege selectie (onbekend merk) matcht niets
        r2 = client.get(f"/api/bcg/categorie-matrix?brands={PFX}-BestaatNiet",
                        headers=admin_headers)
        assert {i["categorie"] for i in r2.json()["items"]} == set()
        # BCG-dashboard: hoog-drukcategorieën ook binnen de selectie
        r3 = client.get(f"/api/bcg/dashboard?{_hn(coffee_world)}",
                        headers=admin_headers)
        assert r3.status_code == 200, r3.text
        druk = r3.json().get("hoog_concurrentiedruk_categories", [])
        druk_cats = {d.get("categorie") or d.get("naam") for d in druk}
        assert f"{PFX}-Thee" not in druk_cats
    finally:
        db.rollback()
        db.query(models.FactBcgClassificationDaily).filter(
            models.FactBcgClassificationDaily.entity_id.in_(
                [f"{PFX}-Koffie", f"{PFX}-Thee"])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_command_center_pending_approvals_filtered(client, admin_headers, coffee_world):
    """pending_approvals telt alleen beslissingen binnen de actieve selectie."""
    full = client.get("/api/command-center/summary", headers=admin_headers).json()
    filtered = client.get(f"/api/command-center/summary?{_hn(coffee_world)}",
                          headers=admin_headers).json()

    def pending(body):
        # veld zit in de ai/approvals-sectie; zoek recursief op sleutelnaam
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("pending_approvals", "approvals_pending"):
                        return v
                    got = walk(v)
                    if got is not None:
                        return got
            return None
        return walk(body)

    p_full, p_filtered = pending(full), pending(filtered)
    assert p_full is not None and p_filtered is not None
    # Fixture heeft 2 proposed besluiten (koffie+thee); gefilterd < ongefilterd
    assert p_filtered < p_full


def test_opportunities_respect_filter(client, admin_headers, coffee_world):
    db = SessionLocal()
    try:
        db.add(models.Opportunity(
            run_date=date.today(), shop_id=1, source_engine="pricing",
            opportunity_type="price", entity_type="sku",
            entity_id=coffee_world["sku_tea"], entity_name="thee",
            title_nl=f"{PFX} thee kans", explanation_nl="t",
            expected_value_eur=10, confidence=0.5, urgency="low",
            effort="low", risk="low", priority_score=1, status="open"))
        db.commit()
        r = client.get(f"/api/opportunities?{_hn(coffee_world)}", headers=admin_headers)
        assert r.status_code == 200, r.text
        ids = {o["sku_id"] for o in r.json()["opportunities"]}
        assert coffee_world["sku_tea"] not in ids
    finally:
        db.query(models.Opportunity).filter(
            models.Opportunity.entity_id.in_(
                [coffee_world["sku_tea"], coffee_world["sku_coffee"]])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()
