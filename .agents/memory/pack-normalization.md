---
name: Prijs-per-eenheid pack-normalisatie
description: Regels voor normalisatie van pakgrootte-veelvouden in de referentieprijs (code-review-eisen).
---

Regels die code review afdwong:

- Normalisatie (n×/1-op-n van de mediaan, ±2% tolerantie) staat **lós van de configureerbare uitbijterdrempel**: detecteer de pack-factor vóór de drempelcheck, anders telt een groot-pak-totaalprijs bij ruime drempels (tot 5.0) rauw mee en vervuilt de referentieprijs stil.
- "Pakgrootte bekend" betekent **sheets_per_pack > 0**; NULL/0/negatief is elders een datakwaliteitsfout en mag normalisatie nooit activeren. Regressietests voor alle drie vereist.
- Genormaliseerde fact-rijen: excluded_reason NULL + exclusion_detail {normalized: true, label "genormaliseerd (n×)"}; rerun-cleanup moet daarom filteren op excluded_reason ÓF exclusion_detail niet-NULL.

**Why:** twee opeenvolgende review-rejections op precies deze punten.
**How to apply:** bij elke wijziging aan calculate_reference_price/score_competition of nieuwe normalisatiepaden.
