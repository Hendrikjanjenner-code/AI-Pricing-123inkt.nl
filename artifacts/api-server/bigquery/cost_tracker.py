"""
BigQuery kostenmeting — scan-bytes en geschatte querykosten per module/job.

Kosten worden berekend op basis van het on-demand BigQuery-tarief:
  $6.25 per TB gescand (per augustus 2026, regio EU).
  Zie: https://cloud.google.com/bigquery/pricing#on_demand

Per query worden bijgehouden:
  - module       : welke engine/module de query uitvoerde
  - query_label  : korte omschrijving van de query
  - bytes_scanned: gerapporteerd door BigQuery job.total_bytes_processed
  - estimated_cost_usd: berekende kosten in USD
  - duration_ms  : uitvoertijd
  - ok           : succes/mislukking

Opslag: PostgreSQL-tabel 'fact_bq_query_cost' (als BigQuery zelf niet
beschikbaar is, slaan we de kosten toch lokaal op voor zichtbaarheid).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("uvicorn.error")

# $6.25 per TB = $6.25 / 1e12 per byte
_COST_PER_BYTE_USD = 6.25 / 1_000_000_000_000


def bytes_to_cost_usd(bytes_scanned: int) -> float:
    """Bereken de geschatte BigQuery-querykosten in USD."""
    return round(bytes_scanned * _COST_PER_BYTE_USD, 8)


def record_query_cost(
    module: str,
    query_label: str,
    bytes_scanned: int,
    duration_ms: int,
    ok: bool,
    db=None,
) -> dict:
    """
    Sla BigQuery query-kosten op in PostgreSQL.

    Parameters
    ----------
    module       : naam van de aanroepende module (bijv. "semantic_layer", "bcg_sync")
    query_label  : korte omschrijving van de query
    bytes_scanned: gescande bytes (uit BQ job.total_bytes_processed)
    duration_ms  : uitvoertijd in milliseconden
    ok           : True als de query succesvol was
    db           : optionele SQLAlchemy-sessie; als None wordt een nieuwe aangemaakt

    Returns
    -------
    dict met kostenmeting
    """
    estimated_cost_usd = bytes_to_cost_usd(bytes_scanned)
    record = {
        "id": str(uuid.uuid4()),
        "module": module,
        "query_label": query_label,
        "bytes_scanned": bytes_scanned,
        "estimated_cost_usd": estimated_cost_usd,
        "duration_ms": duration_ms,
        "ok": ok,
        "queried_at": datetime.now(timezone.utc).isoformat(),
    }

    # Sla op in PostgreSQL via raw SQL (geen eigen ORM-model nodig)
    if db is not None:
        try:
            from sqlalchemy import text
            db.execute(
                text(
                    """
                    INSERT INTO fact_bq_query_cost
                        (id, module, query_label, bytes_scanned,
                         estimated_cost_usd, duration_ms, ok, queried_at)
                    VALUES
                        (:id, :module, :query_label, :bytes_scanned,
                         :estimated_cost_usd, :duration_ms, :ok, :queried_at)
                    ON CONFLICT DO NOTHING
                    """
                ),
                record,
            )
            db.commit()
        except Exception as exc:
            logger.warning("Kostenmeting kon niet worden opgeslagen: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass

    return record


def get_cost_summary(db, days: int = 30) -> dict:
    """
    Geef een kostensamenvatting terug voor de opgegeven periode.
    Geeft lege/nul-resultaten terug als de tabel nog niet bestaat.
    """
    try:
        from sqlalchemy import text
        since = f"NOW() - INTERVAL '{days} days'"
        result = db.execute(
            text(
                f"""
                SELECT
                    module,
                    COUNT(*) AS query_count,
                    SUM(bytes_scanned) AS total_bytes,
                    SUM(estimated_cost_usd) AS total_cost_usd,
                    AVG(duration_ms) AS avg_duration_ms,
                    SUM(CASE WHEN NOT ok THEN 1 ELSE 0 END) AS error_count
                FROM fact_bq_query_cost
                WHERE queried_at >= {since}
                GROUP BY module
                ORDER BY total_cost_usd DESC
                """
            )
        ).fetchall()

        total_bytes = 0
        total_cost = 0.0
        rows = []
        for r in result:
            tb = int(r[2] or 0)  # SUM(BIGINT) komt terug als Decimal
            tc = float(r[3] or 0)
            total_bytes += tb
            total_cost += tc
            rows.append({
                "module": r[0],
                "query_count": r[1],
                "total_bytes": tb,
                "total_tb": round(tb / 1e12, 6),
                "total_cost_usd": round(tc, 6),
                "avg_duration_ms": round(float(r[4] or 0), 1),
                "error_count": r[5],
            })

        return {
            "period_days": days,
            "total_bytes": total_bytes,
            "total_tb": round(total_bytes / 1e12, 6),
            "total_cost_usd": round(total_cost, 6),
            "by_module": rows,
            "pricing_note": f"$6.25/TB (on-demand EU, aug 2026)",
        }
    except Exception as exc:
        logger.warning("Kostensamenvatting kon niet worden geladen: %s", exc)
        return {
            "period_days": days,
            "total_bytes": 0,
            "total_tb": 0.0,
            "total_cost_usd": 0.0,
            "by_module": [],
            "error": str(exc),
            "pricing_note": "$6.25/TB (on-demand EU, aug 2026)",
        }


def ensure_cost_table(engine) -> None:
    """Maak de fact_bq_query_cost-tabel aan als die nog niet bestaat."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS fact_bq_query_cost (
                        id              TEXT PRIMARY KEY,
                        module          TEXT NOT NULL,
                        query_label     TEXT NOT NULL,
                        bytes_scanned   BIGINT DEFAULT 0,
                        estimated_cost_usd DOUBLE PRECISION DEFAULT 0,
                        duration_ms     INTEGER DEFAULT 0,
                        ok              BOOLEAN DEFAULT TRUE,
                        queried_at      TIMESTAMPTZ DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bq_cost_queried_at "
                    "ON fact_bq_query_cost (queried_at DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bq_cost_module "
                    "ON fact_bq_query_cost (module)"
                )
            )
            conn.commit()
    except Exception as exc:
        logger.warning("fact_bq_query_cost aanmaken mislukt: %s", exc)
