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

# Log through the uvicorn error logger so migration output is actually visible
# in the startup logs (the root logger has no INFO handler under uvicorn).
logger = logging.getLogger("uvicorn.error")


# Deliberate, data-DISCARDING column drops. The additive-only migrator never
# removes columns on its own (see module docstring), so a column removed from
# models.py lingers in the live DB as an "orphan" and triggers a startup
# WARNING on every boot. Listing that (table, column) here performs the drop
# exactly once, idempotently (DROP COLUMN IF EXISTS), and records it in
# schema_migrations so the deliberate data loss is captured in the audit trail.
#
# Only add a column here when its data is genuinely disposable. To PRESERVE
# data across a rename, use ALTER TABLE ... RENAME COLUMN instead — never list
# it here.
MANUAL_COLUMN_DROPS = [
    # Removed with the PriceShape-only refactor (no internal web-scraping):
    # the competitor register is no longer scraped, so this flag is obsolete.
    ("dim_competitor", "scraping_enabled"),
]


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


def _load_applied_keys(engine) -> set:
    """
    Return the set of change_keys already recorded in the schema_migrations
    history table. Returns an empty set if the table does not yet exist.
    """
    inspector = inspect(engine)
    if "schema_migrations" not in set(inspector.get_table_names()):
        return set()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT change_key FROM schema_migrations")
            ).fetchall()
        return {row[0] for row in rows}
    except Exception as exc:
        logger.warning(
            "Migration: could not read schema_migrations history: %s", exc
        )
        return set()


def _record_migration(
    conn, change_key, table_name, column_name, ddl, change_type="add_column"
) -> None:
    """
    Insert one audit-trail row into schema_migrations for a change that was just
    applied. Uses ON CONFLICT DO NOTHING so a re-run never duplicates a change.
    Recording failures are logged but never abort the migration itself.
    """
    try:
        conn.execute(
            text(
                "INSERT INTO schema_migrations "
                "(change_key, change_type, table_name, column_name, ddl, applied_at) "
                "VALUES (:change_key, :change_type, :table_name, :column_name, :ddl, NOW()) "
                "ON CONFLICT (change_key) DO NOTHING"
            ),
            {
                "change_key": change_key,
                "change_type": change_type,
                "table_name": table_name,
                "column_name": column_name,
                "ddl": ddl,
            },
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning(
            "Migration: could not record history for change '%s': %s",
            change_key,
            exc,
        )


def _apply_manual_column_drops(engine, applied_keys) -> int:
    """
    Apply the deliberate, data-discarding column drops declared in
    MANUAL_COLUMN_DROPS. Each drop runs at most once (guarded by its
    schema_migrations change_key) and uses DROP COLUMN IF EXISTS so it is safe
    on a fresh DB where the column never existed. Recorded in schema_migrations
    with change_type="drop_column".

    Returns the number of columns actually dropped this run.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    dropped = 0

    with engine.connect() as conn:
        for table_name, column_name in MANUAL_COLUMN_DROPS:
            change_key = f"drop:{table_name}.{column_name}"
            if change_key in applied_keys:
                continue
            if table_name not in existing_tables:
                # Table not created yet — nothing to drop, and create_all() will
                # build it fresh (without the removed column) anyway.
                continue

            live_cols = {c["name"] for c in inspector.get_columns(table_name)}
            ddl = (
                f'ALTER TABLE "{table_name}" '
                f'DROP COLUMN IF EXISTS "{column_name}"'
            )

            if column_name not in live_cols:
                # Fresh DB (or already dropped out-of-band): record the change so
                # the audit trail is complete, but skip the no-op DDL.
                _record_migration(
                    conn, change_key, table_name, column_name, ddl,
                    change_type="drop_column",
                )
                applied_keys.add(change_key)
                continue

            try:
                conn.execute(text(ddl))
                conn.commit()
                _record_migration(
                    conn, change_key, table_name, column_name, ddl,
                    change_type="drop_column",
                )
                applied_keys.add(change_key)
                logger.info(
                    "Migration: dropped orphan column '%s.%s' "
                    "(deliberate manual drop, data discarded).",
                    table_name,
                    column_name,
                )
                dropped += 1
            except Exception as exc:
                conn.rollback()
                logger.warning(
                    "Migration: could not drop column '%s.%s': %s",
                    table_name,
                    column_name,
                    exc,
                )

    return dropped


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
    columns_added = 0
    columns_skipped = 0
    orphan_columns = 0

    # Load the change_keys already recorded in the history table so we can
    # distinguish "newly applied" from "already applied" on every startup.
    applied_keys = _load_applied_keys(engine)

    # Apply deliberate column drops BEFORE inspecting for the add/orphan pass so
    # a just-dropped column is no longer flagged as an orphan on this same run.
    columns_dropped = _apply_manual_column_drops(engine, applied_keys)

    # Re-inspect after the drops so live_cols reflects the post-drop schema.
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

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
                if column.computed is not None:
                    # Generated (Computed) kolommen kan dit additive framework
                    # niet correct toevoegen (het zou een gewone kolom zonder
                    # GENERATED-expressie aanmaken). Die worden via de
                    # _MANUAL_INDEXES-DDL hieronder aangemaakt.
                    continue
                change_key = f"{table_name}.{column.name}"

                if column.name in live_cols:
                    # The column is present in the live DB. If we previously
                    # recorded adding it, report it as "already applied" so the
                    # startup log shows the full per-change history.
                    if change_key in applied_keys:
                        logger.info(
                            "Migration: change '%s' already applied.",
                            change_key,
                        )
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
                    _record_migration(
                        conn, change_key, table_name, column.name, sql
                    )
                    applied_keys.add(change_key)
                    logger.info(
                        "Migration: newly applied change '%s' "
                        "(added column '%s' to table '%s').",
                        change_key,
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

    # Handmatige indexen die het add-column-framework niet dekt. Idempotent
    # via IF NOT EXISTS. De unieke partiële index dwingt idempotente
    # loyalty-imports af op databaseniveau (dubbele external_ref per lid).
    _MANUAL_INDEXES = [
        (
            "uq_loyalty_txn_member_external_ref",
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_loyalty_txn_member_external_ref '
            'ON loyalty_transactions (member_id, external_ref) '
            'WHERE external_ref IS NOT NULL',
        ),
        # Concurrentprofielen zijn shop-scoped geworden: de oude globale
        # unique op competitor_name vervalt; uniek per (shop_id, naam).
        # Backfill van bestaande rijen naar shop 1 gebeurt via de DEFAULT.
        # Twee varianten: de constraint-naam én de index-naam, zodat beide
        # routes (ADD CONSTRAINT vs CREATE UNIQUE INDEX) worden afgedekt.
        (
            "drop_uq_competitor_profile_name",
            'ALTER TABLE competitor_profile '
            'DROP CONSTRAINT IF EXISTS competitor_profile_competitor_name_key',
        ),
        # Tweede variant: de legacy index (aangemaakt via CREATE UNIQUE INDEX)
        # heeft een andere naam dan de constraint; beide moeten weg.
        (
            "drop_ix_competitor_profile_competitor_name",
            'DROP INDEX IF EXISTS ix_competitor_profile_competitor_name',
        ),
        (
            "drop_ix_competitor_profile_competitor_name",
            'DROP INDEX IF EXISTS ix_competitor_profile_competitor_name',
        ),
        (
            "backfill_competitor_profile_shop",
            'UPDATE competitor_profile SET shop_id = 1 WHERE shop_id IS NULL',
        ),
        (
            "uq_competitor_profile_shop_name",
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_competitor_profile_shop_name '
            'ON competitor_profile (shop_id, competitor_name)',
        ),
        # Partiële unique index: dwingt de globale standaard-singleton af voor
        # ai_budget_config (username IS NULL). PostgreSQL's gewone UNIQUE op een
        # nullable kolom staat meerdere NULL-rijen toe; de partiële index niet.
        # Few-shot retrieval: opgeslagen dutch-tsvector over ai_feedback.question
        # (generated column) + GIN-index, zodat FTS een index-scan blijft bij
        # duizenden feedbackrijen. Beide idempotent via IF NOT EXISTS.
        (
            "ai_feedback_question_tsv_generated",
            "ALTER TABLE ai_feedback ADD COLUMN IF NOT EXISTS question_tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('dutch', coalesce(question, ''))) STORED",
        ),
        (
            "ix_ai_feedback_question_tsv",
            'CREATE INDEX IF NOT EXISTS ix_ai_feedback_question_tsv '
            'ON ai_feedback USING gin (question_tsv)',
        ),
        # Campagne-uplift snapshots: het oude schema had een unieke constraint
        # per (campaign_id, run_date); sinds run_at (run-identiteit) mogen
        # meerdere runs per dag bewaard blijven — drop beide legacy-vormen en
        # backfill run_at voor bestaande rijen (created_at, anders run_date).
        (
            "drop_uq_campaign_uplift_run",
            'ALTER TABLE campaign_uplift_snapshots '
            'DROP CONSTRAINT IF EXISTS uq_campaign_uplift_run',
        ),
        (
            "drop_ix_uq_campaign_uplift_run",
            'DROP INDEX IF EXISTS uq_campaign_uplift_run',
        ),
        (
            "backfill_campaign_uplift_run_at",
            'UPDATE campaign_uplift_snapshots '
            'SET run_at = COALESCE(created_at, run_date::timestamp) '
            'WHERE run_at IS NULL',
        ),
        # Datum-index voor de periodieke opruiming van oude AI-budgetslots:
        # de purge verwijdert op slot_date alleen; de unieke (username,
        # slot_date)-index helpt daar niet bij op bestaande, grote tabellen.
        (
            "ix_ai_budget_slots_slot_date",
            'CREATE INDEX IF NOT EXISTS ix_ai_budget_slots_slot_date '
            'ON ai_budget_slots (slot_date)',
        ),
        (
            "uq_ai_budget_config_global_singleton",
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_budget_config_global_singleton '
            'ON ai_budget_config ((username IS NULL)) '
            'WHERE username IS NULL',
        ),
        # Prijspositie/topconcurrenten: de "meest recente waarneming per SKU"
        # subquery filtert op sku_id + date-venster; zonder composiete index
        # loopt dat op grote feed-tabellen tegen de statement-timeout aan.
        (
            "ix_fact_comp_price_sku_date",
            'CREATE INDEX IF NOT EXISTS ix_fact_comp_price_sku_date '
            'ON fact_competitor_price_daily (sku_id, date)',
        ),
        # Run-historie (scheduled_engine_runs) mag een shop-verwijdering nooit
        # blokkeren: herzet de FK naar ON DELETE CASCADE als hij nog zonder
        # cascade bestaat (idempotent via DO-blok).
        (
            "fk_scheduled_engine_runs_shop_cascade",
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint c
                    WHERE c.conname = 'scheduled_engine_runs_shop_id_fkey'
                      AND c.confdeltype <> 'c'
                ) THEN
                    ALTER TABLE scheduled_engine_runs
                        DROP CONSTRAINT scheduled_engine_runs_shop_id_fkey;
                    ALTER TABLE scheduled_engine_runs
                        ADD CONSTRAINT scheduled_engine_runs_shop_id_fkey
                        FOREIGN KEY (shop_id) REFERENCES dim_shop(id)
                        ON DELETE CASCADE;
                END IF;
            END $$
            """,
        ),
    ]
    with engine.connect() as conn:
        for _idx_name, _idx_sql in _MANUAL_INDEXES:
            try:
                conn.execute(text(_idx_sql))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.warning("Migration: could not create index '%s': %s", _idx_name, exc)

    if columns_added or columns_skipped or orphan_columns or columns_dropped:
        logger.info(
            "Migration complete: %d column(s) added, %d dropped, %d skipped, "
            "%d orphan column(s) detected (see warnings above). "
            "%d change(s) tracked in schema_migrations.",
            columns_added,
            columns_dropped,
            columns_skipped,
            orphan_columns,
            len(applied_keys),
        )
    else:
        logger.info(
            "Migration: schema is up-to-date, no columns to add. "
            "%d change(s) tracked in schema_migrations.",
            len(applied_keys),
        )
