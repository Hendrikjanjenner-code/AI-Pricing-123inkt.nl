---
name: Merge kan module-constanten stil laten vallen
description: Auto-rebase/merge van taken kan module-level constanten of blokken uit een bestand laten verdwijnen; NameErrors worden vaak door fail-safe fallbacks verzwolgen.
---

Bij het samenvoegen van parallelle taken op hetzelfde bestand kan de auto-merge een module-level constante of codeblok stilletjes laten verdwijnen, terwijl de gebruikende code blijft staan.

**Why:** dit gebeurde tweemaal in één sessie: een retry-constante verdween uit een routes-bestand (NameError pas in tests) en een FTS-rank-drempel verdween uit de AI-gateway — daar werd de NameError door een try/except-fallback verzwolgen en leek de feature gewoon "0 resultaten" te geven.

**How to apply:** faalt validatie na een rebase met een NameError of met een fail-safe pad dat plots leeg resultaat geeft, grep dan eerst of de gebruikte constante/functie nog ergens GEDEFINIEERD is in plaats van de logica te debuggen. Reken erop dat pre-merge groene tests niets zeggen over de post-merge staat; valideer opnieuw na elke rebase.
