"""
Explainability Engine
Genereert automatisch Nederlandstalige uitleg voor pricing-beslissingen,
aanbevelingen, BCG-classificaties, alerts en scores.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session


# ── Score formaat-helpers ─────────────────────────────────────────────────────

def _pct(v: float) -> str:
    return f"{v * 100:.0f}%"

def _score_woord(v: float, drempels=((0.70, "hoog"), (0.40, "gemiddeld"))) -> str:
    for drempel, label in drempels:
        if v >= drempel:
            return label
    return "laag"


# ── Score-uitleg ──────────────────────────────────────────────────────────────

def generate_score_explanation(score_type: str, score_value: float, context: Dict[str, Any] = None) -> str:
    """Genereer een leesbare uitleg voor een numerieke score."""
    ctx = context or {}
    sku = ctx.get("sku_naam", "dit product")

    handlers = {
        "tds": _explain_tds,
        "bbs": _explain_bbs,
        "sevs": _explain_sevs,
        "pcis": _explain_pcis,
        "eps": _explain_eps,
        "ppfs": _explain_ppfs,
        "confidence": _explain_confidence,
        "elasticiteit": _explain_elasticiteit,
    }
    handler = handlers.get(score_type.lower())
    if handler:
        return handler(score_value, sku, ctx)
    return f"{score_type.upper()} score van {_pct(score_value)}: {_score_woord(score_value)} niveau."


def _explain_tds(score: float, sku: str, ctx: dict) -> str:
    seo = ctx.get("seo_traffic", 0)
    vol = ctx.get("zoekvolume", 0)
    nc  = ctx.get("nieuwe_klanten", 0)
    if score >= 0.80:
        return (f"{sku} is een kritieke traffic driver (TDS {_pct(score)}). "
                f"Met {seo:,} SEO-bezoekers/maand en {vol:,} extern zoekvolume trekt dit product structureel "
                f"nieuwe klanten aan ({nc:,} nieuwe klanten/maand). "
                f"Prijsverhoging riskeert verlies van organische positie en acquisitiekanaal.")
    elif score >= 0.60:
        return (f"{sku} heeft een sterke traffic driver score (TDS {_pct(score)}). "
                f"Significant SEO/SEA verkeer en zoekvolume. Prijswijzigingen voorzichtig doorvoeren.")
    elif score >= 0.40:
        return (f"{sku} heeft matige traffic impact (TDS {_pct(score)}). "
                f"Beperkte traffic-gevoeligheid — standaard pricing regels van toepassing.")
    return (f"{sku} genereert weinig organisch traffic (TDS {_pct(score)}). "
            f"Pricing kan worden geoptimaliseerd op directe marge.")


def _explain_bbs(score: float, sku: str, ctx: dict) -> str:
    attach = ctx.get("attach_rate", 0)
    uplift = ctx.get("basket_uplift_eur", 0)
    if score >= 0.75:
        return (f"{sku} is een kritieke winkelmandvuller (BBS {_pct(score)}). "
                f"Attach-rate: {attach*100:.0f}% van bestellingen, gemiddelde basket uplift: €{uplift:.2f}. "
                f"Bundels en cross-sell promoties sterk aanbevolen.")
    elif score >= 0.55:
        return (f"{sku} heeft sterke basket-uitbreidingseffecten (BBS {_pct(score)}). "
                f"Attach-rate {attach*100:.0f}%: vaak samen gekocht met complementaire producten.")
    return (f"{sku} heeft beperkte winkelmand-impact (BBS {_pct(score)}). "
            f"Focus op directe marge optimalisatie.")


def _explain_sevs(score: float, sku: str, ctx: dict) -> str:
    tds = ctx.get("tds", 0)
    bbs = ctx.get("bbs", 0)
    rol = ctx.get("primaire_rol", "")
    if score >= 0.72:
        drivers = []
        if tds >= 0.60: drivers.append("hoge traffic-waarde")
        if bbs >= 0.55: drivers.append("sterke basket-uitbreiding")
        if ctx.get("rcs", 0) >= 0.60: drivers.append("hoge herhaalaankoop")
        reden = ", ".join(drivers) if drivers else "meerdere commerciële bijdragen"
        return (f"{sku} heeft een kritieke ecosysteemwaarde (SEVS {_pct(score)}). "
                f"Strategisch beschermen ondanks eventueel lage directe marge — waarde zit in {reden}.")
    elif score >= 0.52:
        return (f"{sku} heeft hoge ecosysteemwaarde (SEVS {_pct(score)}). "
                f"Primaire rol: {rol or 'onbekend'}. Pricing voorzichtig aanpassen.")
    elif score >= 0.32:
        return (f"{sku} heeft gemiddelde ecosysteemwaarde (SEVS {_pct(score)}). "
                f"Regulier pricingbeheer van toepassing.")
    return (f"{sku} heeft lage ecosysteemwaarde (SEVS {_pct(score)}). "
            f"Overweeg margeoptimalisatie of sanering.")


def _explain_pcis(score: float, sku: str, ctx: dict) -> str:
    if score >= 0.80:
        return (f"{sku} ervaart kritieke concurrentiedruk (PCIS {_pct(score)}). "
                f"Markt is transparant en prijsgevoelig. Zelfs kleine prijsafwijkingen kunnen conversie schaden.")
    elif score >= 0.60:
        return (f"{sku} staat onder hoge concurrentiedruk (PCIS {_pct(score)}). "
                f"Prijswijzigingen voorzichtig doorvoeren. Monitoring aanbevolen.")
    elif score >= 0.30:
        return (f"{sku} heeft gemiddelde concurrentiedruk (PCIS {_pct(score)}). "
                f"Enige ruimte voor pricing-optimalisatie.")
    return (f"{sku} heeft lage concurrentiedruk (PCIS {_pct(score)}). "
            f"Aanzienlijke vrijheid voor margeoptimalisatie.")


def _explain_eps(score: float, sku: str, ctx: dict) -> str:
    first_pct = ctx.get("eerste_product_pct", 0)
    nc_pct = ctx.get("nieuwe_klant_pct", 0)
    if score >= 0.60:
        return (f"{sku} is een sterk entry product (EPS {_pct(score)}). "
                f"In {first_pct*100:.0f}% van sessies het eerste product, {nc_pct*100:.0f}% van nieuwe klanten start hier. "
                f"Pricing bepaalt de eerste klantindruk — voorzichtig aanpassen.")
    elif score >= 0.30:
        return (f"{sku} speelt een matige entry-rol (EPS {_pct(score)}). "
                f"Enige acquisitie-waarde aanwezig.")
    return f"{sku} heeft beperkte entry-rol (EPS {_pct(score)})."


def _explain_ppfs(score: float, sku: str, ctx: dict) -> str:
    if score >= 0.70:
        return (f"{sku} heeft uitstekende doorberekenbaarheid (PPFS {_pct(score)}). "
                f"Inkoopprijsstijgingen kunnen grotendeels worden doorberekend zonder significant volume-verlies.")
    elif score >= 0.50:
        return (f"{sku} heeft goede doorberekenbaarheid (PPFS {_pct(score)}). "
                f"Gedeeltelijke doorberekening van kostenstijgingen is haalbaar.")
    elif score >= 0.30:
        return (f"{sku} heeft matige doorberekenbaarheid (PPFS {_pct(score)}). "
                f"Voorzichtig doorberekenen — monitor volume na aanpassing.")
    return (f"{sku} heeft slechte doorberekenbaarheid (PPFS {_pct(score)}). "
            f"Kostenstijging zal marge drukken. Alternatief: private label push of kostenreductie.")


def _explain_confidence(score: float, sku: str, ctx: dict) -> str:
    if score >= 0.80:
        return f"Hoge modelbetrouwbaarheid ({_pct(score)}): advies gebaseerd op solide data en historisch patroon."
    elif score >= 0.60:
        return f"Goede modelbetrouwbaarheid ({_pct(score)}): advies betrouwbaar, normaal uitvoerbaar."
    elif score >= 0.40:
        return f"Matige betrouwbaarheid ({_pct(score)}): extra review door pricing analist aanbevolen voor uitvoering."
    return f"Lage betrouwbaarheid ({_pct(score)}): onvoldoende data of inconsistente historie. Handmatige beoordeling vereist."


def _explain_elasticiteit(score: float, sku: str, ctx: dict) -> str:
    # Elasticiteit is negatief; score hier als absolute waarde
    abs_el = abs(score)
    if abs_el >= 2.0:
        return (f"{sku} is sterk prijsgevoelig (elasticiteit {score:.2f}). "
                f"1% prijsverhoging leidt naar verwachting tot {abs_el:.1f}% vraagdaling. Prijsverhoging sterk ontmoedigd.")
    elif abs_el >= 1.0:
        return (f"{sku} is prijsgevoelig (elasticiteit {score:.2f}). "
                f"Prijsverhogingen leiden tot merkbaar volume-verlies.")
    elif abs_el >= 0.5:
        return (f"{sku} is matig prijsgevoelig (elasticiteit {score:.2f}). "
                f"Voorzichtig verhogen mogelijk.")
    return (f"{sku} is weinig prijsgevoelig (elasticiteit {score:.2f}). "
            f"Relatief veilig om prijs te verhogen voor margeoptimalisatie.")


# ── Aanbeveling-uitleg ────────────────────────────────────────────────────────

def generate_recommendation_explanation(rec: Dict[str, Any], db: Session = None) -> Dict[str, Any]:
    """Genereer uitgebreide Nederlandstalige uitleg voor een pricing-aanbeveling."""
    sku_id    = rec.get("sku_id", "")
    sku_naam  = rec.get("product_name", sku_id)
    strategie = rec.get("strategy_type", "")
    huidige   = float(rec.get("current_price") or 0)
    aanbevolen= float(rec.get("recommended_price") or 0)
    conf      = float(rec.get("confidence_score") or 0.5)
    marge     = float(rec.get("current_margin") or 0)

    prijswijziging_pct = ((aanbevolen - huidige) / max(huidige, 0.01)) * 100
    richting = "verhoging" if prijswijziging_pct > 0 else "verlaging"
    abswijz = abs(prijswijziging_pct)

    # Hoofdreden op basis van strategie
    strategie_uitleg: Dict[str, str] = {
        "COMPETITOR_INDEX":          f"Concurrentieanalyse toont dat de marktprijs is veranderd. Een prijs{richting} van {abswijz:.1f}% brengt 123inkt dichter bij de optimale concurrentiepositie.",
        "MARGIN_OPTIMIZATION":       f"Marginale analyse toont optimalisatieruimte. De prijs{richting} van {abswijz:.1f}% verbetert de margebijdrage terwijl het verwachte volume acceptabel blijft.",
        "STOCK_CLEARANCE":           f"Voorraadniveau is te hoog. Prijsverlaging van {abswijz:.1f}% stimuleert verkoop en reduceert opslagkosten.",
        "BASKET_BUILDER":            f"Dit SKU heeft hoge basket-waarde. Lichte prijsverlaging verhoogt attach-rate en totale bestelwaarde.",
        "VOLUME_DISCOUNT":           f"Hoge elasticiteit maakt volumestimulering via prijsverlaging winstgevend.",
        "REPEAT_PURCHASE":           f"Stabiele prijs voor herhalingskopers behoudt klantloyaliteit. Kleine aanpassing op basis van inkoopwijziging.",
        "LOW_VELOCITY":              f"Laag volume SKU met margeruimte. Prijs{richting} optimaliseert margebijdrage.",
        "SUBSTITUTION_PORTFOLIO":    f"Prijs{richting} optimaliseert het prijsverschil tussen A-merk en huismerk equivalent.",
        "PRIVATE_LABEL_PUSH":        f"Private label strategie: huismerkprijs aanpassen voor betere margeverdeling.",
        "TRAFFIC_TO_MARGIN_SWITCH":  f"Traffic driver SKU dat voldoende volume genereert voor veilige margeoptimalisatie.",
    }
    hoofd_reden = strategie_uitleg.get(strategie, f"Pricing optimalisatie via strategie {strategie}.")

    # Factoren
    factoren = []
    conf_niv = _explain_confidence(conf, sku_naam, {})
    factoren.append(f"Betrouwbaarheid: {conf_niv}")

    factoren_samenvatting = " | ".join(factoren)

    samenvatting = (
        f"Prijs{richting} van {abswijz:.1f}% wordt aanbevolen voor '{sku_naam}'. "
        f"{hoofd_reden}"
    )

    return {
        "samenvatting_nl": samenvatting,
        "hoofd_reden": hoofd_reden,
        "strategie_type": strategie,
        "prijswijziging_richting": richting,
        "prijswijziging_pct": round(prijswijziging_pct, 2),
        "confidence_uitleg": _explain_confidence(conf, sku_naam, {}),
        "factoren": factoren,
        "actie_advies": _actie_advies(conf, prijswijziging_pct, strategie),
    }


def _actie_advies(conf: float, wijziging_pct: float, strategie: str) -> str:
    if conf < 0.40:
        return "⚠️ Handmatige review verplicht voor uitvoering wegens lage modelbetrouwbaarheid."
    if abs(wijziging_pct) > 5 and conf < 0.60:
        return "⚠️ Grote prijswijziging met matige betrouwbaarheid. Review door senior analist aanbevolen."
    if abs(wijziging_pct) <= 2 and conf >= 0.70:
        return "✅ Kleine aanpassing met hoge betrouwbaarheid. Veilig goed te keuren."
    return "✅ Normaal niveau. Standaard goedkeuringsproces van toepassing."


# ── BCG-uitleg ────────────────────────────────────────────────────────────────

def generate_bcg_explanation(bcg_class: str, context: Dict[str, Any] = None) -> str:
    """Genereer uitleg voor een BCG-classificatie."""
    ctx = context or {}
    sku = ctx.get("sku_naam", "dit product")

    uitleg = {
        "Star": (
            f"'{sku}' is geclassificeerd als **Ster**. "
            f"Dit product heeft zowel sterke omzetgroei als een goed marktaandeel. "
            f"Strategie: beschermen en investeren. Pricing ter ondersteuning van groei, niet voor korte-termijn margeoptimalisatie."
        ),
        "Cash Cow": (
            f"'{sku}' is een **Cash Cow**. "
            f"Stabiele, winstgevende SKU met hoog marktaandeel in een volwassen markt. "
            f"Strategie: marge maximaliseren. Minimale investering nodig voor ondersteuning."
        ),
        "Question Mark": (
            f"'{sku}' is een **Question Mark**. "
            f"Groeiende markt maar beperkt marktaandeel. "
            f"Strategische keuze nodig: investeren om Star te worden, of afbouwen?"
        ),
        "Dog": (
            f"'{sku}' is een **Dog**. "
            f"Lage groei en laag marktaandeel. "
            f"Overweeg sanering of repositionering. "
            f"Combineer met SEVS — hoge ecosysteemwaarde kan sanering onverstandig maken."
        ),
        "Internal Star": (
            f"'{sku}' is een **Interne Ster** — sterk in omzet en marge binnen het eigen portfolio. "
            f"Hoge strategische prioriteit. Beschermen tegen prijserosie."
        ),
        "Internal Cash Cow": (
            f"'{sku}' is een **Interne Cash Cow** — betrouwbare margegenerator. "
            f"Conservatief beheren. Prijs langzaam optimiliseren."
        ),
    }
    return uitleg.get(bcg_class, f"BCG-klasse '{bcg_class}' voor '{sku}'. Zie BCG documentatie voor details.")


# ── Alert-uitleg ──────────────────────────────────────────────────────────────

def generate_alert_explanation(alert_type: str, context: Dict[str, Any] = None) -> str:
    """Genereer uitleg voor een monitoring-alert."""
    ctx = context or {}
    sku = ctx.get("sku_naam", "dit product")

    uitleg = {
        "PRICE_FLOOR_BREACH":       f"'{sku}': aanbevolen prijs ligt onder de vloerprijs (kostprijs × 1.01). Pricing engine heeft de prijs gecorrigeerd naar de minimumgrens.",
        "LOW_CONFIDENCE":           f"'{sku}': modelbetrouwbaarheid onder 40%. Onvoldoende data voor betrouwbare aanbeveling. Handmatige review vereist.",
        "LARGE_PRICE_CHANGE":       f"'{sku}': aanbevolen prijswijziging overschrijdt dagelijkse grens van 5%. Aanpassing is gesplitst over meerdere dagen.",
        "OUT_OF_STOCK":             f"'{sku}': product is niet op voorraad. Pricing-aanbeveling uitgesteld (behalve bij STOCK_CLEARANCE strategie).",
        "COMPETITOR_PRICE_DROP":    f"'{sku}': concurrent heeft prijs verlaagd met >5%. Concurrentieanalyse wordt opnieuw uitgevoerd.",
        "MARGIN_BELOW_THRESHOLD":   f"'{sku}': marge is gedaald onder het ingestelde minimum. Directe actie aanbevolen: prijs verhogen of kosten reduceren.",
    }
    return uitleg.get(alert_type, f"Alert '{alert_type}' voor '{sku}'. Controleer details in het monitoring-dashboard.")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def get_explainability_dashboard(db: Session) -> Dict[str, Any]:
    """Overzicht van explainability-score voor het platform."""
    from models import FactPricingRecommendationDaily

    total = db.query(FactPricingRecommendationDaily).filter(
        FactPricingRecommendationDaily.approval_status == "pending"
    ).count()

    hoge_conf = db.query(FactPricingRecommendationDaily).filter(
        FactPricingRecommendationDaily.approval_status == "pending",
        FactPricingRecommendationDaily.confidence_score >= 0.70,
    ).count()

    lage_conf = db.query(FactPricingRecommendationDaily).filter(
        FactPricingRecommendationDaily.approval_status == "pending",
        FactPricingRecommendationDaily.confidence_score < 0.40,
    ).count()

    return {
        "totaal_openstaand": total,
        "hoge_betrouwbaarheid": hoge_conf,
        "lage_betrouwbaarheid_review_nodig": lage_conf,
        "automatisch_uitvoerbaar": hoge_conf,
        "handmatig_reviewen": lage_conf,
    }
