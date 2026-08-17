"""
Modelgovernance (§54): registratie van naam/versie/metrics/status per model,
met rollback naar een eerdere versie. Per model is precies één versie 'active'.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

import models

# Default-versies voor de engines uit deze taak.
DEFAULT_MODEL_VERSIONS = {
    "basket": "v1.0.0",
    "promotion": "v1.0.0",
    "forecast_risk": "v1.0.0",
    "opportunity": "v1.0.0",
    "pricing": "v1.0.0",
}


def get_active_model(db: Session, model_name: str) -> Optional[models.ModelRegistryEntry]:
    return (
        db.query(models.ModelRegistryEntry)
        .filter(
            models.ModelRegistryEntry.model_name == model_name,
            models.ModelRegistryEntry.status == "active",
        )
        .order_by(models.ModelRegistryEntry.created_at.desc())
        .first()
    )


def ensure_active_model(
    db: Session,
    model_name: str,
    default_version: Optional[str] = None,
    description: Optional[str] = None,
    default_config: Optional[dict] = None,
) -> models.ModelRegistryEntry:
    """Geef de actieve modelversie terug; registreer de default als er geen is."""
    entry = get_active_model(db, model_name)
    if entry:
        if not entry.config and default_config:
            # Backfill: oudere entries zonder vastgelegde configuratie krijgen
            # eenmalig de huidige defaults, zodat de versie reproduceerbaar is.
            entry.config = dict(default_config)
            db.add(entry)
        return entry
    entry = models.ModelRegistryEntry(
        model_name=model_name,
        version=default_version or DEFAULT_MODEL_VERSIONS.get(model_name, "v1.0.0"),
        status="active",
        description=description,
        config=dict(default_config) if default_config else None,
        activated_at=datetime.utcnow(),
        created_by="system",
    )
    db.add(entry)
    db.flush()
    return entry


def record_run_metrics(db: Session, model_name: str, metrics: dict) -> None:
    """Sla de laatste run-metrics op bij de actieve modelversie."""
    entry = ensure_active_model(db, model_name)
    entry.metrics = {**(entry.metrics or {}), **metrics, "last_run_at": datetime.utcnow().isoformat()}
    db.add(entry)


def register_version(
    db: Session,
    model_name: str,
    version: str,
    *,
    activate: bool = True,
    description: Optional[str] = None,
    metrics: Optional[dict] = None,
    config: Optional[dict] = None,
    created_by: str = "system",
) -> models.ModelRegistryEntry:
    """Registreer een nieuwe versie; bij activate wordt de vorige superseded.

    `config` is de immutabele parameterset van deze versie. Als er geen config
    wordt meegegeven, erft de nieuwe versie de config van de huidige actieve
    versie zodat rollback altijd naar een uitvoerbare parameterset verwijst.
    """
    if config is None:
        cur = get_active_model(db, model_name)
        if cur and cur.config:
            config = dict(cur.config)
    if activate:
        for prev in db.query(models.ModelRegistryEntry).filter(
            models.ModelRegistryEntry.model_name == model_name,
            models.ModelRegistryEntry.status == "active",
        ).all():
            prev.status = "superseded"
            prev.deactivated_at = datetime.utcnow()
    entry = models.ModelRegistryEntry(
        model_name=model_name,
        version=version,
        status="active" if activate else "superseded",
        description=description,
        metrics=metrics,
        config=config,
        activated_at=datetime.utcnow() if activate else None,
        created_by=created_by,
    )
    db.add(entry)
    db.flush()
    return entry


def rollback_model(db: Session, model_name: str, target_entry_id: int, performed_by: str) -> models.ModelRegistryEntry:
    """Rollback: heractiveer een eerdere versie; huidige wordt rolled_back."""
    target = db.query(models.ModelRegistryEntry).filter(
        models.ModelRegistryEntry.id == target_entry_id,
        models.ModelRegistryEntry.model_name == model_name,
    ).first()
    if not target:
        raise ValueError("Modelversie niet gevonden voor rollback")

    for cur in db.query(models.ModelRegistryEntry).filter(
        models.ModelRegistryEntry.model_name == model_name,
        models.ModelRegistryEntry.status == "active",
        models.ModelRegistryEntry.id != target.id,
    ).all():
        cur.status = "rolled_back"
        cur.deactivated_at = datetime.utcnow()

    target.status = "active"
    target.activated_at = datetime.utcnow()
    target.deactivated_at = None
    db.add(models.AuditLog(
        entity_type="model_registry",
        entity_id=str(target.id),
        action="rollback",
        performed_by=performed_by,
        details=f"Model '{model_name}' teruggerold naar versie {target.version}",
    ))
    return target


def get_active_config(db: Session, model_name: str, defaults: dict) -> dict:
    """
    Effectieve modelconfiguratie: de vastgelegde config van de ACTIEVE
    registry-versie, aangevuld met defaults voor ontbrekende sleutels.

    Engines lossen hun parameters bij elke run via deze functie op; een
    rollback naar een eerdere versie herstelt daarmee daadwerkelijk het
    gedrag (de parameterset) van die versie — niet alleen het versielabel.
    """
    entry = ensure_active_model(db, model_name, default_config=defaults)
    cfg = dict(defaults)
    if entry.config:
        cfg.update(entry.config)
    return cfg
