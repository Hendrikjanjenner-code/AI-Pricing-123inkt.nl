---
name: BQ keyset NULL-watermerken
description: Keyset-paginatie op (watermerk, pk) verliest rijen met NULL-watermerk zonder COALESCE.
---
Keyset-paginatie die sorteert/filtert op `(CAST(wm AS TIMESTAMP), pk) > (:lk_wm, :lk_pk)` laat rijen met een NULL-watermerk stil wegvallen: de rijvergelijking evalueert naar NULL en Postgres sorteert NULLs standaard achteraan, dus de rij wordt nooit opgehaald.

**Why:** oude rijen zonder created_at bestaan echt in de dev-DB; een volledige sync miste die rijen zonder ooit een fout te geven.

**How to apply:** wrap het watermerk in filter én ORDER BY in `COALESCE(..., TIMESTAMP '0001-01-01')` zodat NULLs deterministisch vooraan sorteren, en map een None-lk_wm parameter naar datetime.min aan de caller-kant.
