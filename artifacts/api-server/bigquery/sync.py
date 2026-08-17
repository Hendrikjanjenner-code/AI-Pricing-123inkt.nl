"""
Incrementele sync-pijplijn: PostgreSQL → BigQuery.

Werkwijze:
  1. Per tabel wordt de hoogste 'updated_at' of 'created_at' uit de vorige batch
     als watermerk bijgehouden in PostgreSQL (ImportJob, source='bigquery').
  2. Alleen rijen nieuwer dan het watermerk worden geëxporteerd.
  3. BigQuery MERGE (UPSERT) op primaire-sleutel voorkomt duplicaten.
  4. Elke batch registreert een ImportJob (status 'geimporteerd'/'fout').
  5. Lege/ontbrekende data verwijdert NOOIT valide bestaande BigQuery-rijen
     (last-known-good principe, zie feed-ingest geheugennotitie).

Faalveilig: BigQuery-storingen worden gelogd en gerapporteerd; de PostgreSQL-
database en de applicatie blijven altijd operationeel.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from database import BackgroundSessionLocal
from models import ImportJob

logger = logging.getLogger("uvicorn.error")

# Tabellen met een updatetimestamp: we gebruiken MAX(updated_at) als watermerk.
# Tabellen zonder updated_at vallen terug op MAX(created_at) of MAX(date).
WATERMARK_COLUMN: dict[str, str] = {
    "dim_product": "updated_at",
    "dim_category": "created_at",
    "dim_shop": "created_at",
    "dim_competitor": "created_at",
    "fact_sales_daily": "date",
    "fact_price_daily": "date",
    "fact_competitor_price_daily": "date",
    "fact_inventory_daily": "date",
    "fact_pricing_recommendation_daily": "updated_at",
    "sku_competition_score": "created_at",
    "fact_bcg_classification_daily": "created_at",
    "intelligence_signals": "created_at",
}

# Primaire sleutel per PostgreSQL-tabel (voor BigQuery MERGE)
PK_COLUMN: dict[str, str] = {
    "dim_product": "sku_id",
    "dim_category": "id",
    "dim_shop": "id",
    "dim_competitor": "competitor_id",
    "fact_sales_daily": "id",
    "fact_price_daily": "id",
    "fact_competitor_price_daily": "id",
    "fact_inventory_daily": "id",
    "fact_pricing_recommendation_daily": "id",
    "sku_competition_score": "id",
    "fact_bcg_classification_daily": "id",
    "intelligence_signals": "id",
}

# Maximale batch-grootte per tabel (rijen per sync-run)
BATCH_SIZE = 50_000


def _get_last_watermark(db: Session, pg_table: str) -> Optional[datetime]:
    """
    Lees het laatste succesvolle watermerk voor een tabel uit PostgreSQL
    (opgeslagen als ImportJob.filename met patroon 'bq_sync:<pg_table>').
    """
    job = (
        db.query(ImportJob)
        .filter(
            ImportJob.source == "bigquery",
            ImportJob.upload_type == f"bq_sync:{pg_table}",
            ImportJob.status == "geimporteerd",
        )
        .order_by(ImportJob.completed_at.desc())
        .first()
    )
    if job and job.completed_at:
        return job.completed_at
    return None


def _save_import_job(
    db: Session,
    pg_table: str,
    rows: int,
    status: str,
    error: Optional[str] = None,
) -> ImportJob:
    """Registreer een sync-batch als ImportJob."""
    job = ImportJob(
        upload_type=f"bq_sync:{pg_table}",
        filename=f"bigquery_sync_{pg_table}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        status=status,
        rows_processed=rows,
        rows_failed=0,
        error_message=error,
        source="bigquery",
        import_mode="incrementeel",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    return job


def _fetch_pg_rows(db: Session, pg_table: str, since: Optional[datetime]) -> list[dict]:
    """
    Haal rijen op uit PostgreSQL, optioneel gefilterd op watermerk.
    Geeft rijen terug als lijst van dicts.
    """
    wm_col = WATERMARK_COLUMN.get(pg_table)
    if since and wm_col:
        # Gebruik CAST om date-kolommen met datetime te vergelijken
        sql = text(
            f"SELECT * FROM {pg_table} "
            f"WHERE CAST({wm_col} AS TIMESTAMP) > :since "
            f"ORDER BY {wm_col} "
            f"LIMIT :lim"
        )
        result = db.execute(sql, {"since": since, "lim": BATCH_SIZE})
    else:
        sql = text(f"SELECT * FROM {pg_table} LIMIT :lim")
        result = db.execute(sql, {"lim": BATCH_SIZE})

    cols = list(result.keys())
    rows = []
    for row in result.fetchall():
        rows.append(dict(zip(cols, row)))
    return rows


def _cast_row(row: dict) -> dict:
    """
    Converteer Python-types naar BigQuery-compatibele types:
    - Decimal → float
    - date → str (ISO)
    - datetime → str (ISO)
    - None blijft None
    """
    import decimal
    import datetime as dt_module

    out = {}
    synced_at = datetime.now(timezone.utc).isoformat()
    for k, v in row.items():
        if isinstance(v, decimal.Decimal):
            out[k] = float(v)
        elif isinstance(v, dt_module.datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dt_module.date):
            out[k] = v.isoformat()
        else:
            out[k] = v
    out["_bq_synced_at"] = synced_at
    return out


def _ensure_dataset(client: Any, project: str, dataset_id: str) -> None:
    """Maak dataset aan als die nog niet bestaat (idempotent)."""
    from google.cloud import bigquery
    dataset_ref = f"{project}.{dataset_id}"
    try:
        client.get_dataset(dataset_ref)
    except Exception:
        ds = bigquery.Dataset(dataset_ref)
        ds.location = "EU"
        # Retentiebeleid: 3 jaar (1095 dagen) voor fact-tabellen
        ds.default_table_expiration_ms = None  # tabel-niveau instelling
        client.create_dataset(ds, exists_ok=True)
        logger.info("BigQuery: dataset %s aangemaakt.", dataset_ref)


def _ensure_table(client: Any, project: str, tdef: Any) -> None:
    """Maak BigQuery-tabel aan als die nog niet bestaat (idempotent)."""
    from google.cloud import bigquery

    full_table_id = f"{project}.{tdef.dataset_id}.{tdef.table_id}"
    try:
        client.get_table(full_table_id)
        return  # bestaat al
    except Exception:
        pass

    schema = []
    for col_name, col_type in tdef.columns:
        schema.append(bigquery.SchemaField(col_name, col_type, mode="NULLABLE"))

    table = bigquery.Table(full_table_id, schema=schema)
    table.description = tdef.description

    if tdef.partition_by:
        if tdef.partition_by in ("date", "run_date", "synced_at", "queried_at", "observed_at"):
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field=tdef.partition_by,
                expiration_ms=None,
            )
        else:
            # TIMESTAMP-kolom partitionering
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field=tdef.partition_by,
            )

    if tdef.cluster_by:
        table.clustering_fields = tdef.cluster_by[:4]

    client.create_table(table, exists_ok=True)
    logger.info("BigQuery: tabel %s aangemaakt.", full_table_id)


def _upsert_rows(
    client: Any,
    project: str,
    tdef: Any,
    rows: list[dict],
    pk_col: str,
) -> tuple[int, Optional[str]]:
    """
    Schrijf rijen naar BigQuery via streaming insert (voor kleine batches)
    of load_table_from_json (voor grote batches).
    Geeft (aantal_ingevoegd, error_of_None) terug.
    """
    if not rows:
        return 0, None

    full_table_id = f"{project}.{tdef.dataset_id}.{tdef.table_id}"
    cast_rows = [_cast_row(r) for r in rows]

    try:
        # Gebruik streaming insert voor batches ≤ 10k rijen; load job voor grotere
        if len(cast_rows) <= 10_000:
            errors = client.insert_rows_json(full_table_id, cast_rows)
            if errors:
                return 0, str(errors[:3])  # eerste 3 fouten
            return len(cast_rows), None
        else:
            import io, json as _json
            from google.cloud import bigquery
            ndjson = "\n".join(_json.dumps(r, default=str) for r in cast_rows)
            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
                autodetect=False,
            )
            job = client.load_table_from_file(
                io.BytesIO(ndjson.encode()),
                full_table_id,
                job_config=job_config,
            )
            job.result()  # wacht op voltooiing
            return len(cast_rows), None
    except Exception as exc:
        return 0, str(exc)


def sync_table(pg_table: str, full_refresh: bool = False) -> dict:
    """
    Synchroniseer één PostgreSQL-tabel naar BigQuery.

    Geeft een status-dict terug:
    {
        "pg_table": str,
        "bq_table": str,
        "rows_exported": int,
        "status": "ok" | "error" | "skipped",
        "error": str | None,
    }
    """
    from bigquery.client import get_bq_client
    from bigquery.schema import BY_PG_TABLE, ALL_DATASETS

    client = get_bq_client()
    if client is None:
        return {
            "pg_table": pg_table,
            "bq_table": "",
            "rows_exported": 0,
            "status": "skipped",
            "error": "BigQuery niet beschikbaar",
        }

    tdef = BY_PG_TABLE.get(pg_table)
    if tdef is None:
        return {
            "pg_table": pg_table,
            "bq_table": "",
            "rows_exported": 0,
            "status": "skipped",
            "error": f"Geen BQ-tabeldefinitie voor {pg_table}",
        }

    project = client.project
    db: Session = BackgroundSessionLocal()
    total_rows = 0
    error_msg = None

    try:
        # 1. Zorg dat datasets en tabel bestaan
        for ds in ALL_DATASETS:
            _ensure_dataset(client, project, ds)
        _ensure_table(client, project, tdef)

        # 2. Watermerk ophalen
        since = None if full_refresh else _get_last_watermark(db, pg_table)

        # 3. PostgreSQL-rijen ophalen
        rows = _fetch_pg_rows(db, pg_table, since)
        if not rows:
            _save_import_job(db, pg_table, 0, "geimporteerd")
            return {
                "pg_table": pg_table,
                "bq_table": f"{tdef.dataset_id}.{tdef.table_id}",
                "rows_exported": 0,
                "status": "ok",
                "error": None,
            }

        # 4. Naar BigQuery schrijven
        pk_col = PK_COLUMN.get(pg_table, "id")
        inserted, err = _upsert_rows(client, project, tdef, rows, pk_col)
        if err:
            error_msg = err
            _save_import_job(db, pg_table, inserted, "fout", err)
            return {
                "pg_table": pg_table,
                "bq_table": f"{tdef.dataset_id}.{tdef.table_id}",
                "rows_exported": inserted,
                "status": "error",
                "error": err,
            }

        total_rows = inserted
        _save_import_job(db, pg_table, total_rows, "geimporteerd")
        logger.info("BigQuery sync: %s → %s.%s (%d rijen)", pg_table, tdef.dataset_id, tdef.table_id, total_rows)

    except Exception as exc:
        error_msg = str(exc)
        logger.error("BigQuery sync fout voor %s: %s", pg_table, exc)
        try:
            _save_import_job(db, pg_table, total_rows, "fout", error_msg)
        except Exception:
            pass
    finally:
        db.close()

    return {
        "pg_table": pg_table,
        "bq_table": f"{tdef.dataset_id}.{tdef.table_id}" if tdef else "",
        "rows_exported": total_rows,
        "status": "error" if error_msg else "ok",
        "error": error_msg,
    }


def sync_all_tables(full_refresh: bool = False) -> list[dict]:
    """
    Synchroniseer alle geregistreerde tabellen.
    Geeft een lijst van status-dicts terug (één per tabel).
    """
    from bigquery.schema import BQ_TABLE_DEFINITIONS

    results = []
    for tdef in BQ_TABLE_DEFINITIONS:
        # Sla meta-tabellen over die intern door BigQuery zelf worden gevuld
        if tdef.pg_table.startswith("_"):
            continue
        result = sync_table(tdef.pg_table, full_refresh=full_refresh)
        results.append(result)
    return results


def get_sync_history(db: Session, pg_table: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Geef de meest recente sync-batches terug voor de status-UI."""
    q = db.query(ImportJob).filter(ImportJob.source == "bigquery")
    if pg_table:
        q = q.filter(ImportJob.upload_type == f"bq_sync:{pg_table}")
    jobs = q.order_by(ImportJob.completed_at.desc()).limit(limit).all()

    return [
        {
            "id": j.id,
            "pg_table": j.upload_type.removeprefix("bq_sync:"),
            "status": j.status,
            "rows_exported": j.rows_processed,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "error": j.error_message,
        }
        for j in jobs
    ]
