"""
Backfill demo data voor Traffic & Demand Intelligence Engine.

5 demo-scenario's (per spec):
1. INK001 — hoge traffic, dalende conversie (concurrent goedkoper)
2. PAP001 — hoog zoekvolume, lage eigen traffic (SEO opportunity)
3. OFF001 — hoge traffic, hoge conversie, lage elasticiteit (prijsverhoging)
4. ELC001 — nieuw product met hoge zoekvraag (launch promotion)
5. FRN001 / Furniture — dalende externe vraag (clearance)

Overige 21 SKUs krijgen gemiddelde demo-data.
"""
import os, sys
from datetime import date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
from models import (
    FactTrafficDaily, FactSearchDemandDaily, FactTrafficIntelligenceDaily,
    DimProduct,
)

db = SessionLocal()
vandaag = date.today()

if db.query(FactTrafficIntelligenceDaily).count() > 0:
    print("Traffic intelligence data bestaat al — skip.")
    db.close()
    sys.exit(0)

products = {p.sku_id: p for p in db.query(DimProduct).all()}

# ─── Hulpfunctie: maak traffic records voor N dagen ──────────────────────────

def traffic_record(sku_id, dag, sess, pv, orders, atc, rev, margin, bounce=0.52, isearch=0, channel="organic"):
    return FactTrafficDaily(
        date=dag,
        entity_type="SKU",
        entity_id=sku_id,
        pageviews=pv,
        sessions=sess,
        unique_visitors=int(sess * 0.75),
        clicks=int(pv * 0.45),
        add_to_cart=atc,
        orders=orders,
        units_sold=orders,
        revenue=Decimal(str(round(rev, 4))),
        margin=Decimal(str(round(margin, 4))),
        bounce_rate=bounce,
        avg_time_on_page=142.0,
        internal_search_count=isearch,
        channel=channel,
        device_type="desktop",
    )


# ─── Scenario 1: INK001 — hoge traffic, dalende conversie ─────────────────────
# Laatste 30 dagen: sessies stabiel ~1400/dag maar conversie daalt van 3.2% → 2.1%

for i in range(30):
    dag = vandaag - timedelta(days=30 - i)
    dag_idx = i / 29  # 0.0 → 1.0
    sess = 1380 + int(dag_idx * 80)        # stabiel stijgend
    cr = 0.032 - dag_idx * 0.011          # dalende conversie
    orders = max(1, int(sess * cr))
    atc = int(sess * (cr + 0.04))
    rev = orders * 24.95
    margin = orders * 5.20
    db.add(traffic_record("INK001", dag, sess, int(sess * 2.1), orders, atc, rev, margin, 0.58, 85))

print("  ✓ INK001 traffic (30d — dalende conversie)")

# ─── Scenario 2: PAP001 — hoog extern zoekvolume, lage eigen traffic ──────────

for i in range(30):
    dag = vandaag - timedelta(days=30 - i)
    sess = 280 + int((i / 29) * 40)       # laag en stabiel
    orders = max(1, int(sess * 0.028))
    atc = int(sess * 0.065)
    rev = orders * 18.50
    margin = orders * 3.80
    db.add(traffic_record("PAP001", dag, sess, int(sess * 2.3), orders, atc, rev, margin, 0.62, 28))

print("  ✓ PAP001 traffic (30d — lage traffic, hoog zoekvolume)")

# ─── Scenario 3: OFF001 — hoge traffic, hoge conversie, lage elasticiteit ─────

for i in range(30):
    dag = vandaag - timedelta(days=30 - i)
    sess = 1750 + int((i / 29) * 120)
    cr = 0.056 + (i / 29) * 0.004         # licht stijgend
    orders = max(1, int(sess * cr))
    atc = int(sess * (cr + 0.07))
    rev = orders * 3.95
    margin = orders * 1.60
    db.add(traffic_record("OFF001", dag, sess, int(sess * 1.9), orders, atc, rev, margin, 0.38, 45))

print("  ✓ OFF001 traffic (30d — hoge traffic + conversie, pricing power)")

# ─── Scenario 4: ELC001 — nieuw SKU, laag traffic, hoge externe vraag ─────────

for i in range(15):  # pas 15 dagen data (nieuw product)
    dag = vandaag - timedelta(days=15 - i)
    sess = 140 + int((i / 14) * 60)
    orders = max(0, int(sess * 0.022))
    atc = int(sess * 0.052)
    rev = orders * 89.00
    margin = orders * 18.00
    db.add(traffic_record("ELC001", dag, sess, int(sess * 2.5), orders, atc, rev, margin, 0.67, 12))

print("  ✓ ELC001 traffic (15d — nieuw product)")

# ─── Scenario 5: FRN001 — lage traffic, dalende externe vraag ─────────────────

for i in range(30):
    dag = vandaag - timedelta(days=30 - i)
    sess = max(30, 120 - int((i / 29) * 40))   # dalend
    orders = max(0, int(sess * 0.018))
    atc = int(sess * 0.040)
    rev = orders * 289.00
    margin = orders * 42.00
    db.add(traffic_record("FRN001", dag, sess, int(sess * 1.8), orders, atc, rev, margin, 0.70, 5))

print("  ✓ FRN001 traffic (30d — dalende traffic + vraag)")

# ─── Overige SKUs: gemiddelde demo-data ───────────────────────────────────────

GEMIDDELD_CONFIG = {
    "INK002": (820, 0.038, 29.95, 6.50, 0.48),
    "INK003": (650, 0.031, 34.95, 7.20, 0.54),
    "INK004": (580, 0.035, 27.50, 5.80, 0.50),
    "INK005": (490, 0.029, 22.00, 4.60, 0.55),
    "INK006": (380, 0.025, 19.95, 4.10, 0.58),
    "OFF002": (920, 0.042, 8.95, 2.80, 0.44),
    "OFF003": (740, 0.038, 12.95, 3.60, 0.46),
    "OFF004": (560, 0.033, 6.50, 1.90, 0.51),
    "PAP002": (680, 0.030, 15.95, 2.90, 0.56),
    "PAP003": (420, 0.026, 18.50, 3.20, 0.60),
    "FRN002": (75, 0.015, 199.00, 32.00, 0.72),
    "PKG001": (310, 0.028, 4.50, 1.10, 0.54),
    "PKG002": (480, 0.036, 3.80, 1.40, 0.49),
    "CLN001": (290, 0.031, 6.20, 1.80, 0.55),
    "CLN002": (260, 0.028, 5.80, 1.60, 0.57),
    "CAN001": (340, 0.034, 2.90, 0.90, 0.52),
    "CAN002": (410, 0.040, 3.20, 1.20, 0.48),
    "ELC002": (220, 0.020, 49.00, 8.50, 0.64),
    "PRT001": (185, 0.018, 149.00, 22.00, 0.66),
    "PRT002": (160, 0.016, 189.00, 28.00, 0.68),
    "CLR001": (95, 0.012, 12.00, 1.50, 0.71),
}

import random
random.seed(42)

for sku_id, (base_sess, base_cr, price, margin_pp, bounce) in GEMIDDELD_CONFIG.items():
    for i in range(14):  # 14 dagen data
        dag = vandaag - timedelta(days=14 - i)
        noise = random.uniform(0.88, 1.12)
        sess = max(10, int(base_sess * noise))
        cr = max(0.005, base_cr * random.uniform(0.90, 1.10))
        orders = max(0, int(sess * cr))
        atc = int(sess * (cr + 0.03))
        rev = orders * price
        margin = orders * margin_pp
        db.add(traffic_record(sku_id, dag, sess, int(sess * 2.0), orders, atc, rev, margin, bounce, 0))

print(f"  ✓ {len(GEMIDDELD_CONFIG)} overige SKUs — gemiddelde demo-data")

# ─── Search Demand Demo Data ──────────────────────────────────────────────────

SEARCH_DEMO = [
    # INK001: A-merk toner — merkzoekwoorden + generieke zoektermen
    ("INK001", "HP 364 inkt cartridge", "BRAND",   4200, 1850, 92, 0.050, 2.8, 0.75, 0.65, 1.85, "google"),
    ("INK001", "HP 364 zwart",          "BRAND",   2800, 1120, 56, 0.050, 3.1, 0.70, 0.60, 1.42, "google"),
    ("INK001", "HP inktcartridge goedkoop", "GENERIC", 6500, 820, 28, 0.034, 4.8, 0.68, 0.82, 2.10, "google"),
    ("INK001", "CN684EE",               "MPN",     1100, 480, 22, 0.046, 1.5, 0.55, 0.40, 0.95, "google"),

    # PAP001: Generiek papier — hoog zoekvolume, weinig eigen zichtbaarheid
    ("PAP001", "kopieerpapier A4",           "GENERIC", 8500, 210, 8,  0.038, 8.2, 0.45, 0.90, 0.22, "google"),
    ("PAP001", "printpapier goedkoop",       "GENERIC", 6200, 155, 6,  0.039, 9.1, 0.42, 0.88, 0.18, "google"),
    ("PAP001", "80 grams papier bulk",       "GENERIC", 3800, 98,  4,  0.041, 7.8, 0.52, 0.75, 0.28, "google"),
    ("PAP001", "Double A kopieerpapier",     "BRAND",   2100, 320, 18, 0.056, 3.2, 0.72, 0.55, 0.65, "google"),

    # OFF001: Pennen — sterke eigen zichtbaarheid
    ("OFF001", "balpen kantoor",             "GENERIC", 3100, 1480, 95, 0.064, 2.1, 0.82, 0.45, 0.85, "google"),
    ("OFF001", "Staedtler balpen",           "BRAND",   2200, 1250, 80, 0.064, 1.8, 0.85, 0.50, 1.10, "google"),
    ("OFF001", "blauwe balpen set",          "GENERIC", 1800, 920, 62, 0.067, 2.4, 0.78, 0.48, 0.72, "google"),

    # ELC001: Nieuw product — hoog zoekvolume, laag eigen bereik
    ("ELC001", "USB hub kantoor",            "GENERIC", 4200, 95,  4,  0.042, 6.8, 0.55, 0.82, 1.45, "google"),
    ("ELC001", "USB splitter 4 poorten",     "GENERIC", 2900, 65,  3,  0.046, 7.5, 0.50, 0.78, 1.20, "google"),
    ("ELC001", "USB hub desktop computer",   "GENERIC", 2100, 48,  2,  0.042, 8.2, 0.48, 0.80, 1.05, "google"),

    # FRN001: Meubels — dalende marktvraag
    ("FRN001", "ergonomische bureaustoel",   "GENERIC", 5800, 280, 12, 0.043, 5.5, 0.28, 0.55, 2.80, "google"),
    ("FRN001", "bureaustoel goedkoop",       "GENERIC", 4200, 190, 8,  0.042, 6.8, 0.25, 0.62, 2.10, "google"),
    ("FRN001", "thuiswerken stoel",          "GENERIC", 3100, 145, 5,  0.034, 8.1, 0.22, 0.65, 1.85, "google"),

    # Overige SKUs
    ("INK002", "123inkt cartridge HP",      "BRAND",   1800, 920, 62, 0.067, 2.2, 0.78, 0.42, 0.95, "google"),
    ("OFF002", "ordner lever arch",          "GENERIC", 2100, 980, 58, 0.059, 2.8, 0.72, 0.40, 0.62, "google"),
    ("PAP002", "A4 papier 500 vel",          "GENERIC", 3400, 680, 35, 0.051, 4.2, 0.55, 0.68, 0.45, "google"),
    ("PKG002", "verzenddoos karton",         "GENERIC", 2800, 850, 54, 0.064, 2.5, 0.68, 0.52, 0.72, "google"),
    ("CAN002", "koffie kantoor",             "GENERIC", 3200, 980, 68, 0.069, 2.1, 0.80, 0.45, 0.55, "google"),
]

for (sku_id, keyword, ktype, vol, imp, clicks, ctr, pos, trend, comp, cpc, src) in SEARCH_DEMO:
    db.add(FactSearchDemandDaily(
        date=vandaag,
        entity_type="SKU",
        entity_id=sku_id,
        keyword=keyword,
        keyword_type=ktype,
        search_volume=vol,
        impressions=imp,
        clicks=clicks,
        ctr=ctr,
        average_position=pos,
        trend_index=trend,
        competition_level=comp,
        cpc_estimate=Decimal(str(cpc)),
        source=src,
    ))

print(f"  ✓ {len(SEARCH_DEMO)} search demand keyword records")

# ─── Traffic Intelligence Daily (handmatige spec-data) ───────────────────────

INTEL_CONFIG = [
    # sku_id, naam, dss, chs, tos, crs, sgs, tg, ct, reason, uitleg_kort
    ("INK001", None, 0.64, 0.28, 0.42, 0.78, 0.45, 0.05,  -0.34, "CONVERSION_DROP_DETECTED",
     "Conversie gedaald met 34% terwijl traffic stabiel is. Concurrent GoedkoopToner.nl prijst 23% lager (CSRS 72%). Aanbeveling: prijs- of promotietest."),

    ("PAP001", None, 0.82, 0.44, 0.76, 0.35, 0.78, 0.08,  0.02,  "SEARCH_DEMAND_HIGH_LOW_TRAFFIC",
     "Hoog extern zoekvolume (DSS 82%) maar eigen traffic laag (280 sess/mnd). SEO/SEA investering aanbevolen om marktvraag te benutten."),

    ("OFF001", None, 0.74, 0.81, 0.38, 0.18, 0.22, 0.12,  0.08,  "PRICING_POWER_FROM_DEMAND",
     "Hoge conversie (5.8%) + lage elasticiteit (-0.4) + stijgende traffic (+12%). Prijsverhoging van 3–5% testen zonder omzetverlies."),

    ("ELC001", None, 0.71, 0.32, 0.68, 0.28, 0.72, None,  None,  "NEW_SKU_HIGH_SEARCH_DEMAND",
     "Nieuw product met hoge externe zoekvraag (DSS 71%). Eigen traffic nog laag (150 sess/mnd). Launch-promotie aanbevolen."),

    ("FRN001", None, 0.22, 0.35, 0.25, 0.40, 0.20, -0.28, -0.15, "TRAFFIC_DROP_DETECTED",
     "Traffic gedaald met 28%. Externe marktvraag (DSS 22%) daalt ook. Wees voorzichtig met inkoop. Overweeg clearance-pricing."),

    ("INK002", None, 0.62, 0.66, 0.44, 0.25, 0.38, 0.08,  0.06,  "NO_SIGNAL",
     "Geen bijzondere signalen. Traffic en conversie stabiel."),

    ("INK003", None, 0.55, 0.55, 0.38, 0.42, 0.35, -0.05, -0.10, "NO_SIGNAL",
     "Lichte conversiedaling. Monitor concurrentieprijzen."),

    ("INK004", None, 0.58, 0.62, 0.42, 0.22, 0.32, 0.06,  0.04,  "NO_SIGNAL",
     "Traffic en conversie stabiel."),

    ("OFF002", None, 0.60, 0.65, 0.38, 0.20, 0.28, 0.10,  0.06,  "NO_SIGNAL",
     "Stabiele prestaties."),

    ("PAP002", None, 0.68, 0.50, 0.52, 0.48, 0.55, 0.02, -0.08, "HIGH_TRAFFIC_LOW_CONVERSION",
     "Hoge traffic maar conversie daalt. Controleer prijspositie en beschikbaarheid."),

    ("PKG002", None, 0.65, 0.68, 0.40, 0.18, 0.35, 0.14,  0.08,  "PRICING_POWER_FROM_DEMAND",
     "Sterk huismerk met groeiende vraag. Overweeg lichte prijsverhoging."),

    ("CAN002", None, 0.66, 0.70, 0.42, 0.16, 0.32, 0.12,  0.10,  "NO_SIGNAL",
     "Uitstekende prestaties. Geen actie nodig."),

    ("ELC002", None, 0.60, 0.38, 0.58, 0.32, 0.62, 0.05, -0.04, "TRAFFIC_OPPORTUNITY_HIGH",
     "Hoge search gap (SGS 62%). Extra traffic via SEO/SEA gewenst."),

    ("FRN002", None, 0.20, 0.32, 0.22, 0.38, 0.18, -0.25, -0.12, "TRAFFIC_DROP_DETECTED",
     "Traffic daalt. Lage externe vraag voor meubelen."),
]

# Vul overige SKUs met standaard
alle_sku_ids = [p.sku_id for p in db.query(DimProduct).all()]
intel_sku_ids = [c[0] for c in INTEL_CONFIG]
for sku_id in alle_sku_ids:
    if sku_id not in intel_sku_ids:
        p = products.get(sku_id)
        INTEL_CONFIG.append((sku_id, p.product_name if p else sku_id,
            0.42, 0.55, 0.38, 0.28, 0.30, 0.03, 0.01, "NO_SIGNAL",
            "Geen bijzondere signalen. Traffic en conversie binnen normale bandbreedte."))

for cfg in INTEL_CONFIG:
    sku_id = cfg[0]
    naam_override = cfg[1]
    p = products.get(sku_id)
    naam = naam_override or (p.product_name if p else sku_id)
    db.add(FactTrafficIntelligenceDaily(
        date=vandaag,
        entity_type="SKU",
        entity_id=sku_id,
        entity_name=naam,
        demand_signal_score=cfg[2],
        conversion_health_score=cfg[3],
        traffic_opportunity_score=cfg[4],
        conversion_risk_score=cfg[5],
        search_gap_score=cfg[6],
        traffic_growth=cfg[7],
        conversion_trend=cfg[8],
        reason_code=cfg[9],
        explanation_nl=cfg[10],
    ))
    print(f"  ✓ Intelligence: {sku_id} → {cfg[9]}")

db.commit()
db.close()
print("\n✅ Traffic backfill voltooid.")
