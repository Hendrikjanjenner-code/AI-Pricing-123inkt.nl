"""Modelgovernance API (§54) — registratie, versies, metrics en rollback."""
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models
from engine.model_governance import register_version, rollback_model

router = APIRouter(prefix="/api/model-registry", tags=["model-registry"])


@router.get("")
def list_models(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    entries = (
        db.query(models.ModelRegistryEntry)
        .order_by(models.ModelRegistryEntry.model_name,
                  models.ModelRegistryEntry.created_at.desc())
        .all()
    )
    per_model: dict[str, list] = {}
    for e in entries:
        per_model.setdefault(e.model_name, []).append({
            "id": e.id,
            "versie": e.version,
            "status": e.status,
            "metrics": e.metrics or {},
            "config": e.config or {},
            "omschrijving": e.description,
            "geactiveerd_op": e.activated_at.isoformat() if e.activated_at else None,
            "gedeactiveerd_op": e.deactivated_at.isoformat() if e.deactivated_at else None,
            "aangemaakt_door": e.created_by,
            "aangemaakt_op": e.created_at.isoformat() if e.created_at else None,
        })
    return {
        "modellen": [
            {"model_name": name, "actieve_versie": next((v["versie"] for v in versies if v["status"] == "active"), None),
             "versies": versies}
            for name, versies in sorted(per_model.items())
        ]
    }


class RegisterVersionRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    description: Optional[str] = None
    config: Optional[dict] = None   # parameterset van deze versie; erft anders van actieve versie
    activate: bool = True


@router.post("", status_code=201)
def create_version(
    req: RegisterVersionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    entry = register_version(
        db, req.model_name, req.version,
        activate=req.activate, description=req.description,
        config=req.config, created_by=current_user.username,
    )
    db.add(models.AuditLog(
        entity_type="model_registry", entity_id=str(entry.id), action="register_version",
        performed_by=current_user.username,
        details=f"Model '{req.model_name}' versie {req.version} geregistreerd",
    ))
    db.commit()
    return {"id": entry.id, "model_name": entry.model_name, "versie": entry.version, "status": entry.status}


@router.post("/{model_name}/rollback/{entry_id}")
def rollback(
    model_name: str,
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "pricing_manager")),
) -> Any:
    try:
        entry = rollback_model(db, model_name, entry_id, current_user.username)
    except ValueError as e:
        raise HTTPException(404, str(e))
    db.commit()
    return {"id": entry.id, "model_name": entry.model_name, "versie": entry.version, "status": entry.status}
