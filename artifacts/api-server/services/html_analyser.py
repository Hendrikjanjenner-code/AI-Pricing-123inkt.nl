"""
HTML Analyser — automatische selector-suggesties voor de scraping hulpmodus.
Inspecteert een pagina en scoort kandidaat-selectors voor prijs, titel en voorraad.
Detecteert JS-rendering en blokkade-signalen.
Schrijft nooit HTML naar de database.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data-types
# ---------------------------------------------------------------------------

@dataclass
class SelectorCandidate:
    selector: str
    sample_text: str
    score: int  # 0–100


@dataclass
class AnalysisResult:
    prijs_kandidaten: list[SelectorCandidate] = field(default_factory=list)
    titel_kandidaten: list[SelectorCandidate] = field(default_factory=list)
    voorraad_kandidaten: list[SelectorCandidate] = field(default_factory=list)
    js_rendering_waarschijnlijk: bool = False
    geblokkeerd: bool = False
    blok_reden: Optional[str] = None
    aanbevolen_actie: str = ""
    html_preview: Optional[str] = None  # alleen voor Admin, nooit in DB


# ---------------------------------------------------------------------------
# Keyword-sets
# ---------------------------------------------------------------------------

_PRIJS_KLASSE_KEYWORDS = {
    "price", "prijs", "prijs-blok", "priceblock", "price-block", "koop-prijs",
    "product-price", "offer-price", "sale-price", "current-price", "amount",
    "bedrag", "totaalprijs", "verkoopprijs",
}
_TITEL_KLASSE_KEYWORDS = {
    "title", "naam", "name", "product-name", "product-title", "product-naam",
    "heading", "h1", "item-title", "item-name",
}
_VOORRAAD_KLASSE_KEYWORDS = {
    "stock", "voorraad", "beschikbaarheid", "availability", "in-stock",
    "delivery", "levering", "leverbaar", "bestellen",
}

_PRIJS_TEKST_PATRON = re.compile(
    r"(?:^|[\s])(?:€|EUR|GBP|USD|\$|£)?\s*\d{1,5}(?:[.,]\d{1,2})?\s*(?:€|EUR)?(?:$|[\s])"
)
_BLOCKED_PATTERNS = [
    re.compile(r"captcha", re.I),
    re.compile(r"cloudflare", re.I),
    re.compile(r"access denied", re.I),
    re.compile(r"403 forbidden", re.I),
    re.compile(r"bot detection", re.I),
    re.compile(r"ray id", re.I),
]
_JS_FRAMEWORK_TITLES = re.compile(
    r"(react|angular|vue|next\.?js|nuxt|gatsby|ember|svelte)", re.I
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _css_selector(tag) -> str:
    """Bouw een beknopte CSS-selector voor een BS4-element."""
    parts: list[str] = []
    for ancestor in reversed(list(tag.parents)):
        if ancestor.name in (None, "[document]", "html", "body"):
            continue
        cls = ancestor.get("class", [])
        el_id = ancestor.get("id", "")
        if el_id:
            parts.append(f"#{el_id}")
            break
        if cls:
            parts.append(f"{ancestor.name}.{cls[0]}")
        else:
            parts.append(ancestor.name)
    tag_cls = tag.get("class", [])
    tag_id = tag.get("id", "")
    if tag_id:
        parts.append(f"#{tag_id}")
    elif tag_cls:
        parts.append(f"{tag.name}.{tag_cls[0]}")
    else:
        parts.append(tag.name)
    # Beperk tot de laatste 3 stappen — lange selectors zijn fragiel
    return " > ".join(parts[-3:])


def _keyword_score(element, keywords: set[str]) -> int:
    """Score een element op basis van class/id keyword-overeenkomsten (0–40)."""
    score = 0
    cls_str = " ".join(element.get("class", [])).lower()
    id_str = element.get("id", "").lower()
    itemprop = element.get("itemprop", "").lower()
    combined = f"{cls_str} {id_str} {itemprop}"
    for kw in keywords:
        if kw in combined:
            score += 15
    return min(score, 40)


def _schema_score(element, schema_props: set[str]) -> int:
    """Score op basis van schema.org-itemprop (0–20)."""
    prop = element.get("itemprop", "").lower()
    if prop in schema_props:
        return 20
    return 0


def _og_score(soup, field_name: str) -> int:
    """Score op basis van Open Graph meta-tags (0–15)."""
    tag = soup.find("meta", property=f"og:{field_name}")
    if tag and tag.get("content"):
        return 15
    return 0


def _element_frequency_penalty(elements, idx: int) -> int:
    """Meer dan 5 gelijke elementen → penalty (−10 per element boven 5)."""
    count = len(elements)
    if count <= 5:
        return 0
    return min((count - 5) * 10, 30)


# ---------------------------------------------------------------------------
# Prijs-kandidaten
# ---------------------------------------------------------------------------

def _find_prijs_kandidaten(soup) -> list[SelectorCandidate]:
    kandidaten: list[SelectorCandidate] = []
    gezien: set[str] = set()

    # 1. Schema.org priceSpecification / price
    for tag in soup.find_all(itemprop=re.compile(r"price", re.I)):
        tekst = (tag.get("content") or tag.get_text(strip=True))[:60]
        if not tekst:
            continue
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        score = 60 + _keyword_score(tag, _PRIJS_KLASSE_KEYWORDS)
        if _PRIJS_TEKST_PATRON.search(f" {tekst} "):
            score = min(score + 20, 100)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst, score=min(score, 100)))

    # 2. Elementen met prijs-keywords in class/id
    for tag in soup.find_all(True):
        cls_str = " ".join(tag.get("class", [])).lower()
        id_str = tag.get("id", "").lower()
        if not any(kw in cls_str or kw in id_str for kw in _PRIJS_KLASSE_KEYWORDS):
            continue
        tekst = tag.get_text(strip=True)[:60]
        if not tekst:
            continue
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        score = _keyword_score(tag, _PRIJS_KLASSE_KEYWORDS)
        if _PRIJS_TEKST_PATRON.search(f" {tekst} "):
            score = min(score + 30, 100)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst, score=score))

    # 3. Elementen met numeriek-met-valuta-patroon in tekst
    for tag in soup.find_all(["span", "div", "p", "strong", "em", "data"]):
        tekst = tag.get_text(strip=True)
        if len(tekst) > 20 or not _PRIJS_TEKST_PATRON.search(f" {tekst} "):
            continue
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        score = 50 + _keyword_score(tag, _PRIJS_KLASSE_KEYWORDS)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst[:60], score=min(score, 100)))

    kandidaten.sort(key=lambda c: c.score, reverse=True)
    return kandidaten[:5]


# ---------------------------------------------------------------------------
# Titel-kandidaten
# ---------------------------------------------------------------------------

def _find_titel_kandidaten(soup) -> list[SelectorCandidate]:
    kandidaten: list[SelectorCandidate] = []
    gezien: set[str] = set()

    # 1. og:title
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        kandidaten.append(SelectorCandidate(
            selector="meta[property='og:title']",
            sample_text=og["content"][:80],
            score=85,
        ))

    # 2. Schema.org name
    for tag in soup.find_all(itemprop=re.compile(r"^name$", re.I)):
        tekst = (tag.get("content") or tag.get_text(strip=True))[:80]
        if not tekst:
            continue
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        score = 70 + _keyword_score(tag, _TITEL_KLASSE_KEYWORDS)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst, score=min(score, 100)))

    # 3. H1
    for tag in soup.find_all("h1"):
        tekst = tag.get_text(strip=True)[:80]
        if not tekst:
            continue
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        score = 65 + _keyword_score(tag, _TITEL_KLASSE_KEYWORDS)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst, score=min(score, 100)))

    # 4. Klasse/id-keywords
    for tag in soup.find_all(True):
        cls_str = " ".join(tag.get("class", [])).lower()
        id_str = tag.get("id", "").lower()
        if not any(kw in cls_str or kw in id_str for kw in _TITEL_KLASSE_KEYWORDS):
            continue
        tekst = tag.get_text(strip=True)[:80]
        if not tekst or len(tekst) < 5:
            continue
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        score = 40 + _keyword_score(tag, _TITEL_KLASSE_KEYWORDS)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst, score=min(score, 100)))

    kandidaten.sort(key=lambda c: c.score, reverse=True)
    return kandidaten[:5]


# ---------------------------------------------------------------------------
# Voorraad-kandidaten
# ---------------------------------------------------------------------------

_VOORRAAD_TEKST_PATRON = re.compile(
    r"(op voorraad|in stock|leverbaar|beschikbaar|uitverkocht|niet op voorraad|out of stock|niet leverbaar|op=op)",
    re.I,
)

def _find_voorraad_kandidaten(soup) -> list[SelectorCandidate]:
    kandidaten: list[SelectorCandidate] = []
    gezien: set[str] = set()

    # 1. Schema.org availability
    for tag in soup.find_all(itemprop=re.compile(r"availability", re.I)):
        tekst = (tag.get("content") or tag.get_text(strip=True))[:60]
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst, score=80))

    # 2. Klasse/id-keywords
    for tag in soup.find_all(True):
        cls_str = " ".join(tag.get("class", [])).lower()
        id_str = tag.get("id", "").lower()
        if not any(kw in cls_str or kw in id_str for kw in _VOORRAAD_KLASSE_KEYWORDS):
            continue
        tekst = tag.get_text(strip=True)[:60]
        if not tekst:
            continue
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        score = 40 + _keyword_score(tag, _VOORRAAD_KLASSE_KEYWORDS)
        if _VOORRAAD_TEKST_PATRON.search(tekst):
            score = min(score + 30, 100)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst, score=score))

    # 3. Tekst-patroon in kleine elementen
    for tag in soup.find_all(["span", "div", "p", "strong"]):
        tekst = tag.get_text(strip=True)
        if len(tekst) > 50 or not _VOORRAAD_TEKST_PATRON.search(tekst):
            continue
        sel = _css_selector(tag)
        if sel in gezien:
            continue
        gezien.add(sel)
        score = 55 + _keyword_score(tag, _VOORRAAD_KLASSE_KEYWORDS)
        kandidaten.append(SelectorCandidate(selector=sel, sample_text=tekst[:60], score=min(score, 100)))

    kandidaten.sort(key=lambda c: c.score, reverse=True)
    return kandidaten[:5]


# ---------------------------------------------------------------------------
# Detectie JS-rendering en blokkade
# ---------------------------------------------------------------------------

def _detect_js_rendering(soup, html: str) -> bool:
    """Heuristiek: is JS-rendering waarschijnlijk vereist?"""
    # Zware <noscript> blokken
    noscript_content = " ".join(n.get_text() for n in soup.find_all("noscript"))
    if len(noscript_content) > 300:
        return True

    # Paginatitel noemt een JS-framework
    title_tag = soup.find("title")
    if title_tag and _JS_FRAMEWORK_TITLES.search(title_tag.get_text()):
        return True

    # Prijzen ontbreken in HTML maar staan wel in inline <script>
    price_in_html = bool(_PRIJS_TEKST_PATRON.search(soup.get_text()))
    price_in_script = bool(re.search(r'"price"\s*:\s*[\d.]+', html))
    if not price_in_html and price_in_script:
        return True

    # Veel __NEXT_DATA__ / window.__data JSON-blokken (SSR hydration)
    if html.count("__NEXT_DATA__") > 0 or html.count("window.__data") > 0:
        return True

    return False


def _detect_blokkade(http_status: int, html: str) -> tuple[bool, Optional[str]]:
    """Detecteer blokkade-signalen."""
    if http_status in (403, 429):
        return True, f"HTTP {http_status}"
    for pat in _BLOCKED_PATTERNS:
        if pat.search(html):
            return True, pat.pattern
    return False, None


# ---------------------------------------------------------------------------
# Aanbevolen actie (Nederlands)
# ---------------------------------------------------------------------------

def _aanbevolen_actie(
    geblokkeerd: bool,
    blok_reden: Optional[str],
    js_rendering: bool,
    prijs_ok: bool,
    titel_ok: bool,
) -> str:
    if geblokkeerd:
        return (
            f"De website blokkeert de scraper ({blok_reden}). "
            "Neem contact op met de webbeheerder of gebruik een andere methode. "
            "Anti-bot omzeiling valt buiten de scope van dit systeem."
        )
    if js_rendering:
        return (
            "De pagina laadt zijn inhoud via JavaScript. "
            "De HTML-scraper kan de prijs niet vinden in de ruwe HTML. "
            "Overweeg Playwright (headless browser) voor deze concurrent."
        )
    if not prijs_ok and not titel_ok:
        return (
            "Er zijn geen bruikbare elementen gevonden in de HTML. "
            "Controleer of de URL correct is en of de pagina publiek bereikbaar is."
        )
    if not prijs_ok:
        return (
            "Geen prijs-element gevonden met hoge zekerheid. "
            "Controleer de prijs-selector: zoek het prijselement in Chrome DevTools "
            "en kopieer de selector via 'Inspecteren → Copy → Copy selector'."
        )
    return (
        "Selecteer een van de bovenstaande kandidaat-selectors. "
        "Plak de selector in het veld 'Prijs' en klik op 'Test URL' om te bevestigen."
    )


# ---------------------------------------------------------------------------
# Hoofd-analyse functie
# ---------------------------------------------------------------------------

def analyse_html(
    url: str,
    html: str,
    http_status: int,
    is_admin: bool = False,
) -> AnalysisResult:
    """
    Analyseer een HTML-pagina en geef gerangschikte selector-suggesties terug.
    Schrijft nooit HTML naar de database.

    Parameters
    ----------
    url         : De URL die gescraped werd (voor context, niet opgeslagen)
    html        : De ruwe HTML-tekst
    http_status : De HTTP-statuscode die de scraper ontving
    is_admin    : Voeg een beknopte HTML-preview toe (alleen voor Admin-gebruikers)
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return AnalysisResult(
            aanbevolen_actie=(
                "beautifulsoup4 is niet geïnstalleerd. "
                "Installeer het pakket en herstart de server."
            )
        )

    soup = BeautifulSoup(html, "html.parser")

    geblokkeerd, blok_reden = _detect_blokkade(http_status, html)
    js_rendering = _detect_js_rendering(soup, html)

    prijs = _find_prijs_kandidaten(soup)
    titel = _find_titel_kandidaten(soup)
    voorraad = _find_voorraad_kandidaten(soup)

    prijs_ok = bool(prijs and prijs[0].score >= 50)
    titel_ok = bool(titel and titel[0].score >= 50)

    actie = _aanbevolen_actie(geblokkeerd, blok_reden, js_rendering, prijs_ok, titel_ok)

    html_preview: Optional[str] = None
    if is_admin and html:
        html_preview = html[:20_480]  # max 20 KB — nooit in DB

    return AnalysisResult(
        prijs_kandidaten=prijs,
        titel_kandidaten=titel,
        voorraad_kandidaten=voorraad,
        js_rendering_waarschijnlijk=js_rendering,
        geblokkeerd=geblokkeerd,
        blok_reden=blok_reden,
        aanbevolen_actie=actie,
        html_preview=html_preview,
    )
