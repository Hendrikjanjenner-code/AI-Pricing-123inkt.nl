"""
BigQuery analytische datalaag (masterprompt §3-§4).

PostgreSQL blijft de operationele bron. BigQuery is de historie-/analysebron
voor long-range queries (> 90 dagen), managementsnapshots en forecast-opslag.

Faalveilig: als BigQuery niet geconfigureerd of niet bereikbaar is, blijft de
applicatie volledig functioneren via de PostgreSQL fallback (§56).
"""
from .client import BigQueryClientWrapper, get_bq_client, bq_available

__all__ = ["BigQueryClientWrapper", "get_bq_client", "bq_available"]
