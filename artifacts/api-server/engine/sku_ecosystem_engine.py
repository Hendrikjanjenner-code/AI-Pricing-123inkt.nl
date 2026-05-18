"""
SKU Ecosystem Engine
Berekent SKU Ecosystem Value Score (SEVS) en classificeert SKU-rollen.
"""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from models import DimProduct, FactBcgClassificationDaily, SkuCompetitionScore, SkuElasticity


# ── Gewichten SEVS ────────────────────────────────────────────────────────────

SEVS_WEIGHTS = {
    "traffic_driver_score":       0.20,
    "basket_builder_score":       0.18,
    "margin_amplification_score": 0.15,
    "entry_product_score":        0.12,
    "repeat_contribution_score":  0.12,
    "private_label_contribution": 0.08,
    "margin_contribution_score":  0.15,
}

# SKU-rol drempelwaarden
ROLE_THRESHOLDS = {
    "TRAFFIC_DRIVER":       ("traffic_driver_score",       0.55),
    "BASKET_BUILDER":       ("basket_builder_score",       0.50),
    "MARGIN_DRIVER":        ("margin_contribution_score",  0.60),
    "RETENTION_DRIVER":     ("repeat_contribution_score",  0.55),
    "PORTFOLIO_DRIVER":     ("entry_product_score",        0.50),
    "PRIVATE_LABEL_DRIVER": ("private_label_contribution", 0.45),
}

SEVS_LABELS = {
    "KRITIEK": (0.72, "Strategisch kritiek SKU — beschermen ongeacht directe marge."),
    "HOOG":    (0.52, "Hoge ecosysteemwaarde — pricing voorzichtig aanpassen."),
    "MEDIUM":  (0.32, "Gemiddelde ecosysteemwaarde — regulier beheer."),
    "LAAG":    (0.00, "Lage ecosysteemwaarde — optimalisatie of sanering overwegen."),
}


def calculate_margin_amplification(
    sku_id: str,
    direct_margin_pct: float,
    basket_builder_score: float,
    repeat_contribution_score: float,
    private_label_contribution: float,
) -> float:
    """Margin Amplification Score (MAS): indirecte margebijdrage."""
    # Basket uplift: hoge BBS = meer crosssell marge
    basket_factor = basket_builder_score * 0.40
    # Repeat: loyale klanten = lagere acquisitiekosten
    repeat_factor = repeat_contribution_score * 0.35
    # Private label: eigen merk pushes = hogere marge
    pl_factor = private_label_contribution * 0.25
    return round(min(1.0, basket_factor + repeat_factor + pl_factor), 3)


def classify_sku_roles(scores: Dict[str, float]) -> tuple[str, str]:
    """Bepaal primaire en secundaire SKU-rollen op basis van scores."""
    actieve_rollen = [
        rol for rol, (attr, drempel) in ROLE_THRESHOLDS.items()
        if scores.get(attr, 0) >= drempel
    ]

    if not actieve_rollen:
        actieve_rollen = ["MARGIN_DRIVER"]

    primair = actieve_rollen[0]
    secundair = ",".join(actieve_rollen[1:]) if len(actieve_rollen) > 1 else ""
    return primair, secundair


def calculate_repeat_contribution(
    sku_id: str,
    db: Session,
    rng_seed: int = 42,
) -> float:
    """Schat herhaalaankoop-bijdrage (RCS) voor dit SKU."""
    import random
    rng = random.Random(rng_seed)
    # In productie: gebruik fact_sales_daily repeat customer ratio
    # Nu: simuleer op basis van categorie
    prod = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not prod:
        return 0.4
    cat = (prod.category or "").lower()
    if "ink" in cat or "toner" in cat:
        return round(rng.uniform(0.65, 0.90), 3)
    elif "paper" in cat:
        return round(rng.uniform(0.55, 0.80), 3)
    elif "office" in cat:
        return round(rng.uniform(0.40, 0.65), 3)
    elif "electronics" in cat:
        return round(rng.uniform(0.15, 0.35), 3)
    return round(rng.uniform(0.30, 0.55), 3)


def calculate_private_label_contribution(
    sku_id: str,
    db: Session,
) -> float:
    """Private label bijdrage: hoeveel draagt dit SKU bij aan PL strategie."""
    from models import MapSubstitution
    # Check if SKU is in een substitutie-pair (als A-merk of huismerk)
    sub_a = db.query(MapSubstitution).filter(MapSubstitution.a_brand_sku == sku_id).first()
    sub_pl = db.query(MapSubstitution).filter(MapSubstitution.private_label_sku == sku_id).first()

    if sub_pl:
        return 0.80   # IS huismerk
    elif sub_a:
        return 0.45   # Gekoppeld aan huismerk (A-merk met PL alternatief)
    return 0.10


def get_bcg_pricing_power(sku_id: str, db: Session) -> float:
    """Haal pricing power op uit BCG-classificatie."""
    rec = (
        db.query(FactBcgClassificationDaily)
        .filter(
            FactBcgClassificationDaily.entity_id == sku_id,
            FactBcgClassificationDaily.entity_type == "SKU",
        )
        .order_by(FactBcgClassificationDaily.date.desc())
        .first()
    )
    if rec and rec.pricing_power_score:
        return float(rec.pricing_power_score)
    return 0.55


def calculate_sevs(scores: Dict[str, float]) -> float:
    """Bereken SKU Ecosystem Value Score (SEVS) 0–1."""
    sevs = sum(
        scores.get(attr, 0) * weight
        for attr, weight in SEVS_WEIGHTS.items()
    )
    return round(min(1.0, sevs), 3)


def get_sevs_label(sevs: float) -> tuple[str, str]:
    for label, (drempel, tekst) in SEVS_LABELS.items():
        if sevs >= drempel:
            return label, tekst
    return "LAAG", SEVS_LABELS["LAAG"][1]


def generate_pricing_advice(
    sevs: float,
    traffic_driver_score: float,
    basket_builder_score: float,
    direct_margin_pct: float,
    entry_product_score: float,
) -> tuple[str, str, str]:
    """
    Genereer pricing advies op basis van ecosysteemwaarde.
    Returns: (pricing_sensitivity, protection_advice, strategic_note_nl)
    """
    if sevs >= 0.72:
        sensitivity = "HOOG"
        advice = "BESCHERMEN"
        if traffic_driver_score >= 0.60:
            note = "Kritieke traffic driver — vermijd prijsverhoging. SKU beschermen voor organische acquisitie."
        elif basket_builder_score >= 0.55:
            note = "Kritieke winkelmandvuller — promoties en bundels mogelijk. Directe marge minder relevant."
        else:
            note = "Hoge ecosysteemwaarde — strategisch beschermen. Marge-optimalisatie elders zoeken."
    elif sevs >= 0.52:
        sensitivity = "MEDIUM"
        advice = "OPTIMALISEREN"
        if entry_product_score >= 0.50:
            note = "Sterk entry product — pricing voorzichtig aanpassen. Nieuwe klantacquisitie niet in gevaar brengen."
        elif direct_margin_pct < 15:
            note = "Lage directe marge maar hoge ecosysteemwaarde — indirecte waarde compenseert. Niet saneren."
        else:
            note = "Goede ecosysteemwaarde — reguliere pricing optimalisatie mogelijk."
    elif sevs >= 0.32:
        sensitivity = "MEDIUM"
        advice = "NEUTRALE_STRATEGIE"
        note = "Gemiddelde ecosysteemwaarde — standaard pricing regels toepassen."
    else:
        sensitivity = "LAAG"
        advice = "MARGE_OPTIMALISEREN"
        if direct_margin_pct < 10:
            note = "Lage ecosysteemwaarde én lage marge — sanering of repricing overwegen."
        else:
            note = "Lage ecosysteemwaarde — focus op directe margeoptimalisatie."

    return sensitivity, advice, note


def compute_ecosystem_record(
    prod: DimProduct,
    tds_score: float,
    bbs_score: float,
    eps_score: float,
    db: Session,
    ref_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Bereken volledig ecosysteem-record voor één SKU."""
    import random
    if ref_date is None:
        ref_date = date.today()

    rng = random.Random(hash(prod.sku_id) % 10000)

    sp = float(prod.current_price or 10)
    cp = float(prod.cost_price or sp * 0.6)
    direct_margin_pct = max(0, (sp - cp) / sp * 100) if sp > 0 else 30.0

    # Component scores
    repeat_rcs = calculate_repeat_contribution(prod.sku_id, db, rng_seed=abs(hash(prod.sku_id)) % 9999)
    pl_contr = calculate_private_label_contribution(prod.sku_id, db)
    margin_contrib = min(1.0, direct_margin_pct / 50.0)  # 50% marge = perfecte score

    mas = calculate_margin_amplification(prod.sku_id, direct_margin_pct, bbs_score, repeat_rcs, pl_contr)

    scores = {
        "traffic_driver_score":       tds_score,
        "basket_builder_score":       bbs_score,
        "margin_amplification_score": mas,
        "entry_product_score":        eps_score,
        "repeat_contribution_score":  repeat_rcs,
        "private_label_contribution": pl_contr,
        "margin_contribution_score":  margin_contrib,
    }

    sevs = calculate_sevs(scores)
    sevs_label, _ = get_sevs_label(sevs)
    primair, secundair = classify_sku_roles(scores)
    sensitivity, advice, note = generate_pricing_advice(
        sevs, tds_score, bbs_score, direct_margin_pct, eps_score
    )

    return {
        "date": ref_date,
        "sku_id": prod.sku_id,
        "sku_name": prod.product_name,
        "category": prod.category,
        "traffic_driver_score": tds_score,
        "basket_builder_score": bbs_score,
        "margin_amplification_score": mas,
        "entry_product_score": eps_score,
        "repeat_contribution_score": repeat_rcs,
        "private_label_contribution": pl_contr,
        "margin_contribution_score": margin_contrib,
        "ecosystem_value_score": sevs,
        "sevs_label": sevs_label,
        "primary_sku_role": primair,
        "secondary_sku_role": secundair,
        "pricing_sensitivity": sensitivity,
        "protection_advice": advice,
        "strategic_note_nl": note,
    }


def get_ecosystem_dashboard(db: Session) -> Dict[str, Any]:
    """SKU Ecosystem Value dashboard."""
    from models import FactSkuEcosystemDaily
    from sqlalchemy import func

    latest = db.query(func.max(FactSkuEcosystemDaily.date)).scalar()
    if not latest:
        return {"datum": None, "totaal_skus": 0, "skus": []}

    recs = (
        db.query(FactSkuEcosystemDaily)
        .filter(FactSkuEcosystemDaily.date == latest)
        .order_by(FactSkuEcosystemDaily.ecosystem_value_score.desc())
        .all()
    )

    kritiek = [r for r in recs if r.sevs_label == "KRITIEK"]
    laag = [r for r in recs if r.sevs_label == "LAAG"]

    def avg_f(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    rol_verdeling: Dict[str, int] = {}
    for r in recs:
        rol = r.primary_sku_role or "ONBEKEND"
        rol_verdeling[rol] = rol_verdeling.get(rol, 0) + 1

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "kritiek_count": len(kritiek),
        "laag_count": len(laag),
        "gemiddelde_sevs": avg_f("ecosystem_value_score"),
        "gemiddelde_tds": avg_f("traffic_driver_score"),
        "gemiddelde_bbs": avg_f("basket_builder_score"),
        "gemiddelde_mas": avg_f("margin_amplification_score"),
        "rol_verdeling": rol_verdeling,
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "traffic_driver_score": float(r.traffic_driver_score or 0),
                "basket_builder_score": float(r.basket_builder_score or 0),
                "margin_amplification_score": float(r.margin_amplification_score or 0),
                "entry_product_score": float(r.entry_product_score or 0),
                "repeat_contribution_score": float(r.repeat_contribution_score or 0),
                "private_label_contribution": float(r.private_label_contribution or 0),
                "margin_contribution_score": float(r.margin_contribution_score or 0),
                "ecosystem_value_score": float(r.ecosystem_value_score or 0),
                "sevs_label": r.sevs_label,
                "primaire_rol": r.primary_sku_role,
                "secundaire_rollen": (r.secondary_sku_role or "").split(",") if r.secondary_sku_role else [],
                "pricing_gevoeligheid": r.pricing_sensitivity,
                "bescherming_advies": r.protection_advice,
                "strategische_noot": r.strategic_note_nl,
            }
            for r in recs
        ],
    }
