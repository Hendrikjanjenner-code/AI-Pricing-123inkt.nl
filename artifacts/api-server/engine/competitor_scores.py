"""
Concurrentscores: kracht, inkoopmacht & Future Threat (taak #247).

Bouwt op het concurrentprofiel-datamodel (taak #246) de score-laag:

Classificaties
  - Company Size (micro/klein/middelgroot/groot/enterprise): multi-signaal
    (omzet, medewerkers, landen-dekking, vestigingen) met configureerbare
    drempels; één datapunt kan de klasse nooit alleen bepalen als andere
    signalen dat tegenspreken (mediaan over alle signalen).
  - Geographic Scale (lokaal → globaal), apart van company size, met expliciet
    onderscheid "verzendt naar X landen" (webshop) vs. "operationeel actief in
    X landen" (operationeel).
  - Fulfilment Model (eigen_voorraad/dropship/hybride/marketplace) met
    confidence; zonder betrouwbare percentages worden géén fictieve
    percentages getoond maar "Bevestigd / Verdeling onbekend".

Scores (elk 0–100, elk met factoren, gewichten, bronnen en confidence)
  - Operational Strength, Financial Health (status + score + aparte Financial
    Data Confidence), Business Strength, Procurement Power, Future Threat.

Unknown-beleid
  - Ontbrekende data ⇒ score NULL ("Unknown") + Data Completeness; nooit
    automatisch 0. Lage financial confidence dempt het gewicht van de
    financial score in afgeleide modellen (Business Strength).

Feature-dependencies (tegen dubbeltelling)
  - FEATURE_DEPENDENCIES documenteert per ruwe feature welke consumenten hem
    mogen gebruiken; _FeatureLedger dwingt dat af in de berekening. Afgeleide
    scores consumeren classificaties (bv. company-size-index), niet nogmaals
    de ruwe features: "7 landen actief" voedt Geographic Scale én (via de
    scale-index) Business Strength, maar niet 5 scores onafhankelijk.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from services.competitor_profile import source_priority

logger = logging.getLogger(__name__)

MODEL_VERSION = "competitor-scores-v1.0.0"

SIZE_CLASSES = ["micro", "klein", "middelgroot", "groot", "enterprise"]
GEO_CLASSES = ["lokaal", "nationaal", "regionaal", "internationaal", "globaal"]

# ── Feature-dependency-registratie (documentatie + afdwinging) ──────────────
# Ruwe feature → toegestane consumenten. Afgeleide scores gebruiken
# classificatie-indexen (company_size_index, geographic_scale_index,
# financial_health_score), nooit opnieuw de ruwe feature.
FEATURE_DEPENDENCIES: dict[str, set[str]] = {
    "revenue":            {"company_size", "financial_health",
                           "future_threat_growth"},
    "employees":          {"company_size", "future_threat_growth"},
    "countries_operational": {"company_size", "geographic_scale"},
    "countries_webshop":  {"geographic_scale"},
    "warehouse_count":    {"company_size", "operational_strength"},
    "fulfilment_model":   {"fulfilment_classification", "operational_strength"},
    "delivery_speed":     {"operational_strength"},
    "in_stock_rate":      {"operational_strength"},
    "assortment":         {"business_strength"},
    "profit":             {"financial_health"},
    "equity":             {"financial_health"},
    "ownership":          {"procurement_power"},
    "corporate_relations": {"procurement_power", "future_threat_acquisitions"},
    "private_label_role": {"procurement_power", "future_threat_capability"},
    "evolution_events":   {"future_threat_expansion", "future_threat_growth",
                           "future_threat_capability", "future_threat_acquisitions"},
    "supplier_overlap_role": {"future_threat_supplier_overlap"},
    # Afgeleide indexen (uit classificaties) — expliciet toegestane herbruik:
    "company_size_index": {"business_strength", "procurement_power"},
    "geographic_scale_index": {"business_strength"},
    "financial_health_score": {"business_strength"},
}


class FeatureDependencyError(RuntimeError):
    """Een score gebruikt een feature die niet voor hem gedocumenteerd is."""


class _FeatureLedger:
    """Dwingt FEATURE_DEPENDENCIES af: elke feature-consumptie wordt
    geregistreerd en moet gedocumenteerd zijn."""

    def __init__(self) -> None:
        self.used: dict[str, set[str]] = {}

    def use(self, feature: str, consumer: str) -> None:
        allowed = FEATURE_DEPENDENCIES.get(feature)
        if allowed is None or consumer not in allowed:
            raise FeatureDependencyError(
                f"Feature '{feature}' is niet gedocumenteerd voor consument "
                f"'{consumer}' (zie FEATURE_DEPENDENCIES; dubbeltelling-guard).")
        self.used.setdefault(feature, set()).add(consumer)

    def as_dict(self) -> dict[str, list[str]]:
        return {f: sorted(c) for f, c in sorted(self.used.items())}


def _bounds_index(value: float, bounds: list) -> int:
    """0..len(bounds): index van de klasse waar value in valt."""
    idx = 0
    for b in bounds:
        if value >= float(b):
            idx += 1
    return min(idx, len(bounds))


def _range_mid(lo, hi) -> Optional[float]:
    vals = [float(v) for v in (lo, hi) if v is not None]
    return sum(vals) / len(vals) if vals else None


def _meta_confidence(field_meta: dict, field: str, default: float = 0.6) -> float:
    m = (field_meta or {}).get(field) or {}
    c = m.get("confidence")
    return float(c) if isinstance(c, (int, float)) else default


def _meta_source(field_meta: dict, field: str) -> str:
    m = (field_meta or {}).get(field) or {}
    return m.get("source") or m.get("information_layer") or "profiel"


# ── 1. Company Size ──────────────────────────────────────────────────────────

def classify_company_size(*, business, financials: list, geo_rows: list,
                          fulfilment, cfg: dict, ledger: _FeatureLedger) -> dict:
    """
    Multi-signaal classificatie. Elk signaal levert een klasse-index (0..4);
    de uiteindelijke klasse is de mediaan — één afwijkend datapunt kan de
    klasse dus nooit alleen bepalen als andere signalen dat tegenspreken.
    """
    signals: list[dict] = []

    # Omzet: profielrange of beste (bronprioriteit) financiële observatie
    revenue = _range_mid(getattr(business, "revenue_range_min", None),
                         getattr(business, "revenue_range_max", None))
    rev_source = "business_profile"
    if revenue is None:
        obs = _best_observation(financials, "revenue")
        if obs is not None:
            revenue = _range_mid(obs.value_min, obs.value_max)
            rev_source = f"financiele_observatie_{obs.fiscal_year}"
    if revenue is not None:
        ledger.use("revenue", "company_size")
        idx = _bounds_index(revenue / 1_000_000.0, cfg["size_revenue_bounds_meur"])
        signals.append({"signal": "omzet", "value": revenue, "index": idx,
                        "source": rev_source})

    employees = _range_mid(getattr(business, "employee_range_min", None),
                           getattr(business, "employee_range_max", None))
    emp_source = "business_profile"
    if employees is None:
        obs = _best_observation(financials, "employees")
        if obs is not None:
            employees = _range_mid(obs.value_min, obs.value_max)
            emp_source = f"financiele_observatie_{obs.fiscal_year}"
    if employees is not None:
        ledger.use("employees", "company_size")
        idx = _bounds_index(employees, cfg["size_employee_bounds"])
        signals.append({"signal": "medewerkers", "value": employees,
                        "index": idx, "source": emp_source})

    op_countries = {r.country_code for r in geo_rows
                    if r.presence_type == "operationeel" and r.valid_to is None}
    if op_countries:
        ledger.use("countries_operational", "company_size")
        idx = _bounds_index(len(op_countries), cfg["size_country_bounds"])
        signals.append({"signal": "dekking_landen_operationeel",
                        "value": len(op_countries), "index": idx,
                        "source": "geographic_presence"})

    wh = getattr(fulfilment, "warehouse_count", None)
    if wh is not None:
        ledger.use("warehouse_count", "company_size")
        idx = _bounds_index(float(wh), cfg["size_warehouse_bounds"])
        signals.append({"signal": "vestigingen_magazijnen", "value": wh,
                        "index": idx, "source": "fulfilment_profile"})

    if not signals:
        return {"class": None, "index": None, "confidence": None,
                "signals": [], "explanation":
                "Unknown: geen enkel omvangssignaal (omzet, medewerkers, "
                "dekking, vestigingen) beschikbaar."}

    indexes = [s["index"] for s in signals]
    final_idx = int(round(median(indexes)))
    spread = max(indexes) - min(indexes)
    # Confidence: meer signalen + minder onderlinge spreiding = hoger.
    confidence = round(min(0.95, 0.35 + 0.15 * len(signals) - 0.10 * spread), 2)
    confidence = max(0.20, confidence)
    single = len(signals) == 1
    explanation = (
        f"Company size '{SIZE_CLASSES[final_idx]}' op basis van "
        f"{len(signals)} signaal/signalen (mediaan van klasse-indexen "
        f"{sorted(indexes)}); één datapunt kan de klasse niet alleen bepalen."
        + (" Let op: slechts één signaal beschikbaar (lage confidence)."
           if single else ""))
    return {"class": SIZE_CLASSES[final_idx], "index": final_idx,
            "confidence": confidence if not single else min(confidence, 0.5),
            "signals": signals, "explanation": explanation}


def _best_observation(financials: list, metric: str):
    """Beste niet-unknown observatie voor een metric: recentste boekjaar,
    binnen dat jaar de betrouwbaarste bron (laagste source-prioriteit)."""
    rows = [f for f in financials if f.metric == metric and not f.is_unknown
            and (f.value_min is not None or f.value_max is not None)]
    if not rows:
        return None
    rows.sort(key=lambda r: (-r.fiscal_year, r.source_prio, -(r.confidence or 0)))
    return rows[0]


# ── 2. Geographic Scale ──────────────────────────────────────────────────────

def classify_geographic_scale(*, business, geo_rows: list, cfg: dict,
                              ledger: _FeatureLedger) -> dict:
    """Apart van company size. Onderscheidt 'verzendt naar X landen'
    (presence_type webshop) van 'operationeel actief in X landen'."""
    active = [r for r in geo_rows if r.valid_to is None]
    operational = sorted({r.country_code for r in active
                          if r.presence_type == "operationeel"})
    webshop = sorted({r.country_code for r in active
                      if r.presence_type == "webshop"})

    declared = getattr(business, "geographic_scale", None)

    if not operational and not webshop and not declared:
        return {"class": None, "index": None, "confidence": None,
                "ships_to_countries": [], "operational_countries": [],
                "explanation": "Unknown: geen geografische aanwezigheid of "
                               "opgegeven schaal bekend."}

    basis = "operationeel"
    if operational:
        ledger.use("countries_operational", "geographic_scale")
        idx = _bounds_index(len(operational), cfg["geo_country_bounds"])
        confidence = 0.8
    elif webshop:
        # Alleen verzendlanden bekend: schaal op verzendbereik, expliciet
        # lager vertrouwen — verzenden naar een land ≠ er operationeel zijn.
        ledger.use("countries_webshop", "geographic_scale")
        idx = _bounds_index(len(webshop), cfg["geo_country_bounds"])
        basis = "webshop_verzendlanden"
        confidence = 0.5
    else:
        mapping = {"lokaal": 0, "nationaal": 1, "eu": 2, "regionaal": 2,
                   "internationaal": 3, "globaal": 4}
        idx = mapping.get(str(declared).lower(), 1)
        basis = "opgegeven_schaal_business_profile"
        confidence = 0.4

    return {
        "class": GEO_CLASSES[idx], "index": idx,
        "confidence": confidence,
        "basis": basis,
        "ships_to_countries": webshop,
        "operational_countries": operational,
        "explanation": (
            f"Geographic scale '{GEO_CLASSES[idx]}' op basis van {basis}: "
            f"operationeel actief in {len(operational)} land(en) "
            f"({', '.join(operational) or '—'}), verzendt naar "
            f"{len(webshop)} land(en) ({', '.join(webshop) or '—'})."),
    }


# ── 3. Fulfilment Model ──────────────────────────────────────────────────────

def classify_fulfilment_model(*, fulfilment, ledger: _FeatureLedger) -> dict:
    """Classificatie met confidence. Zonder betrouwbare percentages worden
    géén fictieve percentages getoond: distribution_known=False en label
    'Bevestigd / Verdeling onbekend'."""
    if fulfilment is None:
        return {"class": None, "confidence": None, "distribution_known": False,
                "distribution": None, "explanation":
                "Unknown: geen fulfilment-profiel beschikbaar."}

    ledger.use("fulfilment_model", "fulfilment_classification")
    meta = fulfilment.field_meta or {}
    model = fulfilment.inventory_model
    role = (fulfilment.marketplace_role or "").lower()
    dropship = fulfilment.dropship_share_pct
    own = fulfilment.own_stock_share_pct

    if role in ("platform", "beide"):
        cls = "marketplace"
        conf = _meta_confidence(meta, "marketplace_role", 0.6)
        src = _meta_source(meta, "marketplace_role")
    elif dropship is not None and own is not None:
        if dropship >= 80:
            cls = "dropship"
        elif own >= 80:
            cls = "eigen_voorraad"
        else:
            cls = "hybride"
        conf = min(_meta_confidence(meta, "dropship_share_pct", 0.7),
                   _meta_confidence(meta, "own_stock_share_pct", 0.7))
        src = _meta_source(meta, "dropship_share_pct")
    elif model:
        cls = model
        conf = _meta_confidence(meta, "inventory_model", 0.6)
        src = _meta_source(meta, "inventory_model")
    else:
        return {"class": None, "confidence": None, "distribution_known": False,
                "distribution": None, "explanation":
                "Unknown: fulfilment-model niet vastgesteld."}

    distribution_known = dropship is not None and own is not None
    distribution = (
        {"dropship_pct": float(dropship), "own_stock_pct": float(own)}
        if distribution_known else None)
    return {
        "class": cls,
        "confidence": round(float(conf), 2),
        "distribution_known": distribution_known,
        "distribution": distribution,
        "distribution_label": ("verdeling bekend" if distribution_known
                               else "Bevestigd / Verdeling onbekend"),
        "source": src,
        "explanation": (
            f"Fulfilment-model '{cls}' (confidence {conf:.2f}). "
            + (f"Verdeling: {distribution['dropship_pct']:.0f}% dropship / "
               f"{distribution['own_stock_pct']:.0f}% eigen voorraad."
               if distribution_known else
               "Model bevestigd, verdeling onbekend — er worden geen "
               "fictieve percentages getoond.")),
    }


# ── 4. Financial Health ──────────────────────────────────────────────────────

def score_financial_health(*, financials: list,
                           ledger: _FeatureLedger) -> dict:
    """
    Status + score + aparte Financial Data Confidence. Minimum-data-eis:
    minstens één niet-unknown omzet- of winstobservatie; anders status
    'unknown' en score NULL (nooit 0). Bronprioriteit via evidence-bron
    (jaarrekening > kvk > jaarverslag > ...).
    """
    revenue_rows = sorted(
        [f for f in financials if f.metric == "revenue" and not f.is_unknown
         and (f.value_min is not None or f.value_max is not None)],
        key=lambda r: r.fiscal_year)
    profit = _best_observation(financials, "profit")
    equity = _best_observation(financials, "equity")

    if not revenue_rows and profit is None:
        return {"status": "unknown", "score": None, "data_confidence": None,
                "factors": [], "explanation":
                "Unknown: onvoldoende financiële data (geen omzet- of "
                "winstobservatie). Score is bewust géén 0."}

    factors: list[dict] = []
    score = 50.0

    if profit is not None:
        ledger.use("profit", "financial_health")
        val = _range_mid(profit.value_min, profit.value_max) or 0.0
        delta = 20.0 if val > 0 else (-20.0 if val < 0 else 0.0)
        score += delta
        factors.append({"factor": "winstgevendheid", "value": val,
                        "effect": delta,
                        "source": profit.source_label,
                        "confidence": profit.confidence,
                        "fiscal_year": profit.fiscal_year})

    if len(revenue_rows) >= 2:
        ledger.use("revenue", "financial_health")
        # Per boekjaar beste bron nemen, dan trend over de laatste twee jaren
        by_year: dict[int, Any] = {}
        for r in revenue_rows:
            cur = by_year.get(r.fiscal_year)
            if cur is None or r.source_prio < cur.source_prio:
                by_year[r.fiscal_year] = r
        years = sorted(by_year)
        prev = _range_mid(by_year[years[-2]].value_min, by_year[years[-2]].value_max)
        last = _range_mid(by_year[years[-1]].value_min, by_year[years[-1]].value_max)
        if prev and last and prev > 0:
            growth = (last - prev) / prev
            delta = max(-15.0, min(15.0, growth * 75.0))
            score += delta
            factors.append({"factor": "omzettrend", "value": round(growth, 4),
                            "effect": round(delta, 1),
                            "source": by_year[years[-1]].source_label,
                            "confidence": by_year[years[-1]].confidence,
                            "fiscal_years": years[-2:]})
    elif revenue_rows:
        ledger.use("revenue", "financial_health")
        factors.append({"factor": "omzet_bekend_geen_trend",
                        "value": _range_mid(revenue_rows[-1].value_min,
                                            revenue_rows[-1].value_max),
                        "effect": 0.0,
                        "source": revenue_rows[-1].source_label,
                        "confidence": revenue_rows[-1].confidence,
                        "fiscal_year": revenue_rows[-1].fiscal_year})

    if equity is not None:
        ledger.use("equity", "financial_health")
        val = _range_mid(equity.value_min, equity.value_max) or 0.0
        delta = 10.0 if val > 0 else -10.0
        score += delta
        factors.append({"factor": "eigen_vermogen", "value": val,
                        "effect": delta, "source": equity.source_label,
                        "confidence": equity.confidence,
                        "fiscal_year": equity.fiscal_year})

    score = round(max(0.0, min(100.0, score)), 1)
    status = "gezond" if score >= 65 else ("aandacht" if score >= 40 else "zwak")

    # Aparte Financial Data Confidence: bronprioriteit + aantal metrics + recency
    used = [f for f in (revenue_rows[-1:] + [profit, equity]) if f is not None]
    prio_conf = [max(0.2, 1.0 - 0.09 * (f.source_prio - 1)) for f in used]
    base = sum(prio_conf) / len(prio_conf) if prio_conf else 0.3
    this_year = date.today().year
    recency = max((f.fiscal_year for f in used), default=this_year - 5)
    recency_penalty = min(0.3, 0.1 * max(0, this_year - 1 - recency))
    data_confidence = round(max(0.1, min(0.95,
                                         base + 0.05 * (len(used) - 1)
                                         - recency_penalty)), 2)

    return {
        "status": status, "score": score,
        "data_confidence": data_confidence,
        "factors": factors,
        "explanation": (
            f"Financial health '{status}' (score {score:.0f}/100, "
            f"financial data confidence {data_confidence:.2f}) op basis van "
            f"{len(factors)} factor(en) met bronprioriteit "
            "(jaarrekening > KvK > jaarverslag > ...)."),
    }


# ── 5. Operational Strength ──────────────────────────────────────────────────

def score_operational_strength(*, fulfilment, legacy_profile, fulfil_cls: dict,
                               cfg: dict, ledger: _FeatureLedger) -> dict:
    """Factoren: fulfilment-controle (classificatie), leversnelheid,
    magazijn-schaal, beschikbaarheid. Ontbrekende factoren tellen niet als 0
    maar vallen weg (gewichten hernormaliseren); geen enkele factor ⇒ Unknown."""
    w = cfg["operational_weights"]
    factors: list[dict] = []

    if fulfil_cls.get("class") is not None:
        ledger.use("fulfilment_model", "operational_strength")
        control = {"eigen_voorraad": 90.0, "hybride": 70.0,
                   "marketplace": 60.0, "dropship": 40.0}.get(
                       fulfil_cls["class"], 55.0)
        factors.append({"factor": "fulfilment_control", "score": control,
                        "weight": w["fulfilment_control"],
                        "source": "fulfilment_classificatie",
                        "confidence": fulfil_cls.get("confidence")})

    delivery_parts: list[float] = []
    delivery_srcs: list[str] = []
    if fulfilment is not None and (fulfilment.next_day_delivery is not None
                                   or fulfilment.same_day_delivery is not None):
        pts = 50.0
        if fulfilment.next_day_delivery:
            pts = 80.0
        if fulfilment.same_day_delivery:
            pts = 95.0
        delivery_parts.append(pts)
        delivery_srcs.append("fulfilment_profile")
    if legacy_profile is not None and legacy_profile.avg_delivery_days is not None:
        d = float(legacy_profile.avg_delivery_days)
        delivery_parts.append(max(0.0, min(100.0, 100.0 - (d - 1.0) * 20.0)))
        delivery_srcs.append("prijsfeed_levertijden")
    if delivery_parts:
        ledger.use("delivery_speed", "operational_strength")
        factors.append({"factor": "delivery",
                        "score": round(sum(delivery_parts) / len(delivery_parts), 1),
                        "weight": w["delivery"],
                        "source": "+".join(delivery_srcs),
                        "confidence": 0.7})

    if fulfilment is not None and fulfilment.warehouse_count is not None:
        ledger.use("warehouse_count", "operational_strength")
        wh = float(fulfilment.warehouse_count)
        factors.append({"factor": "warehouse_scale",
                        "score": round(min(100.0, 20.0 + wh * 16.0), 1),
                        "weight": w["warehouse_scale"],
                        "source": "fulfilment_profile",
                        "confidence": _meta_confidence(
                            fulfilment.field_meta or {}, "warehouse_count", 0.6)})

    if legacy_profile is not None and legacy_profile.in_stock_rate is not None:
        ledger.use("in_stock_rate", "operational_strength")
        rate = float(legacy_profile.in_stock_rate)
        if rate > 1.0:
            rate = rate / 100.0
        factors.append({"factor": "availability",
                        "score": round(rate * 100.0, 1),
                        "weight": w["availability"],
                        "source": "aanbod_feed_in_stock_rate",
                        "confidence": 0.8})

    return _weighted_score(factors, "Operational Strength")


def _weighted_score(factors: list[dict], label: str,
                    completeness_of: Optional[int] = None) -> dict:
    if not factors:
        return {"score": None, "factors": [], "weights_used": {},
                "explanation": f"Unknown: geen enkele {label}-factor "
                               "beschikbaar. Score is bewust géén 0."}
    total_w = sum(f["weight"] for f in factors)
    score = round(sum(f["score"] * f["weight"] for f in factors) / total_w, 1)
    return {
        "score": score,
        "factors": factors,
        "weights_used": {f["factor"]: f["weight"] for f in factors},
        "explanation": (
            f"{label} {score:.0f}/100 op basis van {len(factors)} factor(en); "
            "ontbrekende factoren zijn weggelaten (gewichten "
            "gehernormaliseerd), niet als 0 geteld."),
    }


# ── 6. Business Strength ─────────────────────────────────────────────────────

def score_business_strength(*, size_cls: dict, geo_cls: dict,
                            financial: dict, legacy_profile,
                            cfg: dict, ledger: _FeatureLedger) -> dict:
    """Gebruikt classificatie-INDEXEN (geen ruwe features opnieuw — zie
    FEATURE_DEPENDENCIES) + assortimentsbreedte + financial health, waarbij
    lage financial data confidence het financiële gewicht dempt."""
    w = cfg["business_weights"]
    factors: list[dict] = []

    if size_cls.get("index") is not None:
        ledger.use("company_size_index", "business_strength")
        factors.append({"factor": "company_size",
                        "score": round(size_cls["index"] / 4.0 * 100.0, 1),
                        "weight": w["company_size"],
                        "source": "company_size_classificatie",
                        "confidence": size_cls.get("confidence")})

    if geo_cls.get("index") is not None:
        ledger.use("geographic_scale_index", "business_strength")
        factors.append({"factor": "geographic_scale",
                        "score": round(geo_cls["index"] / 4.0 * 100.0, 1),
                        "weight": w["geographic_scale"],
                        "source": "geographic_scale_classificatie",
                        "confidence": geo_cls.get("confidence")})

    if legacy_profile is not None and (legacy_profile.assortment_size
                                       or legacy_profile.category_breadth):
        ledger.use("assortment", "business_strength")
        size_pts = min(100.0, float(legacy_profile.assortment_size or 0) / 30.0 * 60.0)
        breadth_pts = min(40.0, float(legacy_profile.category_breadth or 0) * 8.0)
        factors.append({"factor": "assortment_breadth",
                        "score": round(min(100.0, size_pts + breadth_pts), 1),
                        "weight": w["assortment_breadth"],
                        "source": "prijsfeed_assortiment",
                        "confidence": 0.7})

    if financial.get("score") is not None:
        ledger.use("financial_health_score", "business_strength")
        conf = financial.get("data_confidence") or 0.0
        # Demping: lage financial confidence verlaagt het effectieve gewicht.
        damped = round(w["financial_health"] * conf, 2)
        if damped > 0:
            factors.append({"factor": "financial_health",
                            "score": financial["score"],
                            "weight": damped,
                            "weight_before_damping": w["financial_health"],
                            "source": "financial_health_score",
                            "confidence": conf,
                            "note": "gewicht gedempt met financial data confidence"})

    return _weighted_score(factors, "Business Strength")


# ── 7. Procurement Power ─────────────────────────────────────────────────────

def score_procurement_power(*, size_cls: dict, business, relations: list,
                            roles: list, legacy_profile, cfg: dict,
                            ledger: _FeatureLedger) -> dict:
    """Inkoopmacht: omvang (size-index), corporate backing (moederbedrijf /
    ownership), inkoopschaal (assortiment als proxy is NIET toegestaan —
    alleen omvang), private label."""
    w = cfg["procurement_weights"]
    factors: list[dict] = []

    if size_cls.get("index") is not None:
        ledger.use("company_size_index", "procurement_power")
        factors.append({"factor": "company_size",
                        "score": round(size_cls["index"] / 4.0 * 100.0, 1),
                        "weight": w["company_size"],
                        "source": "company_size_classificatie",
                        "confidence": size_cls.get("confidence")})

    active_parents = [r for r in relations
                      if r.relation_type in ("parent", "ultimate_parent")
                      and r.valid_to is None]
    ownership = getattr(business, "ownership_type", None)
    if active_parents or ownership:
        ledger.use("corporate_relations", "procurement_power")
        ledger.use("ownership", "procurement_power")
        pts = 30.0
        srcs = []
        if active_parents:
            pts += 40.0
            srcs.append(f"{len(active_parents)} moederrelatie(s)")
        if ownership in ("private_equity", "beursgenoteerd"):
            pts += 30.0
            srcs.append(f"ownership={ownership}")
        elif ownership:
            srcs.append(f"ownership={ownership}")
        factors.append({"factor": "corporate_backing",
                        "score": round(min(100.0, pts), 1),
                        "weight": w["corporate_backing"],
                        "source": "; ".join(srcs) or "corporate_relations",
                        "confidence": max([r.confidence or 0.5
                                           for r in active_parents], default=0.5)})

    subsidiaries = [r for r in relations
                    if r.relation_type in ("subsidiary", "sister")
                    and r.valid_to is None]
    if subsidiaries:
        factors.append({"factor": "purchasing_scale",
                        "score": round(min(100.0, 40.0 + 15.0 * len(subsidiaries)), 1),
                        "weight": w["purchasing_scale"],
                        "source": f"{len(subsidiaries)} dochter-/zusterbedrijven",
                        "confidence": 0.5})

    pl_roles = [r for r in roles if r.valid_to is None
                and "private_label" in (r.role or "")]
    if pl_roles:
        ledger.use("private_label_role", "procurement_power")
        factors.append({"factor": "private_label",
                        "score": 80.0,
                        "weight": w["private_label"],
                        "source": "marktrol private_label",
                        "confidence": max(r.confidence or 0.5 for r in pl_roles)})

    return _weighted_score(factors, "Procurement Power")


# ── 8. Future Threat ─────────────────────────────────────────────────────────

_THREAT_WINDOW_DAYS = 365


def score_future_threat(*, financials: list, evolution_events: list,
                        relations: list, roles: list, cfg: dict,
                        ledger: _FeatureLedger,
                        ref_date: Optional[date] = None) -> dict:
    """
    Future Threat uit de profielhistorie: omzet-/medewerkersgroei,
    landenuitbreiding, overnames, nieuwe magazijnen, private label en
    supplier overlap. Toont ALTIJD welke signalen verantwoordelijk zijn.
    Groei/expansie-signalen komen uit de evolution-historie en de
    meerjaars-financials. Geen enkel signaal én geen historie ⇒ Unknown.
    """
    w = cfg["future_threat_weights"]
    today = ref_date or date.today()
    window_start = datetime.combine(today - timedelta(days=_THREAT_WINDOW_DAYS),
                                    datetime.min.time())
    events = [e for e in evolution_events
              if e.occurred_at and e.occurred_at >= window_start]

    signals: list[dict] = []

    # Groei: omzet en medewerkers over boekjaren
    growth_pts = []
    for metric, label in (("revenue", "omzetgroei"), ("employees", "medewerkersgroei")):
        rows = sorted([f for f in financials if f.metric == metric
                       and not f.is_unknown
                       and (f.value_min is not None or f.value_max is not None)],
                      key=lambda r: r.fiscal_year)
        by_year: dict[int, Any] = {}
        for r in rows:
            cur = by_year.get(r.fiscal_year)
            if cur is None or r.source_prio < cur.source_prio:
                by_year[r.fiscal_year] = r
        years = sorted(by_year)
        if len(years) >= 2:
            prev = _range_mid(by_year[years[-2]].value_min, by_year[years[-2]].value_max)
            last = _range_mid(by_year[years[-1]].value_min, by_year[years[-1]].value_max)
            if prev and last and prev > 0:
                g = (last - prev) / prev
                pts = max(0.0, min(100.0, g * 250.0))  # +40% groei = maximaal
                growth_pts.append(pts)
                signals.append({"signal": label, "growth_pct": round(g * 100, 1),
                                "points": round(pts, 1),
                                "fiscal_years": years[-2:],
                                "source": by_year[years[-1]].source_label,
                                "component": "growth"})
    if metric_events := [e for e in events if e.section == "financials"]:
        # Historie-events tellen als bewijs van beweging, niet dubbel als groei
        signals.append({"signal": "financiele_profielwijzigingen",
                        "count": len(metric_events), "points": 0.0,
                        "component": "growth",
                        "note": "informatief; groei wordt uit boekjaren berekend"})
    component_scores: dict[str, float] = {}
    if growth_pts:
        # Gedocumenteerd gedeeld gebruik: omzet/medewerkers voeden zowel de
        # size-classificatie/financial health als de groeicomponent — maar
        # binnen Future Threat alleen als groei-delta, niet als niveau.
        ledger.use("revenue", "future_threat_growth")
        ledger.use("employees", "future_threat_growth")
        component_scores["growth"] = sum(growth_pts) / len(growth_pts)

    # Expansie: landen-events in de evolution-historie
    geo_events = [e for e in events if e.section == "geography"
                  and e.event_type in ("created", "changed")]
    if geo_events:
        ledger.use("evolution_events", "future_threat_expansion")
        pts = min(100.0, 30.0 + 20.0 * len(geo_events))
        component_scores["expansion"] = pts
        signals.append({"signal": "landenuitbreiding",
                        "count": len(geo_events), "points": round(pts, 1),
                        "component": "expansion",
                        "source": "evolution_historie"})

    # Overnames / corporate beweging
    rel_events = [e for e in events if e.section == "relations"
                  and e.event_type in ("created", "changed")]
    recent_subsidiaries = [
        r for r in relations if r.relation_type == "subsidiary"
        and r.valid_from and r.valid_from >= today - timedelta(days=_THREAT_WINDOW_DAYS)]
    if rel_events or recent_subsidiaries:
        ledger.use("corporate_relations", "future_threat_acquisitions")
        ledger.use("evolution_events", "future_threat_acquisitions")
        n = len(rel_events) + len(recent_subsidiaries)
        pts = min(100.0, 40.0 + 20.0 * n)
        component_scores["acquisitions"] = pts
        signals.append({"signal": "overnames_corporate",
                        "count": n, "points": round(pts, 1),
                        "component": "acquisitions",
                        "source": "corporate_relations + evolution_historie"})

    # Capability-investeringen: nieuwe magazijnen, private label
    ful_events = [e for e in events if e.section == "fulfilment"
                  and e.field_name == "warehouse_count"]
    pl_events = [e for e in events if e.section == "roles"
                 and "private_label" in str(e.new_value or "")]
    pl_roles = [r for r in roles if r.valid_to is None
                and "private_label" in (r.role or "")
                and r.valid_from
                and r.valid_from >= today - timedelta(days=_THREAT_WINDOW_DAYS)]
    if ful_events or pl_events or pl_roles:
        ledger.use("evolution_events", "future_threat_capability")
        ledger.use("private_label_role", "future_threat_capability")
        n = len(ful_events) + len(pl_events) + len(pl_roles)
        pts = min(100.0, 35.0 + 20.0 * n)
        component_scores["capability_investments"] = pts
        parts = []
        if ful_events:
            parts.append(f"{len(ful_events)} magazijn-wijziging(en)")
        if pl_events or pl_roles:
            parts.append("private-label-start")
        signals.append({"signal": "capability_investeringen",
                        "detail": ", ".join(parts), "points": round(pts, 1),
                        "component": "capability_investments",
                        "source": "evolution_historie + marktrollen"})

    # Supplier overlap (marktrol)
    so_roles = [r for r in roles if r.valid_to is None
                and "supplier_overlap" in (r.role or "")]
    if so_roles:
        ledger.use("supplier_overlap_role", "future_threat_supplier_overlap")
        pts = min(100.0, 50.0 + 20.0 * len(so_roles))
        component_scores["supplier_overlap"] = pts
        signals.append({"signal": "supplier_overlap",
                        "count": len(so_roles), "points": round(pts, 1),
                        "component": "supplier_overlap",
                        "source": "marktrollen"})

    if not component_scores:
        has_history = bool(evolution_events) or bool(financials)
        return {"score": None, "signals": signals, "components": {},
                "explanation": (
                    "Unknown: geen groei-/expansie-signalen in de historie."
                    if has_history else
                    "Unknown: geen profielhistorie beschikbaar. Score is "
                    "bewust géén 0.")}

    # Gewogen over aanwezige componenten (hernormaliseren; groei/expansie
    # wegen per configuratie het zwaarst).
    total_w = sum(w[c] for c in component_scores)
    score = round(sum(component_scores[c] * w[c] for c in component_scores) / total_w, 1)
    return {
        "score": score,
        "signals": signals,
        "components": {c: round(v, 1) for c, v in component_scores.items()},
        "weights_used": {c: w[c] for c in component_scores},
        "explanation": (
            f"Future Threat {score:.0f}/100 uit {len(signals)} signaal/signalen "
            f"({', '.join(sorted(component_scores))}); groei- en "
            "expansie-signalen uit de evolution-historie wegen het zwaarst."),
    }


# ── Orchestratie ─────────────────────────────────────────────────────────────

def run_competitor_scores(db: Session, run_date: Optional[date] = None,
                          shop_id: Optional[int] = None, **_kw) -> dict:
    """
    Bereken en persisteer classificaties + scores per concurrent.
    Per-shop; zonder shop_id draaien alle shops met profieldata.
    Herrun op dezelfde dag = delete-then-insert. Fouten falen zichtbaar.
    """
    from engine.run_profiling import RunProfiler, check_slow_run
    from services import competition_settings as cs

    today = run_date or date.today()
    if shop_id is not None:
        shop_ids = [shop_id]
    else:
        shop_ids = sorted({
            s for (s,) in (
                db.query(models.CompetitorProfile.shop_id).distinct().all()
                + db.query(models.CompetitorBusinessProfile.shop_id).distinct().all()
                + db.query(models.CompetitorFulfilmentProfile.shop_id).distinct().all()
            ) if s is not None})

    written = 0
    profiler = RunProfiler("competitor-scores", logger)
    for sid in shop_ids:
        written += profiler.timed(
            f"shop_{sid}", lambda s=sid: _run_for_shop(db, today, s))
    db.commit()

    # Trage-run-bewaking: per-shop scheduled runs zijn het productiepad —
    # shop-gescopeerde runs worden dus NIET uitgezonderd (shop-scoped signaal).
    cfg_sid = shop_id if shop_id is not None else (
        cs.default_shop_id(db) if shop_ids else None)
    if cfg_sid is not None:
        threshold = float(cs.get_settings(db, cfg_sid)["strength_config"]
                          .get("slow_run_threshold_seconds", 60.0))
        if check_slow_run(
                db, profiler, engine="competition",
                entity_name="Competitor Scores Engine",
                run_date=today, threshold_seconds=threshold,
                model_version=MODEL_VERSION,
                shop_id=shop_id, entity_id=str(shop_id or "all")):
            db.commit()

    return {"rows_written": written, "shops": len(shop_ids)}


class _Obs:
    """Financiële observatie verrijkt met bronprioriteit/-label uit evidence."""
    __slots__ = ("metric", "fiscal_year", "value_min", "value_max",
                 "is_unknown", "confidence", "source_prio", "source_label")

    def __init__(self, row, evidence_by_id: dict):
        self.metric = row.metric
        self.fiscal_year = row.fiscal_year
        self.value_min = row.value_min
        self.value_max = row.value_max
        self.is_unknown = bool(row.is_unknown)
        self.confidence = row.confidence
        ev = evidence_by_id.get(row.evidence_id)
        src = ev.source_type if ev is not None else None
        self.source_prio = source_priority(src) if src else 9
        self.source_label = src or row.source_note or row.information_layer


def _run_for_shop(db: Session, today: date, sid: int) -> int:
    from services import competition_settings as cs
    cfg = cs.get_settings(db, sid)["strength_config"]

    def _by_name(model_cls) -> dict[str, list]:
        out: dict[str, list] = {}
        for r in db.query(model_cls).filter(model_cls.shop_id == sid).all():
            out.setdefault(r.competitor_name, []).append(r)
        return out

    business_by = {r.competitor_name: r for r in
                   db.query(models.CompetitorBusinessProfile)
                   .filter(models.CompetitorBusinessProfile.shop_id == sid).all()}
    fulfil_by = {r.competitor_name: r for r in
                 db.query(models.CompetitorFulfilmentProfile)
                 .filter(models.CompetitorFulfilmentProfile.shop_id == sid).all()}
    legacy_by = {r.competitor_name: r for r in
                 db.query(models.CompetitorProfile)
                 .filter(models.CompetitorProfile.shop_id == sid).all()}
    fin_by = _by_name(models.CompetitorFinancialObservation)
    geo_by = _by_name(models.CompetitorGeographicPresence)
    rel_by = _by_name(models.CompetitorCorporateRelation)
    role_by = _by_name(models.CompetitorMarketRole)
    evo_by = _by_name(models.CompetitorEvolutionEvent)
    evidence_by_id = {e.id: e for e in
                      db.query(models.CompetitionEvidence)
                      .filter(models.CompetitionEvidence.shop_id == sid).all()}

    names = (set(business_by) | set(fulfil_by) | set(fin_by) | set(geo_by)
             | set(rel_by) | set(role_by) | set(legacy_by))
    if not names:
        return 0

    # Herrun = delete-then-insert voor vandaag
    db.query(models.CompetitorScoreResult).filter(
        models.CompetitorScoreResult.shop_id == sid,
        models.CompetitorScoreResult.run_date == today,
    ).delete(synchronize_session=False)

    written = 0
    for name in sorted(names):
        ledger = _FeatureLedger()
        business = business_by.get(name)
        fulfilment = fulfil_by.get(name)
        legacy = legacy_by.get(name)
        financials = [_Obs(r, evidence_by_id) for r in fin_by.get(name, [])]
        geo_rows = geo_by.get(name, [])
        relations = rel_by.get(name, [])
        roles = role_by.get(name, [])
        evolution = evo_by.get(name, [])

        size_cls = classify_company_size(
            business=business, financials=financials, geo_rows=geo_rows,
            fulfilment=fulfilment, cfg=cfg, ledger=ledger)
        geo_cls = classify_geographic_scale(
            business=business, geo_rows=geo_rows, cfg=cfg, ledger=ledger)
        fulfil_cls = classify_fulfilment_model(
            fulfilment=fulfilment, ledger=ledger)
        financial = score_financial_health(
            financials=financials, ledger=ledger)
        operational = score_operational_strength(
            fulfilment=fulfilment, legacy_profile=legacy,
            fulfil_cls=fulfil_cls, cfg=cfg, ledger=ledger)
        business_strength = score_business_strength(
            size_cls=size_cls, geo_cls=geo_cls, financial=financial,
            legacy_profile=legacy, cfg=cfg, ledger=ledger)
        procurement = score_procurement_power(
            size_cls=size_cls, business=business, relations=relations,
            roles=roles, legacy_profile=legacy, cfg=cfg, ledger=ledger)
        threat = score_future_threat(
            financials=financials, evolution_events=evolution,
            relations=relations, roles=roles, cfg=cfg, ledger=ledger,
            ref_date=today)

        sections_available = sum(1 for present in [
            business is not None, fulfilment is not None,
            bool(financials), bool(geo_rows),
            bool(relations) or bool(roles), bool(evolution),
        ] if present)
        completeness = round(100.0 * sections_available / 6.0, 1)

        db.add(models.CompetitorScoreResult(
            shop_id=sid, competitor_name=name, run_date=today,
            company_size_class=size_cls["class"],
            company_size_confidence=size_cls["confidence"],
            geographic_scale_class=geo_cls["class"],
            geographic_scale_confidence=geo_cls["confidence"],
            fulfilment_model_class=fulfil_cls["class"],
            fulfilment_model_confidence=fulfil_cls["confidence"],
            operational_strength_score=operational["score"],
            financial_health_score=financial["score"],
            financial_health_status=financial["status"],
            financial_data_confidence=financial["data_confidence"],
            business_strength_score=business_strength["score"],
            procurement_power_score=procurement["score"],
            future_threat_score=threat["score"],
            data_completeness_pct=completeness,
            details={
                "company_size": size_cls,
                "geographic_scale": geo_cls,
                "fulfilment_model": fulfil_cls,
                "financial_health": financial,
                "operational_strength": operational,
                "business_strength": business_strength,
                "procurement_power": procurement,
                "future_threat": threat,
                "feature_usage": ledger.as_dict(),
                "data_completeness": {
                    "sections_available": sections_available,
                    "sections_total": 6,
                    "pct": completeness,
                },
            },
            model_version=MODEL_VERSION,
        ))
        written += 1
    return written


def latest_scores_by_competitor(db: Session, sid: int) -> dict[str, "models.CompetitorScoreResult"]:
    """Meest recente score-rij per concurrent binnen een shop."""
    out: dict[str, models.CompetitorScoreResult] = {}
    for r in (db.query(models.CompetitorScoreResult)
              .filter(models.CompetitorScoreResult.shop_id == sid)
              .order_by(models.CompetitorScoreResult.competitor_name,
                        models.CompetitorScoreResult.run_date.desc())
              .all()):
        if r.competitor_name not in out:
            out[r.competitor_name] = r
    return out
