"""
SQLAlchemy ORM models for the Pricing Decision Engine.
All tables match the spec: users, dim_product, dim_category, etc.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Date, Numeric, JSON, Index, text, UniqueConstraint, Computed
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import relationship
from sqlalchemy.schema import CreateColumn, CreateIndex


# ── SQLite-portabiliteit voor Postgres-only kolommen ─────────────────────────
# Sommige tests draaien tegen een geïsoleerde SQLite-database via
# Base.metadata.create_all(). TSVECTOR en STORED generated columns met
# to_tsvector() bestaan daar niet; markeer zulke kolommen/indexen met
# info={"pg_only": True} zodat ze in SQLite-DDL worden overgeslagen.
@compiles(CreateColumn, "sqlite")
def _skip_pg_only_columns(element, compiler, **kw):
    """Sla Postgres-specifieke kolommen (tsvector + generated column) over in
    SQLite-DDL, zodat testsuites die een verse SQLite-DB aanmaken niet crashen
    op onbekende types/functies. Markeer zulke kolommen met info={'pg_only'}."""
    if element.element.info.get("pg_only"):
        return None
    return compiler.visit_create_column(element, **kw)


@compiles(CreateIndex, "sqlite")
def _skip_pg_only_indexes(element, compiler, **kw):
    """Idem voor indexen op pg_only-kolommen (bv. de GIN-index op de tsvector)."""
    if element.element.info.get("pg_only"):
        return "SELECT 1"  # no-op DDL: SQLite kent de kolom niet
    return compiler.visit_create_index(element, **kw)
from database import Base


class DimShop(Base):
    """
    Canonieke shop-dimensie (masterprompt §36): het platform is multi-shop
    voorbereid. Elke commerciële entiteit hoort bij precies één shop.
    De bestaande installatie draait met één default shop (id=1).
    """
    __tablename__ = "dim_shop"

    id = Column(Integer, primary_key=True, index=True)
    shop_code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    country = Column(String(2), default="NL")        # ISO 3166-1 alpha-2
    currency = Column(String(3), default="EUR")      # ISO 4217
    legal_entity = Column(String(255))
    channel = Column(String(50), default="online")   # online / retail / marketplace
    is_default = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class IntelligenceSignal(Base):
    """
    Gestandaardiseerd Commercial Intelligence Signal (masterprompt §7).
    Elke engine publiceert bevindingen in dit ene formaat zodat de Decision
    Engine, Copilot en dashboards ze uniform kunnen consumeren.
    Geen signaal zonder explanation + evidence (§64.9-10).
    """
    __tablename__ = "intelligence_signals"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)

    engine = Column(String(100), nullable=False, index=True)       # bv. competition, pricing, traffic
    signal_type = Column(String(100), nullable=False, index=True)  # bv. competitive_pressure_increased
    severity = Column(String(20), default="info")   # info / low / medium / high / critical
    direction = Column(String(20))                  # positive / negative / neutral

    entity_type = Column(String(50), nullable=False, index=True)   # sku / category / brand / competitor / shop
    entity_id = Column(String(255), nullable=False, index=True)
    entity_name = Column(String(500))

    # Centrale producthiërarchie (taak #217): voor SKU-signalen gevuld vanuit
    # de actieve hierarchy-assignment; maakt filteren op de Global Filter
    # Context en aggregatie SKU → subcategorie → categorie mogelijk.
    hierarchy_node_id = Column(Integer, index=True)   # node waar de entiteit onder valt
    hierarchy_path_id = Column(Integer)               # ProductHierarchyPath.id (leaf-pad)
    hierarchy_level = Column(Integer)                 # niveau van de node (1 = top)

    metric = Column(String(100))                    # centrale metric-naam (metrics.py)
    current_value = Column(Float)
    previous_value = Column(Float)
    expected_value = Column(Float)
    change_pct = Column(Float)

    confidence = Column(Float, default=0.0)         # 0..1
    explanation = Column(Text, nullable=False)      # verplicht: waarom dit signaal
    evidence = Column(JSON)                         # onderbouwende datapunten
    sources = Column(JSON)                          # gebruikte bronnen/tabellen
    suggested_action = Column(String(255))

    observed_at = Column(DateTime, default=datetime.utcnow, index=True)
    valid_until = Column(DateTime)
    model_version = Column(String(50))

    status = Column(String(20), default="active")   # active / expired / superseded / dismissed / resolved
    dedupe_key = Column(String(255), index=True)    # engine:signal_type:entity — voorkomt duplicaten
    created_at = Column(DateTime, default=datetime.utcnow)


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

class Department(Base):
    """
    Afdeling / workspace (taak 219). Elke afdeling definieert welke frontend-
    domeinen standaard zichtbaar zijn (workspace), welke permissies leden
    standaard krijgen en wat de default startpagina is.
    """
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    # Frontend-domein-ids (route-registry DomeinId) die deze workspace toont.
    workspace_domains = Column(JSON, default=list)
    # Permissiecodes die leden van deze afdeling standaard krijgen.
    default_permissions = Column(JSON, default=list)
    # Frontend-route die als startpagina/default view geldt.
    default_route = Column(String(255), default="/")
    positie = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
class DimCategory(Base):
    __tablename__ = "dim_category"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    parent_category = Column(String(255))
    default_strategy = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class DimProduct(Base):
    """
    Product-dimensie. Canonical grain-keuze (masterprompt §4): sku_id is
    GLOBAAL uniek over alle shops heen — hetzelfde artikel in een tweede shop
    krijgt een eigen sku_id. shop_id geeft de eigenaar-shop aan en wordt in
    shop-gescopeerde queries als filter gebruikt.
    """
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
    ean = Column(String(50))               # EAN-code (barcode)
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
    raw_attributes = Column(JSON)          # alle overige feedvelden (verliesvrij, per bron)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    price = Column(Numeric(10, 4))
    cost_price = Column(Numeric(10, 4))


class FactCompetitorPriceDaily(Base):
    __tablename__ = "fact_competitor_price_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    sku_id = Column(String(100), nullable=False, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 4))
    url = Column(Text)
    # Provenance of the row (e.g. "manual", "priceshape", "scraper"). Used to
    # scope destructive "vervangen" cleanups to a single pipeline so importing
    # one source never deletes competitor prices captured by another.
    source = Column(String(50), default="manual")
    # Volledige feed-data (PriceShape output feed levert meer dan alleen prijs):
    in_stock = Column(Boolean)                 # voorraadstatus bij de concurrent
    delivery_days = Column(Float)              # levertijd in dagen
    currency = Column(String(3))               # ISO 4217 valuta van de prijs
    vendor_name = Column(String(255))          # weergavenaam (naast domein)
    observed_at = Column(DateTime)             # timestamp uit de feed
    raw_attributes = Column(JSON)              # alle overige vendorvelden (verliesvrij)


class FactInventoryDaily(Base):
    __tablename__ = "fact_inventory_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    sku_id = Column(String(100), nullable=False, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    stock_quantity = Column(Integer, default=0)
    days_of_stock = Column(Float)


class FactBasketAffinity(Base):
    __tablename__ = "fact_basket_affinity"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
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
    # Verwerkingsstatus na export: 'niet_verwerkt' (nog niet geëxporteerd) of
    # 'verwerkt' (succesvol geëxporteerd naar DRS, via API-push of bestand).
    # Losstaand van approval_status, zodat concept -> review -> goedgekeurd ->
    # export -> verwerkt volledig zichtbaar blijft.
    processing_status = Column(String(50), default="niet_verwerkt")
    processed_at = Column(DateTime)
    model_version = Column(String(50))
    override_price = Column(Numeric(10, 4))
    override_reason = Column(Text)
    # Herkomst: gezet wanneer deze aanbeveling automatisch is aangemaakt bij
    # goedkeuring van een Decision (beslisketen: signaal → scenario →
    # goedkeuring → uitvoering). NULL voor reguliere engine-aanbevelingen.
    source_decision_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExportLog(Base):
    """Volledige exportgeschiedenis: elke API-push of bestand-download naar DRS."""
    __tablename__ = "export_log"

    id = Column(Integer, primary_key=True, index=True)
    export_type = Column(String(20), nullable=False)  # api_push, csv, xlsx, xls
    record_count = Column(Integer, default=0)
    recommendation_ids = Column(JSON)  # lijst van bron-recommendation-IDs
    performed_by = Column(String(100))
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="success")  # success, failed
    error_details = Column(Text)


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

class ScheduledEngineRun(Base):
    """
    Uitkomst per engine per shop per nacht (§ taak 51). scheduled_engines.py
    registreert hier succes/fout + tijdstip, zodat een herstart dezelfde dag
    idempotent is: shops/engines met een recente succesvolle run worden
    overgeslagen en alleen mislukte runs worden opnieuw geprobeerd.
    """
    __tablename__ = "scheduled_engine_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_date = Column(Date, nullable=False, index=True)
    # ondelete=CASCADE: run-historie is afgeleide administratie en mag een
    # shop-verwijdering nooit blokkeren.
    shop_id = Column(Integer, ForeignKey("dim_shop.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    engine_name = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="running")  # running / success / failed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)
    error_message = Column(Text)
    result_summary = Column(JSON)
class EngineRun(Base):
    """Run-log van de nachtelijke engines (scheduled_engines.py).

    Eén rij per engine per shop per run, zodat het dashboard kan tonen of de
    run van afgelopen nacht geslaagd is.
    """
    __tablename__ = "engine_runs"

    id = Column(Integer, primary_key=True, index=True)
    engine_name = Column(String(50), nullable=False, index=True)  # basket, promotion, forecast, opportunity
    shop_id = Column(Integer, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime)
    status = Column(String(20), nullable=False, default="running")  # running, success, failed
    error_message = Column(Text)
    result_summary = Column(JSON)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    upload_type = Column(String(100), nullable=False)
    filename = Column(String(500), nullable=False)
    # Volledige statuslevenscyclus (zie engine/import_engine.py STATUS_LIFECYCLE):
    # nieuw, concept, gevalideerd, geimporteerd, bijgewerkt, opgeslagen, fout.
    # Oudere waarden (pending/processing/completed/failed) blijven bestaan in
    # historische rijen en worden door de frontend nog steeds herkend.
    status = Column(String(50), default="nieuw")
    rows_processed = Column(Integer, default=0)
    rows_failed = Column(Integer, default=0)
    error_message = Column(Text)
    uploaded_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    import_mode = Column(String(50))       # aanvullen / updaten / vervangen
    warnings_json = Column(JSON)           # lijst met waarschuwingen van deze import
    source = Column(String(50))            # PriceShape / DRS / Handmatig / Paper_Copy
    file_type = Column(String(10))         # csv / xlsx / xls
    # Importbatch-verrijking (§29): elke import krijgt een uniek batch-ID en
    # gestructureerde tellingen accepted/rejected/duplicates plus een error-log.
    batch_id = Column(String(36), index=True)   # UUID per importbatch
    rows_duplicates = Column(Integer, default=0)  # dubbele rijen binnen de batch
    error_log = Column(JSON)               # gestructureerde foutregels [{rij, veld, bericht}]

class DataQualityIssue(Base):
    """
    Persistente datakwaliteits-issues (§30) met workflow.
    Elke detectie (issue_code) heeft één actuele rij die bij iedere
    kwaliteitsscan wordt bijgewerkt (affected_count, last_detected_at) en
    automatisch op 'opgelost' gaat zodra de detectie niets meer vindt.
    Owner en status zijn door gebruikers te beheren.
    """
    __tablename__ = "data_quality_issue"

    id = Column(Integer, primary_key=True, index=True)
    issue_code = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(300), nullable=False)
    message = Column(Text)
    severity = Column(String(20), default="warning")   # error / warning / info
    source = Column(String(100))          # PriceShape / DRS / GA4 / Handmatig / Systeem / AI
    module = Column(String(100))          # Producten / Prijzen / Concurrentie / Imports / AI-modellen / ...
    affected_count = Column(Integer, default=0)
    business_impact = Column(Text)        # zakelijke impact in het Nederlands
    suggested_action = Column(Text)       # aanbevolen vervolgactie
    owner = Column(String(100))           # toegewezen eigenaar (gebruikersnaam)
    status = Column(String(30), default="open")  # open / in_behandeling / genegeerd / opgelost
    first_detected_at = Column(DateTime, default=datetime.utcnow)
    last_detected_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    updated_by = Column(String(100))

class DataQualityScanRun(Base):
    """
    Audit van datakwaliteits-scans (§30): elke run — automatisch (scheduler)
    of handmatig (dashboard) — wordt vastgelegd zodat eigenaren kunnen zien
    wanneer de laatste scan liep en of die is geslaagd.
    """
    __tablename__ = "data_quality_scan_run"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime)
    triggered_by = Column(String(50), default="scheduler")  # scheduler / dashboard
    status = Column(String(20), default="bezig")            # bezig / geslaagd / fout
    error_message = Column(Text)
    issues_total = Column(Integer, default=0)
    error_issues = Column(Integer, default=0)
    warning_issues = Column(Integer, default=0)
    new_or_worse_errors = Column(Integer, default=0)         # aantal nieuwe/verergerde error-issues
    signals_published = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
class InAppNotification(Base):
    """
    In-app meldingen (taak: DQ-alerts ook in de app tonen).
    Elke melding is gericht aan één gebruiker (username); de nachtelijke
    datakwaliteits-scan maakt per nieuw/heropend issue een melding aan voor de
    eigenaar, of — zonder eigenaar — voor alle actieve beheerders.
    """
    __tablename__ = "in_app_notification"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, index=True)  # ontvanger
    type = Column(String(50), default="data_quality_issue")
    kind = Column(String(20))            # new / reopened
    title = Column(String(300), nullable=False)
    message = Column(Text)
    severity = Column(String(20), default="warning")
    link = Column(String(300))           # frontend-route, bv. /datakwaliteit
    reference = Column(String(150))      # bv. issue_code
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime)
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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
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
    method_label = Column(String(30))             # "regressie" | "heuristiek"
    regression_r2 = Column(Float)                 # R² van de OLS-fit (None bij heuristiek)

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


# ─── Concurrentenregister ────────────────────────────────────────────────────
# PriceShape is de externe prijsbron; interne scraping is verwijderd. Het
# concurrentenregister blijft bestaan voor competition-intelligence.

class FeedImportSetting(Base):
    """
    Importselectie-instellingen per connector (PriceShape): welke data-onderdelen
    en welke concurrenten worden geïmporteerd. Persistent (overleeft herstart) en
    toegepast door de feed-ingest, de connector-sync én de handmatige upload.

    components: {"own_prices": bool, "cost_prices": bool, "competitor_prices": bool,
                 "availability": bool, "extra_attributes": bool}
    disabled_competitors: lijst van concurrent-domeinen die worden overgeslagen.
    """
    __tablename__ = "feed_import_setting"

    id = Column(Integer, primary_key=True, index=True)
    connector_name = Column(String(100), unique=True, nullable=False, index=True)
    components = Column(JSON)
    disabled_competitors = Column(JSON)
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CompetitionSetting(Base):
    """
    Competition-intelligence instellingen per shop: discovery/matching-drempels
    en relevantiegewichten. Persistent (overleeft herstart) en gelezen door de
    discovery-, matching- en categoriescore-engines.

    settings: {"min_discovery_confidence": 0.6, "auto_approve_threshold": 0.9,
               "auto_discovery_enabled": false, "lookback_days": 30,
               "min_match_confidence": 0.5,
               "relevance_weights": {"pricing": 25, "assortment": 30,
                                     "traffic": 20, "authority": 15,
                                     "coverage": 10}}
    """
    __tablename__ = "competition_setting"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), unique=True,
                     nullable=False, index=True)
    settings = Column(JSON, nullable=False)
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
class DimCompetitor(Base):
    """Concurrentenregister (gevoed vanuit de PriceShape-feed / handmatig)."""
    __tablename__ = "dim_competitor"

    competitor_id = Column(Integer, primary_key=True, index=True)
    # Canoniek domein (genormaliseerd via services.domain_normalize).
    competitor_name = Column(String(255), nullable=False, unique=True)
    # Oorspronkelijke schrijfwijzen (aliassen) zoals ze in feeds voorkwamen,
    # zodat de herkomst van een genormaliseerd domein herleidbaar blijft.
    aliases = Column(JSON)
    # Laatst gezien in een feed-sync; een concurrent die uit de feed verdwijnt
    # wordt nooit verwijderd, alleen als "recent niet gezien" herkenbaar.
    last_seen_date = Column(Date)
    base_url = Column(String(500))
    competitor_type = Column(String(50), default="online")
    default_relevance_score = Column(Float, default=0.5)
    channel_relevance = Column(JSON)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# KEEP — al bevat dit model geen scraping meer, het wordt nog actief gelezen
# door de monitoring-routes (routes/monitoring.py: /run en /sku/{id}) voor de
# concurrent-prijshistorie en alertgeneratie. Niet verwijderen.
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

# KEEP — momenteel nog niet aangeroepen in code, maar bewust behouden: dit is de
# AI-match-goedkeuringstabel (own SKU ↔ concurrent, met approved_by/approved_at/
# manual_override) die de bulk-goedkeuring van AI-matches moet gaan voeden. De
# tabel bestaat al in de DB; verwijderen zou die workflow blokkeren. Niet weghalen
# zonder die feature mee te migreren.
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
    # Herkomst: de aanbeveling (fact_pricing_recommendation_daily.id) waaruit
    # deze regel is opgebouwd — nodig om een beslissing bewijsbaar aan de
    # juiste execution-job te koppelen.
    recommendation_id = Column(Integer, index=True)
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


class ProductHierarchyNode(Base):
    """
    Canonieke producthiërarchie (taak #215): één boom met 2–6+ dynamische
    niveaus. Interne id is immutable; external_option_id komt uit het
    bronbestand (optionId) en identificeert bladknopen over imports heen.
    """
    __tablename__ = "product_hierarchy_nodes"

    id = Column(Integer, primary_key=True, index=True)
    external_option_id = Column(String(100), unique=True, index=True)  # NULL toegestaan (tussenniveaus)
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey("product_hierarchy_nodes.id", ondelete="SET NULL"),
                       nullable=True, index=True)
    level = Column(Integer, nullable=False, default=1, index=True)     # 1 = topniveau
    # Gematerialiseerd pad van interne ids, bv. "/3/17/244/" — descendant-
    # queries zijn dan een prefix-LIKE op een geïndexeerde kolom.
    path = Column(String(1000), index=True)
    path_names = Column(String(2000))     # leesbaar pad "Kantoor > Papier > A4"
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    valid_from = Column(Date)             # geldigheidsperiode (optioneel)
    valid_to = Column(Date)
    source = Column(String(50), default="import")   # import / handmatig
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(100))
    updated_by = Column(String(100))

    __table_args__ = (
        Index("ix_ph_nodes_parent_name", "parent_id", "name"),
    )


class ProductHierarchyAssignment(Base):
    """
    Koppeling product ↔ hiërarchie-node. Niet-destructief: bij een verhuizing
    wordt de oude rij op status 'superseded' gezet (met valid_to) en een
    nieuwe actieve rij aangemaakt — mappings verdwijnen nooit stilzwijgend.
    """
    __tablename__ = "product_hierarchy_assignments"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), ForeignKey("dim_product.sku_id", ondelete="CASCADE"),
                    nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("product_hierarchy_nodes.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    is_primary = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="active", nullable=False, index=True)  # active / superseded
    valid_from = Column(DateTime, default=datetime.utcnow)
    valid_to = Column(DateTime)
    source = Column(String(50), default="import")
    assigned_by = Column(String(100))
    import_job_id = Column(Integer, index=True)   # herkomst-batch (ImportJob.id)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_ph_assign_sku_status", "sku_id", "status"),
        Index("ix_ph_assign_node_status", "node_id", "status"),
    )


class ProductHierarchyPath(Base):
    """Gematerialiseerde paden per bladknoop voor snelle rapportage/lookup."""
    __tablename__ = "product_hierarchy_paths"

    id = Column(Integer, primary_key=True, index=True)
    leaf_node_id = Column(Integer, ForeignKey("product_hierarchy_nodes.id", ondelete="CASCADE"),
                          nullable=False, unique=True, index=True)
    path_string = Column(String(2000), nullable=False)   # "Kantoor > Papier > A4"
    node_ids = Column(JSON)                              # [3, 17, 244]
    depth = Column(Integer, nullable=False, default=1)
    external_option_id = Column(String(100), index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProductHierarchyStagingRow(Base):
    """
    Staging voor de niet-destructieve import-wizard: elke bestandsrij wordt
    eerst hier geparkeerd (upload → validate → impact → approve → apply);
    er verandert niets aan de echte hiërarchie tot de apply-stap.
    """
    __tablename__ = "product_hierarchy_staging_rows"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("import_jobs.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    external_option_id = Column(String(100), index=True)
    product_code = Column(String(100), index=True)
    path_names = Column(JSON)             # ["Kantoor", "Papier", "A4"]
    matched_sku_id = Column(String(100), index=True)
    match_method = Column(String(30))     # drs_id / ean / oem / geen
    status = Column(String(20), default="nieuw", index=True)  # nieuw/geldig/fout/duplicaat
    message = Column(Text)


class ProductHierarchyChangeLog(Base):
    """
    Versie-/wijzigingshistorie van de hiërarchie: nieuwe, hernoemde,
    verplaatste en gedeactiveerde nodes plus verplaatste producttoewijzingen,
    met oud/nieuw, bron, gebruiker en tijdstip.
    """
    __tablename__ = "product_hierarchy_change_log"

    id = Column(Integer, primary_key=True, index=True)
    import_job_id = Column(Integer, index=True)
    node_id = Column(Integer, index=True)
    sku_id = Column(String(100), index=True)
    change_type = Column(String(40), nullable=False, index=True)
    # node_created / node_renamed / node_moved / node_deactivated /
    # node_reactivated / assignment_created / assignment_moved
    old_value = Column(JSON)
    new_value = Column(JSON)
    source = Column(String(50), default="import")
    performed_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), index=True)  # eigenaar-shop
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CompetitorProfile(Base):
    """
    Automatisch opgebouwd profiel per goedgekeurde concurrent
    op basis van scrape- en prijsdata.
    """
    __tablename__ = "competitor_profile"
    __table_args__ = (
        UniqueConstraint("shop_id", "competitor_name",
                         name="uq_competitor_profile_shop_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)
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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
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
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), index=True)  # eigenaar-shop
    candidates_found = Column(Integer, default=0)
    candidates_new = Column(Integer, default=0)
    candidates_approved = Column(Integer, default=0)
    candidates_rejected = Column(Integer, default=0)

    parameters = Column(JSON)     # discovery-parameters gebruikt
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class ConnectorConfig(Base):
    """
    Opgeslagen connector-instellingen per bron (priceshape, drs, ga4).
    Geheimen worden versleuteld opgeslagen; worden nooit als plaintext
    teruggegeven via de API. Env-variabelen blijven werken als terugval.
    """
    __tablename__ = "connector_config"

    id = Column(Integer, primary_key=True, index=True)
    connector_name = Column(String(50), unique=True, nullable=False, index=True)
    # Versleutelde velden (Fernet, nooit leesbaar terug via API)
    encrypted_credentials = Column(Text)
    # Welke velden zijn ingevuld (als lijst, veilig te tonen)
    fields_configured = Column(JSON)
    # Status na laatste test
    last_test_status = Column(String(50))   # ok / auth_error / unreachable / error
    last_test_message = Column(Text)
    last_tested_at = Column(DateTime)
    last_synced_at = Column(DateTime)
    # Laatste status waarover de gezondheidsmonitor een melding stuurde.
    # Wordt gebruikt om alleen bij een statuswijziging te alarmeren (geen spam).
    last_alerted_status = Column(String(50))
    last_alerted_at = Column(DateTime)
    # Wie heeft de connector ingesteld/gewijzigd
    configured_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BasketAssociation(Base):
    """
    Product-associatieregel uit de winkelmandanalyse (§16).
    antecedent → consequent met support/confidence/lift en relatie-type
    (cross_sell / upsell / bundle / basket_filler). Gebruikt door Pricing,
    Promotion en Decision Engine.
    """
    __tablename__ = "basket_associations"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    run_date = Column(Date, nullable=False, index=True)
    antecedent_sku = Column(String(100), nullable=False, index=True)
    consequent_sku = Column(String(100), nullable=False, index=True)
    antecedent_name = Column(String(500))
    consequent_name = Column(String(500))

    support = Column(Float, default=0.0)        # aandeel mandjes met beide
    confidence = Column(Float, default=0.0)     # P(consequent | antecedent)
    lift = Column(Float, default=0.0)           # confidence / P(consequent)
    co_purchase_count = Column(Integer, default=0)

    relation_type = Column(String(50))          # cross_sell / upsell / bundle / basket_filler
    bundle_margin_eur = Column(Numeric(12, 4))  # verwachte marge per gecombineerd mandje
    avg_basket_value = Column(Numeric(12, 4))
    explanation_nl = Column(Text)
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

class LoyaltyTier(Base):
    """Loyaliteitsniveaus (bijv. Brons/Zilver/Goud) met drempels en multipliers."""
    __tablename__ = "loyalty_tiers"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    code = Column(String(50), nullable=False, index=True)      # bronze / silver / gold
    name = Column(String(100), nullable=False)
    min_points_12m = Column(Integer, default=0)                 # drempel op 12m verdiende punten
    earn_multiplier = Column(Float, default=1.0)                # punten per euro multiplier
    benefits = Column(JSON)                                     # lijst met voordelen (tekst)
    rank = Column(Integer, default=0)                           # sorteervolgorde (hoger = beter)
    is_demo_data = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class CostUsageRecord(Base):
    """
    Werkelijk gemeten gebruik per module/shop/gebruiker/job (§37-§38).
    Elke rij is één gemeten gebruikseenheid: een API-request, AI-call,
    achtergrondjob, import of databaseoperatie — met duur, tokens en
    (geschatte) kosten. Basis voor het Cost & Scalability Dashboard.
    """
    __tablename__ = "cost_usage_records"

    id = Column(Integer, primary_key=True, index=True)
    occurred_at = Column(DateTime, default=datetime.utcnow, index=True)

    usage_type = Column(String(50), nullable=False, index=True)  # api_request / ai_call / job / import / db / compute
    module = Column(String(100), index=True)      # bv. pricing, competition, uploads, auth
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    username = Column(String(100), index=True)
    job_id = Column(String(100), index=True)      # model_run:<id> / import:<id> / sync:<naam>
    correlation_id = Column(String(64), index=True)

    endpoint = Column(String(255))
    method = Column(String(10))
    status_code = Column(Integer)
    duration_ms = Column(Float)

    # AI-metering
    ai_model = Column(String(100))
    tokens_in = Column(Integer)
    tokens_out = Column(Integer)

    quantity = Column(Float, default=1.0)         # aantal eenheden (rijen, requests, ...)
    cost_eur = Column(Numeric(12, 6))             # geschatte kosten in EUR
    extra = Column(JSON)

class CompetitorRanking(Base):
    """
    Concurrent-ranking per scope (masterprompt §9 en §11).
    Drie gestandaardiseerde scores per concurrent:
    - competition_relevance_score: hoe relevant is de concurrent als geheel
    - price_relevance_score: hoe relevant is zijn prijszetting voor ons
    - influence_score: hoeveel invloed heeft hij op onze conversie/prijs
    Met rank, vorige rank en trend zodat verschuivingen zichtbaar zijn.
    """
    __tablename__ = "competitor_rankings"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    run_date = Column(Date, nullable=False, index=True)
    scope = Column(String(200), nullable=False, default="overall", index=True)  # "overall" of categorienaam
    competitor_name = Column(String(255), nullable=False, index=True)

    competition_relevance_score = Column(Float, default=0.0)   # §9.1
    price_relevance_score = Column(Float, default=0.0)         # §9.2
    influence_score = Column(Float, default=0.0)               # §9.3
    combined_score = Column(Float, default=0.0)

    rank = Column(Integer)
    previous_rank = Column(Integer)
    rank_trend = Column(String(10), default="stable")          # up / down / stable / new

    confidence = Column(Float, default=0.0)
    explanation = Column(Text)                                  # geen score zonder uitleg (§64.9)
    evidence = Column(JSON)
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

class Decision(Base):
    """
    Een commerciële beslissing per entiteit (SKU/categorie), opgebouwd uit
    IntelligenceSignals van meerdere engines (§25). Bevat een aanbevolen
    scenario + alternatieven, en doorloopt de §28-approvalstatussen
    (draft → proposed → in_review → approved/rejected → executed / cancelled).
    Human approval is verplicht; de engine voert nooit autonoom uit.
    """
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)

    run_date = Column(Date, nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)   # sku / category
    entity_id = Column(String(255), nullable=False, index=True)
    entity_name = Column(String(500))

    title = Column(String(500))
    summary = Column(Text)                          # korte samenvatting van de beslissing
    recommended_scenario_id = Column(Integer)       # FK-loos verwijzend naar decision_scenarios.id (gezet na insert)

    # Signaalcontext (§53 reconstructie): welke signalen lagen ten grondslag
    signal_ids = Column(JSON)                       # [int] — intelligence_signals.id
    signal_snapshot = Column(JSON)                  # bevroren kopie van de gebruikte signalen
    data_gaps = Column(JSON)                        # ["data unavailable: ..."] (§56)

    # §28 approval-flow
    status = Column(String(30), default="draft", index=True)
    # draft / proposed / in_review / approved / rejected / executed / cancelled
    proposed_by = Column(String(100))               # AI-model dat voorstelt
    ai_model_version = Column(String(50))
    reviewer = Column(String(100))                  # menselijke reviewer
    reviewed_at = Column(DateTime)
    review_note = Column(Text)

    confidence = Column(Float, default=0.0)
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ModelRegistryEntry(Base):
    """
    Modelgovernance (§54): registratie van naam/versie/metrics/status per
    model met rollback. Per model is precies één versie 'active'.
    """
    __tablename__ = "model_registry"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False, index=True)   # basket / promotion / forecast_risk / opportunity / pricing
    version = Column(String(50), nullable=False)
    status = Column(String(30), default="active")    # active / superseded / rolled_back / archived
    metrics = Column(JSON)                           # laatste run-metrics
    config = Column(JSON)                            # immutabele modelconfiguratie (parameters) van deze versie
    description = Column(Text)
    activated_at = Column(DateTime)
    deactivated_at = Column(DateTime)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

class LoyaltyMember(Base):
    """Pseudoniem loyaliteitslid (§31: geen PII, alleen pseudonymous_customer_id)."""
    __tablename__ = "loyalty_members"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    pseudonymous_customer_id = Column(String(100), unique=True, nullable=False, index=True)
    joined_at = Column(Date)
    tier_code = Column(String(50), default="bronze", index=True)
    status = Column(String(20), default="active")   # active / inactive / blocked
    referral_code = Column(String(50), index=True)  # eigen code om anderen te werven
    referred_by = Column(String(100))               # pseudonymous_customer_id van werver
    consent_marketing = Column(Boolean, default=False)
    is_demo_data = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BusinessValueMeasurement(Base):
    """
    Gemeten of geschatte waarde-realisatie (§39-§40). value_label maakt de
    hardheid expliciet: REALIZED / MEASURED / ESTIMATED / SIMULATED.
    """
    __tablename__ = "business_value_measurements"

    id = Column(Integer, primary_key=True, index=True)
    metric_key = Column(String(100), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(50))
    value_label = Column(String(20), nullable=False, default="ESTIMATED")  # REALIZED / MEASURED / ESTIMATED / SIMULATED
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    period_start = Column(Date)
    period_end = Column(Date)
    explanation = Column(Text)                    # waarom deze waarde / hoe gemeten
    assumptions = Column(JSON)                    # gebruikte aannames bij ESTIMATED/SIMULATED
    source = Column(String(100))                  # handmatig / metering / model
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

class PlatformAssumption(Base):
    """
    Expliciete, zichtbare aannames (§64.11) voor kostenscenario's en
    businesscase. Bewerkbaar door admins; elke berekening toont welke
    aannames zijn gebruikt.
    """
    __tablename__ = "platform_assumptions"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    label = Column(String(255), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(50))                     # EUR/maand, uur/week, %, EUR
    category = Column(String(50), default="cost") # cost / value / scaling
    description = Column(Text)
    source = Column(String(255), default="aanname")  # aanname / gemeten / offerte
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BusinessValueBaseline(Base):
    """
    Nulmeting (§39): hoe lang duurde een taak / hoeveel analyses werden
    gedaan vóór het platform. Basis om besparing tegen af te zetten.
    """
    __tablename__ = "business_value_baselines"

    id = Column(Integer, primary_key=True, index=True)
    metric_key = Column(String(100), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    baseline_value = Column(Float, nullable=False)
    unit = Column(String(50))                     # uur/week, analyses/maand, EUR/maand
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    description = Column(Text)
    measured_at = Column(Date)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

class DecisionScenario(Base):
    """
    Eén scenario binnen een beslissing (§25): price increase/decrease/hold,
    promotion, loyalty incentive, bundle, house-brand action, no action.
    Elk scenario draagt verwachte impact + volledige WHY-structuur (§51).
    """
    __tablename__ = "decision_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("decisions.id"), nullable=False, index=True)

    scenario_type = Column(String(50), nullable=False)
    # price_increase / price_decrease / price_hold / promotion /
    # loyalty_incentive / bundle / house_brand_action / no_action
    label = Column(String(255))
    description = Column(Text)

    # Verwachte impact
    expected_units = Column(Float)
    expected_revenue = Column(Float)
    expected_margin = Column(Float)
    customer_impact = Column(String(500))
    basket_impact = Column(String(500))
    stock_impact = Column(String(500))
    strategic_impact = Column(String(500))
    risk_level = Column(String(20), default="medium")   # low / medium / high
    risk_notes = Column(Text)
    confidence = Column(Float, default=0.0)
    score = Column(Float, default=0.0)               # rangschikkingsscore van de generator

    is_recommended = Column(Boolean, default=False)

    # WHY-structuur (§51)
    why_factors = Column(JSON)        # [{factor, waarde, richting}]
    why_sources = Column(JSON)        # [{engine, signal_type, signal_id}] of tabellen
    why_assumptions = Column(JSON)    # ["aanname ..."]
    why_calculations = Column(JSON)   # [{stap, formule, resultaat}]

    parameters = Column(JSON)         # scenario-specifieke parameters (bv. new_price)
    created_at = Column(DateTime, default=datetime.utcnow)

class FactForecastDaily(Base):
    """
    Forecast & Risk (§20): unit/revenue/margin/stock forecasts per SKU met
    horizon, betrouwbaarheidsinterval, factoren en modelversie.
    """
    __tablename__ = "fact_forecast_daily"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    run_date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    sku_name = Column(String(500))
    category = Column(String(255))

    forecast_type = Column(String(20), nullable=False)   # units / revenue / margin / stock
    horizon_days = Column(Integer, nullable=False)       # 30 / 90
    forecast_value = Column(Float)                       # totaal over horizon (stock: eindstand)
    lower_bound = Column(Float)
    upper_bound = Column(Float)
    confidence = Column(Float, default=0.0)              # 0..1

    trend_pct = Column(Float)              # trend per 30 dagen
    seasonality_factor = Column(Float)     # gewogen seizoenscorrectie
    factors = Column(JSON)                 # {factor: bijdrage/uitleg}
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

class CustomerValueScore(Base):
    """
    Customer Intelligence per pseudoniem lid: CLV, churn, retentie, RFM en
    Next Best Action — altijd met confidence en uitleg (§64.9-10).
    """
    __tablename__ = "customer_value_scores"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    member_id = Column(Integer, ForeignKey("loyalty_members.id"), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)

    # RFM-bouwstenen
    recency_days = Column(Integer)
    frequency_12m = Column(Integer)
    monetary_12m = Column(Numeric(12, 4))
    avg_order_value = Column(Numeric(12, 4))

    # Afgeleide scores
    clv_estimate = Column(Numeric(12, 4))       # verwachte 24m-waarde
    churn_risk = Column(Float)                  # 0..1
    retention_probability = Column(Float)       # 0..1
    value_segment = Column(String(50))          # high_value / mid_value / low_value / at_risk / lost
    confidence = Column(Float, default=0.0)
    explanation = Column(Text)

    # Next Best Action
    next_best_action = Column(String(100))      # bv. loyalty_bonus / winback_voucher / tier_upgrade_nudge / no_action
    nba_reason = Column(Text)
    nba_expected_value = Column(Numeric(12, 4)) # verwachte incrementele waarde
    nba_alternative = Column(String(100))       # vergelijking: bv. generieke prijsverlaging
    nba_alternative_cost = Column(Numeric(12, 4))

    created_at = Column(DateTime, default=datetime.utcnow)

class LoyaltyFraudSignal(Base):
    """Fraude-indicatoren op ledger-niveau (§22)."""
    __tablename__ = "loyalty_fraud_signals"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    member_id = Column(Integer, ForeignKey("loyalty_members.id"), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)
    fraud_type = Column(String(50), nullable=False)  # abnormal_earn_rate / rapid_redemption / referral_ring / balance_mismatch
    severity = Column(String(20), default="medium")
    score = Column(Float, default=0.0)               # 0..1
    explanation = Column(Text, nullable=False)
    evidence = Column(JSON)
    status = Column(String(20), default="open")      # open / reviewed / dismissed
    created_at = Column(DateTime, default=datetime.utcnow)

class LoyaltyReward(Base):
    """Beloningen in de catalogus die met punten ingewisseld kunnen worden."""
    __tablename__ = "loyalty_rewards"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    name = Column(String(255), nullable=False)
    reward_type = Column(String(30), default="voucher")   # voucher / discount / gift
    points_cost = Column(Integer, nullable=False)
    monetary_value = Column(Numeric(10, 4))               # waarde in EUR (voor liability)
    active = Column(Boolean, default=True)
    is_demo_data = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class LoyaltyCampaignMembership(Base):
    """Toewijzing lid ↔ campagne, incl. treatment/control groep."""
    __tablename__ = "loyalty_campaign_memberships"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("loyalty_campaigns.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("loyalty_members.id"), nullable=False, index=True)
    group_type = Column(String(20), default="treatment")  # treatment / control
    assigned_at = Column(DateTime, default=datetime.utcnow)

class LoyaltyVoucher(Base):
    """Uitgegeven voucher (resultaat van een redemption)."""
    __tablename__ = "loyalty_vouchers"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    member_id = Column(Integer, ForeignKey("loyalty_members.id"), nullable=False, index=True)
    reward_id = Column(Integer, ForeignKey("loyalty_rewards.id"))
    code = Column(String(50), unique=True, nullable=False, index=True)
    monetary_value = Column(Numeric(10, 4))
    status = Column(String(20), default="issued")  # issued / used / expired / cancelled
    issued_at = Column(Date)
    expires_at = Column(Date)
    used_at = Column(Date)
    is_demo_data = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class LoyaltyTransaction(Base):
    """
    Ledger-entry (append-only). points_delta > 0 = earn/adjust-in,
    < 0 = redemption/expiry/adjust-out. Saldo mag nooit negatief worden.
    """
    __tablename__ = "loyalty_transactions"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    member_id = Column(Integer, ForeignKey("loyalty_members.id"), nullable=False, index=True)
    txn_date = Column(Date, nullable=False, index=True)
    txn_type = Column(String(30), nullable=False, index=True)  # earn / redeem / expire / adjust / referral_bonus / campaign_bonus
    points_delta = Column(Integer, nullable=False)
    order_reference = Column(String(100))          # pseudoniem orderkenmerk
    order_value = Column(Numeric(12, 4))           # bestedingsbedrag (voor earn-rate checks)
    campaign_id = Column(Integer, ForeignKey("loyalty_campaigns.id"))
    voucher_id = Column(Integer, ForeignKey("loyalty_vouchers.id"))
    description = Column(String(500))
    external_ref = Column(String(150), index=True) # idempotentie-sleutel bij import
    is_demo_data = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        # Database-afgedwongen idempotentie: dezelfde external_ref mag per lid
        # maar één keer voorkomen (partieel: alleen niet-NULL refs).
        Index(
            "uq_loyalty_txn_member_external_ref",
            "member_id", "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
    )

class LoyaltyCampaign(Base):
    """Loyaliteitscampagne met controlegroep (§22: meetbaar effect)."""
    __tablename__ = "loyalty_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    name = Column(String(255), nullable=False)
    campaign_type = Column(String(50), default="bonus_points")  # bonus_points / double_points / referral_drive
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(20), default="active")  # draft / active / completed
    bonus_multiplier = Column(Float, default=1.0)
    control_group_pct = Column(Float, default=10.0)  # % leden uitgesloten als controlegroep
    target_segment = Column(String(100))             # bv. churn_risk / high_value / all
    is_demo_data = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class CampaignUpliftSnapshot(Base):
    """
    Historische uplift-snapshot per campagne per engine-run (§22).
    Elke loyalty-run bewaart de kernmetrics zodat de trend over meerdere
    runs zichtbaar wordt (wordt de campagne beter of slechter?).
    Eén rij per RUN (run_at is de run-identiteit): ook meerdere runs op
    dezelfde dag blijven afzonderlijk bewaard en vergelijkbaar.
    """
    __tablename__ = "campaign_uplift_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    campaign_id = Column(Integer, ForeignKey("loyalty_campaigns.id"), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)
    run_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    spend_uplift_pct = Column(Float)          # besteding/lid uplift % (None als control 0)
    orders_uplift_pct = Column(Float)         # frequentie/lid uplift %
    retention_uplift_pct = Column(Float)      # retentie uplift %
    retention_confidence = Column(Float, default=0.0)
    combined_confidence = Column(Float, default=0.0)
    direction = Column(String(20))            # positive / negative / neutral
    treatment_n = Column(Integer, default=0)
    control_n = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
class LoyaltyWallet(Base):
    """
    Wallet per lid. balance_points is een gedenormaliseerd saldo dat ALLEEN
    via ledger-entries muteert (ledger-integriteit): saldo == som(ledger).
    """
    __tablename__ = "loyalty_wallets"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("loyalty_members.id"), unique=True, nullable=False, index=True)
    balance_points = Column(Integer, default=0, nullable=False)
    lifetime_earned = Column(Integer, default=0, nullable=False)
    lifetime_redeemed = Column(Integer, default=0, nullable=False)
    lifetime_expired = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class LoyaltyExpiryPolicy(Base):
    """
    Configureerbaar verloopbeleid voor loyaliteitspunten.
    Slechts één rij per shop (upsert-patroon).
    """
    __tablename__ = "loyalty_expiry_policies"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, unique=True, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    expiry_months = Column(Integer, default=12, nullable=False)   # punten verlopen N maanden na verdienen
    warn_days_before = Column(Integer, default=30, nullable=False) # hoeveel dagen van tevoren waarschuwen
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
class DecisionEvent(Base):
    """
    Statushistorie per beslissing (§53): elke overgang wordt vastgelegd met
    actor, oude/nieuwe status en waarden, zodat elke beslissing achteraf
    gereconstrueerd kan worden.
    """
    __tablename__ = "decision_events"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("decisions.id"), nullable=False, index=True)
    from_status = Column(String(30))
    to_status = Column(String(30), nullable=False)
    actor = Column(String(100), nullable=False)      # gebruikersnaam of AI-model
    actor_type = Column(String(20), default="human") # human / ai
    note = Column(Text)
    values_snapshot = Column(JSON)                   # relevante waarden op moment van overgang
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class Opportunity(Base):
    """
    Centrale Opportunity Engine (§24): genormaliseerde kansen uit alle engines
    met expected value, urgentie, effort, risico en ondersteunende engines.
    """
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    run_date = Column(Date, nullable=False, index=True)
    source_engine = Column(String(100), nullable=False, index=True)
    supporting_engines = Column(JSON)                # extra engines die dit onderbouwen
    opportunity_type = Column(String(100), nullable=False)  # price_increase / bundle / promo_repeat / risk_mitigation / ...

    entity_type = Column(String(50), default="sku")
    entity_id = Column(String(255), nullable=False, index=True)
    entity_name = Column(String(500))

    title_nl = Column(String(500))
    explanation_nl = Column(Text)

    expected_value_eur = Column(Numeric(12, 4))      # verwachte netto waarde
    expected_revenue_eur = Column(Numeric(12, 4))
    expected_margin_eur = Column(Numeric(12, 4))
    confidence = Column(Float, default=0.0)          # 0..1
    urgency = Column(String(20), default="medium")   # low / medium / high / critical
    effort = Column(String(20), default="medium")    # low / medium / high
    risk = Column(String(20), default="medium")      # low / medium / high
    priority_score = Column(Float, default=0.0, index=True)  # genormaliseerd 0..100

    status = Column(String(30), default="open")      # open / in_progress / done / dismissed
    evidence = Column(JSON)
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class FactPromotionEffect(Base):
    """
    Promotion Intelligence (§19): gemeten effect per promotie — uplift,
    incrementele omzet/marge, break-even, cannibalisatie en halo, met
    controlegroep waar mogelijk.
    """
    __tablename__ = "fact_promotion_effect"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id"), nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)

    period_start = Column(Date)
    period_end = Column(Date)
    baseline_start = Column(Date)
    baseline_end = Column(Date)

    # Baseline vs promo (per dag gemiddeld)
    baseline_units_per_day = Column(Float)
    promo_units_per_day = Column(Float)
    baseline_revenue_per_day = Column(Numeric(12, 4))
    promo_revenue_per_day = Column(Numeric(12, 4))
    baseline_margin_per_day = Column(Numeric(12, 4))
    promo_margin_per_day = Column(Numeric(12, 4))

    uplift_pct = Column(Float)                     # units uplift %
    incremental_revenue = Column(Numeric(12, 4))   # totaal over promo-periode
    incremental_margin = Column(Numeric(12, 4))
    break_even_extra_units = Column(Float)         # nodig om margeverlies te dekken
    break_even_achieved = Column(Boolean)

    cannibalization_pct = Column(Float)            # afzetdaling verwante SKU's
    halo_pct = Column(Float)                       # afzetstijging basket-gerelateerde SKU's

    control_group_used = Column(Boolean, default=False)
    control_group_size = Column(Integer, default=0)
    control_uplift_pct = Column(Float)             # uplift in controlegroep (markteffect)
    net_uplift_pct = Column(Float)                 # promo-uplift minus controlegroep

    verdict = Column(String(50))                   # EFFECTIEF / MARGINAAL / VERLIESGEVEND
    confidence = Column(Float, default=0.0)
    explanation_nl = Column(Text)
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── AI Gateway & Commercial AI Copilot (§26, §32) ───────────────────────────

class AiConversation(Base):
    """Copilot-gesprek van één gebruiker (gespreksgeschiedenis §26)."""
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(300), default="Nieuw gesprek")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AiMessage(Base):
    """Eén bericht in een Copilot-gesprek. Assistant-berichten bevatten het
    volledige gestructureerde antwoord (conclusion, sources, confidence, ...)
    in answer_json."""
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)      # user / assistant
    content = Column(Text, nullable=False)         # vraag of conclusion-tekst
    answer_json = Column(JSON)                     # gestructureerd antwoord (assistant)
    created_at = Column(DateTime, default=datetime.utcnow)


class AiModelCall(Base):
    """
    AI Gateway-logboek (§32): elke call naar het externe model wordt gelogd
    met gebruiker, model, aangeroepen functies, databronnen, doel en
    tokenverbruik. Basis voor audit en kostenbewaking.
    """
    __tablename__ = "ai_model_calls"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    username = Column(String(100), index=True)
    user_role = Column(String(50))
    conversation_id = Column(Integer, index=True)
    purpose = Column(String(255))                  # bv. copilot_question
    provider = Column(String(100), default="replit_ai_openai")
    model = Column(String(100))
    functions_called = Column(JSON)                # [{name, arguments, records, duration_ms}]
    datasources = Column(JSON)                     # gebruikte bronnen/tabellen
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    llm_roundtrips = Column(Integer, default=0)
    duration_ms = Column(Float)
    status = Column(String(30), default="success")  # success / failed / unavailable
    error_message = Column(Text)
    prompt_version_id = Column(Integer, index=True)  # gebruikte PromptVersion (§48)

class AiBudgetConfig(Base):
    """
    Dagelijkse AI-budgetlimieten (§34) per gebruiker of als globale standaard.

    - username=None  →  globale standaard (geldt voor alle gebruikers zonder eigen rij)
    - username=<naam> →  gebruikersspecifieke override
    - max_calls_per_day  = None  →  val per veld terug op de globale rij,
      anders op de omgevingsstandaard (DEFAULT_MAX_CALLS_PER_DAY)
    - max_tokens_per_day = None  →  idem (DEFAULT_MAX_TOKENS_PER_DAY);
      NULL betekent dus nooit 'onbeperkt'

    De globale singleton (username IS NULL) wordt afgedwongen via een partial
    unique index (zie migrate.py). SQLAlchemy's unique=True op een nullable
    kolom voorkomt dit niet in PostgreSQL.
    """
    __tablename__ = "ai_budget_config"

    id = Column(Integer, primary_key=True, index=True)
    # unique=True hier bewust NIET: de partial unique index in migrate.py
    # dwingt de singleton-beperking correct af in PostgreSQL.
    username = Column(String(100), nullable=True, index=True)
    # None = per veld terugvallen op globaal/env-standaard (nooit 'onbeperkt')
    max_calls_per_day = Column(Integer, nullable=True)
    max_tokens_per_day = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(100))

class AiProviderSetting(Base):
    """
    Persistente providerkeuze voor de AI Gateway (Task #79).

    Singleton-rij (id=1). active_provider bepaalt welke LLM-provider de
    gateway gebruikt:
      - "replit_ai_openai"  →  Replit AI-integratie (AI_INTEGRATIONS_OPENAI_*)
      - "openai_direct"     →  eigen OPENAI_API_KEY
      - None                →  automatisch: Replit AI zodra geconfigureerd,
                               anders de eigen OpenAI-sleutel.

    Een expliciete keuze valt nooit stil terug op de andere provider: is de
    gekozen provider niet geconfigureerd, dan is de AI-dienst 'niet
    beschikbaar' en toont het beheerderspaneel dat expliciet.
    """
    __tablename__ = "ai_provider_setting"

    id = Column(Integer, primary_key=True)
    active_provider = Column(String(50), nullable=True)  # None = automatisch
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(100))
class AiBudgetSlot(Base):
    """
    Atomisch reserveringsregister voor AI-budgetten (§34): één rij per
    (gebruiker, dag). Vóór elke LLM-call worden calls_reserved en
    tokens_reserved atomisch verhoogd met SELECT FOR UPDATE. Na de call
    wordt tokens_actual bijgewerkt met het werkelijke verbruik.

    De combinatie (username, slot_date) is uniek (zie UniqueConstraint).
    """
    __tablename__ = "ai_budget_slots"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, index=True)
    # Eigen index op slot_date: de periodieke opruiming verwijdert op
    # datum-alleen (slot_date < cutoff); de unieke (username, slot_date)-index
    # helpt daar niet bij zodra de tabel groot wordt.
    slot_date = Column(Date, nullable=False, index=True)
    calls_reserved = Column(Integer, default=0, nullable=False)
    tokens_reserved = Column(Integer, default=0, nullable=False)
    tokens_actual = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("username", "slot_date", name="uq_ai_budget_slots_user_date"),
    )

class AiFeedback(Base):
    """
    Feedback op één Copilot-antwoord (leerloop): duim omhoog/omlaag met
    optionele toelichting, gekoppeld aan vraag, antwoord, gebruikte tools en
    promptversie. Basis voor het kwaliteitsdashboard en few-shot-hergebruik.
    """
    __tablename__ = "ai_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_ai_feedback_msg_user"),
        # GIN-index op de opgeslagen tsvector: houdt few-shot retrieval snel
        # bij duizenden feedbackrijen (geen to_tsvector per rij meer).
        Index("ix_ai_feedback_question_tsv", "question_tsv", postgresql_using="gin",
              info={"pg_only": True}),
    )

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("ai_messages.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    username = Column(String(100))
    score = Column(Integer, nullable=False)        # +1 (duim omhoog) / -1 (duim omlaag)
    comment = Column(Text)                         # optionele toelichting
    question = Column(Text)                        # de vraag waarop dit antwoord kwam
    answer_excerpt = Column(Text)                  # conclusion-tekst van het antwoord
    tools_used = Column(JSON)                      # [functienamen] uit answer.sources
    prompt_version_id = Column(Integer, index=True)
    # Opgeslagen (STORED) generated column: Postgres onderhoudt de dutch-
    # tsvector zelf bij insert/update; de GIN-index hierboven maakt de
    # few-shot FTS-zoekopdracht een index-scan i.p.v. per-rij to_tsvector.
    # with_variant(Text, "sqlite"): unit-tests die een losse sqlite-DB
    # aanmaken (create_all) kunnen TSVECTOR/Computed niet compileren; de
    # CreateColumn-compiler-override hieronder laat op sqlite ook de
    # Computed-clausule (to_tsvector) weg.
    question_tsv = Column(
        TSVECTOR().with_variant(Text(), "sqlite"),
        Computed("to_tsvector('dutch', coalesce(question, ''))", persisted=True),
        info={"pg_only": True},  # niet aanmaken in SQLite-test-DB's
    )
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@compiles(CreateColumn, "sqlite")
def _sqlite_skip_tsv_computed(element, compiler, **kw):
    col = element.element
    if col.name == "question_tsv" and col.table is not None and col.table.name == "ai_feedback":
        return f"{compiler.preparer.format_column(col)} TEXT"
    return compiler.visit_create_column(element, **kw)
class PlatformModule(Base):
    """
    Module-registry (§46/§49): per platformmodule de verwachte functionaliteit,
    huidige implementatie, gap en prioriteit, plus production-readiness-scores
    op de tien §46-criteria. Het label 'Production Ready' vereist expliciete
    menselijke goedkeuring (production_approved_by).
    """
    __tablename__ = "platform_modules"

    id = Column(Integer, primary_key=True, index=True)
    module_key = Column(String(100), unique=True, nullable=False, index=True)
    name_nl = Column(String(255), nullable=False)
    description_nl = Column(Text)
    expected_feature = Column(Text)          # wat de spec verwacht
    current_implementation = Column(Text)    # wat er nu is
    gap = Column(Text)                       # wat ontbreekt
    priority = Column(String(20), default="medium")  # low / medium / high / critical
    # §46-criteria, elk 0-100
    readiness_scores = Column(JSON)          # {functionality, integration, data_quality, tests, security, performance, auditability, monitoring, documentation, human_control}
    readiness_label = Column(String(50), default="Concept")
    production_approved_by = Column(String(100))   # expliciete menselijke goedkeuring
    production_approved_at = Column(DateTime)
    uses_real_data = Column(Boolean, default=False)  # echte data vs. testdata (§59)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── PIM-integratie & Product Content Intelligence (§23) ────────────────────
# Vendor-neutrale contentlaag bovenop de DRS-productmaster (DimProduct).
# DRS blijft eigenaar van de commerciële kernvelden; deze laag voegt families,
# attributen, varianten/relaties, completeness-scores per channel, source
# ownership per veld en AI-contentsuggesties (altijd als voorstel) toe.


class PimFamily(Base):
    """Productfamilie: bepaalt welke attributen voor een product vereist zijn."""
    __tablename__ = "pim_family"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    # Categorieën (DimProduct.category) die automatisch aan deze familie
    # gekoppeld worden; expliciete koppeling via PimProductContent wint.
    category_patterns = Column(JSON)          # ["Papier", "Cartridges", ...]
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PimAttributeDefinition(Base):
    """
    Attribuutdefinitie met expliciete source ownership (§4): welk systeem is
    eigenaar van dit veld. Waarden van een andere bron dan de eigenaar leveren
    een conflict op in plaats van een stille overschrijving.
    """
    __tablename__ = "pim_attribute_definition"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    data_type = Column(String(30), default="text")   # text / number / boolean / select
    unit = Column(String(50))                        # bv. g/m², vel, mm
    allowed_values = Column(JSON)                    # voor select-type
    # Source ownership: DRS / Leverancier / Handmatig / AI
    source_owner = Column(String(50), default="Handmatig")
    # Optioneel gekoppeld aan een familie; NULL = geldt voor alle producten
    family_id = Column(Integer, ForeignKey("pim_family.id"), index=True)
    is_required = Column(Boolean, default=False)     # vereist voor basiscompleteness
    weight = Column(Float, default=1.0)              # gewicht in completeness-score
    # Kolom op DimProduct waaruit dit attribuut automatisch gevuld wordt
    dim_product_field = Column(String(100))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PimAttributeValue(Base):
    """Attribuutwaarde per SKU met herkomst (source) en review-metadata."""
    __tablename__ = "pim_attribute_value"
    __table_args__ = (
        Index("ix_pim_attr_value_sku_attr", "sku_id", "attribute_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), ForeignKey("dim_product.sku_id"), nullable=False, index=True)
    attribute_id = Column(Integer, ForeignKey("pim_attribute_definition.id"), nullable=False, index=True)
    value = Column(Text)
    # Herkomst van deze waarde: DRS / Leverancier / Handmatig / AI
    source = Column(String(50), default="Handmatig")
    confidence = Column(Float)                       # gevuld bij AI-herkomst
    updated_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PimProductContent(Base):
    """Contentstatus per SKU: familie-koppeling en variant-informatie."""
    __tablename__ = "pim_product_content"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), ForeignKey("dim_product.sku_id"), unique=True, nullable=False, index=True)
    family_id = Column(Integer, ForeignKey("pim_family.id"), index=True)
    # Variant: verwijst naar de parent-SKU waarvan dit een variant is
    parent_sku_id = Column(String(100), index=True)
    variant_axis = Column(String(100))               # bv. kleur / formaat / pakgrootte
    variant_value = Column(String(255))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PimProductRelation(Base):
    """Productrelaties: variant_van / accessoire / vervangt / alternatief."""
    __tablename__ = "pim_product_relation"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    related_sku_id = Column(String(100), nullable=False, index=True)
    relation_type = Column(String(50), nullable=False)  # variant_van / accessoire / vervangt / alternatief
    note = Column(Text)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class PimChannel(Base):
    """Channel-definitie voor channel readiness (bv. webshop, marketplace)."""
    __tablename__ = "pim_channel"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    # Attribuutcodes die voor dit channel verplicht zijn
    required_attribute_codes = Column(JSON)          # ["brand", "ean", ...]
    min_completeness_pct = Column(Float, default=80.0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PimCompletenessScore(Base):
    """Completeness/quality-score per SKU per channel (channel NULL = totaal)."""
    __tablename__ = "pim_completeness_score"
    __table_args__ = (
        Index("ix_pim_completeness_sku_channel", "sku_id", "channel_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    channel_code = Column(String(100))               # NULL = overall
    completeness_pct = Column(Float, default=0.0)    # 0..100, gewogen gevulde attributen
    quality_score = Column(Float, default=0.0)       # 0..100, geldigheid/consistentie
    channel_ready = Column(Boolean, default=False)
    missing_attributes = Column(JSON)                # [attribute_code, ...]
    quality_issues = Column(JSON)                    # [{code, bericht}]
    run_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PimAiSuggestion(Base):
    """
    AI-suggestie voor een ontbrekend attribuut of contentveld.
    Altijd een voorstel met review-status; wordt nooit automatisch toegepast.
    """
    __tablename__ = "pim_ai_suggestion"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    attribute_id = Column(Integer, ForeignKey("pim_attribute_definition.id"), index=True)
    attribute_code = Column(String(100), nullable=False)
    suggested_value = Column(Text, nullable=False)
    current_value = Column(Text)                     # waarde op moment van suggestie
    rationale = Column(Text)                         # uitleg van het model (NL)
    confidence = Column(Float, default=0.0)
    model_version = Column(String(100))
    status = Column(String(20), default="PENDING", index=True)  # PENDING / APPROVED / REJECTED
    reviewed_by = Column(String(100))
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class BacklogItem(Base):
    """Development Backlog per module (§48)."""
    __tablename__ = "backlog_items"

    id = Column(Integer, primary_key=True, index=True)
    module_key = Column(String(100), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    item_type = Column(String(50), default="missing_functionality")  # missing_functionality / bug / improvement / test / documentation
    status = Column(String(30), default="open")     # open / in_progress / done / wont_do
    priority = Column(String(20), default="medium") # low / medium / high / critical
    owner = Column(String(100))
    dependencies = Column(Text)                     # afhankelijkheden (vrije tekst / module keys)
    data_sources = Column(Text)
    tests = Column(Text)
    business_value = Column(Text)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DocPage(Base):
    """Centrale documentatieomgeving (§58): één pagina per onderwerp,
    bewerkbaar zodat de documentatie met de applicatie meegroeit."""
    __tablename__ = "doc_pages"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    title_nl = Column(String(255), nullable=False)
    chapter = Column(String(100), nullable=False)   # §58-hoofdstuk (Architecture, Data Model, ...)
    content_md = Column(Text, default="")
    module_key = Column(String(100), index=True)    # optionele koppeling aan module
    sort_order = Column(Integer, default=0)
    updated_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class FinalEvaluationReport(Base):
    """Final Technical & Business Evaluation (§59): gegenereerd rapport dat de
    twintig evaluatievragen beantwoordt, met onderscheid echte data vs. testdata."""
    __tablename__ = "final_evaluation_reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), default="Final Technical & Business Evaluation")
    generated_by = Column(String(100))
    sections_json = Column(JSON)                    # [{nr, vraag, antwoord, data_label, details}]
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)

class PromptVersion(Base):
    """Prompt Library met versiebehoud per module (§48)."""
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, index=True)
    module_key = Column(String(100), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    version = Column(Integer, default=1)
    prompt_text = Column(Text, nullable=False)
    notes = Column(Text)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Competition Intelligence: events, beschikbaarheid, dekking ──────────────

class CompetitorPriceEvent(Base):
    """
    Gedetecteerde concurrent-prijsgebeurtenis (prijswijziging of promotie).
    event_type: PRICE_CHANGE / PROMO_START / PROMO_END.
    Wordt idempotent per (shop, datum, sku, concurrent, type) vastgelegd.
    """
    __tablename__ = "competitor_price_event"
    __table_args__ = (
        UniqueConstraint("shop_id", "event_date", "sku_id", "competitor_name",
                         "event_type", name="uq_comp_price_event"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    event_date = Column(Date, nullable=False, index=True)
    sku_id = Column(String(100), nullable=False, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)
    event_type = Column(String(30), nullable=False)   # PRICE_CHANGE / PROMO_START / PROMO_END
    old_price = Column(Numeric(10, 4))
    new_price = Column(Numeric(10, 4))
    change_pct = Column(Float)                        # (new-old)/old * 100
    direction = Column(String(10))                    # up / down
    promo_depth_pct = Column(Float)                   # bij PROMO_*: dipdiepte vs referentie
    promo_duration_days = Column(Integer)             # bij PROMO_END: duur van de dip
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorAvailabilityDaily(Base):
    """
    Dagelijkse beschikbaarheids-aggregatie per concurrent uit
    fact_competitor_offer_daily (voorraadstatus + levertijd).
    """
    __tablename__ = "competitor_availability_daily"
    __table_args__ = (
        UniqueConstraint("shop_id", "date", "competitor_name",
                         name="uq_comp_availability_daily"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    date = Column(Date, nullable=False, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)
    offers_total = Column(Integer, default=0)
    offers_in_stock = Column(Integer, default=0)
    in_stock_rate = Column(Float)                     # 0–1
    avg_delivery_days = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorCoverageResult(Base):
    """
    Assortimentsdekking per concurrent (per categorie en totaal, category=None)
    op basis van niet-afgekeurde AI-matches vs. ons eigen assortiment.
    """
    __tablename__ = "competitor_coverage_result"
    __table_args__ = (
        UniqueConstraint("shop_id", "run_date", "competitor_name", "category",
                         name="uq_comp_coverage_result"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    run_date = Column(Date, nullable=False, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)
    category = Column(String(255), index=True)        # None = totaal assortiment
    own_products = Column(Integer, default=0)         # eigen SKU's in scope
    matched_products = Column(Integer, default=0)     # gematchte (niet-REJECTED) SKU's
    coverage_pct = Column(Float)                      # matched/own * 100
    created_at = Column(DateTime, default=datetime.utcnow)

class AiUserMemory(Base):
    """
    Duurzaam Copilot-geheugen (leerloop): voorkeuren en vaste context per
    gebruiker (user_id gezet) of organisatie-breed (user_id NULL), geëxtraheerd
    uit gesprekken en geïnjecteerd in nieuwe gesprekken.
    """
    __tablename__ = "ai_user_memory"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_ai_memory_user_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # NULL = organisatie
    key = Column(String(200), nullable=False)      # bv. favoriete_categorie
    value = Column(Text, nullable=False)           # bv. "Dranken"
    source_conversation_id = Column(Integer, index=True)
    # Herkomst van de huidige waarde: "extracted" (automatisch) of "manual"
    # (door de gebruiker gecorrigeerd). Handmatige waarden mogen NIET door
    # automatische extractie worden overschreven (Task #135).
    source = Column(String(20), nullable=False, default="extracted")
    # Levenscyclus: "active" of "deleted" (tombstone). Verwijderde items
    # blijven bestaan als tombstone zodat extractie dezelfde key niet
    # stilletjes opnieuw aanmaakt (Task #135).
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AiConversationSummary(Base):
    """Samenvatting van lange Copilot-gesprekken: oudere berichten worden
    samengevat i.p.v. afgekapt (leerloop)."""
    __tablename__ = "ai_conversation_summaries"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"),
                             nullable=False, unique=True, index=True)
    summary = Column(Text, nullable=False)
    upto_message_id = Column(Integer)              # laatste bericht in de samenvatting
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@compiles(CreateColumn, "sqlite")
def _sqlite_skip_computed_columns(element, compiler, **kw):
    """SQLite (unit-tests met create_all) kan Postgres-specifieke generated
    columns zoals to_tsvector niet renderen; maak er daar een gewone,
    ongegenereerde kolom van. Op Postgres blijft de STORED kolom intact."""
    column = element.element
    if column.computed is not None:
        return "%s %s" % (
            compiler.preparer.format_column(column),
            compiler.dialect.type_compiler.process(column.type),
        )
    return compiler.visit_create_column(element, **kw)

@compiles(TSVECTOR, "sqlite")
def _tsvector_as_text_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(CreateColumn, "sqlite")
def _skip_postgres_only_columns(element, compiler, **kw):
    """Sla Postgres-specifieke kolommen (bijv. TSVECTOR generated columns)
    over in SQLite-DDL, zodat testdatabases op SQLite blijven werken."""
    if element.element.info.get("postgres_only"):
        return None
    return compiler.visit_create_column(element, **kw)

@compiles(CreateColumn, "sqlite")
def _skip_computed_on_sqlite(element, compiler, **kw):
    column = element.element
    if column.computed is not None:
        return "%s %s" % (
            compiler.preparer.format_column(column),
            compiler.dialect.type_compiler.process(column.type),
        )
    return compiler.visit_create_column(element, **kw)

class UserScope(Base):
    """
    Data-scope per gebruiker: beperkt tot shop / land / juridische entiteit.
    Geen rijen = onbeperkt (alle shops). Handhaving in winkelkeuze en
    shop-gescopeerde queries (zie helper authz.user_allowed_shop_ids).
    """
    __tablename__ = "user_scopes"
    __table_args__ = (UniqueConstraint("user_id", "scope_type", "scope_value", name="uq_user_scope"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = Column(String(20), nullable=False)   # shop / country / legal_entity
    scope_value = Column(String(255), nullable=False) # shop_id / landcode / entiteitsnaam
    created_at = Column(DateTime, default=datetime.utcnow)

class UserDepartment(Base):
    """Koppeling gebruiker ↔ afdeling(en)."""
    __tablename__ = "user_departments"
    __table_args__ = (UniqueConstraint("user_id", "department_id", name="uq_user_department"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class RolePermission(Base):
    """Rollen & Rechten-matrix: welke permissies een rol standaard heeft.
    Bewerkbaar via de beheer-UI (niet hardcoded); wijzigingen worden geaudit."""
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role", "permission_code", name="uq_role_permission"),)

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(50), nullable=False, index=True)
    permission_code = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserPermission(Base):
    """Extra (cross-department) permissies per gebruiker, bovenop rol + afdeling."""
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "permission_code", name="uq_user_permission"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_code = Column(String(100), nullable=False, index=True)
    granted_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class SavedView(Base):
    """
    Opgeslagen view (taak #221): filter-, sorteer-, kolom- en dashboard-
    configuratie per pagina, deelbaar als private / team / department.
    Een department-view kan als afdelings-default worden gemarkeerd.
    """
    __tablename__ = "saved_views"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    page_key = Column(String(200), nullable=False, index=True)  # route-pad, bv. "/recommendations" of "*" (alle pagina's)
    scope = Column(String(20), nullable=False, default="private", index=True)  # private / team / department
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"),
                           nullable=True, index=True)
    is_department_default = Column(Boolean, default=False, nullable=False)
    config = Column(JSON, nullable=False, default=dict)  # {filters, sort, columns, dashboard}
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserUiPreference(Base):
    """
    Persoonlijke UI-voorkeuren per gebruiker (taak #221): favorieten,
    recent gebruikte pagina's/filters e.d. — vrije JSON per sleutel.
    """
    __tablename__ = "user_ui_preferences"
    __table_args__ = (UniqueConstraint("user_id", "pref_key", name="uq_user_ui_pref"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pref_key = Column(String(50), nullable=False)
    value = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════════════════
# Concurrentprofiel: datamodel & evidence-fundament (taak #246)
# Alle tabellen koppelen aan de bestaande concurrent-identiteit per shop:
# (shop_id, competitor_name) — géén tweede concurrententabel.
# ═══════════════════════════════════════════════════════════════════════════

class CompetitionEvidence(Base):
    """
    Evidence-record waarnaar alle profielvelden kunnen verwijzen.
    Bronprioriteit voor financiële data ligt vast in
    services/competitor_profile.py (jaarrekening > kvk > jaarverslag > ...).
    """
    __tablename__ = "competition_evidence"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    source_url = Column(Text)
    source_type = Column(String(50), nullable=False)  # jaarrekening / kvk / jaarverslag / persbericht / nieuwsartikel / bedrijfswebsite / linkedin / social_media / externe_schatting / handmatig / demo_seed
    source_priority = Column(Integer)                 # lager = betrouwbaarder (afgeleid van source_type)
    title = Column(String(500))
    observed_date = Column(Date)                      # peildatum van het feit
    fetched_date = Column(Date)                       # wanneer opgehaald/ingevoerd
    reliability = Column(String(20), default="medium")  # high / medium / low
    status = Column(String(20), default="active")     # active / superseded / rejected / expired
    confidence = Column(Float, default=0.5)           # 0..1
    extracted_fact = Column(Text)                     # het geëxtraheerde feit (NL)
    human_validated = Column(Boolean, default=False)
    review_due_date = Column(Date)                    # wanneer opnieuw beoordelen
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorBusinessProfile(Base):
    """
    Bedrijfsprofiel per concurrent: identiteit, omvang, klantmodel,
    geografische schaal en ownership. Eén rij per (shop, concurrent).
    field_meta bevat per veld: {information_layer, confidence, evidence_id,
    source, as_of_date, last_verified_at, status} waarbij status expliciet
    "unknown" kan zijn — unknown is nooit stilzwijgend 0/leeg.
    """
    __tablename__ = "competitor_business_profile"
    __table_args__ = (
        UniqueConstraint("shop_id", "competitor_name",
                         name="uq_comp_business_profile_shop_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    legal_name = Column(String(255))
    kvk_number = Column(String(50))
    founded_year = Column(Integer)
    customer_model = Column(String(50))         # b2c / b2b / hybrid
    size_class = Column(String(50))             # micro / klein / middelgroot / groot / enterprise
    employee_range_min = Column(Integer)
    employee_range_max = Column(Integer)
    revenue_range_min = Column(Numeric(16, 2))
    revenue_range_max = Column(Numeric(16, 2))
    revenue_currency = Column(String(3))        # ISO 4217
    geographic_scale = Column(String(50))       # lokaal / nationaal / eu / globaal
    ownership_type = Column(String(50))         # familiebedrijf / private_equity / beursgenoteerd / ...
    headquarters_country = Column(String(2))    # ISO 3166-1 alpha-2 (nooit basis voor inferenties)

    field_meta = Column(JSON, default=dict)     # per-veld: laag/bron/peildatum/confidence/status
    last_verified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CompetitorFulfilmentProfile(Base):
    """Fulfilment-/voorraadmodel per concurrent. Eén rij per (shop, concurrent)."""
    __tablename__ = "competitor_fulfilment_profile"
    __table_args__ = (
        UniqueConstraint("shop_id", "competitor_name",
                         name="uq_comp_fulfilment_profile_shop_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    inventory_model = Column(String(50))        # eigen_voorraad / dropship / hybride
    warehouse_count = Column(Integer)
    warehouse_locations = Column(JSON)          # [{country, city}] — nooit basis voor inferenties
    dropship_share_pct = Column(Float)          # 0..100
    own_stock_share_pct = Column(Float)         # 0..100
    next_day_delivery = Column(Boolean)
    same_day_delivery = Column(Boolean)
    marketplace_role = Column(String(50))       # geen / verkoper / platform / beide

    field_meta = Column(JSON, default=dict)
    last_verified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CompetitorFinancialObservation(Base):
    """Financiële observatie per concurrent per boekjaar per metric."""
    __tablename__ = "competitor_financial_observation"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    fiscal_year = Column(Integer, nullable=False, index=True)
    metric = Column(String(50), nullable=False)   # revenue / profit / employees / equity / ...
    value_min = Column(Numeric(16, 2))
    value_max = Column(Numeric(16, 2))
    currency = Column(String(3))
    is_unknown = Column(Boolean, default=False)   # expliciete unknown-markering

    information_layer = Column(String(30), nullable=False, default="schatting")  # feit / schatting / afgeleid_signaal / hypothese
    confidence = Column(Float, default=0.5)
    evidence_id = Column(Integer, ForeignKey("competition_evidence.id"), index=True)
    source_note = Column(String(255))
    as_of_date = Column(Date)
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorMarketRole(Base):
    """Marktrollen (Competition DNA) — meerdere tegelijk mogelijk per concurrent."""
    __tablename__ = "competitor_market_role"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    role = Column(String(50), nullable=False)     # prijsvechter / assortimentsleider / nichespeler / platform / premium_specialist / ...
    information_layer = Column(String(30), nullable=False, default="afgeleid_signaal")
    confidence = Column(Float, default=0.5)
    evidence_id = Column(Integer, ForeignKey("competition_evidence.id"), index=True)
    ai_assigned = Column(Boolean, default=False)
    human_validated = Column(Boolean, default=False)
    valid_from = Column(Date)
    valid_to = Column(Date)                       # NULL = nog geldig
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorGeographicPresence(Base):
    """Geografische aanwezigheid per land, met expliciet presence-type."""
    __tablename__ = "competitor_geographic_presence"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    country_code = Column(String(2), nullable=False)   # ISO 3166-1 alpha-2
    presence_type = Column(String(30), nullable=False)  # webshop / operationeel
    information_layer = Column(String(30), nullable=False, default="feit")
    confidence = Column(Float, default=0.5)
    evidence_id = Column(Integer, ForeignKey("competition_evidence.id"), index=True)
    valid_from = Column(Date)
    valid_to = Column(Date)                       # NULL = nog actief
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorCorporateRelation(Base):
    """Corporate structuur: parent / ultimate_parent / subsidiary / sister."""
    __tablename__ = "competitor_corporate_relation"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    relation_type = Column(String(30), nullable=False)  # parent / ultimate_parent / subsidiary / sister
    related_entity = Column(String(255), nullable=False)
    related_country = Column(String(2))           # informatief; nooit basis voor claims
    information_layer = Column(String(30), nullable=False, default="feit")
    confidence = Column(Float, default=0.5)
    evidence_id = Column(Integer, ForeignKey("competition_evidence.id"), index=True)
    valid_from = Column(Date)
    valid_to = Column(Date)                       # NULL = nog geldig
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorEvolutionEvent(Base):
    """
    Historie: elke betekenisvolle profielwijziging als tijdlijn-event
    (Competitor Evolution Timeline-data).
    """
    __tablename__ = "competitor_evolution_event"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    section = Column(String(50), nullable=False)   # business / fulfilment / financials / roles / geography / relations
    field_name = Column(String(100))
    event_type = Column(String(50), nullable=False, default="changed")  # created / changed / removed / validated
    old_value = Column(JSON)
    new_value = Column(JSON)
    change_source = Column(String(30), default="handmatig")  # ai / handmatig / seed / import
    changed_by = Column(String(100))
    evidence_id = Column(Integer, ForeignKey("competition_evidence.id"))
    occurred_at = Column(DateTime, default=datetime.utcnow, index=True)


class CompetitorFieldValidation(Base):
    """
    Handmatige validatie-workflow: AI-waarde én menselijke waarde blijven
    beide bewaard; de menselijke correctie wint operationeel.
    """
    __tablename__ = "competitor_field_validation"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)

    section = Column(String(50), nullable=False)
    field_name = Column(String(100), nullable=False)
    action = Column(String(30), nullable=False)   # bevestigen / corrigeren / blokkeren / unknown / heronderzoek
    ai_value = Column(JSON)                       # bewaarde AI-waarde
    human_value = Column(JSON)                    # menselijke waarde (bij corrigeren)
    reason = Column(Text)
    reviewer = Column(String(100), nullable=False)
    is_current = Column(Boolean, default=True, index=True)  # laatste beoordeling per veld
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitorFreshnessRule(Base):
    """
    Configureerbare freshness-regels per veldtype: wanneer geldt een
    profielveld als 'verouderd'. shop_id NULL = globale default-override.
    """
    __tablename__ = "competitor_freshness_rule"
    __table_args__ = (
        UniqueConstraint("shop_id", "field_type",
                         name="uq_comp_freshness_shop_fieldtype"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), nullable=True, index=True)
    field_type = Column(String(50), nullable=False)   # price / employees / revenue / countries / fulfilment / ownership / roles / default
    max_age_days = Column(Integer, nullable=False)
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CompetitorScoreResult(Base):
    """
    Concurrentscore-resultaat per (shop, concurrent, run-datum) — taak #247.

    Classificaties (company size, geographic scale, fulfilment model) en
    scores (operational strength, financial health, business strength,
    procurement power, future threat), elk 0–100 of NULL (= Unknown; nooit
    automatisch 0 bij ontbrekende data). `details` bevat per classificatie/
    score de factoren, gewichten, bronnen en confidence (volledige
    uitlegbaarheid) plus de gedocumenteerde feature-dependencies.
    """
    __tablename__ = "competitor_score_result"
    __table_args__ = (
        UniqueConstraint("shop_id", "competitor_name", "run_date",
                         name="uq_comp_score_shop_name_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), default=1, index=True)
    competitor_name = Column(String(255), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)

    # Classificaties
    company_size_class = Column(String(30))       # micro / klein / middelgroot / groot / enterprise / NULL=unknown
    company_size_confidence = Column(Float)
    geographic_scale_class = Column(String(30))   # lokaal / nationaal / regionaal / internationaal / globaal / NULL=unknown
    geographic_scale_confidence = Column(Float)
    fulfilment_model_class = Column(String(40))   # eigen_voorraad / dropship / hybride / marketplace / NULL=unknown
    fulfilment_model_confidence = Column(Float)

    # Scores 0–100; NULL = Unknown (ontbrekende data is nooit score 0)
    operational_strength_score = Column(Float)
    financial_health_score = Column(Float)
    financial_health_status = Column(String(30))  # gezond / aandacht / zwak / unknown
    financial_data_confidence = Column(Float)     # aparte confidence voor financiële data
    business_strength_score = Column(Float)
    procurement_power_score = Column(Float)
    future_threat_score = Column(Float)

    data_completeness_pct = Column(Float)         # 0–100: hoeveel input-secties beschikbaar
    details = Column(JSON)                        # per score: factoren/gewichten/bronnen/confidence
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
