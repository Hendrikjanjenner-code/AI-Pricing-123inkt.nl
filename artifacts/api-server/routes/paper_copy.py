"""
Paper_Copy product master import — dedicated, persistent single-sheet XLSX importer.

Distinct from routes/drs.py (two-tab Sales+Hierarchy importer). This importer reads the
real "Test Document AI Pricing Papier.xlsx" single-sheet layout:
productcode, Titel, Merk, Soort, EAN, OEM, Afzet/Omzet/Marge_YTD (x3 years),
Inkoopprijs ex BTW, Verkoopprijs excl/incl BTW, gemiddeld aantal stuks per order (x3),
Aanmaakdatum, Eerste verkoop, Active/Inactive, productHierarchy.

Endpoints:
  POST /api/uploads/paper-copy/validate  — validate only, no DB writes (except job log)
  POST /api/uploads/paper-copy/save      — upsert into dim_product (append/update/replace)
  GET  /api/uploads/paper-copy/jobs      — list past Paper_Copy imports
"""
import io
from datetime import datetime, date as _date
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/uploads/paper-copy", tags=["paper-copy"])

UPLOAD_TYPE = "paper_copy"
CATEGORY_NAME = "Paper_Copy"
REPLACE_CONFIRM_PHRASE = "VERVANG ALLE PAPER_COPY PRODUCTEN"
DELETE_CONFIRM_PHRASE = "VERWIJDER ALLE PRODUCTDATA"

REQUIRED_COLUMNS = ["productcode", "titel", "merk", "soort"]

# Alle kolommen die het exacte bestandsformat kan bevatten (rij 1 = kolomdefinitie).
COLUMN_ALIASES = {
    "productcode": ["productcode"],
    "titel": ["titel"],
    "merk": ["merk"],
    "soort": ["soort"],
    "ean": ["ean"],
    "oem": ["oem"],
    "afzet_ytd": ["afzet_ytd"],
    "omzet_ytd": ["omzet_ytd"],
    "marge_ytd": ["marge_ytd"],
    "afzet_ytd_1j": ["afzet_ytd_1_jaar", "afzet_ytd-1", "afzet_ytd -1"],
    "omzet_ytd_1j": ["omzet_ytd_1_jaar", "omzet_ytd-1", "omzet_ytd -1"],
    "marge_ytd_1j": ["marge_ytd_1_jaar", "marge_ytd-1", "marge_ytd -1"],
    "afzet_ytd_2j": ["afzet_ytd_2_jaar", "afzet_ytd-2", "afzet_ytd -2"],
    "omzet_ytd_2j": ["omzet_ytd_2_jaar", "omzet_ytd-2", "omzet_ytd -2"],
    "marge_ytd_2j": ["marge_ytd_2_jaar", "marge_ytd-2", "marge_ytd -2"],
    "inkoopprijs": ["inkoopprijs ex btw", "inkoopprijs"],
    "verkoopprijs_excl": ["verkoopprijs excl btw", "verkoopprijs_excl_btw"],
    "verkoopprijs_incl": ["verkoopprijs incl btw", "verkoopprijs_incl_btw"],
    "avg_units_ytd": ["gemiddeld aantal stuks per order ytd"],
    "avg_units_ytd_1j": ["gemiddeld aantal stuks per order ytd -1", "gemiddeld aantal stuks per order ytd-1"],
    "avg_units_ytd_2j": ["gemiddeld aantal stuks per order ytd -2", "gemiddeld aantal stuks per order ytd-2"],
    "aanmaakdatum": ["aanmaakdatum"],
    "eerste_verkoop": ["eerste verkoop", "eerste_verkoop"],
    "actief": ["active/inactive", "active_inactive"],
    "hierarchy": ["producthierarchy", "product_hierarchy", "producthiërarchie"],
}


def _trunc(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    return value[:limit] if len(value) > limit else value


def _get(row: dict, key: str) -> str:
    for alias in COLUMN_ALIASES.get(key, [key]):
        if alias in row:
            v = row.get(alias)
            return "" if v is None else str(v).strip()
    return ""


def _safe_float(val: str) -> Optional[float]:
    if not val or not str(val).strip():
        return None
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _safe_date(val: str) -> Optional[_date]:
    if not val or not str(val).strip():
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _is_inactive(val: str) -> bool:
    if not val or not str(val).strip():
        return False
    return str(val).strip().lower() in ("inactive", "inactief", "0", "false", "nee", "n", "no")


def _load_xlsx_single_sheet(content: bytes, filename: str) -> list[dict]:
    """Read row 1 as headers (lowercased) and every row from row 2 onward as data."""
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl is niet geïnstalleerd; XLSX niet ondersteund")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"XLSX bestand kon niet worden geopend: {e}")

    ws = wb.worksheets[0]
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(c).strip().lower() if c is not None else "" for c in next(rows_iter, [])]
    rows: list[dict] = []
    for row in rows_iter:
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        row_dict: dict = {}
        for h, v in zip(headers, row):
            row_dict[h] = "" if v is None else str(v).strip()
        rows.append(row_dict)
    wb.close()
    return rows


def _run_validation(rows: list[dict]) -> dict:
    """Validate rows in-memory without touching the DB. Returns a full report."""
    errors: list[dict] = []
    warnings: list[str] = []
    sku_seen: dict[str, list[int]] = {}
    merken: set[str] = set()
    ean_count = 0
    oem_count = 0
    actief_count = 0
    inactief_count = 0
    geldig = 0
    ongeldig = 0

    if rows:
        aanwezige_kolommen = set(rows[0].keys())
    else:
        aanwezige_kolommen = set()
    ontbrekende_kolommen = [k for k in REQUIRED_COLUMNS if k not in aanwezige_kolommen]

    for i, row in enumerate(rows, start=2):
        rij_ok = True
        pc = _get(row, "productcode")
        titel = _get(row, "titel")
        merk = _get(row, "merk")
        soort = _get(row, "soort")

        if not pc:
            errors.append({"rij": i, "veld": "productcode", "type": "ontbrekend",
                            "bericht": "Verplicht veld 'productcode' ontbreekt of is leeg"})
            rij_ok = False
        if not titel:
            errors.append({"rij": i, "veld": "titel", "type": "ontbrekend",
                            "bericht": "Verplicht veld 'Titel' ontbreekt of is leeg"})
            rij_ok = False
        if not merk:
            errors.append({"rij": i, "veld": "merk", "type": "ontbrekend",
                            "bericht": "Verplicht veld 'Merk' ontbreekt of is leeg"})
            rij_ok = False
        if not soort:
            errors.append({"rij": i, "veld": "soort", "type": "ontbrekend",
                            "bericht": "Verplicht veld 'Soort' ontbreekt of is leeg"})
            rij_ok = False

        if pc:
            sku_seen.setdefault(pc, []).append(i)
        if merk:
            merken.add(merk)

        ean = _get(row, "ean")
        oem = _get(row, "oem")
        if not ean:
            warnings.append(f"Rij {i} ({pc or '?'}): EAN ontbreekt")
        else:
            ean_count += 1
        if not oem:
            warnings.append(f"Rij {i} ({pc or '?'}): OEM ontbreekt")
        else:
            oem_count += 1

        ip_raw = _get(row, "inkoopprijs")
        vp_excl_raw = _get(row, "verkoopprijs_excl")
        vp_incl_raw = _get(row, "verkoopprijs_incl")
        ip_f = _safe_float(ip_raw)
        vp_excl_f = _safe_float(vp_excl_raw)
        vp_incl_f = _safe_float(vp_incl_raw)

        if ip_raw and ip_f is None:
            errors.append({"rij": i, "veld": "inkoopprijs ex btw", "type": "ongeldig_getal",
                            "bericht": f"Niet-numerieke inkoopprijs: '{ip_raw}'"})
            rij_ok = False
        elif ip_f is not None and ip_f < 0:
            errors.append({"rij": i, "veld": "inkoopprijs ex btw", "type": "negatieve_prijs",
                            "bericht": f"Inkoopprijs mag niet negatief zijn: {ip_f}"})
            rij_ok = False

        if vp_excl_raw and vp_excl_f is None:
            errors.append({"rij": i, "veld": "verkoopprijs excl btw", "type": "ongeldig_getal",
                            "bericht": f"Niet-numerieke verkoopprijs: '{vp_excl_raw}'"})
            rij_ok = False
        elif vp_excl_f is not None and vp_excl_f < 0:
            errors.append({"rij": i, "veld": "verkoopprijs excl btw", "type": "negatieve_prijs",
                            "bericht": f"Verkoopprijs mag niet negatief zijn: {vp_excl_f}"})
            rij_ok = False

        if vp_incl_raw and vp_incl_f is None:
            errors.append({"rij": i, "veld": "verkoopprijs incl btw", "type": "ongeldig_getal",
                            "bericht": f"Niet-numerieke verkoopprijs incl. BTW: '{vp_incl_raw}'"})
            rij_ok = False

        if ip_f is not None and vp_excl_f is not None and vp_excl_f < ip_f:
            warnings.append(f"Rij {i} ({pc or '?'}): verkoopprijs ({vp_excl_f}) < inkoopprijs ({ip_f}) — negatieve marge")

        for veld, key in (("afzet_ytd", "afzet_ytd"), ("omzet_ytd", "omzet_ytd"), ("marge_ytd", "marge_ytd")):
            raw = _get(row, key)
            if raw and _safe_float(raw) is None:
                errors.append({"rij": i, "veld": veld, "type": "ongeldig_getal",
                                "bericht": f"Niet-numerieke waarde voor {veld}: '{raw}'"})
                rij_ok = False
        if not _get(row, "afzet_ytd") and not _get(row, "omzet_ytd") and not _get(row, "marge_ytd"):
            warnings.append(f"Rij {i} ({pc or '?'}): geen YTD-omzet/marge/afzet aanwezig")

        for veld, key in (("aanmaakdatum", "aanmaakdatum"), ("eerste verkoop", "eerste_verkoop")):
            raw = _get(row, key)
            if raw and _safe_date(raw) is None:
                errors.append({"rij": i, "veld": veld, "type": "ongeldige_datum",
                                "bericht": f"Ongeldig datumformaat voor {veld}: '{raw}'"})
                rij_ok = False

        actief_raw = _get(row, "actief")
        if _is_inactive(actief_raw):
            inactief_count += 1
            warnings.append(f"Rij {i} ({pc or '?'}): product is inactief")
        else:
            actief_count += 1

        hierarchy = _get(row, "hierarchy")
        if not hierarchy:
            warnings.append(f"Rij {i} ({pc or '?'}): productHierarchy ontbreekt — valt terug op '{CATEGORY_NAME}'")

        if rij_ok:
            geldig += 1
        else:
            ongeldig += 1

    dubbele = [sku for sku, rijen in sku_seen.items() if len(rijen) > 1]
    for dup in dubbele:
        errors.append({"rij": sku_seen[dup][0], "veld": "productcode", "type": "duplicaat",
                        "bericht": f"Dubbele productcode '{dup}' op rijen: {sku_seen[dup]}"})

    fouten_per_type: dict[str, int] = {}
    for f in errors:
        t = f.get("type", "overige")
        fouten_per_type[t] = fouten_per_type.get(t, 0) + 1

    kan_importeren = len(ontbrekende_kolommen) == 0 and geldig > 0 and len(errors) == 0

    return {
        "samenvatting": {
            "rijen_totaal": len(rows),
            "rijen_geldig": geldig,
            "rijen_ongeldig": ongeldig,
            "actief": actief_count,
            "inactief": inactief_count,
            "unieke_merken": len(merken),
            "met_ean": ean_count,
            "zonder_ean": len(rows) - ean_count,
            "met_oem": oem_count,
            "zonder_oem": len(rows) - oem_count,
        },
        "missing_columns": ontbrekende_kolommen,
        "duplicate_productcodes": dubbele[:20],
        "errors": errors[:100],
        "errors_by_type": fouten_per_type,
        "warnings": warnings[:100],
        "kan_importeren": kan_importeren,
        "preview": rows[:25],
    }


def _log_audit(db: Session, entity_type: str, entity_id: str, action: str,
               performed_by: str, old_val=None, new_val=None, details: str = ""):
    entry = models.AuditLog(
        entity_type=entity_type, entity_id=entity_id, action=action,
        performed_by=performed_by, timestamp=datetime.utcnow(),
        details=details, old_value=old_val, new_value=new_val,
    )
    db.add(entry)


@router.post("/validate")
async def validate_paper_copy(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Valideer het Paper_Copy XLSX-bestand zonder productdata op te slaan."""
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Alleen XLSX-bestanden worden ondersteund voor Paper_Copy import")

    content = await file.read()
    rows = _load_xlsx_single_sheet(content, file.filename or "")
    report = _run_validation(rows)

    job = models.ImportJob(
        upload_type=UPLOAD_TYPE,
        filename=file.filename or "paper_copy.xlsx",
        status="gevalideerd" if report["kan_importeren"] else "fout",
        rows_processed=0,
        rows_failed=report["samenvatting"]["rijen_ongeldig"],
        error_message=None if report["kan_importeren"] else f"{len(report['errors'])} validatiefout(en) gevonden",
        uploaded_by=current_user.username,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        warnings_json=report["warnings"][:50],
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    report["job_id"] = job.id
    report["bestandsnaam"] = file.filename
    return report


@router.post("/save")
async def save_paper_copy(
    file: UploadFile = File(...),
    mode: str = Form("updaten"),  # aanvullen | updaten | vervangen
    confirm_phrase: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager", "analyst")),
):
    """
    Persisteer het Paper_Copy XLSX-bestand in dim_product.

    mode:
      - aanvullen: alleen nieuwe productcodes toevoegen, bestaande blijven ongewijzigd.
      - updaten (default): upsert op productcode — nieuw toevoegen, bestaand bijwerken.
      - vervangen: zoals updaten, plus alle bestaande Paper_Copy-rijen die niet in het
        bestand voorkomen worden verwijderd. Vereist confirm_phrase exact gelijk aan
        REPLACE_CONFIRM_PHRASE.
    """
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Alleen XLSX-bestanden worden ondersteund voor Paper_Copy import")

    mode = (mode or "updaten").strip().lower()
    if mode not in ("aanvullen", "updaten", "vervangen"):
        raise HTTPException(status_code=400, detail="Ongeldige import mode; kies aanvullen, updaten of vervangen")

    if mode == "vervangen" and confirm_phrase != REPLACE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"Voor 'vervangen' moet confirm_phrase exact zijn: '{REPLACE_CONFIRM_PHRASE}'",
        )

    content = await file.read()
    rows = _load_xlsx_single_sheet(content, file.filename or "")
    report = _run_validation(rows)

    if not report["kan_importeren"]:
        job = models.ImportJob(
            upload_type=UPLOAD_TYPE, filename=file.filename or "paper_copy.xlsx",
            status="fout", rows_processed=0, rows_failed=report["samenvatting"]["rijen_ongeldig"],
            error_message=f"Import geweigerd: {len(report['errors'])} validatiefout(en)",
            uploaded_by=current_user.username, import_mode=mode,
            created_at=datetime.utcnow(), completed_at=datetime.utcnow(),
            warnings_json=report["warnings"][:50],
        )
        db.add(job)
        db.commit()
        raise HTTPException(status_code=400, detail={"message": "Validatie mislukt, niets opgeslagen", "report": report})

    job = models.ImportJob(
        upload_type=UPLOAD_TYPE, filename=file.filename or "paper_copy.xlsx",
        status="processing", uploaded_by=current_user.username, import_mode=mode,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        created = updated = skipped = 0
        now = datetime.utcnow()
        seen_productcodes: set[str] = set()

        productcodes_in_file = {
            _trunc(_get(row, "productcode"), 100) for row in rows if _get(row, "productcode")
        }
        existing_products = {
            p.sku_id: p for p in db.query(models.DimProduct)
            .filter(models.DimProduct.sku_id.in_(productcodes_in_file)).all()
        }
        paper_copy_sku_ids = {
            p.sku_id for p in db.query(models.DimProduct.sku_id)
            .filter(models.DimProduct.category == CATEGORY_NAME).all()
        }

        for row in rows:
            pc = _trunc(_get(row, "productcode"), 100)
            if not pc:
                continue
            seen_productcodes.add(pc)

            naam = _trunc(_get(row, "titel") or pc, 500)
            merk = _trunc(_get(row, "merk") or None, 255)
            soort = _trunc(_get(row, "soort") or None, 50)
            ean = _trunc(_get(row, "ean") or None, 50)
            oem = _trunc(_get(row, "oem") or None, 100)

            hierarchy = _get(row, "hierarchy")
            product_group = _trunc(hierarchy or CATEGORY_NAME, 255)

            ip_f = _safe_float(_get(row, "inkoopprijs"))
            vp_excl = _safe_float(_get(row, "verkoopprijs_excl"))
            vp_incl = _safe_float(_get(row, "verkoopprijs_incl"))

            afzet_ytd = _safe_float(_get(row, "afzet_ytd"))
            omzet_ytd = _safe_float(_get(row, "omzet_ytd"))
            marge_ytd = _safe_float(_get(row, "marge_ytd"))
            afzet_ytd_1j = _safe_float(_get(row, "afzet_ytd_1j"))
            omzet_ytd_1j = _safe_float(_get(row, "omzet_ytd_1j"))
            marge_ytd_1j = _safe_float(_get(row, "marge_ytd_1j"))
            afzet_ytd_2j = _safe_float(_get(row, "afzet_ytd_2j"))
            omzet_ytd_2j = _safe_float(_get(row, "omzet_ytd_2j"))
            marge_ytd_2j = _safe_float(_get(row, "marge_ytd_2j"))
            avg_units = _safe_float(_get(row, "avg_units_ytd"))
            aanmaakdatum = _safe_date(_get(row, "aanmaakdatum"))
            eerste_verkoop = _safe_date(_get(row, "eerste_verkoop"))
            actief = not _is_inactive(_get(row, "actief"))

            existing = existing_products.get(pc)

            if existing and mode == "aanvullen":
                skipped += 1
                continue

            if existing:
                existing.product_name = naam
                existing.brand = merk
                existing.category = CATEGORY_NAME
                existing.product_group = product_group
                existing.product_type = soort
                existing.ean = ean
                existing.oem_code = oem
                existing.current_price = vp_excl
                existing.price_incl_vat = vp_incl
                existing.cost_price = ip_f
                existing.is_active = actief
                existing.lifecycle_status = "active" if actief else "discontinued"
                existing.afzet_ytd = afzet_ytd
                existing.omzet_ytd = omzet_ytd
                existing.marge_ytd = marge_ytd
                existing.afzet_ytd_1j = afzet_ytd_1j
                existing.omzet_ytd_1j = omzet_ytd_1j
                existing.marge_ytd_1j = marge_ytd_1j
                existing.afzet_ytd_2j = afzet_ytd_2j
                existing.omzet_ytd_2j = omzet_ytd_2j
                existing.marge_ytd_2j = marge_ytd_2j
                existing.avg_units_per_order = avg_units
                if aanmaakdatum:
                    existing.aanmaakdatum = aanmaakdatum
                if eerste_verkoop:
                    existing.eerste_verkoop = eerste_verkoop
                existing.import_source = "PAPER_COPY"
                existing.updated_at = now
                updated += 1
            else:
                new_product = models.DimProduct(
                    sku_id=pc, product_name=naam, brand=merk, category=CATEGORY_NAME,
                    product_group=product_group, product_type=soort, ean=ean, oem_code=oem,
                    current_price=vp_excl, price_incl_vat=vp_incl, cost_price=ip_f,
                    is_active=actief, lifecycle_status="active" if actief else "discontinued",
                    afzet_ytd=afzet_ytd, omzet_ytd=omzet_ytd, marge_ytd=marge_ytd,
                    afzet_ytd_1j=afzet_ytd_1j, omzet_ytd_1j=omzet_ytd_1j, marge_ytd_1j=marge_ytd_1j,
                    afzet_ytd_2j=afzet_ytd_2j, omzet_ytd_2j=omzet_ytd_2j, marge_ytd_2j=marge_ytd_2j,
                    avg_units_per_order=avg_units, aanmaakdatum=aanmaakdatum,
                    eerste_verkoop=eerste_verkoop, import_source="PAPER_COPY",
                )
                db.add(new_product)
                existing_products[pc] = new_product
                created += 1

        removed = 0
        if mode == "vervangen":
            stale_sku_ids = paper_copy_sku_ids - seen_productcodes
            if stale_sku_ids:
                te_verwijderen = db.query(models.DimProduct).filter(
                    models.DimProduct.sku_id.in_(stale_sku_ids)
                ).all()
                for p in te_verwijderen:
                    db.delete(p)
                    removed += 1

        _log_audit(db, "dim_product", "PAPER_COPY_IMPORT", "import", current_user.username,
                   None, {"created": created, "updated": updated, "skipped": skipped, "removed": removed,
                          "mode": mode, "filename": job.filename},
                   details=f"import_source=PAPER_COPY mode={mode}")
        db.commit()

        total = created + updated
        job.rows_processed = total
        job.rows_failed = 0
        job.status = "opgeslagen"
        job.completed_at = datetime.utcnow()
        job.warnings_json = report["warnings"][:50]
        db.commit()

        return {
            "job_id": job.id,
            "mode": mode,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "removed": removed,
            "rows_processed": total,
            "warnings": report["warnings"],
            "summary": _compute_summary(db),
            "message": (
                f"Paper_Copy import voltooid ({mode}): {created} nieuw, {updated} bijgewerkt"
                + (f", {removed} verwijderd" if removed else "")
                + (f", {skipped} overgeslagen" if skipped else "") + "."
            ),
        }

    except Exception as e:
        db.rollback()
        try:
            job.status = "fout"
            job.error_message = str(e)[:500]
            job.completed_at = datetime.utcnow()
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail=f"Paper_Copy import mislukt: {str(e)[:400]}")


def _compute_summary(db: Session) -> dict:
    products = db.query(models.DimProduct).filter(models.DimProduct.category == CATEGORY_NAME).all()
    total = len(products)
    active = sum(1 for p in products if p.is_active)
    inactive = total - active
    brands = {p.brand for p in products if p.brand}
    oem_articles = sum(1 for p in products if (p.product_type or "").strip().lower() == "oem")
    compat_huismerk = sum(1 for p in products if (p.product_type or "").strip().lower() in ("compatible", "huismerk"))
    missing_ean = sum(1 for p in products if not p.ean)
    missing_oem = sum(1 for p in products if not p.oem_code)
    prices = [float(p.current_price) for p in products if p.current_price]
    avg_price = sum(prices) / len(prices) if prices else None
    total_ytd_revenue = sum(float(p.omzet_ytd) for p in products if p.omzet_ytd) or 0.0
    total_ytd_margin = sum(float(p.marge_ytd) for p in products if p.marge_ytd) or 0.0
    total_ytd_units = sum(float(p.afzet_ytd) for p in products if p.afzet_ytd) or 0.0

    return {
        "total_products": total,
        "active": active,
        "inactive": inactive,
        "unique_brands": len(brands),
        "oem_articles": oem_articles,
        "compatible_huismerk_articles": compat_huismerk,
        "missing_ean": missing_ean,
        "missing_oem": missing_oem,
        "avg_sales_price": round(avg_price, 2) if avg_price is not None else None,
        "total_ytd_revenue": round(total_ytd_revenue, 2),
        "total_ytd_margin": round(total_ytd_margin, 2),
        "total_ytd_units": round(total_ytd_units, 2),
    }


@router.get("/summary")
def get_paper_copy_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Huidige samenvattingsstatistieken voor Paper_Copy productdata."""
    return _compute_summary(db)


@router.get("/jobs")
def list_paper_copy_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Toon het importlog voor Paper_Copy uploads, nieuwste eerst."""
    jobs = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.upload_type == UPLOAD_TYPE)
        .order_by(models.ImportJob.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "jobs": [
            {
                "id": j.id,
                "filename": j.filename,
                "status": j.status,
                "import_mode": j.import_mode,
                "rows_processed": j.rows_processed,
                "rows_failed": j.rows_failed,
                "error_message": j.error_message,
                "warnings": j.warnings_json or [],
                "uploaded_by": j.uploaded_by,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]
    }


@router.delete("/all")
def delete_all_paper_copy_products(
    confirm_phrase: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """
    Admin-only: verwijder alle Paper_Copy productdata (dim_product rows met
    category='Paper_Copy'). Vereist exacte bevestigingszin. Dit is het enige
    codepad dat dim_product-rijen mag verwijderen buiten een 'vervangen'-import.
    """
    if confirm_phrase != DELETE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"confirm_phrase moet exact zijn: '{DELETE_CONFIRM_PHRASE}'",
        )

    aantal = db.query(models.DimProduct).filter(models.DimProduct.category == CATEGORY_NAME).count()
    db.query(models.DimProduct).filter(models.DimProduct.category == CATEGORY_NAME).delete(synchronize_session=False)
    _log_audit(db, "dim_product", "PAPER_COPY_DELETE_ALL", "delete", current_user.username,
               {"rows_deleted": aantal}, None, details="Alle Paper_Copy productdata verwijderd")
    db.commit()

    return {"status": "voltooid", "rows_deleted": aantal, "message": f"{aantal} Paper_Copy producten verwijderd."}
