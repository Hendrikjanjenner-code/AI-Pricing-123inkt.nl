"""
Platform routes — /api/platform/...

- Platform Health Center (§41-§42): status per component + foutdrill-down
- Cost & Scalability Dashboard (§37-§38): werkelijk gebruik + scenario's
- Businesscase per shop (§39-§40): ROI/payback met zichtbare aannames
- Business value-meting (§39): baseline + metingen met waarderingslabels
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from datetime import date, datetime, timedelta, timezone

from database import get_db, engine
from auth import get_current_user, require_role
from models import (
    CostUsageRecord, PlatformAssumption, BusinessValueBaseline,
    BusinessValueMeasurement, ModelRun, ImportJob, ConnectorConfig, User,
)
from services import metering

router = APIRouter(prefix="/api/platform", tags=["platform"])

VALUE_LABELS = ("REALIZED", "MEASURED", "ESTIMATED", "SIMULATED")

# ------------------------------------------------------------------
# Standaard-aannames (§64.11). Eénmalig geseed; daarna bewerkbaar via API.
# ------------------------------------------------------------------
DEFAULT_ASSUMPTIONS = [
    # Kostentarieven (variabel, gemeten gebruik)
    ("rate_api_request_eur", "Kosten per API-request", 0.00002, "EUR/request", "cost",
     "Compute-aandeel per verwerkt API-request."),
    ("rate_ai_token_eur", "Kosten per AI-token", 0.000004, "EUR/token", "cost",
     "Gemiddelde tokenprijs (input+output) van het gebruikte AI-model."),
    ("rate_job_second_eur", "Kosten per seconde jobduur", 0.0002, "EUR/seconde", "cost",
     "Compute-kosten van achtergrondjobs (modelruns, syncs)."),
    ("rate_import_row_eur", "Kosten per geïmporteerde rij", 0.000005, "EUR/rij", "cost",
     "Verwerkingskosten per geïmporteerde datarij."),
    ("rate_db_gb_month_eur", "Databaseopslag per GB per maand", 0.35, "EUR/GB/maand", "cost",
     "Opslagkosten van de PostgreSQL-database."),
    # Centrale (vaste) platformkosten
    ("central_hosting_eur_month", "Hosting & infrastructuur (centraal)", 150.0, "EUR/maand", "cost",
     "Vaste hostingkosten van het platform, onafhankelijk van het aantal shops."),
    ("central_maintenance_eur_month", "Beheer & onderhoud (centraal)", 400.0, "EUR/maand", "cost",
     "Doorlopend technisch beheer, monitoring en updates."),
    # Variabele kosten per shop (naast gemeten gebruik)
    ("shop_variable_eur_month", "Variabele kosten per extra shop", 75.0, "EUR/maand", "cost",
     "Data-feeds, opslag en compute die per aangesloten shop bijkomen."),
    ("shop_setup_eur", "Eenmalige setupkosten per shop", 2500.0, "EUR", "cost",
     "Onboarding, datakoppelingen en configuratie per nieuwe shop."),
    # Waarde-aannames per shop
    ("analyst_hourly_rate_eur", "Uurtarief analist/pricing-manager", 65.0, "EUR/uur", "value",
     "Gebruikt om bespaarde uren in euro's uit te drukken."),
    ("hours_saved_per_week", "Bespaarde uren per week per shop", 8.0, "uur/week", "value",
     "Handmatig prijsonderzoek en rapportage die het platform overneemt."),
    ("margin_uplift_pct_expected", "Verwachte marge-uplift", 1.5, "%", "value",
     "Verwachte netto marge-verbetering door betere prijsbeslissingen."),
    ("shop_monthly_revenue_eur", "Gemiddelde maandomzet per shop", 250000.0, "EUR/maand", "value",
     "Basis voor het berekenen van omzet-/marge-impact per shop."),
    ("shop_gross_margin_pct", "Gemiddelde brutomarge per shop", 22.0, "%", "value",
     "Gebruikt om marge-impact in euro's te berekenen."),
    # Wisselkoers voor BigQuery-kosten (USD) in EUR-overzichten
    ("usd_eur_rate", "Wisselkoers USD → EUR", 0.92, "EUR/USD", "cost",
     "Gebruikt om BigQuery-querykosten (USD) mee te tellen in EUR-kostenscenario's."),
    # Schaal-aannames voor LOW/EXPECTED/HIGH gebruiksscenario's
    ("usage_low_factor", "Gebruiksfactor LOW-scenario", 0.5, "x", "scaling",
     "Vermenigvuldiger op gemeten variabel gebruik in het LOW-scenario."),
    ("usage_high_factor", "Gebruiksfactor HIGH-scenario", 2.5, "x", "scaling",
     "Vermenigvuldiger op gemeten variabel gebruik in het HIGH-scenario."),
]

BUSINESS_CASE_SCENARIOS = {
    "Conservative": {"value_factor": 0.5, "uitleg": "50% van de verwachte waarde wordt gerealiseerd."},
    "Expected": {"value_factor": 1.0, "uitleg": "De verwachte waarde wordt volledig gerealiseerd."},
    "Ambitious": {"value_factor": 1.5, "uitleg": "150% van de verwachte waarde (volledige adoptie + extra use-cases)."},
}


def _ensure_assumptions(db: Session) -> dict:
    """Seed ontbrekende default-aannames en retourneer key->row dict."""
    bestaand = {a.key: a for a in db.query(PlatformAssumption).all()}
    nieuw = False
    for key, label, value, unit, category, desc_ in DEFAULT_ASSUMPTIONS:
        if key not in bestaand:
            row = PlatformAssumption(
                key=key, label=label, value=value, unit=unit,
                category=category, description=desc_, source="aanname",
            )
            db.add(row)
            bestaand[key] = row
            nieuw = True
    if nieuw:
        db.commit()
    return bestaand


def _assumption_values(db: Session) -> dict:
    return {k: float(v.value) for k, v in _ensure_assumptions(db).items()}


def _assumptions_public(rows: dict, keys: list[str]) -> list[dict]:
    out = []
    for k in keys:
        r = rows.get(k)
        if r:
            out.append({
                "key": r.key, "label": r.label, "value": float(r.value),
                "unit": r.unit, "source": r.source, "description": r.description,
            })
    return out


# ==================================================================
# Platform Health Center
# ==================================================================
@router.get("/health")
def platform_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager")),
):
    """Status van applicatie, database, AI, API's, jobs, integraties en imports."""
    from main import startup_state
    nu = datetime.utcnow()

    # Database
    try:
        t0 = datetime.utcnow()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ms = (datetime.utcnow() - t0).total_seconds() * 1000
        database = {"status": "ok", "response_ms": round(db_ms, 1)}
    except Exception as exc:
        database = {"status": "error", "message": str(exc)}

    # API-metrics (rolling laatste uur)
    api = metering.api_metrics_snapshot()
    api_status = "ok"
    if api["totaal"]["error_rate_pct"] > 10:
        api_status = "error"
    elif api["totaal"]["error_rate_pct"] > 2 or api["totaal"]["p95_response_ms"] > 3000:
        api_status = "degraded"

    # Jobs: modelruns
    laatste_run = db.query(ModelRun).order_by(desc(ModelRun.started_at)).first()
    failed_runs = db.query(ModelRun).filter(
        ModelRun.status == "failed",
        ModelRun.started_at >= nu - timedelta(days=7),
    ).count()
    jobs = {
        "status": "error" if (laatste_run and laatste_run.status == "failed") else ("ok" if laatste_run else "not_run"),
        "laatste_run": laatste_run.started_at.isoformat() if laatste_run else None,
        "laatste_status": laatste_run.status if laatste_run else None,
        "failed_last_7d": failed_runs,
    }

    # Imports
    laatste_import = db.query(ImportJob).order_by(desc(ImportJob.created_at)).first()
    failed_imports = db.query(ImportJob).filter(
        ImportJob.status.in_(["fout", "failed"]),
        ImportJob.created_at >= nu - timedelta(days=7),
    ).count()
    imports = {
        "status": "error" if failed_imports > 0 else ("ok" if laatste_import else "none"),
        "laatste_import": laatste_import.created_at.isoformat() if laatste_import else None,
        "laatste_status": laatste_import.status if laatste_import else None,
        "failed_last_7d": failed_imports,
    }

    # Integraties/connectoren
    connectoren = db.query(ConnectorConfig).all()
    conn_items = [{
        "connector": c.connector_name,
        "last_test_status": c.last_test_status,
        "last_synced_at": c.last_synced_at.isoformat() if c.last_synced_at else None,
    } for c in connectoren]
    conn_fout = [c for c in connectoren if c.last_test_status and c.last_test_status != "ok"]
    integraties = {
        "status": "error" if conn_fout else ("ok" if connectoren else "none"),
        "connectoren": conn_items,
    }

    # AI: gemeten AI-calls (24 uur) + provider-bereikbaarheid (gecachet probe)
    ai_q = db.query(CostUsageRecord).filter(
        CostUsageRecord.usage_type == "ai_call",
        CostUsageRecord.occurred_at >= nu - timedelta(hours=24),
    )
    ai_totaal = ai_q.count()
    ai_fouten = ai_q.filter(CostUsageRecord.status_code >= 400).count() if ai_totaal else 0

    # Provider-probe: gebruik gecachet resultaat (geen extra externe call per paginaload)
    from ai_gateway import get_provider_reachable
    ai_reachable, ai_probe_error = get_provider_reachable()

    # Status: "error" als provider onbereikbaar is of foutpercentage hoog;
    # "degraded" als probe nog niet is gelopen (None).
    if ai_reachable is False:
        ai_status = "error"
    elif ai_reachable is None:
        ai_status = "degraded"
    elif ai_totaal and ai_fouten / ai_totaal > 0.2:
        ai_status = "error"
    elif ai_totaal:
        ai_status = "ok"
    else:
        ai_status = "not_used"

    ai = {
        "status": ai_status,
        "calls_last_24h": ai_totaal,
        "failed_last_24h": ai_fouten,
        "provider_reachable": ai_reachable,
        "provider_error": ai_probe_error,
    }

    # Applicatie
    applicatie = {
        "status": "ok" if startup_state["backend_status"] == "running" else startup_state["backend_status"],
        "started_at": startup_state["started_at"],
        "last_start_error": (startup_state["last_start_error"] or {}).get("message")
        if startup_state["last_start_error"] else None,
    }

    componenten = {
        "applicatie": applicatie,
        "database": database,
        "api": {"status": api_status, **api["totaal"]},
        "ai": ai,
        "jobs": jobs,
        "imports": imports,
        "integraties": integraties,
    }
    statussen = [c.get("status") for c in componenten.values()]
    overall = "ok"
    if "error" in statussen:
        overall = "error"
    elif "degraded" in statussen:
        overall = "degraded"

    return {
        "overall_status": overall,
        "componenten": componenten,
        "api_per_module": api["per_module"],
        "recente_fouten": metering.recent_errors(20),
        "generated_at": nu.isoformat(),
    }


@router.get("/health/errors")
def platform_health_errors(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager")),
):
    """Foutdrill-down: recente API-fouten + gefaalde jobs en imports."""
    nu = datetime.utcnow()
    failed_runs = db.query(ModelRun).filter(
        ModelRun.status == "failed",
        ModelRun.started_at >= nu - timedelta(days=14),
    ).order_by(desc(ModelRun.started_at)).limit(20).all()
    failed_imports = db.query(ImportJob).filter(
        ImportJob.status.in_(["fout", "failed"]),
        ImportJob.created_at >= nu - timedelta(days=14),
    ).order_by(desc(ImportJob.created_at)).limit(20).all()
    return {
        "api_fouten": metering.recent_errors(limit),
        "gefaalde_modelruns": [{
            "id": r.id, "started_at": r.started_at.isoformat() if r.started_at else None,
            "error_message": r.error_message,
        } for r in failed_runs],
        "gefaalde_imports": [{
            "id": j.id, "upload_type": j.upload_type, "filename": j.filename,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "error_message": j.error_message,
        } for j in failed_imports],
    }


# ==================================================================
# Usage & Cost Dashboard
# ==================================================================
@router.get("/usage")
def platform_usage(
    dagen: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager")),
):
    """Werkelijk gemeten gebruik en kosten per type/module/shop (§37-§38)."""
    metering.flush_usage_buffer()
    vanaf = datetime.utcnow() - timedelta(days=dagen)
    basis = db.query(CostUsageRecord).filter(CostUsageRecord.occurred_at >= vanaf)

    def agg(*group_cols):
        q = db.query(
            *group_cols,
            func.count(CostUsageRecord.id).label("aantal"),
            func.coalesce(func.sum(CostUsageRecord.cost_eur), 0).label("kosten"),
            func.coalesce(func.sum(CostUsageRecord.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(CostUsageRecord.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(CostUsageRecord.duration_ms), 0).label("duur_ms"),
        ).filter(CostUsageRecord.occurred_at >= vanaf).group_by(*group_cols)
        return q.all()

    per_type = [{
        "usage_type": r[0], "aantal": r.aantal, "kosten_eur": round(float(r.kosten), 4),
        "tokens_in": int(r.tokens_in), "tokens_out": int(r.tokens_out),
        "duur_seconden": round(float(r.duur_ms) / 1000, 1),
    } for r in agg(CostUsageRecord.usage_type)]

    per_module = [{
        "module": r[0] or "onbekend", "aantal": r.aantal,
        "kosten_eur": round(float(r.kosten), 4),
    } for r in agg(CostUsageRecord.module)]

    per_shop = [{
        "shop_id": r[0], "aantal": r.aantal, "kosten_eur": round(float(r.kosten), 4),
    } for r in agg(CostUsageRecord.shop_id)]

    per_gebruiker = [{
        "username": r[0] or "systeem", "aantal": r.aantal,
        "kosten_eur": round(float(r.kosten), 4),
    } for r in agg(CostUsageRecord.username)]

    # Dagelijkse kostentrend
    dag_col = func.date_trunc("day", CostUsageRecord.occurred_at)
    trend = db.query(
        dag_col.label("dag"),
        func.coalesce(func.sum(CostUsageRecord.cost_eur), 0).label("kosten"),
        func.count(CostUsageRecord.id).label("aantal"),
    ).filter(CostUsageRecord.occurred_at >= vanaf).group_by(dag_col).order_by(dag_col).all()

    # Databasegrootte (werkelijk gemeten)
    db_gb = None
    try:
        with engine.connect() as conn:
            size_bytes = conn.execute(text("SELECT pg_database_size(current_database())")).scalar()
        db_gb = round(size_bytes / (1024 ** 3), 3)
    except Exception:
        pass
    rates = _assumption_values(db)
    db_cost_month = round((db_gb or 0) * rates["rate_db_gb_month_eur"], 4)

    # Afgeleide gebruiksstatistieken uit bestaande job/import-tabellen
    runs = db.query(ModelRun).filter(ModelRun.started_at >= vanaf).count()
    import_rows = db.query(func.coalesce(func.sum(ImportJob.rows_processed), 0)).filter(
        ImportJob.created_at >= vanaf).scalar()

    totaal_kosten = float(basis.with_entities(
        func.coalesce(func.sum(CostUsageRecord.cost_eur), 0)).scalar())

    return {
        "periode_dagen": dagen,
        "totaal": {
            "records": basis.count(),
            "kosten_eur": round(totaal_kosten, 4),
            "modelruns": runs,
            "import_rijen": int(import_rows or 0),
            "database_gb": db_gb,
            "database_kosten_eur_maand": db_cost_month,
        },
        "per_type": per_type,
        "per_module": sorted(per_module, key=lambda x: -x["kosten_eur"])[:25],
        "per_shop": per_shop,
        "per_gebruiker": sorted(per_gebruiker, key=lambda x: -x["aantal"])[:25],
        "kosten_trend": [{
            "datum": r.dag.date().isoformat(), "kosten_eur": round(float(r.kosten), 4),
            "aantal": r.aantal,
        } for r in trend],
    }


@router.get("/costs/scenarios")
def cost_scenarios(
    dagen: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager")),
):
    """
    Cost & Scalability: centrale vs. variabele kosten per shop,
    scenario's voor 1/5/10 shops × LOW/EXPECTED/HIGH gebruik.
    """
    metering.flush_usage_buffer()
    aannames = _ensure_assumptions(db)
    v = {k: float(r.value) for k, r in aannames.items()}

    # Gemeten variabele kosten per maand (geëxtrapoleerd uit de periode)
    vanaf = datetime.utcnow() - timedelta(days=dagen)
    gemeten = float(db.query(func.coalesce(func.sum(CostUsageRecord.cost_eur), 0))
                    .filter(CostUsageRecord.occurred_at >= vanaf).scalar())
    gemeten_per_maand = gemeten / dagen * 30.44

    db_gb = 0.0
    try:
        with engine.connect() as conn:
            db_gb = (conn.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0) / (1024 ** 3)
    except Exception:
        pass
    db_kosten_maand = db_gb * v["rate_db_gb_month_eur"]

    # BigQuery-querykosten (USD, gemeten) — nul/nvt als BQ niet geconfigureerd is
    bq_cost_usd = 0.0
    bq_tb = 0.0
    bq_queries = 0
    try:
        from bigquery.cost_tracker import get_cost_summary
        bq = get_cost_summary(db, days=dagen)
        bq_cost_usd = float(bq.get("total_cost_usd") or 0)
        bq_tb = float(bq.get("total_tb") or 0)
        bq_queries = sum(int(r.get("query_count") or 0) for r in bq.get("by_module", []))
    except Exception:
        pass
    usd_eur = v.get("usd_eur_rate", 0.92)
    bq_kosten_eur_maand = (bq_cost_usd * usd_eur) / dagen * 30.44

    centraal_maand = v["central_hosting_eur_month"] + v["central_maintenance_eur_month"]
    # Variabel per shop = gemeten gebruik (1 shop nu) + BigQuery-scankosten
    # + vaste variabele opslag per shop
    variabel_per_shop_expected = (
        gemeten_per_maand + bq_kosten_eur_maand + db_kosten_maand + v["shop_variable_eur_month"]
    )

    factoren = {"LOW": v["usage_low_factor"], "EXPECTED": 1.0, "HIGH": v["usage_high_factor"]}
    scenarios = []
    for shops in (1, 5, 10):
        for niveau, factor in factoren.items():
            variabel = variabel_per_shop_expected * factor * shops
            totaal = centraal_maand + variabel
            scenarios.append({
                "shops": shops,
                "gebruiksniveau": niveau,
                "centrale_kosten_eur_maand": round(centraal_maand, 2),
                "variabele_kosten_eur_maand": round(variabel, 2),
                "totale_kosten_eur_maand": round(totaal, 2),
                "kosten_per_shop_eur_maand": round(totaal / shops, 2),
            })

    return {
        "gemeten_basis": {
            "periode_dagen": dagen,
            "gemeten_variabele_kosten_eur": round(gemeten, 4),
            "geextrapoleerd_eur_maand": round(gemeten_per_maand, 2),
            "database_gb": round(db_gb, 3),
            "database_kosten_eur_maand": round(db_kosten_maand, 2),
            "bigquery_kosten_usd": round(bq_cost_usd, 4),
            "bigquery_tb_gescand": round(bq_tb, 6),
            "bigquery_queries": bq_queries,
            "bigquery_kosten_eur_maand": round(bq_kosten_eur_maand, 2),
        },
        "centrale_kosten_eur_maand": round(centraal_maand, 2),
        "variabele_kosten_per_shop_eur_maand_expected": round(variabel_per_shop_expected, 2),
        "scenarios": scenarios,
        "aannames": _assumptions_public(aannames, [
            "central_hosting_eur_month", "central_maintenance_eur_month",
            "shop_variable_eur_month", "rate_db_gb_month_eur",
            "usd_eur_rate", "usage_low_factor", "usage_high_factor",
        ]),
    }


# ==================================================================
# Businesscase per shop
# ==================================================================
@router.get("/business-case")
def business_case(
    shops: int = Query(1, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager")),
):
    """
    Businesscase per shop: setup/maand/jaar-kosten, verwachte besparingen,
    marge-/omzetimpact, ROI en payback — in Conservative/Expected/Ambitious.
    Alle gebruikte aannames worden expliciet meegegeven (§64.11).
    """
    aannames = _ensure_assumptions(db)
    v = {k: float(r.value) for k, r in aannames.items()}

    centraal_maand = v["central_hosting_eur_month"] + v["central_maintenance_eur_month"]
    variabel_shop_maand = v["shop_variable_eur_month"]
    setup_per_shop = v["shop_setup_eur"]

    kosten_maand_totaal = centraal_maand + variabel_shop_maand * shops
    kosten_maand_per_shop = kosten_maand_totaal / shops
    kosten_jaar_per_shop = kosten_maand_per_shop * 12

    # Verwachte waarde per shop per maand (Expected)
    uren_besparing_maand = v["hours_saved_per_week"] * 4.33
    besparing_eur_maand = uren_besparing_maand * v["analyst_hourly_rate_eur"]
    marge_basis = v["shop_monthly_revenue_eur"] * v["shop_gross_margin_pct"] / 100
    marge_impact_maand = marge_basis * v["margin_uplift_pct_expected"] / 100
    omzet_impact_maand = v["shop_monthly_revenue_eur"] * v["margin_uplift_pct_expected"] / 100

    scenario_resultaten = []
    for naam, cfg in BUSINESS_CASE_SCENARIOS.items():
        f = cfg["value_factor"]
        waarde_maand = (besparing_eur_maand + marge_impact_maand) * f
        netto_maand = waarde_maand - kosten_maand_per_shop
        jaar_waarde = waarde_maand * 12
        jaar_kosten = kosten_jaar_per_shop + setup_per_shop
        roi_pct = ((jaar_waarde - jaar_kosten) / jaar_kosten * 100) if jaar_kosten else None
        payback_maanden = (setup_per_shop / netto_maand) if netto_maand > 0 else None
        scenario_resultaten.append({
            "scenario": naam,
            "uitleg": cfg["uitleg"],
            "waarde_eur_maand": round(waarde_maand, 2),
            "waarvan_tijdsbesparing_eur_maand": round(besparing_eur_maand * f, 2),
            "waarvan_marge_impact_eur_maand": round(marge_impact_maand * f, 2),
            "omzet_impact_eur_maand": round(omzet_impact_maand * f, 2),
            "netto_waarde_eur_maand": round(netto_maand, 2),
            "roi_jaar1_pct": round(roi_pct, 1) if roi_pct is not None else None,
            "payback_maanden": round(payback_maanden, 1) if payback_maanden else None,
        })

    return {
        "shops": shops,
        "kosten": {
            "setup_eur_per_shop": round(setup_per_shop, 2),
            "maandkosten_eur_per_shop": round(kosten_maand_per_shop, 2),
            "jaarkosten_eur_per_shop": round(kosten_jaar_per_shop, 2),
            "centrale_kosten_eur_maand": round(centraal_maand, 2),
            "variabele_kosten_eur_maand_per_shop": round(variabel_shop_maand, 2),
        },
        "scenarios": scenario_resultaten,
        "waarde_label": "ESTIMATED",
        "aannames": _assumptions_public(aannames, [
            "shop_setup_eur", "shop_variable_eur_month",
            "central_hosting_eur_month", "central_maintenance_eur_month",
            "analyst_hourly_rate_eur", "hours_saved_per_week",
            "margin_uplift_pct_expected", "shop_monthly_revenue_eur",
            "shop_gross_margin_pct",
        ]),
    }


# ==================================================================
# Aannames (zichtbaar en bewerkbaar)
# ==================================================================
@router.get("/assumptions")
def list_assumptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager")),
):
    rows = _ensure_assumptions(db)
    return [{
        "key": r.key, "label": r.label, "value": float(r.value), "unit": r.unit,
        "category": r.category, "description": r.description, "source": r.source,
        "updated_by": r.updated_by,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in sorted(rows.values(), key=lambda x: (x.category or "", x.key))]


@router.put("/assumptions/{key}")
def update_assumption(
    key: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager")),
):
    row = db.query(PlatformAssumption).filter(PlatformAssumption.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Aanname niet gevonden")
    if "value" in payload:
        try:
            row.value = float(payload["value"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="value moet een getal zijn")
    if "source" in payload:
        row.source = str(payload["source"])[:255]
    if "description" in payload:
        row.description = payload["description"]
    row.updated_by = current_user.username
    db.commit()
    # Zorg dat nieuwe metering-records direct de bijgewerkte tarieven gebruiken
    metering.invalidate_rates_cache()
    return {"status": "bijgewerkt", "key": key, "value": float(row.value)}


# ==================================================================
# Business value-meting: baselines + metingen + samenvatting
# ==================================================================
@router.get("/business-value/baselines")
def list_baselines(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    rows = db.query(BusinessValueBaseline).order_by(BusinessValueBaseline.metric_key).all()
    return [{
        "id": r.id, "metric_key": r.metric_key, "label": r.label,
        "baseline_value": r.baseline_value, "unit": r.unit,
        "shop_id": r.shop_id, "description": r.description,
        "measured_at": str(r.measured_at) if r.measured_at else None,
        "created_by": r.created_by,
    } for r in rows]


@router.post("/business-value/baselines")
def create_baseline(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    for veld in ("metric_key", "label", "baseline_value"):
        if payload.get(veld) in (None, ""):
            raise HTTPException(status_code=400, detail=f"'{veld}' is verplicht")
    row = BusinessValueBaseline(
        metric_key=str(payload["metric_key"])[:100],
        label=str(payload["label"])[:255],
        baseline_value=float(payload["baseline_value"]),
        unit=(payload.get("unit") or "")[:50] or None,
        shop_id=int(payload.get("shop_id") or 1),
        description=payload.get("description"),
        measured_at=date.fromisoformat(payload["measured_at"]) if payload.get("measured_at") else date.today(),
        created_by=current_user.username,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "aangemaakt", "id": row.id}


@router.get("/business-value/measurements")
def list_measurements(
    value_label: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    q = db.query(BusinessValueMeasurement)
    if value_label:
        q = q.filter(BusinessValueMeasurement.value_label == value_label.upper())
    rows = q.order_by(desc(BusinessValueMeasurement.created_at)).limit(200).all()
    return [{
        "id": r.id, "metric_key": r.metric_key, "label": r.label,
        "value": r.value, "unit": r.unit, "value_label": r.value_label,
        "shop_id": r.shop_id,
        "period_start": str(r.period_start) if r.period_start else None,
        "period_end": str(r.period_end) if r.period_end else None,
        "explanation": r.explanation, "assumptions": r.assumptions,
        "source": r.source, "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.post("/business-value/measurements")
def create_measurement(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    for veld in ("metric_key", "label", "value", "value_label"):
        if payload.get(veld) in (None, ""):
            raise HTTPException(status_code=400, detail=f"'{veld}' is verplicht")
    label = str(payload["value_label"]).upper()
    if label not in VALUE_LABELS:
        raise HTTPException(status_code=400, detail=f"value_label moet één van {VALUE_LABELS} zijn")
    if label in ("ESTIMATED", "SIMULATED") and not (payload.get("explanation") or payload.get("assumptions")):
        raise HTTPException(status_code=400,
                            detail="ESTIMATED/SIMULATED vereist een toelichting of aannames (§64.11)")
    row = BusinessValueMeasurement(
        metric_key=str(payload["metric_key"])[:100],
        label=str(payload["label"])[:255],
        value=float(payload["value"]),
        unit=(payload.get("unit") or "")[:50] or None,
        value_label=label,
        shop_id=int(payload.get("shop_id") or 1),
        period_start=date.fromisoformat(payload["period_start"]) if payload.get("period_start") else None,
        period_end=date.fromisoformat(payload["period_end"]) if payload.get("period_end") else None,
        explanation=payload.get("explanation"),
        assumptions=payload.get("assumptions"),
        source=payload.get("source") or "handmatig",
        created_by=current_user.username,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "aangemaakt", "id": row.id}


@router.get("/business-value/summary")
def business_value_summary(
    dagen: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    """
    Samenvatting: baseline vs. gemeten platformgebruik. Automatisch afgeleide
    metingen krijgen MEASURED (tellingen) of ESTIMATED (euro-vertaling).
    """
    from models import FactPricingRecommendationDaily, IntelligenceSignal
    aannames = _ensure_assumptions(db)
    v = {k: float(r.value) for k, r in aannames.items()}
    vanaf = datetime.utcnow() - timedelta(days=dagen)
    vanaf_d = date.today() - timedelta(days=dagen)

    modelruns = db.query(ModelRun).filter(
        ModelRun.started_at >= vanaf, ModelRun.status == "completed").count()
    adviezen = db.query(FactPricingRecommendationDaily).filter(
        FactPricingRecommendationDaily.date >= vanaf_d).count()
    goedgekeurd = db.query(FactPricingRecommendationDaily).filter(
        FactPricingRecommendationDaily.date >= vanaf_d,
        FactPricingRecommendationDaily.approval_status == "approved").count()
    verwerkt = db.query(FactPricingRecommendationDaily).filter(
        FactPricingRecommendationDaily.date >= vanaf_d,
        FactPricingRecommendationDaily.processing_status == "verwerkt").count()
    signalen = db.query(IntelligenceSignal).filter(
        IntelligenceSignal.created_at >= vanaf).count() if _tabel_bestaat(db, "intelligence_signals") else 0
    imports = db.query(ImportJob).filter(ImportJob.created_at >= vanaf).count()

    # Verwachte marge-uplift van verwerkte adviezen. LET OP: "verwerkt" bewijst
    # alleen dat de prijswijziging is doorgevoerd, niet dat de verwachte marge
    # daadwerkelijk is gerealiseerd — daarom ESTIMATED, geen REALIZED (§64.11).
    verwachte_uplift = float(db.query(
        func.coalesce(func.sum(FactPricingRecommendationDaily.expected_margin_uplift), 0)
    ).filter(
        FactPricingRecommendationDaily.date >= vanaf_d,
        FactPricingRecommendationDaily.processing_status == "verwerkt",
    ).scalar())

    # Geschatte tijdsbesparing in euro's (ESTIMATED — op basis van aannames)
    weken = dagen / 7
    geschatte_uren = v["hours_saved_per_week"] * weken
    geschatte_besparing = geschatte_uren * v["analyst_hourly_rate_eur"]

    automatisch = [
        {"metric_key": "analyses_uitgevoerd", "label": "Uitgevoerde analyses (modelruns)",
         "value": modelruns, "unit": "runs", "value_label": "MEASURED",
         "explanation": "Aantal succesvol afgeronde modelruns, direct gemeten."},
        {"metric_key": "prijsadviezen", "label": "Gegenereerde prijsadviezen",
         "value": adviezen, "unit": "adviezen", "value_label": "MEASURED",
         "explanation": "Aantal gegenereerde prijsadviezen in de periode."},
        {"metric_key": "adviezen_goedgekeurd", "label": "Goedgekeurde prijsadviezen",
         "value": goedgekeurd, "unit": "adviezen", "value_label": "MEASURED",
         "explanation": "Door gebruikers goedgekeurde adviezen."},
        {"metric_key": "adviezen_verwerkt", "label": "Doorgevoerde prijswijzigingen",
         "value": verwerkt, "unit": "adviezen", "value_label": "REALIZED",
         "explanation": "Adviezen die daadwerkelijk zijn geëxporteerd/doorgevoerd."},
        {"metric_key": "intelligence_signalen", "label": "Gepubliceerde intelligence-signalen",
         "value": signalen, "unit": "signalen", "value_label": "MEASURED",
         "explanation": "Aantal gepubliceerde Commercial Intelligence Signals."},
        {"metric_key": "imports", "label": "Uitgevoerde data-imports",
         "value": imports, "unit": "imports", "value_label": "MEASURED",
         "explanation": "Aantal uitgevoerde data-imports in de periode."},
        {"metric_key": "marge_uplift_verwerkt", "label": "Verwachte marge-uplift van doorgevoerde adviezen",
         "value": round(verwachte_uplift, 2), "unit": "EUR", "value_label": "ESTIMATED",
         "explanation": "Som van de vooraf verwachte marge-uplift van doorgevoerde prijswijzigingen. "
                        "ESTIMATED: de wijzigingen zijn doorgevoerd (REALIZED-telling hierboven), maar de "
                        "werkelijke marge-realisatie is nog niet financieel gemeten.",
         "assumptions": {"basis": "expected_margin_uplift per doorgevoerd advies (modeloutput)"}},
        {"metric_key": "tijdsbesparing_eur", "label": "Geschatte tijdsbesparing",
         "value": round(geschatte_besparing, 2), "unit": "EUR", "value_label": "ESTIMATED",
         "explanation": f"Aanname: {v['hours_saved_per_week']} uur/week × €{v['analyst_hourly_rate_eur']}/uur over {dagen} dagen.",
         "assumptions": {"hours_saved_per_week": v["hours_saved_per_week"],
                         "analyst_hourly_rate_eur": v["analyst_hourly_rate_eur"]}},
    ]

    baselines = list_baselines(db=db, current_user=current_user)
    handmatig = list_measurements(value_label=None, db=db, current_user=current_user)

    return {
        "periode_dagen": dagen,
        "waarde_labels": list(VALUE_LABELS),
        "automatische_metingen": automatisch,
        "baselines": baselines,
        "handmatige_metingen": handmatig[:50],
        "aannames": _assumptions_public(aannames, [
            "hours_saved_per_week", "analyst_hourly_rate_eur",
        ]),
    }


def _tabel_bestaat(db: Session, naam: str) -> bool:
    try:
        db.execute(text(f"SELECT 1 FROM {naam} LIMIT 1"))
        return True
    except Exception:
        db.rollback()
        return False
