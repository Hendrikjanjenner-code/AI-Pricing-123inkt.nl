"""
SQLAlchemy ORM models for the Pricing Decision Engine.
All tables match the spec: users, dim_product, dim_category, etc.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Date, Numeric, JSON
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255))
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="viewer")  # admin, pricing_manager, analyst, viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DimCategory(Base):
    __tablename__ = "dim_category"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    parent_category = Column(String(255))
    default_strategy = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class DimProduct(Base):
    __tablename__ = "dim_product"

    sku_id = Column(String(100), primary_key=True, index=True)
    product_name = Column(String(500), nullable=False)
    brand = Column(String(255))
    category = Column(String(255))
    subcategory = Column(String(255))
    product_group = Column(String(255))
    is_private_label = Column(Boolean, default=False)
    is_a_brand = Column(Boolean, default=False)
    lifecycle_status = Column(String(50), default="active")
    strategy_type = Column(String(100))
    cost_price = Column(Numeric(10, 4))
    min_price = Column(Numeric(10, 4))
    max_price = Column(Numeric(10, 4))
    current_price = Column(Numeric(10, 4))
    stock_quantity = Column(Integer, default=0)
    data_quality_score = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CategoryStrategyMapping(Base):
    __tablename__ = "category_strategy_mapping"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(255), nullable=False)
    subcategory = Column(String(255))
    strategy_type = Column(String(100), nullable=False)
    notes = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(100))


class MapSubstitution(Base):
    __tablename__ = "map_substitution"

    id = Column(Integer, primary_key=True, index=True)
    a_brand_sku = Column(String(100), nullable=False)
    private_label_sku = Column(String(100), nullable=False)
    substitution_strength = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class FactSalesDaily(Base):
    __tablename__ = "fact_sales_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    sku_id = Column(String(100), nullable=False, index=True)
    units_sold = Column(Integer, default=0)
    revenue = Column(Numeric(12, 4))
    cost = Column(Numeric(12, 4))
    margin = Column(Numeric(12, 4))
    margin_pct = Column(Float)


class FactPriceDaily(Base):
    __tablename__ = "fact_price_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    sku_id = Column(String(100), nullable=False, index=True)
    price = Column(Numeric(10, 4))
    cost_price = Column(Numeric(10, 4))


class FactCompetitorPriceDaily(Base):
    __tablename__ = "fact_competitor_price_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    sku_id = Column(String(100), nullable=False, index=True)
    competitor_name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 4))
    url = Column(Text)


class FactInventoryDaily(Base):
    __tablename__ = "fact_inventory_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    sku_id = Column(String(100), nullable=False, index=True)
    stock_quantity = Column(Integer, default=0)
    days_of_stock = Column(Float)


class FactBasketAffinity(Base):
    __tablename__ = "fact_basket_affinity"

    id = Column(Integer, primary_key=True, index=True)
    sku_id_a = Column(String(100), nullable=False, index=True)
    sku_id_b = Column(String(100), nullable=False)
    affinity_score = Column(Float)
    co_purchase_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)


class FactPricingRecommendationDaily(Base):
    __tablename__ = "fact_pricing_recommendation_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    sku_id = Column(String(100), nullable=False, index=True)
    current_price = Column(Numeric(10, 4))
    recommended_price = Column(Numeric(10, 4))
    recommended_change_pct = Column(Float)
    expected_units = Column(Float)
    expected_revenue = Column(Numeric(12, 4))
    expected_margin = Column(Numeric(12, 4))
    expected_margin_uplift = Column(Numeric(12, 4))
    confidence_score = Column(Float)
    reason_code = Column(String(100))
    strategy_type = Column(String(100))
    safety_status = Column(String(50), default="ok")
    approval_status = Column(String(50), default="pending")
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    pushed_to_priceshape = Column(Boolean, default=False)
    model_version = Column(String(50))
    override_price = Column(Numeric(10, 4))
    override_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelRun(Base):
    __tablename__ = "model_runs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String(50), default="running")  # running, completed, failed
    skus_processed = Column(Integer, default=0)
    skus_skipped = Column(Integer, default=0)
    model_version = Column(String(50))
    error_message = Column(Text)
    run_metadata = Column(JSON)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    upload_type = Column(String(100), nullable=False)
    filename = Column(String(500), nullable=False)
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    rows_processed = Column(Integer, default=0)
    rows_failed = Column(Integer, default=0)
    error_message = Column(Text)
    uploaded_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(100))  # recommendation, product, user, etc.
    entity_id = Column(String(100))
    action = Column(String(100), nullable=False)
    performed_by = Column(String(100))
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(Text)
    old_value = Column(JSON)
    new_value = Column(JSON)


class SkuCompetitionScore(Base):
    """PCIS — Pricing Competition Impact Score — per SKU."""
    __tablename__ = "sku_competition_score"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    run_date = Column(Date, nullable=False)
    product_comparability_score = Column(Float, default=0.0)
    price_sensitivity_score = Column(Float, default=0.0)
    substitution_score = Column(Float, default=0.0)
    competitor_relevance_score = Column(Float, default=0.0)
    competitor_price_reliability_score = Column(Float, default=0.0)
    basket_dependency_score = Column(Float, default=0.0)
    strategic_importance_score = Column(Float, default=0.0)
    pcis_score = Column(Float, default=0.0)
    competition_class = Column(String(50))  # Ignore, Monitor, Influence, Strong, Critical
    reference_price = Column(Numeric(10, 4))   # Weighted median competitor reference price
    price_index = Column(Float)                # own_price / reference_price
    competitors_used = Column(Integer, default=0)
    competitors_excluded = Column(Integer, default=0)
    excluded_reasons = Column(JSON)            # {reason_code: count}
    created_at = Column(DateTime, default=datetime.utcnow)


class AbTest(Base):
    """A/B test experiment definition."""
    __tablename__ = "ab_tests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    status = Column(String(50), default="active")  # active, completed, paused
    ai_group_sku_count = Column(Integer, default=0)
    control_group_sku_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class AbTestResult(Base):
    """Per-SKU A/B test result: AI group vs CONTROL group."""
    __tablename__ = "ab_test_results"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("ab_tests.id"), nullable=False)
    sku_id = Column(String(100), nullable=False, index=True)
    group_type = Column(String(20), nullable=False)   # AI or CONTROL
    baseline_price = Column(Numeric(10, 4))
    current_price = Column(Numeric(10, 4))
    baseline_units = Column(Float)
    current_units = Column(Float)
    baseline_revenue = Column(Numeric(12, 4))
    current_revenue = Column(Numeric(12, 4))
    baseline_margin = Column(Numeric(12, 4))
    current_margin = Column(Numeric(12, 4))
    baseline_conversion_rate = Column(Float)
    current_conversion_rate = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorInfluenceScore(Base):
    """
    CIS — Competitor Influence Score — per concurrent per SKU.
    Bevat ook CSRS (voorraadbetrouwbaarheid) en CSS (duurzaamheid prijs).
    """
    __tablename__ = "competitor_influence_scores"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    competitor_name = Column(String(255), nullable=False)
    run_date = Column(Date, nullable=False)

    # Concurrentielaag: direct, functioneel, categorie, intern
    competition_layer = Column(String(50), default="direct")

    # CIS sub-scores
    competitor_relevance_score = Column(Float, default=0.0)
    product_comparability_score = Column(Float, default=0.0)
    price_sensitivity_score = Column(Float, default=0.0)
    # CSRS sub-scores
    availability_rate = Column(Float, default=0.0)
    delivery_speed_score = Column(Float, default=0.0)
    stock_stability_score = Column(Float, default=0.0)
    listing_consistency_score = Column(Float, default=0.0)
    # CSS sub-scores
    price_deviation_score = Column(Float, default=0.0)
    price_volatility_score = Column(Float, default=0.0)
    competitor_type_score = Column(Float, default=0.0)
    delivery_reliability_score = Column(Float, default=0.0)

    # Samengestelde scores
    csrs_score = Column(Float, default=0.0)  # Competitor Stock Reliability Score
    css_score = Column(Float, default=0.0)   # Competitor Sustainability Score
    cis_score = Column(Float, default=0.0)   # Competitor Influence Score

    # Classificatie
    cis_class = Column(String(50))  # Primaire/Sterke/Secundaire/Zwakke/Negeren
    status = Column(String(50))     # Actief/Monitoren/Negeren
    reason_code = Column(String(100))
    pricing_action = Column(String(100))

    # Prijs data
    competitor_price = Column(Numeric(10, 4))
    price_vs_own_pct = Column(Float)
    competitor_weight = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)


class SkuElasticity(Base):
    """Prijselasticiteit per SKU — eigen, kruis, concurrentie, intern."""
    __tablename__ = "sku_elasticity"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    run_date = Column(Date, nullable=False)

    own_price_elasticity = Column(Float)          # Eigen prijselasticiteit
    cross_elasticity = Column(Float)              # Kruiselasticiteit met markt
    competitive_elasticity = Column(Float)        # Gevoeligheid voor concurrentieprijs
    internal_substitution_elasticity = Column(Float)  # Overstap naar huismerk

    elasticity_confidence_score = Column(Float, default=0.0)
    confidence_class = Column(String(50))         # hoog_betrouwbaar / bruikbaar / laag_betrouwbaar

    # Context-factoren gebruikt
    category = Column(String(255))
    pcis_score_used = Column(Float)
    csrs_score_used = Column(Float)
    sales_volume_30d = Column(Float)
    price_variation_30d = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)


class InternalCompetitionScore(Base):
    """
    Interne concurrentie: A-merk vs huismerk (ISV — Internal Substitution Value).
    ISV = internal_switch_probability * internal_margin_gap
    """
    __tablename__ = "internal_competition_scores"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)          # A-merk SKU
    paired_sku_id = Column(String(100), nullable=False, index=True)   # Huismerk SKU
    run_date = Column(Date, nullable=False)

    internal_switch_probability = Column(Float, default=0.0)
    internal_margin_gap = Column(Float, default=0.0)   # Margverschil per eenheid
    isv = Column(Float, default=0.0)                   # ISV = prob * gap

    # Aanbevolen actie
    recommended_internal_action = Column(String(100))  # PRIVATE_LABEL_PUSH / etc.
    action_reason = Column(Text)

    # Prijsdruk context
    a_brand_price = Column(Numeric(10, 4))
    private_label_price = Column(Numeric(10, 4))
    a_brand_margin_pct = Column(Float)
    private_label_margin_pct = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Module 1: Scraping ─────────────────────────────────────────────────────

class DimCompetitor(Base):
    """Geconfigureerde concurrenten voor de scraping engine."""
    __tablename__ = "dim_competitor"

    competitor_id = Column(Integer, primary_key=True, index=True)
    competitor_name = Column(String(255), nullable=False, unique=True)
    base_url = Column(String(500))
    competitor_type = Column(String(50), default="online")
    default_relevance_score = Column(Float, default=0.5)
    channel_relevance = Column(JSON)
    scraping_enabled = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorScrapeConfig(Base):
    """CSS-selector configuratie voor een concurrent-pagina."""
    __tablename__ = "competitor_scrape_config"

    config_id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("dim_competitor.competitor_id"), nullable=False)
    page_type = Column(String(50), default="product")
    url_pattern = Column(Text)
    title_selector = Column(String(500))
    price_selector = Column(String(500))
    stock_selector = Column(String(500))
    delivery_selector = Column(String(500))
    ean_selector = Column(String(500))
    mpn_selector = Column(String(500))
    pack_size_selector = Column(String(500))
    scrape_method = Column(String(50), default="requests")
    requests_per_minute = Column(Integer, default=10)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FactScrapeResult(Base):
    """Ruwe scrape-uitkomst per product-URL."""
    __tablename__ = "fact_scrape_result"

    scrape_id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("dim_competitor.competitor_id"), nullable=False, index=True)
    product_url = Column(Text)
    scraped_at = Column(DateTime, default=datetime.utcnow, index=True)
    scrape_status = Column(String(50))
    product_title = Column(String(1000))
    brand = Column(String(255))
    ean = Column(String(50))
    mpn = Column(String(100))
    price_inc_vat = Column(Numeric(10, 4))
    shipping_cost = Column(Numeric(10, 4))
    total_price_inc_vat = Column(Numeric(10, 4))
    stock_status = Column(String(100))
    delivery_text = Column(String(500))
    delivery_days = Column(Integer)
    pack_size = Column(String(100))
    unit_quantity = Column(Float)
    seller_name = Column(String(255))
    raw_html_hash = Column(String(64))
    error_message = Column(Text)


class FactCompetitorOfferDaily(Base):
    """Dagelijks gematcht concurrent-aanbod per eigen SKU."""
    __tablename__ = "fact_competitor_offer_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    own_sku_id = Column(String(100), nullable=False, index=True)
    competitor_id = Column(Integer, ForeignKey("dim_competitor.competitor_id"), nullable=False)
    competitor_sku = Column(String(200))
    product_url = Column(Text)
    competitor_price_inc_vat = Column(Numeric(10, 4))
    shipping_cost = Column(Numeric(10, 4))
    total_price_inc_vat = Column(Numeric(10, 4))
    in_stock = Column(Boolean)
    delivery_days = Column(Integer)
    match_type = Column(String(50))
    match_confidence = Column(Float)
    pack_size = Column(String(100))
    source = Column(String(50), default="scraper")
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Module 2: Product Matching ──────────────────────────────────────────────

class ProductMatch(Base):
    """Koppeling eigen SKU ↔ concurrent aanbod."""
    __tablename__ = "product_match"

    match_id = Column(Integer, primary_key=True, index=True)
    own_sku_id = Column(String(100), nullable=False, index=True)
    competitor_id = Column(Integer, ForeignKey("dim_competitor.competitor_id"), nullable=False)
    competitor_sku = Column(String(200))
    competitor_url = Column(Text)
    match_type = Column(String(50))
    match_confidence = Column(Float)
    match_reason = Column(Text)
    pack_size_warning = Column(Boolean, default=False)
    manual_override = Column(Boolean, default=False)
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Module 3: Monitoring ─────────────────────────────────────────────────────

class FactMonitoringAlert(Base):
    """Monitoring-alerts voor concurrentieprijzen en -voorraad."""
    __tablename__ = "fact_monitoring_alert"

    alert_id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    own_sku_id = Column(String(100), index=True)
    competitor_id = Column(Integer, ForeignKey("dim_competitor.competitor_id"))
    alert_type = Column(String(100))
    severity = Column(String(20))
    message = Column(Text)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Module 4: Execution ──────────────────────────────────────────────────────

class PriceExecutionJob(Base):
    """Uitvoering-batch voor goedgekeurde prijswijzigingen."""
    __tablename__ = "price_execution_job"

    job_id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))
    execution_mode = Column(String(50))
    status = Column(String(50), default="aangemaakt")
    approved_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    export_file_path = Column(String(500))
    error_message = Column(Text)


class PriceExecutionLine(Base):
    """Eén SKU-prijsregel binnen een uitvoering-batch."""
    __tablename__ = "price_execution_line"

    line_id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("price_execution_job.job_id"), nullable=False, index=True)
    sku_id = Column(String(100), nullable=False)
    old_price = Column(Numeric(10, 4))
    new_price = Column(Numeric(10, 4))
    change_pct = Column(Float)
    status = Column(String(50), default="gepland")
    reason_code = Column(String(100))
    rollback_price = Column(Numeric(10, 4))
    created_at = Column(DateTime, default=datetime.utcnow)
