"""
Microsoft Advertising (Bing Ads) connector.

Credentials (DB via ConnectorConfig of omgevingsvariabelen):
  - developer_token  (MS_ADS_DEVELOPER_TOKEN)
  - customer_id      (MS_ADS_CUSTOMER_ID)
  - account_id       (MS_ADS_ACCOUNT_ID)
  - client_id        (MS_ADS_CLIENT_ID)
  - client_secret    (MS_ADS_CLIENT_SECRET)
  - refresh_token    (MS_ADS_REFRESH_TOKEN)

De verbindingscheck verifieert de OAuth-refresh-flow tegen Microsoft Identity
en een lichte SOAP GetUser-aanroep tegen de Customer Management-service.

Rapportagedata (campagnekosten) wordt opgehaald via de asynchrone Reporting-
service v13: SubmitGenerateReport → PollGenerateReport → CSV-download (ZIP).
Rijen landen idempotent in FactMarketingCostDaily (delete + insert per
datum/campagne, sku_id="MSCAMPAGNE:<id>", category="Microsoft Ads").
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

logger = logging.getLogger(__name__)

TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
SCOPE = "https://ads.microsoft.com/msads.manage offline_access"
CUSTOMER_MGMT_URL = "https://clientcenter.api.bingads.microsoft.com/Api/CustomerManagement/v13/CustomerManagementService.svc"
REPORTING_URL = "https://reporting.api.bingads.microsoft.com/Api/Advertiser/Reporting/v13/ReportingService.svc"
REPORT_NS = "https://bingads.microsoft.com/Reporting/v13"
POLL_INTERVAL_S = 5
POLL_MAX_ATTEMPTS = 24  # max ~2 minuten wachten

REQUIRED_KEYS = ["developer_token", "customer_id", "account_id", "client_id", "client_secret", "refresh_token"]
ENV_KEYS = {
    "developer_token": "MS_ADS_DEVELOPER_TOKEN",
    "customer_id": "MS_ADS_CUSTOMER_ID",
    "account_id": "MS_ADS_ACCOUNT_ID",
    "client_id": "MS_ADS_CLIENT_ID",
    "client_secret": "MS_ADS_CLIENT_SECRET",
    "refresh_token": "MS_ADS_REFRESH_TOKEN",
}


class ConnectorError(Exception):
    """Configuratie- of verbindingsfout voor de Microsoft Ads connector."""


def _get_credentials(db=None) -> dict:
    if db is not None:
        try:
            import models
            from connectors.crypto import decrypt_credentials
            cfg = db.query(models.ConnectorConfig).filter(
                models.ConnectorConfig.connector_name == "microsoft_ads"
            ).first()
            if cfg and cfg.encrypted_credentials:
                creds = decrypt_credentials(cfg.encrypted_credentials)
                if all(creds.get(k) for k in REQUIRED_KEYS):
                    return creds
        except Exception:
            logger.warning("Microsoft Ads DB-config kon niet worden gelezen; val terug op env.", exc_info=True)
    creds = {k: os.environ.get(env, "").strip() for k, env in ENV_KEYS.items()}
    if not all(creds.values()):
        raise ConnectorError(
            "Microsoft Ads is niet geconfigureerd. Sla developer token, "
            "customer/account ID en OAuth-gegevens op via de Connectoren-pagina."
        )
    return creds


def _access_token(creds: dict) -> str:
    import httpx
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(TOKEN_URL, data={
                "grant_type": "refresh_token",
                "client_id": creds["client_id"],
                "client_secret": creds["client_secret"],
                "refresh_token": creds["refresh_token"],
                "scope": SCOPE,
            })
    except Exception as exc:
        raise ConnectorError(f"Microsoft Identity niet bereikbaar: {str(exc)[:150]}")
    if resp.status_code != 200:
        raise ConnectorError(f"OAuth-refresh mislukt (HTTP {resp.status_code}): {resp.text[:150]}")
    token = resp.json().get("access_token")
    if not token:
        raise ConnectorError("OAuth-respons bevat geen access_token.")
    return token


def _soap_get_user(token: str, developer_token: str) -> int:
    """Lichte SOAP GetUser-aanroep; retourneert de HTTP-statuscode."""
    envelope = f"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Header xmlns="https://bingads.microsoft.com/Customer/v13">
    <Action mustUnderstand="1">GetUser</Action>
    <AuthenticationToken>{token}</AuthenticationToken>
    <DeveloperToken>{developer_token}</DeveloperToken>
  </s:Header>
  <s:Body>
    <GetUserRequest xmlns="https://bingads.microsoft.com/Customer/v13">
      <UserId i:nil="true" xmlns:i="http://www.w3.org/2001/XMLSchema-instance" />
    </GetUserRequest>
  </s:Body>
</s:Envelope>"""
    import httpx
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            CUSTOMER_MGMT_URL,
            content=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "GetUser"},
        )
    return resp.status_code


def check_connection(db=None) -> dict:
    try:
        creds = _get_credentials(db=db)
    except ConnectorError as exc:
        return {"status": "not_configured", "message": str(exc)}
    try:
        token = _access_token(creds)
    except ConnectorError as exc:
        msg = str(exc)
        if "invalid_grant" in msg or "400" in msg or "401" in msg:
            return {"status": "auth_error", "message": msg}
        return {"status": "unreachable" if "bereikbaar" in msg else "error", "message": msg}
    try:
        code = _soap_get_user(token, creds["developer_token"])
        if code == 200:
            return {"status": "ok",
                    "message": f"Verbonden met Microsoft Ads (customer {creds['customer_id']})."}
        if code in (401, 403):
            return {"status": "auth_error",
                    "message": f"Toegang geweigerd ({code}) door de Microsoft Ads API. Controleer het developer token."}
        return {"status": "error", "message": f"Microsoft Ads API antwoordde met HTTP {code}."}
    except Exception as exc:
        return {"status": "unreachable", "message": str(exc)[:200]}


def verify_connection(db=None) -> dict:
    """
    Sync-stap: verifieer de volledige keten (OAuth + API). Microsoft Ads-rapportage
    verloopt via de asynchrone Reporting-service; deze sync bevestigt de koppeling
    en houdt de bronstatus actueel. Raise ConnectorError bij niet geconfigureerd.
    """
    creds = _get_credentials(db=db)  # raises ConnectorError indien niet geconfigureerd
    token = _access_token(creds)
    code = _soap_get_user(token, creds["developer_token"])
    if code in (401, 403):
        raise ConnectorError(f"Toegang geweigerd ({code}) door de Microsoft Ads API.")
    if code != 200:
        raise ConnectorError(f"Microsoft Ads API antwoordde met HTTP {code}.")
    return {"verified": True, "customer_id": creds["customer_id"], "account_id": creds["account_id"]}


# ── Reporting-service v13 (asynchroon: submit → poll → download) ────────────

def _soap_headers(action: str, token: str, creds: dict) -> tuple[str, dict]:
    header = f"""  <s:Header xmlns="{REPORT_NS}">
    <Action mustUnderstand="1">{action}</Action>
    <AuthenticationToken>{token}</AuthenticationToken>
    <CustomerAccountId>{creds["account_id"]}</CustomerAccountId>
    <CustomerId>{creds["customer_id"]}</CustomerId>
    <DeveloperToken>{creds["developer_token"]}</DeveloperToken>
  </s:Header>"""
    http = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": action}
    return header, http


def _soap_fault(text: str) -> str:
    import re
    m = re.search(r"<(?:\w+:)?Message>(.*?)</(?:\w+:)?Message>", text, re.S)
    return (m.group(1).strip() if m else text)[:200]


def _submit_report(token: str, creds: dict, date_from: str, date_to: str) -> str:
    """SubmitGenerateReport voor een CampaignPerformanceReport (CSV). Retourneert ReportRequestId."""
    d1 = datetime.strptime(date_from, "%Y-%m-%d").date()
    d2 = datetime.strptime(date_to, "%Y-%m-%d").date()
    header, http = _soap_headers("SubmitGenerateReport", token, creds)
    envelope = f"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
{header}
  <s:Body>
    <SubmitGenerateReportRequest xmlns="{REPORT_NS}">
      <ReportRequest i:type="CampaignPerformanceReportRequest">
        <ExcludeColumnHeaders>false</ExcludeColumnHeaders>
        <ExcludeReportFooter>true</ExcludeReportFooter>
        <ExcludeReportHeader>true</ExcludeReportHeader>
        <Format>Csv</Format>
        <ReportName>AI Pricing kostenrapport</ReportName>
        <ReturnOnlyCompleteData>false</ReturnOnlyCompleteData>
        <Aggregation>Daily</Aggregation>
        <Columns>
          <CampaignPerformanceReportColumn>TimePeriod</CampaignPerformanceReportColumn>
          <CampaignPerformanceReportColumn>CampaignId</CampaignPerformanceReportColumn>
          <CampaignPerformanceReportColumn>CampaignName</CampaignPerformanceReportColumn>
          <CampaignPerformanceReportColumn>Spend</CampaignPerformanceReportColumn>
          <CampaignPerformanceReportColumn>Impressions</CampaignPerformanceReportColumn>
          <CampaignPerformanceReportColumn>Clicks</CampaignPerformanceReportColumn>
          <CampaignPerformanceReportColumn>Conversions</CampaignPerformanceReportColumn>
          <CampaignPerformanceReportColumn>Revenue</CampaignPerformanceReportColumn>
        </Columns>
        <Scope>
          <AccountIds xmlns:a="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
            <a:long>{creds["account_id"]}</a:long>
          </AccountIds>
        </Scope>
        <Time>
          <CustomDateRangeEnd><Day>{d2.day}</Day><Month>{d2.month}</Month><Year>{d2.year}</Year></CustomDateRangeEnd>
          <CustomDateRangeStart><Day>{d1.day}</Day><Month>{d1.month}</Month><Year>{d1.year}</Year></CustomDateRangeStart>
          <ReportTimeZone>BrusselsCopenhagenMadridParis</ReportTimeZone>
        </Time>
      </ReportRequest>
    </SubmitGenerateReportRequest>
  </s:Body>
</s:Envelope>"""
    import httpx, re
    with httpx.Client(timeout=30) as client:
        resp = client.post(REPORTING_URL, content=envelope.encode("utf-8"), headers=http)
    if resp.status_code in (401, 403):
        raise ConnectorError(f"Toegang geweigerd ({resp.status_code}) door de Reporting-service.")
    if resp.status_code != 200:
        raise ConnectorError(f"SubmitGenerateReport mislukt (HTTP {resp.status_code}): {_soap_fault(resp.text)}")
    m = re.search(r"<ReportRequestId>(.*?)</ReportRequestId>", resp.text)
    if not m:
        raise ConnectorError(f"Reporting-respons bevat geen ReportRequestId: {_soap_fault(resp.text)}")
    return m.group(1)


def _poll_report(token: str, creds: dict, request_id: str) -> str | None:
    """PollGenerateReport tot Success; retourneert download-URL of None (geen data)."""
    header, http = _soap_headers("PollGenerateReport", token, creds)
    envelope = f"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
{header}
  <s:Body>
    <PollGenerateReportRequest xmlns="{REPORT_NS}">
      <ReportRequestId>{request_id}</ReportRequestId>
    </PollGenerateReportRequest>
  </s:Body>
</s:Envelope>"""
    import httpx, re
    from xml.sax.saxutils import unescape
    for _ in range(POLL_MAX_ATTEMPTS):
        with httpx.Client(timeout=30) as client:
            resp = client.post(REPORTING_URL, content=envelope.encode("utf-8"), headers=http)
        if resp.status_code != 200:
            raise ConnectorError(f"PollGenerateReport mislukt (HTTP {resp.status_code}): {_soap_fault(resp.text)}")
        status = re.search(r"<Status>(.*?)</Status>", resp.text)
        status = status.group(1) if status else ""
        if status == "Success":
            url = re.search(r"<ReportDownloadUrl>(.*?)</ReportDownloadUrl>", resp.text)
            if not url or "nil" in (url.group(1) or ""):
                return None  # rapport gereed maar leeg
            return unescape(url.group(1))
        if status == "Error":
            raise ConnectorError("Reporting-service meldde een fout bij het genereren van het rapport.")
        time.sleep(POLL_INTERVAL_S)
    raise ConnectorError("Rapport niet gereed binnen de wachttijd; probeer de sync later opnieuw.")


def _download_report_csv(url: str) -> list[dict]:
    """Download het ZIP-rapport en parse de CSV naar dict-rijen."""
    import csv, io, zipfile
    import httpx
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(url)
    if resp.status_code != 200:
        raise ConnectorError(f"Rapport-download mislukt (HTTP {resp.status_code}).")
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not names:
        return []
    text = zf.read(names[0]).decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _safe_num(val, cast=float):
    try:
        return cast(str(val).replace(",", "").replace("%", "").strip() or 0)
    except (ValueError, TypeError):
        return cast(0)


def _persist_rows(db, rows: list[dict]) -> int:
    """Idempotente opslag: verwijder bestaande rijen voor dezelfde datum/campagne, voeg dan in."""
    import models
    parsed = []
    for r in rows:
        raw_date = (r.get("TimePeriod") or "").strip()
        camp_id = (r.get("CampaignId") or "").strip()
        if not raw_date or not camp_id:
            continue
        d = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                d = datetime.strptime(raw_date, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            continue
        parsed.append((d, camp_id, r))
    if not parsed:
        return 0
    dates = {p[0] for p in parsed}
    sku_ids = {f"MSCAMPAGNE:{p[1]}"[:50] for p in parsed}
    db.query(models.FactMarketingCostDaily).filter(
        models.FactMarketingCostDaily.date.in_(dates),
        models.FactMarketingCostDaily.sku_id.in_(sku_ids),
    ).delete(synchronize_session=False)
    for d, camp_id, r in parsed:
        cost = _safe_num(r.get("Spend"))
        db.add(models.FactMarketingCostDaily(
            date=d,
            sku_id=f"MSCAMPAGNE:{camp_id}"[:50],
            sku_name=(r.get("CampaignName") or "")[:500],
            category="Microsoft Ads",
            sea_cost=cost,
            sea_impressions=_safe_num(r.get("Impressions"), int),
            sea_clicks=_safe_num(r.get("Clicks"), int),
            sea_conversions=_safe_num(r.get("Conversions"), int),
            sea_revenue=_safe_num(r.get("Revenue")),
            total_marketing_cost=cost,
        ))
    db.commit()
    return len(parsed)


def fetch_campaign_costs(date_from: str, date_to: str, db=None) -> list[dict]:
    """
    Haal campagnekosten op via de asynchrone Reporting-service en sla ze
    idempotent op in FactMarketingCostDaily. Retourneert de geparste rijen.
    """
    creds = _get_credentials(db=db)  # raises ConnectorError indien niet geconfigureerd
    token = _access_token(creds)
    request_id = _submit_report(token, creds, date_from, date_to)
    url = _poll_report(token, creds, request_id)
    if url is None:
        return []  # rapport gereed maar zonder data (geen campagnes in de periode)
    rows = _download_report_csv(url)
    if db is not None and rows:
        _persist_rows(db, rows)
    return rows
