"""
Semantic-layer-functies voor het concurrentprofiel (taak #249).

Approved, gesloten toegangslaag voor de Commercial AI Copilot tot het
concurrentprofiel: business profile, company size, geografische aanwezigheid,
fulfilment, financiële gezondheid, procurement power, marktrollen, corporate
structuur, evolution-timeline, profielvergelijking, future-threat-signalen
en profieldatakwaliteit.

Conventies (identiek aan semantic_layer.py):
- RBAC via _check_access; shop-scope via _shop_scope (default shop);
- fail-safe: geen data => 'data_available': False, nooit een crash;
- informatielagen: elke waarde draagt zijn information_layer/confidence/bron
  mee zodat schattingen en hypotheses nooit als hard feit worden
  gepresenteerd. Elk resultaat bevat een 'information_layer_note' die het
  model hieraan herinnert.
- NULL-scores betekenen Unknown — nooit 0 (§ CompetitorScoreResult).
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from services import competitor_profile as cp

INFORMATION_LAYER_NOTE = (
    "Informatielagen: 'feit' mag als feit worden gebracht; 'schatting', "
    "'afgeleid_signaal' en 'hypothese' moeten expliciet als zodanig worden "
    "benoemd (nooit als hard feit), inclusief confidence en bron. "
    "NULL/unknown betekent onbekend — nooit nul."
)

# Maximumaantal rijen in lijst-antwoorden richting het model
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _clamp_limit(limit) -> int:
    try:
        return max(1, min(int(limit), MAX_LIMIT))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def _scoped(db: Session, model, sid: int, competitor_name: Optional[str] = None):
    q = db.query(model).filter(model.shop_id == sid)
    if competitor_name:
        q = q.filter(model.competitor_name == competitor_name)
    return q


def _latest_scores(db: Session, sid: int) -> dict[str, models.CompetitorScoreResult]:
    """Meest recente CompetitorScoreResult per concurrent binnen de shop."""
    latest = (db.query(func.max(models.CompetitorScoreResult.run_date))
              .filter(models.CompetitorScoreResult.shop_id == sid).scalar())
    if latest is None:
        return {}
    rows = _scoped(db, models.CompetitorScoreResult, sid).filter(
        models.CompetitorScoreResult.run_date == latest).all()
    return {r.competitor_name: r for r in rows}


def _relevance(db: Session, sid: int) -> dict[str, dict]:
    rows = _scoped(db, models.CompetitorProfile, sid).all()
    return {r.competitor_name: {
        "relevance_label": r.relevance_label,
        "traffic_light": r.traffic_light,
        "top_categories": r.top_categories,
    } for r in rows}


def _meta_field(profile, field: str) -> dict:
    """Waarde + metadata (informatielaag/confidence/bron/status) van één
    singleton-profielveld."""
    m = ((profile.field_meta or {}).get(field) or {}) if profile is not None else {}
    value = getattr(profile, field, None) if profile is not None else None
    return {
        "value": cp._jsonable(value),
        "status": m.get("status") or ("known" if value is not None else "missing"),
        "information_layer": m.get("information_layer"),
        "confidence": m.get("confidence"),
        "source": m.get("source"),
        "evidence_id": m.get("evidence_id"),
        "as_of_date": m.get("as_of_date"),
        "last_verified_at": m.get("last_verified_at"),
    }


def _row_meta(r, extra: list[str]) -> dict:
    base = {
        "information_layer": r.information_layer,
        "confidence": r.confidence,
        "evidence_id": r.evidence_id,
        "last_verified_at": (r.last_verified_at.isoformat()
                             if r.last_verified_at else None),
    }
    for f in extra:
        base[f] = cp._jsonable(getattr(r, f))
    return base


def _base(sid: int, extra: dict) -> dict:
    out = {"shop_id": sid, "shop_scope_applied": True,
           "information_layer_note": INFORMATION_LAYER_NOTE}
    out.update(extra)
    return out


# ─── 1. Business profile ────────────────────────────────────────────────────

def get_competitor_business_profile(db: Session, user, competitor_name: str,
                                    shop_id: Optional[int] = None) -> dict:
    """Volledig bedrijfsprofiel van één concurrent, per veld met
    informatielaag, confidence en bron."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    b = _scoped(db, models.CompetitorBusinessProfile, sid, competitor_name).first()
    if b is None:
        return _base(sid, {"competitor_name": competitor_name,
                           "data_available": False, "fields": {}})
    return _base(sid, {
        "competitor_name": competitor_name,
        "data_available": True,
        "fields": {f: _meta_field(b, f) for f in cp.BUSINESS_FIELDS},
        "last_verified_at": (b.last_verified_at.isoformat()
                             if b.last_verified_at else None),
    })


# ─── 2. Company size ────────────────────────────────────────────────────────

def get_competitor_company_size(db: Session, user,
                                competitor_name: Optional[str] = None,
                                size_class: Optional[str] = None,
                                geographic_scale: Optional[str] = None,
                                limit: int = DEFAULT_LIMIT,
                                shop_id: Optional[int] = None) -> dict:
    """Bedrijfsomvang per concurrent (size class, employee-/revenue-ranges,
    geografische schaal), filterbaar op size class en geografische schaal —
    bv. 'grote internationale concurrenten'."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    scores = _latest_scores(db, sid)
    rel = _relevance(db, sid)
    rows = _scoped(db, models.CompetitorBusinessProfile, sid, competitor_name).all()
    items = []
    for b in rows:
        s = scores.get(b.competitor_name)
        item = {
            "competitor_name": b.competitor_name,
            "size_class": _meta_field(b, "size_class"),
            "employee_range": {
                "min": b.employee_range_min, "max": b.employee_range_max,
                **{k: v for k, v in _meta_field(b, "employee_range_min").items()
                   if k not in ("value",)},
            },
            "revenue_range": {
                "min": cp._jsonable(b.revenue_range_min),
                "max": cp._jsonable(b.revenue_range_max),
                "currency": b.revenue_currency,
                **{k: v for k, v in _meta_field(b, "revenue_range_min").items()
                   if k not in ("value",)},
            },
            "geographic_scale": _meta_field(b, "geographic_scale"),
            "score_classification": {
                "company_size_class": s.company_size_class if s else None,
                "company_size_confidence": s.company_size_confidence if s else None,
                "geographic_scale_class": s.geographic_scale_class if s else None,
                "geographic_scale_confidence": s.geographic_scale_confidence if s else None,
            },
            **(rel.get(b.competitor_name) or {}),
        }
        if size_class:
            effective = b.size_class or (s.company_size_class if s else None)
            if (effective or "").lower() != size_class.lower():
                continue
        if geographic_scale:
            effective = b.geographic_scale or (s.geographic_scale_class if s else None)
            if (effective or "").lower() != geographic_scale.lower():
                continue
        items.append(item)
    items = items[:limit]
    return _base(sid, {"data_available": len(items) > 0, "records": len(items),
                       "filters": {"size_class": size_class,
                                   "geographic_scale": geographic_scale},
                       "items": items})


# ─── 3. Geografische aanwezigheid ───────────────────────────────────────────

def get_competitor_geographic_presence(db: Session, user,
                                       competitor_name: Optional[str] = None,
                                       country_code: Optional[str] = None,
                                       limit: int = DEFAULT_LIMIT,
                                       shop_id: Optional[int] = None) -> dict:
    """Actieve landen per concurrent (webshop/operationeel), met
    informatielaag en confidence per land."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    q = _scoped(db, models.CompetitorGeographicPresence, sid, competitor_name).filter(
        models.CompetitorGeographicPresence.valid_to.is_(None))
    if country_code:
        q = q.filter(func.upper(models.CompetitorGeographicPresence.country_code)
                     == country_code.upper())
    rows = q.all()
    per_comp: dict[str, list] = {}
    for r in rows:
        per_comp.setdefault(r.competitor_name, []).append(
            _row_meta(r, ["country_code", "presence_type", "valid_from"]))
    items = [{"competitor_name": n, "countries": c}
             for n, c in sorted(per_comp.items())][:limit]
    return _base(sid, {"data_available": len(items) > 0, "records": len(items),
                       "items": items})


# ─── 4. Fulfilment / dropship ───────────────────────────────────────────────

def get_competitor_fulfilment_profile(db: Session, user,
                                      competitor_name: Optional[str] = None,
                                      dropship_only: bool = False,
                                      limit: int = DEFAULT_LIMIT,
                                      shop_id: Optional[int] = None) -> dict:
    """Fulfilmentprofiel per concurrent (voorraadmodel, dropship-aandeel,
    levertijden, marketplace-rol). Met dropship_only=true alleen concurrenten
    met een (deels) dropship-model — 'welke relevante concurrenten zijn
    dropshipspelers?'."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    scores = _latest_scores(db, sid)
    rel = _relevance(db, sid)
    rows = _scoped(db, models.CompetitorFulfilmentProfile, sid, competitor_name).all()
    items = []
    for f in rows:
        s = scores.get(f.competitor_name)
        model_class = s.fulfilment_model_class if s else None
        is_dropship = (
            (f.inventory_model or "").startswith("dropship")
            or (f.inventory_model == "hybride" and (f.dropship_share_pct or 0) > 0)
            or (f.dropship_share_pct or 0) >= 50
            or (model_class or "") == "dropship")
        if dropship_only and not is_dropship:
            continue
        items.append({
            "competitor_name": f.competitor_name,
            "fields": {fl: _meta_field(f, fl) for fl in cp.FULFILMENT_FIELDS},
            "is_dropship_player": is_dropship,
            "score_classification": {
                "fulfilment_model_class": model_class,
                "fulfilment_model_confidence": s.fulfilment_model_confidence if s else None,
            },
            **(rel.get(f.competitor_name) or {}),
        })
    items = items[:limit]
    return _base(sid, {"data_available": len(items) > 0, "records": len(items),
                       "dropship_only": dropship_only, "items": items})


# ─── 5. Financiële gezondheid ───────────────────────────────────────────────

def get_competitor_financial_health(db: Session, user,
                                    competitor_name: Optional[str] = None,
                                    limit: int = DEFAULT_LIMIT,
                                    shop_id: Optional[int] = None) -> dict:
    """Financiële gezondheid per concurrent: score/status uit de laatste
    scoringsrun plus de onderliggende financiële observaties (met boekjaar,
    informatielaag, confidence en bron). Bevat ook de relevantie voor ons —
    'financieel sterk maar weinig relevant' is daarmee direct te beantwoorden."""
    from semantic_layer import _check_access, _shop_scope, ANALYST_UP
    _check_access(user, ANALYST_UP)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    scores = _latest_scores(db, sid)
    rel = _relevance(db, sid)
    fin_rows = _scoped(db, models.CompetitorFinancialObservation, sid,
                       competitor_name).all()
    fin: dict[str, list] = {}
    for r in fin_rows:
        fin.setdefault(r.competitor_name, []).append(
            _row_meta(r, ["fiscal_year", "metric", "value_min", "value_max",
                          "currency", "is_unknown", "source_note", "as_of_date"]))
    names = set(fin) | set(scores)
    if competitor_name:
        names &= {competitor_name}
    items = []
    for n in sorted(names):
        s = scores.get(n)
        items.append({
            "competitor_name": n,
            "financial_health_score": s.financial_health_score if s else None,
            "financial_health_status": (s.financial_health_status if s else None) or "unknown",
            "financial_data_confidence": s.financial_data_confidence if s else None,
            "observations": fin.get(n, []),
            **(rel.get(n) or {}),
        })
    items.sort(key=lambda i: (i["financial_health_score"] is None,
                              -(i["financial_health_score"] or 0)))
    items = items[:limit]
    return _base(sid, {"data_available": len(items) > 0, "records": len(items),
                       "items": items})


# ─── 6. Procurement power ───────────────────────────────────────────────────

def get_competitor_procurement_power(db: Session, user,
                                     limit: int = DEFAULT_LIMIT,
                                     shop_id: Optional[int] = None) -> dict:
    """Procurement Power-ranking van concurrenten (laatste scoringsrun).
    NULL = Unknown, die concurrenten staan onderaan met een expliciete
    unknown-markering."""
    from semantic_layer import _check_access, _shop_scope, ANALYST_UP
    _check_access(user, ANALYST_UP)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    scores = _latest_scores(db, sid)
    rel = _relevance(db, sid)
    ranked = sorted(scores.values(),
                    key=lambda s: (s.procurement_power_score is None,
                                   -(s.procurement_power_score or 0)))
    items = [{
        "rank": i + 1,
        "competitor_name": s.competitor_name,
        "procurement_power_score": s.procurement_power_score,
        "score_is_unknown": s.procurement_power_score is None,
        "data_completeness_pct": s.data_completeness_pct,
        "run_date": str(s.run_date),
        **(rel.get(s.competitor_name) or {}),
    } for i, s in enumerate(ranked[:limit])]
    return _base(sid, {"data_available": len(items) > 0, "records": len(items),
                       "items": items})


# ─── 7. Marktrollen ─────────────────────────────────────────────────────────

def get_competitor_market_roles(db: Session, user,
                                competitor_name: Optional[str] = None,
                                role: Optional[str] = None,
                                limit: int = DEFAULT_LIMIT,
                                shop_id: Optional[int] = None) -> dict:
    """Actieve marktrollen (Competition DNA) per concurrent, filterbaar op
    rol; met informatielaag, confidence en menselijke validatiestatus."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    q = _scoped(db, models.CompetitorMarketRole, sid, competitor_name).filter(
        models.CompetitorMarketRole.valid_to.is_(None))
    if role:
        q = q.filter(func.lower(models.CompetitorMarketRole.role) == role.lower())
    per_comp: dict[str, list] = {}
    for r in q.all():
        per_comp.setdefault(r.competitor_name, []).append(
            _row_meta(r, ["role", "ai_assigned", "human_validated", "valid_from"]))
    items = [{"competitor_name": n, "roles": rs}
             for n, rs in sorted(per_comp.items())][:limit]
    return _base(sid, {"data_available": len(items) > 0, "records": len(items),
                       "role_filter": role, "items": items})


# ─── 8. Corporate structuur / groepen ───────────────────────────────────────

def get_competitor_corporate_structure(db: Session, user,
                                       competitor_name: Optional[str] = None,
                                       limit: int = DEFAULT_LIMIT,
                                       shop_id: Optional[int] = None) -> dict:
    """Corporate relaties per concurrent (parent/ultimate_parent/subsidiary/
    sister) plus groepsvorming: concurrenten die (indirect) dezelfde
    (ultimate) parent delen — 'welke concurrenten zijn onderdeel van
    dezelfde groep?'. Land van een parent is informatief en nooit basis voor
    afgeleide claims."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    rows = _scoped(db, models.CompetitorCorporateRelation, sid).filter(
        models.CompetitorCorporateRelation.valid_to.is_(None)).all()
    per_comp: dict[str, list] = {}
    groups: dict[str, set] = {}
    for r in rows:
        per_comp.setdefault(r.competitor_name, []).append(
            _row_meta(r, ["relation_type", "related_entity", "related_country",
                          "valid_from"]))
        if r.relation_type in ("parent", "ultimate_parent"):
            groups.setdefault(r.related_entity, set()).add(r.competitor_name)
    if competitor_name:
        per_comp = {competitor_name: per_comp.get(competitor_name, [])}
    items = [{"competitor_name": n, "relations": rs}
             for n, rs in sorted(per_comp.items()) if rs][:limit]
    shared = [{"group_parent": parent, "competitors": sorted(members)}
              for parent, members in sorted(groups.items()) if len(members) > 1]
    if competitor_name:
        shared = [g for g in shared if competitor_name in g["competitors"]]
    return _base(sid, {"data_available": bool(items or shared),
                       "records": len(items), "items": items,
                       "shared_groups": shared})


# ─── 9. Evolution timeline ──────────────────────────────────────────────────

def get_competitor_evolution(db: Session, user, competitor_name: str,
                             days: int = 365, limit: int = 50,
                             shop_id: Optional[int] = None) -> dict:
    """Evolution-timeline van één concurrent: welke profielvelden zijn
    wanneer en door wie/welke bron gewijzigd."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    since = datetime.utcnow() - timedelta(days=max(1, min(int(days), 3650)))
    rows = (_scoped(db, models.CompetitorEvolutionEvent, sid, competitor_name)
            .filter(models.CompetitorEvolutionEvent.occurred_at >= since)
            .order_by(models.CompetitorEvolutionEvent.occurred_at.desc(),
                      models.CompetitorEvolutionEvent.id.desc())
            .limit(limit).all())
    items = [{
        "section": r.section, "field_name": r.field_name,
        "event_type": r.event_type, "old_value": r.old_value,
        "new_value": r.new_value, "change_source": r.change_source,
        "evidence_id": r.evidence_id,
        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
    } for r in rows]
    return _base(sid, {"competitor_name": competitor_name,
                       "period_days": days,
                       "data_available": len(items) > 0,
                       "records": len(items), "events": items})


# ─── 10. Profielvergelijking ────────────────────────────────────────────────

def compare_competitor_profiles(db: Session, user, competitor_names: list,
                                shop_id: Optional[int] = None) -> dict:
    """Vergelijk 2–5 concurrenten zij-aan-zij op omvang, fulfilment,
    financiële gezondheid, procurement power, future threat, marktrollen en
    relevantie. Onbekende waarden blijven expliciet unknown."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    names = [str(n) for n in (competitor_names or [])][:5]
    if len(names) < 2:
        return _base(sid, {"data_available": False,
                           "error": "Geef minimaal 2 concurrentnamen op.",
                           "items": []})
    scores = _latest_scores(db, sid)
    rel = _relevance(db, sid)
    items = []
    for n in names:
        b = _scoped(db, models.CompetitorBusinessProfile, sid, n).first()
        f = _scoped(db, models.CompetitorFulfilmentProfile, sid, n).first()
        roles = _scoped(db, models.CompetitorMarketRole, sid, n).filter(
            models.CompetitorMarketRole.valid_to.is_(None)).all()
        geo = _scoped(db, models.CompetitorGeographicPresence, sid, n).filter(
            models.CompetitorGeographicPresence.valid_to.is_(None)).all()
        s = scores.get(n)
        items.append({
            "competitor_name": n,
            "profile_found": b is not None or f is not None or s is not None,
            "size_class": _meta_field(b, "size_class"),
            "geographic_scale": _meta_field(b, "geographic_scale"),
            "ownership_type": _meta_field(b, "ownership_type"),
            "inventory_model": _meta_field(f, "inventory_model"),
            "dropship_share_pct": _meta_field(f, "dropship_share_pct"),
            "active_countries": sorted({g.country_code for g in geo}),
            "market_roles": [r.role for r in roles],
            "scores": {
                "financial_health_score": s.financial_health_score if s else None,
                "financial_health_status": (s.financial_health_status if s else None) or "unknown",
                "procurement_power_score": s.procurement_power_score if s else None,
                "future_threat_score": s.future_threat_score if s else None,
                "business_strength_score": s.business_strength_score if s else None,
                "data_completeness_pct": s.data_completeness_pct if s else None,
            },
            **(rel.get(n) or {}),
        })
    available = any(i["profile_found"] for i in items)
    return _base(sid, {"data_available": available, "records": len(items),
                       "items": items})


# ─── 11. Future-threat-signalen ─────────────────────────────────────────────

def get_competitor_future_threats(db: Session, user,
                                  limit: int = DEFAULT_LIMIT,
                                  shop_id: Optional[int] = None) -> dict:
    """Future-threat-ranking van concurrenten (laatste scoringsrun) met de
    onderliggende factoren uit de score-details. Threat-scores zijn
    afgeleide signalen — geen feiten."""
    from semantic_layer import _check_access, _shop_scope, ANALYST_UP
    _check_access(user, ANALYST_UP)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    scores = _latest_scores(db, sid)
    rel = _relevance(db, sid)
    ranked = sorted(scores.values(),
                    key=lambda s: (s.future_threat_score is None,
                                   -(s.future_threat_score or 0)))
    items = [{
        "rank": i + 1,
        "competitor_name": s.competitor_name,
        "future_threat_score": s.future_threat_score,
        "score_is_unknown": s.future_threat_score is None,
        "factors": (s.details or {}).get("future_threat"),
        "data_completeness_pct": s.data_completeness_pct,
        "run_date": str(s.run_date),
        **(rel.get(s.competitor_name) or {}),
    } for i, s in enumerate(ranked[:limit])]
    return _base(sid, {"data_available": len(items) > 0, "records": len(items),
                       "information_layer": "afgeleid_signaal",
                       "items": items})


# ─── 12. Profieldatakwaliteit / heronderzoek ────────────────────────────────

def get_competitor_profile_quality(db: Session, user,
                                   competitor_name: Optional[str] = None,
                                   needs_recheck_only: bool = False,
                                   limit: int = DEFAULT_LIMIT,
                                   shop_id: Optional[int] = None) -> dict:
    """Hoe betrouwbaar is onze profielinformatie per concurrent, en welke
    profielen moeten opnieuw worden gecontroleerd? Combineert de Competition
    Data Quality-vlaggen (zelfde definities als de DQ-scan), freshness,
    lage confidence, ontbrekende bronnen en openstaande
    heronderzoek-verzoeken uit de validatie-workflow."""
    from semantic_layer import _check_access, _shop_scope, ALL_ROLES
    _check_access(user, ALL_ROLES)
    sid = _shop_scope(db, shop_id)
    limit = _clamp_limit(limit)
    flags = cp.profile_quality_flags(db, sid, competitor_name)
    rules = cp.get_freshness_rules(db, sid)

    # Open CP_*-issues uit het centrale DQ-register als context.
    open_dq = [{
        "issue_code": r.issue_code, "title": r.title, "severity": r.severity,
        "affected_count": r.affected_count, "status": r.status,
    } for r in db.query(models.DataQualityIssue).filter(
        models.DataQualityIssue.issue_code.like("CP_%"),
        models.DataQualityIssue.status != "opgelost").all()]

    items = []
    for name, info in flags.items():
        if needs_recheck_only and not info["needs_recheck"]:
            continue
        issue_count = len(info["flags"])
        reliability = ("hoog" if issue_count == 0 else
                       "middel" if issue_count <= 3 and not info["needs_recheck"]
                       else "laag")
        items.append({
            "competitor_name": name,
            "reliability": reliability,
            "needs_recheck": info["needs_recheck"],
            "quality_flags": info["flags"],
            "stale_fields": info["stale_fields"],
            "low_confidence_fields": info["low_confidence_fields"],
            "missing_source_fields": info["missing_source_fields"],
            "open_recheck_requests": info["open_recheck_requests"],
        })
    items.sort(key=lambda i: (not i["needs_recheck"], -len(i["quality_flags"]),
                              i["competitor_name"]))
    items = items[:limit]
    return _base(sid, {
        "data_available": len(items) > 0,
        "records": len(items),
        "needs_recheck_only": needs_recheck_only,
        "freshness_rules_days": rules,
        "open_data_quality_issues": open_dq,
        "items": items,
    })
