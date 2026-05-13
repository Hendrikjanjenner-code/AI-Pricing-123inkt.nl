"""
BCG Intelligence Engine — API routes.

Endpoints:
  GET  /api/bcg/dashboard       — overzicht KPI's en classificatietellingen
  GET  /api/bcg/sku-matrix      — SKU-matrix data (scatter plot)
  GET  /api/bcg/sku/{sku_id}    — detail voor één SKU
  GET  /api/bcg/categorie-matrix — categorie-level BCG
  GET  /api/bcg/hybrid-matrix   — hybrid pricing matrix
  GET  /api/bcg/huismerk        — private label intelligence
  GET  /api/bcg/pricing-power   — pricing power ranglijst
  POST /api/bcg/run             — start BCG engine run
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import auth as auth_utils
import models
from engine.bcg_engine import run_bcg_engine

router = APIRouter(prefix="/api/bcg", tags=["bcg"])

# ─── Hulpfuncties ─────────────────────────────────────────────────────────────

INTERNAL_NL = {
    "INTERNAL_STAR": "Interne Ster",
    "INTERNAL_CASH_COW": "Interne Cash Cow",
    "INTERNAL_QUESTION_MARK": "Intern Vraagteken",
    "INTERNAL_DOG": "Interne Dog",
}
EXTERNAL_NL = {
    "EXTERNAL_STAR": "Externe Ster",
    "EXTERNAL_CASH_COW": "Externe Cash Cow",
    "EXTERNAL_QUESTION_MARK": "Extern Vraagteken",
    "EXTERNAL_DOG": "Externe Dog",
}
HYBRID_NL = {
    "PRICING_POWER_STAR": "Pricing Power Ster",
    "DEFENSIVE_CASH_COW": "Defensieve Cash Cow",
    "PRIVATE_LABEL_STAR": "Huismerk Ster",
    "EXPERIMENTAL_QUESTION_MARK": "Experimenteel Vraagteken",
    "LOW_PRIORITY_DOG": "Lage Prioriteit Dog",
}
STRATEGY_NL = {
    "PROTECT_MARGIN": "Bescherm Marge",
    "DEFEND_MARKET_POSITION": "Verdedig Marktpositie",
    "PRIVATE_LABEL_PUSH": "Huismerk Promoten",
    "EXPERIMENT_PRICE_INCREASE": "Prijsverhoging Testen",
    "COMPETITIVE_PRICE_MATCH": "Concurrentieprijs Volgen",
    "LOW_PRIORITY_AUTOMATION": "Automatiseer (Laag Prioriteit)",
}
PL_NL = {
    "PRIVATE_LABEL_STAR": "Huismerk Ster",
    "PRIVATE_LABEL_GROWTH": "Huismerk Groei",
    "PRIVATE_LABEL_DEFENSIVE": "Huismerk Defensief",
    "PRIVATE_LABEL_LOW_PRIORITY": "Huismerk Laag Prioriteit",
}
BCG_KLEUR = {
    "PRICING_POWER_STAR": "#22c55e",
    "DEFENSIVE_CASH_COW": "#f59e0b",
    "PRIVATE_LABEL_STAR": "#8b5cf6",
    "EXPERIMENTAL_QUESTION_MARK": "#3b82f6",
    "LOW_PRIORITY_DOG": "#94a3b8",
    "INTERNAL_STAR": "#22c55e",
    "INTERNAL_CASH_COW": "#f59e0b",
    "INTERNAL_QUESTION_MARK": "#3b82f6",
    "INTERNAL_DOG": "#94a3b8",
    "EXTERNAL_STAR": "#10b981",
    "EXTERNAL_CASH_COW": "#f97316",
    "EXTERNAL_QUESTION_MARK": "#6366f1",
    "EXTERNAL_DOG": "#64748b",
}

def _latest_sku_records(db: Session) -> list[models.FactBcgClassificationDaily]:
    today = date.today()
    rows = db.query(models.FactBcgClassificationDaily).filter(
        models.FactBcgClassificationDaily.entity_type == "SKU",
        models.FactBcgClassificationDaily.date == today,
    ).all()
    if not rows:
        # fallback: neem meest recente datum
        latest = db.query(models.FactBcgClassificationDaily.date).filter(
            models.FactBcgClassificationDaily.entity_type == "SKU"
        ).order_by(models.FactBcgClassificationDaily.date.desc()).first()
        if latest:
            rows = db.query(models.FactBcgClassificationDaily).filter(
                models.FactBcgClassificationDaily.entity_type == "SKU",
                models.FactBcgClassificationDaily.date == latest[0],
            ).all()
    return rows

def _latest_cat_records(db: Session) -> list[models.FactBcgClassificationDaily]:
    today = date.today()
    rows = db.query(models.FactBcgClassificationDaily).filter(
        models.FactBcgClassificationDaily.entity_type == "CATEGORY",
        models.FactBcgClassificationDaily.date == today,
    ).all()
    if not rows:
        latest = db.query(models.FactBcgClassificationDaily.date).filter(
            models.FactBcgClassificationDaily.entity_type == "CATEGORY"
        ).order_by(models.FactBcgClassificationDaily.date.desc()).first()
        if latest:
            rows = db.query(models.FactBcgClassificationDaily).filter(
                models.FactBcgClassificationDaily.entity_type == "CATEGORY",
                models.FactBcgClassificationDaily.date == latest[0],
            ).all()
    return rows


# ─── GET /api/bcg/dashboard ───────────────────────────────────────────────────

@router.get("/dashboard")
def get_bcg_dashboard(db: Session = Depends(get_db), _=Depends(auth_utils.get_current_user)):
    sku_rows = _latest_sku_records(db)

    if not sku_rows:
        return {
            "total_skus": 0,
            "run_date": str(date.today()),
            "internal_counts": {},
            "external_counts": {},
            "hybrid_counts": {},
            "top_pricing_power": [],
            "top_private_label_stars": [],
            "hoog_concurrentiedruk_categories": [],
            "alerts": [],
        }

    # Tellingen
    internal_counts: dict[str, int] = {}
    external_counts: dict[str, int] = {}
    hybrid_counts: dict[str, int] = {}
    for r in sku_rows:
        internal_counts[r.internal_bcg_class or ""] = internal_counts.get(r.internal_bcg_class or "", 0) + 1
        external_counts[r.external_bcg_class or ""] = external_counts.get(r.external_bcg_class or "", 0) + 1
        hybrid_counts[r.hybrid_bcg_class or ""] = hybrid_counts.get(r.hybrid_bcg_class or "", 0) + 1

    # Top pricing power
    top_pps = sorted([r for r in sku_rows if r.pricing_power_score], key=lambda x: x.pricing_power_score, reverse=True)[:6]

    # Top private label stars
    pl_rows = db.query(models.FactPrivateLabelIntelligence).order_by(
        models.FactPrivateLabelIntelligence.private_label_value_score.desc()
    ).limit(6).all()

    # Hoge concurrentiedruk categorieën
    cat_rows = _latest_cat_records(db)
    hoog_druk = sorted(
        [r for r in cat_rows if (r.css_external_score or 1.0) < 0.50],
        key=lambda x: x.css_external_score or 1.0
    )[:5]

    # Alerts
    alerts = []
    for r in sku_rows:
        if r.hybrid_bcg_class == "LOW_PRIORITY_DOG":
            alerts.append({"type": "SKU_MOVED_TO_DOG", "sku_id": r.entity_id, "naam": r.entity_name, "kleur": "#ef4444"})
        elif r.hybrid_bcg_class == "PRICING_POWER_STAR" and (r.pricing_power_score or 0) >= 0.75:
            alerts.append({"type": "PRICING_POWER_INCREASED", "sku_id": r.entity_id, "naam": r.entity_name, "kleur": "#22c55e"})
        elif r.hybrid_bcg_class == "PRIVATE_LABEL_STAR":
            alerts.append({"type": "PRIVATE_LABEL_OPPORTUNITY", "sku_id": r.entity_id, "naam": r.entity_name, "kleur": "#8b5cf6"})
    alerts = alerts[:8]

    return {
        "total_skus": len(sku_rows),
        "run_date": str(sku_rows[0].date) if sku_rows else str(date.today()),
        "internal_counts": {INTERNAL_NL.get(k, k): v for k, v in internal_counts.items() if k},
        "external_counts": {EXTERNAL_NL.get(k, k): v for k, v in external_counts.items() if k},
        "hybrid_counts": {HYBRID_NL.get(k, k): v for k, v in hybrid_counts.items() if k},
        "top_pricing_power": [
            {
                "sku_id": r.entity_id,
                "naam": r.entity_name,
                "score": round(r.pricing_power_score or 0, 3),
                "strategie": STRATEGY_NL.get(r.pricing_strategy or "", r.pricing_strategy or ""),
                "prioriteit": r.strategic_priority,
            }
            for r in top_pps
        ],
        "top_private_label_stars": [
            {
                "sku_id": r.sku_id,
                "plsv": round(r.private_label_value_score or 0, 3),
                "klasse": PL_NL.get(r.private_label_class or "", r.private_label_class or ""),
                "overstapkans": round(r.internal_switch_probability or 0, 2),
                "margeverschil": round(r.internal_margin_gap or 0, 2),
            }
            for r in pl_rows
        ],
        "hoog_concurrentiedruk_categories": [
            {
                "categorie": r.entity_id,
                "css_score": round(r.css_external_score or 0, 3),
                "klasse": EXTERNAL_NL.get(r.external_bcg_class or "", r.external_bcg_class or ""),
            }
            for r in hoog_druk
        ],
        "alerts": alerts,
    }


# ─── GET /api/bcg/sku-matrix ──────────────────────────────────────────────────

@router.get("/sku-matrix")
def get_sku_matrix(
    type: str = "internal",
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    rows = _latest_sku_records(db)
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}

    result = []
    for r in rows:
        p = products.get(r.entity_id)
        revenue = float(p.current_price or 10) * (p.stock_quantity or 0) if p else 100
        bubble = min(40, max(8, revenue / 500))

        if type == "internal":
            x = round(r.ibss_score or 0, 3)
            y = round(r.gps_score or 0, 3)
            klasse = r.internal_bcg_class or ""
            klasse_nl = INTERNAL_NL.get(klasse, klasse)
        elif type == "external":
            x = round(r.css_external_score or 0, 3)
            y = round(r.mos_score or 0, 3)
            klasse = r.external_bcg_class or ""
            klasse_nl = EXTERNAL_NL.get(klasse, klasse)
        else:
            x = round(r.pricing_power_score or 0, 3)
            y = round(r.css_external_score or 0, 3)
            klasse = r.hybrid_bcg_class or ""
            klasse_nl = HYBRID_NL.get(klasse, klasse)

        result.append({
            "sku_id": r.entity_id,
            "naam": r.entity_name,
            "x": x,
            "y": y,
            "bubble": bubble,
            "klasse": klasse,
            "klasse_nl": klasse_nl,
            "kleur": BCG_KLEUR.get(klasse, "#94a3b8"),
            "pricing_power": round(r.pricing_power_score or 0, 3),
            "strategie": STRATEGY_NL.get(r.pricing_strategy or "", r.pricing_strategy or ""),
            "prioriteit": r.strategic_priority,
            "is_private_label": bool(p.is_private_label) if p else False,
            "categorie": p.category if p else "",
        })

    return {"items": result, "type": type, "run_date": str(rows[0].date) if rows else str(date.today())}


# ─── GET /api/bcg/sku/{sku_id} ────────────────────────────────────────────────

@router.get("/sku/{sku_id}")
def get_sku_bcg_detail(
    sku_id: str,
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    rows = _latest_sku_records(db)
    record = next((r for r in rows if r.entity_id == sku_id), None)
    if not record:
        raise HTTPException(404, f"SKU {sku_id} niet gevonden in BCG data")

    product = db.query(models.DimProduct).filter_by(sku_id=sku_id).first()
    pl_intel = db.query(models.FactPrivateLabelIntelligence).filter_by(sku_id=sku_id).order_by(
        models.FactPrivateLabelIntelligence.run_date.desc()
    ).first()

    pcis = db.query(models.SkuCompetitionScore).filter_by(sku_id=sku_id).order_by(
        models.SkuCompetitionScore.run_date.desc()
    ).first()

    elast = db.query(models.SkuElasticity).filter_by(sku_id=sku_id).order_by(
        models.SkuElasticity.run_date.desc()
    ).first()

    history = db.query(models.FactBcgHistory).filter_by(entity_id=sku_id).order_by(
        models.FactBcgHistory.changed_at.desc()
    ).limit(10).all()

    return {
        "sku_id": sku_id,
        "naam": record.entity_name,
        "categorie": product.category if product else "",
        "run_date": str(record.date),
        "scores": {
            "ibss": round(record.ibss_score or 0, 3),
            "gps": round(record.gps_score or 0, 3),
            "css_external": round(record.css_external_score or 0, 3),
            "mos": round(record.mos_score or 0, 3),
            "pricing_power": round(record.pricing_power_score or 0, 3),
            "plsv": round(record.plsv_score or 0, 3),
            "confidence": round(record.confidence_score or 0, 3),
        },
        "classificaties": {
            "intern": {
                "klasse": record.internal_bcg_class,
                "klasse_nl": INTERNAL_NL.get(record.internal_bcg_class or "", ""),
                "kleur": BCG_KLEUR.get(record.internal_bcg_class or "", "#94a3b8"),
            },
            "extern": {
                "klasse": record.external_bcg_class,
                "klasse_nl": EXTERNAL_NL.get(record.external_bcg_class or "", ""),
                "kleur": BCG_KLEUR.get(record.external_bcg_class or "", "#94a3b8"),
            },
            "hybrid": {
                "klasse": record.hybrid_bcg_class,
                "klasse_nl": HYBRID_NL.get(record.hybrid_bcg_class or "", ""),
                "kleur": BCG_KLEUR.get(record.hybrid_bcg_class or "", "#94a3b8"),
            },
        },
        "pricingstrategie": {
            "strategie": record.pricing_strategy,
            "strategie_nl": STRATEGY_NL.get(record.pricing_strategy or "", record.pricing_strategy or ""),
            "prioriteit": record.strategic_priority,
        },
        "concurrentie": {
            "pcis_score": round(float(pcis.pcis_score or 0), 3) if pcis else None,
            "competition_class": pcis.competition_class if pcis else None,
            "price_index": round(float(pcis.price_index or 1), 3) if pcis and pcis.price_index else None,
            "competitors_used": pcis.competitors_used if pcis else 0,
        },
        "elasticiteit": {
            "own": round(elast.own_price_elasticity or 0, 3) if elast else None,
            "cross": round(elast.cross_elasticity or 0, 3) if elast and elast.cross_elasticity else None,
            "confidence_class": elast.confidence_class if elast else None,
        },
        "huismerk": {
            "plsv": round(pl_intel.private_label_value_score or 0, 3) if pl_intel else None,
            "klasse": PL_NL.get(pl_intel.private_label_class or "", pl_intel.private_label_class or "") if pl_intel else None,
            "overstapkans": round(pl_intel.internal_switch_probability or 0, 2) if pl_intel else None,
            "margeverschil": round(pl_intel.internal_margin_gap or 0, 2) if pl_intel else None,
            "a_brand_sku": pl_intel.a_brand_sku if pl_intel else None,
        } if pl_intel else None,
        "geschiedenis": [
            {
                "type": h.classification_type,
                "oud": h.old_classification,
                "nieuw": h.new_classification,
                "datum": str(h.changed_at)[:10],
                "reden": h.reason,
            }
            for h in history
        ],
    }


# ─── GET /api/bcg/categorie-matrix ───────────────────────────────────────────

@router.get("/categorie-matrix")
def get_categorie_matrix(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    rows = _latest_cat_records(db)
    result = []
    for r in rows:
        result.append({
            "categorie": r.entity_id,
            "ibss": round(r.ibss_score or 0, 3),
            "gps": round(r.gps_score or 0, 3),
            "css_external": round(r.css_external_score or 0, 3),
            "mos": round(r.mos_score or 0, 3),
            "pricing_power": round(r.pricing_power_score or 0, 3),
            "internal_bcg_class": r.internal_bcg_class,
            "internal_bcg_nl": INTERNAL_NL.get(r.internal_bcg_class or "", ""),
            "external_bcg_class": r.external_bcg_class,
            "external_bcg_nl": EXTERNAL_NL.get(r.external_bcg_class or "", ""),
            "hybrid_bcg_class": r.hybrid_bcg_class,
            "hybrid_bcg_nl": HYBRID_NL.get(r.hybrid_bcg_class or "", ""),
            "kleur": BCG_KLEUR.get(r.hybrid_bcg_class or "", "#94a3b8"),
            "strategie": STRATEGY_NL.get(r.pricing_strategy or "", r.pricing_strategy or ""),
            "prioriteit": r.strategic_priority,
        })
    return {"items": result, "run_date": str(rows[0].date) if rows else str(date.today())}


# ─── GET /api/bcg/hybrid-matrix ──────────────────────────────────────────────

@router.get("/hybrid-matrix")
def get_hybrid_matrix(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    rows = _latest_sku_records(db)
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}

    result = []
    for r in rows:
        p = products.get(r.entity_id)
        # X-as: Pricing Power, Y-as: Concurrentiedruk (omgekeerd van CSS)
        x = round(r.pricing_power_score or 0, 3)
        y = round(1.0 - (r.css_external_score or 0.5), 3)  # hoog = veel druk
        result.append({
            "sku_id": r.entity_id,
            "naam": r.entity_name,
            "x": x,
            "y": y,
            "klasse": r.hybrid_bcg_class,
            "klasse_nl": HYBRID_NL.get(r.hybrid_bcg_class or "", ""),
            "kleur": BCG_KLEUR.get(r.hybrid_bcg_class or "", "#94a3b8"),
            "ibss": round(r.ibss_score or 0, 3),
            "gps": round(r.gps_score or 0, 3),
            "plsv": round(r.plsv_score or 0, 3),
            "strategie": STRATEGY_NL.get(r.pricing_strategy or "", r.pricing_strategy or ""),
            "prioriteit": r.strategic_priority,
            "is_private_label": bool(p.is_private_label) if p else False,
            "bubble": min(40, max(8, float(p.current_price or 10) * 2)) if p else 12,
        })

    # Kwadrant-samenvatting
    kwadranten = {
        "PRICING_POWER_STAR": sum(1 for r in rows if r.hybrid_bcg_class == "PRICING_POWER_STAR"),
        "DEFENSIVE_CASH_COW": sum(1 for r in rows if r.hybrid_bcg_class == "DEFENSIVE_CASH_COW"),
        "PRIVATE_LABEL_STAR": sum(1 for r in rows if r.hybrid_bcg_class == "PRIVATE_LABEL_STAR"),
        "EXPERIMENTAL_QUESTION_MARK": sum(1 for r in rows if r.hybrid_bcg_class == "EXPERIMENTAL_QUESTION_MARK"),
        "LOW_PRIORITY_DOG": sum(1 for r in rows if r.hybrid_bcg_class == "LOW_PRIORITY_DOG"),
    }

    return {
        "items": result,
        "kwadranten": kwadranten,
        "run_date": str(rows[0].date) if rows else str(date.today()),
    }


# ─── GET /api/bcg/huismerk ────────────────────────────────────────────────────

@router.get("/huismerk")
def get_huismerk_intelligence(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    pl_rows = db.query(models.FactPrivateLabelIntelligence).order_by(
        models.FactPrivateLabelIntelligence.run_date.desc(),
        models.FactPrivateLabelIntelligence.private_label_value_score.desc(),
    ).all()

    # Deduplicate op sku_id (neem meest recente)
    seen: set[str] = set()
    unique: list[models.FactPrivateLabelIntelligence] = []
    for r in pl_rows:
        if r.sku_id not in seen:
            seen.add(r.sku_id)
            unique.append(r)

    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}
    bcg_map = {r.entity_id: r for r in _latest_sku_records(db)}

    items = []
    for r in unique:
        p = products.get(r.sku_id)
        bcg = bcg_map.get(r.sku_id)
        items.append({
            "sku_id": r.sku_id,
            "naam": p.product_name if p else r.sku_id,
            "categorie": p.category if p else "",
            "plsv": round(r.private_label_value_score or 0, 3),
            "klasse": r.private_label_class,
            "klasse_nl": PL_NL.get(r.private_label_class or "", r.private_label_class or ""),
            "overstapkans": round(r.internal_switch_probability or 0, 2),
            "margeverschil": round(r.internal_margin_gap or 0, 2),
            "isv": round(r.internal_substitution_score or 0, 3),
            "a_brand_sku": r.a_brand_sku,
            "a_brand_naam": products[r.a_brand_sku].product_name if r.a_brand_sku and r.a_brand_sku in products else None,
            "prioriteit": r.strategic_priority,
            "hybrid_bcg": bcg.hybrid_bcg_class if bcg else None,
            "hybrid_bcg_nl": HYBRID_NL.get(bcg.hybrid_bcg_class or "", "") if bcg else None,
            "strategie": STRATEGY_NL.get(bcg.pricing_strategy or "", "") if bcg else None,
        })

    # Samenvatting tellingen
    tellingen = {}
    for r in unique:
        k = PL_NL.get(r.private_label_class or "", r.private_label_class or "")
        tellingen[k] = tellingen.get(k, 0) + 1

    return {"items": items, "tellingen": tellingen, "totaal": len(items)}


# ─── GET /api/bcg/pricing-power ───────────────────────────────────────────────

@router.get("/pricing-power")
def get_pricing_power(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    rows = _latest_sku_records(db)
    products = {p.sku_id: p for p in db.query(models.DimProduct).all()}

    sorted_rows = sorted(rows, key=lambda r: r.pricing_power_score or 0, reverse=True)

    items = []
    for r in sorted_rows:
        p = products.get(r.entity_id)
        pps = r.pricing_power_score or 0
        label = "Zeer hoog" if pps >= 0.75 else "Hoog" if pps >= 0.60 else "Gemiddeld" if pps >= 0.45 else "Laag" if pps >= 0.30 else "Zeer laag"
        items.append({
            "sku_id": r.entity_id,
            "naam": r.entity_name,
            "categorie": p.category if p else "",
            "pricing_power_score": round(pps, 3),
            "label": label,
            "ibss": round(r.ibss_score or 0, 3),
            "gps": round(r.gps_score or 0, 3),
            "hybrid_bcg": r.hybrid_bcg_class,
            "hybrid_bcg_nl": HYBRID_NL.get(r.hybrid_bcg_class or "", ""),
            "kleur": BCG_KLEUR.get(r.hybrid_bcg_class or "", "#94a3b8"),
            "strategie": STRATEGY_NL.get(r.pricing_strategy or "", r.pricing_strategy or ""),
            "prioriteit": r.strategic_priority,
            "is_private_label": bool(p.is_private_label) if p else False,
            "is_a_brand": bool(p.is_a_brand) if p else False,
        })

    # Verdelingsgrafiek (histogram per 0.10 bucket)
    distributie = {}
    for r in rows:
        bucket = f"{int((r.pricing_power_score or 0) * 10) * 10}%"
        distributie[bucket] = distributie.get(bucket, 0) + 1

    return {
        "items": items,
        "distributie": [{"bucket": k, "aantal": v} for k, v in sorted(distributie.items())],
        "gemiddeld": round(sum(r.pricing_power_score or 0 for r in rows) / len(rows), 3) if rows else 0,
    }


# ─── POST /api/bcg/run ────────────────────────────────────────────────────────

@router.post("/run")
def run_bcg(
    db: Session = Depends(get_db),
    _=Depends(auth_utils.get_current_user),
):
    processed, skipped = run_bcg_engine(db)
    return {
        "status": "voltooid",
        "verwerkt": processed,
        "overgeslagen": skipped,
        "datum": str(date.today()),
    }
