"""
Decision Engine routes — /api/decisions/...

Commercial Decision & Impact Engine (§25): beslissingen met scenario's,
aanbeveling + WHY (§51), §28-approvalflow en reconstructie-historie (§53).
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime

from database import get_db
import auth as auth_utils
import models
from semantic_layer import _shop_scope

router = APIRouter(prefix="/api/decisions", tags=["decisions"])

# §28 statusmachine: toegestane overgangen
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"proposed", "cancelled"},
    "proposed": {"in_review", "approved", "rejected", "cancelled"},
    "in_review": {"approved", "rejected", "cancelled"},
    "approved": {"executed", "cancelled"},
    "rejected": set(),
    "executed": set(),
    "cancelled": set(),
}
ALL_STATUSES = list(STATUS_TRANSITIONS.keys())

STATUS_NL = {
    "draft": "Concept", "proposed": "Voorgesteld", "in_review": "In review",
    "approved": "Goedgekeurd", "rejected": "Afgewezen",
    "executed": "Uitgevoerd", "cancelled": "Geannuleerd",
}


def _scenario_out(s: models.DecisionScenario) -> dict:
    return {
        "id": s.id,
        "scenario_type": s.scenario_type,
        "label": s.label,
        "description": s.description,
        "expected_units": s.expected_units,
        "expected_revenue": s.expected_revenue,
        "expected_margin": s.expected_margin,
        "customer_impact": s.customer_impact,
        "basket_impact": s.basket_impact,
        "stock_impact": s.stock_impact,
        "strategic_impact": s.strategic_impact,
        "risk_level": s.risk_level,
        "risk_notes": s.risk_notes,
        "confidence": s.confidence,
        "score": s.score,
        "is_recommended": s.is_recommended,
        "why": {
            "factoren": s.why_factors or [],
            "bronnen": s.why_sources or [],
            "aannames": s.why_assumptions or [],
            "berekeningen": s.why_calculations or [],
        },
        "parameters": s.parameters or {},
    }


def _decision_out(d: models.Decision, include_scenarios: bool = False, db: Session = None) -> dict:
    out = {
        "id": d.id,
        "run_date": d.run_date.isoformat() if d.run_date else None,
        "entity_type": d.entity_type,
        "entity_id": d.entity_id,
        "entity_name": d.entity_name,
        "title": d.title,
        "summary": d.summary,
        "status": d.status,
        "status_nl": STATUS_NL.get(d.status, d.status),
        "proposed_by": d.proposed_by,
        "ai_model_version": d.ai_model_version,
        "reviewer": d.reviewer,
        "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
        "review_note": d.review_note,
        "confidence": d.confidence,
        "recommended_scenario_id": d.recommended_scenario_id,
        "signal_count": len(d.signal_ids or []),
        "data_gaps": d.data_gaps or [],
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
    if include_scenarios and db is not None:
        scenarios = (
            db.query(models.DecisionScenario)
            .filter(models.DecisionScenario.decision_id == d.id)
            .order_by(desc(models.DecisionScenario.score))
            .all()
        )
        out["scenarios"] = [_scenario_out(s) for s in scenarios]
    return out


@router.post("/run")
def run_engine(
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Draai de Decision Engine over alle actieve signalen (shop-scoped)."""
    from engine.decision_engine import run_decision_engine
    result = run_decision_engine(db, shop_id=shop_id)
    _audit(db, current_user.username, "decision_engine_run", "decision", "-",
           f"Run: {result['decisions_created']} beslissingen, {result['entities_skipped']} overgeslagen")
    db.commit()
    return result


@router.get("")
def list_decisions(
    status: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    sid = _shop_scope(db, shop_id)
    q = db.query(models.Decision).filter(models.Decision.shop_id == sid)
    if status:
        q = q.filter(models.Decision.status == status)
    if entity_type:
        q = q.filter(models.Decision.entity_type == entity_type)
    if entity_id:
        q = q.filter(models.Decision.entity_id == entity_id)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (models.Decision.entity_id.ilike(like)) | (models.Decision.entity_name.ilike(like))
        )

    total = q.count()
    items = (
        q.order_by(desc(models.Decision.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Statustellingen voor filters
    counts = {}
    for st in ALL_STATUSES:
        counts[st] = db.query(models.Decision).filter(
            models.Decision.status == st,
            models.Decision.shop_id == sid,
        ).count()

    # Entiteitstype-tellingen
    from sqlalchemy import func
    type_rows = (
        db.query(models.Decision.entity_type, func.count(models.Decision.id))
        .filter(models.Decision.shop_id == sid)
        .group_by(models.Decision.entity_type)
        .all()
    )
    entity_type_counts = {et: cnt for et, cnt in type_rows}

    return {
        "items": [_decision_out(d) for d in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "status_counts": counts,
        "statuses": [{"id": s, "label": STATUS_NL[s]} for s in ALL_STATUSES],
        "entity_type_counts": entity_type_counts,
    }


@router.get("/{decision_id}")
def get_decision(
    decision_id: int,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    d = _get_or_404(decision_id, db, shop_id)
    out = _decision_out(d, include_scenarios=True, db=db)
    out["signal_snapshot"] = d.signal_snapshot or []
    if d.entity_type == "category":
        out["category_context"] = _category_context(db, d.shop_id, d.entity_id)
    return out


def _category_context(db: Session, sid: int, category: str) -> dict:
    """Geaggregeerde categoriecontext voor category-beslissingen:
    aantal SKU's, omzet/marge (laatste 30 dagen), huismerkaandeel en
    subcategorie-verdeling. Ontbrekende data blijft expliciet None."""
    from sqlalchemy import func
    from datetime import timedelta

    products = (
        db.query(models.DimProduct)
        .filter(models.DimProduct.category == category, models.DimProduct.shop_id == sid)
        .all()
    )
    n_skus = len(products)
    pl_skus = [p.sku_id for p in products if p.is_private_label]
    n_pl = len(pl_skus)

    # Subcategorie-verdeling (op SKU-telling)
    sub_counts: dict[str, int] = {}
    for p in products:
        key = p.subcategory or "Onbekend"
        sub_counts[key] = sub_counts.get(key, 0) + 1
    subcategories = [
        {"name": k, "sku_count": v}
        for k, v in sorted(sub_counts.items(), key=lambda kv: -kv[1])
    ]

    # Omzet/marge over de laatste 30 dagen t.o.v. de meest recente verkoopdatum
    total_units = total_revenue = total_margin = None
    pl_revenue = None
    sku_ids = [p.sku_id for p in products]
    if sku_ids:
        max_date = (
            db.query(func.max(models.FactSalesDaily.date))
            .filter(
                models.FactSalesDaily.shop_id == sid,
                models.FactSalesDaily.sku_id.in_(sku_ids),
            )
            .scalar()
        )
        if max_date:
            cutoff = max_date - timedelta(days=29)
            base = db.query(
                func.coalesce(func.sum(models.FactSalesDaily.units_sold), 0),
                func.coalesce(func.sum(models.FactSalesDaily.revenue), 0.0),
                func.coalesce(func.sum(models.FactSalesDaily.margin), 0.0),
            ).filter(
                models.FactSalesDaily.shop_id == sid,
                models.FactSalesDaily.date >= cutoff,
                models.FactSalesDaily.sku_id.in_(sku_ids),
            )
            units, rev, mar = base.first()
            total_units, total_revenue, total_margin = int(units or 0), float(rev or 0.0), float(mar or 0.0)
            if pl_skus:
                pl_rev = (
                    db.query(func.coalesce(func.sum(models.FactSalesDaily.revenue), 0.0))
                    .filter(
                        models.FactSalesDaily.shop_id == sid,
                        models.FactSalesDaily.date >= cutoff,
                        models.FactSalesDaily.sku_id.in_(pl_skus),
                    )
                    .scalar()
                )
                pl_revenue = float(pl_rev or 0.0)
            else:
                pl_revenue = 0.0

    return {
        "category": category,
        "sku_count": n_skus,
        "private_label_sku_count": n_pl,
        "private_label_share_skus": round(n_pl / n_skus, 4) if n_skus else None,
        "private_label_share_revenue": (
            round(pl_revenue / total_revenue, 4)
            if pl_revenue is not None and total_revenue else None
        ),
        "total_units_30d": total_units,
        "total_revenue_30d": total_revenue,
        "total_margin_30d": total_margin,
        "subcategories": subcategories,
        "horizon_days": 30,
    }


@router.get("/{decision_id}/history")
def decision_history(
    decision_id: int,
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    """§53: volledige reconstructie — events + bevroren signaalcontext."""
    d = _get_or_404(decision_id, db, shop_id)
    events = (
        db.query(models.DecisionEvent)
        .filter(models.DecisionEvent.decision_id == decision_id)
        .order_by(models.DecisionEvent.created_at.asc())
        .all()
    )
    return {
        "decision": _decision_out(d),
        "signal_snapshot": d.signal_snapshot or [],
        "data_gaps": d.data_gaps or [],
        "events": [
            {
                "id": e.id,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "actor": e.actor,
                "actor_type": e.actor_type,
                "note": e.note,
                "values_snapshot": e.values_snapshot or {},
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


@router.post("/{decision_id}/transition")
def transition_decision(
    decision_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """
    §28-statusovergang: {to_status, note?, scenario_id?}.
    Bij approve kan een alternatief scenario gekozen worden via scenario_id.
    """
    d = _get_or_404(decision_id, db, payload.get("shop_id"))
    to_status = payload.get("to_status")
    note = payload.get("note", "")

    if to_status not in STATUS_TRANSITIONS:
        raise HTTPException(400, f"Onbekende status '{to_status}'. Geldig: {ALL_STATUSES}")
    if to_status not in STATUS_TRANSITIONS.get(d.status, set()):
        raise HTTPException(
            409,
            f"Overgang {STATUS_NL.get(d.status, d.status)} → {STATUS_NL[to_status]} is niet toegestaan",
        )
    if to_status == "rejected" and not note.strip():
        raise HTTPException(400, "Een reden (note) is verplicht bij afwijzen")

    # Optioneel: ander scenario kiezen bij goedkeuring
    chosen = None
    scenario_id = payload.get("scenario_id")
    if to_status == "approved" and scenario_id:
        chosen = db.query(models.DecisionScenario).filter(
            models.DecisionScenario.id == scenario_id,
            models.DecisionScenario.decision_id == decision_id,
        ).first()
        if not chosen:
            raise HTTPException(404, "Scenario niet gevonden bij deze beslissing")
        db.query(models.DecisionScenario).filter(
            models.DecisionScenario.decision_id == decision_id
        ).update({"is_recommended": False})
        chosen.is_recommended = True
        d.recommended_scenario_id = chosen.id

    from_status = d.status
    d.status = to_status
    if to_status in ("approved", "rejected", "in_review", "executed", "cancelled"):
        d.reviewer = current_user.username
        d.reviewed_at = datetime.utcnow()
        if note:
            d.review_note = note

    rec = chosen or db.query(models.DecisionScenario).filter(
        models.DecisionScenario.id == d.recommended_scenario_id
    ).first()

    db.add(models.DecisionEvent(
        decision_id=d.id,
        from_status=from_status,
        to_status=to_status,
        actor=current_user.username,
        actor_type="human",
        note=note or None,
        values_snapshot={
            "scenario_type": rec.scenario_type if rec else None,
            "expected_margin": rec.expected_margin if rec else None,
            "expected_revenue": rec.expected_revenue if rec else None,
            "confidence": rec.confidence if rec else None,
        },
    ))
    _audit(db, current_user.username, f"decision_{to_status}", "decision", str(d.id),
           f"{STATUS_NL.get(from_status, from_status)} → {STATUS_NL[to_status]}" + (f": {note}" if note else ""))
    db.commit()
    db.refresh(d)
    return _decision_out(d, include_scenarios=True, db=db)


def _get_or_404(decision_id: int, db: Session, shop_id: Optional[int] = None) -> models.Decision:
    """Shop-scoped lookup: een beslissing van een andere shop bestaat voor
    deze scope niet (404), zodat IDs niet cross-tenant te raden zijn."""
    sid = _shop_scope(db, shop_id)
    d = db.query(models.Decision).filter(
        models.Decision.id == decision_id,
        models.Decision.shop_id == sid,
    ).first()
    if not d:
        raise HTTPException(404, "Beslissing niet gevonden")
    return d


def _audit(db: Session, user: str, action: str, entity_type: str, entity_id: str, details: str):
    db.add(models.AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        performed_by=user,
        details=details,
        timestamp=datetime.utcnow(),
    ))
