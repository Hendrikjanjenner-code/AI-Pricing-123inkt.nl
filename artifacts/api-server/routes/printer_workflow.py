"""Scoped append-only printer approvals and immutable private workbook downloads."""
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy.orm import Session
from auth import get_current_user
from database import get_db
from channel_models import ChannelSnapshot as Snapshot
from routes.channelmanager import access, lock, latest, get_record, dump, add, commit, audit, Notes
from services.channelmanager import number
from services.printer_workflow import (
    PrinterConfig, PriceRow, calculate, price_index, reconcile, workbook)
from services import hub_feeds_storage as storage

router = APIRouter(prefix="/api/channelmanager/printer", tags=["printer-workflow"])
KINDS = ("config", "pre", "advice", "calculation", "approval", "export", "readback")


class ConfigInput(Notes):
    expected_revision: int = Field(ge=0)
    config: PrinterConfig


class PricesInput(Notes):
    rows: list[PriceRow] = Field(min_length=1, max_length=300000)


class AdviceInput(Notes):
    profile_id: int = Field(gt=0)
    version_id: int = Field(gt=0)
    semantics_confirmed: bool = False


class CalculateInput(Notes):
    advice_snapshot_id: int = Field(gt=0)


class ApproveInput(Notes):
    acknowledge_warnings: bool = False


def record(db, shop, ident, kind):
    return get_record(db, shop, ident, "printer_" + kind)


def current(db, shop, kind):
    return latest(db, shop, "printer_" + kind)


def save(db, user, shop, kind, data, status="draft", claim=None):
    return add(db, user, shop, "printer_" + kind, data, status, claim)


def scoped(db, user, shop, action="pricing.view", config_record=None, active=False):
    access(db, user, shop, action)
    config_record = config_record or current(db, shop, "config")
    if not config_record:
        raise HTTPException(409, "Save explicit printer shop mapping first")
    config = PrinterConfig.model_validate(config_record.data["config"])
    for target in config.shops.values():
        access(db, user, target, action)
    if active and not config.active:
        raise HTTPException(409, "Printer profile is inactive")
    return config_record, config


def feed_records(db, shop, data):
    from services.hub_feeds import active_records
    from feed_models import HubFeedProfile
    # Serialize source changes with approval/export checks; a paused/revised
    # feed cannot slip between validation and committing an approval.
    db.query(HubFeedProfile).filter_by(id=data["profile_id"], shop_id=shop).with_for_update().first()
    return active_records(db, shop, data["profile_id"], purpose="advice",
                          version_id=data["version_id"])


def guard(db, user, shop, calculation, action):
    cfg, config = scoped(db, user, shop, action, active=True)
    pre, advice = current(db, shop, "pre"), current(db, shop, "advice")
    data = calculation.data
    if not pre or not advice or (cfg.id, pre.id, advice.id) != (
            data["config_id"], data["pre_id"], data["advice_id"]):
        raise HTTPException(409, "Stale calculation: config, pre prices or approved advice changed")
    feed_records(db, shop, advice.data)
    return cfg, config, pre, advice


def valid_call(fn, *args):
    try:
        return fn(*args)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{shop_id}")
def overview(shop_id: int, before_id: int | None = Query(default=None, gt=0),
             limit: int = Query(default=50, ge=1, le=100),
             db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id)
    cfg = current(db, shop_id, "config")
    if cfg:
        scoped(db, user, shop_id)
    # Historical mappings may differ; do not leak their cross-shop prices.
    query = db.query(Snapshot).filter(Snapshot.shop_id == shop_id,
        Snapshot.kind.in_(["printer_" + k for k in KINDS]))
    if before_id:
        query = query.filter(Snapshot.id < before_id)
    items = query.order_by(Snapshot.id.desc()).limit(limit + 1).all()
    def authorized(item):
        if item is None:
            return None
        config_id = item.data.get("config_id")
        historical = record(db, shop_id, config_id, "config") if config_id else (
            item if item.kind == "printer_config" else cfg)
        try:
            scoped(db, user, shop_id, config_record=historical)
        except HTTPException:
            return None
        return dump(item)
    visible = [value for item in items[:limit] if (value := authorized(item)) is not None]
    return {**{k: authorized(current(db, shop_id, k)) for k in KINDS},
            "history": visible, "has_more": len(items) > limit,
            "next_before_id": items[limit - 1].id if len(items) > limit else None,
            "drs_compatibility": "unconfirmed", "live_write": False}


@router.put("/{shop_id}/config")
def configure(shop_id: int, body: ConfigInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    for target in body.config.shops.values():
        access(db, user, target, "pricing.propose")
    lock(db, shop_id, *body.config.shops.values())
    previous = current(db, shop_id, "config")
    if previous:
        scoped(db, user, shop_id, "pricing.propose", previous)
    if (previous.revision if previous else 0) != body.expected_revision:
        raise HTTPException(409, "Config revision changed")
    return commit(db, save(db, user, shop_id, "config",
                          {"config": body.config.model_dump(), "notes": body.notes}))


@router.post("/{shop_id}/pre")
def import_pre(shop_id: int, body: PricesInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    lock(db, shop_id)
    cfg, config = scoped(db, user, shop_id, "pricing.propose")
    rows = [r.model_dump() for r in body.rows]
    _, duplicates = valid_call(price_index, rows, set(config.shops.values()))
    return commit(db, save(db, user, shop_id, "pre",
                          {"config_id": cfg.id, "rows": rows, "duplicates": duplicates, "notes": body.notes}))


@router.post("/{shop_id}/advice")
def approve_advice(shop_id: int, body: AdviceInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    lock(db, shop_id)
    cfg, config = scoped(db, user, shop_id, "pricing.approve", active=True)
    if not body.semantics_confirmed:
        raise HTTPException(422, "Explicitly confirm advice currency, VAT basis and unit match printer profile")
    version, rows = feed_records(db, shop_id, body.model_dump())
    # Validate every advice before recording an approved fixed-price basis.
    if not rows:
        raise HTTPException(422, "Empty advice snapshot cannot be approved")
    prices = {}
    duplicates = 0
    for row in rows:
        price = valid_call(number, row.get("advice", "-1"))
        if not row.get("productcode") or price < 0:
            raise HTTPException(422, "Invalid advice row")
        sku = row["productcode"]
        if sku in prices:
            if prices[sku] != price:
                raise HTTPException(422, "Conflicting advice prices for product")
            duplicates += 1
        prices[sku] = price
    return commit(db, save(db, user, shop_id, "advice", {
        "config_id": cfg.id, "profile_id": body.profile_id, "version_id": version.id,
        "rows": rows, "duplicate_rows": duplicates,
        "semantics": {k: getattr(config, k) for k in ("currency", "price_basis", "vat_rate")},
        "notes": body.notes}, "approved"))


@router.post("/{shop_id}/calculate")
def run_calculation(shop_id: int, body: CalculateInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    lock(db, shop_id)
    cfg, config = scoped(db, user, shop_id, "pricing.propose", active=True)
    pre = current(db, shop_id, "pre")
    advice = record(db, shop_id, body.advice_snapshot_id, "advice")
    if not pre or pre.data["config_id"] != cfg.id or advice.data["config_id"] != cfg.id:
        raise HTTPException(409, "Reimport pre prices and approve advice for current config")
    if current(db, shop_id, "advice").id != advice.id or advice.status != "approved":
        raise HTTPException(409, "Only latest explicitly approved advice may be calculated")
    feed_records(db, shop_id, advice.data)
    result = valid_call(calculate, config, advice.data["rows"], pre.data["rows"])
    return commit(db, save(db, user, shop_id, "calculation", {
        **result, "config_id": cfg.id, "pre_id": pre.id, "advice_id": advice.id,
        "notes": body.notes}, "blocked" if result["blocks"] else "calculated"))


@router.post("/{shop_id}/approve/{calculation_id}")
def approve(shop_id: int, calculation_id: int, body: ApproveInput,
            db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    lock(db, shop_id)
    calc = record(db, shop_id, calculation_id, "calculation")
    guard(db, user, shop_id, calc, "pricing.approve")
    if calc.data["blocks"]:
        raise HTTPException(409, "Calculation contains blocked rows")
    if calc.data["warnings"] and not body.acknowledge_warnings:
        raise HTTPException(409, "Explicitly acknowledge changes above 20 percent")
    return commit(db, save(db, user, shop_id, "approval", {
        "config_id": calc.data["config_id"], "calculation_id": calc.id,
        "acknowledge_warnings": body.acknowledge_warnings, "notes": body.notes}, "approved"))


@router.post("/{shop_id}/export/{approval_id}")
def export(shop_id: int, approval_id: int, body: Notes,
           db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    lock(db, shop_id)
    approval = record(db, shop_id, approval_id, "approval")
    calc = record(db, shop_id, approval.data["calculation_id"], "calculation")
    cfg, config, pre, advice = guard(db, user, shop_id, calc, "pricing.approve")
    claim = f"printer-export:{calc.id}"
    existing = db.query(Snapshot).filter_by(shop_id=shop_id, claim=claim).first()
    if existing:
        return dump(existing)
    provenance = {"config_id": cfg.id, "pre_id": pre.id, "advice_id": advice.id,
                  "calculation_id": calc.id, "approval_id": approval.id,
                  "feed_version_id": advice.data["version_id"], "status": "created_not_processed"}
    content = workbook(config, calc.data, provenance, pre.data["rows"], advice.data["rows"])
    key = storage.put(content, shop_id, advice.data["profile_id"], "xlsx")
    filename = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M") + f"_{calc.id}_macro_-_printer_prijs_aanpassingen_PriceShape.xlsx"
    return commit(db, save(db, user, shop_id, "export", {
        **provenance, "object_key": key, "sha256": hashlib.sha256(content).hexdigest(),
        "filename": filename, "rows": calc.data["rows"], "notes": body.notes,
        "drs_compatibility": "unconfirmed"}, "created", claim))


@router.get("/{shop_id}/download/{export_id}")
def download(shop_id: int, export_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    item = record(db, shop_id, export_id, "export")
    scoped(db, user, shop_id, "pricing.approve",
           record(db, shop_id, item.data["config_id"], "config"))
    content = storage.get(item.data["object_key"])
    if hashlib.sha256(content).hexdigest() != item.data["sha256"]:
        raise HTTPException(409, "Stored workbook integrity check failed")
    audit(db, user, shop_id, "printer_download", {"export_id": item.id, "sha256": item.data["sha256"]})
    db.commit()
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{item.data["filename"]}"',
                             "Cache-Control": "private, no-store"})


@router.post("/{shop_id}/readback/{export_id}")
def readback(shop_id: int, export_id: int, body: PricesInput,
             db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    lock(db, shop_id)
    item = record(db, shop_id, export_id, "export")
    cfg, config = scoped(db, user, shop_id, "pricing.approve",
                         record(db, shop_id, item.data["config_id"], "config"))
    rows = [r.model_dump() for r in body.rows]
    result = valid_call(reconcile, item.data["rows"], rows, set(config.shops.values()))
    calc = record(db, shop_id, item.data["calculation_id"], "calculation")
    pre = record(db, shop_id, item.data["pre_id"], "pre")
    advice = record(db, shop_id, item.data["advice_id"], "advice")
    provenance = {k: item.data[k] for k in ("config_id", "pre_id", "advice_id", "calculation_id", "approval_id")}
    provenance.update(export_id=item.id, export_sha256=item.data["sha256"],
                      readback_status="confirmed" if result["confirmed"] else "mismatch",
                      checked_at=datetime.now(timezone.utc).isoformat())
    content = workbook(config, calc.data, provenance, pre.data["rows"], advice.data["rows"], result)
    key = storage.put(content, shop_id, advice.data["profile_id"], "xlsx")
    return commit(db, save(db, user, shop_id, "readback", {
        **result, "config_id": cfg.id, "export_id": item.id, "export_sha256": item.data["sha256"],
        "object_key": key, "sha256": hashlib.sha256(content).hexdigest(),
        "filename": item.data["filename"].replace(".xlsx", "_readback.xlsx"),
        "rows": rows, "notes": body.notes}, "confirmed" if result["confirmed"] else "mismatch"))


@router.get("/{shop_id}/readback/{readback_id}/download")
def download_readback(shop_id: int, readback_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    item = record(db, shop_id, readback_id, "readback")
    scoped(db, user, shop_id, "pricing.approve", record(db, shop_id, item.data["config_id"], "config"))
    content = storage.get(item.data["object_key"])
    if hashlib.sha256(content).hexdigest() != item.data["sha256"]:
        raise HTTPException(409, "Stored checked workbook integrity check failed")
    audit(db, user, shop_id, "printer_checked_download",
          {"readback_id": item.id, "export_id": item.data["export_id"], "sha256": item.data["sha256"]})
    db.commit()
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{item.data["filename"]}"',
                             "Cache-Control": "private, no-store"})
