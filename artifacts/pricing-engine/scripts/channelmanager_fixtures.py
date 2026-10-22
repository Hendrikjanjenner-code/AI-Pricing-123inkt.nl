"""Genereert echte Channelmanager-responses uit de backendroutes (in-memory SQLite)
als fixtures voor de frontend-parsertests. Raakt geen echte database.

Gebruik (vanuit workspace-root):
  cd artifacts/api-server && python ../pricing-engine/scripts/channelmanager_fixtures.py
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

API = Path(__file__).resolve().parents[2] / "api-server"
sys.path.insert(0, str(API))
from routes import channelmanager as api  # noqa: E402
from models import DimShop, AuditLog  # noqa: E402
from channel_models import ChannelSnapshot  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "src/lib/channelmanager/__fixtures__/backend-snapshots.json"
USER = SimpleNamespace(id=1, username="manager", role="pricing_manager", is_active=True)
CONFIG = {"currency": "EUR", "price_basis": "gross", "vat_rate": "0.21", "rule": {"kind": "fixed", "value": "-1"},
          "min_margin": "0.1", "export_columns": {"sku": "sku", "price": "target_price", "name": "name"},
          "delimiter": ";", "decimal": ","}
BASIS = {"currency": "EUR", "price_basis": "gross", "vat_rate": "0.21", "cost_basis": "net",
         "provenance": "manual_csv", "notes": "fixture",
         "rows": [{"sku": "A-1", "name": "Een", "category": "Print", "base_price": "12.10", "cost": "5", "current_price": "12.10"},
                  {"sku": "A-2", "name": "Twee", "category": "Print", "base_price": "2.00", "cost": "1.90", "current_price": None}]}

engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
for table in (DimShop.__table__, AuditLog.__table__, ChannelSnapshot.__table__):
    table.create(engine)
factory = sessionmaker(bind=engine)
with factory() as db:
    db.add_all([DimShop(id=i, shop_code=str(i), name=f"Winkel {i}") for i in (1, 2)])
    db.commit()
api.effective_permissions = lambda db, u: {"pricing.view", "pricing.propose", "pricing.approve"}
api.user_allowed_shop_ids = lambda db, u: {1, 2}
app = FastAPI()
app.include_router(api.router)


def session():
    with factory() as db:
        yield db


app.dependency_overrides[api.get_db] = session
app.dependency_overrides[api.get_current_user] = lambda: USER
c = TestClient(app)


def post(path, body=None, ok=200):
    r = c.post("/api/channelmanager/" + path, json=body)
    assert r.status_code == ok, r.text
    return r.json()


out = {}
out["overview_empty"] = c.get("/api/channelmanager/1/overview").json()
out["error_422_config"] = post("1/config", {"expected_revision": 0, "notes": "x", "config": {**CONFIG, "vat_rate": "2"}}, 422)
out["config"] = post("1/config", {"expected_revision": 0, "notes": "review", "config": CONFIG})
out["error_409_config"] = post("1/config", {"expected_revision": 0, "notes": "x", "config": CONFIG}, 409)
out["basis_staged"] = post("1/basis", BASIS)
out["basis_approved"] = post(f"1/basis/{out['basis_staged']['id']}/approve", {"notes": "ok"})
out["calc_blocked"] = post("1/calculate", {"source_shop_id": 1, "basis_id": out["basis_approved"]["id"]})
ok_basis = post("1/basis", {**BASIS, "rows": BASIS["rows"][:1]})
post(f"1/basis/{ok_basis['id']}/approve", {"notes": "ok"})
out["calc_preview"] = post("1/calculate", {"source_shop_id": 1, "basis_id": ok_basis["id"]})
out["calc_cross_shop"] = post("2/calculate", {"source_shop_id": 1, "basis_id": ok_basis["id"]}) if c.post(
    "/api/channelmanager/2/config", json={"expected_revision": 0, "notes": "r", "config": CONFIG}).status_code == 200 else None
out["calc_approved"] = post(f"1/calculations/{out['calc_preview']['id']}/approve", {"notes": "ok"})
out["export"] = post(f"1/calculations/{out['calc_preview']['id']}/export", {"notes": "exp"})
settings = {"mapping": {"sku": "SKU", "actual_price": "Price"}, "delimiter": ";", "decimal": ",",
            "currency": "EUR", "price_basis": "gross", "vat_rate": "0.21"}


def readback(text):
    r = c.post(f"/api/channelmanager/1/exports/{out['export']['id']}/readback",
               data={"settings": json.dumps(settings)}, files={"file": ("r.csv", text, "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


target = out["export"]["data"]["rows"][0]["target_price"].replace(".", ",")
out["readback_matched"] = readback(f"SKU;Price\nA-1;{target}\n")
out["readback_partial"] = readback("SKU;Price\nA-1;1,00\nZZ;2,00\nZZ;2,00\n")
out["run"] = post("1/run")
out["history_calc"] = c.get("/api/channelmanager/1/history?kind=calculation&limit=1").json()
out["overview_full"] = c.get("/api/channelmanager/1/overview").json()
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
print("fixtures geschreven:", OUT)
