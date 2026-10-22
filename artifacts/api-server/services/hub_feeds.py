"""Full-snapshot staging/imports; never writes live product or competitor tables."""
import csv
import hashlib
import io
import json
import logging
import time
from contextvars import ContextVar
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from connectors.crypto import decrypt_credentials, encrypt_credentials
from connectors.net import validate_external_url
from feed_models import HubFeedProfile, HubFeedVersion
from models import AuditLog, CostPriorityVersion
from services.cost_priority import Rules, SOURCES, select
from services import hub_feeds_storage as storage

OUTPUT_HEADERS = ["Productcode", "Cost Price inc VAT", "Cost Price exc VAT", "Type", "GTIN"]
_private_request = ContextVar("hub_private_request", default=False)


class _PrivateRequestLogFilter(logging.Filter):
    def filter(self, record):
        # httpx INFO normally includes full URLs (including credential query strings).
        # Suppress only this execution context, never other integrations' logs.
        return not _private_request.get()


logging.getLogger("httpx").addFilter(_PrivateRequestLogFilter())


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    purpose: Literal["cost", "products", "advice", "cost_output"]
    config: dict = Field(default_factory=dict)
    base_revision: int | None = None


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: int


class BuildInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_profile_id: int
    source_version_id: int


def audit(db, p, actor, action, details=None):
    db.add(AuditLog(entity_type="hub_feed", entity_id=str(p.id), action=action,
                    performed_by=actor, new_value={"shop_id": p.shop_id, "revision": p.revision,
                                                  **(details or {})}))


def config_input(config, previous=None):
    config = dict(config)
    secrets = decrypt_credentials(previous) if previous else {}
    for key in ("url", "bearer_token"):
        if key in config:
            secrets[key] = config.pop(key)
    config.pop("has_url", None)
    config.pop("has_bearer_token", None)
    if secrets.get("url"):
        u = urlparse(secrets["url"])
        if u.scheme != "https" or u.username or u.password or u.fragment:
            raise HTTPException(422, "Feed URL must be HTTPS without userinfo or fragment")
        try:
            validate_external_url(secrets["url"])
        except ValueError:
            raise HTTPException(422, "Feed URL is not a permitted external URL")
    if not isinstance(config.get("mapping", {}), dict) or not isinstance(config.get("type_mapping", {}), dict):
        raise HTTPException(422, "mapping and type_mapping must be objects")
    if any(not isinstance(v, str) or not v for v in config.get("mapping", {}).values()):
        raise HTTPException(422, "Every mapping value must be a nonempty column name")
    if any(not isinstance(v, str) or not v for v in config.get("type_mapping", {}).values()):
        raise HTTPException(422, "Every type_mapping value must be a named category")
    try:
        interval = int(config.get("interval_minutes", 60))
        minimum = int(config.get("minimum_rows", 1))
        if not 5 <= interval <= 10080 or not 1 <= minimum <= 200000:
            raise ValueError()
    except (TypeError, ValueError):
        raise HTTPException(422, "interval_minutes must be 5..10080 and minimum_rows 1..200000")
    config.update(interval_minutes=interval, minimum_rows=minimum)
    if len(json.dumps(config)) > 65536:
        raise HTTPException(422, "Configuration exceeds 64 KB")
    return config, encrypt_credentials(secrets) if secrets else None


def profile_json(p):
    secrets = decrypt_credentials(p.credentials) if p.credentials else {}
    return {**{k: getattr(p, k) for k in ("id", "shop_id", "name", "purpose", "revision", "active",
            "validated_version_id", "current_version_id", "released_version_id", "last_attempt",
            "last_success", "last_error", "created_at")},
            "config": {**p.config, "has_url": bool(secrets.get("url")),
                       "has_bearer_token": bool(secrets.get("bearer_token"))}}


def version_json(v):
    return {k: getattr(v, k) for k in ("id", "profile_id", "config_revision", "sha256", "status",
                                     "row_count", "report", "created_at")}


def money(value):
    try:
        text = str(value).strip()
        if not text or len(text) > 50:
            raise ValueError()
        # Explicit decimal comma; reject ambiguous mixed separators rather than guessing thousands.
        if "," in text and "." in text:
            raise ValueError()
        number = Decimal(text.replace(",", "."))
        if not number.is_finite() or number < 0 or number > Decimal("1e12") or number.as_tuple().exponent < -12:
            raise ValueError()
        return format(number, "f")
    except (ValueError, InvalidOperation):
        raise ValueError("Missing/invalid nonnegative decimal")


def rules_for(db, shop_id):
    v = db.query(CostPriorityVersion).filter_by(shop_id=shop_id).order_by(CostPriorityVersion.revision.desc()).first()
    return (v.revision, Rules.model_validate(v.rules)) if v else (0, Rules())


def parse(data, purpose, config, rules=None):
    """Bounded complete CSV parse. Preserve every row and exact identifiers, including missing trailing GTIN."""
    rules = rules or Rules()
    errors, warnings, records = [], [], []
    report = {"errors": errors, "warnings": warnings, "duplicate_rows": 0, "distinct_products": 0}
    def error(message):
        if len(errors) < 200:
            errors.append(message)
        report["error_count"] = report.get("error_count", 0) + 1
    if len(data) > storage.MAX_BYTES:
        raise HTTPException(413, "Feed exceeds 64 MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        error("CSV must be UTF-8 (optionally with BOM)")
        return records, report
    mapping = config.get("mapping", {})
    reference = purpose == "cost" and config.get("mode") == "reference"
    required = ["productcode"]
    sources = SOURCES + ([rules.custom_source] if rules.custom_source else [])
    if purpose == "cost":
        required += ["type", "cost_inc", "cost_exc"] if reference else ["type", *sources]
    elif purpose in ("products", "advice"):
        required += ["price" if purpose == "products" else "advice"]
    missing_mapping = [key for key in required if not isinstance(mapping.get(key), str) or not mapping[key]]
    if missing_mapping:
        error("Explicit column mapping required: " + ", ".join(missing_mapping))
        return records, report
    if purpose == "cost" and not reference:
        try:
            rate = Decimal(str(config["vat_rate"]))
            if not rate.is_finite() or not 0 <= rate <= 100 or config.get("vat_basis") not in ("inc", "exc"):
                raise ValueError()
            if config.get("unit_confirmed") is not True:
                raise ValueError()
        except (KeyError, InvalidOperation, ValueError):
            error("Confirm vat_rate, vat_basis (inc/exc) and unit_confirmed before calculating costs")
    if config.get("complete_snapshot_confirmed") is not True:
        error("Full snapshot contract must be explicitly confirmed")
    identities, signatures = set(), {}
    types = set()
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=";", strict=True)
        headers = next(reader, [])
        if not headers or len(set(headers)) != len(headers) or len(headers) > 150:
            error("Missing/duplicate headers or more than 150 columns")
            return records, report
        for key, col in mapping.items():
            if col not in headers:
                error(f"Mapped column not found: {key}")
        if errors and any("column" in e.lower() for e in errors):
            return records, report
        for index, cells in enumerate(reader, 2):
            if index > 200001:
                raise HTTPException(413, "Feed exceeds 200000 rows; no rows imported")
            if len(cells) == len(headers) - 1 and headers[-1] == mapping.get("gtin"):
                cells.append("")
            if len(cells) != len(headers):
                error(f"Row {index}: wrong column count")
                continue
            raw = dict(zip(headers, cells))
            record = {key: raw[col] for key, col in mapping.items()}
            record["raw"] = raw
            code = record.get("productcode", "")
            if not code.strip() or len(code) > 200:
                error(f"Row {index}: missing/oversized Productcode")
            numeric = ["cost_inc", "cost_exc"] if reference else sources if purpose == "cost" else [
                "price" if purpose == "products" else "advice"]
            for key in numeric:
                try:
                    record[key] = money(record.get(key))
                except ValueError:
                    error(f"Row {index}: {key} missing/invalid (missing is never zero)")
            if purpose == "cost" and not reference:
                typ = record["type"]
                types.add(typ)
                category = config.get("type_mapping", {}).get(typ)
                if not category or category not in ("Print", "Other", *rules.categories):
                    error(f"Row {index}: Type {typ!r} needs explicit Print/Other/category mapping")
                record["category"] = category
            # Product grouping for consistency only: never delete EAN rows or join many-to-many.
            signature = tuple(record.get(k) for k in [*numeric, *(["type"] if purpose == "cost" else [])])
            if code in signatures and signatures[code] != signature:
                error(f"Row {index}: conflicting prices/category for Productcode {code!r}")
            signatures[code] = signature
            identity = (code, record.get("gtin", ""))
            if identity in identities:
                report["duplicate_rows"] += 1
            identities.add(identity)
            records.append(record)
    except (csv.Error, KeyError) as exc:
        error("Malformed CSV: " + type(exc).__name__)
    if len(records) < config.get("minimum_rows", 1):
        error("Feed is empty or below confirmed minimum_rows")
    report.update(distinct_products=len(signatures), type_values=sorted(types), row_count=len(records))
    if report["duplicate_rows"]:
        warnings.append(f"{report['duplicate_rows']} repeated Productcode/GTIN combinations retained")
    if reference:
        warnings.append("Five-column reference only; not a full purchase-cost source and cannot build cost output")
    if any(any(v.lstrip().startswith(("=", "+", "-", "@")) for v in r["raw"].values()) for r in records):
        warnings.append("Spreadsheet-like text retained in immutable original; generated CSV escapes formula-leading text")
    return records, report


def fetch(p):
    creds = decrypt_credentials(p.credentials) if p.credentials else {}
    url = creds.get("url")
    if not url:
        raise HTTPException(422, "Feed URL not configured")
    # No redirects: prevents credential forwarding and downgrade. Uses shared SSRF validation.
    log_token = _private_request.set(True)
    try:
        if urlparse(url).scheme != "https":
            raise ValueError()
        validate_external_url(url)
        with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False, trust_env=False) as client:
            headers = {"Authorization": "Bearer " + creds["bearer_token"]} if creds.get("bearer_token") else {}
            start = time.monotonic()
            with client.stream("GET", url, headers=headers) as response:
                if response.is_redirect:
                    raise HTTPException(422, "Redirects are disabled; configure the final HTTPS feed URL")
                response.raise_for_status()
                out = io.BytesIO()
                for chunk in response.iter_bytes(1024 * 1024):
                    if out.tell() + len(chunk) > storage.MAX_BYTES:
                        raise HTTPException(413, "Feed exceeds 64 MB")
                    if time.monotonic() - start > 90:
                        raise HTTPException(504, "Feed exceeded 90 second total deadline")
                    out.write(chunk)
                return out.getvalue()
    except HTTPException:
        raise
    except Exception as exc:
        # Never persist request exceptions: their messages can contain secret URL query strings.
        raise HTTPException(502, "Feed request failed; check HTTPS URL, certificate, credentials and access") from exc
    finally:
        _private_request.reset(log_token)


def stage(db, p, data, actor):
    revision, rules = rules_for(db, p.shop_id)
    context = str(revision) if p.purpose == "cost" else ""
    digest = hashlib.sha256(data).hexdigest()
    prior = db.query(HubFeedVersion).filter_by(profile_id=p.id, config_revision=p.revision,
                                               sha256=digest, context_hash=context).first()
    if prior:
        previous = db.get(HubFeedVersion, p.current_version_id) if p.current_version_id else None
        if previous and prior.row_count < previous.row_count:
            raise HTTPException(409, "Snapshot shrank versus active version; reconfirm source configuration before activation")
        return prior
    records, report = parse(data, p.purpose, p.config, rules)
    report["cost_priority_revision"] = revision
    if p.current_version_id:
        previous = db.get(HubFeedVersion, p.current_version_id)
        # Fail closed on shrinkage; an operator can revise/reconfirm the full-source contract.
        if previous and len(records) < previous.row_count:
            report["errors"].append("Snapshot shrank versus active version; reconfirm source configuration before activation")
    key, records_key = storage.put_pair(data, records, p.shop_id, p.id)
    v = HubFeedVersion(profile_id=p.id, config_revision=p.revision, sha256=digest,
                       context_hash=context, object_key=key, records_key=records_key,
                       row_count=len(records), status="invalid" if report["errors"] else "valid",
                       report=report, created_by=actor)
    db.add(v)
    db.flush()
    audit(db, p, actor, "feed_staged", {"version_id": v.id, "status": v.status})
    return v


def ensure_version(db, p, version_id):
    v = db.get(HubFeedVersion, version_id)
    if not v or v.profile_id != p.id:
        raise HTTPException(404, "Feed version not found in this profile")
    return v


def valid_version(db, p, version_id):
    v = ensure_version(db, p, version_id)
    if v.config_revision != p.revision or v.status != "valid":
        raise HTTPException(409, "Version is invalid or configuration changed; test again")
    previous = db.get(HubFeedVersion, p.current_version_id) if p.current_version_id else None
    if previous and v.row_count < previous.row_count:
        raise HTTPException(409, "Snapshot shrank versus active version; reconfirm source configuration before activation")
    if p.purpose == "cost" and v.report.get("cost_priority_revision") != rules_for(db, p.shop_id)[0]:
        raise HTTPException(409, "Cost priorities changed; test and reactivate source")
    return v


def active_records(db, shop_id, profile_id, purpose="advice", version_id=None):
    """Internal scoped immutable source helper. Caller MUST authorize shop before invoking."""
    p = db.query(HubFeedProfile).filter_by(id=profile_id, shop_id=shop_id, purpose=purpose).first()
    if not p or not p.active or not p.current_version_id:
        raise HTTPException(409, "Required feed is inactive or has no active snapshot")
    if version_id is not None and version_id != p.current_version_id:
        raise HTTPException(409, "Feed changed; recreate approval/export from current source")
    v = valid_version(db, p, p.current_version_id)
    return v, json.loads(storage.get(v.records_key))


def safe_cell(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def cost_csv(records, config, rules):
    rate = Decimal(str(config["vat_rate"])) / 100 + 1
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(OUTPUT_HEADERS)
    selections, result = {}, []
    for r in records:
        code = r["productcode"]
        if code not in selections:
            selections[code] = select(rules, r["category"], {k: r.get(k) for k in SOURCES + ([rules.custom_source] if rules.custom_source else [])})
        chosen = selections[code]
        if chosen["value"] is None:
            raise HTTPException(422, f"Missing cost source for {code}")
        value = Decimal(chosen["value"])
        exc = value / rate if config["vat_basis"] == "inc" else value
        inc = value if config["vat_basis"] == "inc" else value * rate
        fmt = lambda n: format(n.quantize(Decimal(".01"), rounding=ROUND_HALF_UP), ".2f").replace(".", ",")
        writer.writerow([safe_cell(code), fmt(inc), fmt(exc), safe_cell(r["type"]), safe_cell(r.get("gtin", ""))])
        result.append({"productcode": code, "gtin": r.get("gtin", ""), "type": r["type"],
                       "cost_inc": fmt(inc), "cost_exc": fmt(exc), "selection": chosen})
    return output.getvalue().encode("utf-8-sig"), result


def build(db, p, body, actor):
    if p.purpose != "cost_output":
        raise HTTPException(422, "Only cost_output profiles can build CSV")
    source = db.query(HubFeedProfile).filter_by(id=body.source_profile_id, shop_id=p.shop_id, purpose="cost").first()
    if not source or source.config.get("mode") == "reference":
        raise HTTPException(422, "An active full cost-source profile in the same shop is required")
    v, records = active_records(db, p.shop_id, source.id, "cost", body.source_version_id)
    revision, rules = rules_for(db, p.shop_id)
    data, result = cost_csv(records, source.config, rules)
    context = hashlib.sha256(f"{source.id}:{v.id}:{revision}".encode()).hexdigest()
    digest = hashlib.sha256(data).hexdigest()
    old = db.query(HubFeedVersion).filter_by(profile_id=p.id, config_revision=p.revision,
                                             sha256=digest, context_hash=context).first()
    if old:
        return old
    report = {"errors": [], "warnings": [*v.report.get("warnings", []),
              "PriceShape authentication compatibility unconfirmed; manual download available"],
              "source_profile_id": source.id, "source_version_id": v.id, "cost_priority_revision": revision,
              "source_config_revision": source.revision,
              "duplicate_rows": v.report.get("duplicate_rows", 0), "distinct_products": v.report["distinct_products"],
              "vat_rate": source.config["vat_rate"], "vat_basis": source.config["vat_basis"]}
    key, records_key = storage.put_pair(data, result, p.shop_id, p.id)
    output = HubFeedVersion(profile_id=p.id, config_revision=p.revision, sha256=digest, context_hash=context,
                            object_key=key, records_key=records_key,
                            status="valid", row_count=len(result), report=report, created_by=actor)
    db.add(output)
    db.flush()
    audit(db, p, actor, "cost_output_built", {"version_id": output.id, **report})
    return output


def check_output_source(db, p, v, require_current=True):
    source = db.query(HubFeedProfile).filter_by(id=v.report.get("source_profile_id"), shop_id=p.shop_id).first()
    if (not source or not source.active or source.revision != v.report.get("source_config_revision") or
            (require_current and source.current_version_id != v.report.get("source_version_id"))):
        raise HTTPException(409, "Cost source changed or paused; build and release a new snapshot")
    valid_version(db, source, source.current_version_id)
    if v.report.get("cost_priority_revision") != rules_for(db, p.shop_id)[0]:
        raise HTTPException(409, "Cost priorities changed; rebuild output")


def compare_sources(db, shop_id, cost_profile_id, products_profile_id):
    cost_version, cost = active_records(db, shop_id, cost_profile_id, "cost")
    product_version, products = active_records(db, shop_id, products_profile_id, "products")
    costs = {r["productcode"] for r in cost}
    references = {r["productcode"] for r in products}
    # Set comparison, not a join: multiple GTIN rows never multiply.
    return {"cost_version_id": cost_version.id, "products_version_id": product_version.id,
            "cost_only": sorted(costs - references), "products_only": sorted(references - costs),
            "matched_products": len(costs & references),
            "cost_rows": len(cost), "products_rows": len(products)}
