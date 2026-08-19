"""
Data Quality Center (§30) — volledige detectielijst met issue-workflow.

Detecties: ontbrekende/dubbele ID's & EAN's, ontbrekende prijzen/kostprijzen,
verouderde data (stale), eenheid-problemen, pack-size mismatches, mislukte
imports, low-confidence matches en verouderde AI-modellen — plus de bestaande
product- en DRS-checks.

Elke detectie levert per issue: severity, bron, module, aantal getroffen
records, business impact, aanbevolen actie. Issues worden gepersisteerd in
``data_quality_issue`` met een workflow (owner + status) en gaan automatisch
op 'opgelost' zodra de detectie niets meer vindt.
"""
from datetime import datetime, timedelta, date as _date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api", tags=["data-quality"])

STALE_DAYS = 3           # dagen zonder verse fact-data = stale bron
MODEL_STALE_DAYS = 7     # dagen zonder geslaagde modelrun = stale AI-model
LOW_CONFIDENCE = 0.6     # drempel voor low-confidence matches
FAILED_IMPORT_WINDOW_DAYS = 14

VALID_ISSUE_STATUSES = {"open", "in_behandeling", "genegeerd", "opgelost"}

# Alleen deze rollen mogen de issue-registry beschrijven (upsert/auto-resolve)
# tijdens een scan; alle andere rollen (bv. viewer) krijgen een read-only scan.
REGISTRY_WRITE_ROLES = {"admin", "pricing_manager"}


def _issue(code: str, severity: str, title: str, message: str, count: int,
           source: str, module: str, impact: str, action: str) -> dict:
    return {
        "issue_code": code,
        "issue_type": code,          # backwards compatible veldnaam
        "severity": severity,
        "title": title,
        "message": message,
        "affected_count": count,
        "source": source,
        "module": module,
        "business_impact": impact,
        "suggested_action": action,
        "sku_id": None,
    }


def _detect_issues(db: Session, total_skus: int) -> list[dict]:  # noqa: C901
    issues: list[dict] = []
    P = models.DimProduct

    # ── Ontbrekende & dubbele identifiers ─────────────────────────────────
    missing_ean = db.query(P).filter((P.ean.is_(None)) | (P.ean == "")).count()
    if missing_ean:
        # Feedbreed signaal: als ≥95% van de catalogus geen EAN heeft, koppelt
        # de PriceShape-feed op itemGroupId — dat is een bewust feedformaat
        # (geen gebrek), niet 3.228 losse artikelproblemen.
        feed_wide_no_ean = total_skus > 0 and missing_ean >= int(total_skus * 0.95)
        if feed_wide_no_ean:
            issues.append(_issue(
                "MISSING_EAN", "info", "Feed zonder EAN-codes (itemGroupId-koppeling)",
                f"De gehele feed ({missing_ean} SKU's) bevat geen GTIN/EAN — "
                "PriceShape koppelt op itemGroupId", missing_ean,
                "PriceShape", "Producten",
                "Concurrent-matching verloopt via de feed-koppeling op itemGroupId; "
                "EAN-verificatie met externe bronnen is niet mogelijk zonder GTIN.",
                "Geen actie vereist als de PriceShape-export bewust op itemGroupId "
                "exporteert. Voeg een GTIN-kolom toe in PriceShape als externe "
                "EAN-verificatie gewenst is."))
        else:
            issues.append(_issue(
                "MISSING_EAN", "warning", "Ontbrekende EAN-codes",
                "SKU's zonder EAN-code (barcode)", missing_ean,
                "DRS", "Producten",
                "Zonder EAN kan concurrentie-matching (PriceShape) deze producten "
                "niet betrouwbaar koppelen; prijsadviezen missen marktcontext.",
                "Vul EAN-codes aan in DRS of via een product-CSV met kolom 'ean'."))

    dup_eans = (db.query(P.ean, func.count(P.sku_id))
                .filter(P.ean.isnot(None), P.ean != "")
                .group_by(P.ean).having(func.count(P.sku_id) > 1).count())
    if dup_eans:
        issues.append(_issue(
            "DUPLICATE_EAN", "error", "Dubbele EAN-codes",
            "EAN-codes die aan meerdere SKU's zijn gekoppeld", dup_eans,
            "DRS", "Producten",
            "Dubbele EAN's veroorzaken verkeerde concurrent-koppelingen en dus foutieve prijsadviezen op de verkeerde artikelen.",
            "Controleer welke SKU de juiste eigenaar van elke dubbele EAN is en corrigeer de rest."))

    dup_oem = (db.query(P.oem_code, func.count(P.sku_id))
               .filter(P.oem_code.isnot(None), P.oem_code != "")
               .group_by(P.oem_code).having(func.count(P.sku_id) > 1).count())
    if dup_oem:
        issues.append(_issue(
            "DUPLICATE_OEM_CODE", "warning", "Dubbele OEM-codes",
            "OEM-artikelnummers die aan meerdere SKU's hangen", dup_oem,
            "DRS", "Producten",
            "Dubbele OEM-codes kunnen tot verkeerde matches met concurrentaanbod leiden.",
            "Controleer de OEM-nummers; alleen echte duplicaten (multi-shop) zijn toegestaan."))

    # ── Ontbrekende prijzen & kostprijzen ────────────────────────────────
    missing_cost = db.query(P).filter(P.cost_price.is_(None)).count()
    if missing_cost:
        issues.append(_issue(
            "MISSING_COST_PRICE", "error", "Ontbrekende kostprijzen",
            "SKU's zonder kostprijs (vereist voor margeberekening)", missing_cost,
            "DRS", "Prijzen",
            "Zonder kostprijs kan geen marge of veilige bodemprijs worden berekend; deze SKU's krijgen geen betrouwbaar prijsadvies.",
            "Importeer kostprijzen via DRS of een product-CSV (kolom cost_price / inkoopprijs)."))

    missing_price = db.query(P).filter(P.current_price.is_(None)).count()
    if missing_price:
        issues.append(_issue(
            "MISSING_SALES_PRICE", "error", "Ontbrekende verkoopprijzen",
            "SKU's zonder actuele verkoopprijs", missing_price,
            "DRS", "Prijzen",
            "Zonder actuele verkoopprijs kan geen prijsindex of prijsadvies worden bepaald.",
            "Synchroniseer verkoopprijzen vanuit DRS of upload een prijzen-CSV."))

    missing_minmax = db.query(P).filter(P.min_price.is_(None) | P.max_price.is_(None)).count()
    if missing_minmax:
        issues.append(_issue(
            "MISSING_PRICE_GUARDRAILS", "warning", "Ontbrekende prijsgrenzen",
            "SKU's zonder min- of max-prijs (guardrails)", missing_minmax,
            "Handmatig", "Prijzen",
            "Zonder guardrails kunnen prijsadviezen buiten veilige grenzen vallen; adviezen vergen extra handmatige controle.",
            "Stel min/max-prijzen in via productbeheer of een CSV-upload."))

    neg_margin = db.query(P).filter(
        P.current_price.isnot(None), P.cost_price.isnot(None),
        P.current_price < P.cost_price).count()
    if neg_margin:
        issues.append(_issue(
            "NEGATIVE_MARGIN", "error", "Negatieve marge",
            "SKU's waar de verkoopprijs onder de kostprijs ligt", neg_margin,
            "DRS", "Prijzen",
            "Elke verkoop op deze SKU's kost geld; directe margeschade.",
            "Controleer kost- en verkoopprijs; verhoog de prijs of corrigeer de kostprijsdata."))

    invalid_range = db.query(P).filter(
        P.min_price.isnot(None), P.max_price.isnot(None),
        P.min_price > P.max_price).count()
    if invalid_range:
        issues.append(_issue(
            "INVALID_PRICE_RANGE", "error", "Ongeldige prijsrange",
            "SKU's waar min_price groter is dan max_price", invalid_range,
            "Handmatig", "Prijzen",
            "De prijsengine kan geen geldig advies genereren binnen een omgekeerde range.",
            "Corrigeer de min/max-prijzen van deze SKU's."))

    # ── Ontbrekende stamdata ─────────────────────────────────────────────
    missing_cat = db.query(P).filter(P.category.is_(None)).count()
    if missing_cat:
        issues.append(_issue(
            "MISSING_CATEGORY", "warning", "Ontbrekende categorie",
            "SKU's zonder categorietoewijzing", missing_cat,
            "DRS", "Producten",
            "Categorie-analyses (BCG, concurrentie per categorie) missen deze producten.",
            "Wijs categorieën toe via DRS-hiërarchie of product-CSV."))

    missing_strategy = db.query(P).filter(P.strategy_type.is_(None)).count()
    if missing_strategy:
        issues.append(_issue(
            "MISSING_STRATEGY_TYPE", "error", "Ontbrekend strategietype",
            "SKU's zonder prijsstrategie-type", missing_strategy,
            "Handmatig", "Prijsstrategie",
            "Zonder strategietype valt de SKU terug op de standaardstrategie; adviezen sluiten mogelijk niet aan bij het commerciële doel.",
            "Ken strategietypes toe via categorie-mapping of productbeheer."))

    missing_brand = db.query(P).filter(P.brand.is_(None)).count()
    if missing_brand:
        issues.append(_issue(
            "DRS_MISSING_BRAND", "warning", "Ontbrekende merknaam",
            "SKU's zonder merknaam (vereist voor DRS-kwaliteit)", missing_brand,
            "DRS", "Producten",
            "Merk-gebaseerde analyses (A-merk vs huismerk) missen deze producten.",
            "Vul merknamen aan in DRS of via product-CSV."))

    # ── Dekking concurrentie / voorraad ──────────────────────────────────
    skus_with_comp = db.query(models.FactCompetitorPriceDaily.sku_id).distinct().count()
    no_comp = max(0, total_skus - skus_with_comp)
    if no_comp:
        issues.append(_issue(
            "MISSING_COMPETITOR_DATA", "warning", "Geen concurrentiedata",
            "SKU's zonder enige concurrentprijs", no_comp,
            "PriceShape", "Concurrentie",
            "Zonder marktdata zijn prijsadviezen voor deze SKU's puur kosten-gebaseerd.",
            "Controleer de PriceShape-koppeling en matching (EAN/OEM) voor deze SKU's."))

    skus_with_stock = db.query(models.FactInventoryDaily.sku_id).distinct().count()
    no_stock = max(0, total_skus - skus_with_stock)
    if no_stock:
        issues.append(_issue(
            "MISSING_STOCK_DATA", "warning", "Geen voorraaddata",
            "SKU's zonder voorraad-/stockdata", no_stock,
            "DRS", "Voorraad",
            "Voorraadgestuurde prijsregels (schaarste, overstock) werken niet voor deze SKU's.",
            "Synchroniseer voorraadniveaus vanuit DRS of upload een inventory-CSV."))

    # ── Stale data per bron ──────────────────────────────────────────────
    today = _date.today()
    stale_checks = [
        ("STALE_COMPETITOR_PRICES", models.FactCompetitorPriceDaily.date, "PriceShape",
         "Concurrentie", "Concurrentprijzen", "Prijsadviezen zijn gebaseerd op een verouderd marktbeeld.",
         "Start een PriceShape-sync of controleer de feed-URL."),
        ("STALE_SALES_DATA", models.FactSalesDaily.date, "DRS",
         "Verkoop", "Verkoopdata", "Elasticiteits- en vraagmodellen rekenen met verouderde verkoopcijfers.",
         "Start een DRS-sync of upload recente verkoopdata."),
        ("STALE_TRAFFIC_DATA", models.FactTrafficDaily.date, "GA4",
         "Traffic", "Trafficdata", "Conversie- en trafficintelligence lopen achter op de werkelijkheid.",
         "Controleer de GA4-koppeling en draai een sync."),
        ("STALE_INVENTORY_DATA", models.FactInventoryDaily.date, "DRS",
         "Voorraad", "Voorraaddata", "Voorraadgestuurde prijsbeslissingen gebruiken verouderde niveaus.",
         "Synchroniseer voorraad vanuit DRS."),
    ]
    for code, date_col, source, module, label, impact, action in stale_checks:
        newest = db.query(func.max(date_col)).scalar()
        if newest is None:
            continue  # geen data is al gedekt door MISSING_*-checks
        age = (today - newest).days
        if age > STALE_DAYS:
            issues.append(_issue(
                code, "warning" if age <= 7 else "error", f"Verouderde {label.lower()}",
                f"{label} zijn {age} dagen oud (nieuwste: {newest.isoformat()})", age,
                source, module, impact, action))

    # ── Eenheid-problemen & pack-size mismatches ─────────────────────────
    unit_issues = db.query(P).filter(
        (P.paper_weight_gsm.isnot(None) & ((P.paper_weight_gsm <= 0) | (P.paper_weight_gsm > 500)))
        | (P.sheets_per_pack.isnot(None) & (P.sheets_per_pack <= 0))
    ).count()
    if unit_issues:
        issues.append(_issue(
            "UNIT_ISSUES", "warning", "Eenheid-problemen",
            "SKU's met onwaarschijnlijke eenheden (grammage ≤0 of >500 g/m², pakgrootte ≤0)", unit_issues,
            "Handmatig", "Producten",
            "Verkeerde eenheden vertekenen prijs-per-eenheid vergelijkingen met concurrenten.",
            "Corrigeer grammage/pakgrootte in de productdata."))

    pack_mismatch = db.query(models.ProductMatch).filter(
        models.ProductMatch.pack_size_warning == True  # noqa: E712
    ).count()
    if pack_mismatch:
        issues.append(_issue(
            "PACK_SIZE_MISMATCH", "warning", "Pack-size mismatches",
            "Concurrent-matches met een afwijkende pakgrootte", pack_mismatch,
            "PriceShape", "Concurrentie",
            "Prijzen worden vergeleken tussen ongelijke verpakkingen; de prijsindex is dan misleidend.",
            "Beoordeel deze matches en normaliseer naar prijs per eenheid of keur de match af."))

    # ── Feed onbereikbaar (netwerkniveau) ────────────────────────────────
    # Kijk of de meest recente PriceShape feed-sync is mislukt door een
    # netwerk- of verbindingsfout (ConnectorError "niet bereikbaar").
    # Lege-feed-fouten (0 producten) worden ook meegenomen: die beschermen
    # de last-known-good data maar moeten wél zichtbaar zijn.
    last_ps_job = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.upload_type == "api_sync_priceshape")
        .order_by(models.ImportJob.created_at.desc())
        .first()
    )
    if last_ps_job and last_ps_job.status in ("fout", "failed"):
        err_lower = (last_ps_job.error_message or "").lower()
        # Netwerkniveau: ConnectorError "niet bereikbaar" of generieke
        # connectiefouten (timeout, DNS, refused).
        _NETWORK_KEYWORDS = (
            "niet bereikbaar", "unreachable", "connecterror",
            "connection", "timeout", "network", "name or service",
            "0 producten en 0 concurrentprijzen",  # empty-feed guard
        )
        is_network = any(kw in err_lower for kw in _NETWORK_KEYWORDS)
        if is_network:
            issues.append(_issue(
                "FEED_UNREACHABLE", "error",
                "PriceShape feed niet bereikbaar",
                (
                    f"De laatste feed-sync is mislukt: "
                    f"{last_ps_job.error_message or 'onbekende fout'}"
                ),
                1,
                "PriceShape", "Connectoren",
                "Concurrentprijzen worden niet bijgewerkt; prijsbeslissingen draaien op "
                "verouderde data totdat de verbinding hersteld is.",
                "Controleer de feed-URL in de PriceShape-connectorinstellingen en start "
                "een handmatige sync om de verbinding te herstellen.",
            ))

    # ── Mislukte imports ─────────────────────────────────────────────────
    cutoff = datetime.utcnow() - timedelta(days=FAILED_IMPORT_WINDOW_DAYS)
    failed_imports = db.query(models.ImportJob).filter(
        models.ImportJob.status.in_(["fout", "failed"]),
        models.ImportJob.created_at >= cutoff,
    ).count()
    if failed_imports:
        issues.append(_issue(
            "FAILED_IMPORTS", "error", "Mislukte imports",
            f"Mislukte importtaken in de laatste {FAILED_IMPORT_WINDOW_DAYS} dagen", failed_imports,
            "Systeem", "Imports",
            "Mislukte imports betekenen dat een deel van de data niet is bijgewerkt; beslissingen draaien op oude of onvolledige data.",
            "Open de importgeschiedenis, bekijk het foutlog per batch en draai de import opnieuw."))

    # ── Low-confidence matches ───────────────────────────────────────────
    low_conf_ai = db.query(models.AiMatchResult).filter(
        models.AiMatchResult.confidence < LOW_CONFIDENCE,
        models.AiMatchResult.status == "PENDING",
    ).count()
    low_conf_pm = db.query(models.ProductMatch).filter(
        models.ProductMatch.match_confidence.isnot(None),
        models.ProductMatch.match_confidence < LOW_CONFIDENCE,
        models.ProductMatch.manual_override == False,  # noqa: E712
    ).count()
    low_conf = low_conf_ai + low_conf_pm
    if low_conf:
        issues.append(_issue(
            "LOW_CONFIDENCE_MATCHES", "warning", "Low-confidence matches",
            f"Concurrent-matches met confidence onder {LOW_CONFIDENCE:.0%} die nog niet beoordeeld zijn", low_conf,
            "AI", "Concurrentie",
            "Onzekere matches kunnen prijsadviezen op verkeerde marktprijzen baseren.",
            "Beoordeel deze matches in de AI-matching module (goedkeuren of afwijzen)."))

    # ── Stale AI-modellen ────────────────────────────────────────────────
    last_run = db.query(func.max(models.ModelRun.completed_at)).filter(
        models.ModelRun.status == "completed").scalar()
    if last_run is None:
        issues.append(_issue(
            "STALE_AI_MODELS", "error", "Geen geslaagde modelrun",
            "Er is nog nooit een geslaagde modelrun uitgevoerd", 1,
            "AI", "AI-modellen",
            "Zonder modelrun zijn er geen actuele prijsadviezen of scores.",
            "Start een modelrun via Model Health of de admin-pagina."))
    else:
        age_days = (datetime.utcnow() - last_run).days
        if age_days > MODEL_STALE_DAYS:
            issues.append(_issue(
                "STALE_AI_MODELS", "warning", "Verouderd AI-model",
                f"Laatste geslaagde modelrun is {age_days} dagen geleden", age_days,
                "AI", "AI-modellen",
                "Prijsadviezen en scores zijn gebaseerd op een verouderde modelstand.",
                "Start een nieuwe modelrun zodat adviezen de actuele data weerspiegelen."))

    failed_runs = db.query(models.ModelRun).filter(
        models.ModelRun.status == "failed",
        models.ModelRun.started_at >= cutoff).count()
    if failed_runs:
        issues.append(_issue(
            "FAILED_MODEL_RUNS", "warning", "Mislukte modelruns",
            f"Mislukte modelruns in de laatste {FAILED_IMPORT_WINDOW_DAYS} dagen", failed_runs,
            "AI", "AI-modellen",
            "Herhaald mislukkende runs kunnen betekenen dat adviezen stilletjes verouderen.",
            "Bekijk de foutmeldingen bij Model Health en los de onderliggende oorzaak op."))

    # ── PIM content completeness (§23) ───────────────────────────────────
    pim_scores = db.query(models.PimCompletenessScore).filter(
        models.PimCompletenessScore.channel_code.is_(None)).all()
    if pim_scores:
        low_comp = sum(1 for s in pim_scores if (s.completeness_pct or 0) < 60.0)
        if low_comp:
            issues.append(_issue(
                "PIM_LOW_COMPLETENESS", "warning", "Lage content-completeness",
                "SKU's met een content-completeness onder 60%", low_comp,
                "Systeem", "Productcontent",
                "Onvolledige productcontent verzwakt concurrentie-matching, zoekvindbaarheid en channel readiness.",
                "Open Content Completeness (PIM), vul ontbrekende attributen aan of genereer AI-suggesties."))
        qual_issues = sum(1 for s in pim_scores if (s.quality_issues or []))
        if qual_issues:
            issues.append(_issue(
                "PIM_QUALITY_ISSUES", "warning", "Contentkwaliteit-problemen",
                "SKU's met inconsistente of ongeldige contentvelden (bv. te korte naam, onwaarschijnlijke grammage)", qual_issues,
                "Systeem", "Productcontent",
                "Inconsistente content leidt tot verkeerde vergelijkingen en zwakke productpresentatie.",
                "Beoordeel de kwaliteitsissues per SKU op de Content Completeness-pagina."))

    pim_pending = db.query(models.PimAiSuggestion).filter(
        models.PimAiSuggestion.status == "PENDING").count()
    if pim_pending:
        issues.append(_issue(
            "PIM_PENDING_SUGGESTIONS", "info", "Openstaande AI-contentsuggesties",
            "AI-suggesties voor productcontent die op review wachten", pim_pending,
            "AI", "Productcontent",
            "Zolang suggesties niet beoordeeld zijn, blijft de content onvolledig.",
            "Beoordeel de suggesties op de Contentsuggesties-pagina (goedkeuren of afwijzen)."))

    # ── DRS-specifieke checks (bestaand) ─────────────────────────────────
    hier_names = {r.category_name for r in db.query(models.DimCategoryHierarchy.category_name).all()}
    if hier_names:
        missing_hier = db.query(P).filter(P.category.notin_(hier_names)).count()
        if missing_hier:
            issues.append(_issue(
                "DRS_MISSING_HIERARCHY", "warning", "Categorie buiten DRS-hiërarchie",
                "SKU's waarvan de categorie niet in de DRS-hiërarchieboom staat", missing_hier,
                "DRS", "Producten",
                "Rapportages per categorietak missen deze producten.",
                "Werk de DRS-hiërarchie bij of corrigeer de categorienamen."))

    inactief = db.query(P).filter(P.is_active == False).count()  # noqa: E712
    if inactief:
        issues.append(_issue(
            "DRS_INACTIEVE_ARTIKELEN", "info", "Inactieve artikelen",
            "Inactieve artikelen in de productcatalogus (uit DRS-import)", inactief,
            "DRS", "Producten",
            "Geen directe impact; inactieve artikelen worden uitgesloten van adviezen.",
            "Geen actie nodig, tenzij artikelen onterecht inactief staan."))

    neg_marge_ytd = db.query(P).filter(P.marge_ytd.isnot(None), P.marge_ytd < 0).count()
    if neg_marge_ytd:
        issues.append(_issue(
            "DRS_NEGATIEVE_MARGE_YTD", "error", "Negatieve YTD-marge",
            "SKU's met negatieve YTD-marge (DRS Datareport)", neg_marge_ytd,
            "DRS", "Prijzen",
            "Deze SKU's verliezen op jaarbasis geld; margereparatie heeft prioriteit.",
            "Analyseer prijs- en kostenopbouw; overweeg prijsverhoging of sanering."))

    return issues


def _sync_issue_registry(db: Session, detected: list[dict]) -> dict[str, models.DataQualityIssue]:
    """Upsert detecties in data_quality_issue; auto-resolve verdwenen detecties."""
    now = datetime.utcnow()
    existing = {r.issue_code: r for r in db.query(models.DataQualityIssue).all()}
    detected_codes = set()
    for d in detected:
        code = d["issue_code"]
        detected_codes.add(code)
        row = existing.get(code)
        if row is None:
            row = models.DataQualityIssue(
                issue_code=code, first_detected_at=now, status="open")
            db.add(row)
            existing[code] = row
        elif row.status == "opgelost":
            # Issue is terug: heropen de workflow
            row.status = "open"
            row.resolved_at = None
        row.title = d["title"]
        row.message = d["message"]
        row.severity = d["severity"]
        row.source = d["source"]
        row.module = d["module"]
        row.affected_count = d["affected_count"]
        row.business_impact = d["business_impact"]
        row.suggested_action = d["suggested_action"]
        row.last_detected_at = now
    # Auto-resolve issues die niet meer gedetecteerd worden
    for code, row in existing.items():
        if code not in detected_codes and row.status != "opgelost":
            row.status = "opgelost"
            row.resolved_at = now
            row.affected_count = 0
    db.commit()
    return existing


def _issue_row_dict(row: models.DataQualityIssue) -> dict:
    return {
        "id": row.id,
        "issue_code": row.issue_code,
        "title": row.title,
        "message": row.message,
        "severity": row.severity,
        "source": row.source,
        "module": row.module,
        "affected_count": row.affected_count,
        "business_impact": row.business_impact,
        "suggested_action": row.suggested_action,
        "owner": row.owner,
        "status": row.status,
        "first_detected_at": row.first_detected_at.isoformat() if row.first_detected_at else None,
        "last_detected_at": row.last_detected_at.isoformat() if row.last_detected_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "updated_by": row.updated_by,
    }


@router.get("/data-quality")
def get_data_quality(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    total_skus = db.query(models.DimProduct).count()
    detected = _detect_issues(db, total_skus)
    if current_user.role in REGISTRY_WRITE_ROLES:
        registry = _sync_issue_registry(db, detected)
    else:
        # Read-only scan: verrijk met bestaande registry-rijen zonder te schrijven
        registry = {r.issue_code: r for r in db.query(models.DataQualityIssue).all()}

    # Verrijk detecties met workflow-status uit het register
    issues = []
    for d in detected:
        row = registry.get(d["issue_code"])
        merged = dict(d)
        if row is not None:
            merged["id"] = row.id
            merged["owner"] = row.owner
            merged["status"] = row.status
            merged["first_detected_at"] = row.first_detected_at.isoformat() if row.first_detected_at else None
        issues.append(merged)

    summary = {d["issue_code"]: d["affected_count"] for d in detected}
    drs_issues = [i for i in issues if i["issue_code"].startswith("DRS_")]
    drs_summary = {i["issue_code"]: i["affected_count"] for i in drs_issues}

    open_issues = [i for i in issues if i.get("status") not in ("opgelost", "genegeerd")]
    error_count = sum(1 for i in open_issues if i["severity"] == "error")
    warning_count = sum(1 for i in open_issues if i["severity"] == "warning")
    score = max(0.0, 1.0 - (error_count * 0.15) - (warning_count * 0.05))

    hier_count = db.query(models.DimCategoryHierarchy).filter(
        models.DimCategoryHierarchy.active == True).count()  # noqa: E712

    # Laatste geplande (nachtelijke) scan — zichtbaar op de Data Quality-pagina.
    last_scheduled = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.upload_type == "data_quality_scan")
        .order_by(models.ImportJob.created_at.desc())
        .first()
    )

    return {
        "last_scan_at": datetime.utcnow().isoformat(),
        "last_scheduled_scan_at": (
            (last_scheduled.completed_at or last_scheduled.created_at).isoformat()
            if last_scheduled else None
        ),
        "last_scheduled_scan_status": last_scheduled.status if last_scheduled else None,
        "overall_score": round(score * 100, 1),
        "total_skus": total_skus,
        "issues": issues,
        "summary": summary,
        "drs_summary": drs_summary,
        "drs_issues": drs_issues,
        "hierarchy_node_count": hier_count,
        "counts": {
            "errors": error_count,
            "warnings": warning_count,
            "info": sum(1 for i in open_issues if i["severity"] == "info"),
            "open": sum(1 for i in issues if i.get("status") == "open"),
            "in_behandeling": sum(1 for i in issues if i.get("status") == "in_behandeling"),
        },
    }


@router.get("/data-quality/issues")
def list_quality_issues(
    status: str | None = None,
    severity: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Issue-register (incl. opgeloste issues) met workflowvelden."""
    q = db.query(models.DataQualityIssue)
    if status:
        q = q.filter(models.DataQualityIssue.status == status)
    if severity:
        q = q.filter(models.DataQualityIssue.severity == severity)
    if source:
        q = q.filter(models.DataQualityIssue.source == source)
    rows = q.order_by(models.DataQualityIssue.last_detected_at.desc()).all()
    return [_issue_row_dict(r) for r in rows]


class IssueUpdateRequest(BaseModel):
    owner: str | None = None
    status: str | None = None


@router.patch("/data-quality/issues/{issue_id}")
def update_quality_issue(
    issue_id: int,
    body: IssueUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Workflow-update: eigenaar toewijzen en/of status wijzigen."""
    row = db.query(models.DataQualityIssue).filter(models.DataQualityIssue.id == issue_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Issue niet gevonden.")
    if body.status is not None:
        if body.status not in VALID_ISSUE_STATUSES:
            raise HTTPException(status_code=400,
                                detail=f"Ongeldige status. Kies uit: {', '.join(sorted(VALID_ISSUE_STATUSES))}")
        row.status = body.status
        row.resolved_at = datetime.utcnow() if body.status == "opgelost" else None
    if body.owner is not None:
        row.owner = body.owner.strip() or None
    row.updated_by = current_user.username
    db.commit()
    db.refresh(row)
    return _issue_row_dict(row)
