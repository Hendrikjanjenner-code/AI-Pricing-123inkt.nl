"""
PIM Integration & Product Content Intelligence routes (§23).

Overview, product-content detail met source ownership, families/attributen/
channels, productrelaties, completeness-recompute en de AI-suggestie
review-flow (PENDING → APPROVED/REJECTED; nooit automatisch toepassen).
"""
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
import models
import auth as auth_utils
from engine import pim_engine

router = APIRouter(prefix="/api/pim", tags=["pim"])

EDIT_ROLES = ("admin", "pricing_manager", "analyst")


# ─── Overview & scores ───────────────────────────────────────────────────────

@router.get("/overview")
def pim_overview(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    total_skus = db.query(models.DimProduct).count()
    scores = db.query(models.PimCompletenessScore).filter(
        models.PimCompletenessScore.channel_code.is_(None)).all()
    avg_comp = round(sum(s.completeness_pct for s in scores) / len(scores), 1) if scores else 0.0
    avg_qual = round(sum(s.quality_score for s in scores) / len(scores), 1) if scores else 0.0

    channels = db.query(models.PimChannel).filter(models.PimChannel.active == True).all()  # noqa: E712
    channel_stats = []
    for ch in channels:
        ch_scores = db.query(models.PimCompletenessScore).filter(
            models.PimCompletenessScore.channel_code == ch.code).all()
        ready = sum(1 for s in ch_scores if s.channel_ready)
        channel_stats.append({
            "code": ch.code, "name": ch.name,
            "min_completeness_pct": ch.min_completeness_pct,
            "skus_scored": len(ch_scores),
            "skus_ready": ready,
            "avg_completeness_pct": round(
                sum(s.completeness_pct for s in ch_scores) / len(ch_scores), 1) if ch_scores else 0.0,
        })

    pending = db.query(models.PimAiSuggestion).filter(
        models.PimAiSuggestion.status == "PENDING").count()
    last_run = db.query(func.max(models.PimCompletenessScore.run_date)).scalar()

    return {
        "total_skus": total_skus,
        "skus_scored": len(scores),
        "avg_completeness_pct": avg_comp,
        "avg_quality_score": avg_qual,
        "low_completeness_count": sum(1 for s in scores if s.completeness_pct < 60.0),
        "channels": channel_stats,
        "pending_suggestions": pending,
        "last_run_date": last_run.isoformat() if last_run else None,
    }


@router.get("/completeness")
def list_completeness(
    channel: str | None = Query(None, description="Channel-code; leeg = overall"),
    max_pct: float | None = Query(None, description="Alleen SKU's onder dit percentage"),
    only_not_ready: bool = Query(False),
    search: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    S = models.PimCompletenessScore
    q = db.query(S, models.DimProduct).join(
        models.DimProduct, models.DimProduct.sku_id == S.sku_id)
    q = q.filter(S.channel_code == channel) if channel else q.filter(S.channel_code.is_(None))
    if max_pct is not None:
        q = q.filter(S.completeness_pct <= max_pct)
    if only_not_ready and channel:
        q = q.filter(S.channel_ready == False)  # noqa: E712
    if search:
        like = f"%{search}%"
        q = q.filter((models.DimProduct.sku_id.ilike(like))
                     | (models.DimProduct.product_name.ilike(like)))
    total = q.count()
    rows = q.order_by(S.completeness_pct.asc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [{
            "sku_id": s.sku_id,
            "product_name": p.product_name,
            "brand": p.brand,
            "category": p.category,
            "channel_code": s.channel_code,
            "completeness_pct": s.completeness_pct,
            "quality_score": s.quality_score,
            "channel_ready": s.channel_ready,
            "missing_attributes": s.missing_attributes or [],
            "quality_issues": s.quality_issues or [],
            "run_date": s.run_date.isoformat() if s.run_date else None,
        } for s, p in rows],
    }


@router.post("/recompute")
def recompute(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*EDIT_ROLES)),
):
    """Synchroniseer DRS-attributen en herbereken completeness/quality-scores.

    Optioneel: stuur ``{"sku_ids": ["SKU-A", "SKU-B"]}`` om de herberekening
    te beperken tot een subset van SKU's (handig voor tests en gerichte updates).
    """
    sku_ids: list[str] | None = payload.get("sku_ids") or None
    count = pim_engine.compute_completeness(db, sku_ids=sku_ids)
    return {"scores_written": count, "message": f"{count} scores herberekend."}


# ─── Product-contentdetail ───────────────────────────────────────────────────

@router.get("/products/{sku_id}/content")
def product_content(
    sku_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == sku_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="SKU niet gevonden.")
    pim_engine.ensure_defaults(db)
    defs = db.query(models.PimAttributeDefinition).filter(
        models.PimAttributeDefinition.active == True).all()  # noqa: E712
    values = {v.attribute_id: v for v in db.query(models.PimAttributeValue).filter(
        models.PimAttributeValue.sku_id == sku_id).all()}
    content = db.query(models.PimProductContent).filter(
        models.PimProductContent.sku_id == sku_id).first()
    family = None
    if content and content.family_id:
        family = db.query(models.PimFamily).filter(
            models.PimFamily.id == content.family_id).first()
    relations = db.query(models.PimProductRelation).filter(
        (models.PimProductRelation.sku_id == sku_id)
        | (models.PimProductRelation.related_sku_id == sku_id)).all()
    scores = db.query(models.PimCompletenessScore).filter(
        models.PimCompletenessScore.sku_id == sku_id).all()
    suggestions = db.query(models.PimAiSuggestion).filter(
        models.PimAiSuggestion.sku_id == sku_id,
        models.PimAiSuggestion.status == "PENDING").all()

    return {
        "sku_id": sku_id,
        "product_name": product.product_name,
        "brand": product.brand,
        "category": product.category,
        "family": {"id": family.id, "code": family.code, "name": family.name} if family else None,
        "variant": {
            "parent_sku_id": content.parent_sku_id,
            "variant_axis": content.variant_axis,
            "variant_value": content.variant_value,
        } if content and content.parent_sku_id else None,
        "attributes": [{
            "attribute_id": d.id,
            "code": d.code,
            "name": d.name,
            "data_type": d.data_type,
            "unit": d.unit,
            "source_owner": d.source_owner,
            "is_required": d.is_required,
            "value": values[d.id].value if d.id in values else None,
            "value_source": values[d.id].source if d.id in values else None,
            "confidence": values[d.id].confidence if d.id in values else None,
            "updated_by": values[d.id].updated_by if d.id in values else None,
        } for d in defs],
        "relations": [{
            "id": r.id, "sku_id": r.sku_id, "related_sku_id": r.related_sku_id,
            "relation_type": r.relation_type, "note": r.note,
        } for r in relations],
        "scores": [{
            "channel_code": s.channel_code,
            "completeness_pct": s.completeness_pct,
            "quality_score": s.quality_score,
            "channel_ready": s.channel_ready,
            "missing_attributes": s.missing_attributes or [],
            "quality_issues": s.quality_issues or [],
        } for s in scores],
        "pending_suggestions": [{
            "id": s.id, "attribute_code": s.attribute_code,
            "suggested_value": s.suggested_value, "confidence": s.confidence,
            "rationale": s.rationale,
        } for s in suggestions],
    }


class AttributeValueUpdate(BaseModel):
    attribute_code: str
    value: str | None = None


@router.patch("/products/{sku_id}/attributes")
def update_attribute_value(
    sku_id: str,
    body: AttributeValueUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*EDIT_ROLES)),
):
    """
    Handmatige correctie van een attribuutwaarde. DRS-owned velden zijn
    beschermd: die worden bij de volgende sync weer door DRS overschreven,
    dus een handmatige wijziging daarop wordt geweigerd (source ownership §4).
    """
    product = db.query(models.DimProduct).filter(models.DimProduct.sku_id == sku_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="SKU niet gevonden.")
    d = db.query(models.PimAttributeDefinition).filter(
        models.PimAttributeDefinition.code == body.attribute_code).first()
    if d is None:
        raise HTTPException(status_code=404, detail="Attribuut niet gevonden.")
    row = db.query(models.PimAttributeValue).filter(
        models.PimAttributeValue.sku_id == sku_id,
        models.PimAttributeValue.attribute_id == d.id).first()
    # Centrale source-ownership-policy (§4) voor alle schrijvers
    reason = pim_engine.check_write_allowed(d, row, "Handmatig")
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    value = (body.value or "").strip() or None
    if row is None:
        if value is None:
            raise HTTPException(status_code=400, detail="Geen waarde opgegeven.")
        row = models.PimAttributeValue(sku_id=sku_id, attribute_id=d.id)
        db.add(row)
    row.value = value
    row.source = "Handmatig"
    row.confidence = None
    row.updated_by = current_user.username
    db.commit()
    return {"sku_id": sku_id, "attribute_code": d.code, "value": row.value,
            "source": row.source}


# ─── Families / attributen / channels (referentiedata) ──────────────────────

@router.get("/families")
def list_families(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    pim_engine.ensure_defaults(db)
    fams = db.query(models.PimFamily).all()
    counts = dict(db.query(models.PimProductContent.family_id,
                           func.count(models.PimProductContent.id))
                  .group_by(models.PimProductContent.family_id).all())
    return [{
        "id": f.id, "code": f.code, "name": f.name,
        "category_patterns": f.category_patterns or [],
        "active": f.active, "product_count": counts.get(f.id, 0),
    } for f in fams]


@router.get("/attributes")
def list_attributes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    pim_engine.ensure_defaults(db)
    defs = db.query(models.PimAttributeDefinition).all()
    return [{
        "id": d.id, "code": d.code, "name": d.name, "data_type": d.data_type,
        "unit": d.unit, "source_owner": d.source_owner,
        "is_required": d.is_required, "weight": d.weight,
        "dim_product_field": d.dim_product_field, "active": d.active,
    } for d in defs]


@router.get("/channels")
def list_channels(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    pim_engine.ensure_defaults(db)
    chans = db.query(models.PimChannel).all()
    return [{
        "id": c.id, "code": c.code, "name": c.name,
        "required_attribute_codes": c.required_attribute_codes or [],
        "min_completeness_pct": c.min_completeness_pct, "active": c.active,
    } for c in chans]


# ─── Beheer: attribuutdefinities, channels, families ────────────────────────

VALID_SOURCES = {"DRS", "Leverancier", "Handmatig", "AI"}
ADMIN_ROLES = ("admin", "pricing_manager")


VALID_DATA_TYPES = {"text", "number", "boolean", "select"}


def _validate_code(code: str) -> str:
    code = (code or "").strip().lower()
    if not code or not all(c.isalnum() or c in ("_", "-") for c in code):
        raise HTTPException(
            status_code=400,
            detail="Code is verplicht en mag alleen letters, cijfers, '_' en '-' bevatten.")
    return code


class AttributeCreate(BaseModel):
    code: str
    name: str
    data_type: str = "text"
    unit: str | None = None
    source_owner: str = "Handmatig"
    is_required: bool = False
    weight: float = 1.0


@router.post("/attributes", status_code=201)
def create_attribute(
    body: AttributeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*ADMIN_ROLES)),
):
    """Maak een nieuwe attribuutdefinitie aan (beheer, taak: nieuw toevoegen vanuit de app)."""
    code = _validate_code(body.code)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Naam is verplicht.")
    if body.data_type not in VALID_DATA_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Ongeldig datatype. Kies uit: {', '.join(sorted(VALID_DATA_TYPES))}")
    if body.source_owner not in VALID_SOURCES:
        raise HTTPException(status_code=400,
                            detail=f"Ongeldige eigenaar. Kies uit: {', '.join(sorted(VALID_SOURCES))}")
    if body.weight <= 0:
        raise HTTPException(status_code=400, detail="Gewicht moet positief zijn.")
    if db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.code == code).first():
        raise HTTPException(status_code=409, detail=f"Attribuutcode '{code}' bestaat al.")
    d = models.PimAttributeDefinition(
        code=code, name=name, data_type=body.data_type,
        unit=(body.unit or "").strip() or None,
        source_owner=body.source_owner, is_required=body.is_required,
        weight=body.weight, active=True)
    db.add(d)
    db.add(models.AuditLog(
        entity_type="pim_attribute_definition", entity_id=code,
        action="attribute_created", performed_by=current_user.username,
        details=f"code={code}"))
    db.commit()
    db.refresh(d)
    return {
        "id": d.id, "code": d.code, "name": d.name, "data_type": d.data_type,
        "unit": d.unit, "source_owner": d.source_owner,
        "is_required": d.is_required, "weight": d.weight,
        "dim_product_field": d.dim_product_field, "active": d.active,
    }


class ChannelCreate(BaseModel):
    code: str
    name: str
    required_attribute_codes: list[str] = []
    min_completeness_pct: float = 80.0


@router.post("/channels", status_code=201)
def create_channel(
    body: ChannelCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*ADMIN_ROLES)),
):
    """Maak een nieuw channel aan."""
    code = _validate_code(body.code)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Naam is verplicht.")
    if not (0.0 <= body.min_completeness_pct <= 100.0):
        raise HTTPException(status_code=400, detail="Drempel moet tussen 0 en 100 liggen.")
    existing_codes = {d.code for d in db.query(models.PimAttributeDefinition).all()}
    unknown = [x for x in body.required_attribute_codes if x not in existing_codes]
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Onbekende attribuutcodes: {', '.join(unknown)}")
    if db.query(models.PimChannel).filter(models.PimChannel.code == code).first():
        raise HTTPException(status_code=409, detail=f"Channelcode '{code}' bestaat al.")
    c = models.PimChannel(
        code=code, name=name,
        required_attribute_codes=body.required_attribute_codes,
        min_completeness_pct=body.min_completeness_pct, active=True)
    db.add(c)
    db.add(models.AuditLog(
        entity_type="pim_channel", entity_id=code,
        action="channel_created", performed_by=current_user.username,
        details=f"code={code}"))
    db.commit()
    db.refresh(c)
    return {
        "id": c.id, "code": c.code, "name": c.name,
        "required_attribute_codes": c.required_attribute_codes or [],
        "min_completeness_pct": c.min_completeness_pct, "active": c.active,
    }


class FamilyCreate(BaseModel):
    code: str
    name: str
    category_patterns: list[str] = []


@router.post("/families", status_code=201)
def create_family(
    body: FamilyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*ADMIN_ROLES)),
):
    """Maak een nieuwe productfamilie aan."""
    code = _validate_code(body.code)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Naam is verplicht.")
    if db.query(models.PimFamily).filter(models.PimFamily.code == code).first():
        raise HTTPException(status_code=409, detail=f"Familiecode '{code}' bestaat al.")
    f = models.PimFamily(
        code=code, name=name,
        category_patterns=[p.strip() for p in body.category_patterns if p.strip()],
        active=True)
    db.add(f)
    db.add(models.AuditLog(
        entity_type="pim_family", entity_id=code,
        action="family_created", performed_by=current_user.username,
        details=f"code={code}"))
    db.commit()
    db.refresh(f)
    return {
        "id": f.id, "code": f.code, "name": f.name,
        "category_patterns": f.category_patterns or [],
        "active": f.active,
    }


class AttributePatch(BaseModel):
    name: str | None = None
    is_required: bool | None = None
    weight: float | None = None
    source_owner: str | None = None
    active: bool | None = None


@router.patch("/attributes/{attribute_id}")
def patch_attribute(
    attribute_id: int,
    body: AttributePatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*ADMIN_ROLES)),
):
    """Pas is_required, weight, source_owner of active aan van een attribuutdefinitie."""
    d = db.query(models.PimAttributeDefinition).filter(
        models.PimAttributeDefinition.id == attribute_id).first()
    if d is None:
        raise HTTPException(status_code=404, detail="Attribuutdefinitie niet gevonden.")
    if body.name is not None:
        d.name = body.name.strip() or d.name
    if body.is_required is not None:
        d.is_required = body.is_required
    if body.weight is not None:
        if body.weight <= 0:
            raise HTTPException(status_code=400, detail="Gewicht moet positief zijn.")
        d.weight = body.weight
    if body.source_owner is not None:
        if body.source_owner not in VALID_SOURCES:
            raise HTTPException(status_code=400,
                                detail=f"Ongeldige eigenaar. Kies uit: {', '.join(sorted(VALID_SOURCES))}")
        d.source_owner = body.source_owner
    if body.active is not None:
        d.active = body.active
    db.add(models.AuditLog(
        entity_type="pim_attribute_definition", entity_id=str(d.id),
        action="attribute_updated", performed_by=current_user.username,
        details=f"code={d.code}"))
    db.commit()
    return {
        "id": d.id, "code": d.code, "name": d.name, "data_type": d.data_type,
        "unit": d.unit, "source_owner": d.source_owner,
        "is_required": d.is_required, "weight": d.weight,
        "dim_product_field": d.dim_product_field, "active": d.active,
    }


class ChannelPatch(BaseModel):
    name: str | None = None
    required_attribute_codes: list[str] | None = None
    min_completeness_pct: float | None = None
    active: bool | None = None


@router.patch("/channels/{channel_id}")
def patch_channel(
    channel_id: int,
    body: ChannelPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*ADMIN_ROLES)),
):
    """Pas required_attribute_codes, min_completeness_pct of active aan van een channel."""
    c = db.query(models.PimChannel).filter(models.PimChannel.id == channel_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Channel niet gevonden.")
    if body.name is not None:
        c.name = body.name.strip() or c.name
    if body.required_attribute_codes is not None:
        # Valideer dat de codes bestaan
        existing_codes = {d.code for d in db.query(models.PimAttributeDefinition).all()}
        unknown = [x for x in body.required_attribute_codes if x not in existing_codes]
        if unknown:
            raise HTTPException(status_code=400,
                                detail=f"Onbekende attribuutcodes: {', '.join(unknown)}")
        c.required_attribute_codes = body.required_attribute_codes
    if body.min_completeness_pct is not None:
        if not (0.0 <= body.min_completeness_pct <= 100.0):
            raise HTTPException(status_code=400, detail="Drempel moet tussen 0 en 100 liggen.")
        c.min_completeness_pct = body.min_completeness_pct
    if body.active is not None:
        c.active = body.active
    db.add(models.AuditLog(
        entity_type="pim_channel", entity_id=str(c.id),
        action="channel_updated", performed_by=current_user.username,
        details=f"code={c.code}"))
    db.commit()
    return {
        "id": c.id, "code": c.code, "name": c.name,
        "required_attribute_codes": c.required_attribute_codes or [],
        "min_completeness_pct": c.min_completeness_pct, "active": c.active,
    }


class FamilyPatch(BaseModel):
    name: str | None = None
    category_patterns: list[str] | None = None
    active: bool | None = None


@router.patch("/families/{family_id}")
def patch_family(
    family_id: int,
    body: FamilyPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*ADMIN_ROLES)),
):
    """Pas name, category_patterns of active aan van een productfamilie."""
    f = db.query(models.PimFamily).filter(models.PimFamily.id == family_id).first()
    if f is None:
        raise HTTPException(status_code=404, detail="Familie niet gevonden.")
    if body.name is not None:
        f.name = body.name.strip() or f.name
    if body.category_patterns is not None:
        f.category_patterns = [p.strip() for p in body.category_patterns if p.strip()]
    if body.active is not None:
        f.active = body.active
    db.add(models.AuditLog(
        entity_type="pim_family", entity_id=str(f.id),
        action="family_updated", performed_by=current_user.username,
        details=f"code={f.code}"))
    db.commit()
    return {
        "id": f.id, "code": f.code, "name": f.name,
        "category_patterns": f.category_patterns or [],
        "active": f.active,
    }


# ─── Productrelaties ─────────────────────────────────────────────────────────

VALID_RELATION_TYPES = {"variant_van", "accessoire", "vervangt", "alternatief"}


class RelationCreate(BaseModel):
    sku_id: str
    related_sku_id: str
    relation_type: str
    note: str | None = None


@router.post("/relations")
def create_relation(
    body: RelationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*EDIT_ROLES)),
):
    if body.relation_type not in VALID_RELATION_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Ongeldig relatietype. Kies uit: {', '.join(sorted(VALID_RELATION_TYPES))}")
    for sid in (body.sku_id, body.related_sku_id):
        if not db.query(models.DimProduct).filter(models.DimProduct.sku_id == sid).first():
            raise HTTPException(status_code=404, detail=f"SKU '{sid}' niet gevonden.")
    if body.sku_id == body.related_sku_id:
        raise HTTPException(status_code=400, detail="Een product kan geen relatie met zichzelf hebben.")
    rel = models.PimProductRelation(
        sku_id=body.sku_id, related_sku_id=body.related_sku_id,
        relation_type=body.relation_type, note=body.note,
        created_by=current_user.username)
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return {"id": rel.id, "sku_id": rel.sku_id, "related_sku_id": rel.related_sku_id,
            "relation_type": rel.relation_type, "note": rel.note}


@router.delete("/relations/{relation_id}")
def delete_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*EDIT_ROLES)),
):
    rel = db.query(models.PimProductRelation).filter(
        models.PimProductRelation.id == relation_id).first()
    if rel is None:
        raise HTTPException(status_code=404, detail="Relatie niet gevonden.")
    db.delete(rel)
    db.commit()
    return {"deleted": relation_id}


# ─── AI-suggesties: genereren en review-flow ─────────────────────────────────

@router.post("/suggestions/generate")
def generate_suggestions(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*EDIT_ROLES)),
):
    result = pim_engine.generate_ai_suggestions(db, limit=limit, username=current_user.username)
    if not result.get("ai_available"):
        raise HTTPException(status_code=503, detail=result["message"])
    return result


@router.get("/suggestions")
def list_suggestions(
    status: str | None = Query("PENDING"),
    sku_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    q = db.query(models.PimAiSuggestion)
    if status:
        q = q.filter(models.PimAiSuggestion.status == status.upper())
    if sku_id:
        q = q.filter(models.PimAiSuggestion.sku_id == sku_id)
    rows = q.order_by(models.PimAiSuggestion.created_at.desc()).limit(limit).all()
    names = {p.sku_id: p.product_name for p in db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.in_([r.sku_id for r in rows])).all()} if rows else {}
    return [{
        "id": r.id, "sku_id": r.sku_id,
        "product_name": names.get(r.sku_id),
        "attribute_code": r.attribute_code,
        "suggested_value": r.suggested_value,
        "current_value": r.current_value,
        "rationale": r.rationale,
        "confidence": r.confidence,
        "model_version": r.model_version,
        "status": r.status,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


class SuggestionReview(BaseModel):
    action: str  # approve / reject


@router.patch("/suggestions/{suggestion_id}")
def review_suggestion(
    suggestion_id: int,
    body: SuggestionReview,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*EDIT_ROLES)),
):
    s = db.query(models.PimAiSuggestion).filter(
        models.PimAiSuggestion.id == suggestion_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="Suggestie niet gevonden.")
    if s.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Suggestie is al beoordeeld ({s.status}).")
    action = body.action.lower()
    if action == "approve":
        try:
            pim_engine.apply_suggestion(db, s, current_user.username)
        except pim_engine.OwnershipConflict as e:
            # Suggestie blijft PENDING; conflict expliciet terugmelden (§4)
            db.rollback()
            raise HTTPException(status_code=409, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif action == "reject":
        s.status = "REJECTED"
        s.reviewed_by = current_user.username
        s.reviewed_at = datetime.utcnow()
    else:
        raise HTTPException(status_code=400, detail="Actie moet 'approve' of 'reject' zijn.")
    db.add(models.AuditLog(
        entity_type="pim_suggestion", entity_id=str(s.id),
        action=f"suggestion_{action}", performed_by=current_user.username,
        details=f"{s.sku_id} · {s.attribute_code} = '{s.suggested_value}'"))
    db.commit()
    return {"id": s.id, "status": s.status, "reviewed_by": s.reviewed_by}
