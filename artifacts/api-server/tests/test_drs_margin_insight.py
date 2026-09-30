"""Isolated SQLite tests: no app startup, imports, or real model runs."""
import os
import sys
from datetime import date, datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models
from services import margin_insight as mi
from engine.pricing_engine import run_pricing_engine, _drs_price_factor
from engine.strategies import _avg_daily_units


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_test_database_schema():
    # Override shared conftest app startup: these tests own their entire DB.
    yield


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    tables = [models.DimShop, models.DimProduct, models.DrsDailyStage,
              models.ModelRun, models.AuditLog, models.FactSalesDaily,
              models.SalesDailyClaim, models.FactPriceDaily,
              models.FactCompetitorPriceDaily, models.FactInventoryDaily,
              models.FactBasketAffinity, models.MapSubstitution,
              models.FactPricingRecommendationDaily]
    for model in tables:
        model.__table__.create(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    session.add_all([models.DimShop(id=i, shop_code=str(i), name=str(i)) for i in (1, 2)])
    session.add_all([models.DimProduct(sku_id=str(i), shop_id=i, product_name="Test",
        import_source="DRS", cost_price=5, current_price=10) for i in (1, 2)])
    session.add(models.DrsDailyStage(id="confirmed", shop_id=1, created_by="test",
        created_at=datetime(2026, 10, 1), expires_at=datetime(2026, 11, 1), status="confirmed",
        preview={"period_start": "2026-08-30", "period_end": "2026-09-30"},
        result={"confirmed_at": "2026-10-01T12:00:00"}))
    for i in range(32):
        session.add(models.SalesDailyClaim(shop_id=1, sku_id="1",
            date=date(2026, 8, 30) + timedelta(days=i), source="DRS_DAILY"))
    session.add(models.FactSalesDaily(shop_id=1, sku_id="1", date=date(2026, 8, 30),
        units_sold=32, revenue=320, revenue_incl_vat=387.2, source="DRS_DAILY"))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def make_run(db):
    source = mi.source_status(db, 1)
    run = models.ModelRun(status="running", model_version="test-drs",
        run_metadata={"kind": mi.RUN_KIND, "shop_id": 1, **source})
    db.add(run)
    db.commit()
    return run


def test_period_denominator_and_vat(db):
    import pandas as pd
    sales = pd.DataFrame([{"date": date(2026, 8, 30), "units_sold": 32,
                           "revenue": 320, "revenue_incl_vat": 387.2}])
    assert _avg_daily_units({"sales": sales, "volume_days": 32}) == 1
    assert _drs_price_factor(SimpleNamespace(import_source="priceshape"), sales) == pytest.approx(1.21)
    assert _drs_price_factor(SimpleNamespace(import_source="unknown"), sales) is None


def test_scoped_atomic_run_and_reload(db):
    foreign = models.FactPricingRecommendationDaily(shop_id=2, sku_id="2",
        date=date.today(), approval_status="pending", expected_margin_uplift=999)
    db.add(foreign)
    db.commit()
    run = make_run(db)
    mi.execute_recalculation(run.id, 1, sessionmaker(bind=db.bind, autoflush=False))
    db.expire_all()
    result = mi.insight(db, 1)
    assert result["run"]["status"] == "completed"
    assert result["expected"]["status"] == "fresh"
    assert result["expected"]["volume_days"] == 32
    assert result["expected"]["covered_skus"] == 1
    assert result["actual"]["margin"] is None
    assert result["actual"]["missing_cost_rows"] == 1
    assert result["actual"]["comparison_start"] == date(2026, 7, 29)
    assert db.get(models.FactPricingRecommendationDaily, foreign.id).expected_margin_uplift == 999
    assert mi.insight(db, 1, set())["expected"]["margin_uplift"] is None
    db.add(models.DrsDailyStage(id="new", shop_id=1, created_by="test",
        created_at=datetime(2026, 10, 2), expires_at=datetime(2026, 11, 1),
        status="confirmed", preview={"period_start": "2026-08-30", "period_end": "2026-09-30"},
        result={"confirmed_at": "2026-10-02T12:00:00"}))
    db.commit()
    assert mi.insight(db, 1)["expected"]["status"] == "stale"
    assert mi.insight(db, 1)["expected"]["margin_uplift"] is None


def test_human_decisions_preserved_and_zero_volume(db):
    locked = models.FactPricingRecommendationDaily(shop_id=1, sku_id="1",
        date=date.today() - timedelta(days=1), approval_status="pending", override_price=12)
    db.add(locked)
    db.commit()
    assert run_pricing_engine(db, shop_id=1, sales_period=(date(2026, 8, 30),
        date(2026, 9, 30)), model_version="preserve") == (0, 1)
    assert db.get(models.FactPricingRecommendationDaily, locked.id).override_price == 12
    db.delete(locked)
    db.query(models.FactSalesDaily).delete()
    db.commit()
    processed, _ = run_pricing_engine(db, shop_id=1, sales_period=(date(2026, 8, 30),
        date(2026, 9, 30)), model_version="zero")
    assert processed == 1
    rec = db.query(models.FactPricingRecommendationDaily).filter_by(model_version="zero").one()
    assert rec.expected_margin_uplift == 0
    db.rollback()
    db.query(models.SalesDailyClaim).delete()
    db.commit()
    run_pricing_engine(db, shop_id=1, sales_period=(date(2026, 8, 30),
        date(2026, 9, 30)), model_version="missing")
    rec = db.query(models.FactPricingRecommendationDaily).filter_by(model_version="missing").one()
    assert rec.expected_margin_uplift is None


def test_failure_visible_and_rollback(db, monkeypatch):
    import engine.pricing_engine as pe
    run = make_run(db)
    def fail(*args, **kwargs):
        raise RuntimeError("secret must not leak")
    monkeypatch.setattr(pe, "run_pricing_engine", fail)
    mi.execute_recalculation(run.id, 1, sessionmaker(bind=db.bind))
    db.expire_all()
    result = mi.insight(db, 1)
    assert result["run"]["status"] == "failed"
    assert "secret" not in result["run"]["error_message"]
    assert result["expected"]["margin_uplift"] is None


def test_failed_strategy_does_not_delete_previous_advice(db, monkeypatch):
    import engine.pricing_engine as pe
    old = models.FactPricingRecommendationDaily(shop_id=1, sku_id="1",
        date=date.today(), approval_status="pending", expected_margin_uplift=123)
    db.add(old)
    db.commit()
    old_id = old.id
    run = make_run(db)
    monkeypatch.setattr(pe, "_run_strategy", lambda *a: (_ for _ in ()).throw(ValueError("bad strategy")))
    mi.execute_recalculation(run.id, 1, sessionmaker(bind=db.bind, autoflush=False))
    db.expire_all()
    assert db.get(models.FactPricingRecommendationDaily, old_id).expected_margin_uplift == 123
    assert mi.insight(db, 1)["expected"]["margin_uplift"] is None


def test_priceshape_vat_after_guardrails_and_current_cost_unchanged(db):
    from engine.strategies import _estimate_margin_uplift
    product = db.get(models.DimProduct, "1")
    product.import_source, product.current_price, product.price_incl_vat = "priceshape", 12.1, 12.1
    db.commit()
    run = make_run(db)
    mi.execute_recalculation(run.id, 1, sessionmaker(bind=db.bind, autoflush=False))
    db.expire_all()
    rec = db.query(models.FactPricingRecommendationDaily).filter_by(shop_id=1).one()
    expected = _estimate_margin_uplift(5, 10, float(rec.recommended_price) / 1.21, 1)
    assert float(rec.expected_margin_uplift) == pytest.approx(expected["expected_margin_uplift"])
    assert db.get(models.DimProduct, "1").cost_price == 5
    assert mi.insight(db, 1)["expected"]["status"] == "fresh"
    db.get(models.DimProduct, "1").cost_price = 6
    db.commit()
    assert mi.insight(db, 1)["expected"]["status"] == "stale"


def test_attempt_states_historical_costs_and_expiry(db):
    db.add(models.DrsDailyStage(id="blocked", shop_id=2, created_by="test",
        expires_at=datetime(2026, 11, 1), status="blocked", preview={}))
    db.commit()
    assert mi.source_status(db, 2)["status"] == "blocked"
    stage = db.get(models.DrsDailyStage, "blocked")
    stage.mapping_result = {"mapped": 2, "sales_written": 0}
    db.commit()
    assert mi.source_status(db, 2)["status"] == "mappings_only"
    row = db.query(models.FactSalesDaily).one()
    row.cost = 160
    db.commit()
    result = mi.insight(db, 1, comparison_start=date(2026, 8, 30), comparison_end=date(2026, 9, 30))
    assert result["actual"]["margin"] == 160
    assert result["actual"]["margin_change"] == 0
    run = make_run(db)
    run.started_at = datetime.utcnow() - timedelta(hours=3)
    db.commit()
    assert mi.latest_run(db, 1).status == "failed"


def test_async_admission_idempotent_and_authorization(db, monkeypatch):
    from fastapi import HTTPException
    from services.product_identity import authorize_shop
    import services.product_identity as identity
    monkeypatch.setattr(identity, "user_allowed_shop_ids", lambda db, user: {1})
    with pytest.raises(HTTPException):
        authorize_shop(db, SimpleNamespace(), 2)
    monkeypatch.setattr(mi.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None))
    first = mi.start_recalculation(db, 1, "test")
    assert first["status"] == "running"
    assert mi.start_recalculation(db, 1, "test")["id"] == first["id"]
    mi.execute_recalculation(first["id"], 1, sessionmaker(bind=db.bind, autoflush=False))
    db.expire_all()
    assert mi.start_recalculation(db, 1, "test")["id"] == first["id"]
    assert mi.run_query(db, 2).count() == 0
    with pytest.raises(HTTPException) as exc:
        mi.start_recalculation(db, 2, "test")
    assert exc.value.status_code == 409


def test_actual_route_repair_confirm_async_margin_journey(tmp_path, monkeypatch):
    """HTTP contract chain in a disposable DB; real worker thread, no main app."""
    import io
    import time
    import openpyxl
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import auth
    import database
    from routes import drs_daily, dashboard
    import services.product_identity as identity

    engine = create_engine(f"sqlite:///{tmp_path / 'journey.sqlite'}",
                           connect_args={"check_same_thread": False})
    tables = [models.DimShop, models.DimProduct, models.DrsDailyStage,
              models.DrsDailyChunk, models.DrsIdentityResolution, models.ProductSourceAlias,
              models.ModelRun, models.AuditLog, models.FactSalesDaily,
              models.SalesDailyClaim, models.FactPriceDaily,
              models.FactCompetitorPriceDaily, models.FactInventoryDaily,
              models.FactBasketAffinity, models.MapSubstitution,
              models.FactPricingRecommendationDaily]
    for model in tables:
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as session:
        session.add(models.DimShop(id=71, shop_code="isolated-journey", name="Journey"))
        session.add_all([models.DimProduct(
            sku_id=sku, shop_id=71, product_name=sku,
            import_source="DRS" if sku == "link-target" else "priceshape",
            product_group="AMB" if sku != "link-target" else "other",
            current_price=10, cost_price=5) for sku in ("link-target", "amb-a", "amb-b")])
        session.add(models.FactPricingRecommendationDaily(
            shop_id=71, sku_id="amb-a", date=date.today() - timedelta(days=1),
            approval_status="approved", override_price=11, approved_by="human"))
        session.commit()
    user = SimpleNamespace(id=1, username="integration-fixture", role="admin")
    app = FastAPI()
    app.include_router(drs_daily.router)
    app.include_router(dashboard.router)
    def request_db():
        with factory() as session:
            yield session
    app.dependency_overrides[database.get_db] = request_db
    app.dependency_overrides[auth.get_current_user] = lambda: user
    for route in app.routes:
        for dependency in getattr(getattr(route, "dependant", None), "dependencies", []):
            if getattr(dependency.call, "__name__", "") == "role_checker":
                app.dependency_overrides[dependency.call] = lambda: user
    monkeypatch.setattr(identity, "user_allowed_shop_ids", lambda db, user: {71})
    monkeypatch.setattr(database, "BackgroundSessionLocal", factory)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "sales"
    ws.append([None] * 4 + ["30/08", None, None, "31/08", None, None, "Totaal"])
    ws.append(["Productcode", "ProductName", "EAN", "OEM"] +
              ["Quantity", "Revenue Incl VAT", "Revenue Excl. VAT"] * 3)
    for code, name in [("LINK", "Linked item"), ("AMB", "Ambiguous item"), ("NEW", "New item")]:
        ws.append([code, name, None, None, 2, 24.2, 20, 1, 12.1, 10, 3, 36.3, 30])
    workbook = io.BytesIO()
    wb.save(workbook)
    workbook.seek(0)
    try:
        with TestClient(app) as client:
            def checked(method, path, expected=200, **kwargs):
                response = getattr(client, method)(path, **kwargs)
                assert response.status_code == expected, response.text
                return response.json()
            base = "/api/uploads/drs-daily"
            preview = checked("post", f"{base}/preview",
                data={"shop_id": 71, "year": 2026, "period_start": "2026-08-30", "period_end": "2026-08-31"},
                files={"file": ("journey.xlsx", workbook.getvalue(),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            assert preview["status"] == "blocked" and preview["error_count"] == 3
            stage = preview["stage_id"]
            unresolved = checked("get", f"{base}/{stage}/unresolved")
            assert unresolved["total"] == 3
            ambiguous = next(r for r in unresolved["items"] if r["code"] == "AMB")
            assert len(ambiguous["candidates"]) == 2
            impact = checked("post", f"{base}/{stage}/resolution-preview", json={"actions": [
                {"row": 3, "action": "link", "sku_id": "link-target"},
                {"row": 4, "action": "link", "sku_id": "amb-a"},
                {"row": 5, "action": "create"}]})
            resolution = {"resolution_id": impact["resolution_id"], "confirm": True}
            repaired = checked("post", f"{base}/{stage}/resolution-confirm", json=resolution)
            assert repaired["products_created"] == 1 and repaired["sales_written"] == 0
            ready = checked("post", f"{base}/{stage}/revalidate")
            assert ready["status"] == "ready" and ready["resolved_error_count"] == 3
            stage = ready["stage_id"]
            confirmed = checked("post", f"{base}/{stage}/confirm", json={"confirm_mapping": True})
            assert confirmed["status"] == "confirmed" and confirmed["inserted"] == 6
            assert checked("post", f"{base}/{stage}/confirm",
                           json={"confirm_mapping": True}) == confirmed
            run = checked("post", "/api/dashboard/margin-recalculate?shop_id=71", expected=202)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                insight = checked("get", "/api/dashboard/margin-insight?shop_id=71")
                if insight["run"]["status"] != "running":
                    break
                time.sleep(.05)
            assert insight["run"]["id"] == run["id"]
            assert insight["run"]["status"] == "completed", insight["run"]
            assert insight["source"]["status"] == "confirmed"
            assert insight["source"]["confirmed_at"]
            assert insight["source"]["sales_rows"] == 6
            assert insight["expected"]["volume_period_start"] == "2026-08-30"
            assert insight["expected"]["volume_period_end"] == "2026-08-31"
            assert insight["expected"]["volume_days"] == 2
            assert insight["expected"]["preserved_decision_skus"] == 1
            assert insight["expected"]["margin_uplift"] is not None
            assert insight["actual"]["period_start"] == "2026-08-30"
            assert insight["actual"]["period_end"] == "2026-08-31"
            assert insight["actual"]["margin"] is None
            assert insight["actual"]["missing_cost_rows"] == 6
            summary = checked("get", "/api/dashboard/summary?shop_id=71")
            assert summary["total_margin_uplift"] == insight["expected"]["margin_uplift"]
            assert checked("post", "/api/dashboard/margin-recalculate?shop_id=71",
                           expected=202)["id"] == run["id"]
            with factory() as session:
                human = session.query(models.FactPricingRecommendationDaily).filter_by(
                    shop_id=71, sku_id="amb-a").one()
                assert human.approval_status == "approved" and human.override_price == 11
                assert session.query(models.FactSalesDaily).count() == 6
    finally:
        engine.dispose()
        (tmp_path / "journey.sqlite").unlink(missing_ok=True)


@pytest.mark.parametrize("status", ["running", "failed", "completed"])
def test_operational_dashboard_independent_of_drs_snapshot(db, monkeypatch, status):
    from routes import dashboard
    import services.product_identity as identity
    monkeypatch.setattr(identity, "user_allowed_shop_ids", lambda db, user: {1})
    R = models.FactPricingRecommendationDaily
    for sku, decision in [("approved", "approved"), ("rejected", "rejected")]:
        db.add(models.DimProduct(sku_id=sku, shop_id=1, product_name=sku,
                                import_source="DRS", current_price=10, cost_price=5))
        db.add(R(sku_id=sku, shop_id=1, date=date.today() - timedelta(days=10),
                 approval_status=decision, strategy_type="HUMAN", confidence_score=.8,
                 recommended_change_pct=1, expected_margin_uplift=999))
    db.add_all([
        R(sku_id="1", shop_id=1, date=date.today(), approval_status="pending",
          strategy_type="REGULAR", confidence_score=.7, recommended_change_pct=2),
        R(sku_id="2", shop_id=2, date=date.today(), approval_status="pending",
          strategy_type="OTHER_SHOP", confidence_score=.7, recommended_change_pct=2)])
    db.commit()
    run = make_run(db)
    if status == "completed":
        mi.execute_recalculation(run.id, 1, sessionmaker(bind=db.bind, autoflush=False))
        db.expire_all()
        assert mi.insight(db, 1)["expected"]["margin_uplift"] is not None
    else:
        run.status = status
        db.commit()
    args = dict(shop_id=1, hierarchy_node_ids=None, brands=None, statuses=None,
                sku_query=None, db=db, current_user=SimpleNamespace(id=1))
    def check_operational():
        summary = dashboard.get_dashboard_summary(**args)
        assert summary["total_recommendations"] == 3
        assert (summary["approved_count"], summary["rejected_count"], summary["pending_count"]) == (1, 1, 1)
        assert sum(row["count"] for row in dashboard.get_recs_by_strategy(**args)) == 3
        assert sum(row["count"] for row in dashboard.get_confidence_distribution(**args)) == 3
        assert sum(row["count"] for row in dashboard.get_price_change_distribution(**args)) == 3
        return summary
    summary = check_operational()
    categories = dashboard.get_margin_by_category(**args)
    if status == "completed":
        assert sum(row["recommendation_count"] for row in categories) == 1
        assert sum(row["margin_uplift"] for row in categories) == summary["total_margin_uplift"]
        # Real existing engine pathway, without DRS-period/version arguments:
        # pending advice is replaced while earlier human decisions survive.
        run_pricing_engine(db, shop_id=1)
        db.commit()
        assert db.query(R).filter(R.shop_id == 1, R.model_version == "v1.0.0").count() == 1
        summary = check_operational()
        assert summary["total_margin_uplift"] is None
        assert dashboard.get_margin_by_category(**args) == []
    else:
        assert summary["total_margin_uplift"] is None and categories == []


def test_later_day_regular_snapshot_invalidates_margin_not_operational_counts(db, monkeypatch):
    from routes import dashboard
    import services.product_identity as identity
    monkeypatch.setattr(identity, "user_allowed_shop_ids", lambda db, user: {1})
    run = make_run(db)
    mi.execute_recalculation(run.id, 1, sessionmaker(bind=db.bind, autoflush=False))
    db.expire_all()
    assert mi.insight(db, 1)["expected"]["status"] == "fresh"
    # Next-day regular runs retain older advice; no deleted IDs to detect.
    db.add(models.FactPricingRecommendationDaily(
        shop_id=1, sku_id="1", date=date.today() + timedelta(days=1),
        model_version="v1.0.0", approval_status="pending", strategy_type="REGULAR",
        expected_margin_uplift=800, confidence_score=.9, recommended_change_pct=2))
    db.commit()
    args = dict(shop_id=1, hierarchy_node_ids=None, brands=None, statuses=None,
                sku_query=None, db=db, current_user=SimpleNamespace(id=1))
    assert mi.insight(db, 1)["expected"]["status"] == "stale"
    assert dashboard.get_dashboard_summary(**args)["total_recommendations"] == 2
    assert dashboard.get_dashboard_summary(**args)["total_margin_uplift"] is None
    assert dashboard.get_margin_by_category(**args) == []


@pytest.mark.parametrize("expired_attempt", [False, True])
def test_postgres_concurrent_http_admission_is_exclusive(monkeypatch, expired_attempt):
    """Real PostgreSQL requests/connections, disposable schema in TEST database."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import event, text
    import database
    from routes import dashboard
    import services.product_identity as identity

    # conftest switches DATABASE_URL before importing database. Never permit an
    # ad-hoc invocation against the application DB, even if test setup changes.
    assert os.environ.get("APP_DATABASE_URL_ORIGINAL")
    from conftest import _assert_distinct_databases
    _assert_distinct_databases(os.environ["APP_DATABASE_URL_ORIGINAL"],
                              os.environ["DATABASE_URL"])
    assert database.engine.dialect.name == "postgresql"
    schema = "drs_admission_" + uuid4().hex
    with database.engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(database.engine.url, connect_args={
        "options": f"-c search_path={schema} -c statement_timeout=10000"})
    lock_statements = []
    @event.listens_for(engine, "before_cursor_execute")
    def capture_lock(conn, cursor, statement, parameters, context, executemany):
        if "FROM dim_shop" in statement and "FOR UPDATE" in statement:
            lock_statements.append(statement)
    try:
        for model in (models.DimShop, models.DimProduct, models.DrsDailyStage,
                      models.ModelRun, models.AuditLog, models.FactSalesDaily,
                      models.FactPricingRecommendationDaily):
            model.__table__.create(engine)
        factory = sessionmaker(bind=engine, autoflush=False)
        with factory() as session:
            session.add(models.DimShop(id=71, shop_code="only-test-schema", name="Concurrent"))
            session.add(models.DrsDailyStage(id="confirmed", shop_id=71,
                created_by="fixture", expires_at=datetime.utcnow() + timedelta(days=1),
                status="confirmed", preview={"period_start": "2026-08-30", "period_end": "2026-08-31"},
                result={"confirmed_at": "2026-10-01T12:00:00Z"}))
            if expired_attempt:
                session.add(models.ModelRun(status="running",
                    started_at=datetime.utcnow() - timedelta(hours=3),
                    run_metadata={"kind": mi.RUN_KIND, "shop_id": 71}))
            session.commit()
        app = FastAPI()
        app.include_router(dashboard.router)
        def request_db():
            with factory() as session:
                yield session
        app.dependency_overrides[database.get_db] = request_db
        app.dependency_overrides[dashboard.auth_utils.get_current_user] = lambda: SimpleNamespace(
            id=1, username="concurrency-fixture", role="admin")
        for route in app.routes:
            for dependency in getattr(getattr(route, "dependant", None), "dependencies", []):
                if getattr(dependency.call, "__name__", "") == "role_checker":
                    app.dependency_overrides[dependency.call] = lambda: SimpleNamespace(
                        id=1, username="concurrency-fixture", role="admin")
        monkeypatch.setattr(identity, "user_allowed_shop_ids", lambda db, user: {71})
        launches = []
        class NoWorkThread:
            def __init__(self, **kwargs):
                self.args = kwargs["args"]
            def start(self):
                launches.append(self.args)
        # Replace only this module's reference, not threading.Thread globally:
        # HTTP clients and ThreadPoolExecutor continue using real threads.
        monkeypatch.setattr(mi, "threading", SimpleNamespace(Thread=NoWorkThread))
        original_source = mi.source_status
        overlap, active, maximum_active = threading.Lock(), 0, 0
        def slow_source(*args):
            nonlocal active, maximum_active
            with overlap:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                time.sleep(.2)  # both requests contend at admission
                return original_source(*args)
            finally:
                with overlap:
                    active -= 1
        monkeypatch.setattr(mi, "source_status", slow_source)
        gate = threading.Barrier(2)
        def request():
            with TestClient(app) as client:
                gate.wait(timeout=5)
                response = client.post("/api/dashboard/margin-recalculate?shop_id=71")
                assert response.status_code == 202, response.text
                return response.json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request) for _ in range(2)]
            responses = [f.result(timeout=15) for f in futures]
        assert responses[0]["id"] == responses[1]["id"]
        assert all(r["status"] == "running" for r in responses)
        assert maximum_active == 1
        assert len(lock_statements) == 2
        assert all(statement.rstrip().endswith("FOR UPDATE") for statement in lock_statements)
        assert len(launches) == 1
        with factory() as session:
            assert mi.run_query(session, 71).filter(models.ModelRun.status == "running").count() == 1
            assert mi.run_query(session, 71).count() == (2 if expired_attempt else 1)
            assert session.query(models.AuditLog).count() == 1
    finally:
        engine.dispose()
        with database.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))