"""
Admin-only endpoints.

DELETE /api/admin/clear-data              — Verwijder alle data behalve users (standaard).
DELETE /api/admin/clear-data?include_users=true — Volledige DB-wipe incl. users.
  Na een volledige wipe worden de demo-gebruikers automatisch hersteld bij herstart
  (seed_users_only() draait altijd bij opstarten als er nog geen gebruikers zijn).
GET    /api/admin/clear-data/preview      — Toon rijen per tabel zonder te wissen.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Tabellen die standaard beschermd zijn; bij include_users=True wordt 'users' ook gewist.
_ALTIJD_BESCHERMD = {"alembic_version"}


def _ontdek_tabellen(db: Session, include_users: bool = False) -> list[str]:
    """Retourneer te legen tabellen uit het public-schema."""
    beschermd = _ALTIJD_BESCHERMD if include_users else _ALTIJD_BESCHERMD | {"users"}
    rows = db.execute(text("""
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
    """)).fetchall()
    return [r[0] for r in rows if r[0] not in beschermd]


@router.delete("/clear-data")
def clear_all_data(
    include_users: bool = Query(
        False,
        description=(
            "Zet op true voor een volledige DB-wipe inclusief gebruikers. "
            "Demo-accounts worden automatisch hersteld bij de volgende herstart."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """
    Verwijder data via TRUNCATE CASCADE.
    Standaard worden gebruikers bewaard (include_users=false).
    Bij include_users=true worden alle tabellen geleegd voor een volledige pilot-reset;
    seed_users_only() in main.py zorgt bij herstart automatisch voor een bootstrap-admin.
    """
    tabellen = _ontdek_tabellen(db, include_users=include_users)
    verwijderd: list[str] = []
    overgeslagen: list[str] = []

    for tabel in tabellen:
        try:
            db.execute(text(f'TRUNCATE TABLE "{tabel}" RESTART IDENTITY CASCADE'))
            db.commit()
            verwijderd.append(tabel)
        except Exception:
            db.rollback()
            overgeslagen.append(tabel)

    bericht = f"{len(verwijderd)} tabellen geleegd."
    if include_users:
        bericht += " Gebruikers zijn ook verwijderd — demo-accounts worden hersteld bij herstart."
    else:
        bericht += " Gebruikers zijn behouden. Importeer nieuwe data via de CSV-importmodule."

    return {
        "status": "voltooid",
        "tabellen_geleegd": verwijderd,
        "tabellen_overgeslagen": overgeslagen,
        "include_users": include_users,
        "bericht": bericht,
    }


@router.get("/clear-data/preview")
def preview_clear_data(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """Toon het aantal rijen per tabel zonder te wissen (preview)."""
    tabellen = _ontdek_tabellen(db)
    telling: list[dict] = []

    for tabel in tabellen:
        try:
            result = db.execute(text(f'SELECT COUNT(*) FROM "{tabel}"')).scalar()
            telling.append({"tabel": tabel, "rijen": result, "beschermd": False})
        except Exception:
            telling.append({"tabel": tabel, "rijen": None, "fout": "tabel onbereikbaar"})

    # Voeg beschermde tabellen toe ter info
    for tabel in BESCHERMDE_TABELLEN:
        try:
            result = db.execute(text(f'SELECT COUNT(*) FROM "{tabel}"')).scalar()
            telling.append({"tabel": tabel, "rijen": result, "beschermd": True})
        except Exception:
            pass

    telling.sort(key=lambda x: (x.get("beschermd", False), x.get("tabel", "")))
    return {"tabellen": telling}
