"""
Testhulp voor het granulaire permissiemodel (taak 219).

Veel bestaande tests maken verse viewer-/analistgebruikers aan en verwachten
het oude capability-niveau (alle GET-endpoints leesbaar). Nieuwe gebruikers
krijgen sinds taak 219 smalle rol-basisrechten; deze helper geeft een
testgebruiker dezelfde legacy view-extra's die gemigreerde bestaande
gebruikers hebben, zodat die tests hun eigenlijke onderwerp blijven testen.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import authz
import models
from database import SessionLocal


def grant_legacy_views(username: str) -> None:
    """Geef de gebruiker de legacy-permissies van zijn rol (idempotent)."""
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            return
        wanted = set(authz.LEGACY_ROLE_PERMISSIONS.get(user.role, []))
        existing = {
            c for (c,) in db.query(models.UserPermission.permission_code)
            .filter(models.UserPermission.user_id == user.id)
        }
        for code in sorted(wanted - existing):
            db.add(models.UserPermission(user_id=user.id, permission_code=code,
                                         granted_by="testsuite"))
        db.commit()
        authz.invalidate_permission_cache(user.id)
    finally:
        db.close()
