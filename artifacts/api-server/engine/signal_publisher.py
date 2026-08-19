"""
Signal Publisher — herbruikbare helper waarmee engines rechtstreeks een
IntelligenceSignal publiceren (masterprompt §7-§8), met dezelfde
dedupe/supersede-semantiek als de HTTP-route /api/signals.

Garanties:
- Geen signaal zonder explanation + evidence + sources (§64.9-10)
- Dedupe via dedupe_key (engine:signal_type:entity_type:entity_id):
  een bestaand actief signaal met dezelfde sleutel wordt gesuperseded
- valid_until: expliciet meegeven of standaard 7 dagen (valid_days)

De helper commit NIET zelf; de aanroepende engine-run beheert de transactie.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)

VALID_SEVERITIES = ("info", "low", "medium", "high", "critical")

DEFAULT_VALIDITY_DAYS = 7


def _default_shop_id(db: Session) -> int:
    row = db.query(models.DimShop.id).filter(models.DimShop.is_default == True).first()  # noqa: E712
    return row[0] if row else 1


def resolve_shop_id(db: Session, shop_id=None) -> int:
    """Valideer een expliciete shop_id of val terug op de default shop.

    Raises HTTPException(404) bij een onbekende shop, zodat engines/routes
    nooit stilzwijgend data van een verkeerde scope mengen.
    """
    from fastapi import HTTPException
    if shop_id is not None:
        exists = db.query(models.DimShop.id).filter(models.DimShop.id == shop_id).first()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Shop {shop_id} not found")
        return int(shop_id)
    return _default_shop_id(db)


def expire_stale_signals(db: Session) -> int:
    """Markeer actieve signalen met verstreken valid_until als expired."""
    now = datetime.utcnow()
    n = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.status == "active",
        models.IntelligenceSignal.valid_until.isnot(None),
        models.IntelligenceSignal.valid_until < now,
    ).update({"status": "expired"}, synchronize_session=False)
    return n


def auto_resolve_signals(
    db: Session,
    *,
    engine: str,
    still_active: set[tuple[str, str]],
    signal_types: Optional[list[str]] = None,
    entity_type: Optional[str] = None,
    shop_id: Optional[int] = None,
    entity_ids: Optional[set[str]] = None,
) -> int:
    """Zet actieve signalen op 'resolved' zodra de onderliggende conditie
    niet meer geldt (zelfde patroon als warn_suspicious_matches).

    still_active: verzameling (signal_type, entity_id)-paren die volgens de
    meest recente engine-run nog steeds aan de signaalconditie voldoen.
    Actieve signalen van deze engine (optioneel beperkt tot signal_types en
    entity_type) die NIET in die verzameling zitten worden op resolved gezet.

    Shop-scoping: de signaal-levenscyclus is shop-gescoped (net als dedupe in
    publish_signal). Zonder expliciete shop_id wordt de resolutie beperkt tot
    de default shop — dezelfde scope waarin de emitters publiceren — zodat
    signalen van andere winkels nooit worden aangeraakt op basis van
    brondata van een andere winkel.

    entity_ids: optionele beperking tot entiteiten waarvan de conditie in
    deze run daadwerkelijk geëvalueerd kón worden. Signalen van entiteiten
    buiten deze verzameling blijven ongemoeid — "niet geëvalueerd" is niet
    hetzelfde als "conditie verholpen".

    Idempotent: alleen status='active' wordt aangeraakt; al-resolved,
    superseded of expired signalen blijven ongemoeid. Er wordt niets
    opnieuw gepubliceerd. Commit gebeurt door de caller.
    """
    sid = shop_id if shop_id is not None else _default_shop_id(db)
    q = db.query(models.IntelligenceSignal).filter(
        models.IntelligenceSignal.engine == engine,
        models.IntelligenceSignal.status == "active",
        models.IntelligenceSignal.shop_id == sid,
    )
    if signal_types:
        q = q.filter(models.IntelligenceSignal.signal_type.in_(signal_types))
    if entity_type:
        q = q.filter(models.IntelligenceSignal.entity_type == entity_type)
    if entity_ids is not None:
        if not entity_ids:
            return 0
        q = q.filter(models.IntelligenceSignal.entity_id.in_(list(entity_ids)))
    n = 0
    for sig in q.all():
        if (sig.signal_type, sig.entity_id) not in still_active:
            sig.status = "resolved"
            n += 1
    if n:
        logger.info("Auto-resolved %d %s-signalen (conditie verholpen)", n, engine)
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
    valid_until: Optional[datetime] = None,
    valid_days: int = DEFAULT_VALIDITY_DAYS,
    model_version: Optional[str] = None,
    shop_id: Optional[int] = None,
) -> models.IntelligenceSignal:
    """
    Publiceer één IntelligenceSignal. Superseded automatisch een bestaand
    actief signaal met dezelfde dedupe-sleutel. Commit gebeurt door de caller
    aan het einde van de engine-run.
    """
    if not explanation or not explanation.strip():
        raise ValueError(f"Signal {engine}:{signal_type} zonder explanation is niet toegestaan (§64.9)")
    if not evidence:
        raise ValueError(f"Signal {engine}:{signal_type} zonder evidence is niet toegestaan (§64.10)")
    if not sources:
        raise ValueError(f"Signal {engine}:{signal_type} zonder sources is niet toegestaan")
    if severity not in VALID_SEVERITIES:
        logger.warning("Ongeldige severity '%s' voor %s:%s; teruggevallen op 'info'", severity, engine, signal_type)
        severity = "info"

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
        valid_until=valid_until if valid_until is not None else datetime.utcnow() + timedelta(days=valid_days),
        model_version=model_version,
        dedupe_key=dedupe_key,
    )
    db.add(signal)
    return signal
