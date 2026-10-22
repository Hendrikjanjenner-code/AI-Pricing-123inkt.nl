"""Isolated HTTP workflow. Run --noconftest: only dedicated in-memory SQLite is used."""
import sys
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routes import channelmanager as api
from models import DimShop, AuditLog, User
from channel_models import ChannelSnapshot
from services.channelmanager import calculate, ChannelConfig

USER = SimpleNamespace(id=1, username="manager", role="pricing_manager", is_active=True)
CONFIG = {"currency": "EUR", "price_basis": "gross", "vat_rate": "0.21",
          "rule": {"kind": "fixed", "value": "-1"}, "min_margin": "0.1"}
BASIS = {"currency": "EUR", "price_basis": "gross", "vat_rate": "0.21", "cost_basis": "net",
         "provenance": "PriceShape_unverified", "notes": "explicit reference import",
         "rows": [{"sku": "reference-1", "name": "=unsafe", "category": "Print",
                   "base_price": "12.10", "cost": "5", "current_price": "12.10"}]}


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    for table in (DimShop.__table__, AuditLog.__table__, ChannelSnapshot.__table__):
        table.create(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([DimShop(id=i, shop_code=str(i), name=str(i)) for i in (1, 2, 3)])
        db.commit()
    monkeypatch.setattr(api, "effective_permissions", lambda db, u: {"pricing.view", "pricing.propose", "pricing.approve"})
    monkeypatch.setattr(api, "user_allowed_shop_ids", lambda db, u: {1, 2})
    app = FastAPI()
    app.include_router(api.router)
    def session():
        with factory() as db:
            yield db
    app.dependency_overrides[api.get_db] = session
    app.dependency_overrides[api.get_current_user] = lambda: USER
    with TestClient(app) as c:
        yield c
    engine.dispose()


def post(client, path, body=None, expected=200):
    response = client.post("/api/channelmanager/" + path, json=body)
    assert response.status_code == expected, response.text
    return response.json()


def setup(client, config=None):
    cfg = post(client, "1/config", {"expected_revision": 0, "notes": "review", "config": config or CONFIG})
    base = post(client, "2/basis", BASIS)
    post(client, f"2/basis/{base['id']}/approve", {"notes": "human approved"})
    calc = post(client, "1/calculate", {"source_shop_id": 2, "basis_id": base["id"]})
    return cfg, base, calc


def test_full_http_roundtrip(client):
    config = {**CONFIG, "export_columns": {"sku": "sku", "price": "target_price", "name": "name"}}
    cfg, base, calc = setup(client, config)
    assert calc["data"]["rows"][0]["target_price"] == "11.10"
    assert calc["data"]["blocked_rows"] == 0
    post(client, f"1/calculations/{calc['id']}/approve", {"notes": "approved"})
    exported = post(client, f"1/calculations/{calc['id']}/export", {"notes": "export approved snapshot"})
    again = post(client, f"1/calculations/{calc['id']}/export", {"notes": "retry"})
    assert exported["id"] == again["id"]
    assert "'=unsafe" in exported["data"]["csv"]
    download = client.get(f"/api/channelmanager/1/exports/{exported['id']}/download")
    assert download.text == exported["data"]["csv"]
    assert not exported["data"]["processed"]
    settings = {"mapping": {"sku": "SKU", "actual_price": "Price"}, "delimiter": ";", "decimal": ",",
                "currency": "EUR", "price_basis": "gross", "vat_rate": ".21"}
    def upload(text):
        return client.post(f"/api/channelmanager/1/exports/{exported['id']}/readback",
            data={"settings": json.dumps(settings)}, files={"file": ("readback.csv", text, "text/csv")})
    response = upload("SKU;Price\nreference-1;11,10\n")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["processed"]
    partial = upload("SKU;Price\nreference-1;11,10\nreference-1;11,10\nother;2,00\n").json()
    assert not partial["data"]["processed"] and partial["data"]["duplicates"] == ["reference-1"]
    history = client.get("/api/channelmanager/1/history?kind=readback&limit=1").json()
    assert history["has_more"]


def test_stale_and_scopes(client):
    cfg, base, calc = setup(client)
    assert client.get(f"/api/channelmanager/3/records/{calc['id']}").status_code == 404
    assert client.get(f"/api/channelmanager/2/records/{calc['id']}").status_code == 404
    post(client, "1/calculate", {"source_shop_id": 3, "basis_id": base["id"]}, 404)
    post(client, f"1/calculations/{calc['id']}/approve", {"notes": "ok"})
    post(client, "1/config", {"expected_revision": 1, "notes": "new", "config": CONFIG})
    post(client, f"1/calculations/{calc['id']}/export", {"notes": "stale"}, 409)
    assert client.get("/api/channelmanager/1/history?kind=export").json()["items"] == []
    post(client, "1/config", {"expected_revision": 1, "notes": "stale", "config": CONFIG}, 409)
    newer = post(client, "2/basis", BASIS)
    post(client, f"2/basis/{newer['id']}/approve", {"notes": "new base"})
    post(client, "1/calculate", {"source_shop_id": 2, "basis_id": base["id"]}, 409)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "1e1000", "garbage", "1e-100000"])
def test_invalid_input(client, value):
    data = {**BASIS, "rows": [{**BASIS["rows"][0], "base_price": value}]}
    post(client, "1/basis", data, 422)


def test_validation_and_csv(client):
    post(client, "1/basis", {**BASIS, "rows": BASIS["rows"] * 2}, 422)
    post(client, "1/basis", {**BASIS, "cost_basis": "gross"}, 422)
    post(client, "1/basis", {**BASIS, "currency": None}, 422)
    post(client, "1/config", {"expected_revision": 0, "notes": "x", "config": {**CONFIG, "evil": 1}}, 422)
    settings = {k: v for k, v in BASIS.items() if k != "rows"}
    settings.update({"mapping": {"sku": "ID", "base_price": "Price"}, "delimiter": ";", "decimal": ","})
    result = client.post("/api/channelmanager/1/basis-csv", data={"settings": json.dumps(settings)},
                         files={"file": ("base.csv", "ID;Price\nREF;12,10\n", "text/csv")})
    assert result.status_code == 200, result.text
    assert result.json()["data"]["rows"][0]["cost"] is None


def test_rules_vat_margins_rounding():
    basis = api.BasisInput.model_validate(BASIS).model_dump()
    config = ChannelConfig.model_validate({**CONFIG, "price_basis": "net", "increment": ".05",
        "rule": {"kind": "percentage", "value": "10"},
        "category_overrides": {"Print": {"kind": "fixed", "value": ".03"}},
        "sku_overrides": {"reference-1": {"kind": "fixed", "value": ".08"}}}).model_dump()
    row = calculate(basis, config)[0]
    assert row["target_price"] == "10.10" and row["rule_source"] == "sku"
    del config["sku_overrides"]["reference-1"]
    assert calculate(basis, config)[0]["target_price"] == "10.05"
    basis["rows"][0]["cost"] = None
    assert calculate(basis, config)[0]["errors"]
    config["min_margin"] = None
    assert not calculate(basis, config)[0]["errors"]
    config["max_change_absolute"] = ".01"
    assert calculate(basis, config)[0]["errors"]
    config["currency"] = "USD"
    with pytest.raises(ValueError, match="Currency mismatch"):
        calculate(basis, config)


def test_schedule_unique_source_and_failure(client):
    setup(client, {**CONFIG, "schedule_source_shop_id": 2, "schedule_enabled": True})
    first = post(client, "1/run")
    assert first["status"] == "success"
    assert first["data"]["source_shop_id"] == 2
    assert post(client, "1/run")["id"] == first["id"]
    failure = post(client, "2/run")
    assert failure["status"] == "failed" and failure["data"]["error"]
    assert post(client, "2/run")["id"] == failure["id"]


def test_permissions(client, monkeypatch):
    monkeypatch.setattr(api, "effective_permissions", lambda db, u: {"pricing.view"})
    post(client, "1/basis", BASIS, 403)
    post(client, "1/run", expected=403)
    assert client.get("/api/channelmanager/1/overview").json()["can_export"] is False


def test_source_revocation_and_margin_block(client, monkeypatch):
    _, _, calc = setup(client, {**CONFIG, "min_margin": ".9"})
    assert calc["data"]["blocked_rows"] == 1 and calc["data"]["csv_preview"] is None
    post(client, f"1/calculations/{calc['id']}/approve", {"notes": "blocked"}, 422)
    monkeypatch.setattr(api, "user_allowed_shop_ids", lambda db, u: {1})
    assert client.get(f"/api/channelmanager/1/records/{calc['id']}").status_code == 404
    post(client, "1/config", {"expected_revision": 1, "notes": "forbidden source",
                            "config": {**CONFIG, "schedule_source_shop_id": 2}}, 404)


def test_new_basis_blocks_approval_and_export(client):
    _, _, calc = setup(client)
    new_basis = post(client, "2/basis", BASIS)
    post(client, f"2/basis/{new_basis['id']}/approve", {"notes": "new"})
    post(client, f"1/calculations/{calc['id']}/approve", {"notes": "old snapshot"}, 409)
    post(client, f"1/calculations/{calc['id']}/export", {"notes": "old snapshot"}, 409)


def test_cross_shop_current_is_not_destination_actual(client):
    _, _, calc = setup(client, {**CONFIG, "max_change_absolute": "10"})
    row = calc["data"]["rows"][0]
    assert row["source_current_price"] == "12.10"
    assert row["current_price"] is None and row["current_delta"] is None
    assert row["errors"] == ["Missing current price or absolute change guard exceeded"]
    assert calc["data"]["cost_provenance"]["source_shop_id"] == 2
    post(client, f"1/calculations/{calc['id']}/approve", {"notes": "missing actual"}, 422)


def test_scheduler_reports_disabled_in_tests(client):
    scheduler = client.get("/api/channelmanager/1/overview").json()["scheduler"]
    assert scheduler["disabled"] and not scheduler["available"]
    assert scheduler["reason"] == "disabled_by_environment_or_tests"


@pytest.fixture
def postgres_client(monkeypatch):
    """Random schema in independently guarded TEST database, never app database."""
    import os
    from urllib.parse import urlsplit, parse_qsl, urlencode
    from psycopg2.extensions import parse_dsn
    from uuid import uuid4
    from sqlalchemy import text
    original = os.environ.get("APP_DATABASE_URL_ORIGINAL") or os.environ["DATABASE_URL"]
    app_name = parse_dsn(original)["dbname"]
    parts = urlsplit(original)
    test_url = os.environ["DATABASE_URL"] if os.environ.get("APP_DATABASE_URL_ORIGINAL") else (
        os.environ.get("TEST_DATABASE_URL") or parts._replace(path="/" + app_name + "_test",
            query=urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() != "dbname"])).geturl())
    assert parse_dsn(test_url)["dbname"] != app_name
    assert "service" not in parse_dsn(test_url)
    admin = create_engine(test_url)
    schema = "channelmanager_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(test_url, connect_args={
        "options": f"-c search_path={schema} -c statement_timeout=10000"})
    try:
        for table in (DimShop.__table__, AuditLog.__table__, ChannelSnapshot.__table__, User.__table__):
            table.create(engine)
        factory = sessionmaker(bind=engine)
        with factory() as db:
            db.add_all([DimShop(id=i, shop_code=str(i), name=str(i)) for i in (1, 2)])
            db.add(User(id=1, username="manager", email="isolated@example.invalid",
                        hashed_password="not-a-login", role="pricing_manager"))
            db.commit()
        monkeypatch.setattr(api, "effective_permissions", lambda db, u: {"pricing.view", "pricing.propose", "pricing.approve"})
        monkeypatch.setattr(api, "user_allowed_shop_ids", lambda db, u: {1, 2})
        app = FastAPI()
        app.include_router(api.router)
        def session():
            with factory() as db:
                yield db
        app.dependency_overrides[api.get_db] = session
        app.dependency_overrides[api.get_current_user] = lambda: USER
        with TestClient(app) as client:
            yield client, factory
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_concurrent_approval_export(postgres_client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    client, factory = postgres_client
    _, _, calc = setup(client)
    def pair(path):
        barrier = Barrier(2)
        def request(_):
            barrier.wait(timeout=10)
            return client.post("/api/channelmanager/" + path, json={"notes": "concurrent request"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(request, range(2)))
    approvals = pair(f"1/calculations/{calc['id']}/approve")
    assert sorted(r.status_code for r in approvals) == [200, 409]
    exports = pair(f"1/calculations/{calc['id']}/export")
    assert [r.status_code for r in exports] == [200, 200]
    assert exports[0].json()["id"] == exports[1].json()["id"]
    with factory() as db:
        assert db.query(ChannelSnapshot).filter_by(kind="export").count() == 1
        assert db.query(AuditLog).filter_by(action="approve_calculation").count() == 1
        assert db.query(AuditLog).filter_by(action="export").count() == 1


@pytest.mark.parametrize("operation", ["approve", "export"])
@pytest.mark.parametrize("changed", ["config", "basis"])
def test_postgres_stale_write_race(postgres_client, monkeypatch, operation, changed):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    client, factory = postgres_client
    _, base, calc = setup(client)
    if operation == "export":
        post(client, f"1/calculations/{calc['id']}/approve", {"notes": "before race"})
    entered = Event()
    original_lock = api.lock
    with factory() as writer:
        # Hold the exact parent lock used by config / basis approval while the
        # HTTP approval/export request has already loaded its old calculation.
        original_lock(writer, 1 if changed == "config" else 2)
        if changed == "config":
            api.add(writer, USER, 1, "config", {"config": ChannelConfig.model_validate(CONFIG).model_dump()}, "active")
        else:
            api.add(writer, USER, 2, "basis", api.BasisInput.model_validate(BASIS).model_dump(), "approved")
        def observed_lock(db, *shops):
            if db is not writer:
                entered.set()
            return original_lock(db, *shops)
        monkeypatch.setattr(api, "lock", observed_lock)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.post, f"/api/channelmanager/1/calculations/{calc['id']}/{operation}",
                                 json={"notes": "racing with committed new version"})
            assert entered.wait(timeout=10)
            writer.commit()
            response = future.result(timeout=15)
    assert response.status_code == 409, response.text
    with factory() as db:
        assert db.query(ChannelSnapshot).filter_by(kind="export").count() == 0
        if operation == "approve":
            assert db.get(ChannelSnapshot, calc["id"]).status == "preview"


def test_postgres_scheduler_tick_opt_in_claims(postgres_client, monkeypatch):
    import scheduled_channelmanager as scheduler
    client, factory = postgres_client
    monkeypatch.setattr(scheduler, "SessionLocal", factory)
    setup(client, {**CONFIG, "schedule_source_shop_id": 2, "schedule_hour_utc": 0})
    scheduler.tick()
    with factory() as db:
        assert db.query(ChannelSnapshot).filter_by(kind="run").count() == 0
    post(client, "1/config", {"expected_revision": 1, "notes": "opt in",
        "config": {**CONFIG, "schedule_source_shop_id": 2, "schedule_hour_utc": 0, "schedule_enabled": True}})
    scheduler.tick()
    scheduler.tick()
    with factory() as db:
        runs = db.query(ChannelSnapshot).filter_by(kind="run").all()
        assert len(runs) == 1 and runs[0].status == "success"


def test_scheduler_loop_cancels_and_drains(monkeypatch):
    import asyncio
    import scheduled_channelmanager as scheduler
    from threading import Event
    started, finished = Event(), Event()
    def slow_tick(stop):
        started.set()
        assert stop.wait(timeout=5)
        finished.set()
    monkeypatch.setattr(scheduler, "disabled", lambda: False)
    monkeypatch.setattr(scheduler, "tick", slow_tick)
    async def exercise():
        task = asyncio.create_task(scheduler.scheduler_loop())
        assert await asyncio.to_thread(started.wait, 5)
        assert scheduler.scheduler_status()["available"]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert not scheduler.scheduler_status()["running"]
    asyncio.run(exercise())
