"""Authenticated staged daily mode, intentionally separate from DRS YTD replace."""
import json
import csv
import io
from zipfile import BadZipFile
from datetime import date
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2 import IntegrityError as PgIntegrityError
import auth
import models
from database import get_db
from services.product_identity import authorize_shop, IdentityIndex
from services.drs_daily import TEMPLATE, DEFAULT_MAPPING, create_preview, confirm_stage, confirm_mappings
from services.drs_daily import preview_resolution, confirm_resolution, revalidate_stage

router = APIRouter(prefix="/api/uploads/drs-daily", tags=["drs"])
editor = auth.require_role("admin", "pricing_manager")


class DailyConfirmation(BaseModel):
    confirm_mapping: bool = False


class ResolutionAction(BaseModel):
    row: int
    action: str
    sku_id: str | None = None


class ResolutionRequest(BaseModel):
    actions: list[ResolutionAction]


class ResolutionConfirmation(BaseModel):
    resolution_id: str
    confirm: bool = False


@router.get("/templates")
def templates(user=Depends(editor)):
    return [{"id": TEMPLATE, "name": "DRS Sales: twee kopregels, dagelijkse triples",
             "mapping": DEFAULT_MAPPING, "currency": "EUR", "return_semantics": "unverified"}]


@router.post("/preview")
def preview(file: UploadFile = File(...), shop_id: int = Form(...), year: int = Form(...),
            period_start: date = Form(...), period_end: date = Form(...),
            template: str = Form(TEMPLATE), mapping: str = Form("{}"),
            db: Session = Depends(get_db), user=Depends(editor)):
    authorize_shop(db, user, shop_id)
    if template != TEMPLATE:
        raise HTTPException(422, "Onbekend dagverkooptemplate.")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(422, "Dit template vereist XLSX.")
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(413, "Bestand groter dan 50 MB.")
    try:
        parsed_mapping = json.loads(mapping)
        if not isinstance(parsed_mapping, dict):
            raise ValueError("Kolomkoppeling moet een JSON-object zijn.")
        return create_preview(db, user, shop_id, file.file, year, period_start, period_end, parsed_mapping)
    except (ValueError, KeyError, StopIteration, BadZipFile) as exc:
        db.rollback()
        raise HTTPException(422, str(exc))


def get_stage(db, user, stage_id):
    stage = db.get(models.DrsDailyStage, stage_id)
    if not stage:
        raise HTTPException(404, "Preview niet gevonden.")
    authorize_shop(db, user, stage.shop_id)
    return stage


@router.get("/{stage_id}")
def status(stage_id: str, db: Session = Depends(get_db), user=Depends(editor)):
    stage = get_stage(db, user, stage_id)
    return {**stage.preview, "status": stage.status, "result": stage.result,
            "mapping_result": stage.mapping_result}


@router.get("/{stage_id}/unresolved")
def unresolved(stage_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
               db: Session = Depends(get_db), user=Depends(editor), q: str = ""):
    stage = get_stage(db, user, stage_id)
    errors = stage.preview.get("errors", [])
    needle = q.strip().casefold()
    incomplete = stage.preview.get("metadata_version") != 2
    if needle and incomplete:
        raise HTTPException(409, "Oude preview is onvolledig; upload opnieuw voor volledig zoeken.")
    if needle:
        errors = [error for error in errors if any(needle in str(error.get(field) or "").casefold()
                  for field in ("code", "product_name", "ean", "oem", "message"))]
    return {"items": errors[offset:offset + limit], "total": len(errors) if needle else stage.preview["error_count"],
            "offset": offset, "limit": limit,
            "requires_fresh_upload": incomplete}


@router.get("/{stage_id}/unresolved/export")
def export_unresolved(stage_id: str, db: Session = Depends(get_db), user=Depends(editor)):
    stage = get_stage(db, user, stage_id)
    if stage.preview.get("metadata_version") != 2:
        raise HTTPException(409, "Oude preview is onvolledig; upload opnieuw voor volledige export.")
    output = io.StringIO()
    writer = csv.writer(output)
    fields = ["row", "code", "product_name", "ean", "oem", "message", "candidates"]
    writer.writerow(fields)
    for error in stage.preview["errors"]:
        values = [json.dumps(error.get(k, []), ensure_ascii=False) if k == "candidates"
                  else str(error.get(k) or "") for k in fields]
        # Spreadsheet formula injection defense, preserving original values in JSON API.
        writer.writerow(["'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="drs-{stage.id}-unresolved.csv"'})


@router.get("/{stage_id}/products")
def products(stage_id: str, q: str = "", offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
             db: Session = Depends(get_db), user=Depends(editor)):
    stage = get_stage(db, user, stage_id)
    index = IdentityIndex(db, stage.shop_id)
    needle = q.strip().lower()
    items = [index.candidate(s) for s in sorted(index.products)]
    items = [p for p in items if not needle or any(needle in str(p[k] or "").lower()
             for k in ("sku_id", "business_sku", "product_name", "ean", "oem"))]
    return {"items": items[offset:offset + limit], "total": len(items), "offset": offset, "limit": limit}


def repair_transaction(db, operation):
    try:
        return operation()
    except (IntegrityError, PgIntegrityError):
        db.rollback()
        raise HTTPException(409, "Gelijktijdige identiteitwijziging; vraag een nieuwe impactpreview.")
    except Exception:
        db.rollback()
        raise


@router.post("/{stage_id}/resolution-preview")
def resolution_preview(stage_id: str, body: ResolutionRequest, db: Session = Depends(get_db), user=Depends(editor)):
    stage = get_stage(db, user, stage_id)
    return repair_transaction(db, lambda: preview_resolution(db, user, stage, [a.model_dump() for a in body.actions]))


@router.post("/{stage_id}/resolution-confirm")
def resolution_confirm(stage_id: str, body: ResolutionConfirmation, db: Session = Depends(get_db), user=Depends(editor)):
    stage = get_stage(db, user, stage_id)
    return repair_transaction(db, lambda: confirm_resolution(db, user, stage, body.resolution_id, body.confirm))


@router.post("/{stage_id}/revalidate")
def revalidate(stage_id: str, db: Session = Depends(get_db), user=Depends(editor)):
    stage = get_stage(db, user, stage_id)
    return repair_transaction(db, lambda: revalidate_stage(db, user, stage))


@router.post("/{stage_id}/confirm-mappings")
def mappings(stage_id: str, body: DailyConfirmation, db: Session = Depends(get_db), user=Depends(editor)):
    stage = get_stage(db, user, stage_id)
    try:
        return confirm_mappings(db, stage, body.confirm_mapping)
    except (IntegrityError, PgIntegrityError):
        db.rollback()
        raise HTTPException(409, "Gelijktijdige artikelmapping; maak een nieuwe preview.")
    except Exception:
        db.rollback()
        raise


@router.post("/{stage_id}/confirm")
def confirm(stage_id: str, body: DailyConfirmation, db: Session = Depends(get_db), user=Depends(editor)):
    stage = get_stage(db, user, stage_id)
    try:
        return confirm_stage(db, stage, body.confirm_mapping)
    except (IntegrityError, PgIntegrityError):
        db.rollback()
        raise HTTPException(409, "Gelijktijdige wijziging in artikelmapping/dagclaim; maak een nieuwe preview.")
    except Exception:
        db.rollback()
        raise