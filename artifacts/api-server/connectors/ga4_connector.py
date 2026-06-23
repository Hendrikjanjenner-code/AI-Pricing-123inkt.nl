"""
GA4 Connector — Google Analytics 4 integratie.

Leest verbindingsconfig uit omgevingsvariabelen:
  GA4_PROPERTY_ID          (vereist)  bijv. '123456789'
  GA4_SERVICE_ACCOUNT_KEY  (vereist)  volledige JSON-sleutel als string (service account)

Functies retourneren altijd een lijst van dicts; bij ontbrekende config of
een API-fout wordt een ConnectorError opgegooid met een beschrijvende melding.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """Fout bij verbinding met of data-ophalen uit Google Analytics 4."""


def _get_credentials() -> dict:
    """Lees GA4-credentials uit omgevingsvariabelen."""
    property_id = os.environ.get("GA4_PROPERTY_ID", "").strip()
    sa_key_raw = os.environ.get("GA4_SERVICE_ACCOUNT_KEY", "").strip()

    if not property_id or not sa_key_raw:
        raise ConnectorError(
            "GA4 niet geconfigureerd. "
            "Stel GA4_PROPERTY_ID en GA4_SERVICE_ACCOUNT_KEY in als omgevingsvariabelen."
        )

    try:
        sa_key = json.loads(sa_key_raw)
    except json.JSONDecodeError as exc:
        raise ConnectorError(
            f"GA4_SERVICE_ACCOUNT_KEY is geen geldige JSON: {exc}"
        ) from exc

    return {"property_id": property_id, "service_account_key": sa_key}


def _make_client(creds: dict):
    """
    Maak een google-analytics-data BetaAnalyticsDataClient aan.
    Importeert de SDK pas hier zodat de connector bruikbaar blijft als de SDK ontbreekt.
    """
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.oauth2 import service_account
    except ImportError as exc:
        raise ConnectorError(
            "google-analytics-data SDK niet geïnstalleerd. "
            "Voer 'pip install google-analytics-data' uit."
        ) from exc

    sa_key = creds["service_account_key"]
    scopes = ["https://www.googleapis.com/auth/analytics.readonly"]
    gcp_credentials = service_account.Credentials.from_service_account_info(
        sa_key, scopes=scopes
    )
    return BetaAnalyticsDataClient(credentials=gcp_credentials)


def _property_path(creds: dict) -> str:
    return f"properties/{creds['property_id']}"


def _run_report(client, property_path: str, request_body: dict) -> list[dict]:
    """
    Voer een GA4 runReport-verzoek uit en zet de respons om naar een lijst van dicts.
    """
    try:
        from google.analytics.data_v1beta.types import RunReportRequest
        from google.api_core.exceptions import GoogleAPIError
    except ImportError as exc:
        raise ConnectorError("google-analytics-data SDK niet geïnstalleerd.") from exc

    try:
        request = RunReportRequest(property=property_path, **request_body)
        response = client.run_report(request)
    except Exception as exc:
        raise ConnectorError(f"GA4 API-verzoek mislukt: {exc}") from exc

    dimension_names = [h.name for h in response.dimension_headers]
    metric_names = [h.name for h in response.metric_headers]

    rows: list[dict] = []
    for row in response.rows:
        record: dict[str, Any] = {}
        for i, dim_val in enumerate(row.dimension_values):
            record[dimension_names[i]] = dim_val.value
        for i, met_val in enumerate(row.metric_values):
            raw = met_val.value
            try:
                record[metric_names[i]] = float(raw) if "." in raw else int(raw)
            except (ValueError, TypeError):
                record[metric_names[i]] = raw
        rows.append(record)

    return rows


def check_connection() -> dict:
    """
    Test de GA4-verbinding door een minimaal API-verzoek te doen.

    Returns:
        {
          'configured': bool,
          'reachable':  bool,
          'status':     str,    — 'ok' | 'not_configured' | 'unreachable' | 'auth_error'
          'message':    str,
        }
    """
    try:
        creds = _get_credentials()
    except ConnectorError as exc:
        return {
            "configured": False,
            "reachable": False,
            "status": "not_configured",
            "message": str(exc),
        }

    try:
        client = _make_client(creds)
        # Minimaal verzoek: één dag, één dimensie, één metric
        _run_report(
            client,
            _property_path(creds),
            {
                "date_ranges": [{"start_date": "yesterday", "end_date": "yesterday"}],
                "dimensions": [{"name": "date"}],
                "metrics": [{"name": "sessions"}],
                "limit": 1,
            },
        )
    except ConnectorError as exc:
        msg = str(exc)
        status = "auth_error" if "403" in msg or "401" in msg or "PERMISSION_DENIED" in msg else "unreachable"
        return {
            "configured": True,
            "reachable": False,
            "status": status,
            "message": msg,
        }
    except Exception as exc:
        return {
            "configured": True,
            "reachable": False,
            "status": "error",
            "message": f"GA4 onverwachte fout: {exc}",
        }

    return {
        "configured": True,
        "reachable": True,
        "status": "ok",
        "message": "GA4 verbinding succesvol.",
    }


def fetch_traffic_data(
    date_from: str,
    date_to: str,
    sku_ids: list[str] | None = None,
) -> list[dict]:
    """
    Haal dagelijkse traffic-metrics op per SKU-productpagina uit GA4.

    Dimensions: date, pagePath (gematch op sku_ids indien opgegeven)
    Metrics: sessions, screenPageViews, addToCarts, ecommercePurchases

    Args:
        date_from: 'YYYY-MM-DD'
        date_to:   'YYYY-MM-DD'
        sku_ids:   optionele filter (pagePath bevat een van de sku_ids)

    Returns:
        Lijst van dicts: {date, page_path, sessions, pageviews, add_to_cart, orders}
    """
    creds = _get_credentials()
    client = _make_client(creds)

    request_body: dict[str, Any] = {
        "date_ranges": [{"start_date": date_from, "end_date": date_to}],
        "dimensions": [{"name": "date"}, {"name": "pagePath"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "screenPageViews"},
            {"name": "addToCarts"},
            {"name": "ecommercePurchases"},
        ],
        "order_bys": [{"dimension": {"dimension_name": "date"}}],
        "limit": 10000,
    }

    if sku_ids:
        request_body["dimension_filter"] = {
            "or_group": {
                "expressions": [
                    {
                        "filter": {
                            "field_name": "pagePath",
                            "string_filter": {"match_type": "CONTAINS", "value": sku_id},
                        }
                    }
                    for sku_id in sku_ids
                ]
            }
        }

    raw = _run_report(client, _property_path(creds), request_body)

    rows = []
    for r in raw:
        rows.append(
            {
                "date": r.get("date"),
                "page_path": r.get("pagePath"),
                "sessions": r.get("sessions", 0),
                "pageviews": r.get("screenPageViews", 0),
                "add_to_cart": r.get("addToCarts", 0),
                "orders": r.get("ecommercePurchases", 0),
            }
        )

    logger.info(
        "GA4: %d traffic-records opgehaald (%s → %s)", len(rows), date_from, date_to
    )
    return rows


def fetch_conversion_data(
    date_from: str,
    date_to: str,
    segment: str = "all",
) -> list[dict]:
    """
    Haal dagelijkse conversie-metrics op uit GA4.

    Metrics: sessions, addToCarts, ecommercePurchases, purchaseRevenue

    Args:
        date_from: 'YYYY-MM-DD'
        date_to:   'YYYY-MM-DD'
        segment:   'all' | 'organic' | 'paid' | 'direct' | 'email' | 'social'

    Returns:
        Lijst van dicts: {date, channel, sessions, add_to_cart, orders, revenue, conversion_rate}
    """
    creds = _get_credentials()
    client = _make_client(creds)

    request_body: dict[str, Any] = {
        "date_ranges": [{"start_date": date_from, "end_date": date_to}],
        "dimensions": [{"name": "date"}, {"name": "sessionDefaultChannelGrouping"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "addToCarts"},
            {"name": "ecommercePurchases"},
            {"name": "purchaseRevenue"},
        ],
        "order_bys": [{"dimension": {"dimension_name": "date"}}],
        "limit": 10000,
    }

    if segment != "all":
        _CHANNEL_MAP = {
            "organic": "Organic Search",
            "paid": "Paid Search",
            "direct": "Direct",
            "email": "Email",
            "social": "Organic Social",
        }
        ga4_channel = _CHANNEL_MAP.get(segment, segment)
        request_body["dimension_filter"] = {
            "filter": {
                "field_name": "sessionDefaultChannelGrouping",
                "string_filter": {"match_type": "EXACT", "value": ga4_channel},
            }
        }

    raw = _run_report(client, _property_path(creds), request_body)

    rows = []
    for r in raw:
        sessions = r.get("sessions", 0) or 0
        orders = r.get("ecommercePurchases", 0) or 0
        conv_rate = round(orders / sessions, 4) if sessions > 0 else 0.0
        rows.append(
            {
                "date": r.get("date"),
                "channel": r.get("sessionDefaultChannelGrouping"),
                "sessions": sessions,
                "add_to_cart": r.get("addToCarts", 0),
                "orders": orders,
                "revenue": r.get("purchaseRevenue", 0.0),
                "conversion_rate": conv_rate,
            }
        )

    logger.info(
        "GA4: %d conversierecords opgehaald (%s → %s, segment=%s)",
        len(rows), date_from, date_to, segment,
    )
    return rows


def fetch_channel_breakdown(
    date_from: str,
    date_to: str,
) -> list[dict]:
    """
    Haal traffic per kanaal en apparaat op uit GA4 voor rapportage.

    Returns:
        Lijst van dicts: {date, channel, device, sessions, pageviews, orders}
    """
    creds = _get_credentials()
    client = _make_client(creds)

    request_body: dict[str, Any] = {
        "date_ranges": [{"start_date": date_from, "end_date": date_to}],
        "dimensions": [
            {"name": "date"},
            {"name": "sessionDefaultChannelGrouping"},
            {"name": "deviceCategory"},
        ],
        "metrics": [
            {"name": "sessions"},
            {"name": "screenPageViews"},
            {"name": "ecommercePurchases"},
        ],
        "order_bys": [{"dimension": {"dimension_name": "date"}}],
        "limit": 10000,
    }

    raw = _run_report(client, _property_path(creds), request_body)

    rows = [
        {
            "date": r.get("date"),
            "channel": r.get("sessionDefaultChannelGrouping"),
            "device": r.get("deviceCategory"),
            "sessions": r.get("sessions", 0),
            "pageviews": r.get("screenPageViews", 0),
            "orders": r.get("ecommercePurchases", 0),
        }
        for r in raw
    ]

    logger.info("GA4: %d kanaalrecords opgehaald (%s → %s)", len(rows), date_from, date_to)
    return rows


def fetch_sku_pageviews(
    sku_ids: list[str],
    date_from: str,
    date_to: str,
) -> list[dict]:
    """
    Haal paginaweergaven op per specifieke SKU-ID uit GA4.

    Matcht op pagePath die de sku_id bevat (bijv. /product/PAP001).

    Returns:
        Lijst van dicts: {sku_id, date, pageviews, sessions, add_to_cart, orders}
    """
    if not sku_ids:
        raise ConnectorError("fetch_sku_pageviews vereist minimaal één SKU-ID.")

    creds = _get_credentials()
    client = _make_client(creds)

    request_body: dict[str, Any] = {
        "date_ranges": [{"start_date": date_from, "end_date": date_to}],
        "dimensions": [{"name": "date"}, {"name": "pagePath"}],
        "metrics": [
            {"name": "screenPageViews"},
            {"name": "sessions"},
            {"name": "addToCarts"},
            {"name": "ecommercePurchases"},
        ],
        "dimension_filter": {
            "or_group": {
                "expressions": [
                    {
                        "filter": {
                            "field_name": "pagePath",
                            "string_filter": {"match_type": "CONTAINS", "value": sku_id},
                        }
                    }
                    for sku_id in sku_ids
                ]
            }
        },
        "order_bys": [{"dimension": {"dimension_name": "date"}}],
        "limit": 10000,
    }

    raw = _run_report(client, _property_path(creds), request_body)

    results: list[dict] = []
    for r in raw:
        page_path = r.get("pagePath", "")
        matched_sku = next((s for s in sku_ids if s in page_path), page_path)
        results.append(
            {
                "sku_id": matched_sku,
                "date": r.get("date"),
                "pageviews": r.get("screenPageViews", 0),
                "sessions": r.get("sessions", 0),
                "add_to_cart": r.get("addToCarts", 0),
                "orders": r.get("ecommercePurchases", 0),
            }
        )

    logger.info(
        "GA4: %d pageview-records opgehaald voor %d SKU's (%s → %s)",
        len(results), len(sku_ids), date_from, date_to,
    )
    return results
