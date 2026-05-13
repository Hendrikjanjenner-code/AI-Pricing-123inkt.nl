"""
Traffic Engine — hoofdorchestrator voor traffic intelligence.

Berekent per SKU / categorie:
  DSS — Demand Signal Score      (totale vraag)
  CHS — Conversion Health Score  (conversiegezondheid)
  TOS — Traffic Opportunity Score (traffic kansen)
  CRS — Conversion Risk Score    (conversierisico)
  SGS — Search Gap Score         (zoekgap)

Schrijft resultaten naar fact_traffic_intelligence_daily.
"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
import models


# ─── Basisberekeningen ────────────────────────────────────────────────────────

def calculate_conversion_rate(sessions: int, orders: int) -> float:
    """Conversieratio = orders / sessions."""
    return round(orders / sessions, 4) if sessions > 0 else 0.0


def calculate_add_to_cart_rate(sessions: int, add_to_cart: int) -> float:
    """Add-to-cart rate = add_to_cart / sessions."""
    return round(add_to_cart / sessions, 4) if sessions > 0 else 0.0


def calculate_revenue_per_visitor(revenue: float, sessions: int) -> float:
    """Omzet per bezoeker."""
    return round(revenue / sessions, 4) if sessions > 0 else 0.0


def calculate_margin_per_visitor(margin: float, sessions: int) -> float:
    """Marge per bezoeker."""
    return round(margin / sessions, 4) if sessions > 0 else 0.0


def calculate_traffic_growth(recent_sessions: int, prev_sessions: int) -> float:
    """Procentuele groei in sessies (recent vs vorige periode)."""
    if prev_sessions <= 0:
        return 0.10
    return round((recent_sessions - prev_sessions) / prev_sessions, 4)


def calculate_conversion_trend(recent_cr: float, prev_cr: float) -> float:
    """Procentuele verandering in conversieratio."""
    if prev_cr <= 0:
        return 0.0
    return round((recent_cr - prev_cr) / prev_cr, 4)


# ─── Scorefuncties ────────────────────────────────────────────────────────────

def calculate_demand_signal_score(
    pageviews: int,
    sessions: int,
    internal_search_count: int,
    search_volume: int,
    trend_index: float,
) -> float:
    """
    DSS — meet totale vraag (intern + extern).

    Factoren:
    - extern zoekvolume (30%)
    - zoektrend (20%)
    - interne site-search (20%)
    - pageviews als proxy voor interesse (15%)
    - sessies (15%)
    """
    vol_score    = min(1.0, search_volume / 10_000)
    trend_score  = min(1.0, max(0.0, trend_index))
    isearch_score = min(1.0, internal_search_count / 500)
    pv_score     = min(1.0, pageviews / 3_000)
    sess_score   = min(1.0, sessions / 2_000)

    dss = (
        vol_score    * 0.30
        + trend_score  * 0.20
        + isearch_score * 0.20
        + pv_score     * 0.15
        + sess_score   * 0.15
    )
    return round(min(1.0, max(0.0, dss)), 4)


def calculate_conversion_health_score(
    conversion_rate: float,
    add_to_cart_rate: float,
    revenue_per_visitor: float,
    margin_per_visitor: float,
    bounce_rate: float,
    in_stock: bool,
    price_index: float,
) -> float:
    """
    CHS — meet hoe gezond de conversie is.

    Factoren:
    - conversieratio (30%)
    - add-to-cart rate (20%)
    - marge per bezoeker (20%)
    - bounce rate omgekeerd (15%)
    - voorraadstatus (10%)
    - prijspositie (5%)
    """
    cr_score    = min(1.0, conversion_rate / 0.06)       # 6% = perfect
    atc_score   = min(1.0, add_to_cart_rate / 0.15)      # 15% atc = perfect
    mpv_score   = min(1.0, margin_per_visitor / 3.0)     # €3/bezoeker = perfect
    bounce_score = max(0.0, 1.0 - bounce_rate)           # laag bounce = goed
    stock_score  = 1.0 if in_stock else 0.0
    price_score  = min(1.0, max(0.0, 1.5 - price_index)) # prijs_index < 1 = concurrerend

    chs = (
        cr_score    * 0.30
        + atc_score   * 0.20
        + mpv_score   * 0.20
        + bounce_score * 0.15
        + stock_score  * 0.10
        + price_score  * 0.05
    )
    return round(min(1.0, max(0.0, chs)), 4)


def calculate_traffic_opportunity_score(
    demand_signal_score: float,
    sessions: int,
    margin_per_visitor: float,
    in_stock: bool,
    search_gap_score: float,
) -> float:
    """
    TOS — hoge DSS + lage eigen traffic + hoge marge + goede voorraad = kans.

    Hoge score = er is veel externe vraag maar weinig eigen traffic.
    """
    low_traffic_score = max(0.0, 1.0 - min(1.0, sessions / 1_500))
    mpv_score = min(1.0, margin_per_visitor / 2.0)
    stock_score = 1.0 if in_stock else 0.2

    tos = (
        demand_signal_score * 0.35
        + low_traffic_score  * 0.30
        + search_gap_score   * 0.20
        + mpv_score          * 0.10
        + stock_score        * 0.05
    )
    return round(min(1.0, max(0.0, tos)), 4)


def calculate_conversion_risk_score(
    traffic_growth: float,
    conversion_trend: float,
    price_index: float,
    pcis_score: float,
) -> float:
    """
    CRS — traffic stabiel of stijgend + conversie dalend + prijsdruk = risico.

    Hoge score = serieus conversierisico.
    """
    traffic_stable_score = min(1.0, max(0.0, 0.5 + traffic_growth))
    conversion_drop_score = min(1.0, max(0.0, -conversion_trend))
    price_pressure_score = min(1.0, max(0.0, price_index - 0.90) * 5.0)
    pcis_pressure_score = min(1.0, pcis_score)

    crs = (
        traffic_stable_score    * 0.25
        + conversion_drop_score   * 0.40
        + price_pressure_score    * 0.20
        + pcis_pressure_score     * 0.15
    )
    return round(min(1.0, max(0.0, crs)), 4)


def calculate_search_gap_score(
    search_volume: int,
    own_pageviews: int,
    own_impressions: int,
) -> float:
    """
    SGS — hoog zoekvolume + lage eigen zichtbaarheid = gemiste kans.
    """
    demand_component = min(1.0, search_volume / 10_000)
    own_visibility = min(1.0, (own_pageviews + own_impressions) / max(search_volume * 0.05, 1))
    gap = demand_component * (1.0 - min(1.0, own_visibility * 2))
    return round(min(1.0, max(0.0, gap)), 4)


# ─── Signaaldetectie ──────────────────────────────────────────────────────────

def detect_conversion_drop(conversion_trend: float, threshold: float = -0.15) -> bool:
    return conversion_trend < threshold


def detect_traffic_drop(traffic_growth: float, threshold: float = -0.20) -> bool:
    return traffic_growth < threshold


def detect_search_demand_opportunity(dss: float, sessions: int) -> bool:
    return dss >= 0.60 and sessions < 800


def generate_traffic_explanation_nl(
    reason_code: str,
    conversion_trend: float = 0.0,
    traffic_growth: float = 0.0,
    dss: float = 0.0,
    crs: float = 0.0,
    sgs: float = 0.0,
) -> str:
    """Genereert Nederlandse uitleg bij het signaal."""
    texts = {
        "CONVERSION_DROP_DETECTED": (
            f"Conversie gedaald met {abs(round(conversion_trend * 100))}% terwijl traffic "
            f"{'stijgt' if traffic_growth > 0 else 'stabiel blijft'}. "
            "Controleer concurrentieprijzen en prijsindex. Overweeg prijs- of promotietesten."
        ),
        "TRAFFIC_DROP_DETECTED": (
            f"Traffic gedaald met {abs(round(traffic_growth * 100))}%. "
            "Mogelijke oorzaak: lagere zichtbaarheid in zoekresultaten of seizoenseffect."
        ),
        "SEARCH_DEMAND_HIGH_LOW_TRAFFIC": (
            f"Extern zoekvolume hoog (DSS {round(dss * 100)}%) maar eigen traffic laag. "
            "SEO- of SEA-investering aanbevolen om marktvraag te benutten."
        ),
        "HIGH_TRAFFIC_LOW_CONVERSION": (
            "Hoge traffic maar lage conversie. Controleer prijs, landingspagina en beschikbaarheid. "
            "Promotietest kan conversie verbeteren."
        ),
        "PRICING_POWER_FROM_DEMAND": (
            f"Hoge vraag (DSS {round(dss * 100)}%) + gezonde conversie. "
            "Lage elasticiteit biedt ruimte voor 3–5% prijsverhoging zonder omzetverlies."
        ),
        "NEW_SKU_HIGH_SEARCH_DEMAND": (
            f"Nieuw product met hoge externe zoekvraag (DSS {round(dss * 100)}%). "
            "Launch-promotie aanbevolen om traffic te activeren."
        ),
        "CATEGORY_DEMAND_DECLINING": (
            "Externe marktvraag voor deze categorie daalt. Wees voorzichtig met inkoopvolume. "
            "Overweeg clearance-pricing voor overstockrisico."
        ),
        "CATEGORY_DEMAND_RISING": (
            f"Stijgende marktvraag (DSS {round(dss * 100)}%) in deze categorie. "
            "Verhoog traffic via marketing en optimaliseer prijspositie."
        ),
        "TRAFFIC_OPPORTUNITY_HIGH": (
            f"Hoge traffic opportunity score ({round(sgs * 100)}% search gap). "
            "Extra commerciële aandacht kan significante groei opleveren."
        ),
        "PROMOTION_NEEDED_FOR_TRAFFIC": (
            "Hoge externe vraag maar eigen traffic achterblijft. "
            "Marketing- of promotiepush aanbevolen."
        ),
        "NO_SIGNAL": "Geen bijzondere signalen. Traffic en conversie binnen normale bandbreedte.",
    }
    return texts.get(reason_code, reason_code)


def _determine_reason_code(
    crs: float,
    traffic_growth: float,
    dss: float,
    sessions: int,
    tos: float,
    chs: float,
    is_new_sku: bool = False,
    is_category: bool = False,
    category_trend: float = 0.0,
) -> str:
    if is_category and category_trend < -0.10:
        return "CATEGORY_DEMAND_DECLINING"
    if is_category and category_trend > 0.15:
        return "CATEGORY_DEMAND_RISING"
    if is_new_sku and dss >= 0.55:
        return "NEW_SKU_HIGH_SEARCH_DEMAND"
    if crs >= 0.65:
        return "CONVERSION_DROP_DETECTED"
    if traffic_growth < -0.20:
        return "TRAFFIC_DROP_DETECTED"
    if dss >= 0.60 and sessions < 800:
        return "SEARCH_DEMAND_HIGH_LOW_TRAFFIC"
    if sessions >= 1000 and chs < 0.35:
        return "HIGH_TRAFFIC_LOW_CONVERSION"
    if chs >= 0.65 and dss >= 0.60:
        return "PRICING_POWER_FROM_DEMAND"
    if tos >= 0.65:
        return "TRAFFIC_OPPORTUNITY_HIGH"
    if dss >= 0.55 and sessions < 600:
        return "PROMOTION_NEEDED_FOR_TRAFFIC"
    return "NO_SIGNAL"


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run_traffic_engine(db: Session) -> tuple[int, int]:
    """
    Voert de volledige traffic intelligence berekening uit voor alle SKU's.
    Returns: (processed, skipped)
    """
    today = date.today()
    cutoff_30 = today - timedelta(days=30)
    cutoff_60 = today - timedelta(days=60)

    products = db.query(models.DimProduct).all()
    traffic_rows = db.query(models.FactTrafficDaily).filter(
        models.FactTrafficDaily.date >= cutoff_60
    ).all()
    search_rows = db.query(models.FactSearchDemandDaily).all()
    pcis_rows = {r.sku_id: r for r in db.query(models.SkuCompetitionScore).all()}
    inventory = db.query(models.FactInventoryDaily).filter(
        models.FactInventoryDaily.date == today
    ).all()
    stock_map = {r.sku_id: r.quantity_on_hand for r in inventory}

    processed, skipped = 0, 0

    for product in products:
        try:
            existing = db.query(models.FactTrafficIntelligenceDaily).filter_by(
                date=today, entity_type="SKU", entity_id=product.sku_id
            ).first()
            if existing:
                processed += 1
                continue

            sku_traffic = [r for r in traffic_rows if r.entity_id == product.sku_id and r.entity_type == "SKU"]

            recent = [r for r in sku_traffic if r.date >= cutoff_30]
            previous = [r for r in sku_traffic if cutoff_60 <= r.date < cutoff_30]

            r_sess = sum(r.sessions or 0 for r in recent)
            r_orders = sum(r.orders or 0 for r in recent)
            r_atc = sum(r.add_to_cart or 0 for r in recent)
            r_rev = sum(float(r.revenue or 0) for r in recent)
            r_margin = sum(float(r.margin or 0) for r in recent)
            r_pv = sum(r.pageviews or 0 for r in recent)
            r_isearch = sum(r.internal_search_count or 0 for r in recent)
            r_bounce = sum(r.bounce_rate or 0 for r in recent) / len(recent) if recent else 0.55

            p_sess = sum(r.sessions or 0 for r in previous)
            p_orders = sum(r.orders or 0 for r in previous)

            cr_recent = calculate_conversion_rate(r_sess, r_orders)
            cr_prev = calculate_conversion_rate(p_sess, p_orders)

            traffic_growth = calculate_traffic_growth(r_sess, p_sess)
            conversion_trend = calculate_conversion_trend(cr_recent, cr_prev)
            atc_rate = calculate_add_to_cart_rate(r_sess, r_atc)
            rpv = calculate_revenue_per_visitor(r_rev, r_sess)
            mpv = calculate_margin_per_visitor(r_margin, r_sess)

            sku_search = [r for r in search_rows if r.entity_id == product.sku_id]
            total_volume = sum(r.search_volume or 0 for r in sku_search)
            avg_trend = sum(r.trend_index or 0 for r in sku_search) / len(sku_search) if sku_search else 0.30
            own_impressions = sum(r.impressions or 0 for r in sku_search)

            pcis = pcis_rows.get(product.sku_id)
            price_index = float(pcis.price_index or 1.0) if pcis and pcis.price_index else 1.0
            pcis_score = float(pcis.pcis_score or 0.5) if pcis else 0.5
            in_stock = (stock_map.get(product.sku_id) or 0) > 0

            sgs = calculate_search_gap_score(total_volume, r_pv, own_impressions)
            dss = calculate_demand_signal_score(r_pv, r_sess, r_isearch, total_volume, avg_trend)
            chs = calculate_conversion_health_score(cr_recent, atc_rate, rpv, mpv, r_bounce, in_stock, price_index)
            tos = calculate_traffic_opportunity_score(dss, r_sess, mpv, in_stock, sgs)
            crs = calculate_conversion_risk_score(traffic_growth, conversion_trend, price_index, pcis_score)

            reason = _determine_reason_code(crs, traffic_growth, dss, r_sess, tos, chs)
            explanation = generate_traffic_explanation_nl(reason, conversion_trend, traffic_growth, dss, crs, sgs)

            db.add(models.FactTrafficIntelligenceDaily(
                date=today,
                entity_type="SKU",
                entity_id=product.sku_id,
                entity_name=product.product_name,
                demand_signal_score=dss,
                conversion_health_score=chs,
                traffic_opportunity_score=tos,
                conversion_risk_score=crs,
                search_gap_score=sgs,
                traffic_growth=traffic_growth,
                conversion_trend=conversion_trend,
                reason_code=reason,
                explanation_nl=explanation,
            ))
            processed += 1
        except Exception:
            skipped += 1
            continue

    db.commit()
    return processed, skipped
