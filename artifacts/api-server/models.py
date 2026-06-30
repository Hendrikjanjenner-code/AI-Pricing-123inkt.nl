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
    # Paper_Copy pilot fields (nullable — filled only for paper products)
    paper_size = Column(String(20))        # A4 / A3 / A5 / etc.
    paper_weight_gsm = Column(Integer)     # gram per vierkante meter
    sheets_per_pack = Column(Integer)      # vel per pak
    # DRS Datareport fields
    product_type = Column(String(50))      # OEM / Compatible / Huismerk
    oem_code = Column(String(100))         # OEM artikelnummer
    afzet_ytd = Column(Float)             # eenheden YTD huidig jaar
    omzet_ytd = Column(Numeric(14, 4))    # omzet YTD huidig jaar
    marge_ytd = Column(Numeric(14, 4))    # marge YTD huidig jaar
    afzet_ytd_1j = Column(Float)          # eenheden YTD vorig jaar
    omzet_ytd_1j = Column(Numeric(14, 4))
    marge_ytd_1j = Column(Numeric(14, 4))
    afzet_ytd_2j = Column(Float)          # eenheden YTD 2 jaar geleden
    omzet_ytd_2j = Column(Numeric(14, 4))
    marge_ytd_2j = Column(Numeric(14, 4))
    avg_units_per_order = Column(Float)    # gemiddeld aantal per order
    aanmaakdatum = Column(Date)            # datum aangemaakt in DRS
    eerste_verkoop = Column(Date)          # datum eerste verkoop
    price_incl_vat = Column(Numeric(10, 4))    # Verkoopprijs incl BTW
    is_active = Column(Boolean, default=True)  # actief in DRS
    import_source = Column(String(50))     # "DRS" / "CSV" / "seed"
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
    competitor_strategy_signal = Column(JSON)
    safety_status = Column(String(50), default="ok")
    approval_status = Column(String(50), default="pending")
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    exported = Column(Boolean, default=False)
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


class ScrapeSchedule(Base):
    """Dagelijkse scrape-tijdsloten (standaard 3× per dag: 08:00, 13:00, 18:00)."""
    __tablename__ = "scrape_schedule"

    id = Column(Integer, primary_key=True, index=True)
    time_slot = Column(String(5), nullable=False, unique=True)  # HH:MM
    label = Column(String(100))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    triggered_by = Column(String(20), default="manual", index=True)  # manual | scheduled


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


class DimCategoryHierarchy(Base):
    """Hiërarchische categoriestructuur afkomstig uit DRS Datareport Hierarchy-tabblad."""
    __tablename__ = "dim_category_hierarchy"

    category_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    category_name = Column(String(255), nullable=False)
    parent_category_id = Column(Integer, nullable=True, index=True)
    category_level = Column(Integer, nullable=False)    # 1=categorie / 2=subcategorie / 3=sub-subcategorie
    path = Column(String(1000))                         # volledig pad bv. "Inkt & Toner > Cartridges"
    module = Column(String(500))                        # actieve modules kommagescheiden: Pricing,Competition,BCG
    active = Column(Boolean, default=True, nullable=False)
    import_source = Column(String(50), default="DRS")
    created_at = Column(DateTime, default=datetime.utcnow)


class FactPromotionsDaily(Base):
    """Placeholder: dagelijkse promotiedata per SKU (koppeling volgt)."""
    __tablename__ = "fact_promotions_daily"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    promotion_type = Column(String(100))
    discount_pct = Column(Float)
    discount_eur = Column(Numeric(10, 4))
    channel = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class FactSupplierData(Base):
    """Placeholder: leveranciersdata per SKU (koppeling volgt)."""
    __tablename__ = "fact_supplier_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sku_id = Column(String(100), nullable=False, index=True)
    supplier_id = Column(String(100))
    supplier_name = Column(String(255))
    lead_time_days = Column(Integer)
    moq = Column(Integer)                              # minimum order quantity
    purchase_price = Column(Numeric(10, 4))
    valid_from = Column(Date)
    valid_to = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)


class FactLogisticsCost(Base):
    """Placeholder: logistieke kosten per SKU (koppeling volgt)."""
    __tablename__ = "fact_logistics_cost"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    pick_cost = Column(Numeric(10, 4))
    pack_cost = Column(Numeric(10, 4))
    ship_cost = Column(Numeric(10, 4))
    return_cost = Column(Numeric(10, 4))
    total_logistics_cost = Column(Numeric(10, 4))
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Traffic Driver & Basket Intelligence Engine ───────────────────────────────

class FactSkuEcosystemDaily(Base):
    """Dagelijkse ecosysteemwaarde per SKU: gecombineerde commerciële bijdrage."""
    __tablename__ = "fact_sku_ecosystem_daily"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    sku_name = Column(String(500))
    category = Column(String(255))

    # Component scores (0–1)
    traffic_driver_score = Column(Float, default=0.0)       # TDS
    basket_builder_score = Column(Float, default=0.0)       # BBS
    margin_amplification_score = Column(Float, default=0.0) # MAS
    entry_product_score = Column(Float, default=0.0)        # EPS
    repeat_contribution_score = Column(Float, default=0.0)  # RCS
    private_label_contribution = Column(Float, default=0.0) # PLCS
    margin_contribution_score = Column(Float, default=0.0)  # directe marge

    # Totale SEVS
    ecosystem_value_score = Column(Float, default=0.0)      # SEVS 0–1
    sevs_label = Column(String(50))                          # KRITIEK / HOOG / MEDIUM / LAAG

    # SKU rollen (komma-gescheiden)
    primary_sku_role = Column(String(100))      # TRAFFIC_DRIVER / BASKET_BUILDER / ...
    secondary_sku_role = Column(String(200))    # kommalijst

    # Pricing-implicaties
    pricing_sensitivity = Column(String(50))    # HOOG / MEDIUM / LAAG
    protection_advice = Column(String(100))     # BESCHERMEN / OPTIMALISEREN / NEUTRALE / ...
    strategic_note_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


class FactBasketIntelligenceDaily(Base):
    """Dagelijkse winkelmand-analyse per SKU."""
    __tablename__ = "fact_basket_intelligence_daily"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    sku_name = Column(String(500))
    category = Column(String(255))

    # Basket-statistieken
    attach_rate = Column(Float)                  # % bestellingen met bijproduct
    avg_basket_value = Column(Numeric(10, 4))    # gem. mandbedrag incl. dit SKU
    avg_items_per_basket = Column(Float)         # gem. items per bestelling
    basket_co_occurrence_score = Column(Float)   # 0–1: hoe vaak samen met andere topSKUs
    cross_sell_frequency = Column(Float)         # gem. cross-sell producten per bestelling
    incremental_margin = Column(Numeric(10, 4))  # extra marge door basket-uitbreiding
    basket_uplift_eur = Column(Numeric(10, 4))   # gem. extra EUR per bestelling door dit SKU

    # Score
    basket_builder_score = Column(Float)         # BBS 0–1
    bbs_label = Column(String(50))               # KRITIEK / STERK / MATIG / ZWAK

    # Top co-occurerende SKU's (JSON string)
    top_co_skus = Column(Text)                   # kommalijst van sku_ids

    created_at = Column(DateTime, default=datetime.utcnow)


class FactTrafficDriverScoreDaily(Base):
    """Dagelijkse Traffic Driver Score per SKU."""
    __tablename__ = "fact_traffic_driver_score_daily"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    sku_name = Column(String(500))
    category = Column(String(255))

    # Traffic-bronnen
    seo_traffic = Column(Integer, default=0)
    sea_traffic = Column(Integer, default=0)
    direct_traffic = Column(Integer, default=0)
    total_traffic = Column(Integer, default=0)
    organic_visibility = Column(Float)           # 0–1
    search_volume = Column(Integer, default=0)   # extern maandelijks zoekvolume
    landing_page_sessions = Column(Integer, default=0)
    new_customer_entries = Column(Integer, default=0)
    ctr = Column(Float)                          # klikratio

    # Entry product metrics
    first_product_in_session_pct = Column(Float) # % sessies waar dit SKU eerste is
    new_customer_first_order_pct = Column(Float) # % orders van nieuwe klanten

    # Scores
    traffic_driver_score = Column(Float)         # TDS 0–1
    entry_product_score = Column(Float)          # EPS 0–1
    tds_label = Column(String(50))               # KRITIEK / STERK / MATIG / LAAG
    toelichting_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


# ── Cost Change & Break-even Intelligence Engine ─────────────────────────────

class FactCostChangeDaily(Base):
    """Dagelijkse inkoopprijswijzigingen en kostenstructuurmutaties per SKU."""
    __tablename__ = "fact_cost_change_daily"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    sku_name = Column(String(500))
    category = Column(String(255))

    # Inkoopprijswijziging
    previous_cost_price = Column(Numeric(10, 4))
    current_cost_price = Column(Numeric(10, 4))
    cost_change_pct = Column(Float)            # % wijziging inkoopprijs
    cost_change_type = Column(String(100))     # SUPPLIER / TRANSPORT / CURRENCY / SURCHARGE / FULFILMENT / MARKETING

    # Kostencomponenten (absolute bedragen)
    transport_cost = Column(Numeric(10, 4))
    fulfillment_cost = Column(Numeric(10, 4))
    marketing_cost = Column(Numeric(10, 4))
    operational_cost = Column(Numeric(10, 4))
    total_unit_cost = Column(Numeric(10, 4))

    # Prijzen & marges
    current_selling_price = Column(Numeric(10, 4))
    gross_margin = Column(Float)               # %
    net_margin = Column(Float)                 # %
    contribution_margin = Column(Float)        # absolute EUR

    # Scores
    ppfs_score = Column(Float)                 # Price Pass-through Feasibility Score 0–1
    mps_score = Column(Float)                  # Margin Protection Score 0–1
    severity = Column(String(50))              # KRITIEK / HOOG / MEDIUM / LAAG
    aanbeveling = Column(String(100))          # FULL_PASS_THROUGH / PARTIAL / NO_PASS_THROUGH / ...
    reason_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


class FactBreakEvenAnalysisDaily(Base):
    """Break-even analyse: hoeveel extra afzet nodig bij prijsverlaging/promotie."""
    __tablename__ = "fact_break_even_analysis_daily"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    sku_name = Column(String(500))
    category = Column(String(255))

    # Scenario
    scenario_type = Column(String(100))        # PRICE_REDUCTION / PROMOTION / BUNDLE / LAUNCH / CATEGORY_PROMO
    current_price = Column(Numeric(10, 4))
    proposed_price = Column(Numeric(10, 4))
    price_change_pct = Column(Float)

    # Marges
    current_margin_per_unit = Column(Numeric(10, 4))
    new_margin_per_unit = Column(Numeric(10, 4))
    margin_loss_per_unit = Column(Numeric(10, 4))
    current_units_sold = Column(Integer)

    # Break-even berekeningen
    break_even_extra_units = Column(Float)     # extra eenheden nodig
    break_even_extra_units_pct = Column(Float) # % meer dan huidige afzet
    break_even_extra_revenue = Column(Numeric(12, 4))
    break_even_extra_traffic = Column(Float)   # extra bezoekers nodig
    required_conversion_uplift = Column(Float) # % conversie uplift nodig

    # Scores
    break_even_difficulty_score = Column(Float)  # BEDS 0–1
    beds_label = Column(String(50))              # HAALBAAR / MOEILIJK / ONMOGELIJK
    aanbeveling = Column(String(100))
    waarschuwing = Column(String(200))           # alert code
    toelichting_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


class FactPricePassThroughDaily(Base):
    """Price Pass-through Feasibility Score (PPFS) per SKU per dag."""
    __tablename__ = "fact_price_pass_through_daily"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    sku_name = Column(String(500))
    category = Column(String(255))

    # Leveranciersinformatie
    supplier_cost_change_pct = Column(Float)       # % inkoopprijswijziging
    proposed_price_change_pct = Column(Float)      # % voorgestelde verkoopprijswijziging
    pass_through_ratio = Column(Float)             # voorstel / inkoopwijziging

    # Scores & sub-factoren
    ppfs_score = Column(Float)                     # 0–1
    ppfs_label = Column(String(50))                # STERK / GOED / MATIG / RISICOVOL
    elasticity_score = Column(Float)               # 0–1 (laag = inelastisch = makkelijker)
    pricing_power_score = Column(Float)            # 0–1
    competition_pressure = Column(Float)           # 0–1 (hoog = moeilijk)
    bcg_factor = Column(Float)                     # 0–1
    demand_factor = Column(Float)                  # 0–1
    conversion_health = Column(Float)              # 0–1

    # Uitkomst
    recommendation = Column(String(100))
    reason_code = Column(String(100))
    toelichting_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


class Promotion(Base):
    """Promoties per SKU — geïmporteerd via CSV (pilotformaat)."""
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    promotion_type = Column(String(100))           # percentage_off / fixed_amount / buy_x_get_y
    discount_value = Column(Float)                 # % of € afhankelijk van type
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    channel = Column(String(100))                  # online / instore / both
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class FactMarketingVsDiscountDaily(Base):
    """Vergelijking marketing-push vs prijsverlaging per SKU."""
    __tablename__ = "fact_marketing_vs_discount_daily"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    sku_name = Column(String(500))
    category = Column(String(255))

    # Scenario
    scenario_type = Column(String(100))            # PRICE_REDUCTION / PUSH_SEO / PUSH_SEA / COMBINED

    # Verwachte uitkomsten
    expected_revenue = Column(Numeric(12, 4))
    expected_margin = Column(Float)                # %
    expected_margin_eur = Column(Numeric(12, 4))
    expected_traffic = Column(Integer)
    expected_conversion = Column(Float)
    expected_roas = Column(Float)
    expected_extra_units = Column(Integer)

    # Scores
    meds_score = Column(Float)                     # Marketing Efficiency vs Discount Score 0–1
    drs_score = Column(Float)                      # Demand Recovery Score 0–1

    recommended_strategy = Column(String(100))
    toelichting_nl = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


class SchemaMigration(Base):
    """
    Audit trail of schema changes applied automatically by the lightweight
    auto-migrator (migrate.py). One row per column the migrator has added to an
    existing table, recording when it was applied. Provides a history so that,
    after a deployment, it is possible to see exactly which columns were added
    automatically and when.
    """
    __tablename__ = "schema_migrations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    change_key = Column(String(512), unique=True, nullable=False, index=True)  # e.g. "dim_product.paper_size"
    change_type = Column(String(50), nullable=False, default="add_column")
    table_name = Column(String(255), nullable=False)
    column_name = Column(String(255))
    ddl = Column(Text)             # the exact DDL statement that was executed
    applied_at = Column(DateTime, default=datetime.utcnow, index=True)


# ─────────────────────────────────────────────────────────────────────────────
# COMPETITION INTELLIGENCE ENGINE 2.0
# ─────────────────────────────────────────────────────────────────────────────

class CompetitorDiscoveryQueue(Base):
    """
    Automatisch ontdekte concurrenten die wachten op goedkeuring (PROPOSED)
    of al zijn verwerkt (APPROVED / REJECTED).
    """
    __tablename__ = "competitor_discovery_queue"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(500), nullable=False)
    competitor_name = Column(String(255))
    discovery_reason = Column(Text)
    discovery_method = Column(String(100))   # KEYWORD / OEM / CATEGORY / EAN / PATTERN
    categories = Column(JSON)                # lijst categorie-namen waar overlap is
    confidence = Column(Float, default=0.0)  # 0.0–1.0
    status = Column(String(50), default="PROPOSED")  # PROPOSED / APPROVED / REJECTED
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    run_id = Column(String(100), index=True) # koppeling aan discovery-run
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CompetitorProfile(Base):
    """
    Automatisch opgebouwd profiel per goedgekeurde concurrent
    op basis van scrape- en prijsdata.
    """
    __tablename__ = "competitor_profile"

    id = Column(Integer, primary_key=True, index=True)
    competitor_name = Column(String(255), nullable=False, unique=True, index=True)
    domain = Column(String(500))

    # Assortiment
    assortment_size = Column(Integer, default=0)     # aantal SKU's in onze categorieën
    category_breadth = Column(Integer, default=0)    # aantal categorieën
    top_brands = Column(JSON)                        # lijst top-5 merken
    top_categories = Column(JSON)                    # lijst top-5 categorieën

    # Prijssegment
    price_segment = Column(String(50))               # BUDGET / MIDDEN / PREMIUM
    premium_share_pct = Column(Float)                # % premium SKU's
    budget_share_pct = Column(Float)                 # % budget SKU's
    avg_price_index = Column(Float)                  # eigen prijs / concurrent gemiddeld

    # Activiteit
    price_change_frequency = Column(Float)           # prijswijzigingen per week
    last_price_change_date = Column(Date)
    avg_delivery_days = Column(Float)
    in_stock_rate = Column(Float)                    # % tijd op voorraad

    # Relevantie
    functional_overlap_score = Column(Float)         # 0–1 functionele overlap
    relevance_label = Column(String(20))             # HIGH / MONITOR / LOW

    # Verkeerslichtstatus voor UI
    traffic_light = Column(String(10))               # green / orange / red

    run_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CategoryCompetitorRelevance(Base):
    """
    Zeven categoryscores per concurrent per DRS-categorie.
    Vormt de basis voor de categorie-analyseview en managementadviezen.
    """
    __tablename__ = "category_competitor_relevance"

    id = Column(Integer, primary_key=True, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)
    category = Column(String(255), nullable=False, index=True)

    # Zeven scores 0–100
    relevance_score = Column(Float, default=0.0)          # Category Relevance Score
    coverage_index = Column(Float, default=0.0)           # Coverage Index
    authority_score = Column(Float, default=0.0)          # Authority Score
    assortment_gap_score = Column(Float, default=0.0)     # Assortment Gap Score
    pricing_relevance_score = Column(Float, default=0.0)  # Pricing Relevance Score
    traffic_relevance_score = Column(Float, default=0.0)  # Traffic Relevance Score
    opportunity_score = Column(Float, default=0.0)        # Opportunity Score

    # Gecombineerde relevantieclassificatie
    combined_score = Column(Float, default=0.0)
    relevance_label = Column(String(20))  # HIGH / MONITOR / LOW
    traffic_light = Column(String(10))    # green / orange / red

    # Textverklaringen
    relevance_explanation = Column(Text)
    opportunity_explanation = Column(Text)

    # Ontbrekende data
    missing_brands = Column(JSON)
    missing_product_types = Column(JSON)
    missing_price_segments = Column(JSON)

    run_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)


class AiMatchResult(Base):
    """
    AI-matching resultaat per eigen SKU gekoppeld aan een concurrent-SKU.
    Geeft match-type, confidence en Nederlandse uitleg.
    """
    __tablename__ = "ai_match_result"

    id = Column(Integer, primary_key=True, index=True)
    own_sku_id = Column(String(100), nullable=False, index=True)
    competitor_name = Column(String(255), nullable=False)
    competitor_sku = Column(String(200))
    competitor_url = Column(Text)

    # Match-resultaat
    match_type = Column(String(50))   # Exact / Sterk / Functioneel / Categorie_Alternatief / Geen_Match
    confidence = Column(Float, default=0.0)  # 0.0–1.0
    explanation_nl = Column(Text)

    # Gebruikte signalen
    ean_match = Column(Boolean, default=False)
    mpn_match = Column(Boolean, default=False)
    oem_match = Column(Boolean, default=False)
    brand_match = Column(Boolean, default=False)
    product_type_match = Column(Boolean, default=False)
    price_segment_match = Column(Boolean, default=False)

    # Prijsdata
    competitor_price = Column(Numeric(10, 4))
    own_price = Column(Numeric(10, 4))
    price_diff_pct = Column(Float)

    # Status
    status = Column(String(50), default="PENDING")   # PENDING / APPROVED / REJECTED
    approved_by = Column(String(100))
    approved_at = Column(DateTime)

    run_date = Column(Date, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorStrategyResult(Base):
    """
    Strategie-herkenningsresultaat per concurrent (verrijkt met confidence + uitleg).
    Bevat ook historiek van strategiewisselingen.
    """
    __tablename__ = "competitor_strategy_result"

    id = Column(Integer, primary_key=True, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)

    strategy_type = Column(String(100))   # EVERYDAY_LOW_PRICE / PROMOTION_DRIVEN / etc.
    strategy_label_nl = Column(String(255))
    confidence = Column(Float, default=0.0)
    explanation_nl = Column(Text)
    recommended_action_nl = Column(Text)

    # Periode
    period_days = Column(Integer, default=30)
    data_points = Column(Integer, default=0)

    # Historisch: vorige strategie (voor tijdlijn)
    previous_strategy_type = Column(String(100))
    strategy_changed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class AssortmentGap(Base):
    """
    Assortimentsgap per categorie: welke merken, typen, segmenten ontbreken.
    """
    __tablename__ = "assortment_gap"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(255), nullable=False, index=True)
    competitor_name = Column(String(255), nullable=False)

    gap_type = Column(String(50))     # MERK / PRODUCTTYPE / PRIJSSEGMENT / OEM_KANS
    gap_value = Column(String(500))   # naam van het ontbrekende merk / type / segment
    opportunity_score = Column(Float, default=0.0)   # 0–100
    explanation_nl = Column(Text)

    # Extra context
    competitor_has = Column(Boolean, default=True)  # concurrent heeft dit, wij niet
    potential_revenue_eur = Column(Float)            # geschat revenue-potentieel

    run_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorDiscoveryRun(Base):
    """
    Log van elke discovery-run: wanneer, hoeveel gevonden, parameters.
    """
    __tablename__ = "competitor_discovery_run"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), unique=True, nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String(50), default="running")  # running / completed / failed

    categories_searched = Column(JSON)
    candidates_found = Column(Integer, default=0)
    candidates_new = Column(Integer, default=0)
    candidates_approved = Column(Integer, default=0)
    candidates_rejected = Column(Integer, default=0)

    parameters = Column(JSON)     # discovery-parameters gebruikt
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
