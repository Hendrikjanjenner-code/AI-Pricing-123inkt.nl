"""
Saved views & persoonlijke UI-voorkeuren (taak #221).

Saved views: filter/sorteer/kolom/dashboard-configuratie per pagina, met
sharing-niveaus:
  - private    : alleen de eigenaar (elke ingelogde gebruiker mag dit).
  - team       : zichtbaar voor iedereen; aanmaken vereist analyst of hoger.
  - department : zichtbaar voor leden van de afdeling; aanmaken vereist
                 pricing_manager/admin én lidmaatschap van de afdeling
                 (admin mag voor elke afdeling).
Een department-view kan als afdelings-default gemarkeerd worden (max. 1
per afdeling per pagina); die wordt door de frontend toegepast als de
gebruiker nog geen eigen context heeft.

Voorkeuren (/api/me/preferences/{key}): vrije JSON per sleutel, alleen
voor de ingelogde gebruiker zelf. Toegestane sleutels zijn beperkt
(favorites / recents / ui) zodat dit geen vrije opslag wordt.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
import auth as auth_utils
from database import get_db

router = APIRouter(prefix="/api/saved-views", tags=["saved-views"])
prefs_router = APIRouter(prefix="/api/me/preferences", tags=["preferences"])

SCOPES = {"private", "team", "department"}
TEAM_ROLES = {"analyst", "pricing_manager", "admin"}
DEPARTMENT_ROLES = {"pricing_manager", "admin"}
PREF_KEYS = {"favorites", "recents", "ui"}


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    page_key: str = Field(min_length=1, max_length=200)
    scope: str = "private"
    department_id: Optional[int] = None
    is_department_default: bool = False
    config: dict = Field(default_factory=dict)


def _user_department_ids(db: Session, user: models.User) -> set[int]:
    rows = db.query(models.UserDepartment.department_id).filter(
        models.UserDepartment.user_id == user.id).all()
    return {r[0] for r in rows}


def _serialize(v: models.SavedView, db: Session) -> dict:
    dept = None
    if v.department_id:
        d = db.query(models.Department).filter(models.Department.id == v.department_id).first()
        dept = {"id": d.id, "code": d.code, "name": d.name} if d else None
    owner = db.query(models.User).filter(models.User.id == v.owner_user_id).first()
    return {
        "id": v.id,
        "name": v.name,
        "page_key": v.page_key,
        "scope": v.scope,
        "department": dept,
        "department_id": v.department_id,
        "is_department_default": bool(v.is_department_default),
        "config": v.config or {},
        "owner_user_id": v.owner_user_id,
        "owner_username": owner.username if owner else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


def _check_scope_rights(db: Session, user: models.User, payload: SavedViewIn) -> None:
    if payload.scope not in SCOPES:
        raise HTTPException(status_code=422, detail="Ongeldige scope (private/team/department)")
    if payload.scope == "team" and user.role not in TEAM_ROLES:
        raise HTTPException(status_code=403, detail="Team-views vereisen rol analyst of hoger")
    if payload.scope == "department":
        if user.role not in DEPARTMENT_ROLES:
            raise HTTPException(status_code=403,
                                detail="Department-views vereisen rol pricing_manager of admin")
        if not payload.department_id:
            raise HTTPException(status_code=422, detail="department_id is verplicht bij scope=department")
        dept = db.query(models.Department).filter(
            models.Department.id == payload.department_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Afdeling niet gevonden")
        if user.role != "admin" and payload.department_id not in _user_department_ids(db, user):
            raise HTTPException(status_code=403,
                                detail="Alleen leden van de afdeling kunnen department-views aanmaken")
    else:
        if payload.is_department_default:
            raise HTTPException(status_code=422,
                                detail="Alleen department-views kunnen afdelings-default zijn")


def _clear_other_defaults(db: Session, view: models.SavedView) -> None:
    """Max. 1 default per afdeling per pagina."""
    (db.query(models.SavedView)
       .filter(models.SavedView.department_id == view.department_id,
               models.SavedView.page_key == view.page_key,
               models.SavedView.is_department_default.is_(True),
               models.SavedView.id != view.id)
       .update({"is_department_default": False}, synchronize_session=False))


@router.get("")
def list_saved_views(
    page_key: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Eigen views + team-views + department-views van eigen afdeling(en)."""
    V = models.SavedView
    dept_ids = _user_department_ids(db, current_user)
    q = db.query(V)
    if page_key:
        q = q.filter(V.page_key.in_([page_key, "*"]))
    views = q.order_by(V.updated_at.desc()).all()
    visible = []
    for v in views:
        if v.owner_user_id == current_user.id or v.scope == "team":
            visible.append(v)
        elif v.scope == "department" and (
                current_user.role == "admin" or v.department_id in dept_ids):
            visible.append(v)
    return {"views": [_serialize(v, db) for v in visible]}


@router.get("/department-default")
def get_department_default(
    page_key: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Default-view voor de (primaire) afdeling van de gebruiker op deze pagina."""
    dept_ids = _user_department_ids(db, current_user)
    if not dept_ids:
        return {"view": None}
    V = models.SavedView
    v = (db.query(V)
         .filter(V.scope == "department",
                 V.department_id.in_(dept_ids),
                 V.page_key.in_([page_key, "*"]),
                 V.is_department_default.is_(True))
         .order_by(V.updated_at.desc())
         .first())
    return {"view": _serialize(v, db) if v else None}


@router.post("", status_code=201)
def create_saved_view(
    payload: SavedViewIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _check_scope_rights(db, current_user, payload)
    view = models.SavedView(
        name=payload.name.strip(),
        page_key=payload.page_key,
        scope=payload.scope,
        department_id=payload.department_id if payload.scope == "department" else None,
        is_department_default=payload.is_department_default,
        config=payload.config,
        owner_user_id=current_user.id,
    )
    db.add(view)
    db.flush()
    if view.is_department_default:
        _clear_other_defaults(db, view)
    db.commit()
    db.refresh(view)
    return _serialize(view, db)


def _get_editable(db: Session, view_id: int, user: models.User) -> models.SavedView:
    v = db.query(models.SavedView).filter(models.SavedView.id == view_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="View niet gevonden")
    if v.owner_user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Alleen de eigenaar of een admin mag deze view wijzigen")
    return v


@router.put("/{view_id}")
def update_saved_view(
    view_id: int,
    payload: SavedViewIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    v = _get_editable(db, view_id, current_user)
    _check_scope_rights(db, current_user, payload)
    v.name = payload.name.strip()
    v.page_key = payload.page_key
    v.scope = payload.scope
    v.department_id = payload.department_id if payload.scope == "department" else None
    v.is_department_default = payload.is_department_default
    v.config = payload.config
    v.updated_at = datetime.utcnow()
    if v.is_department_default:
        _clear_other_defaults(db, v)
    db.commit()
    db.refresh(v)
    return _serialize(v, db)


@router.delete("/{view_id}")
def delete_saved_view(
    view_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    v = _get_editable(db, view_id, current_user)
    db.delete(v)
    db.commit()
    return {"deleted": True}


# ── Persoonlijke voorkeuren ─────────────────────────────────────────────────

@prefs_router.get("/{pref_key}")
def get_preference(
    pref_key: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    if pref_key not in PREF_KEYS:
        raise HTTPException(status_code=404, detail="Onbekende voorkeurssleutel")
    row = (db.query(models.UserUiPreference)
           .filter(models.UserUiPreference.user_id == current_user.id,
                   models.UserUiPreference.pref_key == pref_key)
           .first())
    return {"key": pref_key, "value": row.value if row else None}


@prefs_router.put("/{pref_key}")
def put_preference(
    pref_key: str,
    value: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    if pref_key not in PREF_KEYS:
        raise HTTPException(status_code=404, detail="Onbekende voorkeurssleutel")
    row = (db.query(models.UserUiPreference)
           .filter(models.UserUiPreference.user_id == current_user.id,
                   models.UserUiPreference.pref_key == pref_key)
           .first())
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        row = models.UserUiPreference(user_id=current_user.id, pref_key=pref_key, value=value)
        db.add(row)
    db.commit()
    return {"key": pref_key, "value": value}
