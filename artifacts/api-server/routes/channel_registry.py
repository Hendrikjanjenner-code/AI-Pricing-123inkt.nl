"""Persistent channel directory. Activation is internal readiness, never dispatch."""
from copy import deepcopy
import hashlib
import json
from datetime import datetime
from uuid import uuid4
from urllib.parse import urlsplit
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy.orm import Session

from auth import get_current_user
from authz import effective_permissions
from database import get_db
from feed_models import HubFeedProfile, HubFeedVersion
from models import DimShop
from routes.channelmanager import access, lock, latest, add, reference_access, SnapshotOutput, commit
from services.channelmanager import Strict, BasisInput
from services.hub_feeds import active_records

router = APIRouter(prefix="/api/channelmanager/channels", tags=["channel-directory"])
KIND = "channel_registry"
DEFAULTS = ("Kabelshop.nl", "Sneltoner.nl", "Printabout.nl", "Tonershop.nl")


def domain(value):
    value = value.strip().lower()
    parsed = urlsplit(value if "://" in value else "https://" + value)
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Gebruik alleen een domeinnaam, zonder pad of inloggegevens")
    host = (parsed.hostname or "").removeprefix("www.").rstrip(".").encode("idna").decode()
    if "." not in host or len(host) > 253 or any(not part or len(part) > 63 or part.startswith("-") or part.endswith("-") or not all(c.isalnum() or c == "-" for c in part) for part in host.split(".")):
        raise ValueError("Ongeldige domeinnaam")
    return host


class Revision(Strict):
    expected_revision: int = Field(ge=1)


class NewChannel(Revision):
    name: str = Field(min_length=1, max_length=120)
    domain: str

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("Kanaalnaam mag niet leeg zijn")
        return value.strip()

    @field_validator("domain")
    @classmethod
    def canonical(cls, value):
        return domain(value)


class Mapping(Strict):
    source_productcode: str = Field(min_length=1, max_length=200)
    target_productcode: str = Field(min_length=1, max_length=200)

    @field_validator("source_productcode", "target_productcode")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Productcode mag niet leeg zijn")
        return value


class Setup(Revision):
    target_shop_id: int | None = Field(default=None, gt=0)
    product_profile_id: int | None = Field(default=None, gt=0)
    mappings: list[Mapping] = Field(default_factory=list, max_length=200000)
    mapping_confirmed: bool = False

    @model_validator(mode="after")
    def unique(self):
        for field in ("source_productcode", "target_productcode"):
            codes = [getattr(m, field) for m in self.mappings]
            if len(set(codes)) != len(codes):
                raise ValueError("Productmapping moet één-op-één zijn; dubbele codes zijn niet toegestaan")
        return self


class Visibility(Revision):
    hidden: bool


class Reorder(Revision):
    channel_ids: list[str]


class ChannelOutput(Strict):
    id: str
    name: str
    domain: str
    hidden: bool
    status: Literal["setup", "ready", "active", "paused", "needs_validation", "restricted"]
    target_shop_id: int | None
    product_profile_id: int | None
    mappings: list[Mapping]
    mapping_confirmed: bool
    mapped_products: int | None
    last_success_at: str | None
    validation_errors: list[str]
    validated_at: str | None
    can_edit: bool
    can_activate: bool
    external_connected: bool = False


class DirectoryOutput(Strict):
    revision: int
    channels: list[ChannelOutput]
    can_edit: bool
    can_activate: bool


def template(name, host=None):
    return dict(id=uuid4().hex, name=name, domain=host or domain(name), hidden=False,
                target_shop_id=None, product_profile_id=None, mappings=[], mapping_confirmed=False,
                active=False, paused=False, validation=None, validation_errors=[])


def setup_signature(channel):
    fields = {k: channel[k] for k in ("target_shop_id", "product_profile_id", "mappings", "mapping_confirmed", "validation")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def registry(db, user, shop):
    access(db, user, shop)
    row = latest(db, shop, KIND)
    if row:
        return row
    # The registry snapshot is the seed-once marker even when every row is hidden.
    lock(db, shop)
    row = latest(db, shop, KIND)
    if row:
        return row
    row = add(db, user, shop, KIND, {"channels": [template(n) for n in DEFAULTS]}, "saved")
    db.commit()
    return row


def references(db, user, shop, channel, action="pricing.view"):
    access(db, user, shop, action)
    target = channel["target_shop_id"]
    if target:
        access(db, user, target, action)
        config = latest(db, target, "config")
        if config:
            reference_access(db, user, config)
    profile = channel["product_profile_id"]
    if profile and not db.query(HubFeedProfile).filter_by(id=profile, shop_id=shop, purpose="products").first():
        raise HTTPException(404, "Productreferentie niet gevonden in deze bronwinkel")


def fingerprint(db, shop, channel):
    p = db.query(HubFeedProfile).filter_by(id=channel["product_profile_id"], shop_id=shop, purpose="products").first()
    target = db.get(DimShop, channel["target_shop_id"]) if channel["target_shop_id"] else None
    config = latest(db, target.id, "config") if target else None
    v = db.get(HubFeedVersion, p.current_version_id) if p and p.current_version_id else None
    if not target or not target.active or not p or not p.active or not v or v.status != "valid" or v.config_revision != p.revision or not config:
        return None
    return {"profile_id": p.id, "profile_revision": p.revision, "version_id": v.id, "config_id": config.id}


def output(db, user, shop, row):
    permissions = effective_permissions(db, user)
    edit, approve = "pricing.propose" in permissions, "pricing.approve" in permissions
    result = []
    for c in row.data["channels"]:
        item = {k: c[k] for k in ("id", "name", "domain", "hidden", "target_shop_id", "product_profile_id", "mappings", "mapping_confirmed")}
        try:
            references(db, user, shop, c)
        except HTTPException:
            result.append({**item, "status": "restricted", "target_shop_id": None, "product_profile_id": None,
                           "mappings": [], "mapping_confirmed": False, "mapped_products": None,
                           "last_success_at": None, "validation_errors": ["Geen toegang tot gekoppelde winkel of bron"],
                           "validated_at": None, "can_edit": False, "can_activate": False, "external_connected": False})
            continue
        validation = c.get("validation")
        fresh = bool(validation and fingerprint(db, shop, c) == validation["fingerprint"])
        status = ("needs_validation" if validation and not fresh else "active" if fresh and c["active"]
                  else "paused" if c.get("paused") else "ready" if fresh else "setup")
        p = db.get(HubFeedProfile, c["product_profile_id"]) if c["product_profile_id"] else None
        last_success = p.last_success if p else None
        exported = latest(db, c["target_shop_id"], "export") if c["target_shop_id"] else None
        if exported and exported.data.get("source_shop_id") == shop:
            last_success = max(filter(None, [last_success, exported.created_at]))
        result.append({**item, "status": status, "mapped_products": len(c["mappings"]) if fresh else None,
                       "last_success_at": last_success.isoformat() + "Z" if last_success else None,
                       "validation_errors": c.get("validation_errors", []),
                       "validated_at": validation["at"] if validation else None,
                       "can_edit": edit, "can_activate": approve, "external_connected": False})
    return {"revision": row.revision, "channels": result, "can_edit": edit, "can_activate": approve}


def writable(db, user, shop, revision, ident=None, action="pricing.propose", extra_target=None):
    access(db, user, shop, action)
    row = registry(db, user, shop)
    targets = [c["target_shop_id"] for c in row.data["channels"] if c["target_shop_id"]]
    lock(db, shop, *targets, *([extra_target] if extra_target else []))
    row = latest(db, shop, KIND)
    if row.revision != revision:
        raise HTTPException(409, "Kanaaloverzicht gewijzigd; herlaad vóór opslaan")
    channels = deepcopy(row.data["channels"])
    selected = next((c for c in channels if c["id"] == ident), None)
    if ident:
        if not selected:
            raise HTTPException(404, "Kanaal niet gevonden")
        references(db, user, shop, selected, action)
    return channels, selected


def save(db, user, shop, channels):
    row = add(db, user, shop, KIND, {"channels": channels}, "saved")
    db.commit()
    return output(db, user, shop, row)


@router.get("/{shop_id}", response_model=DirectoryOutput)
def listing(shop_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(db, user, shop_id, registry(db, user, shop_id))


@router.post("/{shop_id}", response_model=DirectoryOutput)
def create(shop_id: int, body: NewChannel, db: Session = Depends(get_db), user=Depends(get_current_user)):
    channels, _ = writable(db, user, shop_id, body.expected_revision)
    if any(c["domain"] == body.domain for c in channels):
        raise HTTPException(409, "Dit domein bestaat al; herstel eventueel het verborgen kanaal")
    if len(channels) >= 200:
        raise HTTPException(422, "Maximaal 200 kanalen per bronwinkel")
    channels.append(template(body.name.strip(), body.domain))
    return save(db, user, shop_id, channels)


@router.post("/{shop_id}/reorder", response_model=DirectoryOutput)
def reorder(shop_id: int, body: Reorder, db: Session = Depends(get_db), user=Depends(get_current_user)):
    channels, _ = writable(db, user, shop_id, body.expected_revision)
    accessible = []
    for c in channels:
        try:
            references(db, user, shop_id, c, "pricing.propose")
            accessible.append(c["id"])
        except HTTPException:
            pass
    if len(set(body.channel_ids)) != len(body.channel_ids) or set(body.channel_ids) != set(accessible):
        raise HTTPException(422, "Volgorde moet elk toegankelijk kanaal precies één keer bevatten")
    ordered = iter([{c["id"]: c for c in channels}[i] for i in body.channel_ids])
    return save(db, user, shop_id, [next(ordered) if c["id"] in accessible else c for c in channels])


@router.put("/{shop_id}/{channel_id}", response_model=DirectoryOutput)
def configure(shop_id: int, channel_id: str, body: Setup, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if body.target_shop_id:
        access(db, user, body.target_shop_id, "pricing.propose")
    channels, c = writable(db, user, shop_id, body.expected_revision, channel_id, extra_target=body.target_shop_id)
    if body.target_shop_id and any(other["id"] != channel_id and other["target_shop_id"] == body.target_shop_id for other in channels):
        raise HTTPException(409, "Deze doelwinkel is al gekoppeld aan een ander kanaal; ontkoppel dat kanaal eerst")
    c.update(body.model_dump(exclude={"expected_revision"}))
    references(db, user, shop_id, c, "pricing.propose")
    c.update(active=False, paused=False, validation=None, validation_errors=[])
    return save(db, user, shop_id, channels)


def validate_setup(db, user, shop, c):
    errors = []
    if not c["target_shop_id"]:
        errors.append("Koppel een doelwinkel")
    elif c["target_shop_id"] == shop:
        errors.append("Kies een andere doelwinkel dan de bronwinkel")
    if not c["product_profile_id"]:
        errors.append("Kies een productreferentie uit de bronwinkel")
    if not c["mappings"] or not c["mapping_confirmed"]:
        errors.append("Voeg productmapping toe en bevestig de doelproductcodes")
    references(db, user, shop, c)
    if c["product_profile_id"]:
        db.query(HubFeedProfile).filter_by(id=c["product_profile_id"], shop_id=shop).with_for_update().first()
    fp = fingerprint(db, shop, c)
    if not fp:
        errors.append("Actieve geldige productreferentie, actieve doelwinkel en opgeslagen doelprijsregels vereist")
    if errors:
        return None, errors
    _, records = active_records(db, shop, c["product_profile_id"], purpose="products", version_id=fp["version_id"])
    codes = {r["productcode"] for r in records}
    missing = [m["source_productcode"] for m in c["mappings"] if m["source_productcode"] not in codes]
    if missing:
        errors.append(f"{len(missing)} broncodes ontbreken in de huidige productreferentie: " + ", ".join(missing[:10]))
    return fp, errors


@router.post("/{shop_id}/{channel_id}/validate", response_model=DirectoryOutput)
def validate(shop_id: int, channel_id: str, body: Revision, db: Session = Depends(get_db), user=Depends(get_current_user)):
    channels, c = writable(db, user, shop_id, body.expected_revision, channel_id)
    fp, errors = validate_setup(db, user, shop_id, c)
    c.update(active=False, validation_errors=errors,
             validation=None if errors else {"fingerprint": fp, "at": datetime.utcnow().isoformat() + "Z"})
    return save(db, user, shop_id, channels)


@router.post("/{shop_id}/{channel_id}/activate", response_model=DirectoryOutput)
def activate(shop_id: int, channel_id: str, body: Revision, db: Session = Depends(get_db), user=Depends(get_current_user)):
    channels, c = writable(db, user, shop_id, body.expected_revision, channel_id, action="pricing.approve")
    fp, errors = validate_setup(db, user, shop_id, c)
    if c["hidden"] or errors or not c["validation"] or fp != c["validation"]["fingerprint"]:
        raise HTTPException(409, "Valideer de huidige instellingen eerst; verborgen kanalen kunnen niet activeren")
    c.update(active=True, paused=False)
    return save(db, user, shop_id, channels)


@router.post("/{shop_id}/{channel_id}/pause", response_model=DirectoryOutput)
def pause(shop_id: int, channel_id: str, body: Revision, db: Session = Depends(get_db), user=Depends(get_current_user)):
    channels, c = writable(db, user, shop_id, body.expected_revision, channel_id)
    c.update(active=False, paused=True)
    return save(db, user, shop_id, channels)


@router.post("/{shop_id}/{channel_id}/visibility", response_model=DirectoryOutput)
def visibility(shop_id: int, channel_id: str, body: Visibility, db: Session = Depends(get_db), user=Depends(get_current_user)):
    channels, c = writable(db, user, shop_id, body.expected_revision, channel_id)
    c["hidden"] = body.hidden
    if body.hidden:
        c.update(active=False, paused=True)
    return save(db, user, shop_id, channels)


@router.post("/{shop_id}/{channel_id}/prepare-basis", response_model=SnapshotOutput)
def prepare_basis(shop_id: int, channel_id: str, body: Revision, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _, c = writable(db, user, shop_id, body.expected_revision, channel_id)
    fp, errors = validate_setup(db, user, shop_id, c)
    if not c["active"] or c["hidden"] or errors or not c["validation"] or fp != c["validation"]["fingerprint"]:
        raise HTTPException(409, "Activeer en valideer het kanaal eerst")
    source = latest(db, shop_id, "basis", True)
    if not source:
        raise HTTPException(409, "Keur eerst basisprijzen goed in de bronwerkruimte")
    reference_access(db, user, source)
    indexed = {r["sku"]: r for r in source.data["rows"]}
    if any(m["source_productcode"] not in indexed for m in c["mappings"]):
        raise HTTPException(409, "Niet alle gekoppelde producten hebben een goedgekeurde bronbasisprijs")
    rows = []
    for m in c["mappings"]:
        item = {**indexed[m["source_productcode"]], "sku": m["target_productcode"]}
        # Source actuals are not actual prices of the destination product/shop.
        if c["target_shop_id"] != shop_id or m["source_productcode"] != m["target_productcode"]:
            item["current_price"] = None
        rows.append(item)
    data = BasisInput.model_validate({**{k: source.data[k] for k in
        ("currency", "price_basis", "vat_rate", "cost_basis", "provenance")},
        "notes": f"Kanaalbasis {c['name']}; expliciete mapping uit bronbasis #{source.id}",
        "rows": rows}).model_dump()
    data.update(source_shop_id=shop_id, channel_origin={
        "channel_id": c["id"], "registry_revision": body.expected_revision, "source_basis_id": source.id,
        "setup_signature": setup_signature(c)})
    return commit(db, add(db, user, c["target_shop_id"], "basis", data, "staged"))
