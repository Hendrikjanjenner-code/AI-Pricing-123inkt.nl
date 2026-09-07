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

MODEL_VERSION = "rankings-v1.1.0"

# Gewichten voor de gecombineerde score
W_COMPETITION_RELEVANCE = 0.40
W_PRICE_RELEVANCE = 0.30
W_INFLUENCE = 0.30

# Business Strength (taak #247) is een ONDERSTEUNENDE dimensie: de combined
# score wordt (1-W)*basis + W*business_strength, met W ruim onder elk primair
# gewicht — categorie-gebaseerde Competition Relevance blijft dus dominant.
# Zonder score-rij verandert er niets. Price Relevance blijft ongewijzigd en
# weegt financiële grootte bewust vrijwel niet mee (alleen prijsgedrag).
W_BUSINESS_STRENGTH_SUPPORT = 0.10


def _avg(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def _weighted_available(components: list[tuple[str, float | None, float]]) -> tuple[float | None, dict]:
    """Herverdeel gewichten over beschikbare waarden; een gemeten 0 blijft geldig."""
    used = [(name, value, weight) for name, value, weight in components if value is not None]
    weight_sum = sum(weight for _, _, weight in used)
    score = (
        round(sum(value * weight for _, value, weight in used) / weight_sum, 4)
        if weight_sum else None
    )
    evidence = {
        name: {
            "available": value is not None,
            "value": round(value, 4) if value is not None else None,
            "configured_weight": weight,
            "effective_weight": round(weight / weight_sum, 4) if value is not None and weight_sum else 0,
        }
        for name, value, weight in components
    }
    return score, evidence


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

    # Node-specifieke scores per hiërarchie-node (taak #265) draaien in
    # dezelfde run mee — ná de rankings-commit en fout-tolerant per shop:
    # een node-score-probleem mag de zojuist geschreven rankings nooit
    # terugdraaien of de run laten falen, maar wordt wel zichtbaar gelogd.
    import logging
    _log = logging.getLogger("uvicorn.error")
    from engine.competition_node_scores import run_competitor_node_scores
    for sid in shop_ids:
        try:
            node_rows = run_competitor_node_scores(db, ref_date=today, shop_id=sid)
            db.commit()
            _log.info("Node-scores voor shop %s: %d rijen geschreven.", sid, node_rows)
        except Exception:
            db.rollback()
            _log.exception("Node-scores voor shop %s mislukt — rankings blijven staan.", sid)

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

    # Ondersteunende Business Strength-scores (taak #247), indien aanwezig.
    from engine.competitor_scores import latest_scores_by_competitor
    strength_by_comp = latest_scores_by_competitor(db, sid)

    # Aggregaties per concurrent
    cat_by_comp: dict[str, list[models.CategoryCompetitorRelevance]] = {}
    for r in cat_rows:
        cat_by_comp.setdefault(r.competitor_name, []).append(r)

    cis_by_comp: dict[str, list[float]] = {}
    cis_count_by_comp: dict[str, int] = {}
    for r in cis_rows:
        if r.cis_score is None:
            continue
        cis_by_comp.setdefault(r.competitor_name, []).append(float(r.cis_score))
        cis_count_by_comp[r.competitor_name] = cis_count_by_comp.get(r.competitor_name, 0) + 1

    all_names = set(profiles) | set(cat_by_comp) | set(cis_by_comp)
    # Geblokkeerde concurrenten blijven buiten de rankings (taak #288).
    from services.competitor_master import blocked_competitor_names
    all_names -= blocked_competitor_names(db)

    # Vorige rankings voor trendbepaling: het direct voorafgaande gepubliceerde
    # snapshot. Bij een herrun op dezelfde dag (bv. meerdere feed-syncs per dag)
    # zijn dat de rijen van vandaag die zo dadelijk vervangen worden — vergelijken
    # met eergisteren zou verschuivingen van de vorige sync maskeren. Alleen als
    # er vandaag nog niets staat, valt de vergelijking terug op de meest recente
    # run vóór vandaag.
    prev_ranks: dict[tuple[str, str], int] = {}
    todays_rows = db.query(models.CompetitorRanking).filter(
        models.CompetitorRanking.run_date == today,
        models.CompetitorRanking.shop_id == sid,
    ).all()
    if todays_rows:
        for r in todays_rows:
            prev_ranks[(r.scope, r.competitor_name)] = r.rank
    else:
        prev_date = (
            db.query(models.CompetitorRanking.run_date)
            .filter(models.CompetitorRanking.run_date < today,
                    models.CompetitorRanking.shop_id == sid)
            .order_by(models.CompetitorRanking.run_date.desc())
            .first()
        )
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

    def _scores_for(name: str, scope_rows: list[models.CategoryCompetitorRelevance]) -> tuple[float | None, float | None, float | None, float | None, dict]:
        def _norm(v: float | None) -> float | None:
            """Normaliseer naar 0..1 (bronvelden mixen 0..1- en 0..100-schalen)."""
            if v is None:
                return None
            return min(1.0, v / 100.0 if v > 1.0 else v)

        prof = profiles.get(name)
        overlap = _norm(float(prof.functional_overlap_score)
                        if prof and prof.functional_overlap_score is not None else None)
        relevance_cat = _norm(_avg([
            float(r.relevance_score) if r.relevance_score is not None else None
            for r in scope_rows]))
        coverage = _norm(_avg([
            float(r.coverage_index) if r.coverage_index is not None else None
            for r in scope_rows]))
        competition_relevance, competition_components = _weighted_available([
            ("functional_overlap_score", overlap, 0.40),
            ("avg_category_relevance", relevance_cat, 0.40),
            ("avg_coverage_index", coverage, 0.20),
        ])

        pricing_rel = _norm(_avg([
            float(r.pricing_relevance_score)
            if r.pricing_relevance_score is not None else None
            for r in scope_rows]))
        freq = (min(1.0, float(prof.price_change_frequency) / 100.0)
                if prof and prof.price_change_frequency is not None else None)
        price_relevance, price_components = _weighted_available([
            ("avg_pricing_relevance", pricing_rel, 0.70),
            ("price_change_frequency", freq, 0.30),
        ])

        cis_values = cis_by_comp.get(name, [])
        if cis_values:
            influence = round(_norm(_avg(cis_values)), 4)
            influence_basis = "prijshistorie"
        elif prof is not None and any(
            value is not None for value in (
                prof.functional_overlap_score,
                prof.relevance_label,
                prof.in_stock_rate,
            )
        ):
            # Geen prijshistorie: baseline op basis van profiel alleen, zodat
            # pas ontdekte concurrenten niet stilletjes op Influence 0 blijven.
            influence = profile_baseline_influence(prof)
            influence_basis = "profiel"
        else:
            influence = None
            influence_basis = "geen_data"

        base_combined, combined_components = _weighted_available([
            ("competition_relevance", competition_relevance, W_COMPETITION_RELEVANCE),
            ("price_relevance", price_relevance, W_PRICE_RELEVANCE),
            ("influence", influence, W_INFLUENCE),
        ])

        # Business Strength als ONDERSTEUNENDE dimensie (nooit dominant):
        # klein vast gewicht, alleen als er een score bekend is. Unknown
        # verandert de ranking niet (geen impliciete 0).
        strength_row = strength_by_comp.get(name)
        bs = (strength_row.business_strength_score
              if strength_row is not None else None)
        if bs is not None and base_combined is not None:
            combined = round((1.0 - W_BUSINESS_STRENGTH_SUPPORT) * base_combined
                             + W_BUSINESS_STRENGTH_SUPPORT * (float(bs) / 100.0), 4)
        else:
            combined = base_combined

        evidence = {
            "functional_overlap_score": round(overlap, 4) if overlap is not None else None,
            "avg_category_relevance": round(relevance_cat, 4) if relevance_cat is not None else None,
            "avg_coverage_index": round(coverage, 4) if coverage is not None else None,
            "avg_pricing_relevance": round(pricing_rel, 4) if pricing_rel is not None else None,
            "price_change_frequency": (
                float(prof.price_change_frequency)
                if prof and prof.price_change_frequency is not None else None),
            "avg_cis_score": influence,
            "influence_basis": influence_basis,
            "cis_sku_count": cis_count_by_comp.get(name, 0),
            "category_rows_used": len(scope_rows),
            "components": {
                "competition_relevance": competition_components,
                "price_relevance": price_components,
                "combined": combined_components,
            },
            "weights": {
                "competition_relevance": W_COMPETITION_RELEVANCE,
                "price_relevance": W_PRICE_RELEVANCE,
                "influence": W_INFLUENCE,
            },
        }
        if bs is not None:
            evidence["business_strength_support"] = {
                "business_strength_score": float(bs),
                "support_weight": W_BUSINESS_STRENGTH_SUPPORT,
                "base_combined": base_combined,
                "note": ("ondersteunend, nooit dominant; categorie-gebaseerde "
                         "Competition Relevance blijft primair"),
            }
        return competition_relevance, price_relevance, influence, combined, evidence

    def _write_scope(scope: str, names: set[str], rows_for=lambda n: cat_by_comp.get(n, [])) -> None:
        nonlocal written
        scored = []
        for name in names:
            cr, pr, infl, comb, ev = _scores_for(name, rows_for(name))
            scored.append((name, cr, pr, infl, comb, ev))
        scored.sort(key=lambda t: (
            t[4] is None,
            -(t[4] or 0),
            t[0].lower(),
        ))

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
            confidence = (
                round(min(0.95, 0.35 + 0.05 * min(datapunten, 12)), 2)
                if datapunten else 0.0)

            if ev.get("influence_basis") == "profiel":
                influence_uitleg = (
                    f"Influence-score op basis van profiel (geen prijshistorie beschikbaar); "
                    f"gebaseerd op {ev['category_rows_used']} categoriescores."
                )
            elif ev.get("influence_basis") == "geen_data":
                influence_uitleg = "Influence-score niet beschikbaar: geen geldige brondata."
            else:
                influence_uitleg = (
                    f"Influence-score op basis van prijshistorie; gebaseerd op "
                    f"{ev['category_rows_used']} categoriescores en "
                    f"{ev['cis_sku_count']} SKU-invloedscores."
                )
            explanation = ((
                f"{name} staat op rank {idx} in scope '{scope}' met gecombineerde score "
                f"{comb:.2f}" if comb is not None else
                f"{name} staat op rank {idx} in scope '{scope}' zonder beschikbare gecombineerde score"
            ) + (
                f" (competition relevance {cr:.2f}" if cr is not None else " (competition relevance niet beschikbaar"
            ) + (
                f", price relevance {pr:.2f}" if pr is not None else ", price relevance niet beschikbaar"
            ) + (
                f", influence {infl:.2f}). " if infl is not None else ", influence niet beschikbaar). "
            ) + (
                influence_uitleg
                + (f" Vorige rank: {prev}." if prev else " Nieuw in de ranking.")
            ))

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
