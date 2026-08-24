---
name: Competitor master approval & blocked
description: Goedkeurings-/blokkeerstatus leeft op de globale competitor-master; regels voor sync en uitsluiting.
---

De canonieke competitor-master draagt zelf de goedkeurings- en blokkeerstatus.

- Elke beslissing — handmatig én auto-approve in discovery — werkt de master
  in dezelfde transactie bij; feed-sync/upsert raakt deze velden nooit aan.
- Blocked wordt op alle LEES-paden gefilterd (rankings, historie, CIS,
  coverage, events, availability), niet alleen bij herberekening — bestaande
  snapshots van vóór de blokkade tonen de concurrent anders nog.
- De master is een globaal register terwijl beslissingen shop-gescoped worden
  genomen: een blokkade werkt platform-breed (bewuste keuze voor de
  single-org pilot; bij echte multi-tenancy moet status per shop).
- Shop-gescopede tellers mogen nooit op globale master-metadata (zoals
  aliassen) leunen; gebruik per-shop feitdata.

**Why:** stale snapshots en globale metadata in shop-tellers gaven verkeerde
inzichten; auto-approvals bereikten de master anders pas na een herstart.
