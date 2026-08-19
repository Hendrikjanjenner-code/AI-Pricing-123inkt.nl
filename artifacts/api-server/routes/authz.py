"""
Beheer-endpoints voor het granulaire autorisatiemodel (taak 219):
- Permissiecatalogus en afdelingen (workspaces)
- Rollen & Rechten-matrix (bewerkbaar, met audittrail)
- Per-gebruiker afdelingen, extra permissies en data-scopes
Alle mutaties vereisen admin.manage en schrijven een AuditLog-rij.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import authz
import models
from auth import get_current_user, VALID_ROLES
from database import get_db

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/authz", tags=["authz"])

require_admin_manage = authz.require_permission("admin.manage")


def _audit(db: Session, user: models.User, action: str, entity_id: str,
           details: str, old_value=None, new_value=None) -> None:
    db.add(models.AuditLog(
        entity_type="authz", entity_id=entity_id, action=action,
        performed_by=user.username, details=details,
        old_value=old_value, new_value=new_value,
    ))


# ── Catalogus & me ──────────────────────────────────────────────────────────

@router.get("/permissions")
def list_permissions(current_user: models.User = Depends(get_current_user)):
    """Canonieke permissiecatalogus (voor de matrix-UI)."""
    return {"permissions": authz.PERMISSIONS}


@router.get("/me")
def my_authz(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Effectieve permissies + workspace van de ingelogde gebruiker."""
    return authz.authz_payload(db, current_user)


# ── Afdelingen ──────────────────────────────────────────────────────────────

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    workspace_domains: Optional[list[str]] = None
    default_permissions: Optional[list[str]] = None
    default_route: Optional[str] = None
    active: Optional[bool] = None


def _dept_out(d: models.Department) -> dict:
    return {
        "id": d.id, "code": d.code, "name": d.name,
        "workspace_domains": d.workspace_domains or [],
        "default_permissions": d.default_permissions or [],
        "default_route": d.default_route or "/",
        "positie": d.positie, "active": bool(d.active),
    }


@router.get("/departments")
def list_departments(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    depts = db.query(models.Department).order_by(models.Department.positie).all()
    return {"departments": [_dept_out(d) for d in depts]}


@router.patch("/departments/{dept_id}")
def update_department(
    dept_id: int,
    req: DepartmentUpdate,
    current_user: models.User = Depends(require_admin_manage),
    db: Session = Depends(get_db),
):
    dept = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Afdeling niet gevonden")
    if req.default_permissions is not None:
        unknown = set(req.default_permissions) - authz.PERMISSION_CODES
        if unknown:
            raise HTTPException(status_code=400, detail=f"Onbekende permissies: {sorted(unknown)}")
    old = _dept_out(dept)
    if req.name is not None:
        dept.name = req.name
    if req.workspace_domains is not None:
        dept.workspace_domains = req.workspace_domains
    if req.default_permissions is not None:
        dept.default_permissions = req.default_permissions
    if req.default_route is not None:
        dept.default_route = req.default_route
    if req.active is not None:
        dept.active = req.active
    _audit(db, current_user, "department_updated", dept.code,
           f"Afdeling '{dept.name}' bijgewerkt.", old_value=old, new_value=_dept_out(dept))
    db.commit()
    authz.invalidate_permission_cache()
    return _dept_out(dept)


# ── Rollen & Rechten-matrix ─────────────────────────────────────────────────

@router.get("/roles-matrix")
def get_roles_matrix(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    matrix: dict[str, list[str]] = {role: [] for role in VALID_ROLES}
    for rp in db.query(models.RolePermission).all():
        matrix.setdefault(rp.role, []).append(rp.permission_code)
    for role in matrix:
        matrix[role] = sorted(matrix[role])
    return {"roles": list(VALID_ROLES), "matrix": matrix,
            "permissions": authz.PERMISSIONS}


class RolesMatrixUpdate(BaseModel):
    matrix: dict[str, list[str]]


@router.put("/roles-matrix")
def update_roles_matrix(
    req: RolesMatrixUpdate,
    current_user: models.User = Depends(require_admin_manage),
    db: Session = Depends(get_db),
):
    for role, codes in req.matrix.items():
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Onbekende rol '{role}'")
        unknown = set(codes) - authz.PERMISSION_CODES
        if unknown:
            raise HTTPException(status_code=400, detail=f"Onbekende permissies: {sorted(unknown)}")
    # Veiligheidsklep: admin-rol behoudt altijd admin.manage.
    if "admin" in req.matrix and "admin.manage" not in req.matrix["admin"]:
        raise HTTPException(status_code=400,
                            detail="De admin-rol kan admin.manage niet verliezen")

    old: dict[str, list[str]] = {}
    for role, codes in req.matrix.items():
        old[role] = sorted(
            c for (c,) in db.query(models.RolePermission.permission_code)
            .filter(models.RolePermission.role == role)
        )
        db.query(models.RolePermission).filter(
            models.RolePermission.role == role
        ).delete(synchronize_session=False)
        for code in sorted(set(codes)):
            db.add(models.RolePermission(role=role, permission_code=code))
    _audit(db, current_user, "roles_matrix_updated", "roles-matrix",
           f"Rollen & Rechten-matrix bijgewerkt voor rollen: {sorted(req.matrix)}.",
           old_value=old, new_value={r: sorted(set(c)) for r, c in req.matrix.items()})
    db.commit()
    authz.invalidate_permission_cache()
    return get_roles_matrix(current_user, db)


# ── Per-gebruiker: afdelingen, extra permissies, scopes ─────────────────────

def _user_authz_out(db: Session, user: models.User) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "departments": [
            {"id": d.id, "code": d.code, "name": d.name}
            for d in authz.user_departments(db, user)
        ],
        "extra_permissions": sorted(
            c for (c,) in db.query(models.UserPermission.permission_code)
            .filter(models.UserPermission.user_id == user.id)
        ),
        "scopes": [
            {"scope_type": s.scope_type, "scope_value": s.scope_value}
            for s in db.query(models.UserScope).filter(models.UserScope.user_id == user.id)
        ],
        "effective_permissions": sorted(authz.effective_permissions(db, user)),
    }


@router.get("/users/{user_id}")
def get_user_authz(
    user_id: int,
    current_user: models.User = Depends(require_admin_manage),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
    return _user_authz_out(db, user)


class ScopeIn(BaseModel):
    scope_type: str    # shop / country / legal_entity
    scope_value: str


class UserAuthzUpdate(BaseModel):
    department_codes: Optional[list[str]] = None
    extra_permissions: Optional[list[str]] = None
    scopes: Optional[list[ScopeIn]] = None


@router.put("/users/{user_id}")
def update_user_authz(
    user_id: int,
    req: UserAuthzUpdate,
    current_user: models.User = Depends(require_admin_manage),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
    old = _user_authz_out(db, user)

    if req.department_codes is not None:
        depts = db.query(models.Department).filter(
            models.Department.code.in_(req.department_codes)
        ).all() if req.department_codes else []
        found = {d.code for d in depts}
        missing = set(req.department_codes) - found
        if missing:
            raise HTTPException(status_code=400, detail=f"Onbekende afdelingen: {sorted(missing)}")
        db.query(models.UserDepartment).filter(
            models.UserDepartment.user_id == user.id
        ).delete(synchronize_session=False)
        by_code = {d.code: d for d in depts}
        for i, code in enumerate(req.department_codes):
            db.add(models.UserDepartment(user_id=user.id,
                                         department_id=by_code[code].id,
                                         is_primary=(i == 0)))

    if req.extra_permissions is not None:
        unknown = set(req.extra_permissions) - authz.PERMISSION_CODES
        if unknown:
            raise HTTPException(status_code=400, detail=f"Onbekende permissies: {sorted(unknown)}")
        db.query(models.UserPermission).filter(
            models.UserPermission.user_id == user.id
        ).delete(synchronize_session=False)
        for code in sorted(set(req.extra_permissions)):
            db.add(models.UserPermission(user_id=user.id, permission_code=code,
                                         granted_by=current_user.username))

    if req.scopes is not None:
        for s in req.scopes:
            if s.scope_type not in ("shop", "country", "legal_entity"):
                raise HTTPException(status_code=400, detail=f"Onbekend scope-type '{s.scope_type}'")
            if s.scope_type == "shop":
                # user_allowed_shop_ids interpreteert shop-scopes uitsluitend als
                # numerieke DimShop.id; een code/typefout zou de gebruiker anders
                # stilletjes van alle shop-data afsnijden.
                if not str(s.scope_value).isdigit() or not db.query(
                    models.DimShop.id
                ).filter(models.DimShop.id == int(s.scope_value)).first():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Onbekende winkel-scope '{s.scope_value}': gebruik de numerieke winkel-id.",
                    )
        db.query(models.UserScope).filter(
            models.UserScope.user_id == user.id
        ).delete(synchronize_session=False)
        seen = set()
        for s in req.scopes:
            key = (s.scope_type, s.scope_value)
            if key in seen:
                continue
            seen.add(key)
            db.add(models.UserScope(user_id=user.id, scope_type=s.scope_type,
                                    scope_value=s.scope_value))

    db.flush()
    authz.invalidate_permission_cache(user.id)
    new = _user_authz_out(db, user)
    _audit(db, current_user, "user_authz_updated", str(user.id),
           f"Toegangsrechten van '{user.username}' bijgewerkt.",
           old_value=old, new_value=new)
    db.commit()
    authz.invalidate_permission_cache(user.id)
    return new
