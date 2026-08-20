"""
Centrale domeinnormalisatie voor concurrent-identiteit.

Concurrenten komen als ruwe strings binnen (feed-vendors, uploads, discovery):
`https://www.example.nl`, `WWW.Example.nl/`, `example.nl` zijn dezelfde
concurrent maar zouden zonder normalisatie als aparte identiteiten belanden —
met versnipperde scores en dubbele discovery-kandidaten tot gevolg.

`normalize_domain` is de ENIGE plek waar deze regels wonen; feed-ingest,
uploads, discovery en profielopbouw gebruiken allemaal deze functie.

Regels (bewust conservatief — alleen presentatievarianten, geen inhoudelijke
herschrijving):
- whitespace strippen, kleine letters;
- protocol (`http://`, `https://`) strippen;
- `www.`-prefix strippen;
- pad/trailing slash na de host strippen (`example.nl/shop/` → `example.nl`);
- niet-domeinachtige namen (bijv. vendor-namen zonder punt) worden alleen
  getrimd en kleingeschreven — nooit verminkt.

De oorspronkelijke schrijfwijze blijft herleidbaar: ingest bewaart de ruwe
waarde als alias (raw_attributes `_domain_alias` per rij, en centraal in
`DimCompetitor.aliases`).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("uvicorn.error")

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def normalize_domain(raw: str | None) -> str:
    """Normaliseer een concurrent-/domeinstring naar zijn canonieke vorm.

    Retourneert "" voor lege input. Verliest nooit de hele identiteit: als er
    na het strippen niets overblijft, valt de functie terug op de getrimde,
    kleingeschreven invoer.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    lowered = s.lower()
    out = _SCHEME_RE.sub("", lowered)
    # Alles na de host (pad, query, fragment) hoort niet bij de identiteit.
    for sep in ("/", "?", "#"):
        idx = out.find(sep)
        if idx != -1:
            out = out[:idx]
    out = out.strip()
    if out.startswith("www.") and len(out) > 4:
        out = out[4:]
    out = out.strip(". ")
    return out or lowered


# ── Eenmalige merge van bestaande varianten ──────────────────────────────────
#
# Bestaande databases kunnen al domeinvarianten bevatten. Deze migratie voegt
# ze eenmalig samen (AuditLog-marker), niet-destructief:
# - rijen worden HERNOEMD naar het canonieke domein;
# - botst een hernoeming met een al-canonieke rij, dan wint de bestaande
#   canonieke rij en wordt alleen de overtollige variantrij verwijderd
#   (goedkeuringen en historie van de canonieke rij blijven staan);
# - goedkeuringsstatus wordt nooit gedowngraded: een APPROVED-variant draagt
#   zijn goedkeuring over op de canonieke queue-rij;
# - aliassen worden bewaard in DimCompetitor.aliases.

_MARKER_ENTITY = "competitor_domain_merge"
_MARKER_ACTION = "variants_merged"


def _alias_add(aliases: list | None, *values: str) -> list:
    out = list(aliases or [])
    for v in values:
        if v and v not in out:
            out.append(v)
    return out


def register_competitor_sighting(db, raw_name: str | None,
                                 seen_date=None) -> str | None:
    """Canoniseer een concurrentnaam én bewaar de oorspronkelijke schrijfwijze.

    Gedeeld hulpmiddel voor ALLE niet-feed schrijfpaden (handmatige uploads,
    PriceShape REST/upload): upsert de registerrij in dim_competitor, voeg de
    ruwe schrijfwijze toe als alias wanneer die afwijkt van het canonieke
    domein, en werk last_seen_date bij. Geeft de canonieke naam terug (of
    None bij lege invoer). De aanroeper commit zelf.
    """
    import models
    from datetime import date as _date
    if not raw_name or not str(raw_name).strip():
        return None
    raw = str(raw_name).strip()
    canon = normalize_domain(raw)
    if not canon:
        return None
    reg = (db.query(models.DimCompetitor)
           .filter(models.DimCompetitor.competitor_name == canon).first())
    if reg is None:
        reg = models.DimCompetitor(competitor_name=canon[:255])
        db.add(reg)
    if raw.lower() != canon:
        reg.aliases = _alias_add(getattr(reg, "aliases", None), raw) or None
    seen = seen_date or _date.today()
    if reg.last_seen_date is None or seen > reg.last_seen_date:
        reg.last_seen_date = seen
    return canon


def _competitor_fk_refs():
    """Alle gemapte kolommen met een ForeignKey naar dim_competitor.

    Metadata-gedreven zodat een nieuwe verwijzende tabel automatisch wordt
    meegenomen in de merge (geen handmatige lijst die kan verouderen).
    """
    import models
    refs = []
    for mapper in models.Base.registry.mappers:
        cls = mapper.class_
        table = getattr(cls, "__table__", None)
        if table is None or table.name == "dim_competitor":
            continue
        for col in table.columns:
            for fk in col.foreign_keys:
                if fk.column.table.name == "dim_competitor":
                    refs.append((cls, getattr(cls, col.name)))
    return refs


def merge_competitor_domain_variants(db) -> dict:
    """Voer de eenmalige variant-merge uit (idempotent via AuditLog-marker).

    Retourneert een rapport {table: {renamed, collapsed}} van wat er is
    samengevoegd. Draait bij elke start maar doet na de eerste keer niets.
    """
    import models
    from datetime import datetime
    from sqlalchemy import func

    # Concurrency-safe: twee gelijktijdig startende workers mogen de merge
    # niet allebei uitvoeren. Postgres advisory-lock; op andere backends
    # (SQLite-tests) is dit een no-op.
    try:
        from sqlalchemy import text as _text
        db.execute(_text("SELECT pg_advisory_xact_lock(84726101)"))
    except Exception:
        db.rollback()

    done = (db.query(models.AuditLog)
            .filter(models.AuditLog.entity_type == _MARKER_ENTITY,
                    models.AuditLog.action == _MARKER_ACTION)
            .first())
    if done:
        return {}

    report: dict[str, dict] = {}

    # 1. DimCompetitor eerst: het register draagt de aliassen.
    #    Varianten samenvoegen op canoniek domein; offers herwijzen.
    comps = db.query(models.DimCompetitor).all()
    by_canon: dict[str, list] = {}
    for c in comps:
        by_canon.setdefault(normalize_domain(c.competitor_name), []).append(c)
    dim_renamed = dim_collapsed = 0
    for canon, group in by_canon.items():
        if not canon:
            continue
        # Winnaar: de rij die al canoniek heet, anders de oudste.
        winner = next((c for c in group if c.competitor_name == canon), None)
        if winner is None:
            winner = min(group, key=lambda c: c.competitor_id)
        aliases = _alias_add(getattr(winner, "aliases", None),
                             *[c.competitor_name for c in group
                               if c.competitor_name != canon])
        for c in group:
            if c is winner:
                continue
            # ALLE FK-verwijzingen (offers, matches, alerts, …) metadata-
            # gedreven herwijzen naar de winnaar vóór de delete — anders
            # blokkeert een FK de delete of blijven wezen-verwijzingen achter.
            for ref_model, ref_col in _competitor_fk_refs():
                db.query(ref_model).filter(
                    ref_col == c.competitor_id
                ).update({ref_col.key: winner.competitor_id},
                         synchronize_session=False)
            db.delete(c)
            dim_collapsed += 1
        if winner.competitor_name != canon:
            dim_renamed += 1
        winner.competitor_name = canon
        winner.aliases = aliases or None
    db.flush()
    if dim_renamed or dim_collapsed:
        report["dim_competitor"] = {"renamed": dim_renamed,
                                    "collapsed": dim_collapsed}

    # 2. Discovery-queue: goedkeuring nooit verliezen.
    q_rows = db.query(models.CompetitorDiscoveryQueue).all()
    q_by: dict[tuple, list] = {}
    for r in q_rows:
        q_by.setdefault((normalize_domain(r.domain), r.shop_id), []).append(r)
    q_renamed = q_collapsed = 0
    _status_rank = {"APPROVED": 2, "PROPOSED": 1, "REJECTED": 0}
    for (canon, _sid), group in q_by.items():
        if not canon:
            continue
        winner = max(group, key=lambda r: (_status_rank.get(r.status, 0), r.id))
        for r in group:
            if r is winner:
                continue
            # Goedkeuring van een variant overdragen op de winnaar.
            if (_status_rank.get(r.status, 0)
                    > _status_rank.get(winner.status, 0)):
                winner.status = r.status
                winner.approved_by = r.approved_by
                winner.approved_at = r.approved_at
            db.delete(r)
            q_collapsed += 1
        if winner.domain != canon:
            q_renamed += 1
        winner.domain = canon
        if winner.competitor_name:
            winner.competitor_name = canon
    db.flush()
    if q_renamed or q_collapsed:
        report["competitor_discovery_queue"] = {"renamed": q_renamed,
                                                "collapsed": q_collapsed}

    # 3. Metadata-gedreven: ALLE gemapte tabellen met een competitor_name-
    #    kolom (behalve de twee hierboven al behandelde). Hernoemen naar
    #    canoniek; bij botsing binnen een botsingssleutel wint de bestaande
    #    canonieke rij en vervalt de variantrij — nooit een IntegrityError.
    #
    #    Botsingssleutels per tabel = alle UNIQUE-constraints/-indexen waar
    #    competitor_name deel van uitmaakt (overige kolommen vormen de
    #    sleutel). Tabellen zonder zo'n constraint krijgen waar zinvol een
    #    logische sleutel (facts), anders is hernoemen altijd veilig.
    _LOGICAL_KEYS: dict[str, list[tuple[str, ...]]] = {
        # Geen DB-unique, maar logisch is (shop, dag, sku, bron, concurrent)
        # één rij — variant + canoniek op dezelfde sleutel mag niet dubbel.
        "fact_competitor_price_daily": [("shop_id", "date", "sku_id", "source")],
    }

    def _collision_keys(model) -> list[tuple[str, ...]]:
        from sqlalchemy import UniqueConstraint
        keys: list[tuple[str, ...]] = []
        table = model.__table__
        for cons in table.constraints:
            if isinstance(cons, UniqueConstraint):
                cols = [c.name for c in cons.columns]
                if "competitor_name" in cols:
                    keys.append(tuple(c for c in cols if c != "competitor_name"))
        for idx in table.indexes:
            if idx.unique:
                cols = [c.name for c in idx.columns]
                if "competitor_name" in cols:
                    keys.append(tuple(c for c in cols if c != "competitor_name"))
        keys.extend(_LOGICAL_KEYS.get(table.name, []))
        return keys

    handled = {models.DimCompetitor, models.CompetitorDiscoveryQueue}
    generic = []
    for mapper in models.Base.registry.mappers:
        cls = mapper.class_
        if cls in handled:
            continue
        if "competitor_name" in getattr(cls, "__table__").columns:
            generic.append(cls)

    for model in sorted(generic, key=lambda m: m.__tablename__):
        table = model.__tablename__
        key_sets = _collision_keys(model)
        distinct = [n for (n,) in
                    db.query(model.competitor_name).distinct().all() if n]
        renames = {n: normalize_domain(n) for n in distinct
                   if normalize_domain(n) and normalize_domain(n) != n}
        if not renames:
            continue
        renamed = collapsed = 0
        for old, canon in renames.items():
            for key_cols in key_sets:
                # Verwijder variantrijen die binnen deze sleutel botsen met
                # een rij die (al dan niet net hernoemd) canoniek heet.
                canon_keys = {
                    tuple(getattr(r, c) for c in key_cols)
                    for r in db.query(model)
                    .filter(model.competitor_name == canon).all()
                }
                if not canon_keys and not key_cols:
                    continue
                for r in db.query(model).filter(
                        model.competitor_name == old).all():
                    if tuple(getattr(r, c) for c in key_cols) in canon_keys:
                        db.delete(r)
                        collapsed += 1
                db.flush()
            renamed += (db.query(model)
                        .filter(model.competitor_name == old)
                        .update({"competitor_name": canon},
                                synchronize_session=False))
            db.flush()
        report[table] = {"renamed": renamed, "collapsed": collapsed}

    db.add(models.AuditLog(
        entity_type=_MARKER_ENTITY, entity_id="v1", action=_MARKER_ACTION,
        performed_by="system", timestamp=datetime.utcnow(),
        details=f"Domeinvarianten samengevoegd: {report or 'geen gevonden'}",
    ))
    db.commit()
    if report:
        logger.info("Concurrent-domeinmerge uitgevoerd: %s", report)
    return report
