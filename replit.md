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
    engine/
      pricing_engine.py   Main orchestrator (run_pricing_engine)
      strategies.py       8 strategy implementations
      safety_rules.py     Safety guardrails

  pricing-engine/      React + Vite frontend
    src/
      lib/auth.tsx     AuthContext + JWT token management
      pages/           12 pages (login, dashboard, recommendations, etc.)
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
- `model_runs`, `import_jobs`, `audit_log`

## Frontend Pages (12)

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

## Environment Variables

- `DATABASE_URL` — Replit-managed PostgreSQL (auto-set)
- `SESSION_SECRET` — JWT signing secret (Replit secret)
- `PORT` — Service port (set by Replit workflow system)
