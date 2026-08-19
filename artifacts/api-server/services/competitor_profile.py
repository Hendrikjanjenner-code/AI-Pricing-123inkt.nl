"""
Concurrentprofiel-service (taak #246).

Bevat de domeinlogica voor het bedrijfsprofiel per concurrent:
- bronprioriteit voor financiële data (jaarrekening > KvK > jaarverslag > ...)
- de social-media-guard: sociale media mogen nooit de enige basis zijn voor
  een sterke financiële conclusie (informatielaag "feit" of hoge confidence)
- expliciete unknown-afhandeling (unknown ≠ 0 / leeg-goed)
- Data Completeness per profielonderdeel
- configureerbare freshness-regels per veldtype
- evolution-events (Competitor Evolution Timeline)
- handmatige validatie-workflow (AI- én menselijke waarde blijven bewaard;
  menselijke correctie wint operationeel)

Belangrijk: er worden nérgens land-inferenties gedaan. Land van hoofdkantoor,
moederbedrijf of warehouse levert nooit automatisch claims over
belastingvoordeel, inkoopcondities e.d. — zonder aparte evidence blijft dat
"Niet vastgesteld".
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

import models

# ── Informatielagen ──────────────────────────────────────────────────────────
INFORMATION_LAYERS = ("feit", "schatting", "afgeleid_signaal", "hypothese")

# ── Bronprioriteit financiële data (lager = betrouwbaarder) ─────────────────
FINANCIAL_SOURCE_PRIORITY: dict[str, int] = {
    "jaarrekening": 1,
    "kvk": 2,
    "jaarverslag": 3,
    "persbericht": 4,
    "nieuwsartikel": 5,
    "bedrijfswebsite": 6,
    "linkedin": 7,
    "social_media": 8,
    "externe_schatting": 9,
    "handmatig": 6,
    "demo_seed": 9,
}
SOCIAL_SOURCE_TYPES = {"social_media", "linkedin"}
# Sterke financiële conclusie: laag "feit" of confidence >= deze drempel.
STRONG_FINANCIAL_CONFIDENCE = 0.7


def source_priority(source_type: str) -> int:
    return FINANCIAL_SOURCE_PRIORITY.get(source_type, 9)


# ── Freshness-defaults per veldtype (max leeftijd in dagen) ─────────────────
FRESHNESS_DEFAULTS: dict[str, int] = {
    "price": 2,          # prijs: uren/dagen
    "employees": 270,    # 6–12 maanden
    "revenue": 365,      # jaarlijks
    "countries": 150,    # 3–6 maanden
    "fulfilment": 150,   # 3–6 maanden
    "ownership": 365,
    "roles": 180,
    "default": 180,
}

# Welke velden van de singleton-profielen worden gevolgd voor completeness.
BUSINESS_FIELDS = [
    "legal_name", "kvk_number", "founded_year", "customer_model", "size_class",
    "employee_range_min", "employee_range_max", "revenue_range_min",
    "revenue_range_max", "revenue_currency", "geographic_scale",
    "ownership_type", "headquarters_country",
]
FULFILMENT_FIELDS = [
    "inventory_model", "warehouse_count", "warehouse_locations",
    "dropship_share_pct", "own_stock_share_pct", "next_day_delivery",
    "same_day_delivery", "marketplace_role",
]

# Veldnaam → freshness-veldtype voor de singleton-profielen.
FIELD_TYPE_MAP: dict[str, str] = {
    "employee_range_min": "employees",
    "employee_range_max": "employees",
    "revenue_range_min": "revenue",
    "revenue_range_max": "revenue",
    "revenue_currency": "revenue",
    "headquarters_country": "countries",
    "ownership_type": "ownership",
    "inventory_model": "fulfilment",
    "warehouse_count": "fulfilment",
    "warehouse_locations": "fulfilment",
    "dropship_share_pct": "fulfilment",
    "own_stock_share_pct": "fulfilment",
    "next_day_delivery": "fulfilment",
    "same_day_delivery": "fulfilment",
    "marketplace_role": "fulfilment",
}


class SocialOnlyFinancialError(ValueError):
    """Sociale media als enige basis voor een sterke financiële conclusie."""


class EvidenceScopeError(ValueError):
    """Evidence-id bestaat niet of hoort bij een andere shop/concurrent."""


def resolve_evidence(db: Session, shop_id: int, competitor_name: str,
                     evidence_id: Optional[int]):
    """Centrale evidence-resolutie: een evidence_id is alleen geldig als het
    record bestaat én bij dezelfde shop en dezelfde concurrent hoort.
    Voorkomt cross-tenant koppelingen en orphan-referenties."""
    if evidence_id is None:
        return None
    ev = db.query(models.CompetitionEvidence).filter(
        models.CompetitionEvidence.id == evidence_id,
        models.CompetitionEvidence.shop_id == shop_id,
        models.CompetitionEvidence.competitor_name == competitor_name,
    ).first()
    if ev is None:
        raise EvidenceScopeError(
            f"evidence_id {evidence_id} bestaat niet voor deze concurrent "
            "binnen deze winkel")
    return ev


def get_freshness_rules(db: Session, shop_id: int) -> dict[str, int]:
    """Effectieve freshness-regels: defaults ← globale overrides (shop NULL)
    ← shop-specifieke overrides."""
    rules = dict(FRESHNESS_DEFAULTS)
    rows = (db.query(models.CompetitorFreshnessRule)
            .filter((models.CompetitorFreshnessRule.shop_id == None)  # noqa: E711
                    | (models.CompetitorFreshnessRule.shop_id == shop_id))
            .all())
    # Eerst globale (shop_id NULL), daarna shop-specifiek zodat die wint.
    for row in sorted(rows, key=lambda r: (r.shop_id is not None)):
        rules[row.field_type] = row.max_age_days
    return rules


def is_stale(last_verified_at: Optional[datetime], field_type: str,
             rules: dict[str, int]) -> Optional[bool]:
    """True/False, of None als er nog nooit geverifieerd is (dan geldt het
    veld sowieso als niet-vers, maar dat is 'onbekend', niet 'verouderd')."""
    if last_verified_at is None:
        return None
    max_age = rules.get(field_type, rules.get("default", 180))
    return (datetime.utcnow() - last_verified_at) > timedelta(days=max_age)


def validate_information_layer(layer: str) -> None:
    if layer not in INFORMATION_LAYERS:
        raise ValueError(
            f"Onbekende informatielaag '{layer}'; geldig: {', '.join(INFORMATION_LAYERS)}")


def check_financial_evidence_guard(*, information_layer: str,
                                   confidence: float, evidence) -> None:
    """Sociale media mogen nooit de enige basis zijn voor een sterke
    financiële conclusie (laag 'feit' of confidence >= drempel).
    `evidence` is een reeds via resolve_evidence gescoped record (of None)."""
    strong = information_layer == "feit" or (confidence or 0) >= STRONG_FINANCIAL_CONFIDENCE
    if not strong:
        return
    if evidence is None:
        raise SocialOnlyFinancialError(
            "Een sterke financiële conclusie (laag 'feit' of hoge confidence) "
            "vereist een gekoppeld evidence-record.")
    if evidence.source_type in SOCIAL_SOURCE_TYPES:
        raise SocialOnlyFinancialError(
            "Sociale media (of alleen LinkedIn) mogen niet de enige basis zijn "
            "voor een sterke financiële conclusie. Verlaag de informatielaag "
            "naar 'schatting'/'hypothese' of koppel een sterkere bron "
            "(jaarrekening, KvK, jaarverslag).")


def record_event(db: Session, shop_id: int, competitor_name: str, *,
                 section: str, field_name: Optional[str], event_type: str,
                 old_value: Any = None, new_value: Any = None,
                 change_source: str = "handmatig",
                 changed_by: Optional[str] = None,
                 evidence_id: Optional[int] = None) -> None:
    db.add(models.CompetitorEvolutionEvent(
        shop_id=shop_id, competitor_name=competitor_name, section=section,
        field_name=field_name, event_type=event_type,
        old_value=_jsonable(old_value), new_value=_jsonable(new_value),
        change_source=change_source, changed_by=changed_by,
        evidence_id=evidence_id))


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, (int, float, bool)):
        return float(value)
    return value


def apply_profile_update(db: Session, profile, fields: list[str],
                         payload: dict, *, shop_id: int, competitor_name: str,
                         section: str, changed_by: Optional[str],
                         change_source: str = "handmatig") -> list[str]:
    """
    Pas veld-updates toe op een singleton-profiel (business/fulfilment).
    payload["fields"] = {veldnaam: {value, status?, information_layer?,
    confidence?, evidence_id?, source?, as_of_date?}}.
    status "unknown" markeert het veld expliciet als onbekend (waarde wordt
    dan NULL, maar de meta legt vast dát dit een bewuste unknown is).
    Retourneert de lijst van gewijzigde velden; logt evolution-events.
    """
    changed: list[str] = []
    meta = dict(profile.field_meta or {})
    now = datetime.utcnow()
    for field, spec in (payload.get("fields") or {}).items():
        if field not in fields:
            raise ValueError(f"Onbekend profielveld '{field}' voor sectie {section}")
        if not isinstance(spec, dict):
            spec = {"value": spec}
        layer = spec.get("information_layer", "schatting")
        validate_information_layer(layer)
        status = spec.get("status", "known")
        if status not in ("known", "unknown", "blocked", "needs_review"):
            raise ValueError(f"Onbekende veldstatus '{status}'")
        # Evidence moet bestaan én bij deze shop/concurrent horen.
        resolve_evidence(db, shop_id, competitor_name, spec.get("evidence_id"))
        new_value = None if status == "unknown" else spec.get("value")
        old_value = getattr(profile, field)
        old_status = (meta.get(field) or {}).get("status")
        if _jsonable(old_value) != _jsonable(new_value) or old_status != status:
            record_event(db, shop_id, competitor_name, section=section,
                         field_name=field,
                         event_type="changed" if (old_value is not None or old_status) else "created",
                         old_value=old_value,
                         new_value=new_value if status != "unknown" else "unknown",
                         change_source=change_source, changed_by=changed_by,
                         evidence_id=spec.get("evidence_id"))
            changed.append(field)
        setattr(profile, field, new_value)
        meta[field] = {
            "status": status,
            "information_layer": layer,
            "confidence": spec.get("confidence"),
            "evidence_id": spec.get("evidence_id"),
            "source": spec.get("source"),
            "as_of_date": spec.get("as_of_date"),
            "last_verified_at": now.isoformat(),
        }
    profile.field_meta = meta
    profile.last_verified_at = now
    return changed


def section_completeness(profile, fields: list[str],
                         rules: dict[str, int]) -> dict:
    """
    Data Completeness voor een singleton-profielsectie.
    - known: veld heeft een waarde met meta
    - unknown: expliciet als onbekend gemarkeerd (telt niet als compleet,
      maar wél als 'behandeld')
    - missing: nooit ingevuld
    Plus freshness per veld op basis van de regels.
    """
    known = unknown = 0
    stale_fields: list[str] = []
    meta = (profile.field_meta or {}) if profile is not None else {}
    for f in fields:
        m = meta.get(f) or {}
        status = m.get("status")
        if status == "unknown":
            unknown += 1
            continue
        value = getattr(profile, f, None) if profile is not None else None
        if value is not None:
            known += 1
            lva = m.get("last_verified_at")
            ts = datetime.fromisoformat(lva) if isinstance(lva, str) else None
            ftype = FIELD_TYPE_MAP.get(f, "default")
            if is_stale(ts, ftype, rules):
                stale_fields.append(f)
    total = len(fields)
    return {
        "total_fields": total,
        "known": known,
        "unknown_explicit": unknown,
        "missing": total - known - unknown,
        "completeness_pct": round(100.0 * known / total, 1) if total else 0.0,
        "stale_fields": stale_fields,
    }


# ── Profielkwaliteit-vlaggen (Competition Data Quality, taak #249) ──────────
# Eén gedeelde berekening voor de DQ-scan én de Copilot-datakwaliteitsfunctie,
# zodat "profiel moet opnieuw gecontroleerd worden" overal dezelfde definitie
# heeft. Confidence-drempel voor low-confidence profielvelden:
LOW_PROFILE_CONFIDENCE = 0.5

# Issue-codes (code-keyed registry in de DQ-scan)
CP_FLAG_CODES = (
    "CP_UNKNOWN_COMPANY_SIZE", "CP_MISSING_FOUNDED_YEAR",
    "CP_STALE_EMPLOYEE_ESTIMATE", "CP_STALE_REVENUE_ESTIMATE",
    "CP_UNKNOWN_FULFILMENT_MODEL", "CP_UNKNOWN_DROPSHIP_MODEL",
    "CP_UNKNOWN_ACTIVE_COUNTRIES", "CP_MISSING_OWNERSHIP",
    "CP_STALE_FINANCIALS", "CP_CONFLICTING_FINANCIALS",
    "CP_MISSING_PROFILE_SOURCE", "CP_LOW_CONFIDENCE_PROFILE",
    "CP_INCONSISTENT_PARENT_RELATIONS",
)


def _meta_status(meta: dict, field: str) -> Optional[str]:
    return ((meta or {}).get(field) or {}).get("status")


def _meta_verified(meta: dict, field: str) -> Optional[datetime]:
    lva = ((meta or {}).get(field) or {}).get("last_verified_at")
    if isinstance(lva, str):
        try:
            return datetime.fromisoformat(lva)
        except ValueError:
            return None
    return None


def profile_quality_flags(db: Session, shop_id: int,
                          competitor_name: Optional[str] = None) -> dict[str, dict]:
    """
    Kwaliteitsvlaggen per concurrent binnen één shop.

    Returns {competitor_name: {"flags": [issue_codes], "stale_fields": [...],
    "low_confidence_fields": [...], "missing_source_fields": [...],
    "open_recheck_requests": int, "needs_recheck": bool}}.

    Definities volgen de freshness-configuratie (get_freshness_rules) en de
    expliciete unknown-conventie: een veld dat bewust op status "unknown"
    staat is behandeld, maar het gegeven blijft onbekend en vlagt dus wél.
    """
    rules = get_freshness_rules(db, shop_id)

    def _q(model):
        q = db.query(model).filter(model.shop_id == shop_id)
        if competitor_name:
            q = q.filter(model.competitor_name == competitor_name)
        return q.all()

    names: set[str] = set()
    if competitor_name:
        names.add(competitor_name)
    else:
        for model in (models.CompetitorProfile, models.CompetitorBusinessProfile):
            for (n,) in (db.query(model.competitor_name)
                         .filter(model.shop_id == shop_id).distinct()):
                names.add(n)

    business = {b.competitor_name: b for b in _q(models.CompetitorBusinessProfile)}
    fulfilment = {f.competitor_name: f for f in _q(models.CompetitorFulfilmentProfile)}
    geo: dict[str, list] = {}
    for g in _q(models.CompetitorGeographicPresence):
        if g.valid_to is None:
            geo.setdefault(g.competitor_name, []).append(g)
    relations: dict[str, list] = {}
    for r in _q(models.CompetitorCorporateRelation):
        if r.valid_to is None:
            relations.setdefault(r.competitor_name, []).append(r)
    financials: dict[str, list] = {}
    for f in _q(models.CompetitorFinancialObservation):
        financials.setdefault(f.competitor_name, []).append(f)
    recheck: dict[str, int] = {}
    for v in _q(models.CompetitorFieldValidation):
        if v.is_current and v.action == "heronderzoek":
            recheck[v.competitor_name] = recheck.get(v.competitor_name, 0) + 1

    out: dict[str, dict] = {}
    for name in sorted(names):
        flags: list[str] = []
        stale_fields: list[str] = []
        low_conf: list[str] = []
        no_source: list[str] = []
        b = business.get(name)
        bmeta = (b.field_meta or {}) if b is not None else {}

        # Company size / oprichtingsjaar / ownership
        if b is None or (b.size_class is None):
            flags.append("CP_UNKNOWN_COMPANY_SIZE")
        if b is None or (b.founded_year is None):
            flags.append("CP_MISSING_FOUNDED_YEAR")
        if (b is None or b.ownership_type is None) and not relations.get(name):
            flags.append("CP_MISSING_OWNERSHIP")

        # Verouderde employee-/revenue-estimates (freshness-regels)
        if b is not None:
            for field, code in (("employee_range_min", "CP_STALE_EMPLOYEE_ESTIMATE"),
                                ("employee_range_max", "CP_STALE_EMPLOYEE_ESTIMATE"),
                                ("revenue_range_min", "CP_STALE_REVENUE_ESTIMATE"),
                                ("revenue_range_max", "CP_STALE_REVENUE_ESTIMATE")):
                if getattr(b, field) is None:
                    continue
                ftype = FIELD_TYPE_MAP.get(field, "default")
                if is_stale(_meta_verified(bmeta, field), ftype, rules):
                    if code not in flags:
                        flags.append(code)
                    stale_fields.append(f"business.{field}")

        # Fulfilment / dropship
        f = fulfilment.get(name)
        fmeta = (f.field_meta or {}) if f is not None else {}
        if f is None or f.inventory_model is None:
            flags.append("CP_UNKNOWN_FULFILMENT_MODEL")
        if f is None or (f.dropship_share_pct is None
                         and (f.inventory_model or "") != "eigen_voorraad"):
            flags.append("CP_UNKNOWN_DROPSHIP_MODEL")

        # Actieve landen
        if not geo.get(name):
            flags.append("CP_UNKNOWN_ACTIVE_COUNTRIES")

        # Financiële data: te oud of conflicterend
        fin = financials.get(name, [])
        known_fin = [r for r in fin if not r.is_unknown]
        if known_fin and all(
                is_stale(r.last_verified_at, "revenue", rules) for r in known_fin):
            flags.append("CP_STALE_FINANCIALS")
            stale_fields.append("financials")
        by_key: dict[tuple, list] = {}
        for r in known_fin:
            by_key.setdefault((r.metric, r.fiscal_year), []).append(r)
        for key, rows in by_key.items():
            if len(rows) < 2:
                continue
            # Conflicterend: ranges van hetzelfde metric/boekjaar overlappen niet
            lo = max((float(r.value_min) for r in rows if r.value_min is not None),
                     default=None)
            hi = min((float(r.value_max) for r in rows if r.value_max is not None),
                     default=None)
            if lo is not None and hi is not None and lo > hi:
                if "CP_CONFLICTING_FINANCIALS" not in flags:
                    flags.append("CP_CONFLICTING_FINANCIALS")

        # Ontbrekende bron & lage confidence (singleton-velden + rij-secties)
        for section, meta in (("business", bmeta), ("fulfilment", fmeta)):
            for field, m in (meta or {}).items():
                m = m or {}
                if m.get("status") == "unknown":
                    continue
                if not m.get("source") and not m.get("evidence_id"):
                    no_source.append(f"{section}.{field}")
                conf = m.get("confidence")
                if conf is not None and conf < LOW_PROFILE_CONFIDENCE:
                    low_conf.append(f"{section}.{field}")
        for section, rows in (("financials", known_fin),
                              ("geography", geo.get(name, [])),
                              ("corporate_relations", relations.get(name, []))):
            for r in rows:
                if r.evidence_id is None and not getattr(r, "source_note", None):
                    no_source.append(f"{section}#{r.id}")
                if r.confidence is not None and r.confidence < LOW_PROFILE_CONFIDENCE:
                    low_conf.append(f"{section}#{r.id}")
        if no_source:
            flags.append("CP_MISSING_PROFILE_SOURCE")
        if low_conf:
            flags.append("CP_LOW_CONFIDENCE_PROFILE")

        # Inconsistente parent-relaties
        rels = relations.get(name, [])
        parents = [r for r in rels if r.relation_type == "parent"]
        ultimates = {r.related_entity for r in rels
                     if r.relation_type == "ultimate_parent"}
        self_rel = any(r.related_entity == name for r in rels)
        if (len({p.related_entity for p in parents}) > 1
                or len(ultimates) > 1 or self_rel):
            flags.append("CP_INCONSISTENT_PARENT_RELATIONS")

        open_recheck = recheck.get(name, 0)
        needs_recheck = bool(
            open_recheck or stale_fields
            or {"CP_CONFLICTING_FINANCIALS", "CP_INCONSISTENT_PARENT_RELATIONS",
                "CP_LOW_CONFIDENCE_PROFILE"} & set(flags))
        out[name] = {
            "flags": flags,
            "stale_fields": stale_fields,
            "low_confidence_fields": low_conf,
            "missing_source_fields": no_source,
            "open_recheck_requests": open_recheck,
            "needs_recheck": needs_recheck,
        }
    return out


def rows_completeness(rows: list, field_type: str, rules: dict[str, int]) -> dict:
    """Completeness/freshness voor rij-gebaseerde secties (financials, rollen,
    landen, relaties): aanwezig = er zijn rijen; unknown-rijen expliciet."""
    known = [r for r in rows if not getattr(r, "is_unknown", False)]
    unknown = [r for r in rows if getattr(r, "is_unknown", False)]
    stale = [r.id for r in known
             if is_stale(getattr(r, "last_verified_at", None), field_type, rules)]
    return {
        "rows": len(rows),
        "known": len(known),
        "unknown_explicit": len(unknown),
        "completeness_pct": 100.0 if known else 0.0,
        "stale_row_ids": stale,
    }
