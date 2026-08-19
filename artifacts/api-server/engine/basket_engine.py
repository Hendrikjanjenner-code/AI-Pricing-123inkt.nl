"""
Basket Intelligence Engine (§16) — associatieanalyse op basket-facts.

Bouwt uit FactBasketAffinity + productdata: product-associaties,
frequently-bought-together, cross-sell/upsell, basket fillers en marge per
mandje. Resultaten worden in basket_associations opgeslagen, gebruikt door
Pricing, Promotion en de Decision/Opportunity Engine, en gepubliceerd als
IntelligenceSignals.
"""
from __future__ import annotations
from datetime import date
from typing import Any, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from engine.signal_publisher import publish_signal, resolve_shop_id, auto_resolve_signals
from engine.model_governance import ensure_active_model, record_run_metrics, get_active_config

# Default modelconfiguratie — vastgelegd per registry-versie (governance §54).
BASKET_DEFAULT_CONFIG = {
    # Basket filler: goedkoop, hoge attach-kans — vult mandjes zonder risico.
    "filler_max_price": 15.0,
    "upsell_price_ratio": 1.25,   # consequent ≥ 25% duurder dan antecedent = upsell
    "bundle_min_lift": 1.5,       # sterke lift = bundelkandidaat
    "signal_top_n": 5,
}


def _relation_type(a: models.DimProduct | None, b: models.DimProduct | None, lift: float, cfg: dict) -> str:
    price_a = float(a.current_price or 0) if a else 0.0
    price_b = float(b.current_price or 0) if b else 0.0
    if price_b and price_b <= cfg["filler_max_price"] and price_a > price_b:
        return "basket_filler"
    if price_a and price_b and price_b >= price_a * cfg["upsell_price_ratio"]:
        return "upsell"
    if lift >= cfg["bundle_min_lift"]:
        return "bundle"
    return "cross_sell"


def _margin_eur(p: models.DimProduct | None) -> float:
    if not p or p.current_price is None:
        return 0.0
    return float(p.current_price) - float(p.cost_price or 0)


def run_basket_engine(db: Session, run_date: date | None = None,
                      shop_id: int | None = None) -> Dict[str, Any]:
    """Herbereken de basket-associaties voor één shop uit fact_basket_affinity."""
    run_date = run_date or date.today()
    sid = resolve_shop_id(db, shop_id)
    model = ensure_active_model(db, "basket", description="Basket Intelligence associatie-model",
                                default_config=BASKET_DEFAULT_CONFIG)
    cfg = get_active_config(db, "basket", BASKET_DEFAULT_CONFIG)

    rows = db.query(models.FactBasketAffinity).filter(
        models.FactBasketAffinity.shop_id == sid
    ).all()
    if not rows:
        record_run_metrics(db, "basket", {"associations": 0, "skus": 0, "status": "no_data",
                                          "shop_id": sid})
        db.commit()
        return {"associations": 0, "skus": 0, "run_date": str(run_date), "shop_id": sid,
                "detail": "Geen basket-affiniteitsdata aanwezig (upload basket-affinity)."}

    products = {p.sku_id: p for p in db.query(models.DimProduct).filter(
        models.DimProduct.shop_id == sid).all()}
    total_co = sum(r.co_purchase_count or 0 for r in rows) or 1
    # frequentie per SKU (als consequent) voor lift-berekening
    freq: Dict[str, int] = {}
    per_a: Dict[str, int] = {}
    for r in rows:
        freq[r.sku_id_b] = freq.get(r.sku_id_b, 0) + (r.co_purchase_count or 0)
        per_a[r.sku_id_a] = per_a.get(r.sku_id_a, 0) + (r.co_purchase_count or 0)

    # Vervang de associaties van deze run_date voor deze shop (idempotent herdraaien)
    db.query(models.BasketAssociation).filter(
        models.BasketAssociation.run_date == run_date,
        models.BasketAssociation.shop_id == sid,
    ).delete(synchronize_session=False)

    created = 0
    skus = set()
    for r in rows:
        count = r.co_purchase_count or 0
        if count <= 0:
            continue
        a = products.get(r.sku_id_a)
        b = products.get(r.sku_id_b)
        support = count / total_co
        conf = count / max(1, per_a.get(r.sku_id_a, count))
        p_b = (freq.get(r.sku_id_b, 0) / total_co) or (1 / total_co)
        lift = round(conf / p_b, 3) if p_b else 0.0
        rel = _relation_type(a, b, lift, cfg)
        bundle_margin = _margin_eur(a) + _margin_eur(b)
        avg_basket = (float(a.current_price or 0) if a else 0) + (float(b.current_price or 0) if b else 0)

        db.add(models.BasketAssociation(
            run_date=run_date,
            shop_id=sid,
            antecedent_sku=r.sku_id_a,
            consequent_sku=r.sku_id_b,
            antecedent_name=a.product_name if a else None,
            consequent_name=b.product_name if b else None,
            support=round(support, 5),
            confidence=round(min(1.0, conf), 4),
            lift=lift,
            co_purchase_count=count,
            relation_type=rel,
            bundle_margin_eur=round(bundle_margin, 4),
            avg_basket_value=round(avg_basket, 4),
            explanation_nl=(
                f"{count}× samen gekocht; confidence {conf:.0%}, lift {lift:.2f}. "
                f"Geclassificeerd als {rel.replace('_', ' ')}."
            ),
            model_version=model.version,
        ))
        created += 1
        skus.update([r.sku_id_a, r.sku_id_b])

    # Signalen: sterkste bundelkansen
    top = (
        sorted(rows, key=lambda r: (r.affinity_score or 0), reverse=True)[:int(cfg["signal_top_n"])]
    )
    signaled_antecedents: set[str] = set()
    for r in top:
        a = products.get(r.sku_id_a)
        b = products.get(r.sku_id_b)
        if not a or not b:
            continue
        # Eén signaal per antecedent-SKU per run: de dedupe-sleutel is per
        # entity (sku_id_a); een tweede publish in dezelfde run zou de
        # unieke actieve-signaal-constraint schenden. Rijen zijn al op
        # affinity gesorteerd, dus de sterkste associatie wint.
        if r.sku_id_a in signaled_antecedents:
            continue
        signaled_antecedents.add(r.sku_id_a)
        publish_signal(
            db,
            shop_id=sid,
            engine="basket",
            signal_type="strong_product_association",
            entity_type="sku",
            entity_id=r.sku_id_a,
            entity_name=a.product_name,
            severity="info",
            direction="positive",
            confidence=min(1.0, float(r.affinity_score or 0.5)),
            explanation=(
                f"Sterke winkelmand-associatie tussen {a.product_name} en "
                f"{b.product_name} ({r.co_purchase_count or 0}× samen gekocht). "
                f"Bundel- of cross-sell-kans met €{_margin_eur(a) + _margin_eur(b):.2f} marge per mandje."
            ),
            evidence={
                "paired_sku": r.sku_id_b,
                "co_purchase_count": r.co_purchase_count or 0,
                "affinity_score": float(r.affinity_score or 0),
                "bundle_margin_eur": round(_margin_eur(a) + _margin_eur(b), 2),
            },
            sources=["fact_basket_affinity", "dim_product"],
            suggested_action="Bied deze producten als bundel of cross-sell aan",
            model_version=model.version,
        )

    # Auto-resolve: associatiesignalen die niet meer in de top-selectie van
    # deze run zitten worden op resolved gezet. Bij een lege bron (geen
    # affiniteitsdata) komen we hier niet — de early return hierboven bewaakt
    # dat "geen data" nooit tot resolutie leidt.
    auto_resolve_signals(
        db, engine="basket",
        still_active={("strong_product_association", a) for a in signaled_antecedents},
        signal_types=["strong_product_association"], entity_type="sku",
        shop_id=sid)

    record_run_metrics(db, "basket", {"associations": created, "skus": len(skus), "shop_id": sid})
    db.commit()
    return {"associations": created, "skus": len(skus), "run_date": str(run_date), "shop_id": sid}


def get_basket_association_dashboard(db: Session, shop_id: int | None = None) -> Dict[str, Any]:
    """Dashboard: associaties, FBT, cross-sell/upsell, fillers, marge per mandje."""
    sid = resolve_shop_id(db, shop_id)
    latest = db.query(func.max(models.BasketAssociation.run_date)).filter(
        models.BasketAssociation.shop_id == sid).scalar()
    if not latest:
        return {"run_date": None, "shop_id": sid, "totaal_associaties": 0, "associaties": [],
                "per_type": {}, "gemiddelde_mandmarge": 0}

    assocs = (
        db.query(models.BasketAssociation)
        .filter(models.BasketAssociation.run_date == latest,
                models.BasketAssociation.shop_id == sid)
        .order_by(models.BasketAssociation.lift.desc())
        .limit(500)
        .all()
    )
    per_type: Dict[str, int] = {}
    for a in assocs:
        per_type[a.relation_type or "cross_sell"] = per_type.get(a.relation_type or "cross_sell", 0) + 1

    margins = [float(a.bundle_margin_eur or 0) for a in assocs if a.bundle_margin_eur is not None]
    return {
        "run_date": str(latest),
        "shop_id": sid,
        "totaal_associaties": len(assocs),
        "per_type": per_type,
        "gemiddelde_mandmarge": round(sum(margins) / len(margins), 2) if margins else 0,
        "associaties": [
            {
                "id": a.id,
                "antecedent_sku": a.antecedent_sku,
                "antecedent_naam": a.antecedent_name,
                "consequent_sku": a.consequent_sku,
                "consequent_naam": a.consequent_name,
                "support": float(a.support or 0),
                "confidence": float(a.confidence or 0),
                "lift": float(a.lift or 0),
                "samen_gekocht": a.co_purchase_count or 0,
                "relatie_type": a.relation_type,
                "bundel_marge_eur": float(a.bundle_margin_eur or 0),
                "gem_mandwaarde": float(a.avg_basket_value or 0),
                "toelichting": a.explanation_nl,
            }
            for a in assocs
        ],
    }


def get_frequently_bought_together(db: Session, sku_id: str, limit: int = 10,
                                   shop_id: int | None = None) -> list[dict]:
    """FBT voor één SKU — gebruikt door Pricing, Promotion en Decision Engine."""
    sid = resolve_shop_id(db, shop_id)
    latest = db.query(func.max(models.BasketAssociation.run_date)).filter(
        models.BasketAssociation.shop_id == sid).scalar()
    if not latest:
        return []
    rows = (
        db.query(models.BasketAssociation)
        .filter(
            models.BasketAssociation.run_date == latest,
            models.BasketAssociation.shop_id == sid,
            models.BasketAssociation.antecedent_sku == sku_id,
        )
        .order_by(models.BasketAssociation.confidence.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "sku_id": a.consequent_sku,
            "naam": a.consequent_name,
            "confidence": float(a.confidence or 0),
            "lift": float(a.lift or 0),
            "relatie_type": a.relation_type,
            "samen_gekocht": a.co_purchase_count or 0,
        }
        for a in rows
    ]
