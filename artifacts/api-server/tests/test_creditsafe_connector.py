import httpx
import pytest

from connectors.creditsafe_connector import (
    CreditsafeCapabilityError,
    CreditsafeClient,
    CreditsafeError,
    run_single_company_smoke_test,
)
from services.creditsafe_profile import build_profile_preview


API_URL = "https://connect.creditsafe.com/v1"


def _client(handler):
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return CreditsafeClient(
        api_url=API_URL,
        username="fixture-user",
        password="fixture-password",
        client=http_client,
    )


def test_fixture_flow_auth_search_report_and_preview_without_writes():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, str(request.url.query)))
        if request.url.path.endswith("/authenticate"):
            assert request.read() == b'{"username":"fixture-user","password":"fixture-password"}'
            return httpx.Response(200, json={"token": "fixture-token"})
        assert request.headers["authorization"] == "Bearer fixture-token"
        if request.url.path.endswith("/companies"):
            return httpx.Response(200, json={"companies": [{
                "id": "NL-TEST-1", "name": "Voorbeeld B.V.",
                "regNo": "12345678", "status": "Active",
            }]})
        return httpx.Response(200, json={
            "companySummary": {
                "id": "NL-TEST-1", "businessName": "Voorbeeld B.V.",
                "companyRegistrationNumber": "12345678",
                "companyStatus": "Active",
            },
            "contactInformation": {"mainAddress": {"country": "NL", "city": "Utrecht"}},
            "creditScore": {"score": 72},
        })

    with _client(handler) as client:
        search = client.search_companies(country="NL", registration_number="12345678")
        report = client.get_company_report(search["companies"][0]["id"])
        preview = build_profile_preview(report, search_result=search["companies"][0],
                                        as_of_date="2026-09-04")

    assert [item[1] for item in seen] == [
        "/v1/authenticate", "/v1/companies", "/v1/companies/NL-TEST-1"
    ]
    assert preview["dry_run"] is True
    assert preview["will_write"] is False
    assert preview["profile_update"]["fields"]["legal_name"]["value"] == "Voorbeeld B.V."
    assert preview["profile_update"]["fields"]["kvk_number"]["value"] == "12345678"
    assert preview["unmapped"]["credit_score"] == 72


def test_report_call_is_never_retried_and_is_limited_to_one():
    report_requests = 0

    def handler(request):
        nonlocal report_requests
        if request.url.path.endswith("/authenticate"):
            return httpx.Response(200, json={"token": "fixture-token"})
        report_requests += 1
        return httpx.Response(503, json={"message": "unavailable"})

    with _client(handler) as client:
        with pytest.raises(CreditsafeError, match="HTTP 503"):
            client.get_company_report("NL-TEST-1")
        with pytest.raises(CreditsafeError, match="maximaal één rapportcall"):
            client.get_company_report("NL-TEST-1")

    assert report_requests == 1


def test_missing_report_capability_is_explicit():
    def handler(request):
        if request.url.path.endswith("/authenticate"):
            return httpx.Response(200, json={"token": "fixture-token"})
        return httpx.Response(403, json={"message": "not licensed"})

    with _client(handler) as client:
        with pytest.raises(CreditsafeCapabilityError, match="Company Credit Report"):
            client.get_company_report("NL-TEST-1")


def test_preview_marks_absent_allowlisted_values_unknown():
    preview = build_profile_preview({"companySummary": {"id": "NL-EMPTY"}})
    fields = preview["profile_update"]["fields"]
    assert fields["legal_name"]["status"] == "unknown"
    assert fields["kvk_number"]["status"] == "unknown"
    assert fields["headquarters_country"]["status"] == "unknown"


def test_connector_registry_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("CREDITSAFE_USERNAME", raising=False)
    monkeypatch.delenv("CREDITSAFE_PASSWORD", raising=False)
    from routes.connectors import CONNECTOR_FIELDS, _check_env_configured

    assert "creditsafe" in CONNECTOR_FIELDS
    assert _check_env_configured("creditsafe") is False


def test_smoke_test_stops_before_report_when_selection_is_ambiguous(monkeypatch):
    class FixtureClient:
        def __init__(self, **_kwargs):
            self.call_counts = {"authenticate": 1, "search": 0, "report": 0}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def search_companies(self, **_kwargs):
            self.call_counts["search"] += 1
            return {"companies": [{"id": "A"}, {"id": "B"}]}

        def get_company_report(self, _company_id):
            raise AssertionError("rapportcall mag niet plaatsvinden")

    monkeypatch.setattr(
        "connectors.creditsafe_connector.CreditsafeClient", FixtureClient
    )
    result = run_single_company_smoke_test(
        credentials={"username": "x", "password": "y"},
        country="NL",
        name="Dubbel resultaat",
    )
    assert result["status"] == "selection_required"
    assert result["call_counts"]["search"] == 1
    assert result["call_counts"]["report"] == 0
