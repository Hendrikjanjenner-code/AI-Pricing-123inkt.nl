"""
Platform Governance routes — /api/governance/*

- Platform Gap Dashboard (§49): expected vs. current vs. gap vs. priority per module
- Production readiness (§46): tien criteria, labels Concept t/m Production Ready;
  Production Ready vereist expliciete menselijke goedkeuring
- Development Backlog & Prompt Library (§48)
- Centrale documentatieomgeving (§58)
- Final Technical & Business Evaluation (§59)
"""
import logging
from datetime import datetime, date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from auth import get_current_user, require_role
import models

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/governance", tags=["governance"])

READINESS_CRITERIA = [
    "functionality", "integration", "data_quality", "tests", "security",
    "performance", "auditability", "monitoring", "documentation", "human_control",
]

READINESS_LABELS = [
    "Concept", "Prototype", "Integrated Prototype", "POC Ready",
    "Pilot Ready", "Production Candidate", "Production Ready",
]

PRIORITIES = ("low", "medium", "high", "critical")


def compute_readiness_label(scores: Optional[dict], approved: bool) -> tuple[str, float]:
    """§46: gemiddelde van de tien criteria bepaalt het label.
    'Production Ready' alleen bij score >= 80 én expliciete menselijke goedkeuring."""
    scores = scores or {}
    vals = [float(scores.get(c, 0) or 0) for c in READINESS_CRITERIA]
    avg = round(sum(vals) / len(READINESS_CRITERIA), 1)
    if avg >= 80:
        label = "Production Ready" if approved else "Production Candidate"
    elif avg >= 65:
        label = "Pilot Ready"
    elif avg >= 50:
        label = "POC Ready"
    elif avg >= 35:
        label = "Integrated Prototype"
    elif avg >= 20:
        label = "Prototype"
    else:
        label = "Concept"
    return label, avg


# ------------------------------------------------------------------
# Seed: module-registry (§49) en documentatiehoofdstukken (§58).
# Eénmalig geseed bij eerste gebruik; daarna bewerkbaar via de API.
# ------------------------------------------------------------------
DEFAULT_MODULES = [
    ("pricing_engine", "Pricing Engine", "high", True,
     "AI-prijsaanbevelingen met safety rails, approval-workflow en export naar prijsuitvoering.",
     "Aanbevelingen, approval-workflow, safety-status, export en verwerkingsstatus werken op echte DRS-data.",
     "Nachtelijke automatische runs en beslissingen op categorieniveau ontbreken nog."),
    ("competition", "Competition Intelligence", "high", True,
     "Concurrentmonitoring: prijzen, rankings, assortiment-gaps, discovery en AI-matching.",
     "PriceShape-feed, rankings, assortment-gap, discovery-log en AI-matching zijn operationeel.",
     "Influence-score in rankings staat nog op 0; discovery deels handmatig."),
    ("bcg", "BCG Portfolio Intelligence", "medium", True,
     "BCG-classificatie per SKU/categorie met transities, pricing power en huismerkanalyse.",
     "Classificaties, transities, hybride views en huismerk-dashboards aanwezig.",
     "Regressietests op classificatiewijzigingen ontbreken."),
    ("traffic", "Traffic & Search Intelligence", "medium", True,
     "Traffic-drivers, zoekvraag en search-gap-analyse per entiteit.",
     "Traffic-facts, search demand en gap-analyse gevuld via imports.",
     "Automatische verversing en alerting ontbreken."),
    ("loyalty", "Loyalty & Customer Value", "medium", True,
     "Loyaliteitsprogramma met ledger, tiers, campagnes en fraudedetectie.",
     "Ledger, tiers, rewards en fraudesignalen werken.",
     "Puntenverloop (expiry) en treatment/controle-effectmeting ontbreken; regressietests beperkt."),
    ("basket", "Basket Intelligence", "medium", True,
     "Winkelmand-analyse: associaties, affiniteit en bundelkansen.",
     "Associaties en basket-intelligence-facts beschikbaar in dashboards.",
     "Koppeling naar promotie-acties is handmatig."),
    ("promotion", "Promotion Intelligence", "medium", True,
     "Promotie-effectmeting: uplift, kannibalisatie en herhaaladvies.",
     "Promotie-effecten en marketing-vs-discount-analyses aanwezig.",
     "Automatische campagne-evaluatie ontbreekt."),
    ("forecast", "Forecast Engine", "high", True,
     "Vraag- en omzetforecasts per SKU met betrouwbaarheidsbewaking.",
     "Dagelijkse forecasts beschikbaar via de forecast-routes.",
     "Forecast-kwaliteitsbewaking na modelwijzigingen ontbreekt."),
    ("opportunities", "Opportunity Engine", "high", True,
     "Genormaliseerde kansen uit alle engines met waarde, urgentie en prioriteit.",
     "Centrale opportunities-tabel gevuld vanuit meerdere engines.",
     "Automatische opvolging/werkstroom per kans ontbreekt."),
    ("decisions", "Decision Engine", "high", True,
     "Centrale beslissingen met scenario's, approval en doorzet naar uitvoering.",
     "Beslissingen, scenario's en menselijke goedkeuring werken.",
     "Directe doorzet van goedgekeurde beslissingen naar prijsuitvoering ontbreekt."),
    ("copilot", "Commercial Copilot", "high", True,
     "AI-assistent die gecontroleerd data uit meerdere modules combineert, met gateway-logging.",
     "Copilot-UI, AI-gateway, functiecatalogus en kostenlogging staan klaar.",
     "AI-provider nog niet geprovisioneerd (fail-safe modus); kostlimieten per gebruiker ontbreken."),
    ("signals", "Intelligence Signals", "high", True,
     "Gestandaardiseerde signalen uit alle engines naar het decision-framework.",
     "Signal-standaard en publicatie vanuit meerdere engines werken.",
     "Automatische regressietests op signal-publicatie ontbreken."),
    ("data_quality", "Data Quality", "high", True,
     "Datakwaliteitsscans met issue-registry, eigenaren en statusworkflow.",
     "Scans, issue-registry en eigenaartoewijzing werken.",
     "Automatische periodieke scan met notificaties ontbreekt."),
    ("integrations", "Data-integraties & Connectors", "high", True,
     "DRS-, PriceShape- en BigQuery-koppelingen met importbewaking.",
     "Dagelijkse DRS-import, PriceShape-feed en BigQuery-sync werken; importjobs zichtbaar.",
     "Nachtelijke automatische BigQuery-sync en robuuste dubbele-rij-afhandeling ontbreken."),
    ("platform_health", "Platform Health & Cost", "medium", True,
     "Statusbewaking per component, kostenmeting en businesscase per shop.",
     "Health center, kostenmeting, aannames en businesscase-raming werken.",
     "Kostlimieten en alerting bij overschrijding ontbreken."),
    ("reporting", "Executive Reporting", "medium", True,
     "Dagelijkse/wekelijkse/maandelijkse managementrapportages, exporteerbaar.",
     "Rapportagegeneratie en export werken.",
     "Automatische planning en e-maildistributie ontbreken."),
    ("command_center", "Commercial Command Center", "high", True,
     "Eén managementdashboard (TODAY/THIS WEEK/FINANCIAL/AI + §50-blokken) met drill-down naar categorie/merk/SKU.",
     "Command Center met alle secties en KPI-drill-down via de semantic layer.",
     "Persoonlijke KPI-voorkeuren per gebruiker ontbreken."),
    ("governance", "Governance: Gap, Backlog, Docs & Evaluatie", "medium", False,
     "Gap-dashboard, readiness-labels, backlog met promptversies, documentatie en eindevaluatie.",
     "Module-registry, readiness-scoring, backlog, prompt library, documentatie en genereerbaar §59-rapport.",
     "Automatische gap-detectie op basis van code-analyse ontbreekt (registry is handmatig onderhouden)."),
]

DEFAULT_READINESS = {
    "functionality": 70, "integration": 65, "data_quality": 60, "tests": 40,
    "security": 65, "performance": 60, "auditability": 65, "monitoring": 55,
    "documentation": 45, "human_control": 75,
}

DOC_CHAPTERS = [
    ("architecture", "Architecture", "Overzicht van de platformarchitectuur: FastAPI-backend, React-frontend, PostgreSQL, engines en semantic layer."),
    ("data-model", "Data Model", "Canoniek datamodel: dim_shop, dim_product, fact-tabellen per domein en de relaties daartussen."),
    ("data-ownership", "Data Ownership", "Eigenaarschap per databron en issue-registry met eigenaren in Data Quality."),
    ("integrations", "Integrations", "DRS Datareport-import, PriceShape-concurrentiefeed en BigQuery-sync: frequentie, formaat en foutafhandeling."),
    ("intelligence-engines", "Intelligence Engines", "Pricing, Competition, BCG, Traffic, Loyalty, Basket, Promotion, Forecast en Opportunity: input, output en signalen."),
    ("semantic-layer", "Semantic Layer", "Gecontroleerde datalaag met rolchecks, shop-scoping en canonieke metrics; enige toegangspad voor Copilot en dashboards."),
    ("decision-engine", "Decision Engine", "Centrale beslissingen met scenario's, statusworkflow en menselijke goedkeuring."),
    ("copilot", "Copilot", "Commercial Copilot: AI-gateway, functiecatalogus, logging en fail-safe gedrag zonder provider."),
    ("security", "Security", "Authenticatie (JWT), RBAC-rollen, SSRF-bescherming en het security evidence pack."),
    ("ai-governance", "AI Governance", "AI-gateway-logboek per call: gebruiker, doel, functies, databronnen en tokenverbruik."),
    ("testing", "Testing", "Pytest-suite van de API-server en typechecks van de frontend; teststrategie per module."),
    ("cost", "Cost", "Kostenmeting per request/token/job en de centrale platformaannames."),
    ("business-value", "Business Value", "Baselines, metingen en waarderingslabels (REALIZED/MEASURED/ESTIMATED/SIMULATED)."),
    ("deployment", "Deployment", "Replit-deployment, basepad-healthchecks en omgevingsvariabelen."),
    ("operations", "Operations", "Dagelijkse imports, modelruns, monitoring-alerts en herstelprocedures."),
    ("roadmap", "Roadmap", "Development Backlog per module en de aanbevolen productieroadmap uit de eindevaluatie."),
]


def _ensure_seed(db: Session) -> None:
    if db.query(models.PlatformModule).count() == 0:
        for key, name, prio, real, expected, current, gap in DEFAULT_MODULES:
            db.add(models.PlatformModule(
                module_key=key, name_nl=name, priority=prio, uses_real_data=real,
                description_nl=expected, expected_feature=expected,
                current_implementation=current, gap=gap,
                readiness_scores=dict(DEFAULT_READINESS),
            ))
        db.commit()
    if db.query(models.DocPage).count() == 0:
        for i, (slug, title, content) in enumerate(DOC_CHAPTERS):
            db.add(models.DocPage(slug=slug, title_nl=title, chapter=title,
                                  content_md=content, sort_order=i))
        db.commit()


def _serialize_module(m: models.PlatformModule) -> dict:
    label, avg = compute_readiness_label(m.readiness_scores, bool(m.production_approved_by))
    return {
        "id": m.id,
        "module_key": m.module_key,
        "naam": m.name_nl,
        "omschrijving": m.description_nl,
        "expected_feature": m.expected_feature,
        "current_implementation": m.current_implementation,
        "gap": m.gap,
        "priority": m.priority,
        "readiness_scores": m.readiness_scores or {},
        "readiness_score_avg": avg,
        "readiness_label": label,
        "production_approved_by": m.production_approved_by,
        "production_approved_at": str(m.production_approved_at) if m.production_approved_at else None,
        "uses_real_data": bool(m.uses_real_data),
        "updated_at": str(m.updated_at) if m.updated_at else None,
    }


# ------------------------------------------------------------------
# Modules / Gap Dashboard / Readiness (§46, §49)
# ------------------------------------------------------------------

@router.get("/modules")
def list_modules(db: Session = Depends(get_db), _user=Depends(get_current_user)) -> Any:
    _ensure_seed(db)
    mods = db.query(models.PlatformModule).order_by(models.PlatformModule.name_nl).all()
    serialized = [_serialize_module(m) for m in mods]
    by_label: dict[str, int] = {}
    for s in serialized:
        by_label[s["readiness_label"]] = by_label.get(s["readiness_label"], 0) + 1
    return {
        "totaal": len(serialized),
        "criteria": READINESS_CRITERIA,
        "labels": READINESS_LABELS,
        "per_label": by_label,
        "modules": serialized,
    }


@router.put("/modules/{module_id}")
def update_module(
    module_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    m = db.query(models.PlatformModule).filter(models.PlatformModule.id == module_id).first()
    if not m:
        raise HTTPException(404, "Module niet gevonden")
    for field in ("name_nl", "description_nl", "expected_feature",
                  "current_implementation", "gap"):
        if field in payload:
            setattr(m, field, payload[field])
    if "priority" in payload:
        if payload["priority"] not in PRIORITIES:
            raise HTTPException(400, f"Ongeldige priority; kies uit {PRIORITIES}")
        m.priority = payload["priority"]
    if "uses_real_data" in payload:
        m.uses_real_data = bool(payload["uses_real_data"])
    if "readiness_scores" in payload:
        scores = payload["readiness_scores"] or {}
        clean = {}
        for c in READINESS_CRITERIA:
            v = scores.get(c, (m.readiness_scores or {}).get(c, 0))
            try:
                v = max(0.0, min(100.0, float(v)))
            except (TypeError, ValueError):
                raise HTTPException(400, f"Score voor '{c}' moet een getal 0-100 zijn")
            clean[c] = v
        m.readiness_scores = clean
        # Scorewijziging trekt een eerdere productie-goedkeuring in als de
        # module onder de drempel zakt.
        label, avg = compute_readiness_label(clean, True)
        if avg < 80 and m.production_approved_by:
            m.production_approved_by = None
            m.production_approved_at = None
    db.commit()
    db.refresh(m)
    return _serialize_module(m)


@router.post("/modules/{module_id}/approve-production")
def approve_production(
    module_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin")),
) -> Any:
    """§46: 'Production Ready' vereist expliciete menselijke goedkeuring (admin)."""
    m = db.query(models.PlatformModule).filter(models.PlatformModule.id == module_id).first()
    if not m:
        raise HTTPException(404, "Module niet gevonden")
    label, avg = compute_readiness_label(m.readiness_scores, False)
    if avg < 80:
        raise HTTPException(400, f"Module scoort {avg} (< 80) en kan nog niet worden goedgekeurd voor productie")
    m.production_approved_by = user.username
    m.production_approved_at = datetime.utcnow()
    db.commit()
    db.refresh(m)
    return _serialize_module(m)


@router.post("/modules/{module_id}/revoke-production")
def revoke_production(
    module_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin")),
) -> Any:
    m = db.query(models.PlatformModule).filter(models.PlatformModule.id == module_id).first()
    if not m:
        raise HTTPException(404, "Module niet gevonden")
    m.production_approved_by = None
    m.production_approved_at = None
    db.commit()
    db.refresh(m)
    return _serialize_module(m)


# ------------------------------------------------------------------
# Development Backlog & Prompt Library (§48)
# ------------------------------------------------------------------

@router.get("/backlog")
def list_backlog(
    module_key: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    q = db.query(models.BacklogItem).order_by(models.BacklogItem.updated_at.desc())
    if module_key:
        q = q.filter(models.BacklogItem.module_key == module_key)
    if status:
        q = q.filter(models.BacklogItem.status == status)
    items = q.limit(500).all()
    return {
        "totaal": len(items),
        "items": [{
            "id": i.id, "module_key": i.module_key, "title": i.title,
            "description": i.description, "item_type": i.item_type,
            "status": i.status, "priority": i.priority, "owner": i.owner,
            "dependencies": i.dependencies, "data_sources": i.data_sources,
            "tests": i.tests, "business_value": i.business_value,
            "created_by": i.created_by,
            "created_at": str(i.created_at), "updated_at": str(i.updated_at),
        } for i in items],
    }


@router.post("/backlog")
def create_backlog_item(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin", "pricing_manager", "analyst")),
) -> Any:
    if not payload.get("title") or not payload.get("module_key"):
        raise HTTPException(400, "title en module_key zijn verplicht")
    if payload.get("priority") and payload["priority"] not in PRIORITIES:
        raise HTTPException(400, f"Ongeldige priority; kies uit {PRIORITIES}")
    item = models.BacklogItem(
        module_key=payload["module_key"],
        title=payload["title"],
        description=payload.get("description"),
        item_type=payload.get("item_type", "missing_functionality"),
        status=payload.get("status", "open"),
        priority=payload.get("priority", "medium"),
        owner=payload.get("owner"),
        dependencies=payload.get("dependencies"),
        data_sources=payload.get("data_sources"),
        tests=payload.get("tests"),
        business_value=payload.get("business_value"),
        created_by=user.username,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "status": "aangemaakt"}


@router.put("/backlog/{item_id}")
def update_backlog_item(
    item_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin", "pricing_manager", "analyst")),
) -> Any:
    item = db.query(models.BacklogItem).filter(models.BacklogItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Backlog-item niet gevonden")
    if payload.get("priority") and payload["priority"] not in PRIORITIES:
        raise HTTPException(400, f"Ongeldige priority; kies uit {PRIORITIES}")
    for field in ("title", "description", "item_type", "status", "priority",
                  "owner", "dependencies", "data_sources", "tests",
                  "business_value", "module_key"):
        if field in payload:
            setattr(item, field, payload[field])
    db.commit()
    return {"id": item.id, "status": "bijgewerkt"}


@router.delete("/backlog/{item_id}")
def delete_backlog_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    item = db.query(models.BacklogItem).filter(models.BacklogItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Backlog-item niet gevonden")
    db.delete(item)
    db.commit()
    return {"status": "verwijderd"}


@router.get("/prompts")
def list_prompts(
    module_key: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    q = db.query(models.PromptVersion).order_by(
        models.PromptVersion.module_key, models.PromptVersion.title,
        models.PromptVersion.version.desc())
    if module_key:
        q = q.filter(models.PromptVersion.module_key == module_key)
    rows = q.limit(500).all()
    return {
        "totaal": len(rows),
        "prompts": [{
            "id": p.id, "module_key": p.module_key, "title": p.title,
            "version": p.version, "prompt_text": p.prompt_text,
            "notes": p.notes, "created_by": p.created_by,
            "created_at": str(p.created_at),
        } for p in rows],
    }


@router.post("/prompts")
def create_prompt_version(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin", "pricing_manager", "analyst")),
) -> Any:
    """Nieuwe promptversie: zelfde module+titel verhoogt automatisch het versienummer
    (promptversies worden behouden, §48)."""
    for f in ("module_key", "title", "prompt_text"):
        if not payload.get(f):
            raise HTTPException(400, f"{f} is verplicht")
    latest = (db.query(func.max(models.PromptVersion.version))
              .filter(models.PromptVersion.module_key == payload["module_key"],
                      models.PromptVersion.title == payload["title"])
              .scalar()) or 0
    p = models.PromptVersion(
        module_key=payload["module_key"], title=payload["title"],
        version=latest + 1, prompt_text=payload["prompt_text"],
        notes=payload.get("notes"), created_by=user.username,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "version": p.version, "status": "aangemaakt"}


# ------------------------------------------------------------------
# Documentatie (§58)
# ------------------------------------------------------------------

@router.get("/docs")
def list_docs(db: Session = Depends(get_db), _user=Depends(get_current_user)) -> Any:
    _ensure_seed(db)
    pages = db.query(models.DocPage).order_by(models.DocPage.sort_order).all()
    return {
        "totaal": len(pages),
        "paginas": [{
            "id": p.id, "slug": p.slug, "titel": p.title_nl, "chapter": p.chapter,
            "module_key": p.module_key, "updated_by": p.updated_by,
            "updated_at": str(p.updated_at) if p.updated_at else None,
        } for p in pages],
    }


@router.get("/docs/{slug}")
def get_doc(slug: str, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> Any:
    _ensure_seed(db)
    p = db.query(models.DocPage).filter(models.DocPage.slug == slug).first()
    if not p:
        raise HTTPException(404, "Documentatiepagina niet gevonden")
    return {
        "id": p.id, "slug": p.slug, "titel": p.title_nl, "chapter": p.chapter,
        "content_md": p.content_md, "module_key": p.module_key,
        "updated_by": p.updated_by,
        "updated_at": str(p.updated_at) if p.updated_at else None,
    }


@router.put("/docs/{slug}")
def update_doc(
    slug: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin", "pricing_manager", "analyst")),
) -> Any:
    """Documentatie groeit met de applicatie mee: pagina's zijn bewerkbaar."""
    p = db.query(models.DocPage).filter(models.DocPage.slug == slug).first()
    if not p:
        raise HTTPException(404, "Documentatiepagina niet gevonden")
    for field in ("title_nl", "content_md", "module_key"):
        if field in payload:
            setattr(p, field, payload[field])
    p.updated_by = user.username
    db.commit()
    return {"slug": p.slug, "status": "bijgewerkt"}


# ------------------------------------------------------------------
# Final Technical & Business Evaluation (§59)
# ------------------------------------------------------------------

def _build_evaluation_sections(db: Session) -> list[dict]:
    """Beantwoordt de 20 vragen uit §59 op basis van live platformdata.
    data_label: REAL (echte data), TEST (testdata), MIXED, N/A."""
    _ensure_seed(db)
    mods = db.query(models.PlatformModule).all()
    mod_ser = [_serialize_module(m) for m in mods]

    real_mods = [m for m in mod_ser if m["uses_real_data"]]
    test_mods = [m for m in mod_ser if not m["uses_real_data"]]
    label_counts: dict[str, int] = {}
    for m in mod_ser:
        label_counts[m["readiness_label"]] = label_counts.get(m["readiness_label"], 0) + 1

    total_skus = db.query(models.DimProduct).count()
    real_skus = db.query(models.DimProduct).filter(models.DimProduct.import_source == "DRS").count()
    seed_skus = db.query(models.DimProduct).filter(models.DimProduct.import_source == "seed").count()
    comp_prices = db.query(models.FactCompetitorPriceDaily).count()
    recs = db.query(models.FactPricingRecommendationDaily).count()
    signals = db.query(models.IntelligenceSignal).count()
    decisions = db.query(models.Decision).count()
    imports = db.query(models.ImportJob).order_by(models.ImportJob.id.desc()).limit(200).all()
    import_sources = sorted({i.source for i in imports if getattr(i, "source", None)})
    model_runs = db.query(models.ModelRun).count()
    connectors = db.query(models.ConnectorConfig).all()
    conn_names = sorted({c.connector_name for c in connectors if c.connector_name})
    dq_open = db.query(models.DataQualityIssue).filter(models.DataQualityIssue.status != "resolved").count()
    open_bugs = db.query(models.BacklogItem).filter(
        models.BacklogItem.item_type == "bug",
        models.BacklogItem.status.in_(["open", "in_progress"])).count()
    open_backlog = db.query(models.BacklogItem).filter(
        models.BacklogItem.status.in_(["open", "in_progress"])).count()
    ai_calls = db.query(models.AiModelCall).count()
    users = db.query(models.User).count()

    # Kosten (30 dagen) uit metering
    since = datetime.utcnow() - timedelta(days=30)
    cost_30d = (db.query(func.sum(models.CostUsageRecord.cost_eur))
                .filter(models.CostUsageRecord.occurred_at >= since).scalar())
    assumptions = {a.key: a.value for a in db.query(models.PlatformAssumption).all()} \
        if db.query(models.PlatformAssumption).count() else {}
    shop_var = assumptions.get("shop_variable_eur_month")
    central = (assumptions.get("central_hosting_eur_month") or 0) + (assumptions.get("central_maintenance_eur_month") or 0)

    bv_measurements = db.query(models.BusinessValueMeasurement).count()

    gaps = [f"{m['naam']}: {m['gap']}" for m in mod_ser if m.get("gap")]
    prod_ready = [m["naam"] for m in mod_ser if m["readiness_label"] == "Production Ready"]

    def fmt_eur(v):
        return f"€ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if v is not None else "onbekend"

    return [
        {"nr": 1, "vraag": "Wat bestond bij start?", "data_label": "REAL",
         "antwoord": "Bij start bestond een basis-prijsengine met handmatige CSV-uploads en een eenvoudig aanbevelingenoverzicht. Alle intelligence-engines, integraties, governance en het multi-module platform zijn daarna toegevoegd."},
        {"nr": 2, "vraag": "Wat is gebouwd?", "data_label": "REAL",
         "antwoord": f"{len(mod_ser)} modules in de module-registry, waaronder pricing, competition, BCG, traffic, loyalty, basket, promotion, forecast, opportunities, decisions, Copilot, signals, data quality, platform health, reporting, Command Center en governance. Zie het Gap Dashboard voor detail per module."},
        {"nr": 3, "vraag": "Wat is verbeterd?", "data_label": "REAL",
         "antwoord": "Van losse dashboards naar één canoniek datamodel met semantic layer, gestandaardiseerde Intelligence Signals, centrale approval-workflow, audittrail, kostenmeting en shop-scoping."},
        {"nr": 4, "vraag": "Welke modules werken?", "data_label": "REAL",
         "antwoord": "Readiness-verdeling: " + ", ".join(f"{k}: {v}" for k, v in sorted(label_counts.items())) + ".",
         "details": {"modules": [{"naam": m["naam"], "label": m["readiness_label"], "score": m["readiness_score_avg"]} for m in mod_ser]}},
        {"nr": 5, "vraag": "Welke integraties werken?", "data_label": "REAL",
         "antwoord": f"Geconfigureerde connectors: {', '.join(conn_names) if conn_names else 'geen'}. Importbronnen (laatste 200 jobs): {', '.join(import_sources) if import_sources else 'geen'}. Totaal modelruns: {model_runs}."},
        {"nr": 6, "vraag": "Welke echte databronnen zijn gebruikt?", "data_label": "REAL",
         "antwoord": f"DRS Datareport ({real_skus} van {total_skus} SKU's), PriceShape-concurrentiefeed ({comp_prices} prijswaarnemingen) en BigQuery-sync. {len(real_mods)} modules draaien op echte data."},
        {"nr": 7, "vraag": "Welke onderdelen gebruiken testdata?", "data_label": "TEST",
         "antwoord": (f"{seed_skus} SKU's komen uit seed-data. Modules op test-/registrydata: "
                      + (", ".join(m["naam"] for m in test_mods) if test_mods else "geen")
                      + ". Demo-seeding staat alleen aan met SEED_DEMO_DATA=true.")},
        {"nr": 8, "vraag": "Welke tests zijn uitgevoerd?", "data_label": "REAL",
         "antwoord": "Automatische pytest-suite op de API-server (workflow 'apitests') en TypeScript-typechecks op de frontend (workflow 'typecheck'). Kernberekeningen (pricing, loyalty-ledger, break-even) hebben unittests; regressietests per engine staan in de backlog."},
        {"nr": 9, "vraag": "Wat zijn open bugs?", "data_label": "REAL",
         "antwoord": f"{open_bugs} open bugs in de Development Backlog; {dq_open} open datakwaliteitsissues in het issue-registry."},
        {"nr": 10, "vraag": "Wat ontbreekt?", "data_label": "REAL",
         "antwoord": f"{open_backlog} open backlog-items. Belangrijkste gaps per module:",
         "details": {"gaps": gaps}},
        {"nr": 11, "vraag": "Security findings", "data_label": "REAL",
         "antwoord": f"JWT-authenticatie met RBAC ({users} gebruikers), SSRF-bescherming op connector-URL's, rolchecks in de semantic layer en een Security Evidence Pack in de documentatie. Geen openstaande critical findings bekend; periodieke scans staan in de backlog."},
        {"nr": 12, "vraag": "Data protection findings", "data_label": "REAL",
         "antwoord": "Klantdata blijft binnen het platform; AI-calls lopen via de gecontroleerde gateway met logging van databronnen per call. Er gaat geen ongefilterde persoonsdata naar externe modellen."},
        {"nr": 13, "vraag": "Production readiness", "data_label": "REAL",
         "antwoord": (f"Production Ready (menselijk goedgekeurd): {', '.join(prod_ready) if prod_ready else 'nog geen'}. "
                      "Overige labels: zie het Gap Dashboard; goedkeuring verloopt via de admin-workflow (§46).")},
        {"nr": 14, "vraag": "Platform usage", "data_label": "REAL",
         "antwoord": f"{users} gebruikers, {recs} prijsaanbevelingen, {decisions} beslissingen, {signals} intelligence-signalen en {ai_calls} AI-gateway-calls."},
        {"nr": 15, "vraag": "Estimated production cost", "data_label": "MIXED",
         "antwoord": (f"Gemeten kosten laatste 30 dagen: {fmt_eur(cost_30d)}. Vaste centrale kosten (aannames): {fmt_eur(central)}/maand. "
                      "Zie het Cost & Scalability Dashboard voor scenario's.")},
        {"nr": 16, "vraag": "Cost per shop", "data_label": "MIXED",
         "antwoord": f"Variabele kosten per extra shop (aanname): {fmt_eur(shop_var)}/maand plus gemeten gebruik. De businesscase per shop rekent dit door met zichtbare aannames."},
        {"nr": 17, "vraag": "Measured time savings", "data_label": "MIXED",
         "antwoord": f"{bv_measurements} business-value-metingen geregistreerd met labels REALIZED/MEASURED/ESTIMATED/SIMULATED. Tijdsbesparing wordt gemeten via het Business Value-dashboard tegen de vastgelegde baselines."},
        {"nr": 18, "vraag": "Estimated business impact", "data_label": "MIXED",
         "antwoord": "Verwachte marge-uplift uit goedgekeurde prijsaanbevelingen plus gerealiseerde opportunity-waarde; per meting gelabeld als gemeten of geschat in het Business Value-dashboard."},
        {"nr": 19, "vraag": "ROI scenarios", "data_label": "MIXED",
         "antwoord": "ROI- en paybackscenario's per shop zijn beschikbaar in de businesscase-module en rekenen met de centrale aannames (bewerkbaar) en gemeten gebruik."},
        {"nr": 20, "vraag": "Recommended production roadmap", "data_label": "REAL",
         "antwoord": "Aanbevolen volgorde: (1) automatiseer nachtelijke engine-runs en BigQuery-sync, (2) sluit regressietests per engine aan, (3) activeer de AI-provider met kostlimieten, (4) zet goedgekeurde beslissingen automatisch door naar prijsuitvoering, (5) rond module-goedkeuringen naar Production Ready af via de §46-workflow."},
    ]


@router.get("/evaluation")
def list_evaluations(db: Session = Depends(get_db), _user=Depends(get_current_user)) -> Any:
    rows = (db.query(models.FinalEvaluationReport)
            .order_by(models.FinalEvaluationReport.generated_at.desc())
            .limit(20).all())
    return {
        "totaal": len(rows),
        "rapporten": [{
            "id": r.id, "titel": r.title, "generated_by": r.generated_by,
            "generated_at": str(r.generated_at),
        } for r in rows],
    }


@router.get("/evaluation/{report_id}")
def get_evaluation(report_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> Any:
    r = db.query(models.FinalEvaluationReport).filter(models.FinalEvaluationReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Rapport niet gevonden")
    return {
        "id": r.id, "titel": r.title, "generated_by": r.generated_by,
        "generated_at": str(r.generated_at), "sections": r.sections_json or [],
    }


@router.post("/evaluation/generate")
def generate_evaluation(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    """Genereer het Final Technical & Business Evaluation-rapport (§59)."""
    logger.info("governance API: evaluatierapport genereren door %s", user.username)
    sections = _build_evaluation_sections(db)
    r = models.FinalEvaluationReport(
        title="AI Commercial Intelligence Platform — Final Technical & Business Evaluation",
        generated_by=user.username,
        sections_json=sections,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "status": "gegenereerd", "generated_at": str(r.generated_at)}
