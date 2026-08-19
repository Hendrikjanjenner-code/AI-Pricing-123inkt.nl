"""
Competition-instellingen per shop (persistent).

Drempels voor discovery/matching en relevantiegewichten worden per winkel
opgeslagen in `competition_setting` en gelezen door de engines in plaats van
hardcoded waarden. Ontbrekende sleutels vallen terug op DEFAULTS.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

import models

# Confidences als fractie 0–1; gewichten als procenten (som = 100).
DEFAULTS: dict = {
    "min_discovery_confidence": 0.60,
    "auto_approve_threshold": 0.90,
    "auto_discovery_enabled": False,
    "lookback_days": 30,
    "min_match_confidence": 0.50,
    "relevance_weights": {
        "pricing": 25,
        "assortment": 30,
        "traffic": 20,
        "authority": 15,
        "coverage": 10,
    },
}

WEIGHT_KEYS = set(DEFAULTS["relevance_weights"].keys())


def get_settings(db: Session, shop_id: int) -> dict:
    """Effectieve instellingen voor een shop: opgeslagen waarden gemerged
    over de defaults, zodat nieuwe sleutels altijd een waarde hebben."""
    row = (
        db.query(models.CompetitionSetting)
        .filter(models.CompetitionSetting.shop_id == shop_id)
        .first()
    )
    merged = {
        **DEFAULTS,
        "relevance_weights": dict(DEFAULTS["relevance_weights"]),
    }
    if row and isinstance(row.settings, dict):
        stored = row.settings
        for key in DEFAULTS:
            if key == "relevance_weights":
                weights = stored.get("relevance_weights")
                if isinstance(weights, dict):
                    for wk in WEIGHT_KEYS:
                        if wk in weights:
                            merged["relevance_weights"][wk] = weights[wk]
            elif key in stored:
                merged[key] = stored[key]
    return merged


def _validate(payload: dict) -> list[str]:
    errors: list[str] = []

    def check_fraction(key: str):
        if key in payload:
            v = payload[key]
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= float(v) <= 1.0):
                errors.append(f"{key} moet een getal tussen 0 en 1 zijn")

    check_fraction("min_discovery_confidence")
    check_fraction("auto_approve_threshold")
    check_fraction("min_match_confidence")

    if "lookback_days" in payload:
        v = payload["lookback_days"]
        if not isinstance(v, int) or isinstance(v, bool) or not (7 <= v <= 180):
            errors.append("lookback_days moet een geheel getal tussen 7 en 180 zijn")

    if "auto_discovery_enabled" in payload and not isinstance(payload["auto_discovery_enabled"], bool):
        errors.append("auto_discovery_enabled moet true of false zijn")

    if "relevance_weights" in payload:
        weights = payload["relevance_weights"]
        if not isinstance(weights, dict):
            errors.append("relevance_weights moet een object zijn")
        else:
            unknown = set(weights.keys()) - WEIGHT_KEYS
            if unknown:
                errors.append(f"Onbekende gewichtssleutels: {', '.join(sorted(unknown))}")
            bad = [k for k, v in weights.items()
                   if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0 <= v <= 100)]
            if bad:
                errors.append(f"Gewichten moeten getallen tussen 0 en 100 zijn: {', '.join(sorted(bad))}")
            if not unknown and not bad and set(weights.keys()) == WEIGHT_KEYS:
                total = sum(float(v) for v in weights.values())
                if abs(total - 100.0) > 0.001:
                    errors.append(f"Gewichten moeten samen 100% zijn (nu {total:g}%)")
    return errors


def upsert_settings(db: Session, shop_id: int, payload: dict, username: str) -> dict:
    """Valideer en sla instellingen op voor een shop. Onbekende sleutels worden
    genegeerd; opgeslagen wordt de volledige effectieve set (defaults + wijzigingen).

    Raises ValueError met een leesbare boodschap bij ongeldige input.
    """
    errors = _validate(payload)
    if errors:
        raise ValueError("; ".join(errors))

    effective = get_settings(db, shop_id)
    for key in DEFAULTS:
        if key == "relevance_weights":
            weights = payload.get("relevance_weights")
            if isinstance(weights, dict):
                for wk in WEIGHT_KEYS:
                    if wk in weights:
                        effective["relevance_weights"][wk] = weights[wk]
        elif key in payload:
            effective[key] = payload[key]

    row = (
        db.query(models.CompetitionSetting)
        .filter(models.CompetitionSetting.shop_id == shop_id)
        .first()
    )
    if row is None:
        row = models.CompetitionSetting(shop_id=shop_id)
        db.add(row)
    row.settings = effective
    row.updated_by = username
    row.updated_at = datetime.utcnow()
    db.commit()
    return effective


def default_shop_id(db: Session) -> Optional[int]:
    row = db.query(models.DimShop.id).order_by(models.DimShop.id).first()
    return row[0] if row else None
