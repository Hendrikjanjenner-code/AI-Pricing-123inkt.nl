"""User management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    password: str
    role: str
    # Optionele afdelingscodes (taak 219); zonder opgave krijgt de gebruiker
    # de standaardafdeling die bij zijn rol hoort.
    departments: Optional[list[str]] = None


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


def _user_out(u: models.User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("")
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    users = db.query(models.User).all()
    return [_user_out(u) for u in users]


@router.post("", status_code=201)
def create_user(
    req: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    if db.query(models.User).filter(models.User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(models.User).filter(models.User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    if req.role not in auth_utils.VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    user = models.User(
        username=req.username,
        email=req.email,
        full_name=req.full_name,
        hashed_password=auth_utils.hash_password(req.password),
        role=req.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    # Afdelingskoppeling (taak 219): expliciet opgegeven of rol-default.
    import authz
    authz.ensure_user_authz_defaults(db, user, req.departments)
    db.commit()
    return _user_out(user)


@router.patch("/{id}")
def update_user(
    id: int,
    req: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    user = db.query(models.User).filter(models.User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if req.email is not None:
        user.email = req.email
    if req.full_name is not None:
        user.full_name = req.full_name
    if req.role is not None:
        if req.role not in auth_utils.VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = req.role
    if req.is_active is not None:
        user.is_active = req.is_active
    db.commit()
    db.refresh(user)
    # Rol- of statuswijziging beïnvloedt de effectieve permissies direct.
    import authz
    authz.invalidate_permission_cache(user.id)
    return _user_out(user)


@router.delete("/{id}")
def delete_user(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    user = db.query(models.User).filter(models.User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}
