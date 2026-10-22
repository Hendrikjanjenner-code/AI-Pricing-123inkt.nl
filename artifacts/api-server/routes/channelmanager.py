"""Internal, human-approved Channelmanager workflow. No external dispatch."""
import hashlib
import csv as csv_module
import json
from datetime import datetime, timezone
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from pydantic import Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from auth import get_current_user
from authz import effective_permissions, user_allowed_shop_ids
from database import get_db
from models import DimShop, AuditLog
from channel_models import ChannelSnapshot as Snapshot
from services.channelmanager import (Strict, Semantics, CSVSettings, ChannelConfig, BasisInput,
                                     calculate, parse_csv, export_csv, number)

router = APIRouter(prefix="/api/channelmanager", tags=["channelmanager"])


class Notes(Strict):
    notes: str = Field(min_length=1, max_length=2000)


class ConfigInput(Notes):
    expected_revision: int = Field(ge=0)
    config: ChannelConfig


class CalculationInput(Strict):
    source_shop_id: int = Field(gt=0)
    basis_id: int = Field(gt=0)


class SnapshotOutput(Strict):
    id: int
    shop_id: int
    kind: str
    revision: int
    status: str
    created_at: str
    created_by: str
    data: dict


class HistoryOutput(Strict):
    items: list[SnapshotOutput]
    has_more: bool


class SchedulerOutput(Strict):
    running: bool
    available: bool
    disabled: bool
    mode: str
    poll_interval_seconds: int
    timezone: str
    reason: str | None
    last_poll_at: str | None
    last_error: str | None


class OverviewOutput(Strict):
    config: SnapshotOutput | None
    basis: SnapshotOutput | None
    last_run: SnapshotOutput | None
    history_limit: int
    external_formats: str
    schedule_timezone: str
    can_propose: bool
    can_approve: bool
    can_export: bool
    queues: dict[str, int]
    counts: dict[str, int]
    scheduler: SchedulerOutput


def access(db, user, shop_id, action="pricing.view"):
    if not getattr(user, "is_active", True):
        raise HTTPException(403, "Inactive user")
    if not {"pricing.view", action} <= effective_permissions(db, user):
        raise HTTPException(403, "Pricing permission required")
    allowed = user_allowed_shop_ids(db, user)
    if (allowed is not None and shop_id not in allowed) or not db.get(DimShop, shop_id):
        raise HTTPException(404, "Shop not found")


def lock(db, *shops):
    for shop in sorted(set(shops)):
        db.query(DimShop).filter_by(id=shop).with_for_update().one()


def latest(db, shop, kind, approved=False):
    query = db.query(Snapshot).filter_by(shop_id=shop, kind=kind)
    if approved:
        query = query.filter_by(status="approved")
    return query.order_by(Snapshot.revision.desc()).first()


def get_record(db, shop, record_id, kind=None):
    query = db.query(Snapshot).filter_by(shop_id=shop, id=record_id)
    if kind:
        query = query.filter_by(kind=kind)
    result = query.first()
    if not result:
        raise HTTPException(404, "Record not found")
    return result


def dump(record):
    if record is None:
        return None
    return dict(id=record.id, shop_id=record.shop_id, kind=record.kind, revision=record.revision,
                status=record.status, created_at=record.created_at.isoformat() + "Z",
                created_by=record.created_by, data=record.data)


def audit(db, user, shop, action, details):
    db.add(AuditLog(entity_type="channelmanager", entity_id=str(shop), action=action,
                    performed_by=user.username, new_value=details,
                    details="Internal workflow only; external formats provisional/unconfirmed"))


def add(db, user, shop, kind, data, status="draft", claim=None):
    previous = latest(db, shop, kind)
    record = Snapshot(shop_id=shop, kind=kind, revision=previous.revision + 1 if previous else 1,
                      status=status, created_by=user.username, claim=claim,
                      data={**data, "external_formats": "provisional_unconfirmed"})
    db.add(record)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Concurrent modification; reload and retry") from exc
    audit(db, user, shop, kind, {"record_id": record.id, "status": status})
    return record


def commit(db, record):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Concurrent modification; reload and retry") from exc
    return dump(record)


@router.get("/shops/available")
def shops(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if "pricing.view" not in effective_permissions(db, user):
        raise HTTPException(403, "Pricing permission required")
    allowed = user_allowed_shop_ids(db, user)
    query = db.query(DimShop).filter_by(active=True)
    if allowed is not None:
        query = query.filter(DimShop.id.in_(allowed))
    return {"shops": [{"id": s.id, "name": s.name} for s in query.order_by(DimShop.id)]}


def reference_access(db, user, record):
    source = record.data.get("source_shop_id")
    if source is None and record.kind == "config":
        source = record.data["config"].get("schedule_source_shop_id")
    if source:
        access(db, user, source)


@router.get("/{shop_id}/overview", response_model=OverviewOutput)
def overview(shop_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from scheduled_channelmanager import scheduler_status
    access(db, user, shop_id)
    config = latest(db, shop_id, "config")
    if config:
        reference_access(db, user, config)
    last_run = latest(db, shop_id, "run")
    if last_run:
        reference_access(db, user, last_run)
    permissions = effective_permissions(db, user)
    return {"config": dump(config), "basis": dump(latest(db, shop_id, "basis", True)),
            "last_run": dump(last_run), "history_limit": 50,
            "external_formats": "provisional_unconfirmed", "schedule_timezone": "UTC",
            "scheduler": scheduler_status(),
            "can_propose": "pricing.propose" in permissions, "can_approve": "pricing.approve" in permissions,
            "can_export": "pricing.approve" in permissions,
            "queues": {status: db.query(Snapshot).filter_by(shop_id=shop_id, status=status).count()
                       for status in ("staged", "preview", "approved", "exported", "partial", "failed", "running")},
            "counts": {kind: db.query(Snapshot).filter_by(shop_id=shop_id, kind=kind).count()
                       for kind in ("basis", "calculation", "export", "readback", "run")}}


@router.get("/{shop_id}/history", response_model=HistoryOutput)
def history(shop_id: int, kind: str = Query(pattern="^(config|basis|calculation|export|readback|run)$"),
            offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
            db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id)
    records = db.query(Snapshot).filter_by(shop_id=shop_id, kind=kind).order_by(
        Snapshot.revision.desc()).offset(offset).limit(limit + 1).all()
    for record in records:
        reference_access(db, user, record)
    return {"items": [dump(r) for r in records[:limit]], "has_more": len(records) > limit}


@router.get("/{shop_id}/records/{record_id}", response_model=SnapshotOutput)
def record(shop_id: int, record_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id)
    result = get_record(db, shop_id, record_id)
    reference_access(db, user, result)
    return dump(result)


@router.post("/{shop_id}/config", response_model=SnapshotOutput)
def configure(shop_id: int, body: ConfigInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    source = body.config.schedule_source_shop_id or shop_id
    access(db, user, source)
    lock(db, shop_id, source)
    current = latest(db, shop_id, "config")
    if (current.revision if current else 0) != body.expected_revision:
        raise HTTPException(409, "Configuration revision changed")
    return commit(db, add(db, user, shop_id, "config", body.model_dump(), "active"))


def stage(db, user, shop_id, body):
    lock(db, shop_id)
    return commit(db, add(db, user, shop_id, "basis", body.model_dump(), "staged"))


@router.post("/{shop_id}/basis", response_model=SnapshotOutput)
def basis(shop_id: int, body: BasisInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    return stage(db, user, shop_id, body)


async def csv_input(file, settings):
    try:
        parsed = json.loads(settings)
        options = CSVSettings.model_validate({k: parsed.pop(k) for k in ("mapping", "delimiter", "decimal") if k in parsed})
        rows = parse_csv(await file.read(2 * 1024 * 1024 + 1), options)
        return parsed, rows
    except (ValueError, TypeError, UnicodeError, csv_module.Error, AttributeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{shop_id}/basis-csv", response_model=SnapshotOutput)
async def basis_csv(shop_id: int, settings: str = Form(...), file: UploadFile = File(...),
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    parsed, rows = await csv_input(file, settings)
    try:
        body = BasisInput.model_validate({**parsed, "rows": rows})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return stage(db, user, shop_id, body)


@router.post("/{shop_id}/basis/{record_id}/approve", response_model=SnapshotOutput)
def approve_basis(shop_id: int, record_id: int, body: Notes, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    lock(db, shop_id)
    item = get_record(db, shop_id, record_id, "basis")
    db.refresh(item)
    if item.status != "staged":
        raise HTTPException(409, "Basis is not staged")
    current = latest(db, shop_id, "basis", True)
    if current and current.revision > item.revision:
        raise HTTPException(409, "Newer basis is already approved")
    item.status = "approved"
    item.data = {**item.data, "approval": {"by": user.username, "notes": body.notes,
                                         "at": datetime.now(timezone.utc).isoformat()}}
    audit(db, user, shop_id, "approve_basis", {"id": item.id, "notes": body.notes})
    return commit(db, item)


def make_calculation(db, user, shop_id, source_shop_id, basis_id):
    config = latest(db, shop_id, "config")
    basis = get_record(db, source_shop_id, basis_id, "basis")
    if not config or basis.status != "approved":
        raise HTTPException(409, "Active configuration and approved basis required")
    if latest(db, source_shop_id, "basis", True).id != basis.id:
        raise HTTPException(409, "Selected basis is superseded")
    cross_shop = source_shop_id != shop_id
    calculation_basis = basis.data
    if cross_shop:
        calculation_basis = {**basis.data, "rows": [
            {**row, "source_current_price": row["current_price"], "current_price": None}
            for row in basis.data["rows"]]}
    try:
        rows = calculate(calculation_basis, config.data["config"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return add(db, user, shop_id, "calculation",
               {"source_shop_id": source_shop_id, "basis_id": basis.id, "config_id": config.id,
                "config": config.data["config"], "rows": rows,
                "current_price_note": "Destination current price unavailable; source current prices are not destination actuals."
                    if cross_shop else "Current prices supplied explicitly in this shop's approved basis.",
                "cost_provenance": {"source_shop_id": source_shop_id, "basis_id": basis.id,
                                    "provenance": basis.data["provenance"], "cost_basis": "net",
                                    "note": "Explicit imported source costs; not inferred historical or destination-specific purchase costs."},
                "export_schema": config.data["config"]["export_columns"],
                "csv_preview": export_csv(rows[:5], config.data["config"]) if not any(r["errors"] for r in rows) else None,
                "blocked_rows": sum(bool(r["errors"]) for r in rows)}, "preview")


@router.post("/{shop_id}/calculate", response_model=SnapshotOutput)
def calculate_route(shop_id: int, body: CalculationInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    access(db, user, body.source_shop_id)
    lock(db, shop_id, body.source_shop_id)
    return commit(db, make_calculation(db, user, shop_id, body.source_shop_id, body.basis_id))


def fresh(db, user, shop_id, item):
    source = item.data["source_shop_id"]
    access(db, user, source)
    lock(db, shop_id, source)
    config, basis = latest(db, shop_id, "config"), latest(db, source, "basis", True)
    if not config or not basis or config.id != item.data["config_id"] or basis.id != item.data["basis_id"]:
        raise HTTPException(409, "Stale calculation: basis or configuration changed")
    if item.data["blocked_rows"]:
        raise HTTPException(422, "Resolve blocked rows and recalculate")


@router.post("/{shop_id}/calculations/{record_id}/approve", response_model=SnapshotOutput)
def approve_calculation(shop_id: int, record_id: int, body: Notes, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    item = get_record(db, shop_id, record_id, "calculation")
    fresh(db, user, shop_id, item)
    db.refresh(item)
    if item.status != "preview":
        raise HTTPException(409, "Calculation is not awaiting approval")
    item.status = "approved"
    item.data = {**item.data, "approval": {"by": user.username, "notes": body.notes,
                                         "at": datetime.now(timezone.utc).isoformat()}}
    audit(db, user, shop_id, "approve_calculation", {"id": item.id, "notes": body.notes})
    return commit(db, item)


@router.post("/{shop_id}/calculations/{record_id}/export", response_model=SnapshotOutput)
def export(shop_id: int, record_id: int, body: Notes, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    item = get_record(db, shop_id, record_id, "calculation")
    fresh(db, user, shop_id, item)
    db.refresh(item)
    if item.status != "approved":
        raise HTTPException(409, "Calculation must be approved")
    claim = f"export:{item.id}"
    existing = db.query(Snapshot).filter_by(shop_id=shop_id, claim=claim).first()
    if existing:
        return dump(existing)
    csv = export_csv(item.data["rows"], item.data["config"])
    return commit(db, add(db, user, shop_id, "export",
        {**item.data, "calculation_id": item.id, "notes": body.notes, "csv": csv,
         "schema": item.data["config"]["export_columns"],
         "fingerprint": hashlib.sha256(csv.encode()).hexdigest(),
         "processed": False}, "exported", claim))


@router.get("/{shop_id}/exports/{record_id}/download")
def download(shop_id: int, record_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.approve")
    item = get_record(db, shop_id, record_id, "export")
    reference_access(db, user, item)
    audit(db, user, shop_id, "download", {"export_id": item.id})
    db.commit()
    return Response(item.data["csv"], media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="channel-export-{item.id}.csv"'})


@router.post("/{shop_id}/exports/{record_id}/readback", response_model=SnapshotOutput)
async def readback(shop_id: int, record_id: int, settings: str = Form(...), file: UploadFile = File(...),
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    item = get_record(db, shop_id, record_id, "export")
    reference_access(db, user, item)
    parsed, rows = await csv_input(file, settings)
    try:
        semantics = Semantics.model_validate(parsed)
        config = item.data["config"]
        if semantics.currency != config["currency"] or semantics.price_basis != config["price_basis"] or number(semantics.vat_rate) != number(config["vat_rate"]):
            raise ValueError("Readback currency / VAT / price basis must match export exactly")
        for row in rows:
            if set(row) != {"sku", "actual_price"} or not row["sku"] or row["actual_price"] is None or number(row["actual_price"]) < 0:
                raise ValueError("Readback requires SKU and nonnegative actual_price")
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    counts = Counter(r["sku"] for r in rows)
    actual = {r["sku"]: r["actual_price"] for r in rows}
    targets = {r["sku"]: r["target_price"] for r in item.data["rows"]}
    missing = sorted(set(targets) - set(actual))
    unexpected = sorted(set(actual) - set(targets))
    duplicates = sorted(k for k, n in counts.items() if n > 1)
    comparisons = [{"sku": sku, "target_price": target, "actual_price": actual.get(sku),
                    "matched": sku in actual and counts[sku] == 1 and abs(number(actual[sku]) - number(target)) <= number(config["readback_tolerance"])}
                   for sku, target in targets.items()]
    complete = not missing and not unexpected and not duplicates and all(r["matched"] for r in comparisons)
    lock(db, shop_id)
    return commit(db, add(db, user, shop_id, "readback",
        {"export_id": item.id, "source_shop_id": item.data["source_shop_id"],
         "fingerprint": item.data["fingerprint"], "rows": comparisons, "received_rows": rows,
         "missing": missing, "unexpected": unexpected, "duplicates": duplicates,
         "matched_count": sum(r["matched"] for r in comparisons), "processed": complete},
        "matched" if complete else "partial"))


def daily_run(db, user, shop_id):
    """One durable claim per UTC shop/date; failures visible and never silently retried."""
    config = latest(db, shop_id, "config")
    source = (config.data["config"].get("schedule_source_shop_id") if config else None) or shop_id
    access(db, user, source)
    lock(db, shop_id, source)
    claim = f"daily:{datetime.now(timezone.utc).date().isoformat()}"
    prior = db.query(Snapshot).filter_by(shop_id=shop_id, claim=claim).first()
    if prior:
        return dump(prior)
    run = add(db, user, shop_id, "run", {"source_shop_id": source, "timezone": "UTC",
              "started_at": datetime.now(timezone.utc).isoformat()}, "running", claim)
    db.commit()
    try:
        lock(db, shop_id, source)
        current = latest(db, shop_id, "config")
        current_source = (current.data["config"].get("schedule_source_shop_id") if current else None) or shop_id
        if current_source != source:
            raise HTTPException(409, "Schedule source changed; retry on next UTC day")
        base = latest(db, source, "basis", True)
        if not base:
            raise HTTPException(409, "No approved basis for schedule source")
        calculation = make_calculation(db, user, shop_id, source, base.id)
        run.status = "success"
        run.data = {**run.data, "calculation_id": calculation.id}
    except Exception as exc:
        db.rollback()
        run = db.get(Snapshot, run.id)
        run.status = "failed"
        run.data = {**run.data, "error": str(getattr(exc, "detail", exc))[:2000]}
    run.data = {**run.data, "finished_at": datetime.now(timezone.utc).isoformat()}
    audit(db, user, shop_id, "daily_run", {"id": run.id, "status": run.status})
    return commit(db, run)


@router.post("/{shop_id}/run", response_model=SnapshotOutput)
def run(shop_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    access(db, user, shop_id, "pricing.propose")
    return daily_run(db, user, shop_id)
