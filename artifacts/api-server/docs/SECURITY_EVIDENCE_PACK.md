# SECURITY & DATA PROTECTION EVIDENCE PACK

AI Commercial Intelligence Platform — versie 17 augustus 2026.

> Dit document maakt géén juridische certificeringsclaims (geen ISO 27001-,
> SOC 2- of AVG-certificering). Onderdelen die een formele security- of
> privacyreview vereisen zijn gemarkeerd met **[FORMELE REVIEW VEREIST]**.

---

## 1. Architecture diagram

```
┌────────────────────────── Replit-omgeving ──────────────────────────┐
│                                                                     │
│  React/Vite frontend (pricing-engine)          Slides/landing       │
│        │  HTTPS (proxied, mTLS)                                     │
│        ▼                                                            │
│  FastAPI API-server (/api) ── JWT-auth (HS256, SESSION_SECRET)      │
│        │            │                │                              │
│        │            │                └── Engines (30+ intelligence- │
│        │            │                    modules, batch/on-demand)  │
│        ▼            ▼                                               │
│  PostgreSQL     Externe bronnen: PriceShape-feed, DRS/Datareport-   │
│  (Neon,         import, BigQuery (read), Google Analytics (read)    │
│  beheerd)                                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. Data Flow Diagram

1. **Inkomend**: CSV/XLSX-uploads (validate-first via `/api/uploads/validate`),
   PriceShape-feed (volledige catalogus), DRS-dagimport, BigQuery-sync.
2. **Verwerking**: canonical data model (`dim_*`/`fact_*`) → intelligence-engines →
   `intelligence_signals` → Decision Engine → beslissingen + scenario's.
3. **Uitgaand**: dashboards/API-reads (JWT-beschermd), CSV-exports,
   prijsuitvoering (dry-run/push met audit).
4. Alle schrijfpaden lopen via geauthenticeerde, rol-gecontroleerde endpoints;
   engine-runs loggen naar de auditlog.

## 3. Data Ownership Matrix

| Data | System of record | Platformrol |
|---|---|---|
| Productstamdata | DRS/Datareport (extern) | Kopie in `dim_product` |
| Concurrentprijzen | PriceShape (extern) | Kopie in `fact_competitor_price_daily` |
| Verkoop/marge | DRS/BigQuery (extern) | Kopie in `fact_sales_daily` |
| Traffic | Google Analytics/BigQuery | Kopie in `fact_traffic_daily` |
| Signals, beslissingen, scenario's, audit | **Dit platform** | Eigenaar |
| Gebruikers & rollen | **Dit platform** | Eigenaar |

## 4. Data Classification

| Klasse | Voorbeelden | Bescherming |
|---|---|---|
| Vertrouwelijk-commercieel | kostprijzen, marges, strategieën | Auth + RBAC, geen publieke endpoints |
| Persoonsgegevens (beperkt) | gebruikersnaam, e-mail, loyalty-member-id's | Auth + RBAC; wachtwoorden bcrypt-gehasht |
| Secrets | `SESSION_SECRET`, connector-credentials | Replit Secrets (env), nooit in code/repo |
| Publiek | geen | — |

Er worden geen bijzondere persoonsgegevens (gezondheid, etc.) verwerkt.
**[FORMELE REVIEW VEREIST]** voor AVG-grondslag van loyalty-klantdata.

## 5. RBAC Matrix

Rollen: `admin`, `pricing_manager`, `analyst`, `viewer` (gevalideerd bij
aanmaken/wijzigen; onbekende rollen worden geweigerd — `auth.py`).

| Capability | admin | pricing_manager | analyst | viewer |
|---|---|---|---|---|
| Reads (producten, signals, decisions, dashboards) | ✔ | ✔ | ✔ | ✔ |
| Auditlog lezen | ✔ | ✔ | ✔ | ✖ |
| Engine-runs (decisions, forecast, promotion, …) | ✔ | ✔ | ✖ | ✖ |
| Loyalty-run / datakwaliteitsscan / connectors | ✔ | ✔ | ✔ | ✖ |
| Uploads/imports (alle datasets) | ✔ | ✔ | ✖ | ✖ |
| Approvals/overrides (recommendations, decisions) | ✔ | ✔ | ✖ | ✖ |
| Usersbeheer, shops aanmaken, admin/clear-data | ✔ | ✖ | ✖ | ✖ |

Aantoonbaar getest per rol per endpoint in `tests/test_rbac_matrix.py`
(matrix + generieke check dat **iedere** niet-publieke `/api`-route 401 geeft
zonder token) — Gate 2.

## 6. Secrets architecture

- Secrets uitsluitend via Replit Secrets/omgevingsvariabelen (`SESSION_SECRET`,
  `DATABASE_URL`, connector-keys). Geen secrets in code of git.
- JWT-signing key = `SESSION_SECRET`; dev-fallback logt een expliciete
  waarschuwing en in productie een error (auth.py) — productie vereist gezet secret.
- Secrets-scan (HoundDog): **0 bevindingen** (17 aug 2026).

## 7. AI data flow

- AI-gebruik: productmatching en (geplande) Copilot via Replit AI Gateway-proxy.
- Naar het AI-model gaan alleen productnamen/kenmerken en geaggregeerde
  metrics; geen wachtwoorden, secrets of loyalty-persoonsgegevens.
- Er worden geen modellen getraind op klantdata; alleen inference.
- **[FORMELE REVIEW VEREIST]**: contractuele verwerkersafspraken met de
  AI-provider vóór productie.

## 8. External providers

| Provider | Doel | Datarichting |
|---|---|---|
| Replit (hosting, secrets, deployments) | Platform | — |
| Neon PostgreSQL (via Replit) | Database | opslag |
| PriceShape | Concurrentprijzen | inkomend |
| DRS/Datareport | Product/verkoopdata | inkomend |
| Google BigQuery / Analytics | Verkoop/trafficdata | inkomend (read-only) |
| Replit AI Gateway (OpenAI-compatibel) | Matching/Copilot | uitgaand (beperkt, zie §7) |

## 9. Security test results (17 aug 2026)

- **Dependency audit**: 0 critical; 2 high (cryptography CVE-2026-69247,
  pyasn1 CVE-2026-59884) → **beide gefixt** (upgrade naar 50.0.0 resp. 0.6.4). Nu: 0 open.
- **Secrets scan (HoundDog)**: 0 bevindingen.
- **SAST (Semgrep)**: 4 critical + 1 high gemeld, alle geanalyseerd als
  false positive (zie §10); mitigatie toegevoegd.
- **Geautomatiseerde security-tests** (`tests/test_security.py`,
  `test_rbac_matrix.py`, `test_shop_scoping.py`): sessie/JWT-manipulatie
  (tampered, expired, verkeerde key, alg=none, niet-bestaande user), SQL-injectie
  (login + queryparams), input-validatie, uploadvalidatie, IDOR/shop-isolatie,
  privilege-escalatie, audit-immutabiliteit — allemaal groen.
- **Rate limiting**: niet aanwezig op applicatieniveau; zie §16.

## 10. Open vulnerabilities

| Ernst | Bevinding | Status |
|---|---|---|
| Critical | geen | — (Gate 1 voldaan) |
| High | SAST: "SQL-injectie" in `routes/admin.py` (TRUNCATE/COUNT met tabelnaam) | **False positive, gemitigeerd**: tabelnamen komen uit `pg_tables` (niet uit user-input), endpoint is admin-only, en namen worden nu extra gefilterd op `[a-zA-Z0-9_]+` |
| High | SAST: path traversal `engine/import_engine.py` (openpyxl) | **False positive**: er wordt uit een in-memory `BytesIO` gelezen, geen bestandspad uit user-input |
| Medium | Geen rate limiting op login/API | Geaccepteerd risico voor pilot (interne gebruikersgroep); aanbeveling in §16 |
| Medium | JWT niet intrekbaar vóór expiry (24 u); logout is client-side | Geaccepteerd risico; mitigatie: deactiveren van de user blokkeert direct (getest) |
| Low | Geen expliciete maximale uploadgrootte in applicatiecode | Platform-proxy begrenst request-omvang; aanbeveling in §16 |

## 11. Audit logging

- Geschreven bij: login, imports, engine-runs, recommendations, approvals,
  rejections, overrides, prijsuitvoering (dry-run/push/rollback), shop- en
  modelwijzigingen, loyalty-acties.
- Lezen: alleen admin/pricing_manager/analyst (`GET /api/audit-log`).
- **Niet verwijderbaar via de API**: er bestaat geen DELETE-route
  (afgedwongen door test `test_no_delete_route_for_audit_log`).

## 12. Backup strategy

Zie `docs/backup_restore.md`: beheerde Neon-PITR + Replit-checkpoints,
aangevuld met logische `pg_dump`-backups (aanbevolen dagelijks / vóór grote
imports), retentie ≥ 14 dagen.

## 13. Restore strategy

Gedocumenteerde `pg_restore`-procedure met verificatiestappen.
**Restore-test uitgevoerd op testdata (17 aug 2026): geslaagd** —
88/88 tabellen en 21/21 users identiek hersteld in een scratch-database.

## 14. Data retention

- Facttabellen: onbeperkt gedurende de pilot; BigQuery-brondata volgens
  `docs/bigquery_retention_policy.md`.
- Auditlog: onbeperkt (bewijsfunctie), niet verwijderbaar door gebruikers.
- Signals: levenscyclus actief → dismissed/superseded; engine-reruns vervangen
  pending output maar bewaren menselijke beslissingen.
- **[FORMELE REVIEW VEREIST]**: definitieve bewaartermijnen voor
  loyalty-persoonsgegevens.

## 15. Deletion procedures

- Per-domein verwijderen: admin-only endpoints (o.a. loyalty-demo-data,
  Paper_Copy delete-all met bevestigingszin).
- Volledige reset: `DELETE /api/admin/clear-data` (admin-only; users standaard
  behouden, `include_users=true` voor volledige wipe).
- Individuele gebruiker: verwijderen/deactiveren via usersbeheer (admin-only);
  deactivering blokkeert tokens direct.

## 16. Production recommendations

1. **Rate limiting** toevoegen op `/api/auth/login` en mutatie-endpoints
   (bijv. slowapi) vóór externe blootstelling.
2. **Token-revocatie**: kortere token-TTL of een denylist bij logout.
3. **Uploadlimieten**: expliciete maximale bestandsgrootte en extensie-allowlist
   in de uploadroutes.
4. `SESSION_SECRET` verplicht maken in productie (nu: error-log bij ontbreken;
   beter: weigeren te starten).
5. Security headers (CSP, HSTS) op de frontend-serving laag.
6. Dependency-audit en testsuite in de validatieflow houden (geregistreerd:
   `apitests`, `typecheck`) en periodiek herdraaien.
7. **[FORMELE REVIEW VEREIST]**: externe pentest + AVG/DPIA-review vóór
   productie met echte klantdata.

---

### Bijlage: testresultaten (17 aug 2026)

- `pytest tests/` — **94 tests, allemaal groen**, waaronder:
  - berekeningstests (marge, prijsindex, strategieën, safety rules, ISV/switching, PCIS-klassen);
  - RBAC-matrix per rol per endpoint + auth-verplichting op alle routes;
  - security-tests (§33-categorieën);
  - 8 end-to-end acceptance-ketens (§44), incl. human-approvalflow;
  - bestaande integratietests (foundation, shop-scoping, data-integratie, loyalty-ledger, decisions, platform).
- Frontend `tsc --noEmit` — 0 fouten (10 bestaande typefouten gefixt).
