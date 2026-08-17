# BigQuery Data Ownership Matrix & Retentiebeleid

## Overzicht

BigQuery is de **historische/analytische datalaag** van het AI Pricing & Commercial Intelligence Platform. PostgreSQL blijft de **operationele bron** voor actieve data en real-time beslissingen.

---

## Data Ownership Matrix

| Tabel | Eigenaar | PostgreSQL | BigQuery | Retentie BQ | Notitie |
|---|---|---|---|---|---|
| `dim_product` | Pricing Team | Primair | Kopie | 3 jaar | Snapshot bij elke sync |
| `dim_category` | Pricing Team | Primair | Kopie | 3 jaar | |
| `dim_shop` | Platform Admin | Primair | Kopie | 3 jaar | |
| `dim_competitor` | Competition Engine | Primair | Kopie | 3 jaar | |
| `fact_sales_daily` | Sales/ERP | Primair | Historisch archief | 5 jaar | Datum-gepartitioneerd |
| `fact_price_daily` | Pricing Engine | Primair | Historisch archief | 5 jaar | Datum-gepartitioneerd |
| `fact_competitor_price_daily` | PriceShape / Scraper | Primair | Historisch archief | 3 jaar | Datum-gepartitioneerd |
| `fact_inventory_daily` | WMS/ERP | Primair | Historisch archief | 3 jaar | |
| `fact_pricing_recommendation_daily` | AI Pricing Engine | Primair | AI-output archief | 5 jaar | Model audit trail |
| `sku_competition_score` | Competition Engine | Primair | Analytics | 3 jaar | PCIS/CIS scores |
| `fact_bcg_classification_daily` | BCG Engine | Primair | Analytics | 3 jaar | |
| `intelligence_signals` | Alle engines | Primair | Analytics | 2 jaar | Signaalhistorie |
| `bq_sync_batches` | Platform | BigQuery | Meta | 1 jaar | Sync audit trail |
| `bq_query_costs` | Platform | PostgreSQL + BQ | Meta | 1 jaar | Kostenmeting |

---

## Sync-pijplijn

### Werkwijze
- **Incrementeel**: alleen rijen nieuwer dan het laatste watermerk worden geëxporteerd
- **Watermerk**: `MAX(updated_at)` of `MAX(date)` per tabel, opgeslagen als `ImportJob` in PostgreSQL
- **Batchgrootte**: maximaal 50.000 rijen per run
- **Frequentie**: handmatig via `/api/bigquery/sync` of geautomatiseerd via Scheduled Deployment

### Faalveiligheid
- BigQuery-storingen blokkeren nooit de operationele PostgreSQL-laag
- Lege feeds verwijderen nooit valide BigQuery-data (last-known-good principe)
- Elke sync-batch wordt geregistreerd als `ImportJob` (source='bigquery') voor traceerbaarheid

---

## Retentiebeleid

### Fact-tabellen (5 jaar)
- `fact_sales_daily`, `fact_price_daily`, `fact_pricing_recommendation_daily`
- Reden: audit trail, trend-analyse, model-validatie, managementrapportage

### Dimensies en analytics (3 jaar)
- Alle dim-tabellen, PCIS/CIS-scores, BCG-classificaties, concurrentprijzen
- Reden: historische context voor pricing decisions, compliance

### Signalen (2 jaar)
- `intelligence_signals`
- Reden: signaaleffectiviteit meten; oudere signalen zijn zelden nog relevant

### Meta (1 jaar)
- Sync-batches, query-kosten
- Reden: operationele controle; ouder dan 1 jaar is niet actiegericht

---

## Dataset-structuur

| Dataset | Doel | Toeang |
|---|---|---|
| `pricing_facts` | Dagelijkse fact-tabellen | Pricing Team, Analysts |
| `pricing_dims` | Dimensies (product, categorie, shop) | Alle rollen |
| `pricing_analytics` | Scores, aanbevelingen, signalen | Analysts, Managers |
| `pricing_meta` | Sync-batches, kostenmeting | Platform Admin |

---

## Kostenbeheer

- Alle BigQuery-tabellen zijn **datum-gepartitioneerd** → queries scannen alleen de benodigde partities
- Tabellen zijn geclusterd op meest gebruikte filtervelden (shop_id, sku_id, etc.)
- Query-kosten worden automatisch gemeten en opgeslagen in `fact_bq_query_cost`
- Kosten zijn zichtbaar via `/api/bigquery/costs`
- Tarief: **$6,25 per TB** gescand (Google Cloud on-demand, regio EU, aug 2026)

---

## Query-routing

Het semantic layer routeert queries automatisch:
- **Operationele queries** (≤ 90 dagen, real-time beslissingen) → **PostgreSQL**
- **Historische queries** (> 90 dagen, management snapshots, trend-analyse) → **BigQuery** (met PostgreSQL-fallback als BQ niet beschikbaar is)

---

## Configuratie

### Vereiste omgevingsvariabelen

**Optie 1 — Service Account JSON:**
```
BQ_SERVICE_ACCOUNT_JSON=<volledige JSON-inhoud van service-account sleutel>
```

**Optie 2 — Project ID + Application Default Credentials:**
```
BQ_PROJECT_ID=<google-cloud-project-id>
GOOGLE_APPLICATION_CREDENTIALS=<pad-naar-service-account-json>
```

### Datasets aanmaken
Datasets worden automatisch aangemaakt bij de eerste sync (locatie: `EU`).

---

## Contacten

| Rol | Verantwoordelijkheid |
|---|---|
| Platform Admin | BigQuery-credentials, dataset-beheer, kostenbewaking |
| Pricing Team | Sync-configuratie, retentiebeleid fact-tabellen |
| Data Engineer | Schema-wijzigingen, sync-pijplijn aanpassingen |
