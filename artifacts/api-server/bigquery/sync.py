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

# Primaire sleutel per PostgreSQL-tabel (voor BigQuery MERGE). Een lijst
# betekent een samengestelde MERGE-sleutel (bijv. shop-gescopeerde producten).
PK_COLUMN: dict[str, str | list[str]] = {
    "dim_product": ["shop_id", "sku_id"],
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

# Normalisatiewaarde voor NULL-watermerken: moet exact overeenkomen met het
# COALESCE(..., TIMESTAMP 'epoch') in _fetch_pg_rows, anders pagineert een
# pagina vol NULL-watermerken eindeloos opnieuw.
EPOCH = datetime(1970, 1, 1)


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
    if not job:
        return None
    # Voorkeur: het werkelijke maximum bron-watermerk van de vorige export
    # (opgeslagen in warnings_json). Alleen als dat ontbreekt (oude jobs)
    # vallen we terug op completed_at.
    wj = job.warnings_json if isinstance(job.warnings_json, dict) else {}
    wm = wj.get("watermark")
    if wm:
        try:
            return datetime.fromisoformat(wm)
        except ValueError:
            pass
    return job.completed_at


def _save_import_job(
    db: Session,
    pg_table: str,
    rows: int,
    status: str,
    error: Optional[str] = None,
    watermark: Optional[datetime] = None,
    import_mode: str = "incrementeel",
) -> ImportJob:
    """Registreer een sync-batch als ImportJob, incl. het geëxporteerde max-watermerk."""
    job = ImportJob(
        batch_id=str(uuid.uuid4()),
        upload_type=f"bq_sync:{pg_table}",
        filename=f"bigquery_sync_{pg_table}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        status=status,
        rows_processed=rows,
        rows_failed=0,
        rows_duplicates=0,
        error_log=([{"rij": None, "veld": None, "bericht": error}] if error else []),
        error_message=error,
        source="bigquery",
        import_mode=import_mode,
        completed_at=datetime.now(timezone.utc),
        warnings_json={"watermark": watermark.isoformat()} if watermark else None,
    )
    db.add(job)
    db.commit()
    return job


def _fetch_pg_rows(
    db: Session,
    pg_table: str,
    since: Optional[datetime],
    last_key: Optional[tuple] = None,
) -> list[dict]:
    """
    Haal één pagina rijen op uit PostgreSQL, gesorteerd op (watermerk, pk) met
    keyset-paginatie zodat de aanroeper kan doorlopen tot de bron is uitgeput.

    - since: inclusief filter (>=) op het watermerk. Inclusief, zodat updates
      met hetzelfde datum-watermerk niet worden gemist; de MERGE in BigQuery
      maakt het opnieuw verwerken van rijen idempotent.
    - last_key: (watermark, pk) van de laatste rij van de vorige pagina; alleen
      rijen strikt ná deze sleutel worden opgehaald (deterministische
      tie-breaker op pk).
    """
    wm_col = WATERMARK_COLUMN.get(pg_table)
    pk = PK_COLUMN.get(pg_table, "id")
    # Tie-break kolom: laatste element van een samengestelde sleutel
    pk_col = pk[-1] if isinstance(pk, list) else pk
    conds: list[str] = []
    params: dict = {"lim": BATCH_SIZE}

    if wm_col:
        # NULL-watermerken (rijen zonder created_at/updated_at) mogen nooit
        # buiten de keyset-vergelijking vallen: COALESCE naar epoch zodat ze
        # deterministisch vooraan sorteren én meegenomen worden.
        wm_expr = f"COALESCE(CAST({wm_col} AS TIMESTAMP), TIMESTAMP 'epoch')"
        if since is not None:
            # NULL-watermerken kunnen nooit "nieuwer dan since" zijn; neem ze
            # elke run expliciet mee — de MERGE in BigQuery is idempotent, dus
            # herverwerken is veilig en ze raken nooit permanent uitgesloten.
            conds.append(f"({wm_expr} >= :since OR {wm_col} IS NULL)")
            params["since"] = since
        if last_key is not None:
            conds.append(f"({wm_expr}, {pk_col}) > (:lk_wm, :lk_pk)")
            lk_wm, lk_pk = last_key
            params["lk_wm"] = lk_wm if lk_wm is not None else EPOCH
            params["lk_pk"] = lk_pk
        order = f"{wm_expr}, {pk_col}"
    else:
        if last_key is not None:
            conds.append(f"{pk_col} > :lk_pk")
            params["lk_pk"] = last_key[1]
        order = pk_col

    where = f"WHERE {' AND '.join(conds)} " if conds else ""
    sql = text(f"SELECT * FROM {pg_table} {where}ORDER BY {order} LIMIT :lim")
    result = db.execute(sql, params)

    cols = list(result.keys())
    return [dict(zip(cols, row)) for row in result.fetchall()]

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
    pk_col: str | list[str],
) -> tuple[int, Optional[str]]:
    """
    Idempotente upsert: laad rijen in een tijdelijke stagingtabel
    (WRITE_TRUNCATE) en MERGE ze op de primaire sleutel in de doeltabel.
    Herhaalde runs en full refreshes dupliceren daardoor nooit rijen en
    propageren updates correct. Geeft (aantal_verwerkt, error_of_None) terug.
    """
    if not rows:
        return 0, None

    full_table_id = f"{project}.{tdef.dataset_id}.{tdef.table_id}"
    staging_table_id = f"{full_table_id}__staging_{uuid.uuid4().hex[:8]}"
    cast_rows = [_cast_row(r) for r in rows]

    try:
        import io, json as _json
        from google.cloud import bigquery

        # 1. Laad de batch in een verse stagingtabel met het doelschema
        schema = [bigquery.SchemaField(c, t, mode="NULLABLE") for c, t in tdef.columns]
        ndjson = "\n".join(_json.dumps(r, default=str) for r in cast_rows)
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=schema,
            autodetect=False,
            ignore_unknown_values=True,  # _bq_synced_at e.d. buiten het doelschema
        )
        load_job = client.load_table_from_file(
            io.BytesIO(ndjson.encode()), staging_table_id, job_config=job_config)
        load_job.result()

        # 2. MERGE op (samengestelde) primaire sleutel: bijwerken of invoegen
        pk_cols = pk_col if isinstance(pk_col, list) else [pk_col]
        col_names = [c for c, _ in tdef.columns]
        update_cols = [c for c in col_names if c not in pk_cols]
        on_clause = " AND ".join(f"T.`{c}` = S.`{c}`" for c in pk_cols)
        merge_sql = (
            f"MERGE `{full_table_id}` T\n"
            f"USING `{staging_table_id}` S\n"
            f"ON {on_clause}\n"
            + ("WHEN MATCHED THEN UPDATE SET "
               + ", ".join(f"T.`{c}` = S.`{c}`" for c in update_cols) + "\n"
               if update_cols else "")
            + "WHEN NOT MATCHED THEN INSERT ("
            + ", ".join(f"`{c}`" for c in col_names) + ") VALUES ("
            + ", ".join(f"S.`{c}`" for c in col_names) + ")"
        )
        client.query(merge_sql).result()
        return len(cast_rows), None
    except Exception as exc:
        return 0, str(exc)
    finally:
        # 3. Stagingtabel altijd opruimen
        try:
            client.delete_table(staging_table_id, not_found_ok=True)
        except Exception:
            pass


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
        prev_watermark = since

        # 3+4. Pagineer door de bron (keyset) en MERGE elke pagina naar BigQuery
        #      tot de bron is uitgeput — geldt ook voor full refresh.
        pk_col = PK_COLUMN.get(pg_table, "id")
        tie_col = pk_col[-1] if isinstance(pk_col, list) else pk_col
        wm_col = WATERMARK_COLUMN.get(pg_table)
        last_key: Optional[tuple] = None
        max_watermark: Optional[datetime] = None

        while True:
            rows = _fetch_pg_rows(db, pg_table, since, last_key=last_key)
            if not rows:
                break

            inserted, err = _upsert_rows(client, project, tdef, rows, pk_col)
            if err:
                error_msg = err
                # Bewaar het watermerk van wat wél succesvol is geëxporteerd,
                # zodat een volgende run daar verder gaat (geen gaten).
                _save_import_job(db, pg_table, total_rows, "fout", err,
                                 watermark=max_watermark or prev_watermark)
                return {
                    "pg_table": pg_table,
                    "bq_table": f"{tdef.dataset_id}.{tdef.table_id}",
                    "rows_exported": total_rows,
                    "status": "error",
                    "error": err,
                }

            total_rows += inserted
            last_row = rows[-1]
            if wm_col:
                wm_val = last_row.get(wm_col)
                if wm_val is not None:
                    if not isinstance(wm_val, datetime):
                        wm_val = datetime.combine(wm_val, datetime.min.time())
                    max_watermark = wm_val if (max_watermark is None or wm_val > max_watermark) else max_watermark
                    last_key = (wm_val, last_row.get(tie_col))
                else:
                    # Zelfde normalisatie als het COALESCE-naar-epoch in
                    # _fetch_pg_rows, anders pagineert een pagina vol
                    # NULL-watermerken eindeloos opnieuw.
                    last_key = (EPOCH, last_row.get(tie_col))
            else:
                last_key = (None, last_row.get(tie_col))

            if len(rows) < BATCH_SIZE:
                break

        _save_import_job(
            db, pg_table, total_rows, "geimporteerd",
            watermark=max_watermark or prev_watermark,
            import_mode="volledig" if full_refresh else "incrementeel",
        )
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
        # Sla meta-tabellen over: interne BQ-tabellen (prefix "_") en
        # bq_sync_batches (schema zonder generieke pk; de sync-audit staat
        # in PostgreSQL ImportJob-rijen, zie get_sync_history()).
        if tdef.pg_table.startswith("_") or tdef.table_id == "bq_sync_batches":
            continue
        result = sync_table(tdef.pg_table, full_refresh=full_refresh)
        results.append(result)
    return results

def run_nightly_sync() -> int:
    """
    Draai de geplande (nachtelijke) incrementele BigQuery-sync.

    Gebruikt door zowel de in-process feed-sync scheduler als het standalone
    Scheduled-Deployment-script (scheduled_sync.py). Faalveilig:
      - Niet-geconfigureerde BigQuery → overslaan met exit-code 0.
      - Fouten per tabel worden door sync_table als ImportJob (source='bigquery')
        geregistreerd en zijn zichtbaar via /api/bigquery/sync/history.
      - Geeft 0 terug bij succes/overslaan, 1 bij één of meer fouten.
    Deze functie gooit nooit.
    """
    try:
        from bigquery.client import bq_available, bq_configured, bq_last_error
        if not bq_available():
            if not bq_configured():
                logger.info(
                    "BigQuery niet geconfigureerd — geplande BigQuery-sync overgeslagen."
                )
                return 0
            # Geconfigureerd maar kapot (ongeldige credentials, ontbrekend
            # pakket, ...): dit is een fout, geen overslag. Registreer een
            # fout-ImportJob zodat het zichtbaar is in de sync-history, en
            # geef exit 1 zodat de geplande run als mislukt wordt gemarkeerd.
            err = bq_last_error() or "BigQuery-client kon niet worden geïnitialiseerd."
            logger.error(
                "BigQuery is geconfigureerd maar niet beschikbaar: %s", err
            )
            db = BackgroundSessionLocal()
            try:
                _save_import_job(db, "verbinding", 0, "fout", err)
            finally:
                db.close()
            return 1

        logger.info("Geplande BigQuery-sync (incrementeel) gestart ...")
        results = sync_all_tables(full_refresh=False)
        ok = [r for r in results if r["status"] == "ok"]
        skipped = [r for r in results if r["status"] == "skipped"]
        failed = [r for r in results if r["status"] == "error"]
        total_rows = sum(r["rows_exported"] for r in results)
        logger.info(
            "Geplande BigQuery-sync klaar: %d tabellen ok, %d overgeslagen, "
            "%d fout, %d rijen geëxporteerd.",
            len(ok), len(skipped), len(failed), total_rows,
        )
        for r in failed:
            logger.error(
                "Geplande BigQuery-sync fout voor %s: %s", r["pg_table"], r["error"]
            )
        return 1 if failed else 0
    except Exception:
        logger.exception(
            "Geplande BigQuery-sync mislukt — PostgreSQL-data blijft intact."
        )
        return 1
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
