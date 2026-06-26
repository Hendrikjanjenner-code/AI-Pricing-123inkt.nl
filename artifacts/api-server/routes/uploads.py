"""CSV and XLSX upload endpoints for all data types."""
import io
import csv
import zipfile
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils


def _decode_csv_bytes(content: bytes) -> str:
    """
    Decode raw CSV bytes to text, robust to the encodings end users actually
    produce: UTF-8 (with/without BOM), Windows-1252/CP1252 (Excel default on
    Western-European Windows), classic Mac Roman, and Latin-1.

    Strategy:
      1. Prefer strict UTF-8 (handles BOM) — the modern default.
      2. Otherwise use charset-normalizer to detect the legacy code page so
         that special chars (€, smart quotes, accented letters) survive.
      3. Fall back to CP1252, then Latin-1 (never raises — every byte maps).
    """
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass

    try:
        from charset_normalizer import from_bytes

        # Constrain detection to the encodings end users actually produce.
        # Without this, charset-normalizer mis-detects short Western-European
        # text as Eastern-European code pages (e.g. cp775, mac_latin2), which
        # garbles €, smart quotes and accented characters.
        match = from_bytes(
            content,
            cp_isolation=["utf_8", "cp1252", "mac_roman", "latin_1"],
        ).best()
        if match is not None and match.encoding:
            try:
                return content.decode(match.encoding)
            except (UnicodeDecodeError, LookupError):
                pass
    except ImportError:
        pass

    # Deterministic fallback: CP1252 (Excel/Windows default) before Latin-1, so
    # bytes 0x80–0x9F map to € and smart quotes instead of control characters.
    try:
        return content.decode("cp1252")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _file_to_rows(content: bytes, filename: str, warnings: list | None = None) -> list[dict]:
    """
    Parse uploaded file bytes into a list of row dicts.
    Supports .csv (UTF-8/CP1252/Mac-Roman/Latin-1) and .xlsx (first sheet only).
    Values are always returned as strings to match csv.DictReader behaviour.
    If an XLSX contains multiple sheets, an informative warning is appended to
    the optional `warnings` list — the first sheet is always used.
    """
    fname = (filename or "").lower()
    if fname.endswith(".xlsx"):
        try:
            import openpyxl
        except ImportError:
            raise HTTPException(status_code=500, detail="openpyxl is niet geïnstalleerd; XLSX niet ondersteund")
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        if len(wb.worksheets) > 1 and warnings is not None:
            sheet_names = ", ".join(ws.title for ws in wb.worksheets)
            warnings.append(
                f"Alleen het eerste werkblad wordt ingelezen (werkbladen gevonden: {sheet_names})"
            )
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(c).strip() if c is not None else "" for c in next(rows_iter, [])]
        if not headers:
            wb.close()
            return []
        rows = []
        for row in rows_iter:
            row_dict = {}
            for h, v in zip(headers, row):
                row_dict[h] = "" if v is None else str(v).strip()
            rows.append(row_dict)
        wb.close()
        return rows
    else:
        text = _decode_csv_bytes(content)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


async def _process_upload(
    file: UploadFile,
    upload_type: str,
    db: Session,
    user: models.User,
    processor,
) -> dict:
    """Generic upload processor that creates an import job."""
    job = models.ImportJob(
        upload_type=upload_type,
        filename=file.filename or "unknown.csv",
        status="processing",
        uploaded_by=user.username,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        content = await file.read()
        file_warnings: list = []
        rows = _file_to_rows(content, file.filename or "", file_warnings)
        processed, failed, warnings = processor(rows, db)
        warnings = file_warnings + warnings
        job.rows_processed = processed
        job.rows_failed = failed
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
        return {
            "job_id": job.id,
            "rows_processed": processed,
            "rows_failed": failed,
            "warnings": warnings,
            "message": f"Uploaded {processed} rows successfully",
        }
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")


def _safe_float(val: str | None) -> float | None:
    try:
        return float(val) if val and val.strip() else None
    except (ValueError, TypeError):
        return None


def _safe_int(val: str | None) -> int | None:
    try:
        return int(val) if val and val.strip() else None
    except (ValueError, TypeError):
        return None


def _r(row: dict, *keys: str) -> str | None:
    """Return first non-empty value matching any of the alias keys."""
    for k in keys:
        v = (row.get(k) or row.get(k.upper()) or "").strip()
        if v:
            return v
    return None


def _normalize_sku(row: dict) -> str:
    """Resolve sku_id from own_sku_id / sku_id / SKU_ID aliases."""
    return _r(row, "own_sku_id", "sku_id", "SKU_ID") or ""


_PRIJS_KOLOMMEN_SET = {
    "price", "cost_price", "current_price", "min_price", "max_price",
    "revenue", "cost", "margin", "discount_value",
    "price_inc_vat", "price_incl_vat", "price_incl_btw",
    "current_sales_price_inc_vat", "current_sales_price",
    "cost_price_exc_vat", "inkoopprijs",
    "revenue_inc_vat", "revenue_incl_vat", "revenue_incl_btw",
    "competitor_price_inc_vat", "competitor_price_incl_vat",
    "verkoopprijs", "verkoopprijs_incl_btw", "prijs_concurrent",
    "korting_waarde",
}
_DATUM_KOLOMMEN_SET = {"date", "datum", "start_date", "startdatum", "end_date", "einddatum"}
_EAN_KOLOMMEN_SET = {"ean", "ean_code", "ean13", "ean8", "barcode"}


def _enforce_row_validation(row: dict, rij: int, warnings: list) -> bool:
    """
    Run the same strict validation rules as the /validate endpoint on a single row.
    Returns True if the row is acceptable, False if it must be skipped.
    Appends warnings for every violation found.
    """
    row_norm = {k.lower().strip(): v for k, v in row.items()}
    invalid = False

    for kol in _PRIJS_KOLOMMEN_SET:
        val = (row_norm.get(kol) or "").strip()
        if val:
            try:
                f = float(val)
                if f <= 0:
                    warnings.append(f"Rij {rij}: {kol} moet > 0 zijn ({val}) — rij overgeslagen")
                    invalid = True
            except ValueError:
                warnings.append(f"Rij {rij}: {kol} heeft ongeldige waarde '{val}' — rij overgeslagen")
                invalid = True

    for kol in _DATUM_KOLOMMEN_SET:
        val = (row_norm.get(kol) or "").strip()
        if val:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                warnings.append(f"Rij {rij}: {kol} heeft ongeldig datumformaat '{val}' (verwacht YYYY-MM-DD) — rij overgeslagen")
                invalid = True

    for kol in _EAN_KOLOMMEN_SET:
        val = (row_norm.get(kol) or "").strip()
        if val and not _validate_ean(val):
            warnings.append(f"Rij {rij}: {kol} heeft ongeldig EAN '{val}' — rij overgeslagen")
            invalid = True

    return not invalid


def _validate_ean(ean: str) -> bool:
    """Check EAN-13 or EAN-8 check-digit. Returns True if valid."""
    ean = ean.strip().replace(" ", "")
    if not ean.isdigit():
        return False
    if len(ean) == 13:
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(ean[:12]))
        return (10 - (total % 10)) % 10 == int(ean[12])
    if len(ean) == 8:
        weights = [3, 1, 3, 1, 3, 1, 3]
        total = sum(int(d) * w for d, w in zip(ean[:7], weights))
        return (10 - (total % 10)) % 10 == int(ean[7])
    return False


def _process_products(rows, db: Session):
    processed, failed, warnings = 0, 0, []
    for i, row in enumerate(rows, start=1):
        try:
            if not _enforce_row_validation(row, i, warnings):
                failed += 1
                continue

            sku_id = _normalize_sku(row)
            if not sku_id:
                failed += 1
                warnings.append(f"Rij {i} overgeslagen: sku_id / own_sku_id ontbreekt")
                continue

            # Support pilot VAT-inclusive price aliases
            cost_price = _safe_float(_r(row, "cost_price", "cost_price_exc_vat", "inkoopprijs"))
            current_price = _safe_float(_r(row, "current_price", "current_sales_price_inc_vat",
                                           "current_sales_price", "verkoopprijs"))
            min_price = _safe_float(_r(row, "min_price", "min_price_inc_vat"))
            max_price = _safe_float(_r(row, "max_price", "max_price_inc_vat"))

            # Paper_Copy specific fields
            paper_size = (row.get("paper_size") or "").strip() or None
            paper_weight_gsm = _safe_int(row.get("paper_weight_gsm"))
            sheets_per_pack = _safe_int(row.get("sheets_per_pack"))

            existing = db.query(models.DimProduct).filter(models.DimProduct.sku_id == sku_id).first()
            if existing:
                if row.get("product_name"):
                    existing.product_name = row["product_name"]
                if row.get("brand"):
                    existing.brand = row["brand"]
                if row.get("category"):
                    existing.category = row["category"]
                if row.get("subcategory"):
                    existing.subcategory = row["subcategory"]
                if row.get("strategy_type"):
                    existing.strategy_type = row["strategy_type"]
                if cost_price is not None:
                    existing.cost_price = cost_price
                if current_price is not None:
                    existing.current_price = current_price
                if min_price is not None:
                    existing.min_price = min_price
                if max_price is not None:
                    existing.max_price = max_price
                if paper_size:
                    existing.paper_size = paper_size
                if paper_weight_gsm is not None:
                    existing.paper_weight_gsm = paper_weight_gsm
                if sheets_per_pack is not None:
                    existing.sheets_per_pack = sheets_per_pack
                if row.get("is_private_label"):
                    existing.is_private_label = str(row["is_private_label"]).lower() in ("1", "true", "yes")
                if row.get("is_a_brand"):
                    existing.is_a_brand = str(row["is_a_brand"]).lower() in ("1", "true", "yes")
                if row.get("lifecycle_status"):
                    existing.lifecycle_status = row["lifecycle_status"]
            else:
                product = models.DimProduct(
                    sku_id=sku_id,
                    product_name=row.get("product_name", sku_id),
                    brand=row.get("brand"),
                    category=row.get("category"),
                    subcategory=row.get("subcategory"),
                    product_group=row.get("product_group"),
                    is_private_label=str(row.get("is_private_label", "false")).lower() in ("1", "true", "yes"),
                    is_a_brand=str(row.get("is_a_brand", "false")).lower() in ("1", "true", "yes"),
                    lifecycle_status=row.get("lifecycle_status", "active"),
                    strategy_type=row.get("strategy_type"),
                    cost_price=cost_price,
                    min_price=min_price,
                    max_price=max_price,
                    current_price=current_price,
                    paper_size=paper_size,
                    paper_weight_gsm=paper_weight_gsm,
                    sheets_per_pack=sheets_per_pack,
                )
                db.add(product)
            processed += 1
        except Exception as e:
            warnings.append(f"Row error: {str(e)}")
            failed += 1
    db.commit()
    return processed, failed, warnings


@router.post("/validate")
async def validate_csv(
    file: UploadFile = File(...),
    upload_type: str = "products",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Valideer een CSV-bestand zonder op te slaan.
    Retourneert een gestructureerd validatierapport met:
    - rij-aantallen (totaal / geldig / ongeldig)
    - ontbrekende verplichte kolommen (incl. pilot-aliassen)
    - EAN-validatie (EAN-13 checksum + EAN-8 checksum)
    - dubbele SKU-ID's
    - ongeldige prijs-/datumwaarden
    - fouten gegroepeerd op type
    - preview van de eerste 10 rijen
    """
    # Each inner list = set of acceptable column aliases for that requirement
    VERPLICHTE_KOLOMMEN: dict[str, list[list[str]]] = {
        "products": [
            ["sku_id", "own_sku_id"],
            ["product_name", "naam", "productnaam"],
            ["cost_price", "cost_price_exc_vat", "inkoopprijs"],
            ["current_price", "current_sales_price_inc_vat", "current_sales_price", "verkoopprijs"],
        ],
        "sales": [
            ["date", "datum"],
            ["sku_id", "own_sku_id"],
            ["units_sold", "quantity_sold", "aantallen"],
            ["revenue", "revenue_inc_vat", "revenue_incl_vat", "revenue_incl_btw"],
        ],
        "prices": [
            ["date", "datum"],
            ["sku_id", "own_sku_id"],
            ["price", "price_inc_vat", "price_incl_vat", "price_incl_btw", "verkoopprijs_incl_btw"],
        ],
        "competitor-prices": [
            ["date", "datum"],
            ["sku_id", "own_sku_id"],
            ["competitor_name", "concurrent_naam", "concurrentnaam"],
            ["price", "competitor_price_inc_vat", "competitor_price_incl_vat", "prijs_concurrent"],
        ],
        "traffic": [
            ["date", "datum"],
            ["sku_id", "own_sku_id"],
            ["sessions"],
            ["pageviews"],
        ],
        "promotions": [
            ["sku_id", "own_sku_id"],
            ["promotion_type", "promotie_type"],
            ["discount_value", "korting_waarde"],
            ["start_date", "startdatum"],
        ],
        "inventory": [
            ["date", "datum"],
            ["sku_id", "own_sku_id"],
            ["stock_quantity", "voorraad"],
        ],
        "substitutions": [
            ["a_brand_sku", "a_merk_sku"],
            ["private_label_sku", "huismerk_sku"],
        ],
    }
    PRIJS_KOLOMMEN = {
        "price", "cost_price", "current_price", "min_price", "max_price",
        "revenue", "cost", "margin", "discount_value",
        "price_inc_vat", "price_incl_vat", "price_incl_btw",
        "current_sales_price_inc_vat", "current_sales_price",
        "cost_price_exc_vat", "inkoopprijs",
        "revenue_inc_vat", "revenue_incl_vat", "revenue_incl_btw",
        "competitor_price_inc_vat", "competitor_price_incl_vat",
        "verkoopprijs", "verkoopprijs_incl_btw", "prijs_concurrent",
        "discount_value", "korting_waarde",
    }
    DATUM_KOLOMMEN = {"date", "datum", "start_date", "startdatum", "end_date", "einddatum"}
    EAN_KOLOMMEN = {"ean", "ean_code", "ean13", "ean8", "barcode"}

    content = await file.read()
    fname = file.filename or ""
    waarschuwingen: list[str] = []
    try:
        alle_rijen = _file_to_rows(content, fname, waarschuwingen)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bestand kon niet worden ingelezen: {str(e)}")

    if not alle_rijen:
        return {"rows_total": 0, "rows_valid": 0, "rows_failed": 0,
                "missing_fields": [], "duplicate_skus": [], "errors": [],
                "errors_by_type": {}, "preview": [], "warnings": [], "kan_importeren": False}

    kolommen = {k.lower().strip() for k in alle_rijen[0].keys()}
    vereist_groepen = VERPLICHTE_KOLOMMEN.get(upload_type, [])

    # A requirement is satisfied if ANY alias in its group appears in the column set
    ontbrekend: list[str] = []
    for groep in vereist_groepen:
        if not any(alias.lower() in kolommen for alias in groep):
            ontbrekend.append(groep[0])  # Report the canonical field name

    fouten: list[dict] = []
    sku_gezien: dict[str, list[int]] = {}
    preview: list[dict] = []
    geldig = 0
    mislukt = 0
    totaal = 0

    for i, row in enumerate(alle_rijen, start=1):
        totaal += 1
        rij_geldig = True
        row_norm = {k.lower().strip(): v for k, v in row.items()}

        # Check required fields (using alias groups)
        for groep in vereist_groepen:
            aanwezig = False
            for alias in groep:
                val = (row_norm.get(alias.lower()) or "").strip()
                if val:
                    aanwezig = True
                    break
            if not aanwezig:
                fouten.append({
                    "rij": i, "veld": groep[0], "type": "ontbrekend",
                    "bericht": f'Verplicht veld "{groep[0]}" (of alias) ontbreekt of is leeg',
                })
                rij_geldig = False

        # Price validation
        for kol in PRIJS_KOLOMMEN:
            val = (row_norm.get(kol) or "").strip()
            if val:
                try:
                    f = float(val)
                    if f <= 0:
                        fouten.append({"rij": i, "veld": kol, "type": "ongeldige_prijs",
                                       "bericht": f"Prijs moet > 0 zijn: {val}"})
                        rij_geldig = False
                except ValueError:
                    fouten.append({"rij": i, "veld": kol, "type": "ongeldige_prijs",
                                   "bericht": f'Niet-numerieke prijs: "{val}"'})
                    rij_geldig = False

        # Date validation
        for kol in DATUM_KOLOMMEN:
            val = (row_norm.get(kol) or "").strip()
            if val:
                try:
                    datetime.strptime(val, "%Y-%m-%d")
                except ValueError:
                    fouten.append({"rij": i, "veld": kol, "type": "ongeldig_datum",
                                   "bericht": f'Ongeldig datumformaat: "{val}" (verwacht YYYY-MM-DD)'})
                    rij_geldig = False

        # EAN validation
        for kol in EAN_KOLOMMEN:
            val = (row_norm.get(kol) or "").strip()
            if val and not _validate_ean(val):
                fouten.append({"rij": i, "veld": kol, "type": "ongeldig_ean",
                               "bericht": f'Ongeldig EAN: "{val}" (verwacht EAN-13 of EAN-8 met geldige checkdigit)'})
                rij_geldig = False

        # SKU dedup tracking (accept own_sku_id alias)
        sku = (row_norm.get("own_sku_id") or row_norm.get("sku_id") or "").strip()
        if sku:
            sku_gezien.setdefault(sku, []).append(i)

        if rij_geldig:
            geldig += 1
        else:
            mislukt += 1

        if i <= 10:
            preview.append(row_norm)

    dubbele_skus = [sku for sku, rijen in sku_gezien.items() if len(rijen) > 1]
    if dubbele_skus:
        waarschuwingen.append(
            f"{len(dubbele_skus)} dubbele SKU-ID('s) gevonden: {', '.join(dubbele_skus[:5])}"
            + (f" en {len(dubbele_skus)-5} meer" if len(dubbele_skus) > 5 else "")
        )

    # Group errors by type
    fouten_per_type: dict[str, int] = {}
    for f in fouten:
        fouten_per_type[f.get("type", "overige")] = fouten_per_type.get(f.get("type", "overige"), 0) + 1

    return {
        "upload_type": upload_type,
        "bestandsnaam": file.filename,
        "rows_total": totaal,
        "rows_valid": geldig,
        "rows_failed": mislukt,
        "missing_fields": ontbrekend,
        "duplicate_skus": dubbele_skus[:20],
        "errors": fouten[:50],
        "errors_by_type": fouten_per_type,
        "preview": preview,
        "warnings": waarschuwingen,
        "kan_importeren": len(ontbrekend) == 0 and geldig > 0,
    }


@router.get("")
def list_uploads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    jobs = db.query(models.ImportJob).order_by(models.ImportJob.created_at.desc()).limit(50).all()
    return [
        {
            "id": j.id,
            "upload_type": j.upload_type,
            "filename": j.filename,
            "status": j.status,
            "rows_processed": j.rows_processed,
            "rows_failed": j.rows_failed,
            "error_message": j.error_message,
            "uploaded_by": j.uploaded_by,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.post("/products")
async def upload_products(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    return await _process_upload(file, "products", db, current_user, _process_products)


@router.post("/sales")
async def upload_sales(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    async def _inner():
        def _proc(rows, db):
            processed, failed, warnings = 0, 0, []
            from datetime import date
            for i, row in enumerate(rows, start=1):
                try:
                    if not _enforce_row_validation(row, i, warnings):
                        failed += 1
                        continue
                    sku_id = _normalize_sku(row)
                    if not sku_id:
                        failed += 1
                        warnings.append(f"Rij {i} overgeslagen: sku_id / own_sku_id ontbreekt")
                        continue
                    rev_raw = _r(row, "revenue_inc_vat", "revenue_incl_vat", "revenue_incl_btw", "revenue")
                    date_raw = _r(row, "date", "datum")
                    entry = models.FactSalesDaily(
                        date=date.fromisoformat(date_raw.strip()),
                        sku_id=sku_id,
                        units_sold=_safe_int(_r(row, "units_sold", "quantity_sold", "aantallen")) or 0,
                        revenue=_safe_float(rev_raw),
                        cost=_safe_float(_r(row, "cost", "cost_exc_vat", "kosten")),
                        margin=_safe_float(_r(row, "margin", "marge")),
                        margin_pct=_safe_float(_r(row, "margin_pct", "margin_percentage", "marge_pct")),
                    )
                    db.add(entry)
                    processed += 1
                except Exception as e:
                    warnings.append(str(e))
                    failed += 1
            db.commit()
            return processed, failed, warnings
        return await _process_upload(file, "sales", db, current_user, _proc)
    return await _inner()


@router.post("/prices")
async def upload_prices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        from datetime import date
        for i, row in enumerate(rows, start=1):
            try:
                if not _enforce_row_validation(row, i, warnings):
                    failed += 1
                    continue
                sku_id = _normalize_sku(row)
                if not sku_id:
                    failed += 1
                    continue
                price_raw = _r(row, "price_inc_vat", "price_incl_vat", "price_incl_btw",
                               "verkoopprijs_incl_btw", "price")
                cost_raw = _r(row, "cost_price_exc_vat", "cost_price_excl_vat", "inkoopprijs", "cost_price")
                date_raw = _r(row, "date", "datum")
                entry = models.FactPriceDaily(
                    date=date.fromisoformat(date_raw.strip()),
                    sku_id=sku_id,
                    price=_safe_float(price_raw),
                    cost_price=_safe_float(cost_raw),
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "prices", db, current_user, _proc)


@router.post("/competitor-prices")
async def upload_competitor_prices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        from datetime import date
        for i, row in enumerate(rows, start=1):
            try:
                if not _enforce_row_validation(row, i, warnings):
                    failed += 1
                    continue
                sku_id = _normalize_sku(row)
                if not sku_id:
                    failed += 1
                    continue
                price_raw = _r(row, "competitor_price_inc_vat", "competitor_price_incl_vat",
                               "price_inc_vat", "price_incl_vat", "prijs_concurrent", "price")
                date_raw = _r(row, "date", "datum")
                entry = models.FactCompetitorPriceDaily(
                    date=date.fromisoformat(date_raw.strip()),
                    sku_id=sku_id,
                    competitor_name=_r(row, "competitor_name", "concurrent_naam", "concurrentnaam") or "Unknown",
                    price=_safe_float(price_raw),
                    url=_r(row, "url", "product_url", "link"),
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "competitor_prices", db, current_user, _proc)


@router.post("/traffic")
async def upload_traffic(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Importeer traffic/GA4 data per SKU per dag (pilotformaat).

    Verwacht CSV met kolommen: date, sku_id, sessions, pageviews,
    add_to_cart (opt), orders (opt), conversion_rate (opt), channel (opt).
    """
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        for i, row in enumerate(rows, start=1):
            try:
                if not _enforce_row_validation(row, i, warnings):
                    failed += 1
                    continue
                date_raw = _r(row, "date", "datum")
                if not date_raw:
                    failed += 1
                    warnings.append(f"Rij {i} overgeslagen: datum ontbreekt")
                    continue
                date_val = datetime.strptime(date_raw.strip(), "%Y-%m-%d").date()
                sku_id = _normalize_sku(row)
                if not sku_id:
                    failed += 1
                    warnings.append(f"Rij {i} overgeslagen: sku_id / own_sku_id ontbreekt")
                    continue
                entry = models.FactTrafficDaily(
                    date=date_val,
                    entity_type="SKU",
                    entity_id=sku_id,
                    sessions=_safe_int(_r(row, "sessions")) or 0,
                    pageviews=_safe_int(_r(row, "pageviews")) or 0,
                    add_to_cart=_safe_int(_r(row, "add_to_cart", "add_to_basket")) or 0,
                    orders=_safe_int(_r(row, "orders", "bestellingen")) or 0,
                    unique_visitors=_safe_int(_r(row, "unique_visitors", "unieke_bezoekers")) or 0,
                    bounce_rate=_safe_float(_r(row, "bounce_rate", "bouncepercentage")),
                )
                db.add(entry)
                processed += 1
            except (KeyError, ValueError) as e:
                warnings.append(str(e))
                failed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "traffic", db, current_user, _proc)


@router.post("/inventory")
async def upload_inventory(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        from datetime import date
        for i, row in enumerate(rows, start=1):
            try:
                if not _enforce_row_validation(row, i, warnings):
                    failed += 1
                    continue
                sku_id = _normalize_sku(row)
                if not sku_id:
                    failed += 1
                    continue
                entry = models.FactInventoryDaily(
                    date=date.fromisoformat(_r(row, "date", "datum").strip()),
                    sku_id=sku_id,
                    stock_quantity=int(_r(row, "stock_quantity", "voorraad") or 0),
                    days_of_stock=_safe_float(_r(row, "days_of_stock", "voorraaddagen")),
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "inventory", db, current_user, _proc)


@router.post("/substitutions")
async def upload_substitutions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        for i, row in enumerate(rows, start=1):
            try:
                if not _enforce_row_validation(row, i, warnings):
                    failed += 1
                    continue
                a = _r(row, "a_brand_sku", "a_merk_sku") or ""
                pl = _r(row, "private_label_sku", "huismerk_sku") or ""
                if not a or not pl:
                    failed += 1
                    warnings.append(f"Rij {i}: a_brand_sku / private_label_sku ontbreken")
                    continue
                entry = models.MapSubstitution(
                    a_brand_sku=a,
                    private_label_sku=pl,
                    substitution_strength=_safe_float(_r(row, "substitution_strength")) or 1.0,
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "substitutions", db, current_user, _proc)


@router.post("/basket-affinity")
async def upload_basket_affinity(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        for i, row in enumerate(rows, start=1):
            try:
                if not _enforce_row_validation(row, i, warnings):
                    failed += 1
                    continue
                a = _r(row, "sku_id_a") or ""
                b = _r(row, "sku_id_b") or ""
                if not a or not b:
                    failed += 1
                    continue
                entry = models.FactBasketAffinity(
                    sku_id_a=a,
                    sku_id_b=b,
                    affinity_score=_safe_float(_r(row, "affinity_score")) or 0.0,
                    co_purchase_count=_safe_int(_r(row, "co_purchase_count")) or 0,
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "basket_affinity", db, current_user, _proc)


@router.post("/promotions")
async def upload_promotions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Importeer promoties per SKU (pilot: promotions CSV formaat)."""
    def _proc(rows, db):
        from datetime import datetime as _dt
        processed, failed, warnings = 0, 0, []
        for i, row in enumerate(rows, start=1):
            try:
                if not _enforce_row_validation(row, i, warnings):
                    failed += 1
                    continue
                sku_id = _normalize_sku(row)
                promo_type = _r(row, "promotion_type", "promotie_type", "promo_type") or ""
                start_raw = _r(row, "start_date", "startdatum", "start") or ""
                if not sku_id or not start_raw:
                    failed += 1
                    warnings.append(f"SKU {sku_id}: sku_id / own_sku_id en start_date / startdatum zijn verplicht")
                    continue
                try:
                    start_date = _dt.strptime(start_raw.strip(), "%Y-%m-%d").date()
                except ValueError:
                    failed += 1
                    warnings.append(f"Ongeldig datumformaat: {start_raw}")
                    continue
                end_date = None
                end_raw = _r(row, "end_date", "einddatum", "einde") or ""
                if end_raw.strip():
                    try:
                        end_date = _dt.strptime(end_raw.strip(), "%Y-%m-%d").date()
                    except ValueError:
                        warnings.append(f"Ongeldig einddatum: {end_raw}")
                discount_val = None
                disc_raw = _r(row, "discount_value", "korting_waarde", "korting")
                if disc_raw:
                    try:
                        discount_val = float(disc_raw.strip())
                        if discount_val <= 0:
                            warnings.append(f"Ongeldige korting voor SKU {sku_id}: {discount_val} (moet > 0 zijn)")
                            discount_val = None
                    except ValueError:
                        pass
                entry = models.Promotion(
                    sku_id=sku_id,
                    promotion_type=promo_type or None,
                    discount_value=discount_val,
                    start_date=start_date,
                    end_date=end_date,
                    channel=_r(row, "channel", "kanaal") or None,
                    description=_r(row, "description", "omschrijving") or None,
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "promotions", db, current_user, _proc)


def _detect_csv_type(kolommen: set[str]) -> str | None:
    """Auto-detect upload type from CSV column names."""
    kols = {k.lower().strip() for k in kolommen}

    def has_any(*keys):
        return any(k in kols for k in keys)

    if has_any("competitor_name", "concurrent_naam", "concurrentnaam", "competitor_price_inc_vat", "prijs_concurrent"):
        return "competitor-prices"
    if has_any("promotion_type", "promotie_type", "promo_type"):
        return "promotions"
    if has_any("product_name", "productnaam", "naam") and has_any("cost_price", "cost_price_exc_vat", "inkoopprijs"):
        return "products"
    if has_any("units_sold", "quantity_sold", "aantallen") and has_any("revenue", "revenue_inc_vat"):
        return "sales"
    if has_any("price_inc_vat", "price_incl_vat", "verkoopprijs_incl_btw") or (
        has_any("price") and has_any("date", "datum") and not has_any("sessions")
    ):
        return "prices"
    return None


def _detect_type_by_filename(name: str) -> str | None:
    n = name.lower()
    if any(x in n for x in ("product", "catalog", "catalogus", "master")):
        return "products"
    if any(x in n for x in ("sales", "verkoop", "omzet")):
        return "sales"
    if any(x in n for x in ("competitor", "concurrent", "competition")):
        return "competitor-prices"
    if any(x in n for x in ("promo",)):
        return "promotions"
    if any(x in n for x in ("price", "prijs")) and "competitor" not in n:
        return "prices"
    return None


@router.post("/bulk")
async def upload_bulk(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """
    Combineer-upload: accepteert een ZIP met meerdere CSV-bestanden.
    Elk CSV-bestand wordt automatisch herkend op basis van kolomnamen of bestandsnaam.
    Ondersteunde types: products, sales, prices, competitor-prices, promotions.
    """
    content = await file.read()

    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise HTTPException(status_code=400, detail="Bestand is geen geldig ZIP-archief (.zip verwacht)")

    zf = zipfile.ZipFile(io.BytesIO(content))
    csv_names = [
        n for n in zf.namelist()
        if (n.lower().endswith(".csv") or n.lower().endswith(".xlsx"))
        and not n.startswith("__MACOSX")
    ]

    if not csv_names:
        raise HTTPException(status_code=400, detail="ZIP bevat geen CSV- of XLSX-bestanden")

    PROCESSORS = {
        "products": _process_products,
    }

    results = []
    totaal_verwerkt = 0
    totaal_mislukt = 0

    for csv_name in csv_names:
        raw = zf.read(csv_name)
        file_warns: list = []
        try:
            rows = _file_to_rows(raw, csv_name, file_warns)
        except Exception as e:
            results.append({"bestand": csv_name, "type": "onbekend", "status": "overgeslagen", "reden": str(e)})
            continue

        if not rows:
            results.append({"bestand": csv_name, "type": "onbekend", "status": "overgeslagen", "reden": "Leeg bestand"})
            continue

        kolommen = set(rows[0].keys())

        upload_type = _detect_type_by_filename(csv_name) or _detect_csv_type(kolommen)
        if not upload_type:
            results.append({"bestand": csv_name, "type": "onbekend", "status": "overgeslagen",
                            "reden": "Type niet herkend op basis van kolomnamen of bestandsnaam"})
            continue

        job = models.ImportJob(
            upload_type=upload_type,
            filename=f"{file.filename}::{csv_name}",
            status="processing",
            uploaded_by=current_user.username,
            created_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        try:
            from datetime import date as _date

            if upload_type == "products":
                proc, fail, warns = _process_products(rows, db)

            elif upload_type == "sales":
                proc, fail, warns = 0, 0, []
                for i, row in enumerate(rows, start=1):
                    try:
                        if not _enforce_row_validation(row, i, warns):
                            fail += 1; continue
                        sku_id = _normalize_sku(row)
                        if not sku_id:
                            fail += 1; continue
                        rev_raw = _r(row, "revenue_inc_vat", "revenue_incl_vat", "revenue_incl_btw", "revenue")
                        date_raw = _r(row, "date", "datum")
                        entry = models.FactSalesDaily(
                            date=_date.fromisoformat(date_raw.strip()),
                            sku_id=sku_id,
                            units_sold=_safe_int(_r(row, "units_sold", "quantity_sold", "aantallen")) or 0,
                            revenue=_safe_float(rev_raw),
                            cost=_safe_float(_r(row, "cost", "cost_exc_vat")),
                            margin=_safe_float(_r(row, "margin", "marge")),
                            margin_pct=_safe_float(_r(row, "margin_pct", "marge_pct")),
                        )
                        db.add(entry); proc += 1
                    except Exception as e:
                        warns.append(str(e)); fail += 1
                db.commit()

            elif upload_type == "prices":
                proc, fail, warns = 0, 0, []
                for i, row in enumerate(rows, start=1):
                    try:
                        if not _enforce_row_validation(row, i, warns):
                            fail += 1; continue
                        sku_id = _normalize_sku(row)
                        if not sku_id:
                            fail += 1; continue
                        price_raw = _r(row, "price_inc_vat", "price_incl_vat", "verkoopprijs_incl_btw", "price")
                        cost_raw = _r(row, "cost_price_exc_vat", "inkoopprijs", "cost_price")
                        date_raw = _r(row, "date", "datum")
                        entry = models.FactPriceDaily(
                            date=_date.fromisoformat(date_raw.strip()),
                            sku_id=sku_id,
                            price=_safe_float(price_raw),
                            cost_price=_safe_float(cost_raw),
                        )
                        db.add(entry); proc += 1
                    except Exception as e:
                        warns.append(str(e)); fail += 1
                db.commit()

            elif upload_type == "competitor-prices":
                proc, fail, warns = 0, 0, []
                for i, row in enumerate(rows, start=1):
                    try:
                        if not _enforce_row_validation(row, i, warns):
                            fail += 1; continue
                        sku_id = _normalize_sku(row)
                        if not sku_id:
                            fail += 1; continue
                        price_raw = _r(row, "competitor_price_inc_vat", "prijs_concurrent", "price")
                        date_raw = _r(row, "date", "datum")
                        entry = models.FactCompetitorPriceDaily(
                            date=_date.fromisoformat(date_raw.strip()),
                            sku_id=sku_id,
                            competitor_name=_r(row, "competitor_name", "concurrent_naam") or "Unknown",
                            price=_safe_float(price_raw),
                            url=_r(row, "url", "product_url"),
                        )
                        db.add(entry); proc += 1
                    except Exception as e:
                        warns.append(str(e)); fail += 1
                db.commit()

            elif upload_type == "promotions":
                proc, fail, warns = 0, 0, []
                from datetime import datetime as _dt
                for i, row in enumerate(rows, start=1):
                    try:
                        if not _enforce_row_validation(row, i, warns):
                            fail += 1; continue
                        sku_id = _normalize_sku(row)
                        start_raw = _r(row, "start_date", "startdatum") or ""
                        if not sku_id or not start_raw:
                            fail += 1; continue
                        start_date = _dt.strptime(start_raw.strip(), "%Y-%m-%d").date()
                        end_date = None
                        end_raw = _r(row, "end_date", "einddatum") or ""
                        if end_raw.strip():
                            try:
                                end_date = _dt.strptime(end_raw.strip(), "%Y-%m-%d").date()
                            except ValueError:
                                pass
                        disc_raw = _r(row, "discount_value", "korting_waarde")
                        discount_val = None
                        if disc_raw:
                            try:
                                discount_val = float(disc_raw.strip())
                                if discount_val <= 0:
                                    discount_val = None
                            except ValueError:
                                pass
                        entry = models.Promotion(
                            sku_id=sku_id,
                            promotion_type=_r(row, "promotion_type", "promotie_type") or None,
                            discount_value=discount_val,
                            start_date=start_date,
                            end_date=end_date,
                            channel=_r(row, "channel", "kanaal") or None,
                            description=_r(row, "description", "omschrijving") or None,
                        )
                        db.add(entry); proc += 1
                    except Exception as e:
                        warns.append(str(e)); fail += 1
                db.commit()

            else:
                proc, fail, warns = 0, 0, []

            job.rows_processed = proc
            job.rows_failed = fail
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

            totaal_verwerkt += proc
            totaal_mislukt += fail
            all_warns = file_warns + warns
            results.append({
                "bestand": csv_name,
                "type": upload_type,
                "status": "voltooid",
                "rows_processed": proc,
                "rows_failed": fail,
                "warnings": all_warns[:10],
            })

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
            results.append({"bestand": csv_name, "type": upload_type, "status": "mislukt", "reden": str(e)})

    return {
        "bestanden": len(csv_names),
        "totaal_verwerkt": totaal_verwerkt,
        "totaal_mislukt": totaal_mislukt,
        "resultaten": results,
    }


@router.post("/price-rules")
async def upload_price_rules(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        for row in rows:
            try:
                product = db.query(models.DimProduct).filter(
                    models.DimProduct.sku_id == row.get("sku_id")
                ).first()
                if product:
                    if row.get("min_price"):
                        product.min_price = float(row["min_price"])
                    if row.get("max_price"):
                        product.max_price = float(row["max_price"])
                    processed += 1
                else:
                    failed += 1
                    warnings.append(f"SKU {row.get('sku_id')} not found")
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "price_rules", db, current_user, _proc)
