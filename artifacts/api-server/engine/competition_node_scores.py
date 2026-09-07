"""
Node-specifieke concurrentscores per canonieke hiërarchie-node (taak #265).

Berekent per (shop, concurrent, hiërarchie-node) de drie gestandaardiseerde
scores over uitsluitend producten die descendant zijn van die node:
  - Competition Relevance : assortimentsdekking binnen de tak
    (waargenomen SKU's / SKU's onder de node)
  - Price Relevance       : hoe dicht de concurrent binnen de tak op onze
    prijzen zit (CIS price_vs_own_pct-nabijheid over waargenomen SKU's)
  - Influence             : gemiddelde CIS-score over de SKU's onder de node

De koppeling loopt via interne SKU → ProductHierarchyAssignment (active);
PriceShape-categorieën zijn alleen bronmetadata. Waarnemingen op SKU's zonder
actieve mapping tellen niet mee, maar worden per concurrent zichtbaar bewaard
als rij met node_id = NULL ("mapping ontbreekt").

Scores worden opgeslagen voor nodes t/m MAX_NODE_LEVEL (hoofdgroep +
categorie); diepere selecties vallen in de API terug op de dichtstbijzijnde
gescoorde voorouder. Historie blijft behouden (snapshot per run_date,
delete-then-insert per dag — zelfde patroon als CompetitorRanking).

Draait in dezelfde run als de bestaande rankings-refresh: wordt aangeroepen
vanuit `run_competitor_rankings`, fout-tolerant per shop zodat een node-score-
probleem de rankings zelf nooit laat falen.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

import models

logger = logging.getLogger("uvicorn.error")

MODEL_VERSION = "node-scores-v1.0.0"

# Zinnig niveau: hoofdgroep (1) + categorie (2). Diepere nodes erven in de
# API van de dichtstbijzijnde gescoorde voorouder.
MAX_NODE_LEVEL = 2

# Zelfde gewichten als de overall rankings (engine/competition_rankings.py)
from engine.competition_rankings import (  # noqa: E402
    W_COMPETITION_RELEVANCE, W_PRICE_RELEVANCE, W_INFLUENCE,
    _weighted_available,
)


def run_competitor_node_scores(db: Session, ref_date: date | None = None,
                               shop_id: int | None = None) -> int:
    """
    Bereken en persisteer node-scores. Retourneert het aantal geschreven rijen
    (incl. "mapping ontbreekt"-rijen). Commit gebeurt door de aanroeper.
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
    return total


def _norm(v: float) -> float:
    """Normaliseer naar 0..1 (bronvelden mixen 0..1- en 0..100-schalen)."""
    v = float(v or 0)
    return min(1.0, v / 100.0 if v > 1.0 else v)


def _run_for_shop(db: Session, today: date, sid: int) -> int:
    from sqlalchemy import func

    A = models.ProductHierarchyAssignment
    N = models.ProductHierarchyNode
    P = models.DimProduct
    F = models.FactCompetitorPriceDaily
    C = models.CompetitorInfluenceScore

    # SKU → actieve node-mapping, beperkt tot deze shop.
    assign_rows = (db.query(A.sku_id, A.node_id)
                   .join(P, P.sku_id == A.sku_id)
                   .filter(P.shop_id == sid, A.status == "active")
                   .all())
    sku_to_nodes: dict[str, set[int]] = {}
    for sku, nid in assign_rows:
        sku_to_nodes.setdefault(sku, set()).add(nid)

    # Paden van alle gebruikte nodes → voorouders t/m MAX_NODE_LEVEL.
    used_node_ids = {nid for nids in sku_to_nodes.values() for nid in nids}
    node_rows = (db.query(N.id, N.path).filter(N.id.in_(used_node_ids)).all()
                 if used_node_ids else [])
    node_path: dict[int, list[int]] = {}
    for nid, path in node_rows:
        ids = [int(p) for p in (path or "").strip("/").split("/") if p]
        node_path[nid] = ids

    # Alle score-nodes (level ≤ MAX_NODE_LEVEL) waaronder SKU's vallen.
    node_skus: dict[int, set[str]] = {}
    for sku, nids in sku_to_nodes.items():
        for nid in nids:
            for anc in node_path.get(nid, [])[:MAX_NODE_LEVEL]:
                node_skus.setdefault(anc, set()).add(sku)

    # Prijswaarnemingen per (concurrent, sku): tellers + first/last seen.
    obs_rows = (db.query(F.competitor_name, F.sku_id,
                         func.count(F.id), func.min(F.date), func.max(F.date))
                .filter(F.shop_id == sid)
                .group_by(F.competitor_name, F.sku_id)
                .all())
    # Geblokkeerde concurrenten blijven buiten de node-scores (taak #288).
    from services.competitor_master import blocked_competitor_names
    _blocked = blocked_competitor_names(db)
    if _blocked:
        obs_rows = [r for r in obs_rows if r[0] not in _blocked]

    # CIS per (concurrent, sku): influence + prijsnabijheid. Neem per paar
    # deterministisch de MEEST RECENTE CIS-run (de node-score-run draait in
    # dezelfde rankings-run als de CIS-engine, dus normaliter is dat de run
    # van vandaag; oudere historie mag een nieuw dagsnapshot nooit overschrijven).
    cis_rows = (db.query(C.competitor_name, C.sku_id, C.cis_score,
                         C.price_vs_own_pct, C.run_date)
                .join(P, P.sku_id == C.sku_id)
                .filter(P.shop_id == sid)
                .all())
    cis_by_pair: dict[tuple[str, str], tuple[float, float | None]] = {}
    _cis_run: dict[tuple[str, str], date] = {}
    for name, sku, cis, pct, run_d in cis_rows:
        key = (name, sku)
        prev = _cis_run.get(key)
        if prev is not None and run_d is not None and run_d < prev:
            continue  # oudere run: nooit een recentere waarde overschrijven
        _cis_run[key] = run_d
        cis_by_pair[key] = (float(cis or 0),
                            float(pct) if pct is not None else None)

    # Herrun op dezelfde dag: delete-then-insert (historie van eerdere dagen
    # blijft behouden).
    db.query(models.CompetitorHierarchyNodeScore).filter(
        models.CompetitorHierarchyNodeScore.shop_id == sid,
        models.CompetitorHierarchyNodeScore.run_date == today,
    ).delete(synchronize_session=False)

    written = 0

    # Per concurrent: waarnemingen groeperen op gemapte SKU's / ongemapt.
    per_comp_sku: dict[str, dict[str, tuple[int, date, date]]] = {}
    unmapped: dict[str, tuple[int, date | None, date | None]] = {}
    for name, sku, cnt, dmin, dmax in obs_rows:
        if sku in sku_to_nodes:
            per_comp_sku.setdefault(name, {})[sku] = (int(cnt), dmin, dmax)
        else:
            c0, mn, mx = unmapped.get(name, (0, None, None))
            unmapped[name] = (
                c0 + int(cnt),
                min(mn, dmin) if mn else dmin,
                max(mx, dmax) if mx else dmax,
            )

    for name, sku_obs in per_comp_sku.items():
        for nid, all_skus in node_skus.items():
            observed = [s for s in all_skus if s in sku_obs]
            if not observed:
                continue  # concurrent niet waargenomen in deze tak
            node_total = len(all_skus)
            coverage = len(observed) / node_total if node_total else 0.0
            competition_relevance = round(min(1.0, coverage), 4)

            closeness_vals = []
            cis_vals = []
            for s in observed:
                cis, pct = cis_by_pair.get((name, s), (None, None))
                if cis is not None:
                    cis_vals.append(_norm(cis))
                if pct is not None:
                    closeness_vals.append(max(0.0, 1.0 - min(1.0, abs(pct) / 30.0)))
            price_relevance = (
                round(sum(closeness_vals) / len(closeness_vals), 4)
                if closeness_vals else None)
            influence = (
                round(sum(cis_vals) / len(cis_vals), 4)
                if cis_vals else None)
            combined, combined_components = _weighted_available([
                ("competition_relevance", competition_relevance,
                 W_COMPETITION_RELEVANCE),
                ("price_relevance", price_relevance, W_PRICE_RELEVANCE),
                ("influence", influence, W_INFLUENCE),
            ])

            obs_count = sum(sku_obs[s][0] for s in observed)
            first_seen = min(sku_obs[s][1] for s in observed)
            last_seen = max(sku_obs[s][2] for s in observed)
            confidence = round(min(0.95, 0.35 + 0.05 * min(len(observed), 12)), 2)

            db.add(models.CompetitorHierarchyNodeScore(
                shop_id=sid, run_date=today, node_id=nid,
                competitor_name=name,
                node_sku_count=node_total,
                observed_sku_count=len(observed),
                observation_count=obs_count,
                competition_relevance_score=competition_relevance,
                price_relevance_score=price_relevance,
                influence_score=influence,
                combined_score=combined,
                confidence=confidence,
                first_seen=first_seen, last_seen=last_seen,
                evidence={
                    "coverage": round(coverage, 4),
                    "observed_sku_count": len(observed),
                    "node_sku_count": node_total,
                    "cis_sku_count": len(cis_vals),
                    "price_closeness_sku_count": len(closeness_vals),
                    "combined_components": combined_components,
                    "weights": {
                        "competition_relevance": W_COMPETITION_RELEVANCE,
                        "price_relevance": W_PRICE_RELEVANCE,
                        "influence": W_INFLUENCE,
                    },
                },
                model_version=MODEL_VERSION,
            ))
            written += 1

    # "Mapping ontbreekt"-bucket: waarnemingen zonder interne mapping tellen
    # niet mee in node-scores maar verdwijnen niet stilzwijgend.
    for name, (cnt, dmin, dmax) in unmapped.items():
        db.add(models.CompetitorHierarchyNodeScore(
            shop_id=sid, run_date=today, node_id=None,
            competitor_name=name,
            node_sku_count=0, observed_sku_count=0, observation_count=cnt,
            competition_relevance_score=None, price_relevance_score=None,
            influence_score=None, combined_score=None, confidence=0.0,
            first_seen=dmin, last_seen=dmax,
            evidence={"reason": "mapping_ontbreekt",
                      "note": ("waarnemingen op SKU's zonder actieve "
                               "hiërarchie-mapping; tellen niet mee in node-scores")},
            model_version=MODEL_VERSION,
        ))
        written += 1

    return written
