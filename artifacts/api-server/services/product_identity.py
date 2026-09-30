"""Shop-scoped identity resolution, with no fuzzy or OEM matching."""
from collections import defaultdict
from hashlib import sha256
import time
from fastapi import HTTPException
from sqlalchemy import text
import models
from authz import user_allowed_shop_ids


def ean_values(value):
    return {v.strip() for v in (value or "").split(",") if v.strip() and v.strip() != "0"}


def alias_discriminator(ean):
    normalized = ",".join(sorted(ean_values(ean)))
    return normalized if len(normalized) <= 50 else "#" + sha256(normalized.encode()).hexdigest()[:48]


def authorize_shop(db, user, shop_id):
    allowed = user_allowed_shop_ids(db, user)
    if (allowed is not None and shop_id not in allowed) or not db.get(models.DimShop, shop_id):
        raise HTTPException(403, "Geen toegang tot deze winkel.")


def sales_lock(db, shop_id):
    # Shared by daily confirmation and legacy upload: serializes check + write.
    if db.bind.dialect.name == "postgresql":
        # A full-size confirmation can legitimately exceed the request SQL
        # timeout. Do not block a competing HTTP request inside PostgreSQL for
        # 4s and turn a healthy running import into a 500. Short repeats wait;
        # long competitors get an explicit retryable conflict.
        deadline = time.monotonic() + 2
        while True:
            acquired = db.execute(text("SELECT pg_try_advisory_xact_lock(718203, :shop)"),
                                  {"shop": shop_id}).scalar()
            if acquired:
                return
            if time.monotonic() >= deadline:
                raise HTTPException(409, "Winkel wordt momenteel verwerkt; haal de previewstatus op en probeer opnieuw.")
            time.sleep(.05)


class IdentityIndex:
    def __init__(self, db, shop_id):
        self.products = {p.sku_id: p for p in db.query(models.DimProduct).filter_by(shop_id=shop_id)}
        self.codes = defaultdict(set)
        self.aliases = defaultdict(set)
        for p in self.products.values():
            # Technical IDs are not implicitly business codes or EANs.
            for code in (p.business_sku, p.product_group if p.import_source != "DRS" else None):
                if code:
                    self.codes[code].add(p.sku_id)
            if p.import_source == "DRS" and not p.business_sku:
                self.codes[p.sku_id].add(p.sku_id)
            raw = p.raw_attributes or {}
            for key in ("itemGroupId", "itemgroupid", "productcode"):
                if raw.get(key):
                    self.codes[str(raw[key]).strip()].add(p.sku_id)
        for a in db.query(models.ProductSourceAlias).filter_by(shop_id=shop_id):
            if a.sku_id in self.products:
                self.codes[a.code].add(a.sku_id)
                if a.source == "DRS":
                    self.aliases[(a.code, a.discriminator)].add(a.sku_id)

    def resolve(self, code, ean=""):
        exact = self.aliases.get((code, alias_discriminator(ean))) or self.aliases.get((code, ""))
        candidates = set(exact or self.codes.get(code, set()))
        if not candidates:
            raise ValueError("Onbekende artikelcode; eerst catalogusmapping toevoegen.")
        if ean_values(ean):
            matched = {s for s in candidates if ean_values(
                (self.products[s].raw_attributes or {}).get("_ean_full") or self.products[s].ean
            ) & ean_values(ean)}
            if matched:
                candidates = matched
            elif any((self.products[s].raw_attributes or {}).get("_ean_full") or
                     self.products[s].ean for s in candidates):
                raise ValueError("EAN-conflict met artikelcode; geen automatische koppeling.")
        if len(candidates) != 1:
            raise ValueError("Ambigue artikelcode; EAN ontbreekt of onderscheidt niet uniek.")
        sku = next(iter(candidates))
        p = self.products[sku]
        if p.business_sku and p.business_sku != code:
            raise ValueError("Zakelijke SKU-conflict; bestaande code blijft behouden.")
        return sku, not bool(exact)