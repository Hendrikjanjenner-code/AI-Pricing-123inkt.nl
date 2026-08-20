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


def _format_age(hours: float) -> str:
    """Menselijk leesbare leeftijd: 'minder dan een uur', 'N uur' of 'N dagen'."""
    if hours < 1:
        return "minder dan een uur"
    if hours < 48:
        return f"{int(hours)} uur"
    return f"{int(hours // 24)} dagen"


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

    # ── Prijsuitbijters in de referentieprijs (taak #266) ────────────────
    # Uitgesloten observaties worden op de fact-rij gemarkeerd (nooit
    # verwijderd); een hoog uitbijter-aandeel wijst op een dataprobleem
    # (verpakkingsmaat, decimaalfout, verkeerde match) of te strakke drempel.
    from engine import competition_engine as _ce
    FC = models.FactCompetitorPriceDaily
    outlier_run_date = db.query(func.max(FC.date)).filter(
        FC.excluded_reason == _ce.EXCLUSION_OUTLIER).scalar()
    if outlier_run_date is not None:
        outlier_count = db.query(func.count(FC.id)).filter(
            FC.date == outlier_run_date,
            FC.excluded_reason == _ce.EXCLUSION_OUTLIER).scalar() or 0
        obs_count = db.query(func.count(FC.id)).filter(
            FC.date == outlier_run_date, FC.price.isnot(None)).scalar() or 0
        rate = (outlier_count / obs_count) if obs_count else 0.0
        if outlier_count and rate > 0.15:
            causes: dict[str, int] = {}
            for (detail,) in db.query(FC.exclusion_detail).filter(
                    FC.date == outlier_run_date,
                    FC.excluded_reason == _ce.EXCLUSION_OUTLIER).all():
                c = (detail or {}).get("suspected_cause") or _ce.CAUSE_ABOVE_THRESHOLD
                causes[c] = causes.get(c, 0) + 1
            dominant = max(causes, key=lambda k: causes[k]) if causes else None
            dominant_txt = f" Meest voorkomende vermoedelijke oorzaak: {dominant} ({causes.get(dominant, 0)}×)." if dominant else ""
            issues.append(_issue(
                "COMPETITOR_PRICE_OUTLIER_RATE", "error" if rate > 0.35 else "warning",
                "Veel prijsuitbijters uitgesloten",
                f"{outlier_count} van {obs_count} concurrentprijzen ({rate * 100:.0f}%) is als "
                f"prijsuitbijter uitgesloten van de referentieprijs (run {outlier_run_date.isoformat()})."
                + dominant_txt,
                outlier_count, "PriceShape", "Concurrentie",
                "Een hoog uitbijter-aandeel vertekent de referentieprijs en kan wijzen op "
                "verpakkingsmaat-mismatches, decimaal-/valutafouten of een te strakke drempel.",
                "Bekijk de uitbijter-reconciliatie hieronder (per reden en vermoedelijke oorzaak); "
                "pas zo nodig de uitbijterdrempel aan via de importinstellingen op de connectoren-pagina."))

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
            now = datetime.utcnow()
            failed_at = last_ps_job.completed_at or last_ps_job.created_at
            failed_hours = max(0.0, (now - failed_at).total_seconds() / 3600.0)
            # Hoe lang is de feed al niet meer bereikt? Kijk naar de laatste
            # geslaagde sync — niet alleen naar de laatste poging. Een sync die
            # 2 dagen geleden mislukte en daarna niet is herprobeerd, betekent
            # dat de feed al 2 dagen niet bereikt is.
            last_ok = (
                db.query(func.max(
                    func.coalesce(models.ImportJob.completed_at,
                                  models.ImportJob.created_at)))
                .filter(models.ImportJob.upload_type == "api_sync_priceshape",
                        models.ImportJob.status == "geimporteerd")
                .scalar()
            )
            if last_ok is not None:
                unreached_hours = max(0.0, (now - last_ok).total_seconds() / 3600.0)
                reach_txt = (
                    f"laatste geslaagde sync {_format_age(unreached_hours)} geleden"
                )
            else:
                unreached_hours = None
                reach_txt = "er is nog nooit een geslaagde sync geweest"
            # Severity: >24u niet bereikt (of nooit bereikt) = error,
            # anders warning (recente storing, mogelijk tijdelijk).
            severity = (
                "error"
                if unreached_hours is None or unreached_hours > 24.0
                else "warning"
            )
            issues.append(_issue(
                "FEED_UNREACHABLE", severity,
                "PriceShape feed niet bereikbaar",
                (
                    f"De laatste feed-sync is mislukt op "
                    f"{failed_at.strftime('%d-%m-%Y %H:%M')} UTC "
                    f"({_format_age(failed_hours)} geleden; {reach_txt}): "
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

    # ── Producthiërarchie-checks (taak #215) ─────────────────────────────
    PHN = models.ProductHierarchyNode
    PHA = models.ProductHierarchyAssignment
    ph_nodes = db.query(func.count(PHN.id)).scalar() or 0
    if ph_nodes:
        # NB: query op de kolom zelf + .distinct(), zodat de subquery-kolom
        # 'sku_id' blijft heten (func.distinct(...) geeft een anonieme kolom
        # en dan faalt assigned_skus.c.sku_id met AttributeError).
        assigned_skus = (db.query(PHA.sku_id)
                         .filter(PHA.status == "active")
                         .distinct().subquery())
        unassigned = db.query(P).filter(
            P.is_active == True,  # noqa: E712
            P.sku_id.notin_(db.query(assigned_skus.c.sku_id))).count()
        if unassigned:
            issues.append(_issue(
                "PH_PRODUCTS_WITHOUT_HIERARCHY", "warning",
                "Producten zonder producthiërarchie",
                "Actieve SKU's zonder actieve koppeling in de centrale producthiërarchie",
                unassigned, "Systeem", "Producthiërarchie",
                "Deze producten vallen buiten alle hiërarchie-gefilterde analyses en rapportages.",
                "Importeer een hiërarchiebestand met deze productcodes of koppel ze handmatig."))

        parent_ids = {pid for (pid,) in db.query(PHN.parent_id).filter(PHN.parent_id.isnot(None))}
        existing_ids = {nid for (nid,) in db.query(PHN.id)}
        orphan = len(parent_ids - existing_ids)
        inactive_parents = {nid for (nid,) in db.query(PHN.id).filter(PHN.is_active == False)}  # noqa: E712
        orphan += (db.query(func.count(PHN.id))
                   .filter(PHN.is_active == True,  # noqa: E712
                           PHN.parent_id.in_(inactive_parents or {0})).scalar() or 0)
        if orphan:
            issues.append(_issue(
                "PH_ORPHAN_NODES", "error", "Wees-nodes in producthiërarchie",
                "Hiërarchie-nodes met een ontbrekende of inactieve parent", orphan,
                "Systeem", "Producthiërarchie",
                "Wees-nodes en hun producten zijn onbereikbaar via de boom en descendant-queries.",
                "Herstel de parent-koppeling of deactiveer de betreffende subtree bewust."))

        dup_paths = (db.query(PHN.parent_id, func.lower(PHN.name))
                     .filter(PHN.is_active == True)  # noqa: E712
                     .group_by(PHN.parent_id, func.lower(PHN.name))
                     .having(func.count(PHN.id) > 1).count())
        if dup_paths:
            issues.append(_issue(
                "PH_DUPLICATE_PATHS", "error", "Dubbele paden in producthiërarchie",
                "Meerdere actieve nodes met dezelfde naam onder dezelfde parent", dup_paths,
                "Systeem", "Producthiërarchie",
                "Producten kunnen op het verkeerde duplicaat worden gekoppeld; tellingen splitsen onbedoeld.",
                "Voeg de duplicaatnodes samen of hernoem ze."))

        multi_assign = (db.query(PHA.sku_id)
                        .filter(PHA.status == "active")
                        .group_by(PHA.sku_id)
                        .having(func.count(PHA.id) > 1).count())
        if multi_assign:
            issues.append(_issue(
                "PH_MULTIPLE_ACTIVE_ASSIGNMENTS", "warning",
                "Producten met meerdere actieve hiërarchie-koppelingen",
                "SKU's die aan meer dan één node tegelijk actief gekoppeld zijn", multi_assign,
                "Systeem", "Producthiërarchie",
                "Dubbele koppelingen laten producten dubbel meetellen in hiërarchie-aggregaties.",
                "Controleer deze SKU's en laat per product één primaire koppeling actief."))

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

    # ── Competition Data Quality: concurrentprofielen (taak #249) ─────────
    issues.extend(_detect_competitor_profile_issues(db))

    return issues


# Metadata per CP-issuecode: (severity, titel, omschrijving, impact, actie).
# Owner-toewijzing verloopt — net als bij alle andere codes — via de
# issue-workflow in het bestaande data-quality-overzicht.
_CP_ISSUE_META: dict[str, tuple[str, str, str, str, str]] = {
    "CP_UNKNOWN_COMPANY_SIZE": (
        "warning", "Onbekende bedrijfsomvang concurrent",
        "Concurrentprofielen zonder size class",
        "Zonder omvangsindicatie zijn dreiging en inkoopkracht niet in te schatten.",
        "Vul de size class aan of markeer het veld expliciet als unknown met bron."),
    "CP_MISSING_FOUNDED_YEAR": (
        "info", "Ontbrekend oprichtingsjaar concurrent",
        "Concurrentprofielen zonder oprichtingsjaar",
        "Beperkte impact; oprichtingsjaar ondersteunt volwassenheidsinschatting.",
        "Vul het oprichtingsjaar aan (KvK/jaarverslag)."),
    "CP_STALE_EMPLOYEE_ESTIMATE": (
        "warning", "Verouderde employee-estimates",
        "Employee-ranges ouder dan de freshness-regel voor employees",
        "Verouderde personeelsdata vertekent de company-size-classificatie.",
        "Herverifieer de employee-range en werk last_verified_at bij."),
    "CP_STALE_REVENUE_ESTIMATE": (
        "warning", "Verouderde revenue-estimates",
        "Revenue-ranges ouder dan de freshness-regel voor revenue",
        "Verouderde omzetdata vertekent financiële gezondheid en omvang.",
        "Herverifieer de revenue-range en werk last_verified_at bij."),
    "CP_UNKNOWN_FULFILMENT_MODEL": (
        "warning", "Onbekend fulfilmentmodel concurrent",
        "Concurrentprofielen zonder voorraad-/fulfilmentmodel",
        "Zonder fulfilmentmodel is de operationele dreiging niet te duiden.",
        "Bepaal het voorraadmodel of markeer het expliciet als unknown."),
    "CP_UNKNOWN_DROPSHIP_MODEL": (
        "warning", "Onbekend dropshipmodel concurrent",
        "Concurrentprofielen zonder dropship-aandeel",
        "Dropship-vragen aan de Copilot kunnen deze spelers niet meenemen.",
        "Vul het dropship-aandeel aan of markeer het expliciet als unknown."),
    "CP_UNKNOWN_ACTIVE_COUNTRIES": (
        "warning", "Onbekende actieve landen concurrent",
        "Concurrentprofielen zonder actieve geografische aanwezigheid",
        "Geografische schaal en internationale dreiging zijn niet te bepalen.",
        "Registreer de actieve landen (webshop/operationeel) met bron."),
    "CP_MISSING_OWNERSHIP": (
        "warning", "Ontbrekende ownership-informatie",
        "Concurrentprofielen zonder eigendomstype én zonder corporate relaties",
        "Groepsverbanden en financiële slagkracht blijven onzichtbaar.",
        "Vul ownership-type of corporate relaties aan (KvK/jaarverslag)."),
    "CP_STALE_FINANCIALS": (
        "warning", "Verouderde financiële data concurrent",
        "Alle bekende financiële observaties zijn ouder dan de freshness-regel",
        "Financiële gezondheidsscores leunen op verouderde cijfers.",
        "Herverifieer de meest recente jaarcijfers."),
    "CP_CONFLICTING_FINANCIALS": (
        "error", "Conflicterende financiële data concurrent",
        "Meerdere niet-overlappende waardes voor hetzelfde metric/boekjaar",
        "Tegenstrijdige cijfers maken de financiële score onbetrouwbaar.",
        "Beoordeel de bronnen en markeer de foute observatie."),
    "CP_MISSING_PROFILE_SOURCE": (
        "warning", "Profielvelden zonder bron",
        "Profielvelden of -rijen zonder bronvermelding of evidence",
        "Zonder bron kan de Copilot betrouwbaarheid niet onderbouwen.",
        "Voeg bron of evidence toe aan de betreffende velden."),
    "CP_LOW_CONFIDENCE_PROFILE": (
        "warning", "Lage confidence in concurrentprofiel",
        "Profielvelden met confidence onder de drempel",
        "Laag vertrouwen betekent dat antwoorden als hypothese moeten worden gebracht.",
        "Herverifieer de velden met lage confidence of bevestig ze handmatig."),
    "CP_INCONSISTENT_PARENT_RELATIONS": (
        "error", "Inconsistente parent-relaties",
        "Meerdere actieve parents/ultimate parents of zelfverwijzing",
        "Groepsanalyses ('zelfde groep') geven tegenstrijdige antwoorden.",
        "Corrigeer de corporate relaties: één actieve parent per concurrent."),
}


def _detect_competitor_profile_issues(db: Session) -> list[dict]:
    """Profielkwaliteit-detecties over alle shops met concurrentprofielen.

    Gebruikt exact dezelfde vlag-definities als de Copilot-functie
    get_competitor_profile_quality (services.competitor_profile.
    profile_quality_flags), zodat scan en Copilot nooit uiteenlopen.
    Fail-safe: een fout hier mag de rest van de scan nooit breken.
    """
    from services.competitor_profile import profile_quality_flags
    issues: list[dict] = []
    try:
        shop_ids = {sid for (sid,) in db.query(
            models.CompetitorProfile.shop_id).distinct()}
        shop_ids |= {sid for (sid,) in db.query(
            models.CompetitorBusinessProfile.shop_id).distinct()}
        counts: dict[str, int] = {}
        for sid in sorted(shop_ids):
            for info in profile_quality_flags(db, sid).values():
                for code in info["flags"]:
                    counts[code] = counts.get(code, 0) + 1
        for code, meta in _CP_ISSUE_META.items():
            n = counts.get(code, 0)
            if not n:
                continue
            severity, title, message, impact, action = meta
            issues.append(_issue(
                code, severity, title, message, n,
                "Competition", "Concurrentprofielen", impact, action))
    except Exception:  # pragma: no cover — fail-safe, nooit de scan breken
        import logging
        logging.getLogger(__name__).exception(
            "Concurrentprofiel-detecties mislukt; overgeslagen in deze scan.")
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
    from services.data_quality_scan import run_quality_scan, last_scan_info
    if current_user.role in REGISTRY_WRITE_ROLES:
        # Volledige scan: registry-sync + signalen + scan-run audit.
        scan = run_quality_scan(db, triggered_by="dashboard")
        total_skus = scan["total_skus"]
        detected = scan["detected"]
        registry = scan["registry"]
    else:
        # Read-only scan (viewers): detecteer wel, maar schrijf niets —
        # verrijk met bestaande registry-rijen.
        total_skus = db.query(models.DimProduct).count()
        detected = _detect_issues(db, total_skus)
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

    return {
        "last_scan": last_scan_info(db),
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


@router.get("/data-quality/scans")
def list_scan_runs(
    limit: int = 30,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Recente scan-runs (nieuwste eerst) voor de trendweergave in het dashboard.

    Met ``status=geslaagd`` filtert de server vóór de limit, zodat de trend
    altijd de laatste N geslaagde scans bevat, ook als er recent runs faalden.
    """
    from services.data_quality_scan import recent_scan_runs
    limit = max(1, min(limit, 100))
    return {"scans": recent_scan_runs(db, limit=limit, status=status)}


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


@router.get("/data-quality/outliers")
def get_outlier_reconciliation(
    shop_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Uitbijter-/reconciliatiesectie voor het datakwaliteitscentrum.

    Uitgesloten concurrentprijzen worden nooit verwijderd, alleen gemarkeerd
    (fact_competitor_price_daily.excluded_reason). Deze endpoint aggregeert
    de meest recente gemarkeerde dag: totalen per reden, vermoedelijke
    oorzaken van prijsuitbijters, meest geraakte concurrenten/categorieën en
    voorbeelden per reden (drill-down).
    """
    from engine import competition_engine as ce
    from services import import_settings as imps
    import authz

    F = models.FactCompetitorPriceDaily
    P = models.DimProduct

    # Effectieve shop-scope: expliciete shop buiten de toegestane set → 403;
    # zonder shop-keuze zien gescopede gebruikers nooit cross-shop data.
    allowed = authz.user_allowed_shop_ids(db, current_user)
    if shop_id is not None:
        if allowed is not None and shop_id not in allowed:
            raise HTTPException(status_code=403, detail="Geen toegang tot deze shop")
        shop_scope: set[int] | None = {shop_id}
    else:
        shop_scope = set(allowed) if allowed is not None else None

    scoped = db.query(func.max(F.date)).filter(F.excluded_reason.isnot(None))
    if shop_scope is not None:
        scoped = scoped.filter(F.shop_id.in_(shop_scope))
    run_date = scoped.scalar()
    settings = imps.get_settings(db)
    empty = {
        "run_date": None, "total_observations": 0, "total_excluded": 0,
        "outlier_threshold": settings.get("outlier_threshold"),
        "by_reason": {}, "by_suspected_cause": {},
        "top_competitors": [], "top_categories": [], "examples": {},
    }
    if run_date is None:
        return empty

    def _base(q):
        q = q.filter(F.date == run_date)
        if shop_scope is not None:
            q = q.filter(F.shop_id.in_(shop_scope))
        return q

    total_observations = _base(db.query(func.count(F.id)).filter(F.price.isnot(None))).scalar() or 0
    excluded_q = _base(db.query(F).filter(F.excluded_reason.isnot(None)))

    by_reason = {
        reason: count for reason, count in
        _base(db.query(F.excluded_reason, func.count(F.id))
              .filter(F.excluded_reason.isnot(None))).group_by(F.excluded_reason).all()
    }
    total_excluded = sum(by_reason.values())

    # Vermoedelijke oorzaken (alleen uitbijters hebben een detail met cause).
    by_cause: dict[str, int] = {}
    for (detail,) in _base(db.query(F.exclusion_detail).filter(
            F.excluded_reason == ce.EXCLUSION_OUTLIER)).all():
        cause = (detail or {}).get("suspected_cause") or ce.CAUSE_ABOVE_THRESHOLD
        by_cause[cause] = by_cause.get(cause, 0) + 1

    top_competitors = [
        {"competitor_name": name, "excluded": count}
        for name, count in _base(db.query(F.competitor_name, func.count(F.id))
                                 .filter(F.excluded_reason.isnot(None)))
        .group_by(F.competitor_name).order_by(func.count(F.id).desc()).limit(10).all()
    ]
    cat_q = _base(db.query(func.coalesce(P.category, "Onbekend"), func.count(F.id))
                  .filter(F.excluded_reason.isnot(None))
                  .join(P, (P.sku_id == F.sku_id) & (P.shop_id == F.shop_id)))
    top_categories = [
        {"category": cat, "excluded": count}
        for cat, count in cat_q.group_by(func.coalesce(P.category, "Onbekend"))
        .order_by(func.count(F.id).desc()).limit(10).all()
    ]

    # Voorbeelden per reden (drill-down): max 5 per reden.
    examples: dict[str, list[dict]] = {}
    for reason in by_reason:
        rows = excluded_q.filter(F.excluded_reason == reason).order_by(F.id).limit(5).all()
        examples[reason] = [{
            "sku_id": r.sku_id,
            "competitor_name": r.competitor_name,
            "price": float(r.price) if r.price is not None else None,
            "detail": r.exclusion_detail,
        } for r in rows]

    return {
        "run_date": run_date.isoformat(),
        "total_observations": total_observations,
        "total_excluded": total_excluded,
        "outlier_threshold": settings.get("outlier_threshold"),
        "by_reason": by_reason,
        "by_suspected_cause": by_cause,
        "top_competitors": top_competitors,
        "top_categories": top_categories,
        "examples": examples,
    }


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
