"""
Integratietests voor de Commercial Decision & Impact Engine (§25/§28/§53/§56):
- scenario-generatie met WHY-structuur en data gaps
- §28-approvalflow inclusief historie
- shop-isolatie / IDOR (beslissingen van een andere shop zijn onzichtbaar)
- savepoint-gedrag: één kapotte entiteit wist geen eerder werk
Draait tegen de dev-database via de FastAPI TestClient; testdata wordt opgeruimd.
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
from engine.signal_publisher import publish_signal
from unittest.mock import patch
import engine.decision_engine as decision_engine
from engine.decision_engine import run_decision_engine

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}


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


def _seed_product(db, sku, shop_id=1, days=30):
    db.add(models.DimProduct(
        sku_id=sku, product_name=f"Testproduct {sku}", category="Test",
        current_price=20.0, cost_price=10.0, min_price=14.0, max_price=28.0,
        stock_quantity=150, lifecycle_status="active", shop_id=shop_id,
    ))
    for i in range(days):
        db.add(models.FactSalesDaily(
            sku_id=sku, date=date.today() - timedelta(days=i), shop_id=shop_id,
            units_sold=5, revenue=100.0, margin=50.0, margin_pct=50.0,
        ))


def _seed_signal(db, sku, shop_id=1):
    publish_signal(
        db, engine="competition", signal_type="price_increase_opportunity",
        entity_type="sku", entity_id=sku, entity_name=f"Testproduct {sku}",
        severity="high", direction="positive", metric="price_index",
        current_value=0.9, change_pct=-10.0, confidence=0.85,
        explanation="Test: prijsruimte t.o.v. de markt.",
        evidence={"price_index": 0.9}, sources=["fact_competitor_price_daily"],
        model_version="test", shop_id=shop_id,
    )


def _cleanup(db, skus, extra_shop_id=None):
    dids = [d.id for d in db.query(models.Decision).filter(models.Decision.entity_id.in_(skus)).all()]
    # Als er een extra shop is, verwijder ook alle beslissingen voor die shop
    # (inclusief categoriebeslissingen die door de engine zijn aangemaakt).
    if extra_shop_id:
        extra_dids = [d.id for d in db.query(models.Decision).filter(models.Decision.shop_id == extra_shop_id).all()]
        dids = list(set(dids + extra_dids))
    if dids:
        db.query(models.DecisionScenario).filter(models.DecisionScenario.decision_id.in_(dids)).delete(synchronize_session=False)
        db.query(models.DecisionEvent).filter(models.DecisionEvent.decision_id.in_(dids)).delete(synchronize_session=False)
        db.query(models.Decision).filter(models.Decision.id.in_(dids)).delete(synchronize_session=False)
    db.query(models.IntelligenceSignal).filter(models.IntelligenceSignal.entity_id.in_(skus)).delete(synchronize_session=False)
    db.query(models.FactSalesDaily).filter(models.FactSalesDaily.sku_id.in_(skus)).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
    if extra_shop_id:
        db.query(models.CostUsageRecord).filter(models.CostUsageRecord.shop_id == extra_shop_id).delete(synchronize_session=False)
        db.query(models.DimShop).filter(models.DimShop.id == extra_shop_id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


def test_generation_scenarios_why_and_approval_flow(client, admin_headers, db):
    sku = f"TDEC-{uuid.uuid4().hex[:8]}"
    try:
        _seed_product(db, sku)
        _seed_signal(db, sku)
        db.commit()

        r = client.post("/api/decisions/run", headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["decisions_created"] >= 1

        items = client.get("/api/decisions", params={"entity_id": sku}, headers=admin_headers).json()["items"]
        assert len(items) == 1
        did = items[0]["id"]

        det = client.get(f"/api/decisions/{did}", headers=admin_headers).json()
        assert det["status"] == "proposed"
        types = {s["scenario_type"] for s in det["scenarios"]}
        assert {"price_increase", "price_decrease", "price_hold", "promotion",
                "loyalty_incentive", "bundle", "no_action"} <= types
        rec = [s for s in det["scenarios"] if s["is_recommended"]]
        assert len(rec) == 1
        why = rec[0]["why"]
        for k in ("factoren", "bronnen", "aannames", "berekeningen"):
            assert k in why
        # §56: elasticiteit ontbreekt → expliciete data gap
        assert any("data unavailable" in g for g in det["data_gaps"])

        # §28-flow: proposed → in_review → approved → executed; reject vereist note
        t = lambda body: client.post(f"/api/decisions/{did}/transition", json=body, headers=admin_headers)
        assert t({"to_status": "in_review"}).json()["status"] == "in_review"
        assert t({"to_status": "rejected"}).status_code == 400  # note verplicht
        # approve met alternatief scenario
        alt = next(s for s in det["scenarios"] if not s["is_recommended"])
        resp = t({"to_status": "approved", "scenario_id": alt["id"]}).json()
        assert resp["status"] == "approved"
        assert resp["recommended_scenario_id"] == alt["id"]
        assert t({"to_status": "proposed"}).status_code == 409  # illegale overgang
        assert t({"to_status": "executed"}).json()["status"] == "executed"

        hist = client.get(f"/api/decisions/{did}/history", headers=admin_headers).json()
        seq = [(e["from_status"], e["to_status"], e["actor_type"]) for e in hist["events"]]
        assert seq[0] == (None, "proposed", "ai")
        assert (Approved := ("in_review", "approved", "human")) in seq
        assert ("approved", "executed", "human") in seq
        assert len(hist["signal_snapshot"]) >= 1
    finally:
        _cleanup(db, [sku])


def test_shop_isolation_idor(client, admin_headers, db):
    """Beslissingen van een andere shop zijn niet zichtbaar of muteerbaar."""
    sku = f"TDEC-{uuid.uuid4().hex[:8]}"
    other = models.DimShop(shop_code=f"tshop-{uuid.uuid4().hex[:6]}", name="Andere shop")
    db.add(other)
    db.commit()
    try:
        _seed_product(db, sku, shop_id=other.id)
        _seed_signal(db, sku, shop_id=other.id)
        db.commit()

        # Run voor de andere shop maakt daar een beslissing (≥1: SKU + evt. categorie)
        r = client.post("/api/decisions/run", params={"shop_id": other.id}, headers=admin_headers)
        assert r.status_code == 200 and r.json()["decisions_created"] >= 1
        d = db.query(models.Decision).filter(
            models.Decision.entity_id == sku, models.Decision.shop_id == other.id
        ).one()
        assert d.shop_id == other.id

        # Default scope (shop 1): lijst toont hem niet, detail/history/transition zijn 404
        items = client.get("/api/decisions", params={"entity_id": sku}, headers=admin_headers).json()["items"]
        assert items == []
        assert client.get(f"/api/decisions/{d.id}", headers=admin_headers).status_code == 404
        assert client.get(f"/api/decisions/{d.id}/history", headers=admin_headers).status_code == 404
        assert client.post(f"/api/decisions/{d.id}/transition",
                           json={"to_status": "in_review"}, headers=admin_headers).status_code == 404

        # Binnen de eigen shop-scope wél zichtbaar
        assert client.get(f"/api/decisions/{d.id}", params={"shop_id": other.id},
                          headers=admin_headers).status_code == 200
    finally:
        _cleanup(db, [sku], extra_shop_id=other.id)


def test_category_decisions_derived_from_sku_signals(client, admin_headers, db):
    """Categoriebeslissingen worden afgeleid uit SKU-signalen via DimProduct.category."""
    cat = f"TestCat-{uuid.uuid4().hex[:6]}"
    sku1 = f"TDEC-C1-{uuid.uuid4().hex[:6]}"
    sku2 = f"TDEC-C2-{uuid.uuid4().hex[:6]}"
    try:
        # Beide SKU's in dezelfde categorie
        for sku in (sku1, sku2):
            db.add(models.DimProduct(
                sku_id=sku, product_name=f"Catproduct {sku}", category=cat,
                current_price=15.0, cost_price=8.0, min_price=10.0, max_price=20.0,
                stock_quantity=50, lifecycle_status="active", shop_id=1,
            ))
            for i in range(30):
                db.add(models.FactSalesDaily(
                    sku_id=sku, date=date.today() - timedelta(days=i), shop_id=1,
                    units_sold=3, revenue=45.0, margin=21.0, margin_pct=46.7,
                ))
            _seed_signal(db, sku)
        db.commit()

        # Onbeperkt budget: met echte feed-data outranken bestaande categorieën
        # de testcategorie anders binnen het standaard budget.
        with patch.object(decision_engine, "MAX_DECISIONS_PER_RUN", 10**6):
            r = client.post("/api/decisions/run", headers=admin_headers)
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["decisions_created"] >= 3  # ≥2 SKU's + ≥1 categorie

        # Categoriebeslissing is aangemaakt met entity_type="category"
        # Filter op entity_id: met echte feed-data in de DB kunnen er veel
        # categoriebeslissingen zijn en valt onze categorie anders buiten pagina 1.
        items = client.get(
            "/api/decisions", params={"entity_type": "category", "entity_id": cat}, headers=admin_headers
        ).json()["items"]
        cat_items = [d for d in items if d["entity_id"] == cat]
        assert len(cat_items) == 1, f"Verwacht 1 categoriebeslissing voor '{cat}', kreeg: {[d['entity_id'] for d in items]}"

        d = cat_items[0]
        assert d["entity_type"] == "category"
        assert d["entity_name"] == cat

        # Detail: minstens promotie- en no_action-scenario
        det = client.get(f"/api/decisions/{d['id']}", headers=admin_headers).json()
        types = {s["scenario_type"] for s in det["scenarios"]}
        assert "promotion" in types
        assert "no_action" in types

        # entity_type_counts in de lijstrespons
        resp = client.get("/api/decisions", headers=admin_headers).json()
        assert resp["entity_type_counts"].get("category", 0) >= 1
        assert resp["entity_type_counts"].get("sku", 0) >= 1

    finally:
        # Ruim categoriebeslissingen op (entity_id = categorienaam)
        cat_dids = [d.id for d in db.query(models.Decision).filter(models.Decision.entity_id == cat).all()]
        if cat_dids:
            db.query(models.DecisionScenario).filter(models.DecisionScenario.decision_id.in_(cat_dids)).delete(synchronize_session=False)
            db.query(models.DecisionEvent).filter(models.DecisionEvent.decision_id.in_(cat_dids)).delete(synchronize_session=False)
            db.query(models.Decision).filter(models.Decision.id.in_(cat_dids)).delete(synchronize_session=False)
        _cleanup(db, [sku1, sku2])


def test_category_decision_without_sales_has_data_gaps(client, admin_headers, db):
    """Categorie zonder verkoophistorie levert een beslissing op met data_gaps, geen crash."""
    cat = f"TestCat-NS-{uuid.uuid4().hex[:6]}"
    sku = f"TDEC-NS-{uuid.uuid4().hex[:6]}"
    try:
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"Nosales {sku}", category=cat,
            current_price=10.0, cost_price=5.0, min_price=7.0, max_price=14.0,
            stock_quantity=20, lifecycle_status="active", shop_id=1,
        ))
        # Geen FactSalesDaily — simuleer ontbrekende verkoopdata
        _seed_signal(db, sku)
        db.commit()

        with patch.object(decision_engine, "MAX_DECISIONS_PER_RUN", 10**6):
            r = client.post("/api/decisions/run", headers=admin_headers)
        assert r.status_code == 200, r.text

        items = client.get(
            "/api/decisions", params={"entity_type": "category", "entity_id": cat}, headers=admin_headers
        ).json()["items"]
        cat_items = [d for d in items if d["entity_id"] == cat]
        assert len(cat_items) == 1, "Categoriebeslissing moet aangemaakt worden ook zonder verkoop"

        d = cat_items[0]
        assert d["data_gaps"], "data_gaps moet gevuld zijn wanneer verkoophistorie ontbreekt"
        assert any("data unavailable" in g for g in d["data_gaps"])

        # Beslissing heeft aanbevolen scenario (geen crash)
        det = client.get(f"/api/decisions/{d['id']}", headers=admin_headers).json()
        assert det["recommended_scenario_id"] is not None
    finally:
        cat_dids = [d.id for d in db.query(models.Decision).filter(models.Decision.entity_id == cat).all()]
        if cat_dids:
            db.query(models.DecisionScenario).filter(models.DecisionScenario.decision_id.in_(cat_dids)).delete(synchronize_session=False)
            db.query(models.DecisionEvent).filter(models.DecisionEvent.decision_id.in_(cat_dids)).delete(synchronize_session=False)
            db.query(models.Decision).filter(models.Decision.id.in_(cat_dids)).delete(synchronize_session=False)
        _cleanup(db, [sku])


def test_entity_type_filter_isolates_sku_and_category(client, admin_headers, db):
    """entity_type queryparameter filtert strikt op SKU of categorie."""
    cat = f"TestCat-F-{uuid.uuid4().hex[:6]}"
    sku = f"TDEC-F-{uuid.uuid4().hex[:6]}"
    try:
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"Filtertest {sku}", category=cat,
            current_price=12.0, cost_price=6.0, min_price=9.0, max_price=16.0,
            stock_quantity=30, lifecycle_status="active", shop_id=1,
        ))
        for i in range(15):
            db.add(models.FactSalesDaily(
                sku_id=sku, date=date.today() - timedelta(days=i), shop_id=1,
                units_sold=2, revenue=24.0, margin=12.0, margin_pct=50.0,
            ))
        _seed_signal(db, sku)
        db.commit()

        client.post("/api/decisions/run", headers=admin_headers)

        sku_items = client.get("/api/decisions", params={"entity_type": "sku", "entity_id": sku}, headers=admin_headers).json()["items"]
        cat_items = client.get("/api/decisions", params={"entity_type": "category"}, headers=admin_headers).json()["items"]

        assert all(d["entity_type"] == "sku" for d in sku_items)
        assert all(d["entity_type"] == "category" for d in cat_items)
        # SKU-beslissing mag NIET in categorie-filter zitten en vice versa
        sku_ids_in_cat = [d["entity_id"] for d in cat_items if d["entity_id"] == sku]
        assert sku_ids_in_cat == [], f"SKU {sku} mag niet in categorie-filter zitten"
    finally:
        cat_dids = [d.id for d in db.query(models.Decision).filter(models.Decision.entity_id == cat).all()]
        if cat_dids:
            db.query(models.DecisionScenario).filter(models.DecisionScenario.decision_id.in_(cat_dids)).delete(synchronize_session=False)
            db.query(models.DecisionEvent).filter(models.DecisionEvent.decision_id.in_(cat_dids)).delete(synchronize_session=False)
            db.query(models.Decision).filter(models.Decision.id.in_(cat_dids)).delete(synchronize_session=False)
        _cleanup(db, [sku])


def test_single_entity_failure_does_not_erase_prior_work(client, db, monkeypatch):
    """Savepoint per entiteit: een crash bij één SKU wist eerdere beslissingen niet."""
    ok_sku = f"TDEC-{uuid.uuid4().hex[:8]}"
    bad_sku = f"TDEC-BAD-{uuid.uuid4().hex[:6]}"
    try:
        for s in (ok_sku, bad_sku):
            _seed_product(db, s)
            _seed_signal(db, s)
        db.commit()

        import engine.decision_engine as de
        real = de._build_decision

        def flaky(dbs, today, sid, entity_id, sigs, product):
            if entity_id == bad_sku:
                raise RuntimeError("kapotte entiteit (testinjectie)")
            return real(dbs, today, sid, entity_id, sigs, product)

        monkeypatch.setattr(de, "_build_decision", flaky)
        result = run_decision_engine(db)
        # De goede SKU is aangemaakt en gecommit; de kapotte alleen overgeslagen
        assert result["entities_skipped"] >= 1
        ok = db.query(models.Decision).filter(models.Decision.entity_id == ok_sku).all()
        bad = db.query(models.Decision).filter(models.Decision.entity_id == bad_sku).all()
        assert len(ok) == 1 and len(bad) == 0
        # Tellingen kloppen met wat daadwerkelijk in de database staat
        today_count = db.query(models.Decision).filter(
            models.Decision.run_date == date.today(),
            models.Decision.entity_id.in_([ok_sku, bad_sku]),
        ).count()
        assert today_count == 1
    finally:
        _cleanup(db, [ok_sku, bad_sku])
