"""
Competition Rankings Engine (masterprompt §9 en §11).

Berekent per concurrent de drie gestandaardiseerde scores:
1. Competition Relevance — hoe relevant is deze concurrent als geheel
   (functionele overlap, assortimentsdekking, categorierelevantie)
2. Price Relevance — hoe relevant is zijn prijszetting voor ons
   (pricing-relevantie per categorie, prijswijzigingsfrequentie, prijsniveau)
3. Influence — hoeveel invloed heeft hij op onze conversie/prijszetting
   (gemiddelde CIS-score over alle SKU's)

En publiceert rankings (overall + per categorie) met vorige rank en trend.
Elke score krijgt uitleg + evidence — geen score zonder uitleg (§64.9-10).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

import models
from engine.competitor_influence import profile_baseline_influence

MODEL_VERSION = "rankings-v1.0.0"

# Gewichten voor de gecombineerde score
W_COMPETITION_RELEVANCE = 0.40
W_PRICE_RELEVANCE = 0.30
W_INFLUENCE = 0.30


def _avg(values: list[float]) -> float:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def run_competitor_rankings(db: Session, ref_date: date | None = None,
                             shop_id: int | None = None) -> int:
    """
    Bereken en persisteer competitor rankings (overall + per categorie).
    Retourneert het aantal geschreven ranking-rijen.

    shop_id (optioneel): beperk de run tot één shop (snel bij testen/gefocuste runs).
    """
    today = ref_date or date.today()
    if shop_id is not None:
        shop_ids = [shop_id]
    else:
        shop_ids = [s for (s,) in db.query(models.DimProduct.shop_id).distinct().all()
                    if s is not None]
    total = 0
    for sid in shop_ids:
        total += _run_for_shop(db, today, sid)
    db.commit()
    return total


def _run_for_shop(db: Session, today: date, sid: int) -> int:
    """Rankings voor één shop: alle bronnen (profielen, categoriescores, CIS)
    en de output zijn shop-scoped zodat shops elkaar niet vervuilen."""
    profiles = {p.competitor_name: p for p in
                db.query(models.CompetitorProfile)
                .filter(models.CompetitorProfile.shop_id == sid).all()}
    cat_rows = (db.query(models.CategoryCompetitorRelevance)
                .filter(models.CategoryCompetitorRelevance.shop_id == sid).all())
    # CIS is SKU-gekeyd: shop afleiden via de eigenaar van de SKU
    cis_rows = (db.query(models.CompetitorInfluenceScore)
                .join(models.DimProduct,
                      models.DimProduct.sku_id == models.CompetitorInfluenceScore.sku_id)
                .filter(models.DimProduct.shop_id == sid).all())

    if not profiles and not cat_rows and not cis_rows:
        return 0

    # Aggregaties per concurrent
    cat_by_comp: dict[str, list[models.CategoryCompetitorRelevance]] = {}
    for r in cat_rows:
        cat_by_comp.setdefault(r.competitor_name, []).append(r)

    cis_by_comp: dict[str, list[float]] = {}
    cis_count_by_comp: dict[str, int] = {}
    for r in cis_rows:
        cis_by_comp.setdefault(r.competitor_name, []).append(float(r.cis_score or 0))
        cis_count_by_comp[r.competitor_name] = cis_count_by_comp.get(r.competitor_name, 0) + 1

    all_names = set(profiles) | set(cat_by_comp) | set(cis_by_comp)

    # Vorige rankings voor trendbepaling (meest recente run vóór vandaag)
    prev_date = (
        db.query(models.CompetitorRanking.run_date)
        .filter(models.CompetitorRanking.run_date < today,
                models.CompetitorRanking.shop_id == sid)
        .order_by(models.CompetitorRanking.run_date.desc())
        .first()
    )
    prev_ranks: dict[tuple[str, str], int] = {}
    if prev_date:
        for r in db.query(models.CompetitorRanking).filter(
            models.CompetitorRanking.run_date == prev_date[0],
            models.CompetitorRanking.shop_id == sid,
        ).all():
            prev_ranks[(r.scope, r.competitor_name)] = r.rank

    # Verwijder eventuele rankings van vandaag (herrun = delete-then-insert)
    db.query(models.CompetitorRanking).filter(
        models.CompetitorRanking.run_date == today,
        models.CompetitorRanking.shop_id == sid,
    ).delete(synchronize_session=False)

    written = 0

    def _scores_for(name: str, scope_rows: list[models.CategoryCompetitorRelevance]) -> tuple[float, float, float, float, dict]:
        def _norm(v: float) -> float:
            """Normaliseer naar 0..1 (bronvelden mixen 0..1- en 0..100-schalen)."""
            return min(1.0, v / 100.0 if v > 1.0 else v)

        prof = profiles.get(name)
        overlap = _norm(float(prof.functional_overlap_score or 0)) if prof else 0.0
        relevance_cat = _norm(_avg([float(r.relevance_score or 0) for r in scope_rows]))
        coverage = _norm(_avg([float(r.coverage_index or 0) for r in scope_rows]))
        competition_relevance = round(0.40 * overlap + 0.40 * relevance_cat + 0.20 * coverage, 4)

        pricing_rel = _norm(_avg([float(r.pricing_relevance_score or 0) for r in scope_rows]))
        freq = min(1.0, float(prof.price_change_frequency or 0) / 100.0) if prof else 0.0
        price_relevance = round(0.70 * pricing_rel + 0.30 * freq, 4)

        cis_values = cis_by_comp.get(name, [])
        if cis_values:
            influence = round(_norm(_avg(cis_values)), 4)
            influence_basis = "prijshistorie"
        elif prof is not None:
            # Geen prijshistorie: baseline op basis van profiel alleen, zodat
            # pas ontdekte concurrenten niet stilletjes op Influence 0 blijven.
            influence = profile_baseline_influence(prof)
            influence_basis = "profiel"
        else:
            influence = 0.0
            influence_basis = "geen_data"

        combined = round(
            W_COMPETITION_RELEVANCE * competition_relevance
            + W_PRICE_RELEVANCE * price_relevance
            + W_INFLUENCE * influence, 4)

        evidence = {
            "functional_overlap_score": round(overlap, 4),
            "avg_category_relevance": round(relevance_cat, 4),
            "avg_coverage_index": round(coverage, 4),
            "avg_pricing_relevance": round(pricing_rel, 4),
            "price_change_frequency": float(prof.price_change_frequency or 0) if prof else 0,
            "avg_cis_score": influence,
            "influence_basis": influence_basis,
            "cis_sku_count": cis_count_by_comp.get(name, 0),
            "category_rows_used": len(scope_rows),
            "weights": {
                "competition_relevance": W_COMPETITION_RELEVANCE,
                "price_relevance": W_PRICE_RELEVANCE,
                "influence": W_INFLUENCE,
            },
        }
        return competition_relevance, price_relevance, influence, combined, evidence

    def _write_scope(scope: str, names: set[str], rows_for=lambda n: cat_by_comp.get(n, [])) -> None:
        nonlocal written
        scored = []
        for name in names:
            cr, pr, infl, comb, ev = _scores_for(name, rows_for(name))
            scored.append((name, cr, pr, infl, comb, ev))
        scored.sort(key=lambda t: t[4], reverse=True)

        for idx, (name, cr, pr, infl, comb, ev) in enumerate(scored, start=1):
            prev = prev_ranks.get((scope, name))
            if prev is None:
                trend = "new"
            elif idx < prev:
                trend = "up"
            elif idx > prev:
                trend = "down"
            else:
                trend = "stable"

            datapunten = ev["cis_sku_count"] + ev["category_rows_used"]
            confidence = round(min(0.95, 0.35 + 0.05 * min(datapunten, 12)), 2)

            if ev.get("influence_basis") == "profiel":
                influence_uitleg = (
                    f"Influence-score op basis van profiel (geen prijshistorie beschikbaar); "
                    f"gebaseerd op {ev['category_rows_used']} categoriescores."
                )
            else:
                influence_uitleg = (
                    f"Influence-score op basis van prijshistorie; gebaseerd op "
                    f"{ev['category_rows_used']} categoriescores en "
                    f"{ev['cis_sku_count']} SKU-invloedscores."
                )
            explanation = (
                f"{name} staat op rank {idx} in scope '{scope}' met gecombineerde score {comb:.2f} "
                f"(competition relevance {cr:.2f}, price relevance {pr:.2f}, influence {infl:.2f}). "
                + influence_uitleg
                + (f" Vorige rank: {prev}." if prev else " Nieuw in de ranking.")
            )

            db.add(models.CompetitorRanking(
                run_date=today,
                shop_id=sid,
                scope=scope,
                competitor_name=name,
                competition_relevance_score=cr,
                price_relevance_score=pr,
                influence_score=infl,
                combined_score=comb,
                rank=idx,
                previous_rank=prev,
                rank_trend=trend,
                confidence=confidence,
                explanation=explanation,
                evidence=ev,
                model_version=MODEL_VERSION,
            ))
            written += 1

    # Overall ranking
    _write_scope("overall", all_names)

    # Per categorie
    categories: dict[str, set[str]] = {}
    for r in cat_rows:
        categories.setdefault(r.category, set()).add(r.competitor_name)
    for cat, names in categories.items():
        _write_scope(cat, names, rows_for=lambda n, c=cat: [
            r for r in cat_by_comp.get(n, []) if r.category == c
        ])

    return written
