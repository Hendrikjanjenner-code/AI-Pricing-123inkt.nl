"""Minimale Creditsafe Connect-client.

De client doet uit zichzelf niets: zonder expliciete credentials wordt geen
netwerkverbinding geopend. Een instantie staat maximaal één zoek- en één
rapportcall toe, zodat een latere smoke-test niet ongemerkt kan verbreden.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from connectors.net import validate_external_url


DEFAULT_API_URL = "https://connect.creditsafe.com/v1"
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


class CreditsafeError(Exception):
    """Veilige, gebruikersgerichte Creditsafe-fout."""


class CreditsafeNotConfigured(CreditsafeError):
    pass


class CreditsafeCapabilityError(CreditsafeError):
    pass


def _get_credentials(db=None) -> dict[str, str]:
    if db is not None:
        try:
            from connectors.crypto import decrypt_credentials
            import models

            cfg = db.query(models.ConnectorConfig).filter(
                models.ConnectorConfig.connector_name == "creditsafe"
            ).first()
            if cfg and cfg.encrypted_credentials:
                stored = decrypt_credentials(cfg.encrypted_credentials)
                if stored.get("username") and stored.get("password"):
                    return {
                        "api_url": (stored.get("api_url") or DEFAULT_API_URL).rstrip("/"),
                        "username": stored["username"],
                        "password": stored["password"],
                    }
        except Exception:
            pass

    username = os.environ.get("CREDITSAFE_USERNAME", "")
    password = os.environ.get("CREDITSAFE_PASSWORD", "")
    if not username or not password:
        raise CreditsafeNotConfigured(
            "Creditsafe is niet geconfigureerd. Voeg later CREDITSAFE_USERNAME "
            "en CREDITSAFE_PASSWORD toe via Replit Secrets."
        )
    return {
        "api_url": os.environ.get("CREDITSAFE_API_URL", DEFAULT_API_URL).rstrip("/"),
        "username": username,
        "password": password,
    }


class CreditsafeClient:
    def __init__(
        self,
        *,
        api_url: str,
        username: str,
        password: str,
        client: httpx.Client | None = None,
    ):
        if not username or not password:
            raise CreditsafeNotConfigured("Creditsafe-gebruikersnaam en -wachtwoord zijn verplicht.")
        self.api_url = api_url.rstrip("/")
        validate_external_url(self.api_url)
        self.username = username
        self.password = password
        self._client = client or httpx.Client(timeout=_TIMEOUT, follow_redirects=False)
        self._owns_client = client is None
        self._token: str | None = None
        self.call_counts = {"authenticate": 0, "search": 0, "report": 0}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "CreditsafeClient":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _json(self, response: httpx.Response, operation: str) -> dict[str, Any]:
        if response.status_code in (401, 403):
            if operation == "authenticate":
                raise CreditsafeError("Creditsafe-authenticatie is geweigerd.")
            raise CreditsafeCapabilityError(
                f"Creditsafe staat '{operation}' niet toe voor dit abonnement of deze gebruiker."
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise CreditsafeError(
                f"Creditsafe gaf HTTP {exc.response.status_code} bij {operation}."
            ) from None
        try:
            data = response.json()
        except ValueError:
            raise CreditsafeError(f"Creditsafe gaf geen geldige JSON bij {operation}.") from None
        if not isinstance(data, dict):
            raise CreditsafeError(f"Creditsafe gaf een onverwacht antwoord bij {operation}.")
        return data

    def authenticate(self) -> dict[str, Any]:
        if self._token:
            return {"token": self._token, "cached": True}
        self.call_counts["authenticate"] += 1
        try:
            response = self._client.post(
                f"{self.api_url}/authenticate",
                json={"username": self.username, "password": self.password},
                headers={"Accept": "application/json"},
            )
        except httpx.RequestError:
            raise CreditsafeError("Creditsafe is niet bereikbaar tijdens authenticatie.") from None
        data = self._json(response, "authenticate")
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise CreditsafeError("Creditsafe-authenticatie gaf geen token terug.")
        self._token = token
        return {"token": token, "cached": False}

    def _headers(self) -> dict[str, str]:
        token = self.authenticate()["token"]
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def search_companies(
        self,
        *,
        country: str,
        name: str | None = None,
        registration_number: str | None = None,
    ) -> dict[str, Any]:
        if self.call_counts["search"] >= 1:
            raise CreditsafeError("De proef staat maximaal één bedrijfszoekopdracht toe.")
        if not name and not registration_number:
            raise ValueError("Naam of registratienummer is verplicht.")
        self.call_counts["search"] += 1
        params: dict[str, str | int] = {"countries": country.upper(), "pageSize": 10}
        if name:
            params["name"] = name
        if registration_number:
            params["regNo"] = registration_number
        try:
            response = self._client.get(
                f"{self.api_url}/companies", params=params, headers=self._headers()
            )
        except httpx.RequestError:
            raise CreditsafeError("Creditsafe is niet bereikbaar tijdens bedrijfszoeken.") from None
        return self._json(response, "Company Search")

    def get_company_report(
        self, company_id: str, *, language: str = "EN"
    ) -> dict[str, Any]:
        if self.call_counts["report"] >= 1:
            raise CreditsafeError("De proef staat maximaal één rapportcall toe.")
        if not company_id:
            raise ValueError("Creditsafe company-id is verplicht.")
        self.call_counts["report"] += 1
        try:
            response = self._client.get(
                f"{self.api_url}/companies/{company_id}",
                params={"language": language.upper()},
                headers=self._headers(),
            )
        except httpx.RequestError:
            raise CreditsafeError("Creditsafe is niet bereikbaar tijdens rapportophalen.") from None
        return self._json(response, "Company Credit Report")


def check_connection(db=None) -> dict[str, Any]:
    """Authenticeer alleen; zoeken en rapportophalen gebeuren hier nooit."""
    try:
        creds = _get_credentials(db=db)
    except CreditsafeNotConfigured as exc:
        return {
            "configured": False,
            "reachable": False,
            "status": "not_configured",
            "activation_status": "not_configured",
            "message": str(exc),
        }

    try:
        with CreditsafeClient(
            api_url=creds["api_url"],
            username=creds["username"],
            password=creds["password"],
        ) as client:
            client.authenticate()
    except CreditsafeCapabilityError as exc:
        return {
            "configured": True, "reachable": True, "status": "capability_error",
            "activation_status": "ready_for_live_validation", "message": str(exc),
        }
    except CreditsafeError as exc:
        return {
            "configured": True, "reachable": False, "status": "error",
            "activation_status": "ready_for_live_validation", "message": str(exc),
        }

    return {
        "configured": True,
        "reachable": True,
        "status": "ok",
        "activation_status": "ready_for_live_validation",
        "message": "Authenticatie geslaagd; zoek- en rapportrechten zijn nog niet live gevalideerd.",
    }


def run_single_company_smoke_test(
    *,
    credentials: dict[str, str],
    country: str,
    name: str | None = None,
    registration_number: str | None = None,
) -> dict[str, Any]:
    """Latere, expliciete smoke-flow: exact één search en hoogstens één report.

    De functie persisteert niets en kiest nooit stilletjes tussen meerdere
    zoekresultaten. Daardoor kan de caller eerst een ondubbelzinnig testbedrijf
    opgeven en de resulterende preview laten beoordelen.
    """
    from services.creditsafe_profile import build_profile_preview

    with CreditsafeClient(
        api_url=credentials.get("api_url") or DEFAULT_API_URL,
        username=credentials.get("username", ""),
        password=credentials.get("password", ""),
    ) as client:
        search = client.search_companies(
            country=country, name=name, registration_number=registration_number
        )
        companies = search.get("companies")
        if not isinstance(companies, list) or len(companies) != 1:
            return {
                "status": "selection_required",
                "result_count": len(companies) if isinstance(companies, list) else 0,
                "call_counts": dict(client.call_counts),
                "preview": None,
            }
        selected = companies[0]
        company_id = selected.get("id") if isinstance(selected, dict) else None
        if not company_id:
            raise CreditsafeError("Het zoekresultaat bevat geen Creditsafe company-id.")
        report = client.get_company_report(str(company_id))
        return {
            "status": "preview_ready",
            "result_count": 1,
            "call_counts": dict(client.call_counts),
            "preview": build_profile_preview(report, search_result=selected),
        }
