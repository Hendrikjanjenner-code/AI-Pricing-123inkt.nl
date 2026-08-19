"""
PriceShape competitor-price import — CSV/XLSX/XLS uploads from the PriceShape platform.

Recognizes SKU / EAN / OEM / MPN as matching keys (at least one must resolve to an
existing dim_product row), plus competitor name, competitor price, timestamp and
import-source. Rows that can't be matched to a known SKU are reported as warnings
and skipped (never silently dropped from the report — see `skus_niet_gevonden`).

Endpoints:
  POST /api/uploads/priceshape/validate  — validate only, no DB writes (except job log)
  POST /api/uploads/priceshape/import    — upsert into fact_competitor_price_daily
  GET  /api/uploads/priceshape/jobs      — list past PriceShape imports

Distinct from connectors/priceshape_connector.py, which pulls the same data
directly from the PriceShape API (env-var based) instead of a manual file upload.
Both feed the same fact_competitor_price_daily table.
"""
from datetime import datetime, date as _date
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils
from engine.import_engine import (
    file_to_rows,
    safe_float as _safe_float,
    safe_date as _safe_date,
    truncate as _trunc,
    get_alias,
    find_duplicates,
    new_batch_id as _ps_new_batch_id,
    build_preview,
    IMPORT_MODES,
    DEFAULT_IMPORT_MODE,
    PREVIEW_ROW_LIMIT,
)

router = APIRouter(prefix="/api/uploads/priceshape", tags=["priceshape"])

UPLOAD_TYPE = "priceshape"
SOURCE_NAME = "PriceShape"
REPLACE_CONFIRM_PHRASE = "VERVANG ALLE PRICESHAPE DATA"

# Kolomaliassen — SKU/EAN/OEM/MPN worden als matching-sleutels behandeld;
# minstens één moet aanwezig zijn per rij om de rij aan een dim_product te koppelen.
SKU_ALIASES = ["sku", "sku_id", "artikelnummer", "productcode"]
EAN_ALIASES = ["ean", "ean_code", "barcode", "gtin"]
OEM_ALIASES = ["oem", "oem_code", "oem/mpn", "mpn"]
COMPETITOR_NAME_ALIASES = ["competitor", "competitor_name", "concurrent", "concurrentnaam", "retailer", "domain"]
COMPETITOR_PRICE_ALIASES = ["competitor_price", "concurrentprijs", "price", "prijs"]
TIMESTAMP_ALIASES = ["timestamp", "datum", "date", "scraped_at", "gemeten_op"]
IMPORT_SOURCE_ALIASES = ["import_source", "bron", "source"]
URL_ALIASES = ["url", "product_url", "link", "producturl"]


def _match_sku(row: dict, sku_by_ean: dict[str, str], sku_by_oem: dict[str, str],
               known_skus: set[str]) -> tuple[Optional[str], str]:
    """
    Resolve a row to an internal sku_id using SKU → EAN → OEM/MPN, in that order.
    Returns (sku_id_or_None, matched_via).
    """
    sku = get_alias(row, *SKU_ALIASES)
    if sku and sku in known_skus:
        return sku, "sku"

    ean = get_alias(row, *EAN_ALIASES)
    if ean and ean in sku_by_ean:
        return sku_by_ean[ean], "ean"

    oem = get_alias(row, *OEM_ALIASES)
    if oem and oem in sku_by_oem:
        return sku_by_oem[oem], "oem"

    return None, ""


def _run_validation(db: Session, rows: list[dict]) -> dict:
    """Validate rows in-memory (incl. SKU/EAN/OEM matching against dim_product)."""
    errors: list[dict] = []
    warnings: list[str] = []
    skus_niet_gevonden: list[str] = []
    competitors: set[str] = set()
    geldig = 0
    ongeldig = 0

    all_products = db.query(models.DimProduct.sku_id, models.DimProduct.ean, models.DimProduct.oem_code).all()
    known_skus = {p.sku_id for p in all_products}
    sku_by_ean = {p.ean: p.sku_id for p in all_products if p.ean}
    sku_by_oem = {p.oem_code: p.sku_id for p in all_products if p.oem_code}

    for i, row in enumerate(rows, start=2):
        rij_ok = True

        sku_id, matched_via = _match_sku(row, sku_by_ean, sku_by_oem, known_skus)
        prijs_raw = get_alias(row, *COMPETITOR_PRICE_ALIASES)
        prijs = _safe_float(prijs_raw)
        comp_naam = get_alias(row, *COMPETITOR_NAME_ALIASES)
        ts_raw = get_alias(row, *TIMESTAMP_ALIASES)
        ts = _safe_date(ts_raw)

        if not sku_id:
            identifiers = get_alias(row, *SKU_ALIASES, *EAN_ALIASES, *OEM_ALIASES) or "?"
            errors.append({"rij": i, "veld": "sku/ean/oem", "type": "geen_match",
                            "bericht": f"Geen overeenkomstig product gevonden voor '{identifiers}'"})
            skus_niet_gevonden.append(identifiers)
            rij_ok = False
        if not comp_naam:
            errors.append({"rij": i, "veld": "competitor_name", "type": "ontbrekend",
                            "bericht": "Verplicht veld 'competitor_name' ontbreekt of is leeg"})
            rij_ok = False
        else:
            competitors.add(comp_naam)
        if prijs_raw and prijs is None:
            errors.append({"rij": i, "veld": "competitor_price", "type": "ongeldig_getal",
                            "bericht": f"Niet-numerieke concurrentieprijs: '{prijs_raw}'"})
            rij_ok = False
        elif not prijs_raw:
            errors.append({"rij": i, "veld": "competitor_price", "type": "ontbrekend",
                            "bericht": "Verplicht veld 'competitor_price' ontbreekt of is leeg"})
            rij_ok = False
        elif prijs is not None and prijs < 0:
            errors.append({"rij": i, "veld": "competitor_price", "type": "negatieve_prijs",
                            "bericht": f"Concurrentieprijs mag niet negatief zijn: {prijs}"})
            rij_ok = False
        if ts_raw and ts is None:
            warnings.append(f"Rij {i}: ongeldig datumformaat voor timestamp '{ts_raw}' — huidige datum gebruikt")

        if rij_ok:
            geldig += 1
        else:
            ongeldig += 1

    dubbele = find_duplicates(
        rows,
        lambda r: "|".join(filter(None, [
            get_alias(r, *SKU_ALIASES) or get_alias(r, *EAN_ALIASES) or get_alias(r, *OEM_ALIASES),
            get_alias(r, *COMPETITOR_NAME_ALIASES),
        ]))
    )
    for key, rijen in dubbele.items():
        warnings.append(f"Dubbele SKU+concurrent-combinatie '{key}' op rijen: {rijen}")

    fouten_per_type: dict[str, int] = {}
    for f in errors:
        t = f.get("type", "overige")
        fouten_per_type[t] = fouten_per_type.get(t, 0) + 1

    kan_importeren = geldig > 0

    return {
        "samenvatting": {
            "rijen_totaal": len(rows),
            "rijen_geldig": geldig,
            "rijen_ongeldig": ongeldig,
            "rijen_dubbel": sum(len(rijen) - 1 for rijen in dubbele.values()),
            "unieke_concurrenten": len(competitors),
            "skus_niet_gevonden": len(skus_niet_gevonden),
        },
        "errors": errors[:100],
        "errors_by_type": fouten_per_type,
        "warnings": warnings[:100],
        "skus_niet_gevonden": skus_niet_gevonden[:20],
        "kan_importeren": kan_importeren,
        "preview": build_preview(rows, PREVIEW_ROW_LIMIT),
    }


def _log_audit(db: Session, entity_type: str, entity_id: str, action: str,
               performed_by: str, old_val=None, new_val=None, details: str = ""):
    entry = models.AuditLog(
        entity_type=entity_type, entity_id=entity_id, action=action,
        performed_by=performed_by, timestamp=datetime.utcnow(),
        details=details, old_value=old_val, new_value=new_val,
    )
    db.add(entry)


def persist_competitor_rows(db: Session, rows: list[dict], mode: str, username: str,
                            filename: str = "") -> dict:
    """
    Upsert PriceShape-concurrentieprijzen in fact_competitor_price_daily.

    Gedeeld door de handmatige upload-endpoint én de connector feed-synchronisatie,
    zodat beide exact dezelfde matching-, versiebeheer- en herkomstregels volgen.

    Modi:
    - "aanvullen":  alleen nieuwe rijen toevoegen, bestaande overslaan.
    - "vervangen":  upsert + opschonen van eerder door deze connector geschreven
                    rijen op de geraakte dagen die niet in de batch zitten.
                    Alleen veilig bij een VOLLEDIGE batch.
    - "bijwerken":  upsert zonder opschonen — voor incrementele batches
                    (bijv. REST-sync met updated_after) waar ontbrekende rijen
                    "ongewijzigd" betekenen, niet "verdwenen".
    Rijen die niet aan een bekende SKU matchen worden overgeslagen (nooit stil
    gedropt uit het rapport dat de aanroeper zelf opstelt). Commit gebeurt hier.

    Returns {created, updated, skipped, removed, skipped_by_settings}.
    """
    from services import import_settings as imps
    settings = imps.get_settings(db, "priceshape")
    created = updated = skipped = removed = skipped_by_settings = 0
    unmatched = invalid = 0
    now = datetime.utcnow()
    today = now.date()

    if not imps.component_enabled(settings, "competitor_prices"):
        # Onderdeel volledig uitgevinkt: niets importeren, niets wissen.
        return {"created": 0, "updated": 0, "skipped": 0, "removed": 0,
                "skipped_by_settings": len(rows),
                "unmatched": 0, "invalid": 0}

    all_products = db.query(models.DimProduct.sku_id, models.DimProduct.ean, models.DimProduct.oem_code).all()
    known_skus = {p.sku_id for p in all_products}
    sku_by_ean = {p.ean: p.sku_id for p in all_products if p.ean}
    sku_by_oem = {p.oem_code: p.sku_id for p in all_products if p.oem_code}

    # Dagen die deze batch raakt, voor de optionele "vervangen" opschoning.
    touched_dates: set[_date] = set()
    # (datum, sku_id, competitor_name) → gezien, om upserts te versnellen.
    seen_keys: set[tuple] = set()

    for row in rows:
        sku_id, matched_via = _match_sku(row, sku_by_ean, sku_by_oem, known_skus)
        if not sku_id:
            # Onbekende rij: geteld als unmatched (de upload-aanroeper rapporteert
            # deze rijen daarnaast zelf in detail).
            unmatched += 1
            continue

        comp_naam = _trunc(get_alias(row, *COMPETITOR_NAME_ALIASES), 255)
        prijs = _safe_float(get_alias(row, *COMPETITOR_PRICE_ALIASES))
        if prijs is None or prijs < 0 or not comp_naam:
            # Ontbrekende, negatieve of ongeldige prijs of concurrentnaam:
            # nooit stil droppen (zelfde regel als de upload-validator).
            invalid += 1
            continue

        if imps.competitor_disabled(settings, comp_naam):
            # Uitgevinkte concurrent: rij overslaan, bestaande data blijft staan.
            skipped_by_settings += 1
            continue

        ts = _safe_date(get_alias(row, *TIMESTAMP_ALIASES)) or today
        url = get_alias(row, *URL_ALIASES)
        touched_dates.add(ts)

        # Scope the upsert match to rows this connector previously wrote
        # (source == SOURCE_NAME). A row with the same
        # (date, sku_id, competitor_name) key that was created by another
        # pipeline (manual entry, scraper, paper-copy, ...) must never be
        # overwritten or have its provenance silently reassigned.
        existing = (
            db.query(models.FactCompetitorPriceDaily)
            .filter(
                models.FactCompetitorPriceDaily.date == ts,
                models.FactCompetitorPriceDaily.sku_id == sku_id,
                models.FactCompetitorPriceDaily.competitor_name == comp_naam,
                models.FactCompetitorPriceDaily.source == SOURCE_NAME,
            )
            .first()
        )
        seen_keys.add((ts, sku_id, comp_naam))

        if existing and mode == "aanvullen":
            skipped += 1
            continue

        if existing:
            existing.price = prijs
            existing.source = SOURCE_NAME
            if url:
                existing.url = url
            updated += 1
        else:
            db.add(models.FactCompetitorPriceDaily(
                date=ts, sku_id=sku_id, competitor_name=comp_naam, price=prijs, url=url,
                source=SOURCE_NAME,
            ))
            created += 1

    db.flush()

    if mode == "vervangen" and touched_dates:
        # Only ever delete rows previously written by THIS connector
        # (source == SOURCE_NAME). Competitor prices captured by other
        # pipelines (manual uploads, scrapers, paper-copy, etc.) on the
        # same dates must never be touched by a PriceShape replace.
        existing_in_scope = (
            db.query(models.FactCompetitorPriceDaily)
            .filter(
                models.FactCompetitorPriceDaily.date.in_(touched_dates),
                models.FactCompetitorPriceDaily.source == SOURCE_NAME,
            )
            .all()
        )
        for rec in existing_in_scope:
            if imps.competitor_disabled(settings, rec.competitor_name):
                # Uitgevinkte concurrent: bestaande data nooit wissen, ook niet
                # in "vervangen"-modus (de rijen zijn bewust niet aangeleverd).
                continue
            key = (rec.date, rec.sku_id, rec.competitor_name)
            if key not in seen_keys:
                db.delete(rec)
                removed += 1

    _log_audit(db, "fact_competitor_price_daily", "PRICESHAPE_IMPORT", "import", username,
               None, {"created": created, "updated": updated, "skipped": skipped, "removed": removed,
                      "skipped_by_settings": skipped_by_settings,
                      "unmatched": unmatched, "invalid": invalid,
                      "mode": mode, "filename": filename},
               details=f"import_source={SOURCE_NAME} mode={mode}")
    db.commit()

    return {"created": created, "updated": updated, "skipped": skipped, "removed": removed,
            "skipped_by_settings": skipped_by_settings,
            "unmatched": unmatched, "invalid": invalid}


@router.post("/validate")
async def validate_priceshape(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Valideer een PriceShape CSV/XLSX/XLS-bestand zonder data op te slaan."""
    fname = file.filename or ""
    if not fname.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Alleen CSV-, XLSX- of XLS-bestanden worden ondersteund voor PriceShape import")

    content = await file.read()
    file_warnings: list[str] = []
    rows = file_to_rows(content, fname, warnings=file_warnings)
    report = _run_validation(db, rows)
    report["warnings"] = (file_warnings + report["warnings"])[:100]

    job = models.ImportJob(
        batch_id=_ps_new_batch_id(),
        upload_type=UPLOAD_TYPE,
        filename=fname or "priceshape_upload",
        source=SOURCE_NAME,
        file_type="xls" if fname.lower().endswith(".xls") else ("xlsx" if fname.lower().endswith(".xlsx") else "csv"),
        status="gevalideerd" if report["kan_importeren"] else "fout",
        rows_processed=0,
        rows_failed=report["samenvatting"]["rijen_ongeldig"],
        rows_duplicates=report["samenvatting"].get("rijen_dubbel", 0),
        error_log=[{"rij": e.get("rij"), "veld": e.get("veld"), "bericht": e.get("bericht") or e.get("message")}
                   for e in report["errors"][:100]],
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
    report["bestandsnaam"] = fname
    return report


@router.post("/import")
async def import_priceshape(
    file: UploadFile = File(...),
    mode: str = Form(DEFAULT_IMPORT_MODE),
    confirm_phrase: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager", "analyst")),
):
    """
    Persisteer PriceShape-concurrentieprijzen in fact_competitor_price_daily.

    mode:
      - aanvullen: alleen dagrijen toevoegen voor SKU+concurrent-combinaties die nog
        niet bestaan op de gegeven datum; bestaande rijen blijven ongewijzigd.
      - updaten (default): upsert op (datum, sku_id, competitor_name).
      - vervangen: zoals updaten, plus alle bestaande PriceShape-rijen op de datums uit
        dit bestand die niet in het bestand voorkomen worden verwijderd. Vereist
        confirm_phrase exact gelijk aan REPLACE_CONFIRM_PHRASE.
    """
    fname = file.filename or ""
    if not fname.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Alleen CSV-, XLSX- of XLS-bestanden worden ondersteund voor PriceShape import")

    mode = (mode or DEFAULT_IMPORT_MODE).strip().lower()
    if mode not in IMPORT_MODES:
        raise HTTPException(status_code=400, detail=f"Ongeldige mode '{mode}'. Kies uit: {', '.join(IMPORT_MODES)}")

    if mode == "vervangen" and confirm_phrase != REPLACE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"Voor 'vervangen' moet confirm_phrase exact zijn: '{REPLACE_CONFIRM_PHRASE}'",
        )

    content = await file.read()
    file_warnings: list[str] = []
    rows = file_to_rows(content, fname, warnings=file_warnings)
    report = _run_validation(db, rows)
    report["warnings"] = (file_warnings + report["warnings"])[:100]
    file_type = "xls" if fname.lower().endswith(".xls") else ("xlsx" if fname.lower().endswith(".xlsx") else "csv")

    if not report["kan_importeren"]:
        job = models.ImportJob(
            batch_id=_ps_new_batch_id(),
            upload_type=UPLOAD_TYPE, filename=fname or "priceshape_upload",
            source=SOURCE_NAME, file_type=file_type,
            status="fout", rows_processed=0, rows_failed=report["samenvatting"]["rijen_ongeldig"],
            rows_duplicates=report["samenvatting"].get("rijen_dubbel", 0),
            error_log=[{"rij": e.get("rij"), "veld": e.get("veld"), "bericht": e.get("bericht") or e.get("message")}
                       for e in report["errors"][:100]],
            error_message=f"Import geweigerd: {len(report['errors'])} validatiefout(en)",
            uploaded_by=current_user.username, import_mode=mode,
            created_at=datetime.utcnow(), completed_at=datetime.utcnow(),
            warnings_json=report["warnings"][:50],
        )
        db.add(job)
        db.commit()
        raise HTTPException(status_code=400, detail={"message": "Validatie mislukt, niets opgeslagen", "report": report})

    job = models.ImportJob(
        batch_id=_ps_new_batch_id(),
        upload_type=UPLOAD_TYPE, filename=fname or "priceshape_upload",
        source=SOURCE_NAME, file_type=file_type,
        status="nieuw", uploaded_by=current_user.username, import_mode=mode,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        res = persist_competitor_rows(db, rows, mode, current_user.username, filename=job.filename)
        created = res["created"]
        updated = res["updated"]
        skipped = res["skipped"]
        removed = res["removed"]
        skipped_by_settings = res.get("skipped_by_settings", 0)

        total = created + updated
        job.rows_processed = total
        job.rows_failed = 0
        job.rows_duplicates = skipped or 0
        job.status = "bijgewerkt" if updated > 0 else "geimporteerd"
        job.completed_at = datetime.utcnow()
        setting_warnings = (
            [f"{skipped_by_settings} rijen overgeslagen door importinstellingen (uitgevinkte onderdelen/concurrenten)"]
            if skipped_by_settings else []
        )
        job.warnings_json = (setting_warnings + report["warnings"])[:50]
        job.error_log = [{"rij": None, "bericht": w} for w in report["warnings"][:100]]
        db.commit()

        return {
            "job_id": job.id,
            "mode": mode,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "removed": removed,
            "skipped_by_settings": skipped_by_settings,
            "rows_processed": total,
            "warnings": setting_warnings + report["warnings"],
            "skus_niet_gevonden": report["skus_niet_gevonden"],
            "message": (
                f"PriceShape import voltooid ({mode}): {created} nieuw, {updated} bijgewerkt"
                + (f", {removed} verwijderd" if removed else "")
                + (f", {skipped} overgeslagen" if skipped else "")
                + (f", {skipped_by_settings} overgeslagen door importinstellingen" if skipped_by_settings else "")
                + "."
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
        raise HTTPException(status_code=500, detail=f"PriceShape import mislukt: {str(e)[:400]}")


@router.get("/jobs")
async def list_priceshape_jobs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Geef de importgeschiedenis van PriceShape-uploads terug (nieuwste eerst)."""
    jobs = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.upload_type == UPLOAD_TYPE)
        .order_by(models.ImportJob.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "source": j.source,
            "file_type": j.file_type,
            "import_mode": j.import_mode,
            "status": j.status,
            "rows_processed": j.rows_processed,
            "rows_failed": j.rows_failed,
            "error_message": j.error_message,
            "warnings": j.warnings_json,
            "uploaded_by": j.uploaded_by,
            "created_at": j.created_at,
            "completed_at": j.completed_at,
        }
        for j in jobs
    ]


@router.get("/import-settings")
async def get_import_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Importselectie-instellingen (aan/uitvinken) + bekende concurrenten uit de feed."""
    from services import import_settings as imps
    settings = imps.get_settings(db, "priceshape")
    known = [r[0] for r in db.query(models.FactCompetitorPriceDaily.competitor_name)
             .filter(models.FactCompetitorPriceDaily.source.in_(["priceshape", SOURCE_NAME]))
             .distinct().order_by(models.FactCompetitorPriceDaily.competitor_name).limit(500).all()]
    disabled = set(settings["disabled_competitors"])
    # Ook uitgevinkte concurrenten blijven zichtbaar (anders kun je ze nooit
    # meer aanvinken zodra hun data niet meer ververst wordt).
    all_names = sorted(set(known) | disabled, key=str.lower)
    return {
        **settings,
        "component_labels": imps.COMPONENT_LABELS_NL,
        "competitors": [{"name": n, "enabled": n.lower() not in disabled} for n in all_names],
    }


@router.put("/import-settings")
async def update_import_settings(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Sla de importselectie op (persistent — overleeft herstart)."""
    from services import import_settings as imps
    components = payload.get("components") or {}
    disabled = payload.get("disabled_competitors") or []
    if not isinstance(components, dict) or not isinstance(disabled, list):
        raise HTTPException(400, "Ongeldige payload: components (object) en disabled_competitors (lijst) verwacht")
    try:
        if "max_delivery_days" in payload:
            settings = imps.save_settings(db, components, disabled, current_user.username,
                                          max_delivery_days=payload.get("max_delivery_days"))
        else:
            settings = imps.save_settings(db, components, disabled, current_user.username)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _log_audit(db, "feed_import_setting", "priceshape", "update", current_user.username,
               None, settings, details="Importselectie gewijzigd")
    db.commit()
    return settings


@router.get("/connection")
async def check_priceshape_connection(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Test de PriceShape API-verbinding zonder data op te halen.
    Controleert DB-geconfigureerde credentials eerst; valt terug op omgevingsvariabelen."""
    from connectors import priceshape_connector
    return priceshape_connector.check_connection(db=db)
