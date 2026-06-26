"""
Admin-only endpoints.

DELETE /api/admin/clear-data              — Verwijder alle data behalve users (standaard).
DELETE /api/admin/clear-data?include_users=true — Volledige DB-wipe incl. users.
  Na een volledige wipe worden de demo-gebruikers automatisch hersteld bij herstart
  (seed_users_only() draait altijd bij opstarten als er nog geen gebruikers zijn).
GET    /api/admin/clear-data/preview      — Toon rijen per tabel zonder te wissen.
GET    /api/admin/sync/status             — Verbindingsstatus DRS + GA4.
POST   /api/admin/sync                    — Start handmatige sync van DRS én GA4.
"""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
import models
import auth as auth_utils
from connectors import drs_connector, ga4_connector

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

    telling.sort(key=lambda x: (x.get("beschermd", False), x.get("tabel", "")))
    return {"tabellen": telling}


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------

@router.get("/sync/status")
def sync_status(
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """
    Controleer de verbindingsstatus van DRS en GA4 zonder data op te halen.

    Geen authenticatie richting de externe APIs; valideert alleen of de
    omgevingsvariabelen aanwezig en de endpoints bereikbaar zijn.
    """
    drs_status = drs_connector.check_connection()
    ga4_status = ga4_connector.check_connection()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "drs": drs_status,
        "ga4": ga4_status,
    }


@router.post("/sync")
def trigger_sync(
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """
    Start een handmatige datasync van DRS én GA4.

    DRS:  haalt productcatalogus, verkoopdata (laatste 30 dagen),
          voorraadstanden en prijshistorie (laatste 90 dagen) op.
    GA4:  haalt traffic + conversiedata (laatste 30 dagen) op.

    De opgehaalde data wordt momenteel teruggestuurd als JSON-samenvatting.
    Schrijf de records naar de DB wanneer de datapijplijn live gaat.
    """
    from datetime import date, timedelta

    today = date.today().isoformat()
    date_30d = (date.today() - timedelta(days=30)).isoformat()

    result: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "drs": {"status": "skipped", "message": "", "counts": {}},
        "ga4": {"status": "skipped", "message": "", "counts": {}},
    }

    # --- DRS sync ---
    try:
        drs_connector._get_credentials()  # gooit ConnectorError als niet geconfigureerd
    except drs_connector.ConnectorError as exc:
        result["drs"] = {"status": "not_configured", "message": str(exc), "counts": {}}
    else:
        drs_counts: dict = {}
        drs_errors: list[str] = []

        try:
            products = drs_connector.fetch_product_catalog()
            drs_counts["products"] = len(products)
        except drs_connector.ConnectorError as exc:
            drs_errors.append(f"products: {exc}")

        try:
            sales = drs_connector.fetch_sales_history(date_from=date_30d, date_to=today)
            drs_counts["sales_records"] = len(sales)
        except drs_connector.ConnectorError as exc:
            drs_errors.append(f"sales: {exc}")

        try:
            stock = drs_connector.fetch_stock_levels()
            drs_counts["stock_records"] = len(stock)
        except drs_connector.ConnectorError as exc:
            drs_errors.append(f"stock: {exc}")

        try:
            sku_ids = [p["sku_code"] for p in products] if "products" in drs_counts else []
            if sku_ids:
                prices = drs_connector.fetch_price_history(sku_ids=sku_ids[:50], lookback_days=90)
                drs_counts["price_records"] = len(prices)
        except drs_connector.ConnectorError as exc:
            drs_errors.append(f"prices: {exc}")

        result["drs"] = {
            "status": "error" if drs_errors else "ok",
            "message": "; ".join(drs_errors) if drs_errors else "DRS sync voltooid.",
            "counts": drs_counts,
        }

    # --- GA4 sync ---
    try:
        ga4_connector._get_credentials()
    except ga4_connector.ConnectorError as exc:
        result["ga4"] = {"status": "not_configured", "message": str(exc), "counts": {}}
    else:
        ga4_counts: dict = {}
        ga4_errors: list[str] = []

        try:
            traffic = ga4_connector.fetch_traffic_data(date_from=date_30d, date_to=today)
            ga4_counts["traffic_records"] = len(traffic)
        except ga4_connector.ConnectorError as exc:
            ga4_errors.append(f"traffic: {exc}")

        try:
            conversions = ga4_connector.fetch_conversion_data(date_from=date_30d, date_to=today)
            ga4_counts["conversion_records"] = len(conversions)
        except ga4_connector.ConnectorError as exc:
            ga4_errors.append(f"conversions: {exc}")

        try:
            channels = ga4_connector.fetch_channel_breakdown(date_from=date_30d, date_to=today)
            ga4_counts["channel_records"] = len(channels)
        except ga4_connector.ConnectorError as exc:
            ga4_errors.append(f"channels: {exc}")

        result["ga4"] = {
            "status": "error" if ga4_errors else "ok",
            "message": "; ".join(ga4_errors) if ga4_errors else "GA4 sync voltooid.",
            "counts": ga4_counts,
        }

    return result


# ---------------------------------------------------------------------------
# Schema-migratiegeschiedenis
# ---------------------------------------------------------------------------

def _migratie_rijen(db: Session) -> list[models.SchemaMigration]:
    """Haal alle geregistreerde auto-migraties op, nieuwste eerst."""
    return (
        db.query(models.SchemaMigration)
        .order_by(models.SchemaMigration.applied_at.desc())
        .all()
    )


@router.get("/schema-migrations")
def list_schema_migrations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """
    Toon de auditgeschiedenis van automatisch toegepaste schemawijzigingen
    (kolommen die de auto-migrator aan bestaande tabellen heeft toegevoegd),
    met tijdstempel. Nieuwste wijziging eerst.
    """
    rijen = _migratie_rijen(db)
    return {
        "aantal": len(rijen),
        "migraties": [
            {
                "id": r.id,
                "change_key": r.change_key,
                "change_type": r.change_type,
                "table_name": r.table_name,
                "column_name": r.column_name,
                "ddl": r.ddl,
                "applied_at": r.applied_at.isoformat() if r.applied_at else None,
            }
            for r in rijen
        ],
    }


@router.get("/schema-migrations/export")
def export_schema_migrations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """Exporteer de schema-migratiegeschiedenis als CSV-download."""
    rijen = _migratie_rijen(db)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "change_key", "change_type", "table_name", "column_name", "ddl", "applied_at"]
    )
    for r in rijen:
        writer.writerow(
            [
                r.id,
                r.change_key,
                r.change_type,
                r.table_name,
                r.column_name,
                r.ddl,
                r.applied_at.isoformat() if r.applied_at else "",
            ]
        )
    buffer.seek(0)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="schema_migrations_{stamp}.csv"'
        },
    )
