"""DRS Datareport import endpoints — validate + upsert via XLSX (Sales + Hierarchy tabs)."""
import io
from datetime import datetime, date as _date
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/uploads", tags=["drs"])

# ── Column definitions ──────────────────────────────────────────────────────

SALES_REQUIRED = ["productcode", "productnaam", "verkoopprijs", "inkoopprijs"]
SALES_OPTIONAL = [
    "merk", "categorie", "subcategorie", "productgroep", "producttype", "oem_code",
    "afzet_ytd", "omzet_ytd", "marge_ytd",
    "afzet_ytd_1j", "omzet_ytd_1j", "marge_ytd_1j",
    "afzet_ytd_2j", "omzet_ytd_2j", "marge_ytd_2j",
    "gem_eenheden_per_order", "aanmaakdatum", "eerste_verkoop", "actief",
]
HIERARCHY_REQUIRED = ["node_id", "node_naam", "niveau"]
HIERARCHY_OPTIONAL = ["parent_id", "pad", "module", "actief"]


def _load_drs_xlsx(content: bytes) -> tuple[list[dict], list[dict], list[str]]:
    """
    Parse DRS XLSX and return (sales_rows, hierarchy_rows, warnings).
    Raises HTTPException when file is unreadable or required tabs are missing.
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl is niet geïnstalleerd; XLSX niet ondersteund")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"XLSX bestand kon niet worden geopend: {e}")

    sheet_names_lower = {ws.title.lower().strip(): ws.title for ws in wb.worksheets}
    warnings: list[str] = []

    def _get_sheet(candidates: list[str]):
        for c in candidates:
            if c in sheet_names_lower:
                return wb[sheet_names_lower[c]]
        return None

    sales_ws = _get_sheet(["sales", "verkoop", "verkoopdata"])
    hier_ws = _get_sheet(["hierarchy", "hiërarchie", "hierarchie", "categorieën", "categories"])

    missing = []
    if sales_ws is None:
        missing.append("Sales")
    if hier_ws is None:
        missing.append("Hierarchy")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Verplichte tabbladen ontbreken: {', '.join(missing)}. "
                   f"Gevonden tabbladen: {', '.join(ws.title for ws in wb.worksheets)}"
        )

    def _sheet_to_rows(ws) -> list[dict]:
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(c).strip().lower() if c is not None else "" for c in next(rows_iter, [])]
        rows = []
        for row in rows_iter:
            if all(v is None or str(v).strip() == "" for v in row):
                continue
            row_dict: dict = {}
            for h, v in zip(headers, row):
                row_dict[h] = "" if v is None else str(v).strip()
            rows.append(row_dict)
        return rows

    sales_rows = _sheet_to_rows(sales_ws)
    hier_rows = _sheet_to_rows(hier_ws)
    wb.close()
    return sales_rows, hier_rows, warnings


def _safe_float(val: str | None) -> Optional[float]:
    if not val or str(val).strip() == "":
        return None
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _safe_date(val: str | None) -> Optional[_date]:
    if not val or str(val).strip() == "":
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _safe_bool(val: str | None, default: bool = True) -> bool:
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip().lower() not in ("0", "false", "nee", "n", "no", "inactive", "inactief")


# ── Validate endpoint ───────────────────────────────────────────────────────

@router.post("/drs/validate")
async def validate_drs(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Valideer een DRS Datareport XLSX-bestand (tabbladen Sales + Hierarchy) zonder op te slaan.
    Retourneert een gestructureerd validatierapport.
    """
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Alleen XLSX-bestanden worden ondersteund voor DRS import")

    content = await file.read()
    sales_rows, hier_rows, warnings = _load_drs_xlsx(content)

    fouten: list[dict] = []
    sku_gezien: dict[str, list[int]] = {}

    # ── Sales tab validation ──────────────────────────────────────────────
    sales_kolommen = set(sales_rows[0].keys()) if sales_rows else set()
    ontbrekende_sales_kols = [k for k in SALES_REQUIRED if k not in sales_kolommen]

    geldig_sales = 0
    ongeldig_sales = 0

    for i, row in enumerate(sales_rows, start=2):
        rij_ok = True

        for req in SALES_REQUIRED:
            if not row.get(req, "").strip():
                fouten.append({"tab": "Sales", "rij": i, "veld": req, "type": "ontbrekend",
                               "bericht": f'Verplicht veld "{req}" ontbreekt of is leeg'})
                rij_ok = False

        pc = row.get("productcode", "").strip()
        if pc:
            sku_gezien.setdefault(pc, []).append(i)

        vp = row.get("verkoopprijs", "").strip()
        ip = row.get("inkoopprijs", "").strip()
        vp_f = _safe_float(vp)
        ip_f = _safe_float(ip)

        if vp and vp_f is None:
            fouten.append({"tab": "Sales", "rij": i, "veld": "verkoopprijs", "type": "ongeldige_prijs",
                           "bericht": f"Niet-numerieke verkoopprijs: '{vp}'"})
            rij_ok = False
        if ip and ip_f is None:
            fouten.append({"tab": "Sales", "rij": i, "veld": "inkoopprijs", "type": "ongeldige_prijs",
                           "bericht": f"Niet-numerieke inkoopprijs: '{ip}'"})
            rij_ok = False
        if vp_f is not None and ip_f is not None and vp_f < ip_f:
            fouten.append({"tab": "Sales", "rij": i, "veld": "marge", "type": "negatieve_marge",
                           "bericht": f"Verkoopprijs ({vp_f}) < inkoopprijs ({ip_f}): negatieve marge"})
            rij_ok = False

        actief_raw = row.get("actief", "1")
        if actief_raw.strip().lower() in ("0", "false", "nee", "n", "no", "inactive", "inactief"):
            fouten.append({"tab": "Sales", "rij": i, "veld": "actief", "type": "inactief_artikel",
                           "bericht": f"Artikel {pc or i} is gemarkeerd als inactief"})

        if not row.get("merk", "").strip():
            fouten.append({"tab": "Sales", "rij": i, "veld": "merk", "type": "ontbrekend_merk",
                           "bericht": f"Merk ontbreekt voor productcode '{pc or i}'"})

        if not row.get("categorie", "").strip():
            fouten.append({"tab": "Sales", "rij": i, "veld": "categorie", "type": "ontbrekende_hierarchie",
                           "bericht": f"Categorie ontbreekt voor productcode '{pc or i}'"})

        if rij_ok:
            geldig_sales += 1
        else:
            ongeldig_sales += 1

    dubbele_skus = [sku for sku, rijen in sku_gezien.items() if len(rijen) > 1]
    for dup in dubbele_skus:
        warnings.append(f"Dubbele productcode '{dup}' op rijen: {sku_gezien[dup]}")

    # ── Hierarchy tab validation ──────────────────────────────────────────
    hier_kolommen = set(hier_rows[0].keys()) if hier_rows else set()
    ontbrekende_hier_kols = [k for k in HIERARCHY_REQUIRED if k not in hier_kolommen]
    geldig_hier = 0
    ongeldig_hier = 0

    for i, row in enumerate(hier_rows, start=2):
        rij_ok = True
        for req in HIERARCHY_REQUIRED:
            if not row.get(req, "").strip():
                fouten.append({"tab": "Hierarchy", "rij": i, "veld": req, "type": "ontbrekend",
                               "bericht": f'Verplicht veld "{req}" ontbreekt of is leeg'})
                rij_ok = False
        if rij_ok:
            geldig_hier += 1
        else:
            ongeldig_hier += 1

    # ── Summary ───────────────────────────────────────────────────────────
    fouten_per_type: dict[str, int] = {}
    for f in fouten:
        t = f.get("type", "overige")
        fouten_per_type[t] = fouten_per_type.get(t, 0) + 1

    kan_importeren = (
        len(ontbrekende_sales_kols) == 0
        and len(ontbrekende_hier_kols) == 0
        and geldig_sales > 0
    )

    return {
        "bestandsnaam": file.filename,
        "sales": {
            "rows_total": len(sales_rows),
            "rows_valid": geldig_sales,
            "rows_failed": ongeldig_sales,
            "missing_columns": ontbrekende_sales_kols,
        },
        "hierarchy": {
            "rows_total": len(hier_rows),
            "rows_valid": geldig_hier,
            "rows_failed": ongeldig_hier,
            "missing_columns": ontbrekende_hier_kols,
        },
        "duplicate_skus": dubbele_skus[:20],
        "errors": fouten[:50],
        "errors_by_type": fouten_per_type,
        "warnings": warnings,
        "kan_importeren": kan_importeren,
    }


# ── Import endpoint ─────────────────────────────────────────────────────────

@router.post("/drs")
async def import_drs(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """
    Importeer een DRS Datareport XLSX-bestand.
    - Upsert alle SKU's uit het Sales-tabblad in dim_product.
    - Synchroniseer alle knooppunten uit het Hierarchy-tabblad in dim_category_hierarchy.
    - Synchroniseer dim_category op basis van unieke bladknooppunten (niveau-2).
    - Logt elke aanmaak/update in audit_log.
    """
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Alleen XLSX-bestanden worden ondersteund voor DRS import")

    content = await file.read()
    sales_rows, hier_rows, file_warnings = _load_drs_xlsx(content)

    job = models.ImportJob(
        upload_type="drs",
        filename=file.filename or "drs.xlsx",
        status="processing",
        uploaded_by=current_user.username,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        sku_created = sku_updated = 0
        hier_created = hier_updated = 0
        cat_created = cat_updated = 0
        warnings: list[str] = list(file_warnings)
        now = datetime.utcnow()

        # ── Step 1: Sync Hierarchy ────────────────────────────────────────────
        node_id_to_db_id: dict[str, int] = {}

        for i, row in enumerate(hier_rows, start=2):
            node_id_raw = row.get("node_id", "").strip()
            node_naam = row.get("node_naam", "").strip()
            niveau_raw = row.get("niveau", "1").strip()
            if not node_id_raw or not node_naam:
                continue
            try:
                niveau = int(niveau_raw)
            except ValueError:
                niveau = 1

            pad = row.get("pad", "").strip() or node_naam
            module = row.get("module", "").strip()
            actief = _safe_bool(row.get("actief", "1"))

            # parent_id: resolve from node_id_to_db_id mapping
            parent_raw = row.get("parent_id", "").strip()
            parent_db_id: Optional[int] = node_id_to_db_id.get(parent_raw) if parent_raw else None

            # Try to find existing node by name + level
            existing = (
                db.query(models.DimCategoryHierarchy)
                .filter(
                    models.DimCategoryHierarchy.category_name == node_naam,
                    models.DimCategoryHierarchy.category_level == niveau,
                )
                .first()
            )

            if existing:
                existing.path = pad
                existing.module = module
                existing.active = actief
                existing.parent_category_id = parent_db_id
                existing.import_source = "DRS"
                db.flush()
                node_id_to_db_id[node_id_raw] = existing.category_id
                hier_updated += 1
            else:
                new_node = models.DimCategoryHierarchy(
                    category_name=node_naam,
                    parent_category_id=parent_db_id,
                    category_level=niveau,
                    path=pad,
                    module=module,
                    active=actief,
                    import_source="DRS",
                )
                db.add(new_node)
                db.flush()
                node_id_to_db_id[node_id_raw] = new_node.category_id
                _log_audit(db, "dim_category_hierarchy", str(new_node.category_id),
                           "create", current_user.username, {"name": node_naam, "level": niveau})
                hier_created += 1

        db.commit()

        # ── Step 2: Sync dim_category from hierarchy level-1 nodes ───────────
        level1_nodes = (
            db.query(models.DimCategoryHierarchy)
            .filter(models.DimCategoryHierarchy.category_level == 1)
            .all()
        )
        existing_cats = {c.name: c for c in db.query(models.DimCategory).all()}

        for node in level1_nodes:
            if node.category_name in existing_cats:
                cat = existing_cats[node.category_name]
                if cat.parent_category != node.path:
                    cat.parent_category = node.path
                    cat_updated += 1
            else:
                new_cat = models.DimCategory(name=node.category_name, parent_category=node.path)
                db.add(new_cat)
                cat_created += 1

        db.commit()

        # ── Step 3: Upsert SKUs from Sales ───────────────────────────────────
        for i, row in enumerate(sales_rows, start=2):
            pc = row.get("productcode", "").strip()
            if not pc:
                continue

            naam = row.get("productnaam", "") or row.get("productomschrijving", "") or pc
            merk = row.get("merk", "").strip() or None
            categorie = row.get("categorie", "").strip() or None
            subcategorie = row.get("subcategorie", "").strip() or None
            product_group = row.get("productgroep", "").strip() or None
            product_type = row.get("producttype", "").strip() or None
            oem_code = row.get("oem_code", "").strip() or None

            vp_f = _safe_float(row.get("verkoopprijs"))
            ip_f = _safe_float(row.get("inkoopprijs"))
            actief = _safe_bool(row.get("actief", "1"))

            afzet_ytd = _safe_float(row.get("afzet_ytd"))
            omzet_ytd = _safe_float(row.get("omzet_ytd"))
            marge_ytd = _safe_float(row.get("marge_ytd"))
            afzet_ytd_1j = _safe_float(row.get("afzet_ytd_1j"))
            omzet_ytd_1j = _safe_float(row.get("omzet_ytd_1j"))
            marge_ytd_1j = _safe_float(row.get("marge_ytd_1j"))
            afzet_ytd_2j = _safe_float(row.get("afzet_ytd_2j"))
            omzet_ytd_2j = _safe_float(row.get("omzet_ytd_2j"))
            marge_ytd_2j = _safe_float(row.get("marge_ytd_2j"))
            avg_units = _safe_float(row.get("gem_eenheden_per_order"))
            aanmaakdatum = _safe_date(row.get("aanmaakdatum"))
            eerste_verkoop = _safe_date(row.get("eerste_verkoop"))

            existing = db.query(models.DimProduct).filter(models.DimProduct.sku_id == pc).first()

            if existing:
                old_vals = {
                    "product_name": existing.product_name,
                    "current_price": float(existing.current_price) if existing.current_price else None,
                }
                existing.product_name = naam
                existing.brand = merk
                existing.category = categorie
                existing.subcategory = subcategorie
                existing.product_group = product_group
                existing.product_type = product_type
                existing.oem_code = oem_code
                existing.current_price = vp_f
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
                existing.import_source = "DRS"
                existing.updated_at = now
                _log_audit(db, "dim_product", pc, "update", current_user.username,
                           old_vals, {"product_name": naam, "current_price": vp_f})
                sku_updated += 1
            else:
                new_product = models.DimProduct(
                    sku_id=pc,
                    product_name=naam,
                    brand=merk,
                    category=categorie,
                    subcategory=subcategorie,
                    product_group=product_group,
                    product_type=product_type,
                    oem_code=oem_code,
                    current_price=vp_f,
                    cost_price=ip_f,
                    is_active=actief,
                    lifecycle_status="active" if actief else "discontinued",
                    afzet_ytd=afzet_ytd,
                    omzet_ytd=omzet_ytd,
                    marge_ytd=marge_ytd,
                    afzet_ytd_1j=afzet_ytd_1j,
                    omzet_ytd_1j=omzet_ytd_1j,
                    marge_ytd_1j=marge_ytd_1j,
                    afzet_ytd_2j=afzet_ytd_2j,
                    omzet_ytd_2j=omzet_ytd_2j,
                    marge_ytd_2j=marge_ytd_2j,
                    avg_units_per_order=avg_units,
                    aanmaakdatum=aanmaakdatum,
                    eerste_verkoop=eerste_verkoop,
                    import_source="DRS",
                )
                db.add(new_product)
                _log_audit(db, "dim_product", pc, "create", current_user.username,
                           None, {"product_name": naam, "import_source": "DRS"})
                sku_created += 1

        db.commit()

        totaal = sku_created + sku_updated
        job.rows_processed = totaal
        job.rows_failed = 0
        job.status = "completed"
        job.completed_at = now
        db.commit()

        return {
            "job_id": job.id,
            "skus_created": sku_created,
            "skus_updated": sku_updated,
            "hierarchy_created": hier_created,
            "hierarchy_updated": hier_updated,
            "categories_created": cat_created,
            "categories_updated": cat_updated,
            "rows_processed": totaal,
            "rows_failed": 0,
            "warnings": warnings,
            "message": (
                f"DRS import voltooid: {sku_created} nieuwe SKU's, {sku_updated} bijgewerkt. "
                f"Hiërarchie: {hier_created} nieuw, {hier_updated} bijgewerkt."
            ),
        }

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=500, detail=f"DRS import mislukt: {str(e)}")


def _log_audit(db: Session, entity_type: str, entity_id: str, action: str,
               performed_by: str, old_val=None, new_val=None):
    entry = models.AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        performed_by=performed_by,
        timestamp=datetime.utcnow(),
        details=f"import_source=DRS",
        old_value=old_val,
        new_value=new_val,
    )
    db.add(entry)
