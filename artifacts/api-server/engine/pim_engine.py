"""
PIM Integration & Product Content Intelligence Engine (§23).

Vendor-neutrale contentlaag bovenop de DRS-productmaster. DRS blijft eigenaar
van de commerciële kernvelden; deze engine:

- seedt een default attributen-set (gemapt op DimProduct-velden) en channels
- synchroniseert DRS-owned attributen automatisch vanuit DimProduct
- berekent completeness- en quality-scores per SKU en per channel
- genereert AI-suggesties voor ontbrekende attributen via de AI Gateway
  (altijd als PENDING-voorstel; nooit automatisch toegepast)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

import models

logger = logging.getLogger("uvicorn.error")

# Bronnen in prioriteitsvolgorde bij conflictdetectie
SOURCES = ["DRS", "Leverancier", "Handmatig", "AI"]


class OwnershipConflict(Exception):
    """Schrijfpoging die de source-ownership-policy (§4) schendt."""


def check_write_allowed(defn, existing, new_source: str) -> str | None:
    """
    Centrale source-ownership-policy (§4) voor ALLE schrijvers van
    attribuutwaarden (DRS-sync, leveranciersimport, handmatig, AI-approval).

    Regels:
    - DRS-owned velden (gemapt op DimProduct) mogen alleen door de DRS-sync
      worden geschreven — ook als ze nu nog leeg zijn, anders blokkeert een
      vreemde bron de master-sync voorgoed.
    - Een bestaande waarde van een ANDERE bron wordt nooit stil overschreven;
      alleen dezelfde bron mag zijn eigen waarde bijwerken.
    - Lege velden (zonder rij) mag elke bron vullen, behalve DRS-owned velden.

    Returns None als schrijven mag, anders een NL-reden (conflict).
    """
    if new_source != "DRS" and defn.source_owner == "DRS" and defn.dim_product_field:
        return (f"Attribuut '{defn.code}' is eigendom van DRS (productmaster); "
                f"bron {new_source} mag dit veld niet schrijven.")
    if existing is not None and existing.value and existing.source != new_source:
        return (f"Attribuut '{defn.code}' heeft al een waarde van bron "
                f"{existing.source} ('{existing.value}'); bron {new_source} "
                "mag die niet stil overschrijven.")
    return None

# ─── Default attribuutdefinities ─────────────────────────────────────────────
# (code, naam, data_type, unit, source_owner, required, weight, dim_product_field)
DEFAULT_ATTRIBUTES = [
    ("product_name",   "Productnaam",      "text",    None,    "DRS",        True,  2.0, "product_name"),
    ("brand",          "Merk",             "text",    None,    "DRS",        True,  2.0, "brand"),
    ("category",       "Categorie",        "text",    None,    "DRS",        True,  1.5, "category"),
    ("subcategory",    "Subcategorie",     "text",    None,    "DRS",        False, 1.0, "subcategory"),
    ("ean",            "EAN-code",         "text",    None,    "DRS",        True,  2.0, "ean"),
    ("oem_code",       "OEM-code",         "text",    None,    "DRS",        False, 1.0, "oem_code"),
    ("product_type",   "Producttype",      "text",    None,    "DRS",        False, 1.0, "product_type"),
    ("description",    "Omschrijving",     "text",    None,    "Leverancier", True, 1.5, None),
    ("usp_1",          "USP 1",            "text",    None,    "Handmatig",  False, 0.5, None),
    ("material",       "Materiaal",        "text",    None,    "Leverancier", False, 1.0, None),
    ("color",          "Kleur",            "text",    None,    "Leverancier", False, 1.0, None),
    ("paper_size",     "Papierformaat",    "select",  None,    "DRS",        False, 1.0, "paper_size"),
    ("paper_weight_gsm", "Grammage",       "number",  "g/m²",  "DRS",        False, 1.0, "paper_weight_gsm"),
    ("sheets_per_pack", "Vel per pak",     "number",  "vel",   "DRS",        False, 1.0, "sheets_per_pack"),
]

DEFAULT_CHANNELS = [
    ("webshop", "Webshop", ["product_name", "brand", "ean", "description", "category"], 80.0),
    ("marketplace", "Marketplace", ["product_name", "brand", "ean", "description", "color", "material"], 90.0),
]

DEFAULT_FAMILIES = [
    ("papier", "Papier", ["Papier", "Kopieerpapier", "Printpapier"]),
    ("supplies", "Printer Supplies", ["Cartridges", "Toners", "Supplies"]),
]


_defaults_seeded = False  # proces-lokale sneltoets; de echte marker staat in audit_log


def ensure_defaults(db: Session) -> None:
    """
    Seed default attributen, channels en families — maar hooguit één keer.

    Een marker in audit_log voorkomt dat een beheerder die bewust het laatste
    attribuut/channel/familie verwijdert, bij de eerstvolgende lijst-refresh
    de defaults weer terug ziet komen.
    """
    global _defaults_seeded
    if _defaults_seeded:
        return
    marker = (db.query(models.AuditLog)
              .filter(models.AuditLog.entity_type == "pim_defaults",
                      models.AuditLog.action == "defaults_seeded")
              .first())
    if marker is not None:
        _defaults_seeded = True
        return
    if db.query(models.PimAttributeDefinition).count() == 0:
        for code, name, dtype, unit, owner, req, weight, dim_field in DEFAULT_ATTRIBUTES:
            db.add(models.PimAttributeDefinition(
                code=code, name=name, data_type=dtype, unit=unit,
                source_owner=owner, is_required=req, weight=weight,
                dim_product_field=dim_field))
    if db.query(models.PimChannel).count() == 0:
        for code, name, req_codes, min_pct in DEFAULT_CHANNELS:
            db.add(models.PimChannel(
                code=code, name=name, required_attribute_codes=req_codes,
                min_completeness_pct=min_pct))
    if db.query(models.PimFamily).count() == 0:
        for code, name, patterns in DEFAULT_FAMILIES:
            db.add(models.PimFamily(code=code, name=name, category_patterns=patterns))
    db.add(models.AuditLog(
        entity_type="pim_defaults", entity_id="v1", action="defaults_seeded",
        performed_by="system", details="Initiële PIM-defaults geseed (eenmalig)"))
    db.commit()
    _defaults_seeded = True


def _attr_defs(db: Session) -> list[models.PimAttributeDefinition]:
    return (db.query(models.PimAttributeDefinition)
            .filter(models.PimAttributeDefinition.active == True)  # noqa: E712
            .all())


def sync_drs_attributes(db: Session, sku_ids: list[str] | None = None) -> int:
    """
    Vul DRS-owned attributen automatisch vanuit DimProduct (bron = DRS).
    Overschrijft alleen waarden die zelf van bron DRS zijn (of nog ontbreken):
    handmatige of leveranciers-correcties op niet-DRS-owned velden blijven staan.
    """
    defs = [d for d in _attr_defs(db) if d.dim_product_field]
    if not defs:
        return 0
    q = db.query(models.DimProduct)
    if sku_ids:
        q = q.filter(models.DimProduct.sku_id.in_(sku_ids))
    products = q.all()

    existing = {}
    ev_q = db.query(models.PimAttributeValue)
    if sku_ids:
        ev_q = ev_q.filter(models.PimAttributeValue.sku_id.in_(sku_ids))
    for v in ev_q.all():
        existing[(v.sku_id, v.attribute_id)] = v

    count = 0
    for p in products:
        for d in defs:
            raw = getattr(p, d.dim_product_field, None)
            if raw is None or str(raw).strip() == "":
                continue
            val = str(raw).strip()
            row = existing.get((p.sku_id, d.id))
            if row is None:
                row = models.PimAttributeValue(
                    sku_id=p.sku_id, attribute_id=d.id, value=val,
                    source="DRS", updated_by="pim_sync")
                db.add(row)
                existing[(p.sku_id, d.id)] = row
                count += 1
            elif row.source == "DRS" and row.value != val:
                row.value = val
                row.updated_by = "pim_sync"
                count += 1
    db.flush()
    return count


def assign_families(db: Session) -> int:
    """Koppel producten zonder familie op basis van category_patterns."""
    families = db.query(models.PimFamily).filter(models.PimFamily.active == True).all()  # noqa: E712
    if not families:
        return 0
    content = {c.sku_id: c for c in db.query(models.PimProductContent).all()}
    count = 0
    for p in db.query(models.DimProduct).all():
        row = content.get(p.sku_id)
        if row is not None and row.family_id is not None:
            continue
        match = None
        cat = (p.category or "").lower()
        for f in families:
            patterns = [str(x).lower() for x in (f.category_patterns or [])]
            if cat and any(pat in cat or cat in pat for pat in patterns):
                match = f
                break
        if match is None:
            continue
        if row is None:
            row = models.PimProductContent(sku_id=p.sku_id, family_id=match.id)
            db.add(row)
            content[p.sku_id] = row
        else:
            row.family_id = match.id
        count += 1
    db.flush()
    return count


def _quality_checks(product: models.DimProduct, values: dict[str, str]) -> list[dict]:
    """Consistentie-/geldigheidschecks die de quality-score bepalen."""
    issues: list[dict] = []
    ean = values.get("ean") or ""
    if ean and len(ean) not in (8, 13):
        issues.append({"code": "EAN_LENGTE", "bericht": f"EAN '{ean}' heeft geen 8 of 13 cijfers"})
    gsm = values.get("paper_weight_gsm")
    if gsm:
        try:
            g = float(gsm)
            if g <= 0 or g > 500:
                issues.append({"code": "GRAMMAGE_RANGE", "bericht": f"Onwaarschijnlijke grammage: {gsm} g/m²"})
        except ValueError:
            issues.append({"code": "GRAMMAGE_NUMERIEK", "bericht": f"Grammage is niet numeriek: '{gsm}'"})
    name = values.get("product_name") or ""
    if name and len(name) < 10:
        issues.append({"code": "NAAM_TE_KORT", "bericht": "Productnaam korter dan 10 tekens"})
    desc = values.get("description") or ""
    if desc and len(desc) < 30:
        issues.append({"code": "OMSCHRIJVING_TE_KORT", "bericht": "Omschrijving korter dan 30 tekens"})
    return issues


def compute_completeness(db: Session, sku_ids: list[str] | None = None) -> int:
    """
    Bereken completeness- en quality-scores per SKU (overall) en per channel.
    Vervangt de scores van vandaag (idempotent per dag).
    """
    ensure_defaults(db)
    sync_drs_attributes(db, sku_ids)
    assign_families(db)

    defs = _attr_defs(db)
    defs_by_id = {d.id: d for d in defs}
    channels = db.query(models.PimChannel).filter(models.PimChannel.active == True).all()  # noqa: E712
    today = date.today()

    q = db.query(models.DimProduct)
    if sku_ids:
        q = q.filter(models.DimProduct.sku_id.in_(sku_ids))
    products = q.all()

    vq = db.query(models.PimAttributeValue)
    if sku_ids:
        vq = vq.filter(models.PimAttributeValue.sku_id.in_(sku_ids))
    values_by_sku: dict[str, dict[str, str]] = {}
    for v in vq.all():
        d = defs_by_id.get(v.attribute_id)
        if d is None or not v.value:
            continue
        values_by_sku.setdefault(v.sku_id, {})[d.code] = v.value

    # Oude scores van vandaag (of eerder) voor deze SKU's verwijderen
    del_q = db.query(models.PimCompletenessScore)
    if sku_ids:
        del_q = del_q.filter(models.PimCompletenessScore.sku_id.in_(sku_ids))
    del_q.delete(synchronize_session=False)
    db.flush()

    count = 0
    for p in products:
        vals = values_by_sku.get(p.sku_id, {})
        # Overall: gewogen over alle actieve attributen
        total_w = sum(d.weight or 1.0 for d in defs) or 1.0
        filled_w = sum((d.weight or 1.0) for d in defs if vals.get(d.code))
        completeness = round(100.0 * filled_w / total_w, 1)
        issues = _quality_checks(p, vals)
        quality = round(max(0.0, 100.0 - 15.0 * len(issues)), 1)
        missing = [d.code for d in defs if d.is_required and not vals.get(d.code)]
        db.add(models.PimCompletenessScore(
            sku_id=p.sku_id, channel_code=None,
            completeness_pct=completeness, quality_score=quality,
            channel_ready=False, missing_attributes=missing,
            quality_issues=issues, run_date=today))
        count += 1

        for ch in channels:
            req = list(ch.required_attribute_codes or [])
            if not req:
                continue
            ch_filled = [c for c in req if vals.get(c)]
            ch_missing = [c for c in req if not vals.get(c)]
            ch_pct = round(100.0 * len(ch_filled) / len(req), 1)
            threshold = ch.min_completeness_pct if ch.min_completeness_pct is not None else 80.0
            ready = ch_pct >= threshold and not issues
            db.add(models.PimCompletenessScore(
                sku_id=p.sku_id, channel_code=ch.code,
                completeness_pct=ch_pct, quality_score=quality,
                channel_ready=ready, missing_attributes=ch_missing,
                quality_issues=issues, run_date=today))
            count += 1
    db.commit()
    return count


# ─── AI-suggesties via de AI Gateway ─────────────────────────────────────────

AI_SUGGESTION_PROMPT = """Je bent een productcontent-specialist voor een Nederlandse office-supplies webshop.
Je krijgt productgegevens en een lijst met ontbrekende attributen.
Stel voor elk ontbrekend attribuut een waarde voor, alléén als je die met redelijke zekerheid
uit de productnaam/merk/categorie kunt afleiden. Verzin niets.

Antwoord UITSLUITEND met JSON in dit formaat:
{"suggesties": [{"attribute_code": "...", "value": "...", "rationale": "korte NL uitleg", "confidence": 0.0}]}
"""


def generate_ai_suggestions(db: Session, sku_ids: list[str] | None = None,
                            limit: int = 20, username: str = "system") -> dict:
    """
    Genereer AI-suggesties voor ontbrekende attributen via de AI Gateway.
    Suggesties worden altijd als PENDING opgeslagen — nooit automatisch toegepast.
    Fail-safe: zonder geconfigureerde AI-provider wordt niets gegenereerd.
    """
    import ai_gateway

    client, provider = ai_gateway._make_client()
    if client is None:
        return {"generated": 0, "skus_processed": 0, "ai_available": False,
                "message": "AI-dienst is niet geconfigureerd; geen suggesties gegenereerd."}

    ensure_defaults(db)
    defs = {d.code: d for d in _attr_defs(db)}
    # AI mag alleen attributen voorstellen die het straks ook mag schrijven:
    # DRS-owned velden (productmaster) worden uitgesloten (§4).
    ai_writable = {code for code, d in defs.items()
                   if not (d.source_owner == "DRS" and d.dim_product_field)}

    # Kies SKU's met ontbrekende verplichte attributen (laagste completeness eerst)
    sq = db.query(models.PimCompletenessScore).filter(
        models.PimCompletenessScore.channel_code.is_(None))
    if sku_ids:
        sq = sq.filter(models.PimCompletenessScore.sku_id.in_(sku_ids))
    scores = (sq.order_by(models.PimCompletenessScore.completeness_pct.asc())
              .limit(limit).all())
    targets = [s for s in scores if s.missing_attributes]

    generated = 0
    processed = 0
    for score in targets:
        product = db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == score.sku_id).first()
        if product is None:
            continue
        missing = list(score.missing_attributes or [])
        # Geen dubbele open suggesties voor hetzelfde attribuut
        open_codes = {s.attribute_code for s in db.query(models.PimAiSuggestion).filter(
            models.PimAiSuggestion.sku_id == score.sku_id,
            models.PimAiSuggestion.status == "PENDING").all()}
        missing = [m for m in missing if m not in open_codes and m in ai_writable]
        if not missing:
            continue

        context = {
            "sku_id": product.sku_id,
            "product_name": product.product_name,
            "brand": product.brand,
            "category": product.category,
            "subcategory": product.subcategory,
            "product_type": product.product_type,
            "paper_size": product.paper_size,
            "paper_weight_gsm": product.paper_weight_gsm,
            "ontbrekende_attributen": missing,
        }
        try:
            resp = client.chat.completions.create(
                model=ai_gateway.AI_MODEL,
                max_completion_tokens=1024,
                messages=[
                    {"role": "system", "content": AI_SUGGESTION_PROMPT},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False, default=str)},
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = raw.strip("`").lstrip("json").strip()
            payload = json.loads(raw)
        except Exception as e:  # fail-safe: sla deze SKU over, ga door
            logger.warning("PIM AI-suggestie mislukt voor %s: %s", score.sku_id, e)
            continue

        processed += 1
        for s in payload.get("suggesties", []):
            code = s.get("attribute_code")
            value = str(s.get("value") or "").strip()
            if not code or not value or code not in missing:
                continue
            d = defs.get(code)
            db.add(models.PimAiSuggestion(
                sku_id=score.sku_id,
                attribute_id=d.id if d else None,
                attribute_code=code,
                suggested_value=value,
                current_value=None,
                rationale=s.get("rationale"),
                confidence=float(s.get("confidence") or 0.0),
                model_version=ai_gateway.AI_MODEL,
                status="PENDING",
            ))
            generated += 1
    db.commit()
    return {"generated": generated, "skus_processed": processed, "ai_available": True,
            "message": f"{generated} suggestie(s) gegenereerd voor {processed} SKU('s)."}


def apply_suggestion(db: Session, suggestion: models.PimAiSuggestion, username: str) -> models.PimAttributeValue:
    """Pas een goedgekeurde suggestie toe als attribuutwaarde (bron = AI)."""
    d = None
    if suggestion.attribute_id:
        d = db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.id == suggestion.attribute_id).first()
    if d is None:
        d = db.query(models.PimAttributeDefinition).filter(
            models.PimAttributeDefinition.code == suggestion.attribute_code).first()
    if d is None:
        raise ValueError(f"Attribuutdefinitie '{suggestion.attribute_code}' niet gevonden")

    row = db.query(models.PimAttributeValue).filter(
        models.PimAttributeValue.sku_id == suggestion.sku_id,
        models.PimAttributeValue.attribute_id == d.id).first()
    # Source ownership (§4): AI mag DRS-owned velden en waarden van andere
    # bronnen nooit overschrijven — de suggestie blijft dan PENDING.
    reason = check_write_allowed(d, row, "AI")
    if reason:
        raise OwnershipConflict(reason)
    if row is None:
        row = models.PimAttributeValue(sku_id=suggestion.sku_id, attribute_id=d.id)
        db.add(row)
    row.value = suggestion.suggested_value
    row.source = "AI"
    row.confidence = suggestion.confidence
    row.updated_by = username
    suggestion.status = "APPROVED"
    suggestion.reviewed_by = username
    suggestion.reviewed_at = datetime.utcnow()
    db.flush()
    return row
