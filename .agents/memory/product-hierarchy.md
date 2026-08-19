---
name: Canonieke producthiërarchie
description: Duurzame ontwerpregels van het centrale hiërarchiesysteem (staged import, padmaterialisatie)
---

# Canonieke producthiërarchie

- Import is staged en niet-destructief (upload→validate→impact→apply); apply claimt de job atomisch via een conditionele status-UPDATE zodat parallelle applies onmogelijk zijn.
- **Impact en apply moeten dezelfde doelresolutie gebruiken** (optionId eerst, anders pad). **Why:** impact diende als goedkeuringspoort maar rapporteerde bij pad-only bestanden alles als "verplaatst" terwijl apply niets wijzigde.
- **Validatiefouten blokkeren apply**; gedeeltelijk toepassen is een expliciete opt-in. Eén SKU naar meerdere paden in één bestand is een validatiefout, geen stille eerste-rij-keuze.
- Verplaatste toewijzingen worden `superseded`, nooit verwijderd; nodes die uit het bestand verdwijnen blijven actief tenzij expliciete opt-in tot deactiveren.
- De gematerialiseerde leaf-padtabel moet bij **elke** boommutatie (import én node-PATCH) volledig gesynct worden, anders raakt hij stil verouderd.
