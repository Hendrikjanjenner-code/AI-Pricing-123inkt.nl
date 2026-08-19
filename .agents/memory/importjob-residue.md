---
name: ImportJob-residu breekt volgordetests
description: Achterblijvende api_sync ImportJobs uit eerdere suite-runs breken "meest recente job"-aannames
---
Regel: tests die aannemen dat hun eigen faaljob de meest recente api_sync_priceshape job is, breken op een gedeelde DB met residu-succesjobs van eerdere runs (sync-endpointtests persisteren echte jobs zonder cleanup).
**Why:** FEED_UNREACHABLE-detectie kijkt alleen naar de nieuwste job; run 2 van de suite zag succesjobs van run 1 en detecteerde niets.
**How to apply:** maak de faaljob met created_at "nu" (meest recent) en dateer completed_at terug om een oude storing te simuleren; verwacht warning i.p.v. error wanneer er een recente succesjob bestaat.
