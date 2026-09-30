"""Authenticated staged daily mode, intentionally separate from DRS YTD replace."""
import json
from zipfile import BadZipFile
from datetime import date
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2 import IntegrityError as PgIntegrityError
import auth
import models
from database import get_db
from services.product_identity import authorize_shop
from services.drs_daily import TEMPLATE, DEFAULT_MAPPING, create_preview, confirm_stage, confirm_mappings

router = APIRouter(prefix="/api/uploads/drs-daily", tags=["drs"])
editor = auth.require_role("admin", "pricing_manager")


class DailyConfirmation(BaseModel):
    confirm_mapping: bool = False


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