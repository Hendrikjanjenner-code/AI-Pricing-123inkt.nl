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
    # Concurrentscores (taak #247): configureerbare drempels & gewichten.
    # Drempel-lijsten zijn oplopende grenzen tussen de 5 size-klassen.
    "strength_config": {
        # Company size-drempels per signaal (index 0..4 = micro..enterprise)
        "size_revenue_bounds_meur": [2, 10, 50, 250],
        "size_employee_bounds": [10, 50, 250, 1000],
        "size_country_bounds": [1, 3, 8, 15],       # operationeel actieve landen
        "size_warehouse_bounds": [1, 2, 5, 10],
        # Geographic scale: grenzen op aantal landen (nationaal→globaal)
        "geo_country_bounds": [1, 3, 8, 15],
        # Score-gewichten (procenten, per groep samen 100)
        "operational_weights": {
            "fulfilment_control": 30, "delivery": 30,
            "warehouse_scale": 20, "availability": 20,
        },
        "business_weights": {
            "company_size": 30, "geographic_scale": 25,
            "assortment_breadth": 20, "financial_health": 25,
        },
        "procurement_weights": {
            "company_size": 40, "corporate_backing": 30,
            "purchasing_scale": 15, "private_label": 15,
        },
        "future_threat_weights": {
            "growth": 35, "expansion": 25, "acquisitions": 15,
            "capability_investments": 15, "supplier_overlap": 10,
        },
        "slow_run_threshold_seconds": 60.0,
    },
}

WEIGHT_KEYS = set(DEFAULTS["relevance_weights"].keys())
STRENGTH_WEIGHT_GROUPS = [k for k in DEFAULTS["strength_config"]
                          if k.endswith("_weights")]
STRENGTH_BOUND_KEYS = [k for k in DEFAULTS["strength_config"]
                       if k.endswith("_bounds") or k.endswith("_bounds_meur")]


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
        "strength_config": _copy_strength_defaults(),
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
            elif key == "strength_config":
                sc = stored.get("strength_config")
                if isinstance(sc, dict):
                    _merge_strength_config(merged["strength_config"], sc)
            elif key in stored:
                merged[key] = stored[key]
    return merged


def _copy_strength_defaults() -> dict:
    out: dict = {}
    for k, v in DEFAULTS["strength_config"].items():
        out[k] = dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v)
    return out


def _merge_strength_config(target: dict, stored: dict) -> None:
    """Deep-merge alleen bekende sleutels, zodat oude rijen nieuwe defaults
    behouden en onbekende sleutels genegeerd worden."""
    for k, default in DEFAULTS["strength_config"].items():
        if k not in stored:
            continue
        v = stored[k]
        if isinstance(default, dict):
            if isinstance(v, dict):
                for sk in default:
                    if sk in v:
                        target[k][sk] = v[sk]
        else:
            target[k] = v


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

    if "strength_config" in payload:
        sc = payload["strength_config"]
        if not isinstance(sc, dict):
            errors.append("strength_config moet een object zijn")
        else:
            unknown = set(sc.keys()) - set(DEFAULTS["strength_config"].keys())
            if unknown:
                errors.append(
                    f"Onbekende strength_config-sleutels: {', '.join(sorted(unknown))}")
            for k in STRENGTH_BOUND_KEYS:
                if k in sc:
                    v = sc[k]
                    if (not isinstance(v, list)
                            or len(v) != len(DEFAULTS["strength_config"][k])
                            or any(not isinstance(x, (int, float)) or isinstance(x, bool)
                                   or x <= 0 for x in v)
                            or any(v[i] >= v[i + 1] for i in range(len(v) - 1))):
                        errors.append(
                            f"{k} moet een strikt oplopende lijst positieve getallen zijn "
                            f"({len(DEFAULTS['strength_config'][k])} waarden)")
            for k in STRENGTH_WEIGHT_GROUPS:
                if k in sc:
                    w = sc[k]
                    keys = set(DEFAULTS["strength_config"][k].keys())
                    if not isinstance(w, dict) or set(w.keys()) - keys:
                        errors.append(f"{k}: onbekende of ongeldige gewichtssleutels")
                    else:
                        bad = [wk for wk, v in w.items()
                               if not isinstance(v, (int, float)) or isinstance(v, bool)
                               or not (0 <= v <= 100)]
                        if bad:
                            errors.append(
                                f"{k}: gewichten moeten getallen 0–100 zijn: {', '.join(sorted(bad))}")
                        elif set(w.keys()) == keys:
                            total = sum(float(v) for v in w.values())
                            if abs(total - 100.0) > 0.001:
                                errors.append(
                                    f"{k}: gewichten moeten samen 100% zijn (nu {total:g}%)")
            if "slow_run_threshold_seconds" in sc:
                v = sc["slow_run_threshold_seconds"]
                if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                    errors.append("strength_config.slow_run_threshold_seconds moet >= 0 zijn")
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
        elif key == "strength_config":
            sc = payload.get("strength_config")
            if isinstance(sc, dict):
                _merge_strength_config(effective["strength_config"], sc)
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
