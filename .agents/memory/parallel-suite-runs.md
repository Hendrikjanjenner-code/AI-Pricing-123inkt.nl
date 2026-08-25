---
name: Parallelle full-suite runs botsen op de gedeelde dev-DB
description: Waarom completion-validatie en de apitests-workflow nooit tegelijk mogen draaien
---
Regel: start de apitests-workflow niet (en laat hem niet lopen) terwijl markTaskComplete-validatie draait.
**Why:** beide draaien de volledige pytest-suite op dezelfde dev-database; tests als test_data_quality_scan (verwacht scanstatus 'geslaagd', ziet 'bezig' van de parallelle run) en test_hierarchy_autobuild (gedeelde boom/residu) falen dan met schijnbare regressies.
**How to apply:** wacht tot de apitests-workflow FINISHED is vóór markTaskComplete; bij validatiefalen eerst de verdachte tests standalone herdraaien voordat je code aanpast.
