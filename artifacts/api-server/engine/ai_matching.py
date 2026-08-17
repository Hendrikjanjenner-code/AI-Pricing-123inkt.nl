"""
AI Matching Engine.

Matcht eigen SKU's aan concurrent-aanbod op basis van:
- EAN / MPN / OEM-code exacte match
- Merk + producttype combinatie
- Prijssegment overlap
- Functionele beschrijving (trefwoord-overlap)

Produces match_type (Exact / Sterk / Functioneel / Categorie_Alternatief / Geen_Match),
confidence (0–1) en Nederlandse uitleg.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
import models


MATCH_TYPES = [
    "Exact",
    "Sterk",
    "Functioneel",
    "Categorie_Alternatief",
    "Geen_Match",
]

MATCH_TYPE_COLORS = {
    "Exact":                "#10b981",  # groen
    "Sterk":                "#3b82f6",  # blauw
    "Functioneel":          "#f59e0b",  # amber
    "Categorie_Alternatief":"#f97316",  # oranje
    "Geen_Match":           "#ef4444",  # rood
}


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _word_overlap(a: str, b: str) -> float:
    """Jaccard-overlap op woorden."""
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


def match_sku_to_competitor(
    own_product: models.DimProduct,
    competitor_name: str,
    competitor_price: float,
    competitor_sku: Optional[str] = None,
    competitor_url: Optional[str] = None,
    competitor_ean: Optional[str] = None,
    competitor_mpn: Optional[str] = None,
    competitor_brand: Optional[str] = None,
    competitor_product_name: Optional[str] = None,
    own_attributes: Optional[dict] = None,
) -> dict:
    """
    Voer een AI-matching uit voor één eigen SKU t.o.v. één concurrent-aanbod.

    Returns dict met match_type, confidence, explanation_nl en signalen.
    """
    signals: dict[str, bool] = {
        "ean_match": False,
        "mpn_match": False,
        "oem_match": False,
        "brand_match": False,
        "product_type_match": False,
        "price_segment_match": False,
        "attribute_match": False,
    }

    # PIM-verrijkte attributen (§23/§12): EAN uit de contentlaag + attribuut-
    # waarden die in de concurrent-productnaam terugkomen versterken de match.
    own_attributes = own_attributes or {}
    pim_ean = own_attributes.get("ean")
    if competitor_ean and pim_ean and _normalize(competitor_ean) == _normalize(pim_ean):
        signals["ean_match"] = True

    # EAN match
    if competitor_ean and own_product.oem_code:
        if _normalize(competitor_ean) == _normalize(own_product.oem_code):
            signals["ean_match"] = True

    # MPN / OEM match
    if competitor_mpn and own_product.oem_code:
        if _normalize(competitor_mpn) == _normalize(own_product.oem_code):
            signals["mpn_match"] = True
            signals["oem_match"] = True

    # Merk match
    if competitor_brand and own_product.brand:
        if _normalize(competitor_brand) == _normalize(own_product.brand):
            signals["brand_match"] = True

    # Product-type (keyword overlap in naam, verrijkt met PIM-attributen)
    if competitor_product_name and own_product.product_name:
        own_text = own_product.product_name
        enrich_parts = [str(v) for k, v in own_attributes.items()
                        if v and k in ("product_type", "material", "color",
                                       "paper_size", "description")]
        if enrich_parts:
            own_text = own_text + " " + " ".join(enrich_parts)
        overlap = _word_overlap(competitor_product_name, own_text)
        if overlap >= 0.4:
            signals["product_type_match"] = True

    # Attribuut-match: concrete PIM-attribuutwaarden (kleur, materiaal,
    # formaat, grammage) die letterlijk in de concurrent-naam terugkomen.
    if competitor_product_name and own_attributes:
        comp_norm = _normalize(competitor_product_name)
        hits = 0
        for k in ("color", "material", "paper_size", "paper_weight_gsm", "sheets_per_pack"):
            v = own_attributes.get(k)
            if v and len(_normalize(str(v))) >= 2 and _normalize(str(v)) in comp_norm:
                hits += 1
        if hits >= 1:
            signals["attribute_match"] = True

    # Prijssegment
    if own_product.current_price and competitor_price:
        ratio = competitor_price / float(own_product.current_price)
        if 0.7 <= ratio <= 1.3:
            signals["price_segment_match"] = True

    # Bepaal match-type en confidence
    true_signals = sum(signals.values())

    if signals["ean_match"] or signals["oem_match"]:
        match_type = "Exact"
        confidence = 0.95
        explanation = (
            f"Exacte EAN/OEM-code-overeenkomst met {competitor_name}. "
            "Dit is hetzelfde product."
        )
    elif signals["brand_match"] and signals["product_type_match"] and signals["price_segment_match"]:
        match_type = "Sterk"
        confidence = 0.85 if signals["attribute_match"] else 0.80
        explanation = (
            f"Zelfde merk ({own_product.brand}), vergelijkbaar producttype "
            f"en vergelijkbaar prijssegment bij {competitor_name}."
        )
    elif signals["brand_match"] and signals["product_type_match"]:
        match_type = "Sterk"
        confidence = 0.75 if signals["attribute_match"] else 0.70
        explanation = (
            f"Zelfde merk en vergelijkbaar producttype bij {competitor_name}, "
            "maar prijssegment wijkt licht af."
        )
    elif signals["product_type_match"] and signals["price_segment_match"]:
        match_type = "Functioneel"
        confidence = 0.62 if signals["attribute_match"] else 0.55
        explanation = (
            f"Functioneel vergelijkbaar product bij {competitor_name}: "
            "zelfde toepassingstype en prijsklasse, maar ander merk."
        )
        if signals["attribute_match"]:
            explanation += " Productattributen (PIM) komen overeen."
    elif signals["brand_match"] or signals["product_type_match"]:
        match_type = "Categorie_Alternatief"
        confidence = 0.35
        explanation = (
            f"Categorie-alternatief bij {competitor_name}: "
            "beperkte productovereenkomst, maar zit in hetzelfde assortimentsgebied."
        )
    else:
        match_type = "Geen_Match"
        confidence = 0.10
        explanation = (
            f"Geen significante overeenkomst gevonden met {competitor_name}. "
            "Onvoldoende gemeenschappelijke signalen."
        )

    own_price = float(own_product.current_price) if own_product.current_price else None
    price_diff_pct = (
        round((competitor_price / own_price - 1) * 100, 2)
        if own_price and competitor_price else None
    )

    return {
        "match_type": match_type,
        "confidence": round(confidence, 3),
        "explanation_nl": explanation,
        "price_diff_pct": price_diff_pct,
        **signals,
    }


def run_matching_for_all(db: Session, lookback_days: int = 14) -> int:
    """
    Voer matching uit voor alle eigen SKU's × alle recent beschikbare
    concurrent-prijzen. Slaat resultaten op in ai_match_result.
    """
    since = date.today() - timedelta(days=lookback_days)
    comp_prices = (
        db.query(models.FactCompetitorPriceDaily)
        .filter(models.FactCompetitorPriceDaily.date >= since)
        .order_by(
            models.FactCompetitorPriceDaily.sku_id,
            models.FactCompetitorPriceDaily.competitor_name,
            models.FactCompetitorPriceDaily.date.desc(),
        )
        .all()
    )

    # Deduplicate: keep most recent per sku_id × competitor
    seen: set = set()
    deduped = []
    for row in comp_prices:
        key = (row.sku_id, row.competitor_name)
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    products = {
        p.sku_id: p
        for p in db.query(models.DimProduct).all()
    }

    # PIM-verrijkte attributen per SKU (§23): code -> waarde
    attr_defs = {d.id: d.code for d in db.query(models.PimAttributeDefinition).all()}
    pim_attrs: dict[str, dict] = {}
    if attr_defs:
        for v in db.query(models.PimAttributeValue).all():
            code = attr_defs.get(v.attribute_id)
            if code and v.value:
                pim_attrs.setdefault(v.sku_id, {})[code] = v.value

    count = 0
    for row in deduped:
        own_product = products.get(row.sku_id)
        if not own_product or not row.price:
            continue

        result = match_sku_to_competitor(
            own_product=own_product,
            competitor_name=row.competitor_name,
            competitor_price=float(row.price),
            competitor_url=row.url,
            own_attributes=pim_attrs.get(row.sku_id),
        )

        # Upsert
        existing = (
            db.query(models.AiMatchResult)
            .filter(
                models.AiMatchResult.own_sku_id == row.sku_id,
                models.AiMatchResult.competitor_name == row.competitor_name,
            )
            .first()
        )
        if not existing:
            existing = models.AiMatchResult(
                own_sku_id=row.sku_id,
                competitor_name=row.competitor_name,
            )
            db.add(existing)

        existing.competitor_url = row.url
        existing.match_type = result["match_type"]
        existing.confidence = result["confidence"]
        existing.explanation_nl = result["explanation_nl"]
        existing.ean_match = result["ean_match"]
        existing.mpn_match = result["mpn_match"]
        existing.oem_match = result["oem_match"]
        existing.brand_match = result["brand_match"]
        existing.product_type_match = result["product_type_match"]
        existing.price_segment_match = result["price_segment_match"]
        existing.competitor_price = row.price
        existing.own_price = own_product.current_price
        existing.price_diff_pct = result["price_diff_pct"]
        existing.run_date = date.today()
        count += 1

    db.commit()
    return count
