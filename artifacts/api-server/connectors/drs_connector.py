"""
DRS Connector stub — Dynamisch Retail Systeem integratie.

Alle functies gooien NotImplementedError met een beschrijvende melding.
Vervang de stubs door echte implementaties zodra de DRS API beschikbaar is.

Vereiste DRS-velden:
- product_id       (string)       Interne product-ID in DRS
- sku_code         (string)       EAN / artikelnummer
- description      (string)       Productomschrijving
- category_code    (string)       Categoriecode
- cost_price       (decimal)      Inkoopprijs excl. BTW
- selling_price    (decimal)      Huidige verkoopprijs incl. BTW
- stock_qty        (integer)      Actuele voorraad
- sales_qty_7d     (integer)      Verkopen afgelopen 7 dagen
- sales_qty_30d    (integer)      Verkopen afgelopen 30 dagen
- last_sale_date   (date)         Datum laatste verkoop
- supplier_id      (string)       Leverancier-ID
"""


def validate_drs_payload(payload: dict) -> dict:
    """
    Valideer een DRS-datapakket op vereiste velden en datatypes.

    Returns:
        dict met keys 'valid' (bool), 'errors' (list[str])

    Raises:
        NotImplementedError: altijd, DRS API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "DRS API is nog niet gekoppeld. "
        "Gebruik op dit moment de CSV-importmodule (POST /api/uploads/products) "
        "om productdata te importeren."
    )


def import_products_from_drs(credentials: dict, filters: dict | None = None) -> list[dict]:
    """
    Haal productcatalogus op uit DRS via de REST API.

    Args:
        credentials: {'api_key': str, 'base_url': str, 'tenant_id': str}
        filters:     optioneel {'category': str, 'updated_after': date}

    Returns:
        list van product-dicts conform DRS-schema

    Raises:
        NotImplementedError: altijd, DRS API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "import_products_from_drs is nog niet geïmplementeerd. "
        "Wacht tot DRS API-toegang verleend is (zie technische checklist)."
    )


def import_sales_from_drs(credentials: dict, date_from: str, date_to: str) -> list[dict]:
    """
    Haal dagelijkse verkoopdata op uit DRS.

    Args:
        credentials: {'api_key': str, 'base_url': str, 'tenant_id': str}
        date_from:   'YYYY-MM-DD'
        date_to:     'YYYY-MM-DD'

    Returns:
        list van verkooprijen

    Raises:
        NotImplementedError: altijd, DRS API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "import_sales_from_drs is nog niet geïmplementeerd. "
        "Importeer verkoophistorie via CSV (POST /api/uploads/sales)."
    )


def import_stock_from_drs(credentials: dict) -> list[dict]:
    """
    Haal actuele voorraadstanden op uit DRS.

    Args:
        credentials: {'api_key': str, 'base_url': str, 'tenant_id': str}

    Returns:
        list van voorraad-dicts: {'sku_id': str, 'stock_qty': int, 'date': str}

    Raises:
        NotImplementedError: altijd, DRS API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "import_stock_from_drs is nog niet geïmplementeerd. "
        "Importeer voorraaddata via CSV (POST /api/uploads/inventory)."
    )


def import_price_history_from_drs(
    credentials: dict, sku_ids: list[str], lookback_days: int = 90
) -> list[dict]:
    """
    Haal prijshistorie op uit DRS voor een set SKU's.

    Args:
        credentials:   {'api_key': str, 'base_url': str, 'tenant_id': str}
        sku_ids:       lijst van SKU-ID's
        lookback_days: aantal historische dagen (standaard 90)

    Returns:
        list van prijsrijen: {'sku_id': str, 'date': str, 'price': float}

    Raises:
        NotImplementedError: altijd, DRS API nog niet geïmplementeerd.
    """
    raise NotImplementedError(
        "import_price_history_from_drs is nog niet geïmplementeerd. "
        "Importeer prijshistorie via CSV (POST /api/uploads/prices)."
    )
