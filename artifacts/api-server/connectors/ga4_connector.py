"""
GA4 Connector stub — Google Analytics 4 integratie.

Alle functies gooien NotImplementedError met een beschrijvende melding.
Vervang de stubs door echte implementaties zodra GA4 API-toegang beschikbaar is.

Vereiste GA4-velden (8 dimensies/metrics):
- sessions          (integer)  Sessies per SKU / categorie
- pageviews         (integer)  Paginaweergaven per SKU
- add_to_cart       (integer)  Toevoegingen aan winkelwagen
- orders            (integer)  Bestellingen
- conversion_rate   (float)    Conversieratio (orders / sessions)
- channel           (string)   Verkeerskanaal (organic, paid, direct, ...)
- device            (string)   Apparaattype (desktop, mobile, tablet)
- landing_page      (string)   Landingspagina-URL of slug
"""


def validate_ga4_credentials(credentials: dict) -> dict:
    """
    Valideer GA4 API-credentials (service account of OAuth2).

    Args:
        credentials: {'property_id': str, 'service_account_key': dict | None,
                      'oauth_token': str | None}

    Returns:
        dict met keys 'valid' (bool), 'errors' (list[str])

    Raises:
        NotImplementedError: altijd, GA4 API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "GA4 API is nog niet gekoppeld. "
        "Gebruik op dit moment de CSV-importmodule (POST /api/uploads/traffic) "
        "om traffic-data te importeren."
    )


def fetch_sku_traffic(
    credentials: dict,
    sku_ids: list[str],
    date_from: str,
    date_to: str,
) -> list[dict]:
    """
    Haal traffic-metrics op per SKU-productpagina uit GA4.

    Args:
        credentials: {'property_id': str, 'service_account_key': dict}
        sku_ids:     lijst van SKU-ID's (gematch op pagina-slug / item_id)
        date_from:   'YYYY-MM-DD'
        date_to:     'YYYY-MM-DD'

    Returns:
        list van dicts met de 8 vereiste velden per SKU per dag

    Raises:
        NotImplementedError: altijd, GA4 API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "fetch_sku_traffic is nog niet geïmplementeerd. "
        "Importeer traffic-data via CSV (POST /api/uploads/traffic)."
    )


def fetch_category_traffic(
    credentials: dict,
    categories: list[str],
    date_from: str,
    date_to: str,
) -> list[dict]:
    """
    Haal traffic-metrics op per categorie-landingspagina uit GA4.

    Args:
        credentials: {'property_id': str, 'service_account_key': dict}
        categories:  lijst van categorienamen
        date_from:   'YYYY-MM-DD'
        date_to:     'YYYY-MM-DD'

    Returns:
        list van dicts met traffic-metrics per categorie per dag

    Raises:
        NotImplementedError: altijd, GA4 API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "fetch_category_traffic is nog niet geïmplementeerd. "
        "Importeer traffic-data via CSV (POST /api/uploads/traffic)."
    )


def fetch_conversion_data(
    credentials: dict,
    date_from: str,
    date_to: str,
    segment: str = "all",
) -> list[dict]:
    """
    Haal conversie-metrics op uit GA4 (add_to_cart, orders, conversion_rate).

    Args:
        credentials: {'property_id': str, 'service_account_key': dict}
        date_from:   'YYYY-MM-DD'
        date_to:     'YYYY-MM-DD'
        segment:     'all' | 'organic' | 'paid' | 'direct'

    Returns:
        list van conversie-dicts per SKU/categorie per dag

    Raises:
        NotImplementedError: altijd, GA4 API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "fetch_conversion_data is nog niet geïmplementeerd. "
        "Importeer conversiedata via CSV (POST /api/uploads/traffic)."
    )
