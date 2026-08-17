"""
Intelligence Signals API — /api/signals
Gestandaardiseerde signalen van alle engines (masterprompt §7) plus de
semantic-layer functiecatalogus en centrale metric-definities.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models
from sqlalchemy.exc import IntegrityError
from semantic_layer import SEMANTIC_FUNCTIONS, get_active_signals, signal_to_dict, _shop_scope
from metrics import METRIC_DEFINITIONS

router = APIRouter(prefix="/api/signals", tags=["signals"])

VALID_SEVERITIES = ("info", "low", "medium", "high", "critical")
VALID_DIRECTIONS = ("positive", "negative", "neutral")
VALID_ENTITY_TYPES = ("sku", "category", "brand", "competitor", "shop", "supplier")
VALID_STATUSES = ("active", "expired", "superseded", "dismissed")


class SignalCreate(BaseModel):
    engine: str = Field(min_length=1, max_length=100)
    signal_type: str = Field(min_length=1, max_length=100)
    severity: str = "info"
    direction: Optional[str] = None
    entity_type: str
    entity_id: str = Field(min_length=1, max_length=255)
    entity_name: Optional[str] = None
    metric: Optional[str] = None
    current_value: Optional[float] = None
    previous_value: Optional[float] = None
    expected_value: Optional[float] = None
    change_pct: Optional[float] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    explanation: str = Field(min_length=1)
    # Verplicht (§64.9-10): geen signaal zonder onderbouwend bewijs.
    evidence: dict = Field(description="Onderbouwende datapunten — verplicht en niet leeg")
    sources: list = Field(description="Gebruikte bronnen/tabellen — verplicht en niet leeg")
    suggested_action: Optional[str] = None
    valid_until: Optional[datetime] = None
    model_version: Optional[str] = None
    shop_id: Optional[int] = None


@router.get("")
def list_signals(
    engine: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    status: str = Query("active"),
    shop_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lijst van Intelligence Signals met filters en paginering."""
    sid = _shop_scope(db, shop_id)
    q = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.shop_id == sid
    )
    if status and status != "all":
        q = q.filter(models.IntelligenceSignal.status == status)
    if engine:
        q = q.filter(models.IntelligenceSignal.engine == engine)
    if severity:
        q = q.filter(models.IntelligenceSignal.severity == severity)
    if entity_type:
        q = q.filter(models.IntelligenceSignal.entity_type == entity_type)
    if entity_id:
        q = q.filter(models.IntelligenceSignal.entity_id == entity_id)

    total = q.count()
    rows = (
        q.order_by(desc(models.IntelligenceSignal.observed_at))
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    engines = [r[0] for r in db.query(models.IntelligenceSignal.engine).distinct().all()]
    return {
        "signals": [signal_to_dict(s) for s in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "filter_options": {
            "engines": sorted(engines),
            "severities": list(VALID_SEVERITIES),
            "entity_types": list(VALID_ENTITY_TYPES),
        },
    }


@router.get("/catalog")
def get_catalog(current_user: models.User = Depends(get_current_user)):
    """Catalogus: goedgekeurde semantic-layer functies + metric-definities."""
    return {
        "semantic_functions": [
            {
                "name": f.name,
                "description": f.description,
                "required_roles": list(f.required_roles),
            }
            for f in SEMANTIC_FUNCTIONS.values()
        ],
        "metrics": [
            {
                "name": m.name,
                "label_nl": m.label_nl,
                "description": m.description,
                "formula": m.formula,
                "unit": m.unit,
            }
            for m in METRIC_DEFINITIONS.values()
        ],
    }


@router.get("/{signal_id}")
def get_signal(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    s = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.id == signal_id
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal_to_dict(s)


@router.post("", status_code=201)
def create_signal(
    req: SignalCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    """
    Publiceer een signaal. Bedoeld voor engines en beheerders; een eerder
    actief signaal met dezelfde dedupe-key wordt superseded (geen duplicaten).
    """
    if req.severity not in VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity. Valid: {VALID_SEVERITIES}")
    if req.direction is not None and req.direction not in VALID_DIRECTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid direction. Valid: {VALID_DIRECTIONS}")
    if req.entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity_type. Valid: {VALID_ENTITY_TYPES}")
    if not req.evidence:
        raise HTTPException(status_code=400, detail="evidence is required and must not be empty (no signal without evidence)")
    if not req.sources:
        raise HTTPException(status_code=400, detail="sources is required and must not be empty")
    if req.metric is not None and req.metric not in METRIC_DEFINITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric '{req.metric}'. Valid metrics: {sorted(METRIC_DEFINITIONS)}",
        )

    sid = _shop_scope(db, req.shop_id)
    dedupe_key = f"{req.engine}:{req.signal_type}:{req.entity_type}:{req.entity_id}"

    db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.dedupe_key == dedupe_key,
        models.IntelligenceSignal.shop_id == sid,
        models.IntelligenceSignal.status == "active",
    ).update({"status": "superseded"})

    signal = models.IntelligenceSignal(
        shop_id=sid,
        engine=req.engine,
        signal_type=req.signal_type,
        severity=req.severity,
        direction=req.direction,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        entity_name=req.entity_name,
        metric=req.metric,
        current_value=req.current_value,
        previous_value=req.previous_value,
        expected_value=req.expected_value,
        change_pct=req.change_pct,
        confidence=req.confidence,
        explanation=req.explanation,
        evidence=req.evidence,
        sources=req.sources,
        suggested_action=req.suggested_action,
        valid_until=req.valid_until,
        model_version=req.model_version,
        dedupe_key=dedupe_key,
    )
    db.add(signal)
    try:
        db.commit()
    except IntegrityError:
        # Race met een gelijktijdige publisher: de partial unique index
        # (dedupe_key, shop_id, status='active') hield het duplicaat tegen.
        # Supersede opnieuw en probeer één keer opnieuw.
        db.rollback()
        db.query(models.IntelligenceSignal).filter(
            models.IntelligenceSignal.dedupe_key == dedupe_key,
            models.IntelligenceSignal.shop_id == sid,
            models.IntelligenceSignal.status == "active",
        ).update({"status": "superseded"})
        db.add(signal)
        db.commit()
    db.refresh(signal)
    return signal_to_dict(signal)

@router.post("/refresh")
def refresh_all_signals(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
):
    """
    Draai alle signal-emitters over de meest recente engine-resultaten
    (incl. verse competitor rankings) en expireer verouderde signalen.
    """
    from engine.signal_emitters import emit_all_signals
    results = emit_all_signals(db)
    return {
        "status": "voltooid",
        "published_per_engine": {k: v for k, v in results.items() if k not in ("expired",)},
        "expired": results.get("expired", 0),
        "failed_engines": [k for k, v in results.items() if v == -1],
    }


@router.post("/{signal_id}/dismiss")
def dismiss_signal(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager", "analyst")),
):
    s = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.id == signal_id
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Signal not found")
    s.status = "dismissed"
    db.add(models.AuditLog(
        entity_type="intelligence_signal",
        entity_id=str(signal_id),
        action="dismiss",
        performed_by=current_user.username,
        details=f"Signal '{s.signal_type}' ({s.engine}) dismissed",
    ))
    db.commit()
    return signal_to_dict(s)
