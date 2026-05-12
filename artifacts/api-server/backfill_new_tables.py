"""
One-time backfill: inserts competition scores, A/B test data,
CIS/CSRS/CSS, elasticity, and ISV data for existing seeded databases.
Run: python backfill_new_tables.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta, datetime
from database import SessionLocal
import models

PRODUCTS = [
    ("INK001", 18.99, 8.50),
    ("INK002",  7.49, 2.50),
    ("INK003", 16.99, 7.20),
    ("INK004",  5.99, 1.80),
    ("INK005", 21.99, 9.00),
    ("INK006", 49.99,22.00),
    ("OFF001",  4.99, 1.20),
    ("OFF002",  6.49, 2.50),
    ("OFF003",  2.99, 0.80),
    ("OFF004",  5.49, 2.00),
    ("PAP001",  4.49, 1.80),
    ("PAP002", 19.99, 8.00),
    ("PAP003",  6.99, 2.20),
    ("PKG001", 14.99, 6.00),
    ("PKG002", 18.99, 8.00),
    ("CLN001",  3.99, 1.50),
    ("CLN002",  3.49, 1.20),
    ("CAN001", 12.99, 6.00),
    ("CAN002",  4.99, 2.00),
    ("ELC001",  8.99, 3.00),
    ("ELC002",  9.99, 4.00),
    ("FRN001",189.00,80.00),
    ("FRN002",299.00,150.00),
    ("PRT001",129.00,55.00),
    ("PRT002", 59.00,28.00),
    ("CLR001", 19.99,12.00),
]

COMPETITION_SCORES = [
    ("INK001",0.85,0.62,0.70,0.75,0.78,0.05,0.38,0.72,"Strong",  0.97,3,1,{"COMPETITOR_IGNORED_OUTLIER":1}),
    ("INK002",0.80,0.72,0.90,0.75,0.80,0.05,0.15,0.76,"Strong",  0.99,3,0,{}),
    ("INK003",0.83,0.58,0.70,0.75,0.76,0.05,0.32,0.70,"Strong",  0.97,3,1,{"COMPETITOR_IGNORED_OUTLIER":1}),
    ("INK004",0.78,0.68,0.90,0.75,0.79,0.05,0.12,0.74,"Strong",  0.98,2,0,{}),
    ("INK005",0.72,0.55,0.68,0.50,0.72,0.05,0.35,0.62,"Influence",1.02,2,1,{"COMPETITOR_IGNORED_OUT_OF_STOCK":1}),
    ("INK006",0.80,0.75,0.10,0.75,0.82,0.05,0.52,0.65,"Influence",0.96,3,0,{}),
    ("OFF001",0.65,0.55,0.05,0.50,0.68,0.10,0.22,0.48,"Influence",1.01,2,0,{}),
    ("OFF002",0.45,0.38,0.05,0.25,0.55,0.10,0.28,0.35,"Monitor", 1.03,1,0,{}),
    ("OFF003",0.55,0.52,0.05,0.50,0.65,0.10,0.18,0.44,"Monitor", 0.99,2,0,{}),
    ("OFF004",0.58,0.50,0.05,0.50,0.62,0.10,0.25,0.47,"Influence",1.00,2,1,{"COMPETITOR_IGNORED_DIFFERENT_PACK_SIZE":1}),
    ("PAP001",0.88,0.90,0.05,0.75,0.85,0.05,0.42,0.82,"Strong",  0.96,3,0,{}),
    ("PAP002",0.85,0.88,0.05,0.75,0.82,0.05,0.45,0.81,"Strong",  0.95,3,1,{"COMPETITOR_IGNORED_BAD_MATCH":1}),
    ("PAP003",0.60,0.55,0.05,0.50,0.65,0.05,0.32,0.54,"Influence",1.04,2,0,{}),
    ("PKG001",0.65,0.62,0.05,0.50,0.70,0.05,0.28,0.57,"Influence",0.97,2,0,{}),
    ("PKG002",0.68,0.65,0.05,0.50,0.68,0.05,0.35,0.58,"Influence",0.98,2,1,{"COMPETITOR_IGNORED_OUTLIER":1}),
    ("CLN001",0.48,0.45,0.05,0.50,0.60,0.82,0.22,0.44,"Monitor", 1.00,2,0,{}),
    ("CLN002",0.45,0.42,0.05,0.50,0.58,0.78,0.20,0.43,"Monitor", 1.01,2,0,{}),
    ("CAN001",0.55,0.50,0.05,0.25,0.62,0.88,0.28,0.52,"Influence",0.96,1,0,{}),
    ("CAN002",0.50,0.45,0.05,0.25,0.58,0.82,0.18,0.48,"Influence",0.97,1,0,{}),
    ("ELC001",0.92,0.85,0.05,0.75,0.88,0.05,0.38,0.78,"Strong",  0.94,3,1,{"COMPETITOR_IGNORED_OUTLIER":1}),
    ("ELC002",0.90,0.82,0.05,0.75,0.85,0.05,0.42,0.76,"Strong",  0.95,3,0,{}),
    ("FRN001",0.35,0.15,0.05,0.25,0.52,0.05,0.58,0.32,"Monitor", 0.98,1,0,{}),
    ("FRN002",0.32,0.12,0.05,0.25,0.48,0.05,0.62,0.30,"Monitor", 0.99,1,0,{}),
    ("PRT001",0.88,0.85,0.05,0.75,0.85,0.05,0.55,0.74,"Strong",  0.96,3,1,{"COMPETITOR_IGNORED_BAD_DELIVERY":1}),
    ("PRT002",0.85,0.82,0.05,0.75,0.82,0.05,0.48,0.71,"Strong",  0.95,3,0,{}),
    ("CLR001",0.15,0.12,0.05,0.25,0.35,0.02,0.08,0.14,"Ignore",  1.25,0,2,{"COMPETITOR_IGNORED_LOW_RELEVANCE":2}),
]

# sku_id, group, bl_price, curr_price, bl_units, curr_units, bl_conv, curr_conv
AB_SKUS = [
    ("INK001","AI",   18.99,18.49, 14,15,0.0480,0.0510),
    ("INK003","AI",   16.99,16.49, 10,11,0.0420,0.0455),
    ("INK005","AI",   21.99,22.49,  8, 8,0.0350,0.0348),
    ("OFF001","AI",    4.99, 5.29, 24,23,0.0620,0.0610),
    ("PAP001","AI",    4.49, 4.29, 75,82,0.0820,0.0870),
    ("PKG001","AI",   14.99,14.49, 12,13,0.0390,0.0415),
    ("CLN001","AI",    3.99, 3.99, 21,21,0.0680,0.0682),
    ("CAN001","AI",   12.99,12.49, 14,15,0.0510,0.0540),
    ("ELC001","AI",    8.99, 8.49, 20,22,0.0720,0.0785),
    ("FRN001","AI",  189.00,185.00, 1, 1,0.0085,0.0088),
    ("PRT001","AI",  129.00,124.00, 2, 3,0.0120,0.0145),
    ("PAP003","AI",    6.99, 6.99,  9, 9,0.0340,0.0342),
    ("PKG002","AI",   18.99,17.99, 17,19,0.0480,0.0520),
    ("INK002","CONTROL", 7.49, 7.49, 11,11,0.0520,0.0519),
    ("INK004","CONTROL", 5.99, 5.99,  9, 9,0.0490,0.0491),
    ("INK006","CONTROL",49.99,49.99,  6, 6,0.0310,0.0309),
    ("OFF002","CONTROL", 6.49, 6.49, 11,11,0.0430,0.0430),
    ("PAP002","CONTROL",19.99,19.99, 54,54,0.0780,0.0779),
    ("CLN002","CONTROL", 3.49, 3.49, 18,18,0.0650,0.0650),
    ("CAN002","CONTROL", 4.99, 4.99, 11,11,0.0470,0.0470),
    ("ELC002","CONTROL", 9.99, 9.99, 14,14,0.0690,0.0688),
    ("FRN002","CONTROL",299.00,299.00, 0, 0,0.0075,0.0074),
    ("PRT002","CONTROL", 59.00,59.00,  3, 3,0.0130,0.0130),
    ("OFF003","CONTROL", 2.99, 2.99, 29,29,0.0750,0.0749),
    ("OFF004","CONTROL", 5.49, 5.49, 18,18,0.0570,0.0570),
    ("CLR001","CONTROL",19.99,19.99,  0, 0,0.0045,0.0045),
]

# CIS data per SKU per competitor
# (sku_id, competitor_name, layer, cis, csrs, css, cis_class, status,
#  reason_code, pricing_action, competitor_price,
#  avail, del_speed, stock_stab, list_consist,
#  price_dev, price_vol, comp_type, del_rel, weight)
CIS_DATA = [
    # INK001 — Strong competition
    ("INK001","Bol.com",        "direct",      0.82,0.88,0.85,"Primaire concurrent","Actief","PRIJS_MONITOREN","PRIJSHERZIENING_NODIG",18.29, 0.92,0.85,0.88,0.90, 0.88,0.82,0.90,0.85, 0.82),
    ("INK001","Amazon NL",      "direct",      0.71,0.72,0.78,"Sterke concurrent", "Actief","PRIJS_MONITOREN","PRIJSHERZIENING_NODIG",18.49, 0.78,0.70,0.72,0.68, 0.80,0.75,0.85,0.72, 0.71),
    ("INK001","Coolblue",       "direct",      0.65,0.80,0.80,"Sterke concurrent", "Actief","PRIJS_ACCEPTABEL","GEEN_ACTIE_NODIG",      19.99, 0.85,0.80,0.82,0.72, 0.82,0.78,0.88,0.80, 0.65),
    ("INK001","Office Depot",   "functioneel", 0.38,0.60,0.72,"Zwakke concurrent", "Monitoren","PRIJS_BUITEN_BEREIK","GEEN_ACTIE_NODIG",17.50, 0.65,0.58,0.62,0.55, 0.74,0.68,0.75,0.60, 0.38),
    # INK002 — Strong
    ("INK002","Bol.com",        "direct",      0.78,0.90,0.88,"Primaire concurrent","Actief","PRIJS_MONITOREN","PRIJSHERZIENING_NODIG",7.29,  0.95,0.88,0.90,0.88, 0.90,0.85,0.92,0.88, 0.78),
    ("INK002","Amazon NL",      "direct",      0.65,0.75,0.80,"Sterke concurrent", "Actief","PRIJS_MONITOREN","GEEN_ACTIE_NODIG",      7.49,  0.80,0.72,0.75,0.72, 0.82,0.78,0.85,0.75, 0.65),
    ("INK002","Staples",        "functioneel", 0.42,0.55,0.68,"Zwakke concurrent", "Monitoren","PRIJS_ACCEPTABEL","GEEN_ACTIE_NODIG",   7.99,  0.60,0.52,0.55,0.52, 0.70,0.65,0.72,0.55, 0.42),
    # INK003 — Strong
    ("INK003","Bol.com",        "direct",      0.79,0.85,0.82,"Primaire concurrent","Actief","PRIJS_MONITOREN","PRIJSHERZIENING_NODIG",16.49, 0.88,0.82,0.85,0.85, 0.85,0.80,0.88,0.82, 0.79),
    ("INK003","Amazon NL",      "direct",      0.68,0.70,0.75,"Sterke concurrent", "Actief","PRIJS_MONITOREN","GEEN_ACTIE_NODIG",      16.99, 0.75,0.68,0.70,0.65, 0.78,0.72,0.82,0.70, 0.68),
    ("INK003","Office Depot",   "functioneel", 0.35,0.55,0.65,"Zwakke concurrent", "Monitoren","UITBIJTER_PRIJS","GEEN_ACTIE_NODIG",   15.00, 0.60,0.55,0.58,0.50, 0.68,0.62,0.70,0.55, 0.35),
    # PAP001 — Strong
    ("PAP001","Bol.com",        "direct",      0.85,0.92,0.88,"Primaire concurrent","Actief","PRIJS_MONITOREN","PRIJSHERZIENING_NODIG",4.29,  0.95,0.90,0.92,0.90, 0.90,0.88,0.92,0.90, 0.85),
    ("PAP001","Amazon NL",      "direct",      0.72,0.82,0.80,"Sterke concurrent", "Actief","PRIJS_MONITOREN","GEEN_ACTIE_NODIG",      4.49,  0.85,0.80,0.82,0.78, 0.82,0.80,0.88,0.82, 0.72),
    ("PAP001","Staples",        "direct",      0.60,0.75,0.78,"Sterke concurrent", "Actief","PRIJS_ACCEPTABEL","GEEN_ACTIE_NODIG",      4.69,  0.78,0.72,0.75,0.70, 0.80,0.75,0.85,0.75, 0.60),
    # ELC001 — Strong
    ("ELC001","Bol.com",        "direct",      0.88,0.90,0.85,"Primaire concurrent","Actief","PRIJS_MONITOREN","PRIJSHERZIENING_NODIG",8.49,  0.92,0.88,0.90,0.88, 0.88,0.85,0.90,0.88, 0.88),
    ("ELC001","Amazon NL",      "direct",      0.75,0.80,0.82,"Primaire concurrent","Actief","PRIJS_MONITOREN","PRIJSHERZIENING_NODIG",8.29,  0.82,0.78,0.80,0.78, 0.85,0.80,0.88,0.80, 0.75),
    ("ELC001","Coolblue",       "direct",      0.62,0.72,0.78,"Sterke concurrent", "Actief","PRIJS_ACCEPTABEL","GEEN_ACTIE_NODIG",      8.99,  0.75,0.70,0.72,0.68, 0.80,0.75,0.85,0.72, 0.62),
    # OFF001 — Influence
    ("OFF001","Bol.com",        "direct",      0.58,0.72,0.75,"Sterke concurrent", "Actief","PRIJS_MONITOREN","GEEN_ACTIE_NODIG",       4.79,  0.75,0.70,0.72,0.70, 0.78,0.72,0.80,0.72, 0.58),
    ("OFF001","Amazon NL",      "functioneel", 0.40,0.60,0.68,"Zwakke concurrent", "Monitoren","PRIJS_ACCEPTABEL","GEEN_ACTIE_NODIG",   5.29,  0.65,0.58,0.60,0.55, 0.70,0.65,0.72,0.60, 0.40),
    # PRT001 — Strong
    ("PRT001","Bol.com",        "direct",      0.80,0.88,0.82,"Primaire concurrent","Actief","PRIJS_MONITOREN","PRIJSHERZIENING_NODIG",124.00, 0.90,0.85,0.88,0.88, 0.85,0.80,0.88,0.85, 0.80),
    ("PRT001","Amazon NL",      "direct",      0.68,0.78,0.80,"Sterke concurrent", "Actief","PRIJS_MONITOREN","GEEN_ACTIE_NODIG",      129.00, 0.80,0.75,0.78,0.72, 0.82,0.78,0.85,0.78, 0.68),
    ("PRT001","Coolblue",       "direct",      0.55,0.70,0.75,"Sterke concurrent", "Actief","PRIJS_ACCEPTABEL","GEEN_ACTIE_NODIG",      134.99, 0.72,0.68,0.70,0.65, 0.78,0.72,0.80,0.70, 0.55),
    # CLR001 — Negeren
    ("CLR001","Bol.com",        "categorie",   0.15,0.55,0.60,"Negeren",           "Negeren","LAGE_RELEVANTIE","GEEN_ACTIE_NODIG",      22.99, 0.60,0.55,0.58,0.50, 0.62,0.58,0.65,0.55, 0.15),
    ("CLR001","Amazon NL",      "categorie",   0.12,0.45,0.55,"Negeren",           "Negeren","LAGE_RELEVANTIE","GEEN_ACTIE_NODIG",      24.99, 0.50,0.45,0.48,0.42, 0.58,0.52,0.60,0.45, 0.12),
]

# Elasticity data per SKU
# (sku_id, own_elast, cross_elast, comp_elast, intern_elast, confidence, confidence_class, volume_30d, price_var_30d)
ELASTICITY_DATA = [
    ("INK001", -1.82, 0.45, 1.20, -0.35, 0.85, "hoog_betrouwbaar", 420, 0.03),
    ("INK002", -2.15, 0.52, 1.45, -0.28, 0.88, "hoog_betrouwbaar", 330, 0.02),
    ("INK003", -1.65, 0.38, 1.10, -0.42, 0.82, "hoog_betrouwbaar", 300, 0.04),
    ("INK004", -1.95, 0.48, 1.35, -0.25, 0.86, "hoog_betrouwbaar", 270, 0.02),
    ("INK005", -1.45, 0.30, 0.95, -0.30, 0.78, "bruikbaar",         240, 0.05),
    ("INK006", -0.85, 0.20, 0.72, -0.18, 0.75, "bruikbaar",         180, 0.03),
    ("OFF001", -1.25, 0.35, 0.88, -0.15, 0.72, "bruikbaar",         720, 0.02),
    ("OFF002", -0.95, 0.28, 0.65, -0.10, 0.68, "bruikbaar",         330, 0.03),
    ("OFF003", -1.10, 0.32, 0.72, -0.08, 0.65, "bruikbaar",         870, 0.02),
    ("OFF004", -0.88, 0.25, 0.60, -0.12, 0.62, "bruikbaar",         540, 0.03),
    ("PAP001", -2.35, 0.65, 1.55, -0.22, 0.90, "hoog_betrouwbaar", 2250,0.01),
    ("PAP002", -2.10, 0.58, 1.42, -0.20, 0.88, "hoog_betrouwbaar", 1620,0.01),
    ("PAP003", -1.35, 0.42, 0.92, -0.15, 0.70, "bruikbaar",         270, 0.03),
    ("PKG001", -1.18, 0.35, 0.85, -0.12, 0.68, "bruikbaar",         360, 0.04),
    ("PKG002", -1.22, 0.38, 0.88, -0.14, 0.70, "bruikbaar",         510, 0.04),
    ("CLN001", -0.75, 0.18, 0.55, -0.08, 0.58, "bruikbaar",         630, 0.02),
    ("CLN002", -0.70, 0.15, 0.50, -0.06, 0.55, "bruikbaar",         540, 0.02),
    ("CAN001", -1.05, 0.28, 0.72, -0.10, 0.65, "bruikbaar",         420, 0.03),
    ("CAN002", -0.92, 0.22, 0.65, -0.08, 0.62, "bruikbaar",         330, 0.03),
    ("ELC001", -1.68, 0.45, 1.15, -0.28, 0.80, "hoog_betrouwbaar",  600, 0.04),
    ("ELC002", -1.55, 0.40, 1.05, -0.25, 0.78, "bruikbaar",          420, 0.04),
    ("FRN001", -0.45, 0.12, 0.38, -0.05, 0.42, "laag_betrouwbaar",   30, 0.08),
    ("FRN002", -0.38, 0.10, 0.32, -0.04, 0.38, "laag_betrouwbaar",    0, 0.10),
    ("PRT001", -1.12, 0.32, 0.82, -0.18, 0.72, "bruikbaar",           60, 0.05),
    ("PRT002", -1.05, 0.28, 0.75, -0.15, 0.68, "bruikbaar",           90, 0.05),
    ("CLR001", -0.22, 0.05, 0.18, -0.02, 0.28, "laag_betrouwbaar",    0, 0.15),
]

# ISV (Internal Substitution Value) paren
# (a_brand_sku, private_label_sku, switch_prob, margin_gap, isv, actie, reden,
#  a_brand_price, hl_price, a_marge_pct, hl_marge_pct)
ISV_DATA = [
    ("INK001","INK002", 0.42, 0.38, 0.1596, "PRIVATE_LABEL_PUSH",
     "Hoge schakelkans en significante margekloof — huismerk actief promoten.",
     18.99, 7.49, 0.448, 0.666),
    ("INK003","INK004", 0.38, 0.35, 0.1330, "PRIVATE_LABEL_PUSH",
     "Substitutiemogelijkheid aanwezig — huismerk bij bezoek tonen.",
     16.99, 5.99, 0.424, 0.700),
    ("INK005","INK006", 0.18, 0.22, 0.0396, "HOLD_PRICE_MONITOR",
     "Lage schakelkans — schakeldrempel te hoog voor actieve push.",
     21.99,49.99, 0.410, 0.560),
    ("PAP001","PAP003", 0.55, 0.42, 0.2310, "PORTFOLIO_MARGIN_OPTIMIZATION",
     "Hoge schakelkans — portfolio-marge optimaliseren via mix-pricing.",
     4.49,  6.99, 0.401, 0.685),
    ("PAP002","PAP003", 0.48, 0.38, 0.1824, "TRAFFIC_TO_MARGIN_SWITCH",
     "Traffic van volumeproduct naar hogere margevariant sturen.",
     19.99, 6.99, 0.400, 0.685),
    ("ELC001","ELC002", 0.35, 0.28, 0.0980, "PRICE_A_BRAND_COMPETITIVELY",
     "Beperkte margekloof — A-merkprijs competitief houden om switching te voorkomen.",
     8.99,  9.99, 0.666, 0.600),
    ("PRT001","PRT002", 0.28, 0.32, 0.0896, "PRICE_A_BRAND_COMPETITIVELY",
     "Prijsverschil te klein voor switching — A-merk competitief prijzen.",
     129.00,59.00, 0.574, 0.525),
    ("CLN001","CLN002", 0.22, 0.18, 0.0396, "HOLD_PRICE_MONITOR",
     "Lage schakelkans — bewaken maar geen actie.",
     3.99,  3.49, 0.624, 0.656),
    ("CAN001","CAN002", 0.30, 0.25, 0.0750, "HOLD_PRICE_MONITOR",
     "Matige schakelkans — prijsniveaus bewaken.",
     12.99, 4.99, 0.538, 0.599),
]


def run():
    db = SessionLocal()
    today = date.today()
    try:
        # ---- 1. PCIS competition scores ----------------------------------------
        if db.query(models.SkuCompetitionScore).count() > 0:
            print("Competition scores already exist — skipping.")
        else:
            prod_map = {p[0]: p for p in PRODUCTS}
            for row in COMPETITION_SCORES:
                sku_id, comp, ps, sub, cr, pr, bd, si, pcis, cls, pi, cu, ce, er = row
                p = prod_map.get(sku_id)
                ref_price = round(float(p[1]) / pi, 4) if p and pi else None
                db.add(models.SkuCompetitionScore(
                    sku_id=sku_id, run_date=today,
                    product_comparability_score=comp,
                    price_sensitivity_score=ps,
                    substitution_score=sub,
                    competitor_relevance_score=cr,
                    competitor_price_reliability_score=pr,
                    basket_dependency_score=bd,
                    strategic_importance_score=si,
                    pcis_score=pcis,
                    competition_class=cls,
                    reference_price=ref_price,
                    price_index=pi,
                    competitors_used=cu,
                    competitors_excluded=ce,
                    excluded_reasons=er,
                ))
            db.commit()
            print(f"Inserted {len(COMPETITION_SCORES)} competition scores.")

        # ---- 2. A/B tests -------------------------------------------------------
        if db.query(models.AbTest).count() > 0:
            print("A/B tests already exist — skipping.")
        else:
            ab_test = models.AbTest(
                name="AI Pricing Engine vs. Statische Prijsstelling — K1 2026",
                description=(
                    "Evalueert de margeverbeteringen, omzetimpact en conversieverbetering "
                    "bij AI-aanbevolen prijzen t.o.v. ongewijzigde prijzen. "
                    "Verdeling: 50/50 per SKU over alle categorieën."
                ),
                start_date=today - timedelta(days=30),
                end_date=today,
                status="active",
                ai_group_sku_count=13,
                control_group_sku_count=13,
            )
            db.add(ab_test)
            db.commit()

            prod_map = {p[0]: p for p in PRODUCTS}
            for row in AB_SKUS:
                sku_id, grp, bl_p, curr_p, bl_u, curr_u, bl_conv, curr_conv = row
                p = prod_map.get(sku_id)
                cost = float(p[2]) if p else float(bl_p) * 0.5
                db.add(models.AbTestResult(
                    test_id=ab_test.id,
                    sku_id=sku_id,
                    group_type=grp,
                    baseline_price=bl_p,
                    current_price=curr_p,
                    baseline_units=float(bl_u),
                    current_units=float(curr_u),
                    baseline_revenue=round(bl_p * bl_u * 30, 2),
                    current_revenue=round(curr_p * curr_u * 30, 2),
                    baseline_margin=round((bl_p - cost) * bl_u * 30, 2),
                    current_margin=round((curr_p - cost) * curr_u * 30, 2),
                    baseline_conversion_rate=bl_conv,
                    current_conversion_rate=curr_conv,
                ))
            db.commit()
            print(f"Inserted A/B test with {len(AB_SKUS)} SKU results.")

        # ---- 3. CIS / CSRS / CSS scores -----------------------------------------
        if db.query(models.CompetitorInfluenceScore).count() > 0:
            print("CIS scores already exist — skipping.")
        else:
            prod_map = {p[0]: p for p in PRODUCTS}
            for row in CIS_DATA:
                (sku_id, comp_name, layer, cis, csrs, css, cis_class, status,
                 reason_code, pricing_action, comp_price,
                 avail, del_sp, stock_stab, list_cons,
                 price_dev, price_vol, comp_type, del_rel, weight) = row
                p = prod_map.get(sku_id)
                own_price = float(p[1]) if p else None
                price_vs_own = round((comp_price - own_price) / own_price * 100, 2) if own_price else None
                db.add(models.CompetitorInfluenceScore(
                    sku_id=sku_id,
                    run_date=today,
                    competitor_name=comp_name,
                    competition_layer=layer,
                    cis_score=cis,
                    csrs_score=csrs,
                    css_score=css,
                    cis_class=cis_class,
                    status=status,
                    reason_code=reason_code,
                    pricing_action=pricing_action,
                    competitor_price=comp_price,
                    price_vs_own_pct=price_vs_own,
                    competitor_weight=weight,
                    # CSRS sub-scores
                    availability_rate=avail,
                    delivery_speed_score=del_sp,
                    stock_stability_score=stock_stab,
                    listing_consistency_score=list_cons,
                    # CSS sub-scores
                    price_deviation_score=price_dev,
                    price_volatility_score=price_vol,
                    competitor_type_score=comp_type,
                    delivery_reliability_score=del_rel,
                ))
            db.commit()
            print(f"Inserted {len(CIS_DATA)} CIS/CSRS/CSS scores.")

        # ---- 4. Elasticity scores ------------------------------------------------
        if db.query(models.SkuElasticity).count() > 0:
            print("Elasticity data already exist — skipping.")
        else:
            for row in ELASTICITY_DATA:
                (sku_id, own_e, cross_e, comp_e, intern_e,
                 conf_score, conf_class, vol_30d, price_var) = row
                db.add(models.SkuElasticity(
                    sku_id=sku_id,
                    run_date=today,
                    own_price_elasticity=own_e,
                    cross_elasticity=cross_e,
                    competitive_elasticity=comp_e,
                    internal_substitution_elasticity=intern_e,
                    elasticity_confidence_score=conf_score,
                    confidence_class=conf_class,
                    sales_volume_30d=vol_30d,
                    price_variation_30d=price_var,
                ))
            db.commit()
            print(f"Inserted {len(ELASTICITY_DATA)} elasticity records.")

        # ---- 5. ISV / Internal competition --------------------------------------
        if db.query(models.InternalCompetitionScore).count() > 0:
            print("ISV data already exist — skipping.")
        else:
            prod_map = {p[0]: p for p in PRODUCTS}
            for row in ISV_DATA:
                (a_sku, hl_sku, switch_prob, margin_gap, isv,
                 actie, reden, a_price, hl_price, a_marge, hl_marge) = row
                db.add(models.InternalCompetitionScore(
                    sku_id=a_sku,
                    paired_sku_id=hl_sku,
                    run_date=today,
                    internal_switch_probability=switch_prob,
                    internal_margin_gap=margin_gap,
                    isv=isv,
                    recommended_internal_action=actie,
                    action_reason=reden,
                    a_brand_price=a_price,
                    private_label_price=hl_price,
                    a_brand_margin_pct=a_marge,
                    private_label_margin_pct=hl_marge,
                ))
            db.commit()
            print(f"Inserted {len(ISV_DATA)} ISV pairs.")

    except Exception as e:
        db.rollback()
        print(f"Backfill mislukt: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run()
    print("Klaar.")
