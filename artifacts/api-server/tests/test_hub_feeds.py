"""Isolated Hub feeds checks: no app lifecycle, no live DB or network mutations."""
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import hub_feeds as svc
from services import hub_feeds_storage as storage
from services.cost_priority import Rules, SOURCES
from routes import hub_feeds as api
from feed_models import HubFeedProfile, HubFeedVersion
from models import DimShop, CostPriorityVersion, AuditLog, User

USER = SimpleNamespace(id=41, username="feed-test", role="pricing_manager")
ASSETS = Path(__file__).resolve().parents[3] / "attached_assets"


@pytest.fixture
def store(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for table in (DimShop.__table__, User.__table__, CostPriorityVersion.__table__, AuditLog.__table__,
                  HubFeedProfile.__table__, HubFeedVersion.__table__):
        table.create(engine)
    factory = sessionmaker(bind=engine)
    objects = {}
    def put(data, shop, profile, suffix):
        key = f"{shop}/{profile}/{len(objects)}.{suffix}"
        objects[key] = data
        return key
    monkeypatch.setattr(storage, "put", put)
    monkeypatch.setattr(storage, "get", lambda key: objects[key])
    monkeypatch.setattr(storage, "delete", lambda key: objects.pop(key))
    def access(db, user, shop, action=None, sensitive=False):
        if shop != 1:
            raise HTTPException(403, "Shop access denied")
    monkeypatch.setattr(api, "access", access)
    with factory() as db:
        db.add_all([DimShop(id=i, shop_code=str(i), name=str(i)) for i in (1, 2)])
        db.add(User(id=USER.id, username=USER.username, email="feed-test@example.invalid",
                    hashed_password="not-a-real-password", role="pricing_manager", is_active=True))
        db.commit()
    yield factory, objects
    engine.dispose()


def cost_config():
    return {"mapping": {"productcode": "Productcode", "type": "Type", "gtin": "GTIN",
                         **{s: s for s in SOURCES}},
            "type_mapping": {"Printer": "Print", "Office": "Other"}, "vat_rate": "9",
            "vat_basis": "exc", "unit_confirmed": True, "complete_snapshot_confirmed": True}


def cost_data():
    return ("Productcode;Type;GTIN;Stockprice;ABCLev;AB;123inkt.nl Marktprijs\r\n"
            "001;Printer;000123;0;12,50;8;20\r\n"
            "001;Printer;;0;12,50;8;20\r\n"
            "001;Printer;;0;12,50;8;20\r\n"
            "002;Office;;0;12;8;20\r\n").encode()


def profile(db, purpose="cost", config=None):
    result = api.create(1, svc.ProfileInput(name="Test", purpose=purpose, config=config or cost_config()), db, USER)
    return db.get(HubFeedProfile, result["id"])


def test_priority_vat_duplicate_rows_and_original_preserved(store):
    factory, objects = store
    with factory() as db:
        p = profile(db)
        original = cost_data()
        v = svc.stage(db, p, original, USER.username)
        assert objects[v.object_key] == original
        assert v.row_count == 4 and v.report["duplicate_rows"] == 1
        records = json.loads(objects[v.records_key])
        data, results = svc.cost_csv(records, p.config, Rules())
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
        assert rows[0] == svc.OUTPUT_HEADERS
        assert rows[1] == ["001", "13,63", "12,50", "Printer", "000123"]
        assert rows[4][1:3] == ["8,72", "8,00"]
        assert len(rows) == 5 and len(results) == 4


def test_inactive_staging_activation_pause_scoped_dedupe_and_stale_config(store):
    factory, objects = store
    with factory() as db:
        p = profile(db)
        v = api.test_stage(db, p, USER.username, cost_data())
        assert not p.active and p.current_version_id is None
        assert svc.stage(db, p, cost_data(), USER.username).id == v["id"]
        p2 = profile(db)
        assert svc.stage(db, p2, cost_data(), USER.username).id != v["id"]
        with pytest.raises(HTTPException) as e:
            api.versions(2, p.id, db, USER)
        assert e.value.status_code == 403
        api.activate(1, p.id, svc.VersionInput(version_id=v["id"]), db, USER)
        assert p.active
        api.pause(1, p.id, db, USER)
        assert not p.active
        with pytest.raises(HTTPException):
            svc.active_records(db, 1, p.id, "cost")
        api.update(1, p.id, svc.ProfileInput(name="Changed", purpose="cost",
                   config=cost_config(), base_revision=1), db, USER)
        with pytest.raises(HTTPException) as e:
            api.activate(1, p.id, svc.VersionInput(version_id=v["id"]), db, USER)
        assert e.value.status_code == 409


def test_missing_not_zero_conflicts_type_mapping_and_formula_escape():
    data = cost_data().replace(b";0;12,50;8;20", b";;12,50;8;20", 1)
    records, report = svc.parse(data, "cost", cost_config())
    assert any("Stockprice missing" in e for e in report["errors"])
    assert any("conflicting" in e for e in report["errors"])
    config = cost_config()
    config["type_mapping"] = {}
    assert svc.parse(cost_data(), "cost", config)[1]["errors"]
    assert svc.safe_cell("=HYPERLINK(\"bad\")").startswith("'=")
    assert svc.safe_cell("000123") == "000123"
    records, report = svc.parse(cost_data().replace(b";0;12,50;8;20", b";0;0;0;0"), "cost", cost_config())
    data, result = svc.cost_csv(records, cost_config(), Rules())
    assert result[0]["selection"]["value"] == "0"


def test_products_price_never_advice_and_missing_advice_configuration():
    data = b"Productcode;Prijs\n001;12,50\n"
    cfg = {"mapping": {"productcode": "Productcode", "price": "Prijs"}, "complete_snapshot_confirmed": True}
    assert not svc.parse(data, "products", cfg)[1]["errors"]
    assert svc.parse(data, "advice", cfg)[1]["errors"]
    cfg["mapping"]["advice"] = "Prijs"  # explicit operator mapping, never inferred automatically
    assert not svc.parse(data, "advice", cfg)[1]["errors"]


def test_output_release_token_pause_and_last_good_snapshot(store):
    factory, objects = store
    with factory() as db:
        p = profile(db)
        staged = api.test_stage(db, p, USER.username, cost_data())
        api.activate(1, p.id, svc.VersionInput(version_id=staged["id"]), db, USER)
        out = profile(db, "cost_output", {"complete_snapshot_confirmed": True})
        body = svc.BuildInput(source_profile_id=p.id, source_version_id=staged["id"])
        v = api.build(1, out.id, body, db, USER)
        assert api.build(1, out.id, body, db, USER)["id"] == v["id"]
        assert not out.active and out.released_version_id is None
        token = api.rotate_token(1, out.id, db, USER)["token"]
        assert token not in json.dumps(svc.profile_json(out), default=str)
        assert out.token_hash != token
        cred = SimpleNamespace(credentials=token)
        with pytest.raises(HTTPException):
            api.feed(1, out.id, db, cred)
        api.activate(1, out.id, svc.VersionInput(version_id=v["id"]), db, USER)
        api.release(1, out.id, svc.VersionInput(version_id=v["id"]), db, USER)
        assert api.feed(1, out.id, db, cred).body == objects[db.get(HubFeedVersion, v["id"]).object_key]
        api.pause(1, out.id, db, USER)
        with pytest.raises(HTTPException) as e:
            api.feed(1, out.id, db, cred)
        assert e.value.status_code == 403
        # Empty staging does not replace last valid active source.
        bad = api.test_stage(db, p, USER.username, b"Productcode;Type;GTIN\n")
        assert bad["status"] == "invalid" and p.current_version_id == staged["id"]


def test_approval_only_feed_actions_match_middleware_and_real_access(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from routes import cost_priority
    from authz import required_action_permission, required_permission_for_path

    factory, _ = store
    with factory() as db:
        source = profile(db)
        staged = api.test_stage(db, source, USER.username, cost_data())
        api.activate(1, source.id, svc.VersionInput(version_id=staged["id"]), db, USER)
        output = profile(db, "cost_output", {"complete_snapshot_confirmed": True})
        version = api.build(1, output.id, svc.BuildInput(
            source_profile_id=source.id, source_version_id=staged["id"]), db, USER)
        output_id = output.id
    permissions = {"pricing.view", "pricing.approve"}
    monkeypatch.setattr(api, "access", cost_priority.access)
    monkeypatch.setattr(cost_priority, "effective_permissions", lambda db, user: permissions)
    monkeypatch.setattr(cost_priority, "user_allowed_shop_ids", lambda db, user: {1})
    app = FastAPI()
    app.include_router(api.router)
    def session():
        with factory() as db:
            yield db
    app.dependency_overrides[api.get_db] = session
    app.dependency_overrides[api.get_current_user] = lambda: USER
    @app.middleware("http")
    async def permission_gate(request, call_next):
        required = (required_action_permission(request.url.path, request.method)
                    or required_permission_for_path(request.url.path))
        if required and required not in permissions:
            return JSONResponse({"required_permission": required}, status_code=403)
        return await call_next(request)
    base = f"/api/hub-feeds/1/profiles/{output_id}"
    with TestClient(app) as client:
        for action in ("activate", "release", "token"):
            response = client.post(base + "/" + action, json={"version_id": version["id"]})
            assert response.status_code == 200, response.text
        # Pause is deliberately a proposal in the actual handler, not approval.
        response = client.post(base + "/pause")
        assert response.status_code == 403
        assert response.json()["required_permission"] == "pricing.propose"
        assert client.post(base + "/build", json={}).status_code == 403
        permissions.clear()
        permissions.update({"pricing.view", "pricing.propose"})
        for action in ("activate", "release", "token"):
            response = client.post(base + "/" + action, json={"version_id": version["id"]})
            assert response.status_code == 403
            assert response.json()["required_permission"] == "pricing.approve"
        assert client.post(base + "/pause").status_code == 200
        assert client.get(f"/api/hub-feeds/2/profiles/{output_id}/versions").status_code == 403


@pytest.mark.parametrize("path,permission", [
    ("hub-feeds/1/profiles/2/activate", "pricing.approve"),
    ("hub-feeds/1/profiles/2/release", "pricing.approve"),
    ("hub-feeds/1/profiles/2/token", "pricing.approve"),
    ("hub-feeds/1/profiles/2/pause", "pricing.propose"),
    ("hub-feeds/1/profiles/2/test", "pricing.propose"),
    ("hub-feeds/1/profiles/2/upload", "pricing.propose"),
    ("hub-feeds/1/profiles/2/build", "pricing.propose"),
    ("channelmanager/printer/1/advice", "pricing.approve"),
    ("channelmanager/printer/1/approve/2", "pricing.approve"),
    ("channelmanager/printer/1/export/2", "pricing.approve"),
    ("channelmanager/printer/1/readback/2", "pricing.approve"),
    ("channelmanager/printer/1/config", "pricing.propose"),
    ("channelmanager/printer/1/pre", "pricing.propose"),
    ("channelmanager/printer/1/calculate", "pricing.propose"),
    ("channelmanager/1/basis/2/approve", "pricing.approve"),
    ("channelmanager/1/calculations/2/approve", "pricing.approve"),
    ("channelmanager/1/calculations/2/export", "pricing.approve"),
    ("channelmanager/1/exports/2/readback", "pricing.propose"),
    ("channelmanager/1/config", "pricing.propose"),
    ("channelmanager/1/basis", "pricing.propose"),
    ("channelmanager/1/basis-csv", "pricing.propose"),
    ("channelmanager/1/calculate", "pricing.propose"),
    ("channelmanager/1/run", "pricing.propose"),
    # Do not infer approval from incidental path text or extra segments.
    ("hub-feeds/1/profiles/2/release/extra", "pricing.propose"),
    ("channelmanager/printer/1/export", "pricing.propose"),
    ("channelmanager/printer/1/approve/2/extra", "pricing.propose"),
])
def test_workflow_action_permission_registry(path, permission):
    from authz import required_action_permission
    assert required_action_permission("/api/" + path, "POST") == permission
    assert required_action_permission("/api/" + path + "?note=approve", "post") == permission
    assert required_action_permission("/api/" + path, "GET") is None


def test_storage_unconfigured_explicit_failure(monkeypatch):
    monkeypatch.delenv("PRIVATE_OBJECT_DIR", raising=False)
    with pytest.raises(HTTPException) as e:
        storage.location()
    assert e.value.status_code == 503


def test_active_advice_bridge_exact_version_and_shop_scope(store):
    factory, objects = store
    with factory() as db:
        cfg = {"mapping": {"productcode": "SKU", "advice": "Recommended", "old_price": "Old"},
               "complete_snapshot_confirmed": True}
        p = profile(db, "advice", cfg)
        first = api.test_stage(db, p, USER.username, b"SKU;Recommended;Old\n0001;19,99;20\n")
        api.activate(1, p.id, svc.VersionInput(version_id=first["id"]), db, USER)
        version, records = svc.active_records(db, 1, p.id, version_id=first["id"])
        assert version.id == first["id"] and records[0]["advice"] == "19.99"
        assert records[0]["productcode"] == "0001" and records[0]["old_price"] == "20"
        with pytest.raises(HTTPException):
            svc.active_records(db, 2, p.id, version_id=first["id"])
        second = api.test_stage(db, p, USER.username, b"SKU;Recommended;Old\n0001;21;20\n")
        assert p.current_version_id == first["id"]  # even active test remains staging
        api.activate(1, p.id, svc.VersionInput(version_id=second["id"]), db, USER)
        with pytest.raises(HTTPException):
            svc.active_records(db, 1, p.id, version_id=first["id"])


def test_rotated_token_revokes_old_and_output_keeps_explicit_release(store):
    factory, objects = store
    with factory() as db:
        p = profile(db)
        first = api.test_stage(db, p, USER.username, cost_data())
        api.activate(1, p.id, svc.VersionInput(version_id=first["id"]), db, USER)
        out = profile(db, "cost_output", {"complete_snapshot_confirmed": True})
        v = api.build(1, out.id, svc.BuildInput(source_profile_id=p.id, source_version_id=first["id"]), db, USER)
        api.activate(1, out.id, svc.VersionInput(version_id=v["id"]), db, USER)
        api.release(1, out.id, svc.VersionInput(version_id=v["id"]), db, USER)
        token = api.rotate_token(1, out.id, db, USER)["token"]
        out.token_rotated_at = datetime.utcnow() - timedelta(minutes=2)
        new_token = api.rotate_token(1, out.id, db, USER)["token"]
        with pytest.raises(HTTPException) as e:
            api.feed(1, out.id, db, SimpleNamespace(credentials=token))
        assert e.value.status_code == 401
        second = api.test_stage(db, p, USER.username, cost_data().replace(b"12,50", b"15,50"))
        api.activate(1, p.id, svc.VersionInput(version_id=second["id"]), db, USER)
        response = api.feed(1, out.id, db, SimpleNamespace(credentials=new_token))
        assert response.body == objects[db.get(HubFeedVersion, v["id"]).object_key]
        assert out.released_version_id == v["id"]  # no automatic publication of changed costs


def test_network_test_redacts_errors_and_rejects_http_private_url(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "isolated-test-secret-not-production")
    for url in ("http://example.com/feed", "https://127.0.0.1/feed", "https://user:pass@example.com/feed"):
        with pytest.raises(HTTPException):
            svc.config_input({"url": url})
    monkeypatch.setattr(svc, "validate_external_url", lambda url: None)
    config, encrypted = svc.config_input({"url": "https://example.com/feed?secret=never-display",
                                           "bearer_token": "test-only-secret"})
    assert "never-display" not in encrypted and "url" not in config
    class BadClient:
        def __init__(self, **kwargs):
            raise RuntimeError("https://example.com/feed?secret=never-display")
    monkeypatch.setattr(svc.httpx, "Client", BadClient)
    with pytest.raises(HTTPException) as e:
        svc.fetch(SimpleNamespace(credentials=encrypted))
    assert "never-display" not in str(e.value.detail)


def test_scheduler_inactive_no_fetch_and_persistent_failed_snapshot(store, monkeypatch):
    import scheduled_hub_feeds as scheduler
    factory, objects = store
    monkeypatch.setattr(scheduler, "BackgroundSessionLocal", factory)
    monkeypatch.setattr(svc, "fetch", lambda p: pytest.fail("inactive profile must never fetch"))
    with factory() as db:
        p = profile(db)
        p.credentials = "encrypted-not-used"
        db.commit()
    scheduler.tick()
    with factory() as db:
        p = db.query(HubFeedProfile).first()
        assert p.last_attempt is None and not p.active


def test_scheduler_active_import_restart_idempotency_and_failure_keeps_good(store, monkeypatch):
    import scheduled_hub_feeds as scheduler
    factory, objects = store
    monkeypatch.setattr(scheduler, "BackgroundSessionLocal", factory)
    monkeypatch.setattr(scheduler, "access", api.access)
    fetched = []
    changed = cost_data().replace(b"12,50", b"15,50")
    def fetch(p):
        fetched.append(p.id)
        return changed
    monkeypatch.setattr(svc, "fetch", fetch)
    with factory() as db:
        p = profile(db)
        first = api.test_stage(db, p, USER.username, cost_data())
        api.activate(1, p.id, svc.VersionInput(version_id=first["id"]), db, USER)
        p.credentials = "encrypted-not-used"
        p.last_attempt = datetime.utcnow() - timedelta(days=1)
        db.commit()
        ident = p.id
    scheduler.tick()
    with factory() as db:
        p = db.get(HubFeedProfile, ident)
        assert p.active and p.current_version_id != first["id"]
        good = p.current_version_id
        assert p.last_success and not p.last_error
    scheduler.tick()
    assert fetched == [ident]  # interval survives a fresh session
    with factory() as db:
        db.get(HubFeedProfile, ident).last_attempt = datetime.utcnow() - timedelta(days=1)
        db.commit()
    scheduler.tick()
    with factory() as db:
        p = db.get(HubFeedProfile, ident)
        assert p.current_version_id == good
        assert db.query(HubFeedVersion).filter_by(profile_id=ident).count() == 2
        p.last_attempt = datetime.utcnow() - timedelta(days=1)
        db.commit()
    monkeypatch.setattr(svc, "fetch", lambda p: b"")
    scheduler.tick()
    with factory() as db:
        p = db.get(HubFeedProfile, ident)
        assert p.current_version_id == good and p.last_error
        assert p.active and p.last_success


def test_scheduler_rejects_previously_seen_smaller_snapshot(store, monkeypatch):
    import scheduled_hub_feeds as scheduler
    factory, _ = store
    monkeypatch.setattr(scheduler, "BackgroundSessionLocal", factory)
    monkeypatch.setattr(scheduler, "access", api.access)
    small = cost_data()
    # Preserve the exact original bytes for A, add a duplicate valid row for B.
    large = small.rstrip(b"\r\n") + b"\n" + small.splitlines()[1] + b"\n"
    with factory() as db:
        p = profile(db)
        first = api.test_stage(db, p, USER.username, small)
        api.activate(1, p.id, svc.VersionInput(version_id=first["id"]), db, USER)
        p.credentials = "encrypted-not-used"
        p.last_attempt = datetime.utcnow() - timedelta(days=1)
        ident = p.id
        db.commit()
    monkeypatch.setattr(svc, "fetch", lambda p: large)
    scheduler.tick()
    with factory() as db:
        p = db.get(HubFeedProfile, ident)
        good = p.current_version_id
        assert good != first["id"]
        success = p.last_success
        p.last_attempt = datetime.utcnow() - timedelta(days=1)
        db.commit()
    monkeypatch.setattr(svc, "fetch", lambda p: small)
    scheduler.tick()
    with factory() as db:
        p = db.get(HubFeedProfile, ident)
        assert p.current_version_id == good
        assert p.last_success == success
        assert "shrank" in p.last_error
        with pytest.raises(HTTPException, match="shrank"):
            svc.valid_version(db, p, first["id"])


def test_storage_pair_cleanup_when_second_write_fails(monkeypatch):
    calls, deleted = [], []
    def put(data, shop, profile, suffix):
        calls.append(suffix)
        if suffix == "json":
            raise HTTPException(503, "storage unavailable")
        return "uncommitted-original"
    monkeypatch.setattr(storage, "put", put)
    monkeypatch.setattr(storage, "delete", lambda key: deleted.append(key))
    with pytest.raises(HTTPException):
        storage.put_pair(b"original", [], 1, 1)
    assert calls == ["csv", "json"] and deleted == ["uncommitted-original"]


def test_supplied_files_readonly_complete_counts_optional_gtin_and_mismatches():
    paths = [ASSETS / "PriceShapeDemoPrice_(1)_1792672566452.csv",
             ASSETS / "PriceShapeDemoProducts_(3)_1792672566452.csv"]
    if not all(p.exists() for p in paths):
        pytest.skip("Supplied read-only assets unavailable")
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    cost, cr = svc.parse(paths[0].read_bytes(), "cost", {
        "mode": "reference", "complete_snapshot_confirmed": True,
        "mapping": {"productcode": "Productcode", "cost_inc": "Cost Price inc VAT",
                    "cost_exc": "Cost Price exc VAT", "type": "Type", "gtin": "GTIN"}})
    products, pr = svc.parse(paths[1].read_bytes(), "products", {
        "complete_snapshot_confirmed": True,
        "mapping": {"productcode": "Productcode", "price": "Prijs", "type": "Type", "gtin": "EAN"}})
    assert not cr["errors"] and not pr["errors"]
    assert (len(cost), len(products)) == (44854, 44654)
    assert (cr["distinct_products"], pr["distinct_products"]) == (33189, 32989)
    assert cr["duplicate_rows"] == pr["duplicate_rows"] == 3680
    assert sum(not r["gtin"] for r in cost) == 2530
    assert sum(not r["gtin"] for r in products) == 2330
    codes = {r["productcode"] for r in cost}
    pcodes = {r["productcode"] for r in products}
    assert (len(codes - pcodes), len(pcodes - codes)) == (205, 5)
    assert len({r["type"] for r in cost}) == 69
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
