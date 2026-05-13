"""
Backfill demo data voor BCG Intelligence Engine.

Demo scenario (spec):
- INK002 (123inkt huismerk toner)      → PRIVATE_LABEL_STAR
- INK001 (HP 364 Black Ink)            → DEFENSIVE_CASH_COW
- OFF001 (Staedtler Ballpoint Pen)     → EXTERNAL_STAR  (potloden)
- OFF002 (Avery Lever Arch File)       → INTERNAL_CASH_COW (ordners)
- PAP001 (Double A Copy Paper)         → EXPERIMENTAL_QUESTION_MARK (hoge concurrentiedruk)
- FRN001 (Ergonomic Office Chair)      → LOW_PRIORITY_DOG (meubels)
- Overige SKUs: realistische scores
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
from models import (
    FactBcgClassificationDaily,
    FactBcgHistory,
    FactPrivateLabelIntelligence,
    DimProduct,
)

db = SessionLocal()
vandaag = date.today()
gisteren = vandaag - timedelta(days=1)

# Guard
if db.query(FactBcgClassificationDaily).count() > 0:
    print("BCG data bestaat al — skip.")
    db.close()
    sys.exit(0)

products = {p.sku_id: p for p in db.query(DimProduct).all()}

# ─── Handmatig afgestemde BCG-data per SKU (spec-scenario) ───────────────────
BCG_CONFIG = {
    # Huismerk toners → PRIVATE_LABEL_STAR
    "INK002": {
        "internal": "INTERNAL_STAR",
        "external": "EXTERNAL_STAR",
        "hybrid":   "PRIVATE_LABEL_STAR",
        "ibss": 0.82, "gps": 0.74, "css": 0.76, "mos": 0.71,
        "pps": 0.78, "plsv": 0.85,
        "strategie": "PRIVATE_LABEL_PUSH", "prioriteit": "hoog",
    },
    "INK004": {
        "internal": "INTERNAL_STAR",
        "external": "EXTERNAL_STAR",
        "hybrid":   "PRIVATE_LABEL_STAR",
        "ibss": 0.78, "gps": 0.69, "css": 0.72, "mos": 0.68,
        "pps": 0.74, "plsv": 0.80,
        "strategie": "PRIVATE_LABEL_PUSH", "prioriteit": "hoog",
    },
    # A-merk toners → DEFENSIVE_CASH_COW
    "INK001": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.77, "gps": 0.44, "css": 0.45, "mos": 0.62,
        "pps": 0.52, "plsv": 0.0,
        "strategie": "DEFEND_MARKET_POSITION", "prioriteit": "hoog",
    },
    "INK003": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.72, "gps": 0.41, "css": 0.43, "mos": 0.59,
        "pps": 0.50, "plsv": 0.0,
        "strategie": "DEFEND_MARKET_POSITION", "prioriteit": "hoog",
    },
    "INK005": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.68, "gps": 0.40, "css": 0.44, "mos": 0.55,
        "pps": 0.48, "plsv": 0.0,
        "strategie": "DEFEND_MARKET_POSITION", "prioriteit": "gemiddeld",
    },
    "INK006": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_CASH_COW",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.65, "gps": 0.38, "css": 0.62, "mos": 0.48,
        "pps": 0.55, "plsv": 0.0,
        "strategie": "PROTECT_MARGIN", "prioriteit": "gemiddeld",
    },
    # Potloden / pennen → EXTERNAL_STAR
    "OFF001": {
        "internal": "INTERNAL_STAR",
        "external": "EXTERNAL_STAR",
        "hybrid":   "PRICING_POWER_STAR",
        "ibss": 0.71, "gps": 0.68, "css": 0.73, "mos": 0.75,
        "pps": 0.80, "plsv": 0.0,
        "strategie": "PROTECT_MARGIN", "prioriteit": "hoog",
    },
    "OFF004": {
        "internal": "INTERNAL_QUESTION_MARK",
        "external": "EXTERNAL_STAR",
        "hybrid":   "EXPERIMENTAL_QUESTION_MARK",
        "ibss": 0.55, "gps": 0.71, "css": 0.65, "mos": 0.72,
        "pps": 0.63, "plsv": 0.0,
        "strategie": "EXPERIMENT_PRICE_INCREASE", "prioriteit": "gemiddeld",
    },
    # Ordners → INTERNAL_CASH_COW
    "OFF002": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_CASH_COW",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.74, "gps": 0.39, "css": 0.66, "mos": 0.45,
        "pps": 0.69, "plsv": 0.0,
        "strategie": "PROTECT_MARGIN", "prioriteit": "gemiddeld",
    },
    "OFF003": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_CASH_COW",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.63, "gps": 0.42, "css": 0.58, "mos": 0.43,
        "pps": 0.61, "plsv": 0.0,
        "strategie": "PROTECT_MARGIN", "prioriteit": "gemiddeld",
    },
    # Papier → hoge concurrentiedruk
    "PAP001": {
        "internal": "INTERNAL_QUESTION_MARK",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "EXPERIMENTAL_QUESTION_MARK",
        "ibss": 0.55, "gps": 0.65, "css": 0.38, "mos": 0.70,
        "pps": 0.34, "plsv": 0.0,
        "strategie": "COMPETITIVE_PRICE_MATCH", "prioriteit": "gemiddeld",
    },
    "PAP002": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.68, "gps": 0.47, "css": 0.35, "mos": 0.58,
        "pps": 0.31, "plsv": 0.0,
        "strategie": "DEFEND_MARKET_POSITION", "prioriteit": "hoog",
    },
    "PAP003": {
        "internal": "INTERNAL_QUESTION_MARK",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "EXPERIMENTAL_QUESTION_MARK",
        "ibss": 0.42, "gps": 0.55, "css": 0.45, "mos": 0.60,
        "pps": 0.46, "plsv": 0.0,
        "strategie": "EXPERIMENT_PRICE_INCREASE", "prioriteit": "gemiddeld",
    },
    # Meubels → LOW_PRIORITY_DOG
    "FRN001": {
        "internal": "INTERNAL_DOG",
        "external": "EXTERNAL_DOG",
        "hybrid":   "LOW_PRIORITY_DOG",
        "ibss": 0.22, "gps": 0.18, "css": 0.35, "mos": 0.28,
        "pps": 0.38, "plsv": 0.0,
        "strategie": "LOW_PRIORITY_AUTOMATION", "prioriteit": "laag",
    },
    "FRN002": {
        "internal": "INTERNAL_DOG",
        "external": "EXTERNAL_DOG",
        "hybrid":   "LOW_PRIORITY_DOG",
        "ibss": 0.19, "gps": 0.15, "css": 0.32, "mos": 0.25,
        "pps": 0.35, "plsv": 0.0,
        "strategie": "LOW_PRIORITY_AUTOMATION", "prioriteit": "laag",
    },
    # Verpakking + Schoonmaak (huismerk)
    "PKG001": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_CASH_COW",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.64, "gps": 0.48, "css": 0.55, "mos": 0.50,
        "pps": 0.58, "plsv": 0.0,
        "strategie": "PROTECT_MARGIN", "prioriteit": "gemiddeld",
    },
    "PKG002": {
        "internal": "INTERNAL_STAR",
        "external": "EXTERNAL_STAR",
        "hybrid":   "PRIVATE_LABEL_STAR",
        "ibss": 0.70, "gps": 0.63, "css": 0.68, "mos": 0.64,
        "pps": 0.72, "plsv": 0.75,
        "strategie": "PRIVATE_LABEL_PUSH", "prioriteit": "hoog",
    },
    "CLN001": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_CASH_COW",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.61, "gps": 0.44, "css": 0.57, "mos": 0.46,
        "pps": 0.55, "plsv": 0.0,
        "strategie": "PROTECT_MARGIN", "prioriteit": "gemiddeld",
    },
    "CLN002": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_CASH_COW",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.59, "gps": 0.42, "css": 0.54, "mos": 0.44,
        "pps": 0.53, "plsv": 0.0,
        "strategie": "PROTECT_MARGIN", "prioriteit": "gemiddeld",
    },
    # Kantine
    "CAN001": {
        "internal": "INTERNAL_CASH_COW",
        "external": "EXTERNAL_CASH_COW",
        "hybrid":   "DEFENSIVE_CASH_COW",
        "ibss": 0.66, "gps": 0.50, "css": 0.61, "mos": 0.52,
        "pps": 0.60, "plsv": 0.0,
        "strategie": "PROTECT_MARGIN", "prioriteit": "gemiddeld",
    },
    "CAN002": {
        "internal": "INTERNAL_STAR",
        "external": "EXTERNAL_STAR",
        "hybrid":   "PRIVATE_LABEL_STAR",
        "ibss": 0.72, "gps": 0.67, "css": 0.70, "mos": 0.65,
        "pps": 0.74, "plsv": 0.78,
        "strategie": "PRIVATE_LABEL_PUSH", "prioriteit": "hoog",
    },
    # Elektronica
    "ELC001": {
        "internal": "INTERNAL_QUESTION_MARK",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "EXPERIMENTAL_QUESTION_MARK",
        "ibss": 0.52, "gps": 0.62, "css": 0.42, "mos": 0.65,
        "pps": 0.40, "plsv": 0.0,
        "strategie": "COMPETITIVE_PRICE_MATCH", "prioriteit": "gemiddeld",
    },
    "ELC002": {
        "internal": "INTERNAL_QUESTION_MARK",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "EXPERIMENTAL_QUESTION_MARK",
        "ibss": 0.49, "gps": 0.58, "css": 0.40, "mos": 0.61,
        "pps": 0.38, "plsv": 0.0,
        "strategie": "COMPETITIVE_PRICE_MATCH", "prioriteit": "gemiddeld",
    },
    # Printers
    "PRT001": {
        "internal": "INTERNAL_QUESTION_MARK",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "EXPERIMENTAL_QUESTION_MARK",
        "ibss": 0.48, "gps": 0.65, "css": 0.44, "mos": 0.68,
        "pps": 0.45, "plsv": 0.0,
        "strategie": "COMPETITIVE_PRICE_MATCH", "prioriteit": "gemiddeld",
    },
    "PRT002": {
        "internal": "INTERNAL_QUESTION_MARK",
        "external": "EXTERNAL_QUESTION_MARK",
        "hybrid":   "EXPERIMENTAL_QUESTION_MARK",
        "ibss": 0.45, "gps": 0.61, "css": 0.41, "mos": 0.64,
        "pps": 0.42, "plsv": 0.0,
        "strategie": "COMPETITIVE_PRICE_MATCH", "prioriteit": "gemiddeld",
    },
    # Stock clearance
    "CLR001": {
        "internal": "INTERNAL_DOG",
        "external": "EXTERNAL_DOG",
        "hybrid":   "LOW_PRIORITY_DOG",
        "ibss": 0.15, "gps": 0.12, "css": 0.30, "mos": 0.20,
        "pps": 0.25, "plsv": 0.0,
        "strategie": "LOW_PRIORITY_AUTOMATION", "prioriteit": "laag",
    },
}

# ─── Insert BCG classificaties ────────────────────────────────────────────────
for sku_id, cfg in BCG_CONFIG.items():
    p = products.get(sku_id)
    naam = p.product_name if p else sku_id
    db.add(FactBcgClassificationDaily(
        date=vandaag,
        entity_type="SKU",
        entity_id=sku_id,
        entity_name=naam,
        internal_bcg_class=cfg["internal"],
        external_bcg_class=cfg["external"],
        hybrid_bcg_class=cfg["hybrid"],
        ibss_score=cfg["ibss"],
        gps_score=cfg["gps"],
        css_external_score=cfg["css"],
        mos_score=cfg["mos"],
        pricing_power_score=cfg["pps"],
        plsv_score=cfg["plsv"],
        confidence_score=0.88,
        pricing_strategy=cfg["strategie"],
        strategic_priority=cfg["prioriteit"],
    ))
    print(f"  ✓ BCG SKU: {sku_id} → {cfg['hybrid']}")

# ─── Categorie-level BCG ──────────────────────────────────────────────────────
CAT_CONFIG = [
    ("Ink & Toner",        "INTERNAL_STAR",           "EXTERNAL_STAR",           "PRIVATE_LABEL_STAR",          0.76, 0.57, 0.60, 0.64, 0.65, 0.42, "PRIVATE_LABEL_PUSH",      "hoog"),
    ("Office Supplies",    "INTERNAL_CASH_COW",       "EXTERNAL_CASH_COW",       "DEFENSIVE_CASH_COW",          0.68, 0.47, 0.63, 0.54, 0.68, 0.0,  "PROTECT_MARGIN",          "gemiddeld"),
    ("Paper",              "INTERNAL_QUESTION_MARK",  "EXTERNAL_QUESTION_MARK",  "EXPERIMENTAL_QUESTION_MARK",  0.55, 0.55, 0.39, 0.63, 0.37, 0.0,  "COMPETITIVE_PRICE_MATCH", "gemiddeld"),
    ("Packaging",          "INTERNAL_STAR",           "EXTERNAL_STAR",           "PRIVATE_LABEL_STAR",          0.67, 0.56, 0.62, 0.57, 0.65, 0.38, "PRIVATE_LABEL_PUSH",      "hoog"),
    ("Cleaning",           "INTERNAL_CASH_COW",       "EXTERNAL_CASH_COW",       "DEFENSIVE_CASH_COW",          0.60, 0.43, 0.56, 0.45, 0.54, 0.0,  "PROTECT_MARGIN",          "gemiddeld"),
    ("Canteen Supplies",   "INTERNAL_STAR",           "EXTERNAL_STAR",           "PRIVATE_LABEL_STAR",          0.69, 0.59, 0.66, 0.59, 0.67, 0.39, "PRIVATE_LABEL_PUSH",      "hoog"),
    ("Electronics",        "INTERNAL_QUESTION_MARK",  "EXTERNAL_QUESTION_MARK",  "EXPERIMENTAL_QUESTION_MARK",  0.51, 0.60, 0.41, 0.63, 0.39, 0.0,  "COMPETITIVE_PRICE_MATCH", "gemiddeld"),
    ("Furniture",          "INTERNAL_DOG",            "EXTERNAL_DOG",            "LOW_PRIORITY_DOG",            0.21, 0.17, 0.34, 0.27, 0.37, 0.0,  "LOW_PRIORITY_AUTOMATION", "laag"),
    ("Printers",           "INTERNAL_QUESTION_MARK",  "EXTERNAL_QUESTION_MARK",  "EXPERIMENTAL_QUESTION_MARK",  0.47, 0.63, 0.43, 0.66, 0.44, 0.0,  "COMPETITIVE_PRICE_MATCH", "gemiddeld"),
]

for (cat, ic, ec, hc, ibss, gps, css, mos, pps, plsv, strat, prio) in CAT_CONFIG:
    db.add(FactBcgClassificationDaily(
        date=vandaag,
        entity_type="CATEGORY",
        entity_id=cat,
        entity_name=cat,
        internal_bcg_class=ic,
        external_bcg_class=ec,
        hybrid_bcg_class=hc,
        ibss_score=ibss, gps_score=gps,
        css_external_score=css, mos_score=mos,
        pricing_power_score=pps, plsv_score=plsv,
        confidence_score=0.85,
        pricing_strategy=strat,
        strategic_priority=prio,
    ))
    print(f"  ✓ BCG Categorie: {cat} → {hc}")

# ─── Private Label Intelligence ───────────────────────────────────────────────
PL_CONFIG = [
    # sku_id, switch_prob, margin_gap, isv, plsv, klasse, prio, a_brand_sku
    ("INK002", 0.72, 3.20, 0.58, 0.85, "PRIVATE_LABEL_STAR",     "hoog",     "INK001"),
    ("INK004", 0.68, 3.00, 0.52, 0.80, "PRIVATE_LABEL_STAR",     "hoog",     "INK003"),
    ("PKG002", 0.55, 2.10, 0.40, 0.75, "PRIVATE_LABEL_STAR",     "hoog",     None),
    ("CAN002", 0.60, 2.50, 0.45, 0.78, "PRIVATE_LABEL_STAR",     "hoog",     None),
]

for (sku_id, sp, mg, isv, plsv, klasse, prio, a_sku) in PL_CONFIG:
    p = products.get(sku_id)
    a_p = products.get(a_sku) if a_sku else None
    db.add(FactPrivateLabelIntelligence(
        sku_id=sku_id,
        run_date=vandaag,
        internal_substitution_score=isv,
        internal_switch_probability=sp,
        internal_margin_gap=mg,
        private_label_value_score=plsv,
        private_label_class=klasse,
        strategic_priority=prio,
        a_brand_sku=a_sku,
        paired_sku_name=a_p.product_name if a_p else None,
    ))
    print(f"  ✓ PL Intel: {sku_id} → {klasse}")

# ─── BCG History (demo wijzigingen) ──────────────────────────────────────────
from datetime import datetime
history_items = [
    ("INK001", "SKU", "hybrid", "PRICING_POWER_STAR",    "DEFENSIVE_CASH_COW",   "Concurrentiedruk gestegen (Amazon -12%)"),
    ("PAP001", "SKU", "hybrid", "INTERNAL_CASH_COW",     "EXPERIMENTAL_QUESTION_MARK", "Hoge marktdynamiek gedetecteerd"),
    ("OFF001", "SKU", "hybrid", "INTERNAL_QUESTION_MARK","PRICING_POWER_STAR",   "Omzetgroei +34% afgelopen kwartaal"),
    ("FRN001", "SKU", "hybrid", "INTERNAL_QUESTION_MARK","LOW_PRIORITY_DOG",     "Lage verkoop + geen groei"),
    ("INK002", "SKU", "internal","INTERNAL_CASH_COW",    "INTERNAL_STAR",        "Huismerk volume gestegen na campagne"),
]
for (eid, etype, ctype, oud, nieuw, reden) in history_items:
    db.add(FactBcgHistory(
        entity_id=eid, entity_type=etype,
        classification_type=ctype,
        old_classification=oud, new_classification=nieuw,
        changed_at=datetime.utcnow() - __import__('datetime').timedelta(days=7),
        reason=reden,
    ))
    print(f"  ✓ BCG History: {eid} {oud} → {nieuw}")

db.commit()
db.close()
print("\n✅ BCG backfill voltooid.")
