"""
Signal-publicatie framework (masterprompt §7-§8).

Herbruikbare publisher die elke engine aanroept aan het einde van een run.
Garanties:
- Geen signaal zonder explanation + evidence + sources (§64.9-10)
- Dedupe via dedupe_key (engine:signal_type:entity_type:entity_id):
  een bestaand actief signaal met dezelfde sleutel wordt gesuperseded
- valid_until standaard 7 dagen; verlopen signalen worden ge-expired
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)

VALID_SEVERITIES = ("info", "low", "medium", "high", "critical")
VALID_DIRECTIONS = ("positive", "negative", "neutral", None)
VALID_ENTITY_TYPES = ("sku", "category", "brand", "competitor", "shop", "supplier")

DEFAULT_VALIDITY_DAYS = 7


def _default_shop_id(db: Session) -> int:
    row = db.query(models.DimShop.id).filter(models.DimShop.is_default == True).first()  # noqa: E712
    return row[0] if row else 1


def expire_stale_signals(db: Session) -> int:
    """Markeer actieve signalen met verstreken valid_until als expired."""
    now = datetime.utcnow()
    n = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.status == "active",
        models.IntelligenceSignal.valid_until.isnot(None),
        models.IntelligenceSignal.valid_until < now,
    ).update({"status": "expired"}, synchronize_session=False)
    return n


def publish_signal(
    db: Session,
    *,
    engine: str,
    signal_type: str,
    entity_type: str,
    entity_id: str,
    explanation: str,
    evidence: dict,
    sources: list,
    model_version: str,
    entity_name: Optional[str] = None,
    severity: str = "info",
    direction: Optional[str] = None,
    metric: Optional[str] = None,
    current_value: Optional[float] = None,
    previous_value: Optional[float] = None,
    expected_value: Optional[float] = None,
    change_pct: Optional[float] = None,
    confidence: float = 0.5,
    suggested_action: Optional[str] = None,
    valid_days: int = DEFAULT_VALIDITY_DAYS,
    shop_id: Optional[int] = None,
) -> models.IntelligenceSignal:
    """
    Publiceer één IntelligenceSignal. Superseded automatisch een bestaand
    actief signaal met dezelfde dedupe-sleutel. Commit gebeurt door de caller
    (of gebruik publish_batch/commit aan het einde van de engine-run).
    """
    if not explanation or not explanation.strip():
        raise ValueError(f"Signal {engine}:{signal_type} zonder explanation is niet toegestaan (§64.9)")
    if not evidence:
        raise ValueError(f"Signal {engine}:{signal_type} zonder evidence is niet toegestaan (§64.10)")
    if not sources:
        raise ValueError(f"Signal {engine}:{signal_type} zonder sources is niet toegestaan")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Ongeldige severity '{severity}'")
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"Ongeldige direction '{direction}'")
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(f"Ongeldig entity_type '{entity_type}'")
    if not model_version:
        raise ValueError("model_version is verplicht")

    sid = shop_id if shop_id is not None else _default_shop_id(db)
    dedupe_key = f"{engine}:{signal_type}:{entity_type}:{entity_id}"

    db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.dedupe_key == dedupe_key,
        models.IntelligenceSignal.shop_id == sid,
        models.IntelligenceSignal.status == "active",
    ).update({"status": "superseded"}, synchronize_session=False)

    signal = models.IntelligenceSignal(
        shop_id=sid,
        engine=engine,
        signal_type=signal_type,
        severity=severity,
        direction=direction,
        entity_type=entity_type,
        entity_id=str(entity_id),
        entity_name=entity_name,
        metric=metric,
        current_value=current_value,
        previous_value=previous_value,
        expected_value=expected_value,
        change_pct=change_pct,
        confidence=max(0.0, min(1.0, float(confidence))),
        explanation=explanation.strip(),
        evidence=evidence,
        sources=sources,
        suggested_action=suggested_action,
        valid_until=datetime.utcnow() + timedelta(days=valid_days),
        model_version=model_version,
        dedupe_key=dedupe_key,
    )
    db.add(signal)
    return signal
