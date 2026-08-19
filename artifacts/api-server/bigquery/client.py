"""
BigQuery client wrapper — faalveilig en credential-agnostisch.

Credentials worden geconfigureerd via één van:
  BQ_SERVICE_ACCOUNT_JSON   — JSON-inhoud van een service-account sleutel
  BQ_PROJECT_ID             — project-id; GOOGLE_APPLICATION_CREDENTIALS of
                              Application Default Credentials doen de auth

Geen credentials? Dan is bq_available() False en valt alles terug op
PostgreSQL. De applicatie start en draait altijd, ook zonder BigQuery.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("uvicorn.error")

# Module-level singleton
_client: Any = None          # google.cloud.bigquery.Client of None
_client_error: str = ""      # laatste foutbericht voor /api/bigquery/status
_last_check_ts: float = 0.0  # epoch-timestamp van de laatste client-init-poging
_CHECK_INTERVAL = 300        # 5 min tussen herverbindingspogingen


def _build_client() -> tuple[Any, str]:
    """
    Probeer een BigQuery-client te maken op basis van omgevingsvariabelen.
    Geeft (client, "")  terug bij succes,  (None, reden)  bij mislukking.
    """
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        sa_json = os.environ.get("BQ_SERVICE_ACCOUNT_JSON", "").strip()
        project_id = os.environ.get("BQ_PROJECT_ID", "").strip()

        if sa_json:
            info = json.loads(sa_json)
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            project = project_id or info.get("project_id", "")
            client = bigquery.Client(project=project, credentials=creds)
        elif project_id:
            # Application Default Credentials / GOOGLE_APPLICATION_CREDENTIALS
            client = bigquery.Client(project=project_id)
        else:
            return None, (
                "BigQuery niet geconfigureerd. Stel BQ_SERVICE_ACCOUNT_JSON "
                "of BQ_PROJECT_ID in als omgevingsvariabele."
            )

        return client, ""

    except ImportError:
        return None, "google-cloud-bigquery pakket niet geïnstalleerd."
    except Exception as exc:
        return None, f"BigQuery client init mislukt: {exc}"


def _get_singleton() -> tuple[Any, str]:
    global _client, _client_error, _last_check_ts
    now = time.monotonic()
    if _client is not None:
        return _client, ""
    if now - _last_check_ts < _CHECK_INTERVAL:
        return None, _client_error
    _last_check_ts = now
    client, err = _build_client()
    _client = client
    _client_error = err
    if err:
        logger.warning("BigQuery: %s (applicatie blijft werken via PostgreSQL)", err)
    else:
        logger.info("BigQuery: client succesvol aangemaakt.")
    return _client, _client_error


def get_bq_client() -> Optional[Any]:
    """Geeft de BigQuery-client terug, of None als die niet beschikbaar is."""
    client, _ = _get_singleton()
    return client


def bq_available() -> bool:
    """True als er een werkende BigQuery-verbinding beschikbaar is."""
    return get_bq_client() is not None


def bq_configured() -> bool:
    """
    True als BigQuery bewust is geconfigureerd (credentials/omgevingsvariabelen
    aanwezig), los van of de client-initialisatie slaagt. Hiermee kan een
    geplande sync 'niet geconfigureerd' (overslaan) onderscheiden van
    'geconfigureerd maar kapot' (fout melden).
    """
    return bool(
        os.environ.get("BQ_SERVICE_ACCOUNT_JSON", "").strip()
        or os.environ.get("BQ_PROJECT_ID", "").strip()
    )


def bq_last_error() -> str:
    """Laatste client-initialisatiefout ('' als er geen fout is)."""
    _, err = _get_singleton()
    return err


def bq_status() -> dict:
    """Status-dict voor /api/bigquery/status."""
    client, err = _get_singleton()
    project = ""
    if client is not None:
        try:
            project = client.project or ""
        except Exception:
            pass
    return {
        "available": client is not None,
        "project": project,
        "error": err or None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


class BigQueryClientWrapper:
    """
    Dunne wrapper die een BigQuery-query uitvoert en scan-bytes registreert.

    Gebruik:
        bq = BigQueryClientWrapper()
        rows, meta = bq.query("SELECT ... FROM `project.dataset.table`")
        # meta: {"bytes_scanned": int, "duration_ms": int, "ok": bool, "error": str|None}
    """

    def __init__(self):
        self._client = get_bq_client()

    def is_available(self) -> bool:
        return self._client is not None

    def query(self, sql: str, params: Optional[list] = None) -> tuple[list[dict], dict]:
        """
        Voer een BigQuery-query uit.

        Geeft (rijen_als_dicts, meta_dict) terug.
        Bij een fout zijn rijen leeg en meta["ok"] == False.
        """
        meta: dict = {"bytes_scanned": 0, "duration_ms": 0, "ok": False, "error": None}
        if self._client is None:
            meta["error"] = "BigQuery niet beschikbaar"
            return [], meta

        t0 = time.monotonic()
        try:
            job_config = None
            if params:
                from google.cloud.bigquery import QueryJobConfig
                job_config = QueryJobConfig(query_parameters=params)

            job = self._client.query(sql, job_config=job_config)
            rows = [dict(row) for row in job.result()]
            stats = job.query_plan  # noqa – trigger metadata fetch
            meta["bytes_scanned"] = job.total_bytes_processed or 0
            meta["ok"] = True
        except Exception as exc:
            logger.error("BigQuery query fout: %s\nSQL: %s", exc, sql[:500])
            meta["error"] = str(exc)
            rows = []

        meta["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rows, meta

    def dataset_ref(self, dataset_id: str) -> Any:
        if self._client is None:
            raise RuntimeError("BigQuery niet beschikbaar")
        return self._client.dataset(dataset_id)

    def get_project(self) -> str:
        if self._client is None:
            return ""
        return self._client.project or ""
