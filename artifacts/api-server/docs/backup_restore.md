# Backup & Restore-procedure (§55)

## Backupstrategie

| Onderdeel | Aanpak |
|---|---|
| Database | Replit-beheerde PostgreSQL (Neon) met platform-side point-in-time recovery; daarnaast logische backups via `pg_dump -Fc` |
| Frequentie | Platform: continu (checkpoints + PITR). Aanbevolen aanvullend: dagelijkse `pg_dump` vóór grote imports/engine-runs |
| Retentie | Dumps: minimaal 14 dagen bewaren; zie ook `bigquery_retention_policy.md` voor brondata-retentie |
| Applicatiecode | Git + Replit-checkpoints (elke agentwijziging is een herstelpunt) |

## Backup maken

```bash
pg_dump -Fc "$DATABASE_URL" -f backup_$(date +%Y%m%d).dump
```

## Restore-procedure

1. Maak (of leeg) een doel-database.
2. `pg_restore --no-owner --no-privileges -d "<DOEL_URL>" backup_YYYYMMDD.dump`
3. Verifieer: aantal tabellen, aantal users, steekproef op kernfeiten (`dim_product`, `fact_sales_daily`, `decisions`).
4. Wijs `DATABASE_URL` naar de herstelde database en herstart de API-workflow.

## Uitgevoerde restore-test (17 aug 2026, testdata)

- `pg_dump -Fc` van de ontwikkeldatabase (88 tabellen) — < 1 s.
- Restore naar scratch-database `evidence_restore_test` met `pg_restore --no-owner --no-privileges`.
- Verificatie: **88/88 tabellen** en **21/21 users** identiek tussen bron en restore.
- Scratch-database daarna verwijderd.

Resultaat: **GESLAAGD** — de gedocumenteerde procedure herstelt een volledige, consistente kopie.
