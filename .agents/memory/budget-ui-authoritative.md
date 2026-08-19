---
name: Budget-UI toelating
description: UI-blokkering van AI-budget moet de server-toelatingsregel volgen, niet ruwe tellers
---
De server weigert een call al als tokens_reserved + _UPFRONT_TOKEN_RESERVATION > max_tokens_per_day; een UI-check op `used >= max` laat dus vragen door die server-side falen.
**Why:** een frontend met een eigen (lossere) uitputtingsregel laat vragen door die server-side falen, wat gebruikers een verwarrende generieke fout geeft.
**How to apply:** laat het budget-endpoint een autoritatief `exhausted`-veld teruggeven en baseer alle disabled states daarop; toon 429-races als budgetmelding, niet als generieke storing.
