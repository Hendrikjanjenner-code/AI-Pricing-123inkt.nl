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


@pytest.fixture(scope="module")
def shop_id():
    """
    Dedicated testshop: de dev-DB is gedeeld (3k+ producten met echte actieve
    signalen na een feed-sync). De Decision Engine rankt signalen op severity
    met een cap (MAX_DECISIONS_PER_RUN), dus in shop 1 wordt een vers geseede
    SKU verdrongen en ontstaat er geen decision. Alle tests die de engine
    draaien doen dat daarom in hun eigen shop-scope.
    """
    s = SessionLocal()
    shop = models.DimShop(
        shop_code=f"tdec-{uuid.uuid4().hex[:8]}",
        name="Decisions testshop", is_default=False, active=True,
    )
    s.add(shop)
    s.commit()
    sid = shop.id
    try:
        yield sid
    finally:
        try:
            # Volgorde: eerst afhankelijke rijen (o.a. cost-usage via request-
            # middleware), dan de shop zelf.
            s.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(synchronize_session=False)
            s.query(models.IntelligenceSignal).filter(
                models.IntelligenceSignal.shop_id == sid).delete(synchronize_session=False)
            dids = [d.id for d in s.query(models.Decision).filter(
                models.Decision.shop_id == sid).all()]
            if dids:
                s.query(models.DecisionScenario).filter(
                    models.DecisionScenario.decision_id.in_(dids)).delete(synchronize_session=False)
                s.query(models.DecisionEvent).filter(
                    models.DecisionEvent.decision_id.in_(dids)).delete(synchronize_session=False)
                s.query(models.Decision).filter(
                    models.Decision.id.in_(dids)).delete(synchronize_session=False)
            s.query(models.FactPricingRecommendationDaily).filter(
                models.FactPricingRecommendationDaily.shop_id == sid).delete(synchronize_session=False)
            s.query(models.FactSalesDaily).filter(
                models.FactSalesDaily.shop_id == sid).delete(synchronize_session=False)
            s.query(models.DimProduct).filter(
                models.DimProduct.shop_id == sid).delete(synchronize_session=False)
            s.query(models.DimShop).filter(models.DimShop.id == sid).delete()
            s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()


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


def _pre_cleanup_cat(db, cat):
    """Verwijder eventuele overgebleven categoriebeslissingen (dirty-DB guard)."""
    cat_dids = [d.id for d in db.query(models.Decision).filter(models.Decision.entity_id == cat).all()]
    if cat_dids:
        db.query(models.DecisionScenario).filter(models.DecisionScenario.decision_id.in_(cat_dids)).delete(synchronize_session=False)
        db.query(models.DecisionEvent).filter(models.DecisionEvent.decision_id.in_(cat_dids)).delete(synchronize_session=False)
        db.query(models.Decision).filter(models.Decision.id.in_(cat_dids)).delete(synchronize_session=False)
        db.commit()


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


def test_generation_scenarios_why_and_approval_flow(client, admin_headers, db, shop_id):
    sku = f"TDEC-{uuid.uuid4().hex[:8]}"
    try:
        _seed_product(db, sku, shop_id=shop_id)
        _seed_signal(db, sku, shop_id=shop_id)
        db.commit()

        r = client.post("/api/decisions/run", params={"shop_id": shop_id}, headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["decisions_created"] >= 1

        items = client.get("/api/decisions", params={"entity_id": sku, "shop_id": shop_id}, headers=admin_headers).json()["items"]
        assert len(items) == 1
        did = items[0]["id"]

        det = client.get(f"/api/decisions/{did}", params={"shop_id": shop_id}, headers=admin_headers).json()
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
        t = lambda body: client.post(f"/api/decisions/{did}/transition",
                                     json={**body, "shop_id": shop_id}, headers=admin_headers)
        assert t({"to_status": "in_review"}).json()["status"] == "in_review"
        assert t({"to_status": "rejected"}).status_code == 400  # note verplicht
        # approve met alternatief (niet-prijs) scenario — prijsscenario's volgen
        # sinds de executiekoppeling het execution-pad (zie aparte test)
        alt = next(s for s in det["scenarios"]
                   if not s["is_recommended"]
                   and s["scenario_type"] not in ("price_increase", "price_decrease"))
        resp = t({"to_status": "approved", "scenario_id": alt["id"]}).json()
        assert resp["status"] == "approved"
        assert resp["recommended_scenario_id"] == alt["id"]
        assert t({"to_status": "proposed"}).status_code == 409  # illegale overgang
        assert t({"to_status": "executed"}).json()["status"] == "executed"

        hist = client.get(f"/api/decisions/{did}/history", params={"shop_id": shop_id}, headers=admin_headers).json()
        seq = [(e["from_status"], e["to_status"], e["actor_type"]) for e in hist["events"]]
        assert seq[0] == (None, "proposed", "ai")
        assert (Approved := ("in_review", "approved", "human")) in seq
        assert ("approved", "executed", "human") in seq
        assert len(hist["signal_snapshot"]) >= 1
    finally:
        _cleanup(db, [sku])

def test_approved_price_scenario_flows_into_execution(client, admin_headers, db, shop_id):
    """Goedkeuring van een prijsscenario zet een goedgekeurde prijsregel klaar;
    'markeer als uitgevoerd' vereist en koppelt de execution-job."""
    sku = f"TDEC-{uuid.uuid4().hex[:8]}"
    job_id = None
    try:
        _seed_product(db, sku, shop_id=shop_id)
        _seed_signal(db, sku, shop_id=shop_id)
        db.commit()

        r = client.post("/api/decisions/run", params={"shop_id": shop_id}, headers=admin_headers)
        assert r.status_code == 200, r.text
        items = client.get("/api/decisions", params={"entity_id": sku, "shop_id": shop_id}, headers=admin_headers).json()["items"]
        did = items[0]["id"]
        det = client.get(f"/api/decisions/{did}", params={"shop_id": shop_id}, headers=admin_headers).json()

        price_sc = next(s for s in det["scenarios"] if s["scenario_type"] == "price_increase")
        assert price_sc["parameters"].get("new_price")

        t = lambda body: client.post(f"/api/decisions/{did}/transition",
                                     json={**body, "shop_id": shop_id}, headers=admin_headers)
        assert t({"to_status": "in_review"}).status_code == 200
        resp = t({"to_status": "approved", "scenario_id": price_sc["id"]})
        assert resp.status_code == 200, resp.text
        execution = resp.json().get("execution")
        assert execution and execution["execution_staged"] is True
        rec_id = execution["recommendation_id"]

        # Detail-GET blijft de klaargezette prijsregel tonen (badge overleeft refresh)
        det2 = client.get(f"/api/decisions/{did}", params={"shop_id": shop_id}, headers=admin_headers).json()
        assert det2.get("execution", {}).get("execution_staged") is True
        assert det2["execution"]["recommendation_id"] == rec_id
        assert "execution_job_id" not in det2["execution"]

        # Aanbeveling staat klaar in het bestaande execution-pad
        rec = db.get(models.FactPricingRecommendationDaily, rec_id)
        assert rec.source_decision_id == did
        assert rec.approval_status == "approved"
        assert float(rec.recommended_price) == price_sc["parameters"]["new_price"]

        # Zonder execution-job kan de beslissing niet 'uitgevoerd' worden
        blocked = t({"to_status": "executed"})
        assert blocked.status_code == 409, blocked.text

        # Regressie: een export voor een ANDERE aanbeveling van dezelfde SKU
        # (oudere datum) telt niet als uitvoering van deze beslissing
        decoy_date = date.today() - timedelta(days=3)
        decoy = models.FactPricingRecommendationDaily(
            date=decoy_date, sku_id=sku, shop_id=shop_id,
            current_price=20.0, recommended_price=20.50,
            confidence_score=0.9, reason_code="decoy",
            approval_status="approved", approved_by="test",
        )
        db.add(decoy)
        db.commit()
        exp_decoy = client.post("/api/execution/export-csv",
                                json={"datum": str(decoy_date)}, headers=admin_headers)
        assert exp_decoy.status_code == 200, exp_decoy.text
        still_blocked = t({"to_status": "executed"})
        assert still_blocked.status_code == 409, still_blocked.text

        # Menselijk gestuurde uitvoering: export maakt een job aan
        exp = client.post("/api/execution/export-csv", json={}, headers=admin_headers)
        assert exp.status_code == 200, exp.text
        line = (
            db.query(models.PriceExecutionLine)
            .filter(models.PriceExecutionLine.recommendation_id == rec_id)
            .order_by(models.PriceExecutionLine.line_id.desc())
            .first()
        )
        assert line is not None and line.status == "goedgekeurd"
        job_id = line.job_id

        # Nu wél uitvoerbaar; event koppelt terug naar de job (audit compleet)
        done = t({"to_status": "executed"})
        assert done.status_code == 200, done.text
        hist = client.get(f"/api/decisions/{did}/history", params={"shop_id": shop_id}, headers=admin_headers).json()
        exec_event = next(e for e in hist["events"] if e["to_status"] == "executed")
        assert exec_event["values_snapshot"]["execution_job_id"] == job_id
        assert exec_event["values_snapshot"]["recommendation_id"] == rec_id

        # Detail-GET toont nu ook de gekoppelde execution-job
        det3 = client.get(f"/api/decisions/{did}", params={"shop_id": shop_id}, headers=admin_headers).json()
        assert det3["execution"]["execution_job_id"] == job_id
    finally:
        db.rollback()
        sku_job_ids = [
            l.job_id for l in db.query(models.PriceExecutionLine)
            .filter(models.PriceExecutionLine.sku_id == sku).all()
        ]
        if sku_job_ids:
            db.query(models.PriceExecutionLine).filter(models.PriceExecutionLine.job_id.in_(sku_job_ids)).delete(synchronize_session=False)
            db.query(models.PriceExecutionJob).filter(models.PriceExecutionJob.job_id.in_(sku_job_ids)).delete(synchronize_session=False)
        db.query(models.FactPricingRecommendationDaily).filter(
            models.FactPricingRecommendationDaily.sku_id == sku
        ).delete(synchronize_session=False)
        db.commit()
        _cleanup(db, [sku])

def test_second_export_skips_already_processed_lines(client, admin_headers, db, shop_id):
    """Dubbel-uitvoer-guard: een klaargezette regel gaat niet nogmaals mee.
    - Twee opeenvolgende exports: de tweede vindt de al verwerkte regel niet meer.
    - Een dry-run markeert niets als verwerkt.
    - Regels van een 'executed' beslissing gaan niet mee in nieuwe jobs."""
    sku = f"TDEC-{uuid.uuid4().hex[:8]}"
    datum1 = date.today() - timedelta(days=40)
    datum2 = date.today() - timedelta(days=41)
    decision_id = None
    try:
        _seed_product(db, sku, shop_id=shop_id, days=0)
        rec1 = models.FactPricingRecommendationDaily(
            date=datum1, sku_id=sku, shop_id=shop_id,
            current_price=20.0, recommended_price=21.0,
            confidence_score=0.9, reason_code="test_dubbel_export",
            approval_status="approved", approved_by="test",
        )
        db.add(rec1)
        db.commit()

        # Dry-run neemt de regel mee maar markeert niets als verwerkt
        dr = client.post("/api/execution/dry-run", json={"datum": str(datum1)}, headers=admin_headers)
        assert dr.status_code == 200, dr.text
        db.refresh(rec1)
        assert rec1.processing_status != "verwerkt"

        # Eerste export: regel gaat mee en wordt verwerkt
        exp1 = client.post("/api/execution/export-csv", json={"datum": str(datum1)}, headers=admin_headers)
        assert exp1.status_code == 200, exp1.text
        db.refresh(rec1)
        assert rec1.processing_status == "verwerkt"
        assert rec1.exported is True
        assert rec1.processed_at is not None

        # Tweede export met dezelfde datum: de regel gaat NIET nogmaals mee
        exp2 = client.post("/api/execution/export-csv", json={"datum": str(datum1)}, headers=admin_headers)
        assert exp2.status_code == 404, exp2.text
        from services.execution_engine import DRY_RUN
        lijnen = (
            db.query(models.PriceExecutionLine)
            .join(models.PriceExecutionJob,
                  models.PriceExecutionJob.job_id == models.PriceExecutionLine.job_id)
            .filter(
                models.PriceExecutionLine.recommendation_id == rec1.id,
                models.PriceExecutionJob.execution_mode != DRY_RUN,
            )
            .count()
        )
        assert lijnen == 1, "regel mag maar in één export-job zitten"

        # Regel van een beslissing met status 'executed' gaat niet meer mee,
        # ook als processing_status (nog) niet is bijgewerkt
        d = models.Decision(
            shop_id=shop_id, run_date=date.today(), entity_type="sku",
            entity_id=sku, title="Test executed", status="executed",
        )
        db.add(d)
        db.flush()
        decision_id = d.id
        rec2 = models.FactPricingRecommendationDaily(
            date=datum2, sku_id=sku, shop_id=shop_id,
            current_price=20.0, recommended_price=22.0,
            confidence_score=0.9, reason_code="test_executed_decision",
            approval_status="approved", approved_by="test",
            source_decision_id=d.id,
        )
        db.add(rec2)
        db.commit()

        exp3 = client.post("/api/execution/export-csv", json={"datum": str(datum2)}, headers=admin_headers)
        assert exp3.status_code == 404, exp3.text
    finally:
        db.rollback()
        job_ids = [
            l.job_id for l in db.query(models.PriceExecutionLine)
            .filter(models.PriceExecutionLine.sku_id == sku).all()
        ]
        if job_ids:
            db.query(models.PriceExecutionLine).filter(models.PriceExecutionLine.job_id.in_(job_ids)).delete(synchronize_session=False)
            db.query(models.PriceExecutionJob).filter(models.PriceExecutionJob.job_id.in_(job_ids)).delete(synchronize_session=False)
        db.query(models.FactPricingRecommendationDaily).filter(
            models.FactPricingRecommendationDaily.sku_id == sku
        ).delete(synchronize_session=False)
        if decision_id:
            db.query(models.DecisionEvent).filter(models.DecisionEvent.decision_id == decision_id).delete(synchronize_session=False)
            db.query(models.Decision).filter(models.Decision.id == decision_id).delete(synchronize_session=False)
        db.commit()
        _cleanup(db, [sku])

def test_concurrent_exports_execute_line_only_once(client, admin_headers, db, shop_id):
    """Race-guard: twee gelijktijdige exports van dezelfde klaargezette regel
    leiden tot precies één uitvoering — de claim is atomisch (conditionele
    UPDATE), dus maar één verzoek krijgt de regel mee."""
    from concurrent.futures import ThreadPoolExecutor

    sku = f"TDEC-{uuid.uuid4().hex[:8]}"
    datum = date.today() - timedelta(days=50)
    try:
        _seed_product(db, sku, shop_id=shop_id, days=0)
        rec = models.FactPricingRecommendationDaily(
            date=datum, sku_id=sku, shop_id=shop_id,
            current_price=20.0, recommended_price=21.0,
            confidence_score=0.9, reason_code="test_race_export",
            approval_status="approved", approved_by="test",
        )
        db.add(rec)
        db.commit()
        rec_id = rec.id

        doe_export = lambda _: client.post(
            "/api/execution/export-csv", json={"datum": str(datum)}, headers=admin_headers)
        with ThreadPoolExecutor(max_workers=2) as pool:
            resp_a, resp_b = list(pool.map(doe_export, range(2)))

        statussen = sorted([resp_a.status_code, resp_b.status_code])
        assert statussen in ([200, 404], [200, 200]), (resp_a.text, resp_b.text)

        # Ongeacht de timing: de regel zit in precies één export-job
        lijnen = db.query(models.PriceExecutionLine).filter(
            models.PriceExecutionLine.recommendation_id == rec_id
        ).count()
        assert lijnen == 1, f"regel is {lijnen}x uitgevoerd i.p.v. 1x"
        db.refresh(rec)
        assert rec.processing_status == "verwerkt"
    finally:
        db.rollback()
        job_ids = [
            l.job_id for l in db.query(models.PriceExecutionLine)
            .filter(models.PriceExecutionLine.sku_id == sku).all()
        ]
        if job_ids:
            db.query(models.PriceExecutionLine).filter(models.PriceExecutionLine.job_id.in_(job_ids)).delete(synchronize_session=False)
            db.query(models.PriceExecutionJob).filter(models.PriceExecutionJob.job_id.in_(job_ids)).delete(synchronize_session=False)
        db.query(models.FactPricingRecommendationDaily).filter(
            models.FactPricingRecommendationDaily.sku_id == sku
        ).delete(synchronize_session=False)
        db.commit()
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


def test_category_decisions_derived_from_sku_signals(client, admin_headers, db, shop_id):
    """Categoriebeslissingen worden afgeleid uit SKU-signalen via DimProduct.category."""
    cat = f"TestCat-{uuid.uuid4().hex[:6]}"
    sku1 = f"TDEC-C1-{uuid.uuid4().hex[:6]}"
    sku2 = f"TDEC-C2-{uuid.uuid4().hex[:6]}"
    try:
        # Verwijder eventuele overgebleven beslissingen van eerdere mislukte runs
        # voor dezelfde categorie (validatieomgeving kan dirty state hebben).
        _pre_cleanup_cat(db, cat)

        # Beide SKU's in dezelfde categorie; één huismerk voor huismerkaandeel
        for sku in (sku1, sku2):
            db.add(models.DimProduct(
                sku_id=sku, product_name=f"Catproduct {sku}", category=cat,
                subcategory="TestSub", is_private_label=(sku == sku1),
                current_price=15.0, cost_price=8.0, min_price=10.0, max_price=20.0,
                stock_quantity=50, lifecycle_status="active", shop_id=shop_id,
            ))
            for i in range(30):
                db.add(models.FactSalesDaily(
                    sku_id=sku, date=date.today() - timedelta(days=i), shop_id=shop_id,
                    units_sold=3, revenue=45.0, margin=21.0, margin_pct=46.7,
                ))
            _seed_signal(db, sku, shop_id=shop_id)
        db.commit()

        # Eigen shop-scope: echte feed-data (shop 1) kan de testdata niet meer
        # verdringen binnen het standaard budget (MAX_DECISIONS_PER_RUN).
        r = client.post("/api/decisions/run", params={"shop_id": shop_id}, headers=admin_headers)
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["decisions_created"] >= 3  # ≥2 SKU's + ≥1 categorie

        # Categoriebeslissing is aangemaakt met entity_type="category"
        items = client.get(
            "/api/decisions",
            params={"entity_type": "category", "entity_id": cat, "shop_id": shop_id},
            headers=admin_headers,
        ).json()["items"]
        cat_items = [d for d in items if d["entity_id"] == cat]
        assert len(cat_items) == 1, f"Verwacht 1 categoriebeslissing voor '{cat}', kreeg: {[d['entity_id'] for d in items]}"

        d = cat_items[0]
        assert d["entity_type"] == "category"
        assert d["entity_name"] == cat

        # Detail: minstens promotie- en no_action-scenario
        det = client.get(f"/api/decisions/{d['id']}", params={"shop_id": shop_id}, headers=admin_headers).json()
        types = {s["scenario_type"] for s in det["scenarios"]}
        assert "promotion" in types
        assert "no_action" in types

        # Categoriecontext (task: geaggregeerde omzet-/marge-impact op detailpagina)
        ctx = det.get("category_context")
        assert ctx is not None, "category_context moet aanwezig zijn voor categoriebeslissingen"
        assert ctx["sku_count"] == 2
        assert ctx["private_label_sku_count"] == 1
        assert ctx["private_label_share_skus"] == 0.5
        # 2 SKU's × 30 dagen × €45 omzet / €21 marge
        assert ctx["total_revenue_30d"] == pytest.approx(2700.0)
        assert ctx["total_margin_30d"] == pytest.approx(1260.0)
        assert ctx["private_label_share_revenue"] == pytest.approx(0.5)
        assert {"name": "TestSub", "sku_count": 2} in ctx["subcategories"]
        # Top-SKU's op omzet (doorklik naar onderliggende SKU's)
        top = ctx["top_skus"]
        assert {t["sku_id"] for t in top} == {sku1, sku2}
        for t in top:
            assert t["revenue_30d"] == pytest.approx(1350.0)
            assert t["margin_30d"] == pytest.approx(630.0)
            assert t["units_30d"] == 90
            assert t["is_private_label"] == (t["sku_id"] == sku1)
            assert t["product_name"] == f"Catproduct {t['sku_id']}"
        # Scenario-parameters bevatten de huismerk-SKU's (mix-shift scenario)
        mix = [s for s in det["scenarios"] if s["parameters"].get("private_label_skus")]
        assert mix and sku1 in mix[0]["parameters"]["private_label_skus"]

        # SKU-beslissingen krijgen géén category_context
        sku_items = client.get(
            "/api/decisions", params={"entity_type": "sku", "entity_id": sku1, "shop_id": shop_id}, headers=admin_headers
        ).json()["items"]
        if sku_items:
            sku_det = client.get(f"/api/decisions/{sku_items[0]['id']}", params={"shop_id": shop_id}, headers=admin_headers).json()
            assert "category_context" not in sku_det

        # entity_type_counts in de lijstrespons
        resp = client.get("/api/decisions", params={"shop_id": shop_id}, headers=admin_headers).json()
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


def test_category_decision_without_sales_has_data_gaps(client, admin_headers, db, shop_id):
    """Categorie zonder verkoophistorie levert een beslissing op met data_gaps, geen crash."""
    cat = f"TestCat-NS-{uuid.uuid4().hex[:6]}"
    sku = f"TDEC-NS-{uuid.uuid4().hex[:6]}"
    try:
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"Nosales {sku}", category=cat,
            current_price=10.0, cost_price=5.0, min_price=7.0, max_price=14.0,
            stock_quantity=20, lifecycle_status="active", shop_id=shop_id,
        ))
        # Geen FactSalesDaily — simuleer ontbrekende verkoopdata
        _seed_signal(db, sku, shop_id=shop_id)
        db.commit()

        # Eigen shop-scope i.p.v. cap-patch: geen verdringing door feed-data
        r = client.post("/api/decisions/run", params={"shop_id": shop_id}, headers=admin_headers)
        assert r.status_code == 200, r.text

        items = client.get(
            "/api/decisions",
            params={"entity_type": "category", "entity_id": cat, "shop_id": shop_id},
            headers=admin_headers,
        ).json()["items"]
        cat_items = [d for d in items if d["entity_id"] == cat]
        assert len(cat_items) == 1, "Categoriebeslissing moet aangemaakt worden ook zonder verkoop"

        d = cat_items[0]
        assert d["data_gaps"], "data_gaps moet gevuld zijn wanneer verkoophistorie ontbreekt"
        assert any("data unavailable" in g for g in d["data_gaps"])

        # Beslissing heeft aanbevolen scenario (geen crash)
        det = client.get(f"/api/decisions/{d['id']}", params={"shop_id": shop_id}, headers=admin_headers).json()
        assert det["recommended_scenario_id"] is not None
    finally:
        cat_dids = [d.id for d in db.query(models.Decision).filter(models.Decision.entity_id == cat).all()]
        if cat_dids:
            db.query(models.DecisionScenario).filter(models.DecisionScenario.decision_id.in_(cat_dids)).delete(synchronize_session=False)
            db.query(models.DecisionEvent).filter(models.DecisionEvent.decision_id.in_(cat_dids)).delete(synchronize_session=False)
            db.query(models.Decision).filter(models.Decision.id.in_(cat_dids)).delete(synchronize_session=False)
        _cleanup(db, [sku])


def test_entity_type_filter_isolates_sku_and_category(client, admin_headers, db, shop_id):
    """entity_type queryparameter filtert strikt op SKU of categorie."""
    cat = f"TestCat-F-{uuid.uuid4().hex[:6]}"
    sku = f"TDEC-F-{uuid.uuid4().hex[:6]}"
    try:
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"Filtertest {sku}", category=cat,
            current_price=12.0, cost_price=6.0, min_price=9.0, max_price=16.0,
            stock_quantity=30, lifecycle_status="active", shop_id=shop_id,
        ))
        for i in range(15):
            db.add(models.FactSalesDaily(
                sku_id=sku, date=date.today() - timedelta(days=i), shop_id=shop_id,
                units_sold=2, revenue=24.0, margin=12.0, margin_pct=50.0,
            ))
        _seed_signal(db, sku, shop_id=shop_id)
        db.commit()

        client.post("/api/decisions/run", params={"shop_id": shop_id}, headers=admin_headers)

        sku_items = client.get("/api/decisions", params={"entity_type": "sku", "entity_id": sku, "shop_id": shop_id}, headers=admin_headers).json()["items"]
        cat_items = client.get("/api/decisions", params={"entity_type": "category", "shop_id": shop_id}, headers=admin_headers).json()["items"]

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

def test_build_category_decision_empty_category_returns_none(client, db):
    """Lege categorie (geen producten) → None: expliciet overslaan i.p.v. lege beslissing."""
    decision, n_gaps = decision_engine._build_category_decision(
        db, date.today(), 1, f"LeegCat-{uuid.uuid4().hex[:6]}", [], []
    )
    assert decision is None
    assert n_gaps == 0
    db.rollback()

def test_category_cap_defers_explicitly_with_stable_order(client, db):
    """Meer categorieën dan het budget: de overloop wordt expliciet gerapporteerd
    (categories_deferred) en de selectie is deterministisch (alfabetisch bij
    gelijk signaalgewicht) — geen stille, willekeurige gaten in het dashboard."""
    n_cats = decision_engine.MAX_DECISIONS_PER_RUN + 5
    other = models.DimShop(shop_code=f"tshop-{uuid.uuid4().hex[:6]}", name="Cap shop")
    db.add(other)
    db.commit()
    skus, cats = [], []
    try:
        for i in range(n_cats):
            cat = f"CapCat-{i:03d}"
            sku = f"TDEC-CAP-{i:03d}-{uuid.uuid4().hex[:4]}"
            cats.append(cat)
            skus.append(sku)
            db.add(models.DimProduct(
                sku_id=sku, product_name=f"Cap {sku}", category=cat,
                current_price=10.0, cost_price=5.0, min_price=7.0, max_price=14.0,
                stock_quantity=10, lifecycle_status="active", shop_id=other.id,
            ))
        # Bewust géén signalen: alle categorieën hebben gelijk gewicht
        db.commit()

        result = run_decision_engine(db, shop_id=other.id)
        # Geen SKU-signalen → volledig budget voor categorieën
        assert result["decisions_created"] == decision_engine.MAX_DECISIONS_PER_RUN
        assert result["categories_deferred"] == n_cats - decision_engine.MAX_DECISIONS_PER_RUN

        decided = sorted(d.entity_id for d in db.query(models.Decision).filter(
            models.Decision.shop_id == other.id,
            models.Decision.entity_type == "category",
        ).all())
        # Deterministisch: exact de eerste N categorieën op alfabet
        assert decided == sorted(cats)[:decision_engine.MAX_DECISIONS_PER_RUN]
    finally:
        _cleanup(db, skus, extra_shop_id=other.id)
def test_single_entity_failure_does_not_erase_prior_work(client, db, monkeypatch, shop_id):
    """Savepoint per entiteit: een crash bij één SKU wist eerdere beslissingen niet."""
    ok_sku = f"TDEC-{uuid.uuid4().hex[:8]}"
    bad_sku = f"TDEC-BAD-{uuid.uuid4().hex[:6]}"
    try:
        for s in (ok_sku, bad_sku):
            _seed_product(db, s, shop_id=shop_id)
            _seed_signal(db, s, shop_id=shop_id)
        db.commit()

        import engine.decision_engine as de
        real = de._build_decision

        def flaky(dbs, today, sid, entity_id, sigs, product):
            if entity_id == bad_sku:
                raise RuntimeError("kapotte entiteit (testinjectie)")
            return real(dbs, today, sid, entity_id, sigs, product)

        monkeypatch.setattr(de, "_build_decision", flaky)
        result = run_decision_engine(db, shop_id=shop_id)
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

def test_products_deeplink_filters_server_side(client, admin_headers, db):
    """Doorklik vanaf een categoriebeslissing: /api/products moet subcategory
    en is_private_label server-side filteren (incl. correcte totalen), zodat
    deep-links ook kloppen bij categorieën groter dan één pagina."""
    cat = f"TCATP-{uuid.uuid4().hex[:8]}"
    skus = [f"{cat}-S{i}" for i in range(4)]
    try:
        for i, sku in enumerate(skus):
            db.add(models.DimProduct(
                sku_id=sku, product_name=f"Deeplink {sku}", category=cat,
                subcategory="SubA" if i < 3 else "SubB",
                is_private_label=(i % 2 == 0),
                current_price=10.0, cost_price=5.0,
                stock_quantity=10, lifecycle_status="active", shop_id=1,
            ))
        db.commit()

        # Subcategorie server-side, totalen op dezelfde predicaten
        r = client.get("/api/products", params={"category": cat, "subcategory": "SubA", "page_size": 2}, headers=admin_headers).json()
        assert r["total"] == 3
        assert all(p["subcategory"] == "SubA" for p in r["items"])
        # Paginatie over het gefilterde resultaat
        r2 = client.get("/api/products", params={"category": cat, "subcategory": "SubA", "page_size": 2, "page": 2}, headers=admin_headers).json()
        assert len(r["items"]) + len(r2["items"]) == 3

        # Huismerk server-side
        r3 = client.get("/api/products", params={"category": cat, "is_private_label": True}, headers=admin_headers).json()
        assert r3["total"] == 2
        assert all(p["is_private_label"] for p in r3["items"])

        # Combinatie subcategorie + huismerk
        r4 = client.get("/api/products", params={"category": cat, "subcategory": "SubA", "is_private_label": True}, headers=admin_headers).json()
        assert r4["total"] == 2
        assert {p["sku_id"] for p in r4["items"]} == {skus[0], skus[2]}
    finally:
        db.query(models.DimProduct).filter(models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
        db.commit()

def test_build_category_decision_mix_shift_requires_private_label(client, db):
    """Mix-shift scenario alleen wanneer er huismerk-SKU's naast A-merken staan."""
    cat = f"UnitCat-PL-{uuid.uuid4().hex[:6]}"

    def make_products(pl_flags):
        rows = []
        for flag in pl_flags:
            sku = f"TDEC-PL-{uuid.uuid4().hex[:6]}"
            p = models.DimProduct(
                sku_id=sku, product_name=f"PL {sku}", category=cat,
                current_price=12.0, cost_price=6.0, min_price=9.0, max_price=16.0,
                stock_quantity=30, lifecycle_status="active", shop_id=1,
                is_private_label=flag,
            )
            db.add(p)
            db.flush()
            db.add(models.FactSalesDaily(
                sku_id=sku, date=date.today(), shop_id=1,
                units_sold=2, revenue=24.0, margin=12.0, margin_pct=50.0,
            ))
            rows.append(p)
        return rows

    def scenario_types(decision):
        return {
            s.scenario_type
            for s in db.query(models.DecisionScenario).filter(
                models.DecisionScenario.decision_id == decision.id
            ).all()
        }

    try:
        # Mix van huismerk + A-merk → mix-shift scenario aanwezig
        d1, _ = decision_engine._build_category_decision(
            db, date.today(), 1, cat, [], make_products([True, False])
        )
        assert "house_brand_action" in scenario_types(d1)
        db.rollback()

        # Alleen A-merken → geen mix-shift, wel expliciete gap
        d2, _ = decision_engine._build_category_decision(
            db, date.today(), 1, cat, [], make_products([False, False])
        )
        assert "house_brand_action" not in scenario_types(d2)
        assert any("huismerk" in g for g in d2.data_gaps)
    finally:
        db.rollback()

def test_run_decision_engine_category_without_signals_gets_decision(client, admin_headers, db):
    """Categorie met producten maar zonder actieve signalen krijgt tóch een
    beslissing (baseline) — het dashboard blijft niet stilletjes leeg."""
    cat = f"TestCat-NoSig-{uuid.uuid4().hex[:6]}"
    sku = f"TDEC-NSG-{uuid.uuid4().hex[:6]}"
    other = models.DimShop(shop_code=f"tshop-{uuid.uuid4().hex[:6]}", name="No-signal shop")
    db.add(other)
    db.commit()
    try:
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"Nosig {sku}", category=cat,
            current_price=15.0, cost_price=8.0, min_price=10.0, max_price=20.0,
            stock_quantity=50, lifecycle_status="active", shop_id=other.id,
        ))
        # Bewust géén signalen; ook geen verkoop → expliciete data_gaps
        db.commit()

        result = run_decision_engine(db, shop_id=other.id)
        assert result["decisions_created"] >= 1

        cat_decisions = db.query(models.Decision).filter(
            models.Decision.shop_id == other.id,
            models.Decision.entity_type == "category",
            models.Decision.entity_id == cat,
        ).all()
        assert len(cat_decisions) == 1, "Categorie zonder signalen moet een baseline-beslissing krijgen"
        d = cat_decisions[0]
        assert d.recommended_scenario_id is not None
        assert d.signal_ids == []
        assert any("data unavailable" in g for g in (d.data_gaps or []))
    finally:
        _cleanup(db, [sku], extra_shop_id=other.id)
def test_build_category_decision_no_sales_fills_data_gaps(client, db):
    """Geen verkoophistorie → beslissing mét expliciete data_gaps, impactvelden None."""
    cat = f"UnitCat-NS-{uuid.uuid4().hex[:6]}"
    sku = f"TDEC-UNS-{uuid.uuid4().hex[:6]}"
    try:
        p = models.DimProduct(
            sku_id=sku, product_name=f"Nosales {sku}", category=cat,
            current_price=10.0, cost_price=5.0, min_price=7.0, max_price=14.0,
            stock_quantity=20, lifecycle_status="active", shop_id=1,
        )
        db.add(p)
        db.flush()

        decision, n_gaps = decision_engine._build_category_decision(
            db, date.today(), 1, cat, [], [p]
        )
        assert decision is not None
        assert n_gaps >= 1
        assert any("verkoophistorie" in g for g in decision.data_gaps)
        assert any("data unavailable" in g for g in decision.data_gaps)
        # Impactcijfers zijn expliciet onbekend, niet stilletjes 0
        promo = db.query(models.DecisionScenario).filter(
            models.DecisionScenario.decision_id == decision.id,
            models.DecisionScenario.scenario_type == "promotion",
        ).one()
        assert promo.expected_units is None
        assert promo.expected_revenue is None
        assert promo.expected_margin is None
    finally:
        db.rollback()

def test_run_decision_engine_counts_category_decisions(client, admin_headers, db):
    """run_decision_engine pikt categorieën op uit SKU-signalen en telt ze in de return."""
    cat = f"TestCat-RC-{uuid.uuid4().hex[:6]}"
    sku = f"TDEC-RC-{uuid.uuid4().hex[:6]}"
    other = models.DimShop(shop_code=f"tshop-{uuid.uuid4().hex[:6]}", name="Count shop")
    db.add(other)
    db.commit()
    try:
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"Count {sku}", category=cat,
            current_price=15.0, cost_price=8.0, min_price=10.0, max_price=20.0,
            stock_quantity=50, lifecycle_status="active", shop_id=other.id,
        ))
        for i in range(10):
            db.add(models.FactSalesDaily(
                sku_id=sku, date=date.today() - timedelta(days=i), shop_id=other.id,
                units_sold=3, revenue=45.0, margin=21.0, margin_pct=46.7,
            ))
        _seed_signal(db, sku, shop_id=other.id)
        db.commit()

        # Geïsoleerde shop: exact 1 SKU- en 1 categoriebeslissing verwacht
        result = run_decision_engine(db, shop_id=other.id)
        assert result["decisions_created"] == 2
        cat_decisions = db.query(models.Decision).filter(
            models.Decision.shop_id == other.id,
            models.Decision.entity_type == "category",
        ).all()
        assert len(cat_decisions) == 1
        assert cat_decisions[0].entity_id == cat
    finally:
        _cleanup(db, [sku], extra_shop_id=other.id)
