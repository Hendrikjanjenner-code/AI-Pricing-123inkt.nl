"""
BigQuery tabelschema's — spiegel van de canonieke PostgreSQL fact-tabellen.

Elke definitie beschrijft:
  - dataset_id   : BigQuery dataset waar de tabel in leeft
  - table_id     : BigQuery tabel-ID
  - pg_table     : naam van de PostgreSQL-bronbrontabel
  - columns      : lijst van (kolom, BigQuery-type) tuples
  - partition_by : optionele partitie-kolom (DATE) voor kostenbeheersing
  - cluster_by   : optionele clustering-kolommen (max 4)
  - description  : leesbare omschrijving

Dataset-structuur:
  pricing_facts     — dagelijkse fact-tabellen (sales, margin, prijs, voorraad, etc.)
  pricing_dims      — dimensies (product, categorie, shop, concurrent)
  pricing_analytics — afgeleide tabellen (scores, aanbevelingen, signalen, BCG)
  pricing_meta      — beheersbeheer (sync-batches, kostenmeting)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

DATASET_FACTS = "pricing_facts"
DATASET_DIMS = "pricing_dims"
DATASET_ANALYTICS = "pricing_analytics"
DATASET_META = "pricing_meta"

ALL_DATASETS = [DATASET_FACTS, DATASET_DIMS, DATASET_ANALYTICS, DATASET_META]


@dataclass
class BQTableDef:
    dataset_id: str
    table_id: str
    pg_table: str
    columns: list[tuple[str, str]]       # (col_name, bq_type)
    partition_by: Optional[str] = None   # DATE partitie-kolom
    cluster_by: list[str] = field(default_factory=list)
    description: str = ""


BQ_TABLE_DEFINITIONS: list[BQTableDef] = [

    # ── Dimensies ──────────────────────────────────────────────────────────────
    BQTableDef(
        dataset_id=DATASET_DIMS,
        table_id="dim_product",
        pg_table="dim_product",
        description="Product-dimensie: canonical graankorrel per SKU per shop.",
        columns=[
            ("sku_id", "STRING"),
            ("product_name", "STRING"),
            ("brand", "STRING"),
            ("category", "STRING"),
            ("subcategory", "STRING"),
            ("product_group", "STRING"),
            ("is_private_label", "BOOL"),
            ("is_a_brand", "BOOL"),
            ("lifecycle_status", "STRING"),
            ("strategy_type", "STRING"),
            ("cost_price", "NUMERIC"),
            ("min_price", "NUMERIC"),
            ("max_price", "NUMERIC"),
            ("current_price", "NUMERIC"),
            ("stock_quantity", "INT64"),
            ("data_quality_score", "FLOAT64"),
            ("product_type", "STRING"),
            ("oem_code", "STRING"),
            ("ean", "STRING"),
            ("shop_id", "INT64"),
            ("import_source", "STRING"),
            ("created_at", "TIMESTAMP"),
            ("updated_at", "TIMESTAMP"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
        cluster_by=["shop_id", "category"],
    ),

    BQTableDef(
        dataset_id=DATASET_DIMS,
        table_id="dim_category",
        pg_table="dim_category",
        description="Categorie-dimensie.",
        columns=[
            ("id", "INT64"),
            ("name", "STRING"),
            ("parent_category", "STRING"),
            ("default_strategy", "STRING"),
            ("created_at", "TIMESTAMP"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_DIMS,
        table_id="dim_shop",
        pg_table="dim_shop",
        description="Shop-dimensie: multi-shop canonical.",
        columns=[
            ("id", "INT64"),
            ("shop_code", "STRING"),
            ("name", "STRING"),
            ("country", "STRING"),
            ("currency", "STRING"),
            ("channel", "STRING"),
            ("is_default", "BOOL"),
            ("active", "BOOL"),
            ("created_at", "TIMESTAMP"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_DIMS,
        table_id="dim_competitor",
        pg_table="dim_competitor",
        description="Concurrentenregister.",
        columns=[
            ("competitor_id", "INT64"),
            ("competitor_name", "STRING"),
            ("base_url", "STRING"),
            ("competitor_type", "STRING"),
            ("default_relevance_score", "FLOAT64"),
            ("active", "BOOL"),
            ("created_at", "TIMESTAMP"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    # ── Dagelijkse Facts ───────────────────────────────────────────────────────
    BQTableDef(
        dataset_id=DATASET_FACTS,
        table_id="fact_sales_daily",
        pg_table="fact_sales_daily",
        description="Dagelijkse sales: omzet, afzet, marge per SKU.",
        partition_by="date",
        cluster_by=["shop_id", "sku_id"],
        columns=[
            ("id", "INT64"),
            ("date", "DATE"),
            ("sku_id", "STRING"),
            ("shop_id", "INT64"),
            ("units_sold", "INT64"),
            ("revenue", "NUMERIC"),
            ("cost", "NUMERIC"),
            ("margin", "NUMERIC"),
            ("margin_pct", "FLOAT64"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_FACTS,
        table_id="fact_price_daily",
        pg_table="fact_price_daily",
        description="Dagelijkse eigen prijzen per SKU.",
        partition_by="date",
        cluster_by=["shop_id", "sku_id"],
        columns=[
            ("id", "INT64"),
            ("date", "DATE"),
            ("sku_id", "STRING"),
            ("shop_id", "INT64"),
            ("price", "NUMERIC"),
            ("cost_price", "NUMERIC"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_FACTS,
        table_id="fact_competitor_price_daily",
        pg_table="fact_competitor_price_daily",
        description="Dagelijkse concurrentprijzen per SKU per concurrent.",
        partition_by="date",
        cluster_by=["shop_id", "sku_id", "competitor_name"],
        columns=[
            ("id", "INT64"),
            ("date", "DATE"),
            ("sku_id", "STRING"),
            ("shop_id", "INT64"),
            ("competitor_name", "STRING"),
            ("price", "NUMERIC"),
            ("url", "STRING"),
            ("source", "STRING"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_FACTS,
        table_id="fact_inventory_daily",
        pg_table="fact_inventory_daily",
        description="Dagelijkse voorraad per SKU.",
        partition_by="date",
        cluster_by=["shop_id", "sku_id"],
        columns=[
            ("id", "INT64"),
            ("date", "DATE"),
            ("sku_id", "STRING"),
            ("shop_id", "INT64"),
            ("stock_quantity", "INT64"),
            ("days_of_stock", "FLOAT64"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    # ── Analytics / Scores / Aanbevelingen ────────────────────────────────────
    BQTableDef(
        dataset_id=DATASET_ANALYTICS,
        table_id="fact_pricing_recommendation_daily",
        pg_table="fact_pricing_recommendation_daily",
        description="Dagelijkse prijsaanbevelingen per SKU (AI-output).",
        partition_by="date",
        cluster_by=["shop_id", "sku_id"],
        columns=[
            ("id", "INT64"),
            ("date", "DATE"),
            ("sku_id", "STRING"),
            ("shop_id", "INT64"),
            ("current_price", "NUMERIC"),
            ("recommended_price", "NUMERIC"),
            ("recommended_change_pct", "FLOAT64"),
            ("expected_units", "FLOAT64"),
            ("expected_revenue", "NUMERIC"),
            ("expected_margin", "NUMERIC"),
            ("expected_margin_uplift", "NUMERIC"),
            ("confidence_score", "FLOAT64"),
            ("reason_code", "STRING"),
            ("strategy_type", "STRING"),
            ("safety_status", "STRING"),
            ("approval_status", "STRING"),
            ("approved_by", "STRING"),
            ("approved_at", "TIMESTAMP"),
            ("model_version", "STRING"),
            ("processing_status", "STRING"),
            ("processed_at", "TIMESTAMP"),
            ("created_at", "TIMESTAMP"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_ANALYTICS,
        table_id="sku_competition_score",
        pg_table="sku_competition_score",
        description="PCIS per SKU per rundag.",
        partition_by="run_date",
        cluster_by=["sku_id"],
        columns=[
            ("id", "INT64"),
            ("sku_id", "STRING"),
            ("run_date", "DATE"),
            ("pcis_score", "FLOAT64"),
            ("competition_class", "STRING"),
            ("price_index", "FLOAT64"),
            ("reference_price", "NUMERIC"),
            ("competitors_used", "INT64"),
            ("created_at", "TIMESTAMP"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_ANALYTICS,
        table_id="fact_bcg_classification_daily",
        pg_table="fact_bcg_classification_daily",
        description="BCG-classificatie per SKU/categorie per dag.",
        partition_by="date",
        cluster_by=["entity_type", "entity_id"],
        columns=[
            ("id", "INT64"),
            ("date", "DATE"),
            ("entity_type", "STRING"),
            ("entity_id", "STRING"),
            ("entity_name", "STRING"),
            ("internal_bcg_class", "STRING"),
            ("external_bcg_class", "STRING"),
            ("hybrid_bcg_class", "STRING"),
            ("ibss_score", "FLOAT64"),
            ("gps_score", "FLOAT64"),
            ("pricing_power_score", "FLOAT64"),
            ("pricing_strategy", "STRING"),
            ("strategic_priority", "STRING"),
            ("confidence_score", "FLOAT64"),
            ("created_at", "TIMESTAMP"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_ANALYTICS,
        table_id="intelligence_signals",
        pg_table="intelligence_signals",
        description="Commercial Intelligence Signals van alle engines.",
        partition_by="observed_at",
        cluster_by=["engine", "entity_type"],
        columns=[
            ("id", "INT64"),
            ("shop_id", "INT64"),
            ("engine", "STRING"),
            ("signal_type", "STRING"),
            ("severity", "STRING"),
            ("direction", "STRING"),
            ("entity_type", "STRING"),
            ("entity_id", "STRING"),
            ("entity_name", "STRING"),
            ("metric", "STRING"),
            ("current_value", "FLOAT64"),
            ("previous_value", "FLOAT64"),
            ("confidence", "FLOAT64"),
            ("explanation", "STRING"),
            ("suggested_action", "STRING"),
            ("observed_at", "TIMESTAMP"),
            ("valid_until", "TIMESTAMP"),
            ("status", "STRING"),
            ("dedupe_key", "STRING"),
            ("created_at", "TIMESTAMP"),
            ("_bq_synced_at", "TIMESTAMP"),
        ],
    ),

    # ── Meta ──────────────────────────────────────────────────────────────────
    BQTableDef(
        dataset_id=DATASET_META,
        table_id="bq_sync_batches",
        pg_table="import_jobs",  # read-only verwijzing; deze tabel wordt door sync.py gevuld
        description="BigQuery sync-batch registratie: welke tabellen wanneer gesynchroniseerd.",
        partition_by="synced_at",
        columns=[
            ("batch_id", "STRING"),
            ("pg_table", "STRING"),
            ("bq_table", "STRING"),
            ("rows_exported", "INT64"),
            ("watermark_from", "TIMESTAMP"),
            ("watermark_to", "TIMESTAMP"),
            ("synced_at", "TIMESTAMP"),
            ("status", "STRING"),    # ok / error
            ("error_msg", "STRING"),
        ],
    ),

    BQTableDef(
        dataset_id=DATASET_META,
        table_id="bq_query_costs",
        pg_table="_bq_query_costs",  # intern — gevuld door cost_tracker.py
        description="BigQuery scan-bytes en geschatte kosten per query/module.",
        partition_by="queried_at",
        columns=[
            ("id", "STRING"),
            ("module", "STRING"),
            ("query_label", "STRING"),
            ("bytes_scanned", "INT64"),
            ("estimated_cost_usd", "FLOAT64"),
            ("duration_ms", "INT64"),
            ("ok", "BOOL"),
            ("queried_at", "TIMESTAMP"),
        ],
    ),
]

# Opzoek-dict: pg_table → BQTableDef
BY_PG_TABLE: dict[str, BQTableDef] = {t.pg_table: t for t in BQ_TABLE_DEFINITIONS}

# Opzoek-dict: (dataset_id, table_id) → BQTableDef
BY_BQ_TABLE: dict[tuple[str, str], BQTableDef] = {
    (t.dataset_id, t.table_id): t for t in BQ_TABLE_DEFINITIONS
}
