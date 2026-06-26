"""
Competitor Strategy Recognition Engine.

Analyseert prijshistorie per concurrent en classificeert naar één van
7 strategietypen met confidence score en aanbevolen reactie.

Strategietypen:
- EVERYDAY_LOW_PRICE   — Altijd laagste prijs, weinig variatie
- PROMOTION_DRIVEN     — Frequente promotie-dips gevolgd door herstel
- MARKET_SHARE_ATTACK  — Agressieve prijsdalingen in korte tijd
- MARGIN_PROTECTION    — Stabiele hoge prijzen, weinig reactie op markt
- INVENTORY_CLEARANCE  — Geleidelijke prijsdalingen (opruimen)
- PRICE_FOLLOWER       — Volgt marktgemiddelde, weinig initiatief
- PRICE_LEADER         — Zet prijsbewegingen in gang die anderen volgen
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Optional


STRATEGIE_LABELS: dict[str, str] = {
    "EVERYDAY_LOW_PRICE":  "Altijd-Laagste-Prijs",
    "PROMOTION_DRIVEN":    "Promotiegedreven",
    "MARKET_SHARE_ATTACK": "Marktaandeeloffensief",
    "MARGIN_PROTECTION":   "Margebescherming",
    "INVENTORY_CLEARANCE": "Opruimingsstrategie",
    "PRICE_FOLLOWER":      "Prijsvolger",
    "PRICE_LEADER":        "Prijsleider",
}

# Gewicht waarmee een concurrent meetelt in de COMPETITOR_INDEX-strategie.
# Concurrenten in opruiming (INVENTORY_CLEARANCE) verlaten de markt en mogen de
# referentieprijs niet naar beneden trekken → laag gewicht. Prijsleiders zetten
# de toon en krijgen extra gewicht. Overige strategieën tellen neutraal mee (1.0).
STRATEGIE_GEWICHT: dict[str, float] = {
    "PRICE_LEADER":        1.5,
    "INVENTORY_CLEARANCE": 0.3,
}


def strategie_gewicht(strategy_type: Optional[str]) -> float:
    """Weegfactor voor een concurrentstrategie in de prijsindex (default 1.0)."""
    if not strategy_type:
        return 1.0
    return STRATEGIE_GEWICHT.get(strategy_type, 1.0)


AANBEVOLEN_REACTIE: dict[str, str] = {
    "EVERYDAY_LOW_PRICE":  "Handhaaf eigen PCIS-gewogen referentieprijs; follow niet blind.",
    "PROMOTION_DRIVEN":    "Monitor promotiecycli; vermijd structurele prijsverlaging.",
    "MARKET_SHARE_ATTACK": "Alert actief — overweeg tijdelijke match voor strategische SKU's.",
    "MARGIN_PROTECTION":   "Kans om margeruimte te benutten; verhoog prijs met index.",
    "INVENTORY_CLEARANCE": "Niet volgen; tijdelijk fenomeen — concurrent verdwijnt uit markt.",
    "PRICE_FOLLOWER":      "Gebruik als referentiesignaal; concurrent volgt toch.",
    "PRICE_LEADER":        "Hoog gewicht toekennen in PCIS; snel reageren op wijzigingen.",
}


def _coeff_variation(prijzen: list[float]) -> float:
    """Variatiecoëfficiënt (std / mean). Maat voor prijsvolatiliteit."""
    if len(prijzen) < 2:
        return 0.0
    mu = statistics.mean(prijzen)
    if mu == 0:
        return 0.0
    return statistics.stdev(prijzen) / mu


def _promotie_dips(prijzen: list[float], drempel: float = 0.05) -> int:
    """Tel het aantal keren dat prijs >drempel daalt en daarna terugkeert."""
    if len(prijzen) < 3:
        return 0
    dips = 0
    for i in range(1, len(prijzen) - 1):
        if prijzen[i] < prijzen[i - 1] * (1 - drempel) and prijzen[i + 1] > prijzen[i] * (1 + drempel):
            dips += 1
    return dips


def _trend(prijzen: list[float]) -> float:
    """
    Lineaire trend (slope / mean) over de prijsreeks.
    Positief = stijgend, negatief = dalend.
    """
    n = len(prijzen)
    if n < 2:
        return 0.0
    mu = statistics.mean(prijzen)
    if mu == 0:
        return 0.0
    xs = list(range(n))
    x_mean = statistics.mean(xs)
    num = sum((xs[i] - x_mean) * (prijzen[i] - mu) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0.0
    return slope / mu


def _wijzigingen_per_dag(prijzen: list[float]) -> float:
    """Gemiddeld aantal dagelijkse prijswijzigingen."""
    if len(prijzen) < 2:
        return 0.0
    changes = sum(1 for i in range(1, len(prijzen)) if abs(prijzen[i] - prijzen[i - 1]) / (prijzen[i - 1] + 1e-9) > 0.002)
    return changes / (len(prijzen) - 1)


def _is_altijd_laag(prijzen_concurrent: list[float], marktgemiddelden: list[float]) -> bool:
    """True als concurrent structureel 3%+ onder markt zit."""
    if len(prijzen_concurrent) < 5 or len(marktgemiddelden) < 5:
        return False
    paren = list(zip(prijzen_concurrent[-len(marktgemiddelden):], marktgemiddelden))
    onder = sum(1 for c, m in paren if c < m * 0.97)
    return onder / len(paren) >= 0.8


def _is_prijsleider(
    concurrent: str,
    alle_concurrenten: dict[str, list[float]],
    datums: list[date],
) -> bool:
    """
    Ruwe proxy: concurrent wijzigt prijs op dag D, anderen volgen op D+1..D+3.
    """
    if len(alle_concurrenten) < 2 or len(datums) < 5:
        return False
    eigen = alle_concurrenten.get(concurrent, [])
    if len(eigen) < 4:
        return False

    volger_count = 0
    total_signals = 0
    for i in range(1, len(eigen) - 2):
        if abs(eigen[i] - eigen[i - 1]) / (eigen[i - 1] + 1e-9) > 0.01:
            total_signals += 1
            richting = 1 if eigen[i] > eigen[i - 1] else -1
            volgers = 0
            for andere, andere_prijzen in alle_concurrenten.items():
                if andere == concurrent or len(andere_prijzen) <= i + 2:
                    continue
                for lag in range(1, 3):
                    if i + lag < len(andere_prijzen):
                        delta = (andere_prijzen[i + lag] - andere_prijzen[i + lag - 1]) / (andere_prijzen[i + lag - 1] + 1e-9)
                        if abs(delta) > 0.005 and (delta > 0) == (richting > 0):
                            volgers += 1
                            break
            if volgers >= max(1, len(alle_concurrenten) // 2 - 1):
                volger_count += 1

    return total_signals > 0 and volger_count / total_signals >= 0.4


def classeer_concurrent(
    concurrent_naam: str,
    prijsreeks: list[float],
    marktgemiddelden: Optional[list[float]] = None,
    alle_concurrenten: Optional[dict[str, list[float]]] = None,
    datums: Optional[list[date]] = None,
) -> dict:
    """
    Classificeer één concurrent op basis van prijshistorie.

    Args:
        concurrent_naam:  Naam van de concurrent
        prijsreeks:       Chronologische lijst van dagprijzen (oudste eerst)
        marktgemiddelden: Marktgemiddelde per dag (zelfde lengte als prijsreeks)
        alle_concurrenten: Prijsreeksen van alle concurrenten (voor leader-detectie)
        datums:           Datumlijst (zelfde lengte als prijsreeks)

    Returns:
        dict met strategy_type, confidence, label_nl, reden, aanbevolen_reactie
    """
    if len(prijsreeks) < 3:
        return {
            "concurrent": concurrent_naam,
            "strategy_type": "PRICE_FOLLOWER",
            "confidence": 0.20,
            "label_nl": STRATEGIE_LABELS["PRICE_FOLLOWER"],
            "reden": "Onvoldoende historische data (< 3 datapunten).",
            "aanbevolen_reactie": AANBEVOLEN_REACTIE["PRICE_FOLLOWER"],
        }

    cv = _coeff_variation(prijsreeks)
    trend_val = _trend(prijsreeks)
    dips = _promotie_dips(prijsreeks)
    wijzigingen = _wijzigingen_per_dag(prijsreeks)
    mu = statistics.mean(prijsreeks)

    # Snel markt-laag check
    altijd_laag = False
    if marktgemiddelden and len(marktgemiddelden) >= 5:
        altijd_laag = _is_altijd_laag(prijsreeks, marktgemiddelden)

    # Snel leader check
    is_leider = False
    if alle_concurrenten and len(alle_concurrenten) >= 2 and datums:
        is_leider = _is_prijsleider(concurrent_naam, alle_concurrenten, datums)

    # ── Classificatieboom ──────────────────────────────────────────────────
    candidates: list[tuple[str, float, str]] = []  # (type, score, reden)

    # 1. EVERYDAY_LOW_PRICE
    if altijd_laag and cv < 0.04:
        score = 0.55 + min(0.30, (0.04 - cv) * 10)
        candidates.append(("EVERYDAY_LOW_PRICE", score,
            f"Structureel ≥80% van de tijd onder markt; lage volatiliteit (CV={cv:.3f})."))

    # 2. PROMOTION_DRIVEN
    if dips >= 2:
        promo_score = min(0.85, 0.50 + dips * 0.07)
        candidates.append(("PROMOTION_DRIVEN", promo_score,
            f"{dips} promotie-dip(s) gedetecteerd (≥5% daling gevolgd door herstel)."))

    # 3. MARKET_SHARE_ATTACK
    if trend_val < -0.08 and wijzigingen > 0.2:
        attack_score = min(0.85, 0.50 + abs(trend_val) * 2)
        candidates.append(("MARKET_SHARE_ATTACK", attack_score,
            f"Sterke neerwaartse trend ({trend_val:.3f}) met hoge wijzigingsfrequentie."))

    # 4. MARGIN_PROTECTION
    if cv < 0.025 and trend_val >= -0.01:
        margin_score = 0.55 + (0.025 - cv) * 12
        candidates.append(("MARGIN_PROTECTION", min(0.80, margin_score),
            f"Zeer stabiele prijs (CV={cv:.3f}); nauwelijks reactie op markt."))

    # 5. INVENTORY_CLEARANCE
    if trend_val < -0.05 and dips < 2 and wijzigingen < 0.15:
        clear_score = min(0.80, 0.50 + abs(trend_val) * 3)
        candidates.append(("INVENTORY_CLEARANCE", clear_score,
            f"Geleidelijke daling ({trend_val:.3f}) zonder promotiepatroon."))

    # 6. PRICE_LEADER
    if is_leider:
        candidates.append(("PRICE_LEADER", 0.70,
            "Concurrent initieert prijsbewegingen die door anderen gevolgd worden."))

    # 7. PRICE_FOLLOWER (default / fallback)
    follower_score = max(0.30, 0.50 - cv * 5 - abs(trend_val) * 2)
    candidates.append(("PRICE_FOLLOWER", follower_score,
        f"Geen dominante strategie; volgt markt (CV={cv:.3f}, trend={trend_val:.3f})."))

    # Kies de kandidaat met de hoogste score
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_type, best_conf, best_reden = candidates[0]

    return {
        "concurrent": concurrent_naam,
        "strategy_type": best_type,
        "confidence": round(min(0.95, best_conf), 3),
        "label_nl": STRATEGIE_LABELS[best_type],
        "reden": best_reden,
        "aanbevolen_reactie": AANBEVOLEN_REACTIE[best_type],
    }


def analyseer_alle_concurrenten(
    prijsdata: dict[str, list[tuple[date, float]]],
) -> list[dict]:
    """
    Analyseer alle concurrenten in de prijsdata.

    Args:
        prijsdata: {concurrent_naam: [(datum, prijs), ...]}  (gesorteerd op datum)

    Returns:
        lijst van classificatie-dicts per concurrent
    """
    alle_namen = list(prijsdata.keys())

    # --- Stap 1: ruwe reeksen per concurrent -----------------------------------
    prijsreeksen_raw: dict[str, list[float]] = {}
    datumreeksen: dict[str, list[date]] = {}
    for naam, reeks in prijsdata.items():
        gesorteerd = sorted(reeks, key=lambda x: x[0])
        datumreeksen[naam] = [d for d, _ in gesorteerd]
        prijsreeksen_raw[naam] = [float(p) for _, p in gesorteerd]

    # --- Stap 2: gemeenschappelijke datumindex (unie van alle datums) -----------
    alle_datums = sorted({d for reeks in datumreeksen.values() for d in reeks})
    if not alle_datums:
        return []

    # --- Stap 3: projecteer elke reeks op de gemeenschappelijke index ----------
    # Gebruik forward-fill zodat ontbrekende dagen de laatste bekende prijs houden.
    def _project(naam: str) -> list[float]:
        datum_prijs = dict(zip(datumreeksen[naam], prijsreeksen_raw[naam]))
        projected: list[float] = []
        last: Optional[float] = None
        for d in alle_datums:
            if d in datum_prijs:
                last = datum_prijs[d]
            projected.append(last if last is not None else 0.0)
        return projected

    prijsreeksen_aligned: dict[str, list[float]] = {
        naam: _project(naam) for naam in alle_namen
    }

    # --- Stap 4: marktgemiddelde per dag op de gemeenschappelijke index --------
    marktgemiddelden_gemeenschappelijk: list[float] = []
    for i in range(len(alle_datums)):
        dagprijzen = [
            prijsreeksen_aligned[n][i]
            for n in alle_namen
            if prijsreeksen_aligned[n][i] > 0
        ]
        marktgemiddelden_gemeenschappelijk.append(
            statistics.mean(dagprijzen) if dagprijzen else 0.0
        )
    datum_naar_markt = dict(zip(alle_datums, marktgemiddelden_gemeenschappelijk))

    # --- Stap 5: classificeer elke concurrent ----------------------------------
    resultaten = []
    for naam in alle_namen:
        prijzen = prijsreeksen_raw[naam]
        datums = datumreeksen[naam]

        # Marktgemiddelden uitsluitend op de eigen datums van deze concurrent
        # zodat zip(prijzen, marktgemiddelden) correct uitlijnt.
        marktgemiddelden_eigen = [datum_naar_markt.get(d, 0.0) for d in datums]

        result = classeer_concurrent(
            naam, prijzen,
            marktgemiddelden=marktgemiddelden_eigen,
            alle_concurrenten=prijsreeksen_aligned,   # uitgelijnde reeksen voor leader-detectie
            datums=alle_datums,                        # gemeenschappelijke index voor leader-detectie
        )
        result["datapunten"] = len(prijzen)
        result["periode_dagen"] = (
            (datums[-1] - datums[0]).days + 1 if len(datums) >= 2 else 0
        )
        resultaten.append(result)

    resultaten.sort(key=lambda x: x["confidence"], reverse=True)
    return resultaten
