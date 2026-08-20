"""CSV, XLSX and XLS upload endpoints for all data types.

File parsing/decoding and low-level validation primitives live in the
central Data Integration Engine (`engine/import_engine.py`) and are reused
here rather than duplicated — the same module backs the PriceShape and DRS
import routes.
"""
import io
import zipfile
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils
from engine.import_engine import (
    file_to_rows as _file_to_rows,
    safe_float as _safe_float,
    safe_int as _safe_int,
    validate_ean as _validate_ean,
    new_batch_id as _new_batch_id,
    PREVIEW_ROW_LIMIT,
)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


async def _process_upload(
    file: UploadFile,
    upload_type: str,
    db: Session,
    user: models.User,
    processor,
) -> dict:
    """Generic upload processor that creates an import job."""
    fname = file.filename or "unknown.csv"
    file_ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "csv"
    job = models.ImportJob(
        upload_type=upload_type,
        filename=fname,
        status="nieuw",
        uploaded_by=user.username,
        created_at=datetime.utcnow(),
        source="Handmatig",
        file_type=file_ext,
        batch_id=_new_batch_id(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        content = await file.read()
        file_warnings: list = []
        rows = _file_to_rows(content, fname, file_warnings)
        rows, duplicates = _dedupe_rows(rows, file_warnings)
        processed, failed, warnings = processor(rows, db)
        warnings = file_warnings + warnings
        # Structurele waarschuwingen (zoals onbekende kolommen) mogen nooit
        # wegvallen door de cap op warnings_json/error_log wanneer er veel
        # rij-waarschuwingen (bv. duplicaten) zijn — zet ze vooraan.
        warnings = ([w for w in warnings if w.startswith("Onbekende kolommen")]
                    + [w for w in warnings if not w.startswith("Onbekende kolommen")])
        job.rows_processed = processed
        job.rows_failed = failed
        job.rows_duplicates = duplicates
        job.status = "geimporteerd"
        job.completed_at = datetime.utcnow()
        job.warnings_json = warnings[:50]
        job.error_log = [{"rij": None, "bericht": w} for w in warnings[:100]]
        db.commit()
        return {
            "job_id": job.id,
            "batch_id": job.batch_id,
            "rows_processed": processed,
            "rows_failed": failed,
            "rows_duplicates": duplicates,
            "warnings": warnings,
            "message": f"Uploaded {processed} rows successfully",
        }
    except Exception as e:
        db.rollback()
        job.status = "fout"
        job.error_message = str(e)
        job.error_log = [{"rij": None, "bericht": str(e)[:500]}]
        job.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")


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
_DATUM_KOLOMMEN_SET = {"date", "datum", "start_date", "startdatum", "end_date", "einddatum", "txn_date"}
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


# Alle kolommen die de product-/Paper_Copy-import daadwerkelijk leest
# (incl. pilot-aliassen) of valideert. Al het overige wordt stil genegeerd
# en moet daarom als waarschuwing worden gerapporteerd (zelfde patroon als
# de supplier-contentimport, §23).
_PRODUCT_BEKENDE_KOLOMMEN: set[str] = {
    "sku_id", "own_sku_id",
    "product_name", "brand", "category", "subcategory", "product_group",
    "strategy_type", "lifecycle_status",
    "is_private_label", "is_a_brand",
    "cost_price", "cost_price_exc_vat", "inkoopprijs",
    "current_price", "current_sales_price_inc_vat", "current_sales_price",
    "verkoopprijs",
    "min_price", "min_price_inc_vat",
    "max_price", "max_price_inc_vat",
    # Paper_Copy-specifieke velden
    "paper_size", "paper_weight_gsm", "sheets_per_pack",
} | _EAN_KOLOMMEN_SET


def _collect_unknown_columns(rows, known: set[str]) -> set[str]:
    """Bepaal onbekende kolommen op basis van de bestandsheaders zelf —
    onafhankelijk van rij-geldigheid en ook bij een bestand zonder datarijen."""
    headers = list(getattr(rows, "headers", None) or [])
    if not headers and rows:
        headers = [k.lower().strip() for k in rows[0].keys() if isinstance(k, str)]
    return {h for h in headers if h and h.lower().strip() not in known}


def _process_products(rows, db: Session):
    processed, failed, warnings = 0, 0, []
    unknown_columns = _collect_unknown_columns(rows, _PRODUCT_BEKENDE_KOLOMMEN)
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
    if unknown_columns:
        warnings.insert(0, (
            f"Onbekende kolommen genegeerd: {', '.join(sorted(unknown_columns))}. "
            f"Waarden in deze kolommen zijn NIET geïmporteerd. Geldige kolommen: "
            f"{', '.join(sorted(_PRODUCT_BEKENDE_KOLOMMEN))}."
        ))
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
        "supplier-content": [
            ["sku_id", "own_sku_id"],
        ],
        "loyalty-members": [
            ["pseudonymous_customer_id", "customer_id", "klant_id"],
        ],
        "loyalty-transactions": [
            ["pseudonymous_customer_id", "customer_id", "klant_id"],
            ["date", "datum", "txn_date"],
            ["txn_type", "transactie_type", "type"],
            ["points_delta", "points", "punten"],
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
    DATUM_KOLOMMEN = {"date", "datum", "start_date", "startdatum", "end_date", "einddatum", "txn_date"}
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

        if i <= PREVIEW_ROW_LIMIT:
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
    source: str | None = Query(None, description="Filter op bron: PriceShape, DRS, Handmatig, Paper_Copy"),
    status: str | None = Query(None, description="Filter op status uit de importlevenscyclus"),
    upload_type: str | None = Query(None, description="Filter op importtype"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Importgeschiedenis over alle bronnen (Handmatig, PriceShape, DRS, Paper_Copy).
    Bedoeld om herbruikt te worden door een toekomstige 'Data Integratie'
    dashboardpagina; ondersteunt filteren op bron/status/type.
    """
    q = db.query(models.ImportJob)
    if source:
        q = q.filter(models.ImportJob.source == source)
    if status:
        q = q.filter(models.ImportJob.status == status)
    if upload_type:
        q = q.filter(models.ImportJob.upload_type == upload_type)
    jobs = q.order_by(models.ImportJob.created_at.desc()).limit(limit).all()
    return [
        {
            "id": j.id,
            "upload_type": j.upload_type,
            "filename": j.filename,
            "status": j.status,
            "source": j.source,
            "file_type": j.file_type,
            "import_mode": j.import_mode,
            "batch_id": j.batch_id,
            "rows_processed": j.rows_processed,
            "rows_failed": j.rows_failed,
            "rows_duplicates": j.rows_duplicates or 0,
            "error_log": j.error_log or [],
            "error_message": j.error_message,
            "warnings": j.warnings_json or [],
            "uploaded_by": j.uploaded_by,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
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
                from services.domain_normalize import register_competitor_sighting
                _comp_raw = _r(row, "competitor_name", "concurrent_naam", "concurrentnaam")
                _row_date = date.fromisoformat(date_raw.strip())
                # Canoniek domein: uploads mogen geen www./https-varianten als
                # aparte concurrenten aanmaken; de ruwe schrijfwijze blijft
                # herleidbaar als alias in het concurrentenregister.
                _comp_canon = register_competitor_sighting(db, _comp_raw,
                                                           seen_date=_row_date)
                entry = models.FactCompetitorPriceDaily(
                    date=_row_date,
                    sku_id=sku_id,
                    competitor_name=_comp_canon or "Unknown",
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
    totaal_duplicaten = 0

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

        rows, dup_count = _dedupe_rows(rows, file_warns)
        job = models.ImportJob(
            upload_type=upload_type,
            filename=f"{file.filename}::{csv_name}",
            status="processing",
            uploaded_by=current_user.username,
            created_at=datetime.utcnow(),
            source="Handmatig",
            batch_id=_new_batch_id(),
            rows_duplicates=dup_count,
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
                        from services.domain_normalize import register_competitor_sighting
                        _comp_raw = _r(row, "competitor_name", "concurrent_naam")
                        _row_date = _date.fromisoformat(date_raw.strip())
                        # Canoniek domein + ruwe schrijfwijze als alias in het
                        # register (zie services.domain_normalize).
                        _comp_canon = register_competitor_sighting(
                            db, _comp_raw, seen_date=_row_date)
                        entry = models.FactCompetitorPriceDaily(
                            date=_row_date,
                            sku_id=sku_id,
                            competitor_name=_comp_canon or "Unknown",
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
            job.warnings_json = (file_warns + warns)[:50]
            job.error_log = [{"rij": None, "bericht": w} for w in (file_warns + warns)[:100]]
            db.commit()

            totaal_verwerkt += proc
            totaal_mislukt += fail
            totaal_duplicaten += dup_count
            all_warns = file_warns + warns
            results.append({
                "bestand": csv_name,
                "type": upload_type,
                "status": "voltooid",
                "rows_processed": proc,
                "rows_failed": fail,
                "rows_duplicates": dup_count,
                "warnings": all_warns[:10],
            })

        except Exception as e:
            db.rollback()
            job.status = "failed"
            job.error_message = str(e)
            job.error_log = [{"rij": None, "bericht": str(e)[:500]}]
            job.completed_at = datetime.utcnow()
            db.commit()
            results.append({"bestand": csv_name, "type": upload_type, "status": "mislukt", "reden": str(e)})

    return {
        "bestanden": len(csv_names),
        "totaal_verwerkt": totaal_verwerkt,
        "totaal_mislukt": totaal_mislukt,
        "totaal_duplicaten": totaal_duplicaten,
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


# ---------------------------------------------------------------------------
# Loyalty & Customer Value Intelligence imports (§22, §64.5)
# Er is nog geen live loyalty-databron: CSV/XLSX-import is de primaire route.
# Ledger-mutaties lopen uitsluitend via engine.loyalty_intelligence
# (apply_ledger_entry) zodat wallet-saldi transactioneel correct blijven.
# ---------------------------------------------------------------------------

def _process_loyalty_members(rows, db: Session):
    from engine import loyalty_intelligence as li
    li.ensure_default_tiers(db)
    processed, failed, warnings = 0, 0, []
    for i, row in enumerate(rows, start=1):
        try:
            if not _enforce_row_validation(row, i, warnings):
                failed += 1
                continue
            pid = _r(row, "pseudonymous_customer_id", "customer_id", "klant_id")
            if not pid:
                failed += 1
                warnings.append(f"Rij {i} overgeslagen: pseudonymous_customer_id ontbreekt")
                continue
            joined = _r(row, "joined_at", "lid_sinds")
            joined_date = None
            if joined:
                try:
                    joined_date = datetime.strptime(joined, "%Y-%m-%d").date()
                except ValueError:
                    warnings.append(f"Rij {i}: joined_at '{joined}' ongeldig (YYYY-MM-DD) — genegeerd")
            existing = db.query(models.LoyaltyMember).filter(
                models.LoyaltyMember.pseudonymous_customer_id == pid).first()
            if existing:
                if joined_date:
                    existing.joined_at = joined_date
                if _r(row, "tier_code", "tier"):
                    existing.tier_code = _r(row, "tier_code", "tier").lower()
                if _r(row, "status"):
                    existing.status = _r(row, "status").lower()
                if _r(row, "referral_code"):
                    existing.referral_code = _r(row, "referral_code")
                if _r(row, "referred_by"):
                    existing.referred_by = _r(row, "referred_by")
            else:
                member = models.LoyaltyMember(
                    pseudonymous_customer_id=pid,
                    joined_at=joined_date,
                    tier_code=(_r(row, "tier_code", "tier") or "bronze").lower(),
                    status=(_r(row, "status") or "active").lower(),
                    referral_code=_r(row, "referral_code"),
                    referred_by=_r(row, "referred_by"),
                    consent_marketing=str(row.get("consent_marketing", "false")).lower() in ("1", "true", "yes"),
                    is_demo_data=False,
                )
                db.add(member)
                db.flush()
                li.ensure_wallet(db, member.id)
            processed += 1
        except Exception as e:
            warnings.append(f"Rij {i}: {str(e)}")
            failed += 1
    db.commit()
    return processed, failed, warnings


_LOYALTY_TXN_TYPES = {"earn", "redeem", "expire", "adjust", "referral_bonus", "campaign_bonus"}


def _process_loyalty_transactions(rows, db: Session):
    from engine import loyalty_intelligence as li
    processed, failed, warnings = 0, 0, []
    member_cache: dict[str, models.LoyaltyMember] = {}
    for i, row in enumerate(rows, start=1):
        try:
            if not _enforce_row_validation(row, i, warnings):
                failed += 1
                continue
            pid = _r(row, "pseudonymous_customer_id", "customer_id", "klant_id")
            txn_type = (_r(row, "txn_type", "transactie_type", "type") or "").lower()
            datum = _r(row, "date", "datum", "txn_date")
            punten = _safe_int(_r(row, "points_delta", "points", "punten"))
            if not pid or not datum or punten is None or not txn_type:
                failed += 1
                warnings.append(f"Rij {i} overgeslagen: verplicht veld ontbreekt")
                continue
            if txn_type not in _LOYALTY_TXN_TYPES:
                failed += 1
                warnings.append(f"Rij {i}: onbekend txn_type '{txn_type}' (geldig: {sorted(_LOYALTY_TXN_TYPES)})")
                continue
            try:
                txn_date = datetime.strptime(datum, "%Y-%m-%d").date()
            except ValueError:
                failed += 1
                warnings.append(f"Rij {i}: ongeldige datum '{datum}' (YYYY-MM-DD)")
                continue
            member = member_cache.get(pid) or db.query(models.LoyaltyMember).filter(
                models.LoyaltyMember.pseudonymous_customer_id == pid).first()
            if not member:
                failed += 1
                warnings.append(f"Rij {i}: lid '{pid}' onbekend — importeer eerst loyalty-members")
                continue
            member_cache[pid] = member
            try:
                li.apply_ledger_entry(
                    db, member, txn_date, txn_type, punten,
                    order_reference=_r(row, "order_reference", "order_ref"),
                    order_value=_safe_float(_r(row, "order_value", "orderbedrag")),
                    description=_r(row, "description", "omschrijving"),
                    external_ref=_r(row, "external_ref", "externe_ref"),
                    is_demo_data=False,
                )
            except li.LedgerError as le:
                failed += 1
                warnings.append(f"Rij {i}: {str(le)}")
                continue
            processed += 1
        except Exception as e:
            warnings.append(f"Rij {i}: {str(e)}")
            failed += 1
    db.commit()
    return processed, failed, warnings


@router.post("/loyalty-members")
async def upload_loyalty_members(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    return await _process_upload(file, "loyalty-members", db, current_user, _process_loyalty_members)


@router.post("/loyalty-transactions")
async def upload_loyalty_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    return await _process_upload(file, "loyalty-transactions", db, current_user, _process_loyalty_transactions)

def _dedupe_rows(rows: list[dict], warnings: list) -> tuple[list[dict], int]:
    """
    Dedupliceer rijen binnen een batch op basis van SKU (+datum en concurrent
    indien aanwezig). Retourneert (unieke_rijen, aantal_duplicaten) en voegt per
    overgeslagen duplicaat een waarschuwing toe zodat het foutlog vermeldt welke
    rijen als duplicaat zijn overgeslagen. Zo laat één dubbele rij niet de hele
    upload op de primary key mislukken.
    """
    from engine.import_engine import RowList
    seen: dict[tuple, int] = {}
    unique: list[dict] = RowList()
    unique.headers = list(getattr(rows, "headers", None) or [])
    dups = 0
    for i, row in enumerate(rows, start=1):
        norm = {k.lower().strip(): (v or "").strip() for k, v in row.items() if isinstance(k, str)}
        sku = norm.get("own_sku_id") or norm.get("sku_id") or ""
        if not sku:
            unique.append(row)
            continue
        key = (sku, norm.get("date") or norm.get("datum") or "",
               norm.get("competitor_name") or norm.get("concurrent_naam") or "")
        if key in seen:
            dups += 1
            warnings.append(
                f"Rij {i}: duplicaat van rij {seen[key]} (SKU '{sku}'"
                + (f", datum {key[1]}" if key[1] else "")
                + ") — overgeslagen als duplicaat"
            )
        else:
            seen[key] = i
            unique.append(row)
    return unique, dups


# ─── PIM: supplier-contentimport (§23) ───────────────────────────────────────

def _process_supplier_content(rows, db: Session):
    """
    Leveranciers-contentimport: rijen met sku_id + attribuutkolommen
    (kolomnamen = attribuutcodes, bv. description, color, material).
    Source ownership (§4): waarden van een andere eigenaar (DRS/Handmatig/AI)
    worden NIET stil overschreven — dat levert een conflictwaarschuwing op.
    Alleen lege velden of bestaande Leverancier-waarden worden bijgewerkt.
    """
    from engine import pim_engine
    pim_engine.ensure_defaults(db)
    defs = {d.code.lower(): d for d in db.query(models.PimAttributeDefinition)
            .filter(models.PimAttributeDefinition.active == True).all()}  # noqa: E712

    processed, failed, warnings = 0, 0, []
    # Kolomvalidatie op basis van de headers zelf (§23) — onafhankelijk van
    # rij-geldigheid of lege cellen, en ook bij een bestand zonder datarijen.
    headers = list(getattr(rows, "headers", None) or [])
    if not headers and rows:
        headers = [k.lower().strip() for k in rows[0].keys() if isinstance(k, str)]
    unknown_columns: set[str] = {
        h for h in headers
        if h and h not in ("sku_id", "own_sku_id") and h not in defs
    }
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
            product = db.query(models.DimProduct).filter(
                models.DimProduct.sku_id == sku_id).first()
            if product is None:
                failed += 1
                warnings.append(f"Rij {i} overgeslagen: SKU '{sku_id}' bestaat niet in de productmaster (DRS)")
                continue

            row_norm = {k.lower().strip(): (v or "").strip() for k, v in row.items()
                        if isinstance(k, str)}
            updated_any = False
            for col, val in row_norm.items():
                if col in ("sku_id", "own_sku_id") or not val:
                    continue
                d = defs.get(col)
                if d is None:
                    # Onbekende kolom (bv. via afwijkende rij-keys): ook rapporteren
                    unknown_columns.add(col)
                    continue
                existing = db.query(models.PimAttributeValue).filter(
                    models.PimAttributeValue.sku_id == sku_id,
                    models.PimAttributeValue.attribute_id == d.id).first()
                # Centrale ownership-policy (§4): DRS-owned velden en waarden
                # van andere bronnen worden nooit stil overgenomen.
                reason = pim_engine.check_write_allowed(d, existing, "Leverancier")
                if reason:
                    if existing is None or (existing.value or "") != val:
                        warnings.append(f"Rij {i}: conflict voor {sku_id} — {reason} "
                                        f"Leverancierswaarde ('{val}') is niet toegepast.")
                    continue
                if existing is None:
                    db.add(models.PimAttributeValue(
                        sku_id=sku_id, attribute_id=d.id, value=val,
                        source="Leverancier", updated_by="supplier_import"))
                    updated_any = True
                elif existing.value != val:
                    existing.value = val
                    existing.updated_by = "supplier_import"
                    updated_any = True
            processed += 1
        except Exception as e:
            warnings.append(f"Rij {i}: {str(e)}")
            failed += 1
    if unknown_columns:
        geldige = ", ".join(sorted(defs.keys()))
        warnings.insert(0, (
            f"Onbekende kolommen genegeerd (geen bekend attribuut): "
            f"{', '.join(sorted(unknown_columns))}. Waarden in deze kolommen zijn NIET "
            f"geïmporteerd. Geldige attribuutcodes: {geldige}. "
            f"Download het CSV-sjabloon via /api/uploads/supplier-content/template."
        ))
    db.commit()
    return processed, failed, warnings

@router.get("/supplier-content/template")
def supplier_content_template(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """CSV-sjabloon voor de leveranciers-contentimport: sku_id + alle geldige
    (actieve) attribuutcodes uit pim_attribute_definition als kolomkoppen."""
    from engine import pim_engine
    pim_engine.ensure_defaults(db)
    codes = [d.code for d in db.query(models.PimAttributeDefinition)
             .filter(models.PimAttributeDefinition.active == True)  # noqa: E712
             .order_by(models.PimAttributeDefinition.code).all()]
    header = ",".join(["sku_id"] + codes)
    csv_content = header + "\n"
    from fastapi.responses import Response
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="supplier_content_sjabloon.csv"'},
    )
@router.post("/supplier-content")
async def upload_supplier_content(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Leveranciers-contentimport (PIM §23): attribuutwaarden per SKU."""
    return await _process_upload(file, "supplier-content", db, current_user, _process_supplier_content)
