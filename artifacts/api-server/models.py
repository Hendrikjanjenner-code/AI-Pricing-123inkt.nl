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


# ─── BCG Intelligence Engine ──────────────────────────────────────────────────

class FactBcgClassificationDaily(Base):
    """Dagelijkse BCG-classificatie per SKU of categorie (intern, extern, hybrid)."""
    __tablename__ = "fact_bcg_classification_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)   # SKU or CATEGORY
    entity_id = Column(String(200), nullable=False, index=True)
    entity_name = Column(String(500))

    # BCG classificaties
    internal_bcg_class = Column(String(50))   # INTERNAL_STAR / INTERNAL_CASH_COW / ...
    external_bcg_class = Column(String(50))   # EXTERNAL_STAR / ...
    hybrid_bcg_class = Column(String(80))     # PRICING_POWER_STAR / DEFENSIVE_CASH_COW / ...

    # Scores 0.00–1.00
    ibss_score = Column(Float)                # Internal Business Strength Score
    gps_score = Column(Float)                 # Growth Potential Score
    css_external_score = Column(Float)        # Competitive Strength Score (extern)
    mos_score = Column(Float)                 # Market Opportunity Score
    pricing_power_score = Column(Float)       # Pricing Power Score
    plsv_score = Column(Float)                # Private Label Strategic Value Score

    # Pricingstrategie aanbeveling
    pricing_strategy = Column(String(100))    # PROTECT_MARGIN / DEFEND_MARKET_POSITION / ...
    strategic_priority = Column(String(20))   # hoog / gemiddeld / laag
    confidence_score = Column(Float, default=0.8)

    created_at = Column(DateTime, default=datetime.utcnow)


class FactBcgHistory(Base):
    """Wijzigingshistorie van BCG-classificaties."""
    __tablename__ = "fact_bcg_history"

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(String(200), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)
    classification_type = Column(String(20))  # internal / external / hybrid
    old_classification = Column(String(80))
    new_classification = Column(String(80))
    changed_at = Column(DateTime, default=datetime.utcnow)
    reason = Column(String(500))


class FactPrivateLabelIntelligence(Base):
    """Huismerk-intelligence per SKU: ISV, PLSV en strategische prioriteit."""
    __tablename__ = "fact_private_label_intelligence"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    run_date = Column(Date, nullable=False)

    internal_substitution_score = Column(Float)    # kans dat klant overstapt naar huismerk
    internal_switch_probability = Column(Float)    # sub-component van ISV
    internal_margin_gap = Column(Float)            # margverschil per eenheid (€)
    private_label_value_score = Column(Float)      # PLSV 0–1
    private_label_class = Column(String(80))       # PRIVATE_LABEL_STAR / GROWTH / DEFENSIVE / LOW_PRIORITY
    strategic_priority = Column(String(20))        # hoog / gemiddeld / laag
    a_brand_sku = Column(String(100))              # gekoppeld A-merk SKU (indien huismerk)
    paired_sku_name = Column(String(500))

    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Traffic & Demand Intelligence Engine ─────────────────────────────────────

class FactTrafficDaily(Base):
    """Dagelijkse interne traffic per SKU of categorie."""
    __tablename__ = "fact_traffic_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)   # SKU / CATEGORY
    entity_id = Column(String(200), nullable=False, index=True)

    pageviews = Column(Integer, default=0)
    sessions = Column(Integer, default=0)
    unique_visitors = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    add_to_cart = Column(Integer, default=0)
    orders = Column(Integer, default=0)
    units_sold = Column(Integer, default=0)
    revenue = Column(Numeric(12, 4))
    margin = Column(Numeric(12, 4))
    bounce_rate = Column(Float)                    # 0.0–1.0
    avg_time_on_page = Column(Float)               # seconden
    internal_search_count = Column(Integer, default=0)
    channel = Column(String(50))                   # organic / paid / direct / email / social
    device_type = Column(String(20))               # desktop / mobile / tablet

    created_at = Column(DateTime, default=datetime.utcnow)


class FactSearchDemandDaily(Base):
    """Externe zoekvraag per keyword, SKU of categorie."""
    __tablename__ = "fact_search_demand_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)
    entity_id = Column(String(200), nullable=False, index=True)

    keyword = Column(String(500), nullable=False)
    keyword_type = Column(String(20))              # BRAND / GENERIC / EAN / MPN / CATEGORY
    search_volume = Column(Integer, default=0)     # maandelijks zoekvolume
    impressions = Column(Integer, default=0)       # eigen vertoningen
    clicks = Column(Integer, default=0)            # eigen klikken
    ctr = Column(Float)                            # klikratio eigen vertoningen
    average_position = Column(Float)               # gemiddelde eigen positie
    trend_index = Column(Float)                    # 0.0–1.0 (Google Trends-stijl)
    competition_level = Column(Float)              # 0.0–1.0
    cpc_estimate = Column(Numeric(8, 4))           # geschatte CPC in €
    source = Column(String(50))                    # google / bing / amazon / gsc

    created_at = Column(DateTime, default=datetime.utcnow)


class FactTrafficIntelligenceDaily(Base):
    """Dagelijkse traffic intelligence scores per SKU of categorie."""
    __tablename__ = "fact_traffic_intelligence_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)
    entity_id = Column(String(200), nullable=False, index=True)
    entity_name = Column(String(500))

    # Vijf kernscores (0.00–1.00)
    demand_signal_score = Column(Float)            # DSS — totale vraag
    conversion_health_score = Column(Float)        # CHS — conversiegezondheid
    traffic_opportunity_score = Column(Float)      # TOS — traffic kansen
    conversion_risk_score = Column(Float)          # CRS — conversierisico
    search_gap_score = Column(Float)               # SGS — zoekgap

    # Trends
    traffic_growth = Column(Float)                 # % groei t.o.v. vorige periode
    conversion_trend = Column(Float)               # % verandering conversieratio

    # Signaal en uitleg
    reason_code = Column(String(100))              # CONVERSION_DROP_DETECTED / ...
    explanation_nl = Column(Text)                  # Nederlandse uitleg

    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# COST INTELLIGENCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class FactCostDaily(Base):
    """Dagelijkse volledige kostenstructuur per SKU."""
    __tablename__ = "fact_cost_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(50), nullable=False, index=True)
    category = Column(String(200))
    sku_name = Column(String(500))

    # Directe kosten (€ per eenheid)
    purchase_cost = Column(Numeric(10, 4))       # inkoopkosten
    transport_cost = Column(Numeric(10, 4))      # transportkosten
    dropshipping_cost = Column(Numeric(10, 4))   # dropshipping kosten
    fulfilment_cost = Column(Numeric(10, 4))     # fulfilmentkosten
    packaging_cost = Column(Numeric(10, 4))      # verpakkingskosten

    # Indirecte kosten (€ per eenheid)
    labour_cost = Column(Numeric(10, 4))         # personeelskosten (ABC)
    marketplace_fee = Column(Numeric(10, 4))     # marketplace fees (%)
    return_cost = Column(Numeric(10, 4))         # retourkosten
    overhead_cost = Column(Numeric(10, 4))       # operationele overhead

    # Totalen
    total_direct_cost = Column(Numeric(10, 4))
    total_indirect_cost = Column(Numeric(10, 4))
    total_cost = Column(Numeric(10, 4))

    # Verkoopprijs en marges
    selling_price = Column(Numeric(10, 4))
    gross_margin = Column(Numeric(10, 4))        # verkoopprijs - directe kosten
    net_margin = Column(Numeric(10, 4))          # verkoopprijs - totale kosten
    net_margin_pct = Column(Float)               # netto marge %

    # Signaal
    cost_signal = Column(String(100))            # MARGIN_CRITICAL / COST_RISING / HEALTHY
    cost_signal_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


class FactMarketingCostDaily(Base):
    """Dagelijkse marketing kosten en efficiëntie per SKU."""
    __tablename__ = "fact_marketing_cost_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(50), nullable=False, index=True)
    category = Column(String(200))
    sku_name = Column(String(500))

    # SEO kosten
    seo_cost = Column(Numeric(10, 4))
    seo_impressions = Column(Integer, default=0)
    seo_clicks = Column(Integer, default=0)
    seo_conversions = Column(Integer, default=0)
    seo_revenue = Column(Numeric(12, 2))

    # SEA kosten
    sea_cost = Column(Numeric(10, 4))
    sea_impressions = Column(Integer, default=0)
    sea_clicks = Column(Integer, default=0)
    sea_conversions = Column(Integer, default=0)
    sea_revenue = Column(Numeric(12, 2))

    # Efficiëntiemetrics
    cac = Column(Numeric(10, 4))                        # Customer Acquisition Cost
    roas = Column(Float)                                 # Return on Ad Spend
    seo_efficiency = Column(Float)                       # 0.0–1.0
    sea_efficiency = Column(Float)                       # 0.0–1.0
    marketing_dependency_score = Column(Float)           # 0.0–1.0

    # Netto marges
    total_marketing_cost = Column(Numeric(10, 4))
    margin_after_marketing = Column(Numeric(10, 4))
    contribution_margin_pct = Column(Float)

    # Signaal
    marketing_signal = Column(String(100))               # HIGH_CAC / LOW_ROAS / EFFICIENT
    marketing_signal_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


class FactOperationalComplexityDaily(Base):
    """Dagelijkse operationele complexiteitsscore per SKU (Activity-Based Costing)."""
    __tablename__ = "fact_operational_complexity_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(50), nullable=False, index=True)
    category = Column(String(200))
    sku_name = Column(String(500))

    # ABC factoren (0.0–1.0)
    pick_time_score = Column(Float)             # picktijd
    packaging_time_score = Column(Float)        # verpakkingstijd
    return_pressure = Column(Float)             # retourdruk
    customer_service_load = Column(Float)       # klantenservicebelasting
    handling_complexity = Column(Float)         # handling complexiteit
    dropship_management = Column(Float)         # dropship management
    supplier_management = Column(Float)         # supplier management
    error_sensitivity = Column(Float)           # foutgevoeligheid

    # OCS (gewogen gemiddelde)
    operational_complexity_score = Column(Float)    # OCS 0.0–1.0
    ocs_label = Column(String(20))                  # LAAG / GEMIDDELD / HOOG / KRITIEK

    # Kosten
    labour_cost_per_unit = Column(Numeric(10, 4))
    total_operational_cost = Column(Numeric(10, 4))

    # Aanbeveling
    recommended_action = Column(String(300))

    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# FORECASTING & PROCUREMENT ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class FactProcurementForecastDaily(Base):
    """Dagelijkse procurement forecast en opportunity scores per SKU."""
    __tablename__ = "fact_procurement_forecast_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(50), nullable=False, index=True)
    category = Column(String(200))
    sku_name = Column(String(500))

    # Huidige positie
    current_purchase_price = Column(Numeric(10, 4))
    current_stock_days = Column(Integer)         # voorraad in dagen
    lead_time_days = Column(Integer)             # levertijd

    # Forecast (30/90 dagen)
    forecast_purchase_price_30d = Column(Numeric(10, 4))
    forecast_purchase_price_90d = Column(Numeric(10, 4))
    price_change_pct_30d = Column(Float)
    price_change_pct_90d = Column(Float)
    demand_forecast_30d = Column(Integer)        # verwachte eenheden
    demand_forecast_90d = Column(Integer)

    # Scores (0.0–1.0)
    procurement_opportunity_score = Column(Float)   # POS: nu inkopen?
    future_margin_risk_score = Column(Float)         # FMR: toekomstige margedruk
    seasonality_factor = Column(Float)               # seizoensinvloed

    # Signaal
    signal_code = Column(String(100))            # BUY_NOW / MARGIN_RISK / STABLE
    signal_label_nl = Column(String(500))
    recommended_order_qty = Column(Integer)
    recommended_action_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# ECONOMIC INTELLIGENCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class FactEconomicSignalDaily(Base):
    """Dagelijkse economische signalen met impact op pricing en procurement."""
    __tablename__ = "fact_economic_signal_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    signal_type = Column(String(50), nullable=False)    # RAW_MATERIAL / TRANSPORT / CURRENCY / etc.
    signal_name = Column(String(200), nullable=False)
    region = Column(String(100))                         # NL / EU / GLOBAL

    # Ernst
    severity = Column(String(20))                        # LAAG / GEMIDDELD / HOOG / KRITIEK
    severity_score = Column(Float)                       # 0.0–1.0

    # Waarden
    current_value = Column(Float)
    baseline_value = Column(Float)
    change_pct = Column(Float)                           # % verandering t.o.v. baseline
    unit = Column(String(50))                            # €/ton, $/container, EUR/USD, etc.

    # Impact
    affected_categories_json = Column(Text)              # JSON array van categorie IDs
    pricing_impact_pct = Column(Float)                   # verwachte prijsimpact %
    margin_impact_pct = Column(Float)                    # verwachte margeimpact %
    procurement_urgency = Column(String(50))             # DIRECT / BINNEN_MAAND / MONITOREN

    # Signaal code
    signal_code = Column(String(100))
    description_nl = Column(Text)
    recommended_action_nl = Column(Text)
    valid_until = Column(Date)

    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# BCG TRANSITION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class FactBcgTransition(Base):
    """BCG classificatiewijzigingen per SKU of categorie."""
    __tablename__ = "fact_bcg_transition"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)     # SKU / CATEGORY
    entity_id = Column(String(200), nullable=False, index=True)
    entity_name = Column(String(500))
    category = Column(String(200))

    # Transitie
    from_classification = Column(String(50))             # STAR / CASH_COW / QUESTION_MARK / DOG
    to_classification = Column(String(50))
    from_growth_score = Column(Float)
    to_growth_score = Column(Float)
    from_market_score = Column(Float)
    to_market_score = Column(Float)

    # Oorzaak
    trigger_code = Column(String(100))  # SKU_MOVED_TO_STAR / SKU_MOVED_TO_DOG / etc.
    trigger_reason_nl = Column(Text)
    business_impact_nl = Column(String(500))
    revenue_impact_eur = Column(Numeric(12, 2))

    # Aanbeveling
    recommended_action_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTIVE REPORTING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class FactManagementReport(Base):
    """Automatisch gegenereerde managementrapportages (dagelijks/wekelijks/maandelijks)."""
    __tablename__ = "fact_management_report"

    id = Column(Integer, primary_key=True, index=True)
    report_date = Column(Date, nullable=False, index=True)
    report_type = Column(String(20), nullable=False)     # DAGELIJKS / WEKELIJKS / MAANDELIJKS
    period_start = Column(Date)
    period_end = Column(Date)

    # Inhoud
    title_nl = Column(String(500))
    summary_nl = Column(Text)
    kpis_json = Column(Text)                             # JSON: {key: {value, delta, label}}
    alerts_json = Column(Text)                           # JSON: [{code, severity, message}]
    insights_json = Column(Text)                         # JSON: [{section, text}]
    recommendations_json = Column(Text)                  # JSON: [{priority, action}]

    # Metadata
    generated_at = Column(DateTime, default=datetime.utcnow)
    is_exported = Column(Boolean, default=False)
    export_filename = Column(String(500))

    created_at = Column(DateTime, default=datetime.utcnow)
