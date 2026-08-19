"""
Concurrentprofiel-API (taak #246): shop-gescopede CRUD-/lees-endpoints voor
het bedrijfsprofiel per concurrent — business profile, fulfilment profile,
financiële observaties, marktrollen (Competition DNA), geografische
aanwezigheid, corporate relaties, evidence, validatie-workflow,
evolution-timeline en freshness-regels.

Alle endpoints koppelen aan de bestaande concurrent-identiteit per shop
(CompetitorProfile / competitor_name); een concurrent van een andere shop
geeft 404 (IDOR-veilig).
"""
from typing import Optional
from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
import models
import auth as auth_utils
from services import competitor_profile as cp

router = APIRouter(prefix="/api/competition/competitor-profile",
                   tags=["competitor-profile"])

WRITE_ROLES = ("admin", "pricing_manager", "analyst")


def _scope(db: Session, shop_id: Optional[int]) -> int:
    from semantic_layer import _shop_scope
    return _shop_scope(db, shop_id)


def _require_competitor(db: Session, sid: int, name: str) -> None:
    """Bestaat deze concurrent binnen deze shop? Anders 404 (geen tweede
    concurrententabel: identiteit = CompetitorProfile of prijsdata)."""
    exists = (
        db.query(models.CompetitorProfile.id)
        .filter(models.CompetitorProfile.shop_id == sid,
                models.CompetitorProfile.competitor_name == name)
        .first()
        or db.query(models.FactCompetitorPriceDaily.id)
        .filter(models.FactCompetitorPriceDaily.shop_id == sid,
                models.FactCompetitorPriceDaily.competitor_name == name)
        .first()
    )
    if not exists:
        raise HTTPException(404, "Concurrent niet gevonden voor deze winkel")


def _parse_date(v):
    if v in (None, ""):
        return None
    return date.fromisoformat(v) if isinstance(v, str) else v


def _evidence_out(e: models.CompetitionEvidence) -> dict:
    return {
        "id": e.id, "competitor_name": e.competitor_name,
        "source_url": e.source_url, "source_type": e.source_type,
        "source_priority": e.source_priority, "title": e.title,
        "observed_date": e.observed_date.isoformat() if e.observed_date else None,
        "fetched_date": e.fetched_date.isoformat() if e.fetched_date else None,
        "reliability": e.reliability, "status": e.status,
        "confidence": e.confidence, "extracted_fact": e.extracted_fact,
        "human_validated": e.human_validated,
        "review_due_date": e.review_due_date.isoformat() if e.review_due_date else None,
        "created_by": e.created_by,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _singleton_out(profile, fields: list[str]) -> Optional[dict]:
    if profile is None:
        return None
    out = {f: cp._jsonable(getattr(profile, f)) for f in fields}
    out["field_meta"] = profile.field_meta or {}
    out["last_verified_at"] = (profile.last_verified_at.isoformat()
                               if profile.last_verified_at else None)
    return out


def _row_out(r, extra: list[str]) -> dict:
    base = {
        "id": r.id,
        "information_layer": r.information_layer,
        "confidence": r.confidence,
        "evidence_id": r.evidence_id,
        "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
    }
    for f in extra:
        v = getattr(r, f)
        base[f] = v.isoformat() if isinstance(v, (date, datetime)) else cp._jsonable(v)
    return base


# ── Evidence ─────────────────────────────────────────────────────────────────

@router.post("/{competitor_name}/evidence", status_code=201)
def create_evidence(
    competitor_name: str,
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    source_type = payload.get("source_type")
    if not source_type:
        raise HTTPException(400, "source_type is verplicht")
    ev = models.CompetitionEvidence(
        shop_id=sid, competitor_name=competitor_name,
        source_url=payload.get("source_url"),
        source_type=source_type,
        source_priority=cp.source_priority(source_type),
        title=payload.get("title"),
        observed_date=_parse_date(payload.get("observed_date")),
        fetched_date=_parse_date(payload.get("fetched_date")) or date.today(),
        reliability=payload.get("reliability", "medium"),
        confidence=payload.get("confidence", 0.5),
        extracted_fact=payload.get("extracted_fact"),
        human_validated=bool(payload.get("human_validated", False)),
        review_due_date=_parse_date(payload.get("review_due_date")),
        created_by=current_user.username,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return _evidence_out(ev)


@router.get("/{competitor_name}/evidence")
def list_evidence(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    q = db.query(models.CompetitionEvidence).filter(
        models.CompetitionEvidence.shop_id == sid,
        models.CompetitionEvidence.competitor_name == competitor_name)
    if status:
        q = q.filter(models.CompetitionEvidence.status == status)
    items = q.order_by(models.CompetitionEvidence.created_at.desc()).all()
    return {"items": [_evidence_out(e) for e in items], "total": len(items)}


# ── Singleton-secties: business & fulfilment ─────────────────────────────────

def _upsert_singleton(db, model, sid, name):
    row = db.query(model).filter(model.shop_id == sid,
                                 model.competitor_name == name).first()
    if row is None:
        row = model(shop_id=sid, competitor_name=name)
        db.add(row)
        db.flush()
    return row


@router.put("/{competitor_name}/business")
def update_business_profile(
    competitor_name: str,
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    profile = _upsert_singleton(db, models.CompetitorBusinessProfile, sid, competitor_name)
    try:
        changed = cp.apply_profile_update(
            db, profile, cp.BUSINESS_FIELDS, payload, shop_id=sid,
            competitor_name=competitor_name, section="business",
            changed_by=current_user.username,
            change_source=payload.get("change_source", "handmatig"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"status": "ok", "changed_fields": changed,
            "business": _singleton_out(profile, cp.BUSINESS_FIELDS)}


@router.put("/{competitor_name}/fulfilment")
def update_fulfilment_profile(
    competitor_name: str,
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    profile = _upsert_singleton(db, models.CompetitorFulfilmentProfile, sid, competitor_name)
    try:
        changed = cp.apply_profile_update(
            db, profile, cp.FULFILMENT_FIELDS, payload, shop_id=sid,
            competitor_name=competitor_name, section="fulfilment",
            changed_by=current_user.username,
            change_source=payload.get("change_source", "handmatig"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"status": "ok", "changed_fields": changed,
            "fulfilment": _singleton_out(profile, cp.FULFILMENT_FIELDS)}


# ── Financiële observaties ───────────────────────────────────────────────────

@router.post("/{competitor_name}/financials", status_code=201)
def add_financial_observation(
    competitor_name: str,
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    layer = payload.get("information_layer", "schatting")
    confidence = payload.get("confidence", 0.5)
    is_unknown = bool(payload.get("is_unknown", False))
    try:
        cp.validate_information_layer(layer)
        evidence = cp.resolve_evidence(db, sid, competitor_name,
                                       payload.get("evidence_id"))
        if not is_unknown:
            cp.check_financial_evidence_guard(
                information_layer=layer, confidence=confidence,
                evidence=evidence)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if payload.get("fiscal_year") is None or not payload.get("metric"):
        raise HTTPException(400, "fiscal_year en metric zijn verplicht")
    row = models.CompetitorFinancialObservation(
        shop_id=sid, competitor_name=competitor_name,
        fiscal_year=int(payload["fiscal_year"]), metric=payload["metric"],
        value_min=None if is_unknown else payload.get("value_min"),
        value_max=None if is_unknown else payload.get("value_max"),
        currency=payload.get("currency"),
        is_unknown=is_unknown,
        information_layer=layer, confidence=confidence,
        evidence_id=payload.get("evidence_id"),
        source_note=payload.get("source_note"),
        as_of_date=_parse_date(payload.get("as_of_date")),
    )
    db.add(row)
    cp.record_event(db, sid, competitor_name, section="financials",
                    field_name=f"{payload['metric']}:{payload['fiscal_year']}",
                    event_type="created",
                    new_value=("unknown" if is_unknown else {
                        "value_min": cp._jsonable(payload.get("value_min")),
                        "value_max": cp._jsonable(payload.get("value_max")),
                        "currency": payload.get("currency")}),
                    changed_by=current_user.username,
                    evidence_id=payload.get("evidence_id"))
    db.commit()
    db.refresh(row)
    return _row_out(row, ["fiscal_year", "metric", "value_min", "value_max",
                          "currency", "is_unknown", "source_note", "as_of_date"])


@router.get("/{competitor_name}/financials")
def list_financial_observations(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    rows = (db.query(models.CompetitorFinancialObservation)
            .filter(models.CompetitorFinancialObservation.shop_id == sid,
                    models.CompetitorFinancialObservation.competitor_name == competitor_name)
            .order_by(models.CompetitorFinancialObservation.fiscal_year.desc())
            .all())
    return {"items": [_row_out(r, ["fiscal_year", "metric", "value_min",
                                   "value_max", "currency", "is_unknown",
                                   "source_note", "as_of_date"]) for r in rows],
            "total": len(rows)}


# ── Marktrollen (Competition DNA) ───────────────────────────────────────────

@router.post("/{competitor_name}/roles", status_code=201)
def add_market_role(
    competitor_name: str,
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    if not payload.get("role"):
        raise HTTPException(400, "role is verplicht")
    layer = payload.get("information_layer", "afgeleid_signaal")
    try:
        cp.validate_information_layer(layer)
        cp.resolve_evidence(db, sid, competitor_name, payload.get("evidence_id"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    row = models.CompetitorMarketRole(
        shop_id=sid, competitor_name=competitor_name, role=payload["role"],
        information_layer=layer,
        confidence=payload.get("confidence", 0.5),
        evidence_id=payload.get("evidence_id"),
        ai_assigned=bool(payload.get("ai_assigned", False)),
        human_validated=bool(payload.get("human_validated", False)),
        valid_from=_parse_date(payload.get("valid_from")) or date.today(),
        valid_to=_parse_date(payload.get("valid_to")),
    )
    db.add(row)
    cp.record_event(db, sid, competitor_name, section="roles",
                    field_name=payload["role"], event_type="created",
                    new_value={"role": payload["role"],
                               "ai_assigned": row.ai_assigned},
                    change_source="ai" if row.ai_assigned else "handmatig",
                    changed_by=current_user.username,
                    evidence_id=payload.get("evidence_id"))
    db.commit()
    db.refresh(row)
    return _row_out(row, ["role", "ai_assigned", "human_validated",
                          "valid_from", "valid_to"])


@router.delete("/{competitor_name}/roles/{role_id}")
def end_market_role(
    competitor_name: str,
    role_id: int,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    """Beëindig een rol (valid_to = vandaag) — historie blijft bewaard."""
    sid = _scope(db, shop_id)
    row = db.query(models.CompetitorMarketRole).filter(
        models.CompetitorMarketRole.id == role_id,
        models.CompetitorMarketRole.shop_id == sid,
        models.CompetitorMarketRole.competitor_name == competitor_name).first()
    if not row:
        raise HTTPException(404, "Rol niet gevonden voor deze winkel")
    row.valid_to = date.today()
    cp.record_event(db, sid, competitor_name, section="roles",
                    field_name=row.role, event_type="removed",
                    old_value={"role": row.role},
                    changed_by=current_user.username)
    db.commit()
    return {"status": "beeindigd", "id": row.id,
            "valid_to": row.valid_to.isoformat()}


@router.get("/{competitor_name}/roles")
def list_market_roles(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    q = db.query(models.CompetitorMarketRole).filter(
        models.CompetitorMarketRole.shop_id == sid,
        models.CompetitorMarketRole.competitor_name == competitor_name)
    if active_only:
        q = q.filter(models.CompetitorMarketRole.valid_to == None)  # noqa: E711
    rows = q.order_by(models.CompetitorMarketRole.created_at.desc()).all()
    return {"items": [_row_out(r, ["role", "ai_assigned", "human_validated",
                                   "valid_from", "valid_to"]) for r in rows],
            "total": len(rows)}


# ── Geografische aanwezigheid ────────────────────────────────────────────────

@router.post("/{competitor_name}/geography", status_code=201)
def add_geographic_presence(
    competitor_name: str,
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    country = (payload.get("country_code") or "").upper()
    presence_type = payload.get("presence_type")
    if len(country) != 2 or presence_type not in ("webshop", "operationeel"):
        raise HTTPException(400, "country_code (ISO-2) en presence_type "
                                 "(webshop|operationeel) zijn verplicht")
    layer = payload.get("information_layer", "feit")
    try:
        cp.validate_information_layer(layer)
        cp.resolve_evidence(db, sid, competitor_name, payload.get("evidence_id"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    row = models.CompetitorGeographicPresence(
        shop_id=sid, competitor_name=competitor_name,
        country_code=country, presence_type=presence_type,
        information_layer=layer, confidence=payload.get("confidence", 0.5),
        evidence_id=payload.get("evidence_id"),
        valid_from=_parse_date(payload.get("valid_from")) or date.today(),
        valid_to=_parse_date(payload.get("valid_to")),
    )
    db.add(row)
    cp.record_event(db, sid, competitor_name, section="geography",
                    field_name=country, event_type="created",
                    new_value={"country": country, "presence_type": presence_type},
                    changed_by=current_user.username,
                    evidence_id=payload.get("evidence_id"))
    db.commit()
    db.refresh(row)
    return _row_out(row, ["country_code", "presence_type", "valid_from", "valid_to"])


@router.get("/{competitor_name}/geography")
def list_geographic_presence(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    q = db.query(models.CompetitorGeographicPresence).filter(
        models.CompetitorGeographicPresence.shop_id == sid,
        models.CompetitorGeographicPresence.competitor_name == competitor_name)
    if active_only:
        q = q.filter(models.CompetitorGeographicPresence.valid_to == None)  # noqa: E711
    rows = q.order_by(models.CompetitorGeographicPresence.country_code).all()
    return {"items": [_row_out(r, ["country_code", "presence_type",
                                   "valid_from", "valid_to"]) for r in rows],
            "total": len(rows)}


# ── Corporate relaties ───────────────────────────────────────────────────────

@router.post("/{competitor_name}/relations", status_code=201)
def add_corporate_relation(
    competitor_name: str,
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    rtype = payload.get("relation_type")
    if rtype not in ("parent", "ultimate_parent", "subsidiary", "sister"):
        raise HTTPException(400, "relation_type moet parent|ultimate_parent|subsidiary|sister zijn")
    if not payload.get("related_entity"):
        raise HTTPException(400, "related_entity is verplicht")
    layer = payload.get("information_layer", "feit")
    try:
        cp.validate_information_layer(layer)
        cp.resolve_evidence(db, sid, competitor_name, payload.get("evidence_id"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    row = models.CompetitorCorporateRelation(
        shop_id=sid, competitor_name=competitor_name,
        relation_type=rtype, related_entity=payload["related_entity"],
        related_country=(payload.get("related_country") or None),
        information_layer=layer, confidence=payload.get("confidence", 0.5),
        evidence_id=payload.get("evidence_id"),
        valid_from=_parse_date(payload.get("valid_from")) or date.today(),
        valid_to=_parse_date(payload.get("valid_to")),
    )
    db.add(row)
    cp.record_event(db, sid, competitor_name, section="relations",
                    field_name=rtype, event_type="created",
                    new_value={"relation_type": rtype,
                               "related_entity": payload["related_entity"]},
                    changed_by=current_user.username,
                    evidence_id=payload.get("evidence_id"))
    db.commit()
    db.refresh(row)
    return _row_out(row, ["relation_type", "related_entity", "related_country",
                          "valid_from", "valid_to"])


@router.get("/{competitor_name}/relations")
def list_corporate_relations(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    rows = (db.query(models.CompetitorCorporateRelation)
            .filter(models.CompetitorCorporateRelation.shop_id == sid,
                    models.CompetitorCorporateRelation.competitor_name == competitor_name)
            .order_by(models.CompetitorCorporateRelation.created_at.desc()).all())
    return {"items": [_row_out(r, ["relation_type", "related_entity",
                                   "related_country", "valid_from", "valid_to"])
                      for r in rows],
            "total": len(rows)}


# ── Validatie-workflow ───────────────────────────────────────────────────────

VALID_ACTIONS = ("bevestigen", "corrigeren", "blokkeren", "unknown", "heronderzoek")
SECTION_MODELS = {
    "business": ("CompetitorBusinessProfile", "BUSINESS_FIELDS"),
    "fulfilment": ("CompetitorFulfilmentProfile", "FULFILMENT_FIELDS"),
}


@router.post("/{competitor_name}/validate", status_code=201)
def validate_field(
    competitor_name: str,
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*WRITE_ROLES)),
):
    """
    Handmatige validatie door Category Manager / Competition Analyst:
    bevestigen / corrigeren / blokkeren / unknown / heronderzoek.
    AI-waarde én menselijke waarde blijven beide bewaard; de menselijke
    correctie wint operationeel (wordt de actuele profielwaarde).
    """
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    section = payload.get("section")
    field = payload.get("field_name")
    action = payload.get("action")
    if action not in VALID_ACTIONS:
        raise HTTPException(400, f"action moet één van {VALID_ACTIONS} zijn")
    if section not in SECTION_MODELS or not field:
        raise HTTPException(400, "section (business|fulfilment) en field_name zijn verplicht")
    model_name, fields_name = SECTION_MODELS[section]
    model = getattr(models, model_name)
    fields = getattr(cp, fields_name)
    if field not in fields:
        raise HTTPException(400, f"Onbekend veld '{field}' voor sectie {section}")

    profile = _upsert_singleton(db, model, sid, competitor_name)
    current_value = getattr(profile, field)
    meta = dict(profile.field_meta or {})
    fmeta = dict(meta.get(field) or {})

    # Vorige beoordelingen op niet-actueel zetten
    db.query(models.CompetitorFieldValidation).filter(
        models.CompetitorFieldValidation.shop_id == sid,
        models.CompetitorFieldValidation.competitor_name == competitor_name,
        models.CompetitorFieldValidation.section == section,
        models.CompetitorFieldValidation.field_name == field,
        models.CompetitorFieldValidation.is_current == True,  # noqa: E712
    ).update({"is_current": False}, synchronize_session=False)

    human_value = payload.get("human_value")
    validation = models.CompetitorFieldValidation(
        shop_id=sid, competitor_name=competitor_name, section=section,
        field_name=field, action=action,
        ai_value=cp._jsonable(current_value),
        human_value=cp._jsonable(human_value) if action == "corrigeren" else None,
        reason=payload.get("reason"),
        reviewer=current_user.username, is_current=True)
    db.add(validation)

    now = datetime.utcnow()
    if action == "bevestigen":
        fmeta.update({"status": "known", "human_validated": True,
                      "last_verified_at": now.isoformat()})
        profile.last_verified_at = now
    elif action == "corrigeren":
        if human_value is None:
            raise HTTPException(400, "human_value is verplicht bij corrigeren")
        setattr(profile, field, human_value)
        fmeta.update({"status": "known", "human_validated": True,
                      "information_layer": "feit",
                      "last_verified_at": now.isoformat()})
        profile.last_verified_at = now
    elif action == "blokkeren":
        fmeta.update({"status": "blocked", "human_validated": True})
    elif action == "unknown":
        setattr(profile, field, None)
        fmeta.update({"status": "unknown", "human_validated": True,
                      "last_verified_at": now.isoformat()})
    elif action == "heronderzoek":
        fmeta.update({"status": "needs_review"})

    meta[field] = fmeta
    profile.field_meta = meta

    cp.record_event(db, sid, competitor_name, section=section,
                    field_name=field, event_type="validated",
                    old_value=cp._jsonable(current_value),
                    new_value={"action": action,
                               "human_value": cp._jsonable(human_value)},
                    changed_by=current_user.username)
    db.commit()
    db.refresh(validation)
    return {
        "id": validation.id, "action": action, "section": section,
        "field_name": field, "ai_value": validation.ai_value,
        "human_value": validation.human_value, "reason": validation.reason,
        "reviewer": validation.reviewer,
        "created_at": validation.created_at.isoformat(),
    }


@router.get("/{competitor_name}/validations")
def list_validations(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    section: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    q = db.query(models.CompetitorFieldValidation).filter(
        models.CompetitorFieldValidation.shop_id == sid,
        models.CompetitorFieldValidation.competitor_name == competitor_name)
    if section:
        q = q.filter(models.CompetitorFieldValidation.section == section)
    rows = q.order_by(models.CompetitorFieldValidation.created_at.desc()).all()
    return {"items": [{
        "id": r.id, "section": r.section, "field_name": r.field_name,
        "action": r.action, "ai_value": r.ai_value, "human_value": r.human_value,
        "reason": r.reason, "reviewer": r.reviewer, "is_current": r.is_current,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows], "total": len(rows)}


# ── Timeline ─────────────────────────────────────────────────────────────────

@router.get("/{competitor_name}/timeline")
def get_evolution_timeline(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    section: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    q = db.query(models.CompetitorEvolutionEvent).filter(
        models.CompetitorEvolutionEvent.shop_id == sid,
        models.CompetitorEvolutionEvent.competitor_name == competitor_name)
    if section:
        q = q.filter(models.CompetitorEvolutionEvent.section == section)
    total = q.count()
    rows = (q.order_by(models.CompetitorEvolutionEvent.occurred_at.desc(),
                       models.CompetitorEvolutionEvent.id.desc())
            .offset(offset).limit(limit).all())
    return {"items": [{
        "id": r.id, "section": r.section, "field_name": r.field_name,
        "event_type": r.event_type, "old_value": r.old_value,
        "new_value": r.new_value, "change_source": r.change_source,
        "changed_by": r.changed_by, "evidence_id": r.evidence_id,
        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
    } for r in rows], "total": total, "limit": limit, "offset": offset}


# ── Vergelijking (2–5 concurrenten) ─────────────────────────────────────────

def _latest_ranking_by_name(db: Session, sid: int) -> dict:
    """Meest recente overall-ranking-rij per concurrent."""
    from sqlalchemy import func as _func
    latest = db.query(_func.max(models.CompetitorRanking.run_date)).filter(
        models.CompetitorRanking.scope == "overall",
        models.CompetitorRanking.shop_id == sid).scalar()
    if not latest:
        return {}
    rows = db.query(models.CompetitorRanking).filter(
        models.CompetitorRanking.scope == "overall",
        models.CompetitorRanking.shop_id == sid,
        models.CompetitorRanking.run_date == latest).all()
    return {r.competitor_name: r for r in rows}


def _ranking_out(r) -> Optional[dict]:
    if r is None:
        return None
    return {
        "rank": r.rank,
        "competition_relevance_score": round(float(r.competition_relevance_score or 0), 4),
        "price_relevance_score": round(float(r.price_relevance_score or 0), 4),
        "influence_score": round(float(r.influence_score or 0), 4),
        "combined_score": round(float(r.combined_score or 0), 4),
        "run_date": str(r.run_date),
    }


def _profile_summary_for(db: Session, sid: int, name: str, rules: dict) -> dict:
    """Compacte profielsamenvatting voor de vergelijkings-view."""
    business = db.query(models.CompetitorBusinessProfile).filter(
        models.CompetitorBusinessProfile.shop_id == sid,
        models.CompetitorBusinessProfile.competitor_name == name).first()
    fulfilment = db.query(models.CompetitorFulfilmentProfile).filter(
        models.CompetitorFulfilmentProfile.shop_id == sid,
        models.CompetitorFulfilmentProfile.competitor_name == name).first()
    financials = db.query(models.CompetitorFinancialObservation).filter(
        models.CompetitorFinancialObservation.shop_id == sid,
        models.CompetitorFinancialObservation.competitor_name == name).all()
    roles = db.query(models.CompetitorMarketRole).filter(
        models.CompetitorMarketRole.shop_id == sid,
        models.CompetitorMarketRole.competitor_name == name,
        models.CompetitorMarketRole.valid_to.is_(None)).all()
    geo = db.query(models.CompetitorGeographicPresence).filter(
        models.CompetitorGeographicPresence.shop_id == sid,
        models.CompetitorGeographicPresence.competitor_name == name,
        models.CompetitorGeographicPresence.valid_to.is_(None)).all()
    legacy = db.query(models.CompetitorProfile).filter(
        models.CompetitorProfile.shop_id == sid,
        models.CompetitorProfile.competitor_name == name).first()
    return {
        "competitor_name": name,
        "business": _singleton_out(business, cp.BUSINESS_FIELDS),
        "fulfilment": _singleton_out(fulfilment, cp.FULFILMENT_FIELDS),
        "financials": [_row_out(r, ["fiscal_year", "metric", "value_min",
                                    "value_max", "currency", "is_unknown",
                                    "as_of_date"]) for r in financials],
        "market_roles": [_row_out(r, ["role", "ai_assigned", "human_validated"])
                         for r in roles],
        "countries": sorted({g.country_code for g in geo if g.country_code}),
        "assortment_size": legacy.assortment_size if legacy else None,
        "price_segment": legacy.price_segment if legacy else None,
        "completeness": {
            "business": cp.section_completeness(business, cp.BUSINESS_FIELDS, rules),
            "fulfilment": cp.section_completeness(fulfilment, cp.FULFILMENT_FIELDS, rules),
        },
    }


@router.get("/compare")
def compare_competitors(
    names: str = Query(..., description="Komma-gescheiden lijst van 2–5 concurrentnamen"),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Vergelijking van 2–5 concurrenten: profiel, fulfilment, financieel,
    landen, marktrollen en alle scores naast elkaar. Onbekend blijft null."""
    sid = _scope(db, shop_id)
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    if not (2 <= len(name_list) <= 5):
        raise HTTPException(400, "Kies 2 tot 5 concurrenten om te vergelijken")
    for n in name_list:
        _require_competitor(db, sid, n)
    rules = cp.get_freshness_rules(db, sid)
    from engine.competitor_scores import latest_scores_by_competitor
    scores = latest_scores_by_competitor(db, sid)
    rankings = _latest_ranking_by_name(db, sid)
    items = []
    for n in name_list:
        item = _profile_summary_for(db, sid, n, rules)
        s = scores.get(n)
        item["scores"] = _score_summary_out(s) if s is not None else None
        item["ranking"] = _ranking_out(rankings.get(n))
        items.append(item)
    return {"shop_id": sid, "items": items, "total": len(items)}


def _score_summary_out(r) -> dict:
    return {
        "run_date": str(r.run_date),
        "company_size_class": r.company_size_class,
        "company_size_confidence": r.company_size_confidence,
        "geographic_scale_class": r.geographic_scale_class,
        "geographic_scale_confidence": r.geographic_scale_confidence,
        "fulfilment_model_class": r.fulfilment_model_class,
        "fulfilment_model_confidence": r.fulfilment_model_confidence,
        "operational_strength_score": r.operational_strength_score,
        "financial_health_score": r.financial_health_score,
        "financial_health_status": r.financial_health_status,
        "financial_data_confidence": r.financial_data_confidence,
        "business_strength_score": r.business_strength_score,
        "procurement_power_score": r.procurement_power_score,
        "future_threat_score": r.future_threat_score,
        "data_completeness_pct": r.data_completeness_pct,
        "model_version": r.model_version,
    }


# ── Volledig profiel + completeness/freshness ───────────────────────────────

@router.get("/{competitor_name}")
def get_full_profile(
    competitor_name: str,
    shop_id: Optional[int] = Query(None),
    include_scores: bool = Query(False, description="Voeg de acht scorecards (incl. factoren/gewichten) en de relevantiescores toe"),
    include_timeline: bool = Query(False, description="Voeg de eerste pagina van de evolution-timeline toe"),
    include_evidence: bool = Query(False, description="Voeg evidence-referenties toe"),
    timeline_limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    _require_competitor(db, sid, competitor_name)
    rules = cp.get_freshness_rules(db, sid)

    business = db.query(models.CompetitorBusinessProfile).filter(
        models.CompetitorBusinessProfile.shop_id == sid,
        models.CompetitorBusinessProfile.competitor_name == competitor_name).first()
    fulfilment = db.query(models.CompetitorFulfilmentProfile).filter(
        models.CompetitorFulfilmentProfile.shop_id == sid,
        models.CompetitorFulfilmentProfile.competitor_name == competitor_name).first()
    financials = db.query(models.CompetitorFinancialObservation).filter(
        models.CompetitorFinancialObservation.shop_id == sid,
        models.CompetitorFinancialObservation.competitor_name == competitor_name).all()
    roles = db.query(models.CompetitorMarketRole).filter(
        models.CompetitorMarketRole.shop_id == sid,
        models.CompetitorMarketRole.competitor_name == competitor_name).all()
    geography = db.query(models.CompetitorGeographicPresence).filter(
        models.CompetitorGeographicPresence.shop_id == sid,
        models.CompetitorGeographicPresence.competitor_name == competitor_name).all()
    relations = db.query(models.CompetitorCorporateRelation).filter(
        models.CompetitorCorporateRelation.shop_id == sid,
        models.CompetitorCorporateRelation.competitor_name == competitor_name).all()

    active_roles = [r for r in roles if r.valid_to is None]
    active_geo = [g for g in geography if g.valid_to is None]

    extra: dict = {}
    if include_scores:
        row = (db.query(models.CompetitorScoreResult)
               .filter(models.CompetitorScoreResult.shop_id == sid,
                       models.CompetitorScoreResult.competitor_name == competitor_name)
               .order_by(models.CompetitorScoreResult.run_date.desc())
               .first())
        extra["scores"] = (
            {**_score_summary_out(row), "details": row.details or {}}
            if row is not None else None)
        extra["ranking"] = _ranking_out(
            _latest_ranking_by_name(db, sid).get(competitor_name))
    if include_evidence:
        ev = (db.query(models.CompetitionEvidence)
              .filter(models.CompetitionEvidence.shop_id == sid,
                      models.CompetitionEvidence.competitor_name == competitor_name)
              .order_by(models.CompetitionEvidence.created_at.desc())
              .all())
        extra["evidence"] = {"items": [_evidence_out(e) for e in ev],
                             "total": len(ev)}
    if include_timeline:
        tq = db.query(models.CompetitorEvolutionEvent).filter(
            models.CompetitorEvolutionEvent.shop_id == sid,
            models.CompetitorEvolutionEvent.competitor_name == competitor_name)
        t_total = tq.count()
        t_rows = (tq.order_by(models.CompetitorEvolutionEvent.occurred_at.desc(),
                              models.CompetitorEvolutionEvent.id.desc())
                  .limit(timeline_limit).all())
        extra["timeline"] = {"items": [{
            "id": r.id, "section": r.section, "field_name": r.field_name,
            "event_type": r.event_type, "old_value": r.old_value,
            "new_value": r.new_value, "change_source": r.change_source,
            "changed_by": r.changed_by, "evidence_id": r.evidence_id,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
        } for r in t_rows], "total": t_total, "limit": timeline_limit}

    return {
        **extra,
        "shop_id": sid,
        "competitor_name": competitor_name,
        "business": _singleton_out(business, cp.BUSINESS_FIELDS),
        "fulfilment": _singleton_out(fulfilment, cp.FULFILMENT_FIELDS),
        "financials": [_row_out(r, ["fiscal_year", "metric", "value_min",
                                    "value_max", "currency", "is_unknown",
                                    "source_note", "as_of_date"])
                       for r in financials],
        "market_roles": [_row_out(r, ["role", "ai_assigned", "human_validated",
                                      "valid_from", "valid_to"]) for r in roles],
        "geography": [_row_out(r, ["country_code", "presence_type",
                                   "valid_from", "valid_to"]) for r in geography],
        "corporate_relations": [_row_out(r, ["relation_type", "related_entity",
                                             "related_country", "valid_from",
                                             "valid_to"]) for r in relations],
        "completeness": {
            "business": cp.section_completeness(business, cp.BUSINESS_FIELDS, rules),
            "fulfilment": cp.section_completeness(fulfilment, cp.FULFILMENT_FIELDS, rules),
            "financials": cp.rows_completeness(financials, "revenue", rules),
            "market_roles": cp.rows_completeness(active_roles, "roles", rules),
            "geography": cp.rows_completeness(active_geo, "countries", rules),
            "corporate_relations": cp.rows_completeness(relations, "ownership", rules),
        },
        "freshness_rules": rules,
    }


# ── Freshness-regels ─────────────────────────────────────────────────────────

@router.get("/config/freshness")
def get_freshness_config(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    sid = _scope(db, shop_id)
    return {"shop_id": sid, "rules": cp.get_freshness_rules(db, sid),
            "defaults": cp.FRESHNESS_DEFAULTS}


@router.put("/config/freshness")
def update_freshness_config(
    payload: dict = Body(...),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Zet shop-specifieke freshness-overrides: {"rules": {field_type: dagen}}."""
    sid = _scope(db, shop_id)
    rules = payload.get("rules")
    if not isinstance(rules, dict) or not rules:
        raise HTTPException(400, "rules (object met field_type → dagen) is verplicht")
    for field_type, days in rules.items():
        if field_type not in cp.FRESHNESS_DEFAULTS:
            raise HTTPException(400, f"Onbekend field_type '{field_type}'; "
                                     f"geldig: {sorted(cp.FRESHNESS_DEFAULTS)}")
        if not isinstance(days, int) or isinstance(days, bool) or not (1 <= days <= 3650):
            raise HTTPException(400, f"{field_type}: max_age_days moet 1..3650 zijn")
        row = db.query(models.CompetitorFreshnessRule).filter(
            models.CompetitorFreshnessRule.shop_id == sid,
            models.CompetitorFreshnessRule.field_type == field_type).first()
        if row is None:
            row = models.CompetitorFreshnessRule(shop_id=sid, field_type=field_type,
                                                 max_age_days=days)
            db.add(row)
        row.max_age_days = days
        row.updated_by = current_user.username
    db.commit()
    return {"shop_id": sid, "rules": cp.get_freshness_rules(db, sid)}
