"""DRS Datareport import endpoints — validate + upsert via XLSX (Sales + Hierarchy tabs).

Low-level parsing/validation primitives (safe_float, safe_date, truncate) are
shared with every other import source via engine/import_engine.py.
"""
import io
from datetime import datetime, date as _date
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils
from engine.import_engine import (
    safe_float as _safe_float,
    safe_date as _safe_date,
    truncate as _trunc,
    build_preview,
    IMPORT_MODES,
    DEFAULT_IMPORT_MODE,
)

router = APIRouter(prefix="/api/uploads", tags=["drs"])

DRS_REPLACE_CONFIRM_PHRASE = "VERVANG ALLE DRS DATA"


# ── Column definitions (real DATAREPORT structure) ───────────────────────────
# Headers are stored lowercase after parsing.

# Verplichte kolommen in het Sales-tabblad
SALES_REQUIRED = [
    "productcode",
    "titel",
    "inkoopprijs ex btw",
    "verkoopprijs excl btw",
]

# Optionele kolommen in het Sales-tabblad (voor informatie, niet validatie-blokkerend)
SALES_OPTIONAL = [
    "merk", "soort", "oem",
    "afzet_ytd", "omzet_ytd", "marge_ytd",
    "afzet_ytd_1_jaar", "omzet_ytd_1_jaar", "marge_ytd_1_jaar",
    "afzet_ytd_2_jaar", "omzet_ytd_2_jaar", "marge_ytd_2_jaar",
    "verkoopprijs incl btw",
    "gemiddeld aantal stuks per order ytd",
    "gemiddeld aantal stuks per order ytd -1",
    "gemiddeld aantal stuks per order ytd -2",
    "aanmaakdatum", "eerste verkoop", "active/inactive", "producthierarchy",
]

# Verplichte kolommen in het Hierarchy-tabblad
HIERARCHY_REQUIRED = ["productcode", "name", "path"]


SALES_SHEET_NAMES = ["sales", "verkoop", "verkoopdata"]
HIERARCHY_SHEET_NAMES = ["hierarchy", "hiërarchie", "hierarchie", "categorieën", "categories"]


def _load_drs_xlsx(content: bytes, filename: str = "") -> tuple[list[dict], list[dict], list[str]]:
    """
    Parse a DRS workbook (XLSX or legacy XLS) and return
    (sales_rows, hierarchy_rows, warnings). Raises HTTPException when the
    file is unreadable or the required Sales/Hierarchy tabs are missing.
    Sheet lookup and cell parsing are delegated to the shared engine module
    so DRS gets the same XLS support as every other import source.
    """
    from engine.import_engine import (
        open_xlsx_workbook, xlsx_worksheet_to_rows,
        open_xls_workbook, xls_sheet_to_rows,
    )

    warnings: list[str] = []
    is_xls = (filename or "").lower().endswith(".xls") and not (filename or "").lower().endswith(".xlsx")

    if is_xls:
        wb = open_xls_workbook(content)
        sheet_names_lower = {name.lower().strip(): name for name in wb.sheet_names()}

        def _get_sheet(candidates: list[str]):
            for c in candidates:
                if c in sheet_names_lower:
                    return wb.sheet_by_name(sheet_names_lower[c])
            return None

        sales_ws = _get_sheet(SALES_SHEET_NAMES)
        hier_ws = _get_sheet(HIERARCHY_SHEET_NAMES)
        found_names = wb.sheet_names()
        to_rows = lambda ws: xls_sheet_to_rows(wb, ws)
    else:
        wb = open_xlsx_workbook(content)
        sheet_names_lower = {ws.title.lower().strip(): ws.title for ws in wb.worksheets}

        def _get_sheet(candidates: list[str]):
            for c in candidates:
                if c in sheet_names_lower:
                    return wb[sheet_names_lower[c]]
            return None

        sales_ws = _get_sheet(SALES_SHEET_NAMES)
        hier_ws = _get_sheet(HIERARCHY_SHEET_NAMES)
        found_names = [ws.title for ws in wb.worksheets]
        to_rows = xlsx_worksheet_to_rows

    missing = []
    if sales_ws is None:
        missing.append("Sales")
    if hier_ws is None:
        missing.append("Hierarchy")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Verplichte tabbladen ontbreken: {', '.join(missing)}. "
                   f"Gevonden tabbladen: {', '.join(found_names)}"
        )

    sales_rows = to_rows(sales_ws)
    hier_rows = to_rows(hier_ws)
    if not is_xls:
        wb.close()
    return sales_rows, hier_rows, warnings


def _is_inactive(val: str | None) -> bool:
    """Returns True when the Active/Inactive value signals inactief."""
    if val is None or str(val).strip() == "":
        return False
    return str(val).strip().lower() in ("inactive", "inactief", "0", "false", "nee", "n", "no")


def _build_hierarchy_from_paths(paths: list[str]) -> dict[str, dict]:
    """
    Given a list of pipe-separated path strings like 'Paper + | Paper_copy | A4 | 80 grams',
    return a dict keyed by full-path-prefix with node metadata:
      { "Paper +" : { "name": "Paper +", "level": 1, "parent_path": None, "path": "Paper +" },
        "Paper + | Paper_copy": { "name": "Paper_copy", "level": 2, "parent_path": "Paper +", ... }, ... }
    """
    nodes: dict[str, dict] = {}
    for raw_path in paths:
        if not raw_path.strip():
            continue
        segments = [s.strip() for s in raw_path.split(" | ")]
        for i, seg in enumerate(segments):
            prefix = " | ".join(segments[: i + 1])
            if prefix in nodes:
                continue
            parent_prefix = " | ".join(segments[:i]) if i > 0 else None
            nodes[prefix] = {
                "name": seg,
                "level": i + 1,
                "parent_path": parent_prefix,
                "path": prefix,
            }
    return nodes


# ── Validate endpoint ───────────────────────────────────────────────────────

@router.post("/drs/validate")
async def validate_drs(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Valideer een DRS Datareport-bestand (XLSX of XLS, tabbladen Sales + Hierarchy)
    zonder op te slaan. Retourneert een gestructureerd validatierapport.
    """
    fname = (file.filename or "")
    if not fname.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Alleen XLSX- of XLS-bestanden worden ondersteund voor DRS import")

    content = await file.read()
    sales_rows, hier_rows, warnings = _load_drs_xlsx(content, fname)

    fouten: list[dict] = []
    sku_gezien: dict[str, list[int]] = {}

    # ── Sales tab: check aanwezige kolommen ──────────────────────────────
    sales_kolommen = set(sales_rows[0].keys()) if sales_rows else set()
    ontbrekende_sales_kols = [k for k in SALES_REQUIRED if k not in sales_kolommen]

    # ── Hierarchy tab: check aanwezige kolommen ───────────────────────────
    hier_kolommen = set(hier_rows[0].keys()) if hier_rows else set()
    ontbrekende_hier_kols = [k for k in HIERARCHY_REQUIRED if k not in hier_kolommen]

    # Bouw een mapping productcode → path vanuit de Hierarchy-tab
    hier_path_by_sku: dict[str, str] = {}
    unieke_paden: set[str] = set()
    for row in hier_rows:
        pc = row.get("productcode", "").strip()
        pad = row.get("path", "").strip()
        if pc:
            hier_path_by_sku[pc] = pad
        if pad:
            unieke_paden.add(pad)

    actief_count = 0
    inactief_count = 0
    merken: set[str] = set()
    skus_zonder_hierarchy: list[str] = []
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

        vp_raw = row.get("verkoopprijs excl btw", "").strip()
        ip_raw = row.get("inkoopprijs ex btw", "").strip()
        vp_f = _safe_float(vp_raw)
        ip_f = _safe_float(ip_raw)

        if vp_raw and vp_f is None:
            fouten.append({"tab": "Sales", "rij": i, "veld": "verkoopprijs excl btw",
                           "type": "ongeldige_prijs",
                           "bericht": f"Niet-numerieke verkoopprijs: '{vp_raw}'"})
            rij_ok = False
        if ip_raw and ip_f is None:
            fouten.append({"tab": "Sales", "rij": i, "veld": "inkoopprijs ex btw",
                           "type": "ongeldige_prijs",
                           "bericht": f"Niet-numerieke inkoopprijs: '{ip_raw}'"})
            rij_ok = False
        if vp_f is not None and ip_f is not None and vp_f < ip_f:
            fouten.append({"tab": "Sales", "rij": i, "veld": "marge", "type": "negatieve_marge",
                           "bericht": f"Verkoopprijs excl BTW ({vp_f}) < inkoopprijs ({ip_f}): negatieve marge"})

        # Actief/inactief — waarschuwing, geen fout
        actief_raw = row.get("active/inactive", "").strip()
        if _is_inactive(actief_raw):
            inactief_count += 1
            warnings.append(f"Inactief artikel: '{pc or i}' (rij {i})")
        else:
            actief_count += 1

        merk = row.get("merk", "").strip()
        if merk:
            merken.add(merk)

        # Waarschuw als SKU geen overeenkomst heeft in de Hierarchy-tab
        if pc and pc not in hier_path_by_sku:
            skus_zonder_hierarchy.append(pc)
            warnings.append(f"Productcode '{pc}' (rij {i}) heeft geen overeenkomstige rij in Hierarchy-tab")

        if rij_ok:
            geldig_sales += 1
        else:
            ongeldig_sales += 1

    dubbele_skus = [sku for sku, rijen in sku_gezien.items() if len(rijen) > 1]
    for dup in dubbele_skus:
        fouten.append({"tab": "Sales", "rij": sku_gezien[dup][0],
                       "veld": "productcode", "type": "dubbele_productcode",
                       "bericht": f"Dubbele productcode '{dup}' op rijen {sku_gezien[dup]}. "
                                  "Maak productcodes uniek vóór import; verschillende EANs "
                                  "maken dubbele cataloguscodes niet veilig."})

    # ── Hierarchy tab row validation ──────────────────────────────────────
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
        and not dubbele_skus
    )

    return {
        "bestandsnaam": file.filename,
        "samenvatting": {
            "skus_totaal": len(sales_rows),
            "skus_actief": actief_count,
            "skus_inactief": inactief_count,
            "unieke_merken": len(merken),
            "unieke_hierarchiepaden": len(unieke_paden),
            "skus_zonder_hierarchy_match": len(skus_zonder_hierarchy),
        },
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
            "unieke_paden": len(unieke_paden),
        },
        "duplicate_skus": dubbele_skus[:20],
        "skus_zonder_hierarchy": skus_zonder_hierarchy[:20],
        "errors": fouten[:50],
        "errors_by_type": fouten_per_type,
        "warnings": warnings[:50],
        "kan_importeren": kan_importeren,
        "preview": build_preview(sales_rows),
        "preview_hierarchy": build_preview(hier_rows),
    }


# ── Import endpoint ─────────────────────────────────────────────────────────

@router.post("/drs")
async def import_drs(
    file: UploadFile = File(...),
    mode: str = Form(DEFAULT_IMPORT_MODE),
    shop_id: int = Form(1),
    confirm_phrase: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """
    Importeer een DRS Datareport-bestand (XLSX of XLS).
    - Upsert alle SKU's uit het Sales-tabblad in dim_product.
    - Bouw de hiërarchieboom op vanuit de unieke path-waarden in het Hierarchy-tabblad.
    - Synchroniseer dim_category op basis van level-1 knooppunten.
    - Logt elke aanmaak/update in audit_log.

    `mode` bepaalt het importgedrag:
    - "aanvullen": alleen nieuwe SKU's toevoegen, bestaande SKU's ongemoeid laten.
    - "updaten" (standaard): bestaande SKU's bijwerken, nieuwe toevoegen.
    - "vervangen": zoals "updaten", maar deactiveert ontbrekende DRS-SKU's
      binnen de gekozen winkel. Identiteit en historie blijven intact.
      Vereist `confirm_phrase` exact gelijk aan DRS_REPLACE_CONFIRM_PHRASE.
    """
    fname = (file.filename or "")
    if not fname.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Alleen XLSX- of XLS-bestanden worden ondersteund voor DRS import")

    if mode not in IMPORT_MODES:
        raise HTTPException(status_code=400, detail=f"Ongeldige mode '{mode}'. Kies uit: {', '.join(IMPORT_MODES)}")

    if mode == "vervangen" and confirm_phrase != DRS_REPLACE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"Voor 'vervangen' is de exacte bevestigingszin vereist: '{DRS_REPLACE_CONFIRM_PHRASE}'"
        )

    content = await file.read()
    sales_rows, hier_rows, file_warnings = _load_drs_xlsx(content, fname)
    from services.product_identity import authorize_shop, IdentityIndex, alias_discriminator
    from uuid import uuid4
    authorize_shop(db, current_user, shop_id)
    # Catalog/hierarchy processing is keyed by productcode, not (code, EAN).
    # Reject before jobs, category writes or replace retirement can happen.
    code_rows = {}
    for row_number, row in enumerate(sales_rows, start=2):
        code = row.get("productcode", "").strip()
        if code:
            code_rows.setdefault(code, []).append(row_number)
    duplicates = {code: rows for code, rows in code_rows.items() if len(rows) > 1}
    if duplicates:
        details = "; ".join(f"'{code}' op rijen {rows}" for code, rows in list(duplicates.items())[:20])
        raise HTTPException(422, "Dubbele productcodes: " + details +
                            ". Maak productcodes uniek vóór catalogusimport, ook bij verschillende EANs. "
                            "Geen producten, aliassen of hiërarchie gewijzigd.")
    identity = IdentityIndex(db, shop_id)
    resolved_codes = {}
    for row in sales_rows:
        code = row.get("productcode", "").strip()
        if not code:
            continue
        if len(code) > 100:
            raise HTTPException(422, "Artikelcode te lang; identiteit wordt niet afgekapt.")
        try:
            resolved_codes[code] = identity.resolve(code, row.get("ean", "").strip())[0]
        except ValueError as exc:
            if code in identity.codes:
                raise HTTPException(409, f"Artikelcode {code}: {exc}")
            # Catalog import may create products; daily imports never may.
            resolved_codes[code] = "drs:" + str(uuid4())
    file_type = "xls" if fname.lower().endswith(".xls") else "xlsx"

    from engine.import_engine import new_batch_id as _new_batch_id
    job = models.ImportJob(
        upload_type="drs",
        filename=file.filename or "drs.xlsx",
        source="DRS",
        file_type=file_type,
        import_mode=mode,
        status="nieuw",
        uploaded_by=current_user.username,
        created_at=datetime.utcnow(),
        batch_id=_new_batch_id(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        sku_created = sku_updated = sku_skipped = 0
        hier_created = hier_updated = 0
        cat_created = cat_updated = 0
        warnings: list[str] = list(file_warnings)
        now = datetime.utcnow()
        seen_skus: set[str] = set()

        # ── Step 1: Bouw mapping productcode → path vanuit Hierarchy-tab ─────
        hier_path_by_sku: dict[str, str] = {}
        for row in hier_rows:
            pc = row.get("productcode", "").strip()
            pad = row.get("path", "").strip()
            if pc and pad:
                hier_path_by_sku[pc] = pad

        # ── Step 2: Verzamel alle unieke paden en bouw knooppunt-structuur ───
        unieke_paden: set[str] = {r.get("path", "").strip() for r in hier_rows if r.get("path", "").strip()}
        node_defs = _build_hierarchy_from_paths(list(unieke_paden))

        # Verwerk knooppunten level-voor-level zodat ouders eerder worden aangemaakt
        max_level = max((n["level"] for n in node_defs.values()), default=0)
        path_to_db_id: dict[str, int] = {}

        # Laad alle bestaande hiërarchie-knooppunten in één query (voorkomt N queries)
        existing_nodes = {n.path: n for n in db.query(models.DimCategoryHierarchy).all()}

        for level in range(1, max_level + 1):
            level_nodes = {p: n for p, n in node_defs.items() if n["level"] == level}
            for full_path, node in level_nodes.items():
                node_naam = _trunc(node["name"], 255)
                full_path = _trunc(full_path, 1000)
                parent_path = node["parent_path"]
                parent_db_id: Optional[int] = path_to_db_id.get(parent_path) if parent_path else None

                existing = existing_nodes.get(full_path)

                if existing:
                    existing.category_name = node_naam
                    existing.category_level = level
                    existing.parent_category_id = parent_db_id
                    existing.active = True
                    existing.import_source = "DRS"
                    db.flush()
                    path_to_db_id[full_path] = existing.category_id
                    hier_updated += 1
                else:
                    new_node = models.DimCategoryHierarchy(
                        category_name=node_naam,
                        parent_category_id=parent_db_id,
                        category_level=level,
                        path=full_path,
                        active=True,
                        import_source="DRS",
                    )
                    db.add(new_node)
                    db.flush()
                    path_to_db_id[full_path] = new_node.category_id
                    _log_audit(db, "dim_category_hierarchy", str(new_node.category_id),
                               "create", current_user.username, {"name": node_naam, "level": level})
                    hier_created += 1

        db.commit()

        # ── Step 3: Sync dim_category vanuit level-1 knooppunten ─────────────
        level1_nodes = (
            db.query(models.DimCategoryHierarchy)
            .filter(models.DimCategoryHierarchy.category_level == 1,
                    models.DimCategoryHierarchy.import_source == "DRS")
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

        # ── Step 4: Upsert SKU's vanuit Sales-tabblad ─────────────────────────
        # Laad alle bestaande producten in één query (voorkomt N queries → timeout)
        # Earlier hierarchy/job commits release transaction locks. Refresh
        # identity under the same shop lock as feed and daily confirmation.
        from services.product_identity import sales_lock
        sales_lock(db, shop_id)
        identity = IdentityIndex(db, shop_id)
        for row in sales_rows:
            code = row.get("productcode", "").strip()
            if code and code in identity.codes:
                try:
                    resolved_codes[code] = identity.resolve(code, row.get("ean", "").strip())[0]
                except ValueError as exc:
                    raise HTTPException(409, f"Artikelcode {code}: {exc}")
        existing_products = dict(identity.products)

        for i, row in enumerate(sales_rows, start=2):
            pc = row.get("productcode", "").strip()
            if not pc:
                continue

            naam = _trunc(row.get("titel", "").strip() or pc, 500)
            merk = _trunc(row.get("merk", "").strip() or None, 255)
            soort = _trunc(row.get("soort", "").strip() or None, 50)
            oem_code = _trunc(row.get("oem", "").strip() or None, 100)

            vp_excl = _safe_float(row.get("verkoopprijs excl btw"))
            vp_incl = _safe_float(row.get("verkoopprijs incl btw"))
            ip_f = _safe_float(row.get("inkoopprijs ex btw"))

            actief_raw = row.get("active/inactive", "").strip()
            actief = not _is_inactive(actief_raw)

            afzet_ytd = _safe_float(row.get("afzet_ytd"))
            omzet_ytd = _safe_float(row.get("omzet_ytd"))
            marge_ytd = _safe_float(row.get("marge_ytd"))
            afzet_ytd_1j = _safe_float(row.get("afzet_ytd_1_jaar"))
            omzet_ytd_1j = _safe_float(row.get("omzet_ytd_1_jaar"))
            marge_ytd_1j = _safe_float(row.get("marge_ytd_1_jaar"))
            afzet_ytd_2j = _safe_float(row.get("afzet_ytd_2_jaar"))
            omzet_ytd_2j = _safe_float(row.get("omzet_ytd_2_jaar"))
            marge_ytd_2j = _safe_float(row.get("marge_ytd_2_jaar"))

            avg_units = _safe_float(row.get("gemiddeld aantal stuks per order ytd"))
            aanmaakdatum = _safe_date(row.get("aanmaakdatum"))
            eerste_verkoop = _safe_date(row.get("eerste verkoop"))

            # Hiërarchie: haal pad op via Hierarchy-tab mapping
            pad = hier_path_by_sku.get(pc, "")
            segments = [s.strip() for s in pad.split(" | ")] if pad else []
            # category = level-2 segment (bijv. "Paper_copy"), of level-1 als er maar 1 niveau is
            categorie = _trunc(segments[1] if len(segments) >= 2 else (segments[0] if segments else None), 255)
            product_group = _trunc(pad or None, 255)

            if not pad:
                warnings.append(f"SKU '{pc}': geen Hierarchy-pad gevonden, category/product_group leeg gelaten")

            technical_sku = resolved_codes[pc]
            seen_skus.add(technical_sku)
            existing = existing_products.get(technical_sku)

            if existing and mode == "aanvullen":
                # "aanvullen": alleen nieuwe SKU's toevoegen, bestaande overslaan.
                sku_skipped += 1
                continue

            if existing:
                # Explicit DRS aliases may differ from a canonical business SKU.
                # Catalog refresh must not erase the identity retained by repair.
                existing.business_sku = existing.business_sku or pc
                existing.product_name = naam
                existing.brand = merk
                existing.category = categorie
                existing.product_group = product_group
                existing.product_type = soort
                existing.oem_code = oem_code
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
                existing.import_source = "DRS"
                existing.updated_at = now
                sku_updated += 1
            else:
                full_ean = row.get("ean", "").strip()
                new_product = models.DimProduct(
                    sku_id=technical_sku,
                    business_sku=pc,
                    shop_id=shop_id,
                    ean=full_ean if len(full_ean) <= 50 else None,
                    raw_attributes={"_ean_full": full_ean} if len(full_ean) > 50 else None,
                    product_name=naam,
                    brand=merk,
                    category=categorie,
                    product_group=product_group,
                    product_type=soort,
                    oem_code=oem_code,
                    current_price=vp_excl,
                    price_incl_vat=vp_incl,
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
                existing_products[technical_sku] = new_product
                sku_created += 1
            discriminator = alias_discriminator(row.get("ean", "").strip())
            if not identity.aliases.get((pc, discriminator)):
                db.flush()
                db.add(models.ProductSourceAlias(shop_id=shop_id, source="DRS", code=pc,
                       discriminator=discriminator, sku_id=technical_sku))
                identity.aliases[(pc, discriminator)].add(technical_sku)

        # ── Step 5: "vervangen" — verwijder DRS-SKU's die niet in dit bestand voorkomen ──
        sku_deleted = 0
        if mode == "vervangen":
            stale_products = [
                p for sku, p in existing_products.items()
                if sku not in seen_skus and (p.import_source or "").upper() == "DRS"
            ]
            for p in stale_products:
                # Retire instead of destroying technical identity and history.
                p.is_active = False
                p.lifecycle_status = "discontinued"
                sku_deleted += 1
            if stale_products:
                _log_audit(db, "dim_product", "DRS_REPLACE", "delete", current_user.username,
                           {"skus_deleted": [p.sku_id for p in stale_products][:100]},
                           {"count": sku_deleted, "filename": job.filename})

        # Eén samenvattende audit-entry i.p.v. duizenden losse inserts
        _log_audit(db, "dim_product", "DRS_IMPORT", "import", current_user.username,
                   None, {"skus_created": sku_created, "skus_updated": sku_updated,
                          "skus_skipped": sku_skipped, "skus_deleted": sku_deleted,
                          "mode": mode, "filename": job.filename})
        db.commit()

        totaal = sku_created + sku_updated
        job.rows_processed = totaal
        job.rows_failed = 0
        job.rows_duplicates = max(0, len(sales_rows) - len(seen_skus)) if sales_rows else 0
        job.warnings_json = warnings[:200]
        job.error_log = [{"rij": None, "bericht": w} for w in warnings[:100]]
        job.status = "bijgewerkt" if mode in ("updaten", "vervangen") and sku_updated > 0 else "geimporteerd"
        job.completed_at = now
        db.commit()

        mode_msg = {
            "aanvullen": f"{sku_skipped} bestaande SKU's overgeslagen (aanvullen-modus).",
            "updaten": "",
            "vervangen": f"{sku_deleted} verouderde DRS-SKU's gedeactiveerd; historie behouden.",
        }.get(mode, "")

        return {
            "job_id": job.id,
            "mode": mode,
            "skus_created": sku_created,
            "skus_updated": sku_updated,
            "skus_skipped": sku_skipped,
            "skus_deleted": 0,
            "skus_retired": sku_deleted,
            "hierarchy_created": hier_created,
            "hierarchy_updated": hier_updated,
            "categories_created": cat_created,
            "categories_updated": cat_updated,
            "rows_processed": totaal,
            "rows_failed": 0,
            "warnings": warnings,
            "message": (
                f"DRS import voltooid: {sku_created} nieuwe SKU's, {sku_updated} bijgewerkt. "
                f"Hiërarchie: {hier_created} nieuw, {hier_updated} bijgewerkt. {mode_msg}"
            ).strip(),
        }

    except Exception as e:
        db.rollback()
        try:
            job.status = "fout"
            job.error_message = str(e)[:500]
            job.error_log = [{"rij": None, "bericht": str(e)[:500]}]
            job.completed_at = datetime.utcnow()
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail=f"DRS import mislukt: {str(e)[:400]}")


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
