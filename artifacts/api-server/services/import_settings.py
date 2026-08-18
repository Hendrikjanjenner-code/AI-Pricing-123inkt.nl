"""
Importselectie-instellingen (aan/uitvinken) voor feed-connectoren.

Persistent in de database (FeedImportSetting) zodat keuzes een herstart
overleven. Toegepast door feed_ingest (automatische + handmatige sync) én de
handmatige PriceShape-upload, zodat álle importpaden dezelfde selectie volgen.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

import models

# Alle bekende data-onderdelen met hun standaardwaarde (alles aan).
DEFAULT_COMPONENTS: dict[str, bool] = {
    "own_prices": True,          # eigen dagprijzen (fact_price_daily)
    "cost_prices": True,         # kostprijzen op product + dagprijs
    "competitor_prices": True,   # concurrentprijzen (fact_competitor_price_daily)
    "availability": True,        # voorraad/levertijd van concurrenten
    "extra_attributes": True,    # alle overige (raw) feedvelden
}

COMPONENT_LABELS_NL: dict[str, str] = {
    "own_prices": "Eigen prijzen",
    "cost_prices": "Kostprijzen",
    "competitor_prices": "Concurrentprijzen",
    "availability": "Voorraad & levertijd concurrenten",
    "extra_attributes": "Extra feedvelden (raw attributen)",
}


def get_settings(db: Session, connector_name: str = "priceshape") -> dict:
    """Lees de instellingen; ontbrekende rij of onderdelen = standaard (alles aan)."""
    row = db.query(models.FeedImportSetting).filter(
        models.FeedImportSetting.connector_name == connector_name
    ).first()
    components = dict(DEFAULT_COMPONENTS)
    disabled: list[str] = []
    if row:
        stored = row.components or {}
        for key in components:
            if isinstance(stored.get(key), bool):
                components[key] = stored[key]
        disabled = [str(d).strip().lower() for d in (row.disabled_competitors or []) if str(d).strip()]
    return {
        "connector_name": connector_name,
        "components": components,
        "disabled_competitors": sorted(set(disabled)),
        "updated_by": row.updated_by if row else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def save_settings(db: Session, components: dict, disabled_competitors: list[str],
                  username: str, connector_name: str = "priceshape") -> dict:
    """Upsert de instellingen. Onbekende component-sleutels worden geweigerd."""
    unknown = [k for k in (components or {}) if k not in DEFAULT_COMPONENTS]
    if unknown:
        raise ValueError(f"Onbekende data-onderdelen: {', '.join(unknown)}")
    clean_components = {k: bool(v) for k, v in (components or {}).items()}
    clean_disabled = sorted({str(d).strip().lower() for d in (disabled_competitors or []) if str(d).strip()})

    row = db.query(models.FeedImportSetting).filter(
        models.FeedImportSetting.connector_name == connector_name
    ).first()
    if row is None:
        row = models.FeedImportSetting(connector_name=connector_name)
        db.add(row)
    merged = dict(DEFAULT_COMPONENTS)
    merged.update({k: v for k, v in (row.components or {}).items() if k in DEFAULT_COMPONENTS})
    merged.update(clean_components)
    row.components = merged
    row.disabled_competitors = clean_disabled
    row.updated_by = username
    db.commit()
    return get_settings(db, connector_name)


def component_enabled(settings: dict, key: str) -> bool:
    return bool(settings.get("components", {}).get(key, DEFAULT_COMPONENTS.get(key, True)))


def competitor_disabled(settings: dict, domain: str) -> bool:
    return (domain or "").strip().lower() in set(settings.get("disabled_competitors", []))
