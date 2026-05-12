"""
Product Matching Engine — Module 2
Koppelt concurrent-producten aan eigen SKU's op basis van meerdere signalen.
Een slechte match mag nooit pricing beïnvloeden.
"""
import re
import math
from datetime import datetime
from typing import Optional

# ── Match types ─────────────────────────────────────────────────────────────
EXACT_MATCH = "EXACT_MATCH"
STRONG_MATCH = "STRONG_MATCH"
PROBABLE_MATCH = "PROBABLE_MATCH"
FUNCTIONAL_MATCH = "FUNCTIONAL_MATCH"
NO_MATCH = "NO_MATCH"

# ── Reason codes ────────────────────────────────────────────────────────────
MATCH_EXACT_EAN = "MATCH_EXACT_EAN"
MATCH_EXACT_MPN = "MATCH_EXACT_MPN"
MATCH_STRONG_TITLE_BRAND = "MATCH_STRONG_TITLE_BRAND"
MATCH_PACK_SIZE_DIFFERENCE = "MATCH_PACK_SIZE_DIFFERENCE"
MATCH_LOW_CONFIDENCE = "MATCH_LOW_CONFIDENCE"
MATCH_MANUAL_OVERRIDE = "MATCH_MANUAL_OVERRIDE"
MATCH_REJECTED = "MATCH_REJECTED"


def _tokenize(text: str) -> set[str]:
    """Verwijder stopwoorden en splits op tokens."""
    stopwords = {"de", "het", "een", "van", "voor", "met", "aan", "op", "in", "bij",
                 "en", "of", "als", "the", "a", "an", "for", "with", "of"}
    tokens = re.findall(r"\b\w+\b", text.lower())
    return {t for t in tokens if t not in stopwords and len(t) > 1}


def calculate_title_similarity(title_a: str, title_b: str) -> float:
    """Jaccard-gelijkenis tussen twee producttitels."""
    if not title_a or not title_b:
        return 0.0
    tokens_a = _tokenize(title_a)
    tokens_b = _tokenize(title_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return round(len(intersection) / len(union), 4)


def calculate_pack_size_similarity(pack_a: Optional[str], pack_b: Optional[str]) -> float:
    """
    Vergelijk verpakkingsgroottes.
    Geeft 1.0 bij overeenkomst, 0.5 bij ontbrekende info, 0.0 bij afwijking.
    """
    if not pack_a or not pack_b:
        return 0.5  # Onbekend — voorzichtig
    def _extract_qty(s: str) -> Optional[float]:
        m = re.search(r"(\d+(?:[.,]\d+)?)", s)
        return float(m.group(1).replace(",", ".")) if m else None
    qty_a = _extract_qty(pack_a)
    qty_b = _extract_qty(pack_b)
    if qty_a is None or qty_b is None:
        return 0.5
    if math.isclose(qty_a, qty_b, rel_tol=0.01):
        return 1.0
    return 0.0


def calculate_brand_similarity(brand_a: Optional[str], brand_b: Optional[str]) -> float:
    """Merk-overeenkomst: exacte match of deelmatch."""
    if not brand_a or not brand_b:
        return 0.5
    a = brand_a.lower().strip()
    b = brand_b.lower().strip()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.8
    return 0.0


def calculate_identifier_match_score(
    own_ean: Optional[str],
    own_mpn: Optional[str],
    comp_ean: Optional[str],
    comp_mpn: Optional[str],
) -> tuple[float, str]:
    """
    Vergelijk EAN en MPN identifiers.
    Geeft (score, reason_code) terug.
    """
    if own_ean and comp_ean and own_ean.strip() == comp_ean.strip():
        return 1.0, MATCH_EXACT_EAN
    if own_mpn and comp_mpn and own_mpn.strip().lower() == comp_mpn.strip().lower():
        return 0.95, MATCH_EXACT_MPN
    return 0.0, ""


def calculate_final_match_confidence(
    identifier_score: float,
    title_similarity: float,
    brand_similarity: float,
    pack_size_similarity: float,
    category_match: bool = True,
) -> tuple[float, str, str]:
    """
    Bereken eindconfidence en bepaal match type + primaire reden.
    Geeft (confidence, match_type, reason_code) terug.
    """
    # Exacte identifier → direct EXACT_MATCH
    if identifier_score >= 1.0:
        return 1.0, EXACT_MATCH, MATCH_EXACT_EAN
    if identifier_score >= 0.95:
        return 0.97, EXACT_MATCH, MATCH_EXACT_MPN

    # Gewogen score zonder identifier
    gewogen = (
        title_similarity * 0.45
        + brand_similarity * 0.25
        + pack_size_similarity * 0.20
        + (0.10 if category_match else 0.0)
    )

    # Verpakkingswaarschuwing
    pack_warning = pack_size_similarity == 0.0

    if gewogen >= 0.80 and brand_similarity >= 0.8:
        return round(gewogen, 3), STRONG_MATCH, MATCH_STRONG_TITLE_BRAND
    if gewogen >= 0.60:
        code = MATCH_PACK_SIZE_DIFFERENCE if pack_warning else MATCH_STRONG_TITLE_BRAND
        return round(gewogen, 3), PROBABLE_MATCH, code
    if gewogen >= 0.35 and category_match:
        return round(gewogen, 3), FUNCTIONAL_MATCH, MATCH_LOW_CONFIDENCE
    return round(gewogen, 3), NO_MATCH, MATCH_REJECTED


def explain_match(
    own_sku: dict,
    competitor_offer: dict,
    identifier_score: float,
    identifier_reason: str,
    title_sim: float,
    brand_sim: float,
    pack_sim: float,
    final_confidence: float,
    match_type: str,
) -> dict:
    """Genereer een voor mensen leesbare uitleg van de match-beslissing."""
    uitleg = []
    if identifier_score >= 0.95:
        uitleg.append(f"Exacte identifier-match ({identifier_reason}): score {identifier_score:.2f}")
    else:
        uitleg.append(f"Geen exacte EAN/MPN-match")
    uitleg.append(f"Titelgelijkenis (Jaccard): {title_sim:.2f}")
    uitleg.append(f"Merkgelijkenis: {brand_sim:.2f}")
    uitleg.append(f"Verpakkingsgelijkenis: {pack_sim:.2f}")
    if pack_sim == 0.0:
        uitleg.append("⚠️ WAARSCHUWING: verpakkingsgrootte verschilt — prijsvergelijking niet direct")

    return {
        "eigen_sku": own_sku.get("sku_id"),
        "concurrent_sku": competitor_offer.get("competitor_sku"),
        "match_type": match_type,
        "confidence": final_confidence,
        "uitleg": uitleg,
        "pack_size_warning": pack_sim == 0.0,
    }


def match_competitor_offer_to_sku(
    own_sku: dict,
    competitor_offer: dict,
) -> dict:
    """
    Hoofdfunctie: match één concurrent-aanbod aan een eigen SKU.

    own_sku verwacht: sku_id, product_name, brand, ean, mpn, category, pack_size
    competitor_offer verwacht: competitor_sku, product_title, brand, ean, mpn, pack_size, category
    """
    id_score, id_reason = calculate_identifier_match_score(
        own_sku.get("ean"), own_sku.get("mpn"),
        competitor_offer.get("ean"), competitor_offer.get("mpn"),
    )
    title_sim = calculate_title_similarity(
        own_sku.get("product_name", ""),
        competitor_offer.get("product_title", ""),
    )
    brand_sim = calculate_brand_similarity(
        own_sku.get("brand"), competitor_offer.get("brand")
    )
    pack_sim = calculate_pack_size_similarity(
        own_sku.get("pack_size"), competitor_offer.get("pack_size")
    )
    cat_match = (
        own_sku.get("category", "").lower() == competitor_offer.get("category", "").lower()
        if own_sku.get("category") and competitor_offer.get("category")
        else True
    )

    confidence, match_type, reason = calculate_final_match_confidence(
        id_score, title_sim, brand_sim, pack_sim, cat_match
    )

    uitleg = explain_match(
        own_sku, competitor_offer, id_score, id_reason,
        title_sim, brand_sim, pack_sim, confidence, match_type
    )

    return {
        "own_sku_id": own_sku.get("sku_id"),
        "competitor_offer_id": competitor_offer.get("scrape_id"),
        "competitor_sku": competitor_offer.get("competitor_sku"),
        "match_type": match_type,
        "match_confidence": confidence,
        "match_reason": reason,
        "pack_size_warning": pack_sim == 0.0,
        "manual_override": False,
        "uitleg": uitleg,
    }


def create_manual_match_override(
    db,
    own_sku_id: str,
    competitor_id: int,
    competitor_sku: str,
    competitor_url: str,
    approved_by: str,
) -> dict:
    """Registreer een handmatige koppeling door een gebruiker."""
    from models import ProductMatch
    match = ProductMatch(
        own_sku_id=own_sku_id,
        competitor_id=competitor_id,
        competitor_sku=competitor_sku,
        competitor_url=competitor_url,
        match_type=EXACT_MATCH,
        match_confidence=1.0,
        match_reason=MATCH_MANUAL_OVERRIDE,
        pack_size_warning=False,
        manual_override=True,
        approved_by=approved_by,
        approved_at=datetime.utcnow(),
        active=True,
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return {
        "match_id": match.match_id,
        "status": "aangemaakt",
        "own_sku_id": own_sku_id,
        "competitor_sku": competitor_sku,
        "approved_by": approved_by,
    }
