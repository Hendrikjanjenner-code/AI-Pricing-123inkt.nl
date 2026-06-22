"""
Lightweight auto-migration: adds missing columns to existing tables on every
server start. Uses SQLAlchemy inspect to diff ORM models against the live
schema and issues ALTER TABLE ... ADD COLUMN IF NOT EXISTS for any gaps.

Idempotent — safe to run every startup whether or not anything changed.
Does NOT drop columns, rename columns, or change types of existing columns.
"""
import logging
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql as pg_dialect

logger = logging.getLogger(__name__)


def _pg_type(column) -> str:
    """Return the PostgreSQL DDL type string for a SQLAlchemy column."""
    try:
        return column.type.compile(dialect=pg_dialect.dialect())
    except Exception:
        return "TEXT"


def _default_clause(column) -> str:
    """Return a SQL DEFAULT clause string, or empty string if not applicable."""
    if column.default is None or not column.default.is_scalar:
        return ""
    val = column.default.arg
    if isinstance(val, bool):
        return f" DEFAULT {'TRUE' if val else 'FALSE'}"
    if isinstance(val, str):
        escaped = val.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    if isinstance(val, (int, float)):
        return f" DEFAULT {val}"
    return ""


def run_migrations(engine, metadata) -> None:
    """
    For every table registered in *metadata*, compare the live DB schema
    and add any columns that are present in the ORM model but absent from
    the actual table.

    New tables (not yet created) are skipped here — create_all() handles them.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    columns_added = 0
    columns_skipped = 0

    with engine.connect() as conn:
        for table_name, table in metadata.tables.items():
            if table_name not in existing_tables:
                continue

            live_cols = {
                col["name"]
                for col in inspector.get_columns(table_name)
            }

            for column in table.columns:
                if column.name in live_cols:
                    continue

                pg_type = _pg_type(column)
                default = _default_clause(column)

                # When adding a column to an existing table that may already
                # contain rows, always allow NULL to prevent constraint errors.
                # Application-level NOT NULL is enforced on new inserts anyway.
                nullable_clause = "NULL"

                sql = (
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN IF NOT EXISTS "{column.name}" '
                    f"{pg_type}{default} {nullable_clause}"
                )

                try:
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(
                        "Migration: added column '%s' to table '%s'",
                        column.name,
                        table_name,
                    )
                    columns_added += 1
                except Exception as exc:
                    conn.rollback()
                    logger.warning(
                        "Migration: could not add column '%s' to '%s': %s",
                        column.name,
                        table_name,
                        exc,
                    )
                    columns_skipped += 1

    if columns_added or columns_skipped:
        logger.info(
            "Migration complete: %d column(s) added, %d skipped.",
            columns_added,
            columns_skipped,
        )
    else:
        logger.info("Migration: schema is up-to-date, no columns to add.")
