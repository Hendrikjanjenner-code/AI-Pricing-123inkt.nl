"""
Cross-sell Engine
Detecteert cross-sell patronen en berekent incrementele margebijdrage.
"""
from __future__ import annotations
from datetime import date
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from models import DimProduct, FactBasketAffinity


def detect_cross_sell_patterns(sku_id: str, db: Session, top_n: int = 5) -> List[Dict[str, Any]]:
    """
    Detecteer cross-sell patronen voor een SKU op basis van basket affinity.
    Returns lijst van gerelateerde SKU's met affinity-score.
    """
    affinities = (
        db.query(FactBasketAffinity)
        .filter(FactBasketAffinity.sku_id_a == sku_id)
        .order_by(FactBasketAffinity.affinity_score.desc())
        .limit(top_n)
        .all()
    )

    # Ook andere kant checken (B→A)
    affinities_rev = (
        db.query(FactBasketAffinity)
        .filter(FactBasketAffinity.sku_id_b == sku_id)
        .order_by(FactBasketAffinity.affinity_score.desc())
        .limit(top_n)
        .all()
    )

    resultaten = []
    gezien = set()

    for aff in list(affinities) + list(affinities_rev):
        partner_sku = aff.sku_id_b if aff.sku_id_a == sku_id else aff.sku_id_a
        if partner_sku in gezien:
            continue
        gezien.add(partner_sku)

        partner = db.query(DimProduct).filter(DimProduct.sku_id == partner_sku).first()
        if not partner:
            continue

        sp = float(partner.current_price or 0)
        cp = float(partner.cost_price or sp * 0.6)
        partner_margin = (sp - cp) if sp > 0 else 0

        resultaten.append({
            "partner_sku_id": partner_sku,
            "partner_naam": partner.product_name,
            "partner_categorie": partner.category,
            "affinity_score": float(aff.affinity_score or 0),
            "co_purchase_rate": float(aff.co_purchase_rate or 0) if hasattr(aff, 'co_purchase_rate') else 0,
            "partner_prijs": sp,
            "partner_marge_eur": round(partner_margin, 4),
        })

    return sorted(resultaten, key=lambda x: x["affinity_score"], reverse=True)[:top_n]


def calculate_attach_rate(
    sku_id: str,
    db: Session,
) -> float:
    """
    Schat attach-rate: % bestellingen waar dit SKU samen met een ander product is.
    Gebaseerd op basket affinity data.
    """
    count = db.query(FactBasketAffinity).filter(
        (FactBasketAffinity.sku_id_a == sku_id) | (FactBasketAffinity.sku_id_b == sku_id)
    ).count()

    if count == 0:
        return 0.15   # baseline
    return min(0.95, 0.15 + count * 0.08)


def calculate_incremental_margin_from_cross_sell(
    cross_sell_patterns: List[Dict[str, Any]],
    avg_attach_rate: float,
) -> float:
    """Bereken totale incrementele marge uit cross-sell patronen."""
    if not cross_sell_patterns:
        return 0.0
    total = sum(
        p["partner_marge_eur"] * p["affinity_score"] * avg_attach_rate
        for p in cross_sell_patterns
    )
    return round(total, 4)


def get_cross_sell_recommendations(sku_id: str, db: Session) -> Dict[str, Any]:
    """Volledig cross-sell advies voor één SKU."""
    prod = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not prod:
        return {"error": "SKU niet gevonden"}

    patterns = detect_cross_sell_patterns(sku_id, db)
    attach_rate = calculate_attach_rate(sku_id, db)
    inc_margin = calculate_incremental_margin_from_cross_sell(patterns, attach_rate)

    sp = float(prod.current_price or 0)
    cp = float(prod.cost_price or sp * 0.6)
    direct_margin = (sp - cp) if sp > 0 else 0

    cross_sell_amplification = inc_margin / max(0.01, direct_margin) if direct_margin > 0 else 0

    if cross_sell_amplification >= 0.50:
        advies = "CROSS_SELL_CAMPAGNE_PRIORITEIT"
        toelichting = f"Cross-sell genereert {cross_sell_amplification*100:.0f}% extra marge boven directe SKU-marge. Actief promoten via bundels of aanbevelingen."
    elif cross_sell_amplification >= 0.20:
        advies = "CROSS_SELL_KANS"
        toelichting = f"Significante cross-sell kans aanwezig (+{cross_sell_amplification*100:.0f}% marge-amplificatie). Upsell flow optimaliseren."
    else:
        advies = "BEPERKTE_CROSS_SELL"
        toelichting = "Beperkte cross-sell waarde gedetecteerd. Focus op directe marge-optimalisatie."

    return {
        "sku_id": sku_id,
        "naam": prod.product_name,
        "categorie": prod.category,
        "attach_rate": round(attach_rate, 4),
        "incrementele_marge": inc_margin,
        "cross_sell_amplificatie_pct": round(cross_sell_amplification * 100, 1),
        "directe_marge_eur": round(direct_margin, 4),
        "advies": advies,
        "toelichting_nl": toelichting,
        "top_cross_sell_skus": patterns,
    }


def get_cross_sell_overview(db: Session) -> Dict[str, Any]:
    """Overzicht cross-sell kansen voor alle SKU's."""
    prods = db.query(DimProduct).filter(DimProduct.lifecycle_status == "active").all()

    resultaten = []
    for prod in prods:
        patterns = detect_cross_sell_patterns(prod.sku_id, db, top_n=3)
        if not patterns:
            continue
        attach_rate = calculate_attach_rate(prod.sku_id, db)
        inc_margin = calculate_incremental_margin_from_cross_sell(patterns, attach_rate)
        sp = float(prod.current_price or 0)
        cp = float(prod.cost_price or sp * 0.6)
        direct_margin = (sp - cp) if sp > 0 else 0
        amplificatie = inc_margin / max(0.01, direct_margin) if direct_margin > 0 else 0

        resultaten.append({
            "sku_id": prod.sku_id,
            "naam": prod.product_name,
            "categorie": prod.category,
            "attach_rate": round(attach_rate, 4),
            "incrementele_marge": round(inc_margin, 4),
            "cross_sell_amplificatie_pct": round(amplificatie * 100, 1),
            "aantal_cross_sell_skus": len(patterns),
            "top_partner": patterns[0]["partner_naam"] if patterns else None,
        })

    resultaten.sort(key=lambda x: x["incrementele_marge"], reverse=True)

    return {
        "totaal_skus_met_cross_sell": len(resultaten),
        "totale_incrementele_marge": round(sum(r["incrementele_marge"] for r in resultaten), 2),
        "skus": resultaten,
    }
