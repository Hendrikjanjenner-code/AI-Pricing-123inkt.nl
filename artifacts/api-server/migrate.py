"""
Lightweight auto-migration: adds missing columns to existing tables on every
server start. Uses SQLAlchemy inspect to diff ORM models against the live
schema and issues ALTER TABLE ... ADD COLUMN IF NOT EXISTS for any gaps.

Idempotent — safe to run every startup whether or not anything changed.

KNOWN LIMITATIONS (read before relying on this for schema evolution)
-------------------------------------------------------------------
This migrator is intentionally additive-only. It can ONLY add new columns.
It does NOT, and cannot safely, handle:

  * Column RENAMES.   Renaming a column in models.py is seen as "drop old +
    add new". The migrator adds a fresh, EMPTY column under the new name while
    the old column (with all its data) is left untouched in the DB. The data
    is NOT moved — it silently becomes orphaned.
  * Column TYPE CHANGES. Changing a column's type in models.py is ignored; the
    live column keeps its original type. No ALTER TYPE is issued (that can fail
    or lose precision, so it is left to a deliberate migration).
  * Column DROPS. Removing a column from models.py does NOT drop it from the
    DB. The column and its data remain as an "orphan".

Because renames and drops both leave an orphan column behind, this module logs
a WARNING for every column found in the live table but absent from the ORM
model (see _warn_orphan_columns). That warning is the signal that a manual,
data-preserving migration is required — e.g. an explicit
`ALTER TABLE ... RENAME COLUMN` (to keep the data) or a deliberate
`ALTER TABLE ... DROP COLUMN` (to discard it).

For a proper diff-based migration trail (rename detection, type changes,
down-migrations) integrate Alembic autogenerate. This lightweight migrator is
a convenience for the common additive case only.
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


def _warn_orphan_columns(table_name, live_cols, model_cols) -> int:
    """
    Log a WARNING for every column that exists in the live DB table but is
    absent from the ORM model. These "orphan" columns are the tell-tale sign
    of a rename or drop in models.py that this additive-only migrator cannot
    handle safely — the data is stranded and needs a manual, data-preserving
    migration (RENAME COLUMN) or a deliberate DROP COLUMN.

    Returns the number of orphan columns detected.
    """
    orphans = sorted(live_cols - model_cols)
    for orphan in orphans:
        logger.warning(
            "Migration: orphan column '%s' exists in table '%s' but is not in "
            "the ORM model. This usually means a column was renamed, dropped, "
            "or had its type changed in models.py. The auto-migrator does NOT "
            "move or drop data — review and apply a manual migration "
            "(ALTER TABLE \"%s\" RENAME COLUMN \"%s\" TO ... to keep the data, "
            "or DROP COLUMN \"%s\" to discard it).",
            orphan,
            table_name,
            table_name,
            orphan,
            orphan,
        )
    return len(orphans)


def run_migrations(engine, metadata) -> None:
    """
    For every table registered in *metadata*, compare the live DB schema
    and add any columns that are present in the ORM model but absent from
    the actual table.

    Also detects "orphan" columns — present in the live DB but absent from the
    ORM model — and logs a WARNING for each. See module docstring and
    _warn_orphan_columns for why these cannot be auto-handled.

    New tables (not yet created) are skipped here — create_all() handles them.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    columns_added = 0
    columns_skipped = 0
    orphan_columns = 0

    with engine.connect() as conn:
        for table_name, table in metadata.tables.items():
            if table_name not in existing_tables:
                continue

            live_cols = {
                col["name"]
                for col in inspector.get_columns(table_name)
            }

            model_cols = {column.name for column in table.columns}
            orphan_columns += _warn_orphan_columns(
                table_name, live_cols, model_cols
            )

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

    if columns_added or columns_skipped or orphan_columns:
        logger.info(
            "Migration complete: %d column(s) added, %d skipped, "
            "%d orphan column(s) detected (see warnings above).",
            columns_added,
            columns_skipped,
            orphan_columns,
        )
    else:
        logger.info("Migration: schema is up-to-date, no columns to add.")
