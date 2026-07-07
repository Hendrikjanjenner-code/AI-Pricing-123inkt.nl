# AI Pricing Decision Engine

## Overview

Production-grade pricing operations platform for a multi-category B2B/B2C e-commerce company (modelled on 123inkt). A pricing analyst's daily cockpit: review AI recommendations, approve/reject them, and push approved prices to PriceShape.

pnpm workspace monorepo with a Python FastAPI backend and React+Vite frontend.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **Frontend**: React + Vite (artifact: `pricing-engine`, path: `/`)
- **Backend**: Python 3.11 FastAPI (artifact: `api-server`, path: `/api`)
- **Database**: PostgreSQL (Replit-managed, `DATABASE_URL` env var)
- **ORM**: SQLAlchemy (Python)
- **Auth**: JWT (python-jose) + bcrypt, 24-hour tokens, 4 roles
- **ML layer**: pandas, numpy, scikit-learn
- **API codegen**: Orval (from OpenAPI spec in `lib/api-spec/openapi.yaml`)
- **Client hooks**: `@workspace/api-client-react` (React Query)
- **Charts**: Recharts
- **UI**: Tailwind + shadcn/ui components

## Architecture

```
artifacts/
  api-server/          FastAPI app (Python)
    main.py            App entry + router registration
    database.py        SQLAlchemy engine/session
    models.py          ORM models (all tables)
    auth.py            JWT + bcrypt auth utilities
    seed.py            Demo data seeder (runs on startup if empty)
    routes/
      auth.py          POST /login, POST /logout, GET /me
      products.py      GET/PATCH /products
      categories.py    GET /categories, GET/PUT /category-strategies
      recommendations.py  GET/POST /recommendations + approve/reject/override
      dashboard.py     GET /dashboard/summary, /charts/*
      uploads.py       POST /uploads/* (8 CSV types)
      data_quality.py  GET /data-quality
      substitutions.py GET /substitutions
      model_health.py  GET /model-health, GET/POST /model-runs
      exports.py       GET /exports/recommendations (+ /download)
      users.py         GET/POST/PATCH/DELETE /users
      skus.py          GET /skus/{id}/history
      competition.py   GET /competition/summary|skus|skus/{id}|charts/*
      ab_tests.py      GET /ab-tests, GET /ab-tests/{id}
    engine/
      pricing_engine.py      Main orchestrator (run_pricing_engine)
      strategies.py          8 strategy implementations
      safety_rules.py        Safety guardrails
      competition_engine.py  PCIS scoring (7 sub-scores → competition class)

  pricing-engine/      React + Vite frontend
    src/
      lib/auth.tsx     AuthContext + JWT token management
      pages/           15 pages (login, dashboard, recommendations, competition, ab-tests, etc.)
      components/      Sidebar layout, ProtectedRoute, UI components

lib/
  api-spec/
    openapi.yaml       OpenAPI 3.0 spec (~40 endpoints, source of truth)
    orval.config.ts    Codegen config
  api-client-react/    Generated React Query hooks
  api-zod/             Generated Zod schemas
```

## Key Commands

```bash
# Run codegen after changing OpenAPI spec
pnpm --filter @workspace/api-spec run codegen

# Typecheck all packages
pnpm run typecheck

# Backend starts via workflow (uvicorn)
# cd artifacts/api-server && uvicorn main:app --host 0.0.0.0 --port $PORT --reload
```

## Pricing Strategies (8 types)

1. **SUBSTITUTION_PORTFOLIO** — Optimise A-brand / private-label price gap
2. **COMPETITOR_INDEX** — Track competitor average and maintain target price index
3. **MARGIN_OPTIMIZATION** — Grid-search for margin-maximising price
4. **STOCK_CLEARANCE** — Graduated discount to liquidate overstock
5. **BASKET_BUILDER** — Stay competitive on basket-driver SKUs
6. **VOLUME_DISCOUNT** — Lower price for high-elasticity volume SKUs
7. **REPEAT_PURCHASE** — Price stability for recurring buyers
8. **LOW_VELOCITY** — Protect margin on slow-moving items

## Safety Rules

- Price floor: cost_price × 1.01
- Min/max price guardrails per SKU
- Max ±5% price change per day
- Out-of-stock blocks recommendation (except STOCK_CLEARANCE)
- Low confidence (<40%) flags recommendation as warning

## Demo Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin123 |
| Pricing Manager | pricing_manager | manager123 |
| Analyst | analyst | analyst123 |
| Viewer | viewer | viewer123 |

## Database Tables

- `users` — 4 roles: admin, pricing_manager, analyst, viewer
- `dim_product` — 26 seeded SKUs across 9 categories
- `dim_category`, `category_strategy_mapping`
- `map_substitution` — A-brand / private-label pairs
- `fact_sales_daily`, `fact_price_daily`, `fact_competitor_price_daily`
- `fact_inventory_daily`, `fact_basket_affinity`
- `fact_pricing_recommendation_daily` — 24 seeded recommendations
- `sku_competition_score` — 26 PCIS scores (backfilled via backfill_new_tables.py)
- `ab_tests`, `ab_test_results` — 1 test · 26 SKU results (13 AI / 13 CONTROL)
- `model_runs`, `import_jobs`, `audit_log`
- `schema_migrations` — audit trail of columns auto-added by `migrate.py` (change_key, table, column, ddl, applied_at)

## Frontend Pages (15)

1. `/` — Dashboard (KPIs + 4 Recharts charts)
2. `/recommendations` — Filterable table, bulk approve
3. `/recommendations/:id` — Detail: factors, competitor landscape, audit trail
4. `/skus` — SKU management table
5. `/skus/:id` — Deep dive: price/sales/margin/stock/competitor charts
6. `/categories` — Category strategy mapping (inline editable)
7. `/data-upload` — 8 CSV upload cards + import job history
8. `/data-quality` — Quality score + issues table
9. `/substitutions` — A-brand vs private-label pairs
10. `/model-health` — Last run, trigger new run
11. `/export` — Export approved recommendations as CSV for PriceShape
12. `/settings` — User management (admin only)
13. `/competition` — PCIS scores, price index, class distribution (filterable SKU table + 2 charts)
14. `/competition/:sku_id` — PCIS sub-score bars + radar chart + competitor price table
15. `/ab-tests` — AI vs CONTROL uplift, margin/revenue/conversion KPIs, statistical confidence

## Database Initialisation (new / empty DB)

Run the single bundled command to populate all demo data tables in the correct order:

```bash
python artifacts/api-server/backfill_all.py
```

This runs the backfill scripts sequentially, each idempotent (already-filled tables are skipped):

| # | Script | Data |
|---|--------|------|
| 1 | `backfill_new_tables` | Competition scores, A/B tests, CIS, elasticiteit, ISV |
| 2 | `backfill_category_hierarchy` | Categorieënhiërarchie |
| 3 | `backfill_bcg` | BCG-classificaties |
| 4 | `backfill_traffic` | Traffic & zoekvolume |
| 5 | `backfill_intelligence` | Kosten, marketing, OCS, inkoop, economie, BCG-transities |
| 6 | `backfill_break_even` | Kostprijswijziging & break-even analyse |
| 7 | `backfill_ecosystem` | Traffic driver & mandjeintelligentie |

The individual scripts can still be run standalone if you only need to refresh one table group.
`backfill_modules` (scraping/pilot config) was removed in the PriceShape-only refactor.

## PriceShape-only refactor (no internal scraping)

The platform relies exclusively on the PriceShape competitor feed — there is **no**
internal web-scraping and **no** Pilot Paper_Copy module.

- Removed backend: all scraping routes/services, pilot & paper-copy routes/services,
  the standalone AI-matching engine, `backfill_modules.py`, and the
  `ScrapeSchedule` / `CompetitorScrapeConfig` / `FactScrapeResult` models.
- **Concurrent Discovery** (`engine/competitor_discovery.py`) derives competitors
  from real `FactCompetitorPriceDaily` feed rows (SKU overlap, category coverage,
  avg price_index), `discovery_method="FEED"`. No KENNISBANK seed list.
- **AI Matching** is populated from the real feed by GTIN/EAN
  (`feed_ingest.build_ai_matches`), wired into the model run after competition scoring.
- **Prijsstrategie-herkenning** now lives under Competition at
  `/competition/strategie-herkenning`, computed live from competitor price history
  (`GET /api/competition/strategies`) with a `low_history` flag + `history_notice`
  when < 5 days of history exist.
- **Honest empty states**: Traffic, Basket/Mandje, Economic, and (sales-based)
  Elasticity pages render `components/ExterneDatabronVereist` — they show **no**
  synthetic data and instead point to DRS/GA4 integration. The old synthetic
  backfills for these tables may still run, but these pages never present them.
  DRS/GA4 integration pages live under the "Externe databronnen" sidebar group.

## Gotchas

- Seed guard (`if users.count() > 0: return`) means new tables won't seed on existing DBs.
  Run `python artifacts/api-server/backfill_all.py` to initialise all demo data at once.
  Add new backfill scripts to the `STEPS` list in `backfill_all.py` to keep it complete.
- New pages (competition, ab-tests) use direct `fetch()` with Bearer token, not generated hooks.
- Login endpoint is `POST /api/auth/login` and returns `{ user, token }` (field is `token`, not `access_token`).

## Environment Variables

- `DATABASE_URL` — Replit-managed PostgreSQL (auto-set)
- `SESSION_SECRET` — JWT signing secret (Replit secret)
- `PORT` — Service port (set by Replit workflow system)
