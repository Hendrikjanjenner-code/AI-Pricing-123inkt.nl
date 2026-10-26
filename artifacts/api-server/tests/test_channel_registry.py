"""Directory integration tests use isolated SQLite, no app data or network."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routes import channel_registry as api, channelmanager as legacy
from models import DimShop, AuditLog
from channel_models import ChannelSnapshot
from feed_models import HubFeedProfile, HubFeedVersion
from services.channelmanager import ChannelConfig
from authz import required_action_permission


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for table in (DimShop.__table__, AuditLog.__table__, ChannelSnapshot.__table__,
                  HubFeedProfile.__table__, HubFeedVersion.__table__):
        table.create(engine)
    factory = sessionmaker(bind=engine)
    user = SimpleNamespace(username="directory-test", role="pricing_manager", is_active=True)
    permissions = {"pricing.view", "pricing.propose", "pricing.approve"}
    shops = {1, 2, 3}
    monkeypatch.setattr(api, "effective_permissions", lambda *a: permissions)
    monkeypatch.setattr(legacy, "effective_permissions", lambda *a: permissions)
    monkeypatch.setattr(legacy, "user_allowed_shop_ids", lambda *a: shops)
    with factory() as db:
        db.add_all([DimShop(id=i, shop_code=str(i), name=f"Shop {i}", active=True) for i in shops])
        db.add(HubFeedProfile(id=1, shop_id=1, name="Products", purpose="products", revision=1,
                             active=True, current_version_id=1, created_by=user.username))
        db.add(HubFeedVersion(id=1, profile_id=1, config_revision=1, sha256="test", context_hash="",
                             object_key="test", records_key="test", status="valid", row_count=2,
                             report={}, created_by=user.username))
        config = ChannelConfig(currency="EUR", price_basis="gross", vat_rate=".21",
                               rule={"kind": "fixed", "value": "2"}).model_dump()
        db.add(ChannelSnapshot(shop_id=2, kind="config", revision=1, status="active",
                               data={"config": config}, created_by=user.username))
        db.add(ChannelSnapshot(shop_id=1, kind="basis", revision=1, status="approved",
                               data={"currency": "EUR", "price_basis": "gross", "vat_rate": ".21",
                                     "cost_basis": "net", "provenance": "manual_csv",
                                     "notes": "test", "rows": [
                                         {"sku": "001", "base_price": "30", "name": "", "category": "Print", "cost": "10", "current_price": "25"},
                                         {"sku": "002", "base_price": "50", "name": "", "category": "Print", "cost": "20", "current_price": "45"}]},
                               created_by=user.username))
        db.commit()
    def records(db, shop, profile, **kwargs):
        assert shop == 1 and profile == 1
        return db.get(HubFeedVersion, 1), [{"productcode": "001"}, {"productcode": "002"}]
    monkeypatch.setattr(api, "active_records", records)
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(legacy.router)
    app.dependency_overrides[api.get_current_user] = lambda: user
    def session():
        with factory() as db:
            yield db
    app.dependency_overrides[api.get_db] = session
    with TestClient(app) as client:
        yield client, factory, permissions, shops
    engine.dispose()


BASE = "/api/channelmanager/channels/1"


def get(client):
    response = client.get(BASE)
    assert response.status_code == 200, response.text
    return response.json()


def mutate(client, state, suffix="", body=None, method="post", code=200):
    response = getattr(client, method)(BASE + suffix,
        json={"expected_revision": state["revision"], **(body or {})})
    assert response.status_code == code, response.text
    return response.json()


def ready(client):
    state = get(client)
    ident = state["channels"][0]["id"]
    state = mutate(client, state, "/" + ident, {"target_shop_id": 2, "product_profile_id": 1,
        "mappings": [{"source_productcode": "001", "target_productcode": "000ABC"}],
        "mapping_confirmed": True}, "put")
    state = mutate(client, state, f"/{ident}/validate")
    assert state["channels"][0]["status"] == "ready"
    assert state["channels"][0]["mapped_products"] == 1
    state = mutate(client, state, f"/{ident}/activate")
    return state, ident


def test_defaults_once_hidden_and_reorder_persist(setup):
    client, factory, _, _ = setup
    state = get(client)
    assert [c["name"] for c in state["channels"]] == list(api.DEFAULTS)
    assert all(c["status"] == "setup" and not c["external_connected"] for c in state["channels"])
    assert get(client)["revision"] == state["revision"]
    ident = state["channels"][0]["id"]
    state = mutate(client, state, f"/{ident}/visibility", {"hidden": True})
    state = mutate(client, state, "/reorder", {"channel_ids": [c["id"] for c in reversed(state["channels"])]})
    assert get(client)["channels"][-1]["hidden"]
    with factory() as db:
        assert db.query(DimShop).count() == 3  # no implicit stores or grants


@pytest.mark.parametrize("host", ["KABELSHOP.NL", "https://www.kabelshop.nl/"])
def test_canonical_duplicates_including_hidden(setup, host):
    client, *_ = setup
    state = get(client)
    mutate(client, state, body={"name": "Duplicate", "domain": host}, code=409)


def test_configure_draft_validate_activate_pause_and_stale(setup):
    client, factory, _, _ = setup
    state, ident = ready(client)
    assert state["channels"][0]["status"] == "active"
    with factory() as db:
        p = db.get(HubFeedProfile, 1)
        p.active = False
        db.commit()
    assert get(client)["channels"][0]["status"] == "needs_validation"
    mutate(client, state, f"/{ident}/activate", code=409)
    state = mutate(client, state, f"/{ident}/pause")
    assert not state["channels"][0]["external_connected"]
    mutate(client, {"revision": 1}, f"/{ident}/pause", code=409)


def test_invalid_mapping_and_wrong_source(setup):
    client, *_ = setup
    state = get(client)
    ident = state["channels"][0]["id"]
    state = mutate(client, state, "/" + ident, {"target_shop_id": 2, "product_profile_id": 1,
        "mappings": [{"source_productcode": "missing", "target_productcode": "001"}],
        "mapping_confirmed": True}, "put")
    state = mutate(client, state, f"/{ident}/validate")
    assert state["channels"][0]["validation_errors"]
    mutate(client, state, f"/{ident}/activate", code=409)
    mutate(client, state, "/" + ident, {"target_shop_id": 2, "product_profile_id": 99}, "put", 404)


def test_one_destination_per_channel_and_save_never_activates(setup):
    client, *_ = setup
    state, ident = ready(client)
    other = state["channels"][1]["id"]
    mutate(client, state, "/" + other, {"target_shop_id": 2}, "put", 409)
    state = mutate(client, state, "/" + ident, {"target_shop_id": 2, "product_profile_id": 1,
        "mappings": [{"source_productcode": "002", "target_productcode": "002"}],
        "mapping_confirmed": True}, "put")
    assert state["channels"][0]["status"] == "setup"
    assert state["channels"][0]["mapped_products"] is None


def test_restricted_targets_masked_cannot_modify_or_read_registry_snapshot(setup):
    client, factory, _, allowed = setup
    state, ident = ready(client)
    allowed.remove(2)
    state = get(client)
    channel = state["channels"][0]
    assert channel["status"] == "restricted"
    assert channel["mappings"] == [] and channel["target_shop_id"] is None
    mutate(client, state, f"/{ident}/pause", code=404)
    with factory() as db:
        row = legacy.latest(db, 1, api.KIND)
        assert client.get(f"/api/channelmanager/1/records/{row.id}").status_code == 404


def test_approve_only_and_propose_only(setup):
    client, _, perms, _ = setup
    state, ident = ready(client)
    state = mutate(client, state, f"/{ident}/pause")
    perms.remove("pricing.propose")
    assert required_action_permission(BASE + f"/{ident}/activate", "POST") == "pricing.approve"
    state = mutate(client, state, f"/{ident}/activate")
    mutate(client, state, f"/{ident}/pause", code=403)
    perms.add("pricing.propose")
    perms.remove("pricing.approve")
    mutate(client, state, f"/{ident}/activate", code=403)


def test_mapping_drives_staged_basis_and_export_without_automatic_approval(setup):
    client, factory, _, allowed = setup
    state, ident = ready(client)
    staged = mutate(client, state, f"/{ident}/prepare-basis")
    assert staged["status"] == "staged"
    assert [r["sku"] for r in staged["data"]["rows"]] == ["000ABC"]
    assert staged["data"]["rows"][0]["current_price"] is None
    path = "/api/channelmanager/2"
    assert client.post(f"{path}/basis/{staged['id']}/approve", json={"notes": "test"}).status_code == 200
    calc = client.post(path + "/calculate", json={"source_shop_id": 2, "basis_id": staged["id"]})
    assert calc.status_code == 200, calc.text
    calc = calc.json()
    assert calc["data"]["rows"][0]["target_price"] == "32.00"
    assert client.post(f"{path}/calculations/{calc['id']}/approve", json={"notes": "test"}).status_code == 200
    export = client.post(f"{path}/calculations/{calc['id']}/export", json={"notes": "test"})
    assert export.status_code == 200, export.text
    assert "000ABC" in export.json()["data"]["csv"]
    allowed.remove(1)
    assert client.get(f"{path}/records/{calc['id']}").status_code == 404
    assert client.get(f"{path}/exports/{export.json()['id']}/download").status_code == 404


def test_mapping_change_invalidates_staged_basis_but_not_reorder(setup):
    client, *_ = setup
    state, ident = ready(client)
    staged = mutate(client, state, f"/{ident}/prepare-basis")
    state = mutate(client, state, "/reorder", {"channel_ids": [c["id"] for c in reversed(state["channels"])]})
    approve_path = f"/api/channelmanager/2/basis/{staged['id']}/approve"
    assert client.post(approve_path, json={"notes": "test"}).status_code == 200
    state = mutate(client, state, f"/{ident}/pause")
    calc = client.post("/api/channelmanager/2/calculate", json={"source_shop_id": 2, "basis_id": staged["id"]})
    assert calc.status_code == 409
