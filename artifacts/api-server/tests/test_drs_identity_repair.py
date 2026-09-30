"""Repair writes only to the independently configured pytest database."""
from datetime import datetime, timedelta, date
from types import SimpleNamespace
import copy
import io
import json
import csv
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import openpyxl
from fastapi import HTTPException
import models
from test_drs_daily import db, workbook, preview
from services.drs_daily import (preview_resolution, confirm_resolution, revalidate_stage,
                                parse_workbook, create_preview, confirm_stage)
from services.product_identity import IdentityIndex
from routes.drs_daily import unresolved, export_unresolved, get_stage

USER = SimpleNamespace(username="test", role="admin")


def stage_for(db, **kwargs):
    p = preview(db, code="new-0008", **kwargs)
    return db.get(models.DrsDailyStage, p["stage_id"])


def test_link_is_explicit_durable_audited_and_revalidated(db):
    stage = stage_for(db)
    original = copy.deepcopy(stage.preview)
    sku = db.test_products[0].sku_id
    impact = preview_resolution(db, USER, stage, [{"row": 3, "action": "link", "sku_id": sku}])
    assert impact["aliases_added"] == 1 and impact["sales_written"] == 0
    assert not db.query(models.ProductSourceAlias).filter_by(shop_id=stage.shop_id).count()
    with pytest.raises(HTTPException):
        confirm_resolution(db, USER, stage, impact["resolution_id"], False)
    result = confirm_resolution(db, USER, stage, impact["resolution_id"], True)
    assert confirm_resolution(db, USER, stage, impact["resolution_id"], True) == result
    assert db.query(models.AuditLog).filter_by(entity_id=sku, entity_type="drs_identity").count() == 1
    assert db.test_products[0].import_source == "priceshape"
    assert db.test_products[0].business_sku is None
    assert IdentityIndex(db, stage.shop_id).resolve("new-0008", "001234") == (sku, False)
    assert not db.query(models.FactSalesDaily).filter_by(shop_id=stage.shop_id).count()
    new = revalidate_stage(db, USER, stage)
    assert new["stage_id"] != stage.id and new["status"] == "ready"
    assert new["resolved_error_count"] == 1 and stage.preview == original
    assert preview(db, code="new-0008")["status"] == "ready"


def test_create_uses_stable_id_separate_identifiers_and_no_cost(db):
    stage = stage_for(db, ean="00009876")
    impact = preview_resolution(db, USER, stage, [{"row": 3, "action": "create"}])
    confirm_resolution(db, USER, stage, impact["resolution_id"], True)
    sku = impact["actions"][0]["sku_id"]
    p = db.get(models.DimProduct, sku)
    assert sku.startswith("drs-") and sku != "new-0008"
    assert (p.business_sku, p.product_name, p.ean, p.oem_code) == ("new-0008", "Product", "00009876", "NONUNIQUE")
    assert p.cost_price is None and p.import_source == "DRS"
    new = revalidate_stage(db, USER, stage)
    assert new["status"] == "ready"
    confirm_stage(db, db.get(models.DrsDailyStage, new["stage_id"]), True)
    facts = db.query(models.FactSalesDaily).filter_by(shop_id=stage.shop_id).all()
    assert len(facts) == 2 and all(f.cost is None and f.margin is None for f in facts)
    # A feed key with the same EAN resolves to the newly created technical ID.
    from feed_ingest import _identity_rows
    for _ in range(2):
        catalog, _, _, aliases, proposals = _identity_rows(db, "priceshape", stage.shop_id,
            [{"sku_id": "00009876", "ean": "00009876", "product_group": "new-0008"}], [])
        assert list(catalog)[0]["sku_id"] == sku
        for (code, discriminator), target in proposals.items():
            if (code, discriminator) not in aliases:
                db.add(models.ProductSourceAlias(shop_id=stage.shop_id, source="priceshape",
                       code=code, discriminator=discriminator, sku_id=target))
        db.commit()
    assert db.query(models.DimProduct).filter_by(shop_id=stage.shop_id).count() == 2
    assert IdentityIndex(db, stage.shop_id).resolve("new-0008", "00009876")[0] == sku


def test_conflicts_cross_shop_duplicates_and_stale(db):
    stage = stage_for(db, ean="9999")
    for action in [{"row": 3, "action": "link", "sku_id": db.test_products[0].sku_id},
                   {"row": 3, "action": "link", "sku_id": db.test_products[1].sku_id}]:
        with pytest.raises(HTTPException):
            preview_resolution(db, USER, stage, [action])
    with pytest.raises(HTTPException):
        preview_resolution(db, USER, stage, [{"row": 3, "action": "create"}] * 2)
    impact = preview_resolution(db, USER, stage, [{"row": 3, "action": "create"}])
    db.test_products[0].ean = "changed"
    db.commit()
    with pytest.raises(HTTPException) as err:
        confirm_resolution(db, USER, stage, impact["resolution_id"], True)
    assert err.value.status_code == 409
    assert not db.query(models.ProductSourceAlias).filter_by(shop_id=stage.shop_id).count()
    other = SimpleNamespace(username="other", role="admin")
    with pytest.raises(HTTPException) as err:
        confirm_resolution(db, other, stage, impact["resolution_id"], True)
    assert err.value.status_code == 403


def test_duplicate_creation_ean_and_expired_old_stages(db):
    stage = stage_for(db)  # EAN already belongs to an existing product
    with pytest.raises(HTTPException):
        preview_resolution(db, USER, stage, [{"row": 3, "action": "create"}])
    stage.preview = {**stage.preview, "metadata_version": 1}
    db.commit()
    with pytest.raises(HTTPException) as err:
        revalidate_stage(db, USER, stage)
    assert err.value.status_code == 409
    stage.expires_at = datetime.utcnow() - timedelta(seconds=1)
    with pytest.raises(HTTPException) as err:
        revalidate_stage(db, USER, stage)
    assert err.value.status_code == 410


def test_full_unresolved_persistence_pagination_and_export(db, monkeypatch):
    wb = openpyxl.load_workbook(workbook(code="unknown-0"))
    ws = wb.active
    for i in range(1, 235):
        ws.append([f"unknown-{i}", "Rich name", f"000{i:05}", "000OEM"] +
                  [2, 24.2, 20, -1, -12.1, -10, 1, 12.1, 10])
    data = io.BytesIO()
    wb.save(data)
    data.seek(0)
    p = create_preview(db, USER, db.test_shops[0].id, data, 2026, date(2026, 8, 30), date(2026, 8, 31), {})
    db.expire_all()
    stage = db.get(models.DrsDailyStage, p["stage_id"])
    assert stage.preview["error_count"] == len(stage.preview["errors"]) == 235
    monkeypatch.setattr("routes.drs_daily.authorize_shop", lambda *args: None)
    page = unresolved(stage.id, 200, 50, db, USER)
    assert len(page["items"]) == 35 and page["total"] == 235
    assert page["items"][0]["product_name"] == "Rich name"
    result = export_unresolved(stage.id, db, USER)
    exported = list(csv.reader(io.StringIO(result.body.decode("utf-8-sig"))))
    assert len(exported) == 236
    assert json.loads(exported[1][-1])[0]["evidence"] == ["EAN:001234"]
    # Search must cover records beyond the first page and paginate AFTER filtering.
    page = unresolved(stage.id, 0, 10, db, USER, q="unknown-234")
    assert page["total"] == 1 and page["items"][0]["code"] == "unknown-234"
    page = unresolved(stage.id, 230, 10, db, USER, q="rIcH NAME")
    assert page["total"] == 234 and len(page["items"]) == 4
    assert unresolved(stage.id, 0, 10, db, USER, q="00000234")["total"] == 1
    assert unresolved(stage.id, 0, 10, db, USER, q="000oem")["total"] == 234
    assert unresolved(stage.id, 0, 10, db, USER, q="Onbekende artikelcode")["total"] == 235
    assert unresolved(stage.id, 0, 10, db, USER, q="no-such-value")["total"] == 0


def test_ambiguous_evidence_explicit_selection_and_no_overwrite(db):
    p = db.test_products[0]
    p.business_sku = "canonical-other"
    second = models.DimProduct(sku_id=p.sku_id + "-b", shop_id=p.shop_id,
                               product_name="Other candidate", product_group="0007", ean=p.ean)
    db.add(second)
    db.commit()
    raw = preview(db)
    stage = db.get(models.DrsDailyStage, raw["stage_id"])
    assert len(stage.preview["errors"][0]["candidates"]) == 2
    plan = preview_resolution(db, USER, stage, [{"row": 3, "action": "link", "sku_id": p.sku_id}])
    confirm_resolution(db, USER, stage, plan["resolution_id"], True)
    assert revalidate_stage(db, USER, stage)["status"] == "ready"
    assert p.business_sku == "canonical-other"


def test_feed_conflicting_ean_never_changes_identity(db):
    from feed_ingest import _identity_rows
    p = db.test_products[0]
    with pytest.raises(ValueError, match="EAN-conflict"):
        _identity_rows(db, "priceshape", p.shop_id,
                       [{"sku_id": p.sku_id, "ean": "different", "product_group": "0007"}], [])
    assert p.ean == "001234"


def test_concurrent_repair_proposals_are_stale_and_retry_is_idempotent(db):
    from concurrent.futures import ThreadPoolExecutor
    from database import SessionLocal
    stage = stage_for(db, ean="00009876")
    a = preview_resolution(db, USER, stage, [{"row": 3, "action": "create"}])
    b = preview_resolution(db, USER, stage, [{"row": 3, "action": "create"}])
    stage_id = stage.id
    def submit(token):
        with SessionLocal() as session:
            try:
                return confirm_resolution(session, USER, session.get(models.DrsDailyStage, stage_id), token, True)
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [a["resolution_id"], b["resolution_id"]]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert 409 in results
    db.expire_all()
    assert db.query(models.ProductSourceAlias).filter_by(shop_id=stage.shop_id, source="DRS").count() == 1
    assert db.query(models.DimProduct).filter_by(shop_id=stage.shop_id).count() == 2


def test_repair_routes_enforce_permission_and_shop(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import auth
    from database import get_db
    from routes.drs_daily import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    user = SimpleNamespace(username="repair-viewer", role="viewer", id=987654321)
    app.dependency_overrides[auth.get_current_user] = lambda: user
    monkeypatch.setattr("authz.effective_permissions", lambda *_: {"data.view"})
    stage = stage_for(db)
    with TestClient(app) as client:
        response = client.post(f"/api/uploads/drs-daily/{stage.id}/resolution-preview",
                               json={"actions": [{"row": 3, "action": "create"}]})
        assert response.status_code == 403
        user.role = "admin"
        monkeypatch.setattr("services.product_identity.user_allowed_shop_ids", lambda *_: {db.test_shops[1].id})
        for endpoint in ("unresolved", "unresolved/export", "products"):
            assert client.get(f"/api/uploads/drs-daily/{stage.id}/{endpoint}").status_code == 403
        assert client.post(f"/api/uploads/drs-daily/{stage.id}/revalidate").status_code == 403


def test_full_supplied_report_metadata_parser():
    from pathlib import Path
    path = Path(__file__).resolve().parents[3] / "attached_assets/0_Sales_(100)_1790757168579.xlsx"
    if not path.exists():
        pytest.skip("Supplied private workbook not distributed")
    rows, dates, errors, totals = parse_workbook(path, 2026, date(2026, 8, 30), date(2026, 9, 30))
    assert len(rows) == 11038 and len(dates) == 32 and errors == []
    assert all("product_name" in r and "oem" in r and "ean" in r for r in rows)
    assert totals["quantity"] == 726924
    assert next(r for r in rows if r["code"] == "214557")["ean"] == "04046711601255, 4046711601255"