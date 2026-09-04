"""Pure Creditsafe-naar-concurrentprofiel preview; schrijft nooit naar de DB."""
from __future__ import annotations

from datetime import date
from typing import Any


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", []):
            return value
    return None


def _address(report: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    contact = report.get("contactInformation") or {}
    addresses = contact.get("mainAddress") or report.get("mainAddress") or summary.get("address") or {}
    return addresses if isinstance(addresses, dict) else {}


def build_profile_preview(
    report: dict[str, Any],
    *,
    search_result: dict[str, Any] | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Maak een allowlist-preview in het formaat van apply_profile_update."""
    summary = search_result or {}
    company = report.get("companySummary") or report.get("company") or report
    if not isinstance(company, dict):
        company = {}
    address = _address(report, summary)
    company_id = _first(company, "id", "companyId", "safeNo") or _first(
        summary, "id", "companyId", "safeNo"
    )
    legal_name = _first(company, "businessName", "legalName", "name") or _first(
        summary, "name", "businessName"
    )
    reg_no = _first(company, "companyRegistrationNumber", "registrationNumber", "regNo") or _first(
        summary, "regNo", "registrationNumber"
    )
    country = _first(address, "country", "countryCode") or _first(
        company, "country", "countryCode"
    )
    if isinstance(country, str) and len(country) > 2:
        country = None

    fields: dict[str, dict[str, Any]] = {}
    for field, value in (
        ("legal_name", legal_name),
        ("kvk_number", reg_no),
        ("headquarters_country", country.upper() if isinstance(country, str) else None),
    ):
        fields[field] = {
            "value": value,
            "status": "known" if value not in (None, "") else "unknown",
            "information_layer": "feit",
            "confidence": 0.9 if value not in (None, "") else None,
            "source": "creditsafe_report",
            "as_of_date": as_of_date or date.today().isoformat(),
        }

    credit = report.get("creditScore") or report.get("creditRating") or {}
    if not isinstance(credit, dict):
        credit = {}
    score = _first(credit, "currentCreditRating", "score", "value")
    status = _first(company, "companyStatus", "status") or _first(summary, "status")

    return {
        "dry_run": True,
        "will_write": False,
        "company_id": company_id,
        "profile_update": {"fields": fields},
        "evidence_preview": {
            "source_type": "creditsafe_report",
            "title": f"Creditsafe bedrijfsrapport — {legal_name or company_id or 'onbekend'}",
            "observed_date": as_of_date or date.today().isoformat(),
            "reliability": "hoog",
            "confidence": 0.9,
            "extracted_fact": {
                "company_id": company_id,
                "registration_number": reg_no,
                "company_status": status,
                "credit_score": score,
                "address": address or None,
            },
        },
        "unmapped": {
            "company_status": status,
            "credit_score": score,
        },
    }
