/**
 * Centrale kennisbank: uitleg voor alle KPI's, scores en metrics.
 * Elke definitie bevat: korte tooltip, uitgebreide uitleg, formule, interpretatie en business-impact.
 */

export interface KpiDefinition {
  id: string;
  naam: string;
  afkorting?: string;
  categorie: KpiCategorie;
  korteUitleg: string;           // Voor hover tooltip (max 2 zinnen)
  uitgebreideUitleg: string;     // Voor modal
  formule?: string;              // Optionele formule
  interpretatie: string;         // Schaal-uitleg
  businessImpact: string;        // Wat betekent dit voor pricing?
  voorbeeld?: string;            // Praktisch voorbeeld
  gerelateerd?: string[];        // Gerelateerde KPI-id's
}

export type KpiCategorie =
  | "concurrentie"
  | "pricing"
  | "traffic"
  | "basket"
  | "bcg"
  | "forecasting"
  | "promotie"
  | "marge"
  | "ecosysteem"
  | "algemeen";

export const KPI_DEFINITIES: Record<string, KpiDefinition> = {

  // ── CONCURRENTIE ──────────────────────────────────────────────────────────

  pcis: {
    id: "pcis",
    naam: "Product Competition Intensity Score",
    afkorting: "PCIS",
    categorie: "concurrentie",
    korteUitleg: "Meet de totale concurrentiedruk op een SKU. Hogere score = meer pricing-risico bij afwijking van marktprijs.",
    uitgebreideUitleg: `De PCIS (Product Competition Intensity Score) geeft aan hoeveel concurrentiedruk een SKU ervaart vanuit de markt.

De score combineert zeven sub-scores die elk een ander aspect van concurrentie meten: prijsverschil met markt, aantal relevante concurrenten, voorraadbetrouwbaarheid van concurrenten, prijsvolatiliteit, marktaandeel, zoekzichtbaarheid en prijsindexafwijking.

Een hoge PCIS-score betekent dat klanten eenvoudig kunnen vergelijken en snel zullen overstappen bij een te hoog prijsverschil. Een lage PCIS-score geeft ruimte voor hogere marges.`,
    formule: `PCIS =
0.25 × prijsverschil_score
+ 0.20 × concurrent_count_score
+ 0.15 × CSRS (voorraadbetrouwbaarheid)
+ 0.15 × prijsvolatiliteit_score
+ 0.10 × marktaandeel_score
+ 0.10 × zoekzichtbaarheid_score
+ 0.05 × prijsindex_afwijking`,
    interpretatie: `0.00–0.30 → Lage concurrentiedruk (ruimte voor prijsverhoging)
0.30–0.60 → Gemiddelde concurrentiedruk (prijsaanpassingen voorzichtig doorvoeren)
0.60–0.80 → Hoge concurrentiedruk (prijswijzigingen riskant)
0.80–1.00 → Kritieke concurrentiedruk (marktprijs nauw volgen)`,
    businessImpact: `Hoge PCIS: prijsverhoging leidt waarschijnlijk tot omzetverlies. Prijsverlaging heeft meer impact op conversie. 
Lage PCIS: meer vrijheid om marge te optimaliseren zonder klanten te verliezen.`,
    voorbeeld: `HP 305 toner heeft PCIS 0.82 (kritiek): 4 relevante concurrenten, kleine prijsverschillen, hoge zoekzichtbaarheid. Een prijsverhoging van 5% riskeert significant conversieverlies.`,
    gerelateerd: ["csrs", "cis", "css"],
  },

  csrs: {
    id: "csrs",
    naam: "Competitor Stock Reliability Score",
    afkorting: "CSRS",
    categorie: "concurrentie",
    korteUitleg: "Meet hoe betrouwbaar een concurrent leverbaar is. Lage score = concurrent niet relevant voor pricing.",
    uitgebreideUitleg: `De CSRS meet of een concurrent structureel leverbaar is. Als een concurrent regelmatig out-of-stock is of traag levert, is hun prijs minder relevant als referentie.

Een concurrent met lage CSRS biedt klanten een slechte koopervaring, waardoor hun lage prijs minder aantrekkelijk is dan op het eerste gezicht lijkt.`,
    formule: `CSRS =
0.40 × beschikbaarheidspercentage
+ 0.25 × leversneelheids_score
+ 0.20 × voorraadstabiliteit_score
+ 0.15 × listing_consistentie_score`,
    interpretatie: `0.80–1.00 → Zeer betrouwbaar leverbaar (sterke concurrentierelevantie)
0.50–0.80 → Gemiddeld betrouwbaar
0.30–0.50 → Beperkt betrouwbaar
<0.30 → Onbetrouwbaar (laag gewicht in prijsberekening)`,
    businessImpact: "Bij lage CSRS kan een lage concurrentieprijs worden genegeerd in de pricing-beslissing, wat ruimte biedt voor een hogere prijs.",
    gerelateerd: ["pcis", "cis"],
  },

  cis: {
    id: "cis",
    naam: "Competition Intensity Score",
    afkorting: "CIS",
    categorie: "concurrentie",
    korteUitleg: "Geaggregeerde concurrentie-intensiteit per categorie. Combinatie van PCIS-scores van alle SKU's in de categorie.",
    uitgebreideUitleg: `De CIS (Competition Intensity Score) is een categorie-niveau aggregatie van de PCIS-scores. Hij geeft aan hoe competitief een productcategorie als geheel is.

De CIS helpt bij het bepalen van categoriestrategieën: in hoog-CIS categorieën is margeoptimalisatie riskanter.`,
    interpretatie: `Hoge CIS: categorie heeft scherpe marktprijzen, weinig margeruimte.
Lage CIS: categorieniche, meer pricing-vrijheid.`,
    businessImpact: "Categorieën met hoge CIS vereisen frequentere prijsmonitoring en snellere reactietijden op concurrentiewijzigingen.",
    gerelateerd: ["pcis"],
  },

  css: {
    id: "css",
    naam: "Competitor Search Share",
    afkorting: "CSS",
    categorie: "concurrentie",
    korteUitleg: "Percentage zoekopdrachten waarbij een concurrent zichtbaar is. Hoog CSS = concurrent domineert zoekresultaten.",
    uitgebreideUitleg: `De CSS (Competitor Search Share) meet hoeveel procent van de relevante zoekopdrachten een concurrent zichtbaar is in organische of betaalde zoekresultaten.

Een hoge CSS bij een concurrent betekent dat zij actief investeren in traffic-acquisitie voor dezelfde producten, wat de concurrentiedruk verhoogt.`,
    interpretatie: `>70%: concurrent domineert zoekopdrachten voor dit product
40–70%: sterke zoekaanwezigheid
<40%: beperkte zoekaanwezigheid`,
    businessImpact: "Concurrenten met hoge CSS trekken organisch veel bezoekers, waardoor ze volume-gevoeliger zijn voor prijsverschillen.",
    gerelateerd: ["pcis", "tds"],
  },

  // ── PRICING & MARGE ───────────────────────────────────────────────────────

  elasticiteit: {
    id: "elasticiteit",
    naam: "Prijselasticiteit",
    categorie: "pricing",
    korteUitleg: "Meet hoe gevoelig de vraag is voor prijswijzigingen. Sterk negatief = klein prijsverschil heeft grote impact op afzet.",
    uitgebreideUitleg: `Prijselasticiteit geeft aan hoe de vraag naar een product reageert op een prijswijziging.

Een elasticiteit van -2.0 betekent: 1% prijsverhoging leidt tot 2% vraagdaling. Een elasticiteit van -0.5 betekent: 1% prijsverhoging leidt tot slechts 0.5% vraagdaling (inelastisch).

Producten met hoge elasticiteit zijn prijsgevoeliger en vereisen voorzichtigheid bij prijsverhogingen.`,
    formule: `Elasticiteit = (% verandering in vraag) / (% verandering in prijs)

Voorbeeld:
Prijs stijgt 5% → afzet daalt 10%
Elasticiteit = -10% / 5% = -2.0`,
    interpretatie: `0 tot -0.5 → Inelastisch (prijsverhoging veilig)
-0.5 tot -1.0 → Matig elastisch (voorzichtig verhogen)
-1.0 tot -2.0 → Elastisch (prijsverhoging riskant)
<-2.0 → Sterk elastisch (prijsverhoging sterk ontmoedigd)`,
    businessImpact: "Bij hoge elasticiteit overstijgt het omzetverlies vaak de margewinst bij prijsverhogingen. Promoties kunnen juist winstgevend zijn.",
    voorbeeld: "Papier A4 heeft elasticiteit -1.8: 3% prijsverhoging leidt naar verwachting tot 5.4% minder afzet.",
    gerelateerd: ["ppfs", "breakeven_afzet"],
  },

  ppfs: {
    id: "ppfs",
    naam: "Price Pass-through Feasibility Score",
    afkorting: "PPFS",
    categorie: "pricing",
    korteUitleg: "Meet hoe goed een inkoopprijsstijging kan worden doorberekend aan klanten zonder significant volume te verliezen.",
    uitgebreideUitleg: `De PPFS (Price Pass-through Feasibility Score) beantwoordt de vraag: "Als onze inkoopprijs stijgt, kunnen we dat doorbereken zonder klanten te verliezen?"

De score combineert vier factoren: prijselasticiteit (hoe gevoelig is de klant?), concurrentiedruk (hoeveel ruimte laat de markt?), merkpositie (is het product uniek?) en substitutiedruk (zijn er alternatieven beschikbaar?).`,
    formule: `PPFS =
0.30 × (1 – elasticiteit_genormaliseerd)
+ 0.35 × (1 – PCIS)
+ 0.20 × merkpositionering_score
+ 0.15 × (1 – substitutie_druk)`,
    interpretatie: `0.70–1.00 → Uitstekend (kostenstijging volledig door te berekenen)
0.50–0.70 → Goed (gedeeltelijk doorberekenen)
0.30–0.50 → Matig (voorzichtig doorberekenen)
<0.30 → Slecht (doorberekening leidt tot volume-verlies)`,
    businessImpact: "Lage PPFS betekent dat een kostenstijging de marge aanzienlijk verlaagt omdat de verkoopprijs niet kan stijgen. Alternatief: kostenbesparing of mix-shift naar private label.",
    gerelateerd: ["elasticiteit", "pcis", "breakeven_afzet"],
  },

  breakeven_afzet: {
    id: "breakeven_afzet",
    naam: "Break-even Extra Afzet",
    categorie: "pricing",
    korteUitleg: "Hoeveel extra eenheden moeten worden verkocht om een prijsverlaging terug te verdienen in totale marge.",
    uitgebreideUitleg: `De break-even extra afzet beantwoordt: "Als we de prijs verlagen, hoeveel extra verkopen zijn dan nodig om dezelfde totale marge te behalen?"

Een hoge break-even afzet maakt een promotie riskant. Een lage break-even afzet maakt een promotie haalbaar, mits elasticiteit voldoende is.`,
    formule: `Break-even afzet =
(huidige_marge / nieuwe_marge_per_stuk) – huidige_verkopen

Of:
BE% = (prijsdaling%) / (marge% – prijsdaling%)

Voorbeeld:
Marge 20%, prijsdaling 5%:
BE% = 5% / (20% – 5%) = 33% extra afzet nodig`,
    interpretatie: `<10% extra afzet → Promotie veilig (lage elasticiteit nodig)
10–25% extra afzet → Matig risico
25–50% extra afzet → Hoog risico
>50% extra afzet → Promotie waarschijnlijk verlieslatend`,
    businessImpact: "Gebruik break-even analyse vóór elke promotie om te toetsen of verwacht volumestijging realistisch is.",
    voorbeeld: "Ordner A4 met 25% marge: 5% prijsdaling vereist 25% meer afzet om break-even te zijn. Haalbaar als elasticiteit hoog genoeg is.",
    gerelateerd: ["elasticiteit", "ppfs"],
  },

  beds: {
    id: "beds",
    naam: "Break-even Difficulty Score",
    afkorting: "BEDS",
    categorie: "pricing",
    korteUitleg: "Samengestelde score voor hoe moeilijk een promotie of prijsverlaging terug te verdienen is.",
    uitgebreideUitleg: `De BEDS (Break-even Difficulty Score) combineert meerdere factoren om te bepalen hoe riskant een promotie is:

- Hoe laag is de huidige marge? (lage marge = hogere break-even eis)
- Hoe inelastisch is de vraag? (inelastisch = extra volume onwaarschijnlijk)
- Hoe hoog is de concurrentiedruk? (hoge PCIS = volume-stijging minder zeker)
- Hoe groot is de promotiekorting?`,
    interpretatie: `0.00–0.30 → Lage moeilijkheid (promotie haalbaar)
0.30–0.60 → Gemiddelde moeilijkheid (kritisch evalueren)
0.60–1.00 → Hoge moeilijkheid (promotie waarschijnlijk verlieslatend)`,
    businessImpact: "Hoge BEDS betekent dat de commerciële organisatie realistische volumedoelen moet stellen vóór goedkeuring van de promotie.",
    gerelateerd: ["breakeven_afzet", "elasticiteit"],
  },

  mps: {
    id: "mps",
    naam: "Margin Protection Score",
    afkorting: "MPS",
    categorie: "marge",
    korteUitleg: "Meet hoe goed de huidige prijs de marge beschermt tegen inkoopprijsstijgingen en concurrentiedruk.",
    uitgebreideUitleg: `De MPS (Margin Protection Score) geeft aan hoe robuust de marge van een SKU is bij negatieve omstandigheden, zoals een inkoopprijsstijging of agressievere concurrentie.

Een hoge MPS betekent dat de marge redelijk stabiel blijft onder druk. Een lage MPS signaleert kwetsbaarheid.`,
    interpretatie: `0.70–1.00 → Sterke margebescherming
0.40–0.70 → Gemiddelde bescherming
<0.40 → Kwetsbare marge (actie aanbevolen)`,
    businessImpact: "SKU's met lage MPS vereisen monitoring en mogelijk een prijsaanpassing of kostenreductie bij de eerstvolgende inkooponderhandeling.",
    gerelateerd: ["ppfs", "elasticiteit"],
  },

  // ── TRAFFIC & DEMAND ──────────────────────────────────────────────────────

  tds: {
    id: "tds",
    naam: "Traffic Driver Score",
    afkorting: "TDS",
    categorie: "traffic",
    korteUitleg: "Meet hoe belangrijk een SKU is voor het aantrekken van bezoekers via SEO, SEA en organisch zoekverkeer.",
    uitgebreideUitleg: `De TDS (Traffic Driver Score) beantwoordt: "Hoe sterk trekt dit SKU bezoekers aan naar 123inkt.nl?"

De score combineert SEO-traffic, SEA-traffic, organische zichtbaarheid, extern zoekvolume, landingspaginasessies, nieuwe klantbijdrage, CTR en zoekontwikkeling.

SKU's met hoge TDS zijn cruciale acquisitiekanalen, ook al is hun directe marge bescheiden. Hun strategische waarde zit in het aantrekken van nieuwe klanten en het openen van basket-uitbreidingen.`,
    formule: `TDS =
0.20 × SEO_traffic_factor
+ 0.10 × SEA_traffic_factor
+ 0.15 × organische_zichtbaarheid
+ 0.20 × zoekvolume_factor
+ 0.10 × landingspagina_factor
+ 0.15 × nieuw_klant_factor
+ 0.05 × CTR_factor
+ 0.05 × trend_factor`,
    interpretatie: `0.80–1.00 → Kritieke Traffic Driver (beschermen, nooit agressief verhogen)
0.60–0.80 → Sterke Traffic Driver (voorzichtig aanpassen)
0.40–0.60 → Matige Traffic Driver
<0.40 → Lage traffic impact`,
    businessImpact: `Hoge TDS: prijsverhoging kan acquisitie schaden. SEO/SEA-kosten stijgen bij verlies van organische positie.
Lage TDS: meer vrijheid voor margeoptimalisatie.`,
    voorbeeld: "HP 305 toner heeft TDS 0.92: 3.200 SEO-bezoekers/maand, 45.000 extern zoekvolume. Prijsverhoging riskeert 15–20% SEO-positieverlies.",
    gerelateerd: ["eps", "bbs", "sevs"],
  },

  eps: {
    id: "eps",
    naam: "Entry Product Score",
    afkorting: "EPS",
    categorie: "traffic",
    korteUitleg: "Meet hoe vaak dit product het startpunt is van een klantaankoop of nieuwe klantsessie.",
    uitgebreideUitleg: `De EPS (Entry Product Score) beantwoordt: "Hoe vaak is dit SKU het eerste product dat een klant ziet of koopt bij 123inkt.nl?"

Entry products zijn cruciaal voor eerste indruk en klantacquisitie. Ze zetten de toon voor de klantrelatie en de kans op vervolgaankopen.`,
    formule: `EPS =
0.40 × eerste_product_in_sessie_%
+ 0.35 × nieuwe_klant_eerste_order_%
+ 0.25 × landingspagina_conversieratio`,
    interpretatie: `>0.60 → Sterk entry product (pricing nauwkeurig beheren)
0.30–0.60 → Gematigd entry product
<0.30 → Beperkte entry-rol`,
    businessImpact: "Prijsverhogingen op entry products schaden de eerste indruk en kunnen nieuwe klantacquisitie significant verlagen. Prijs als acquisitiemiddel, niet alleen als margeinstrument.",
    gerelateerd: ["tds", "sevs"],
  },

  // ── BASKET & ECOSYSTEEM ───────────────────────────────────────────────────

  bbs: {
    id: "bbs",
    naam: "Basket Builder Score",
    afkorting: "BBS",
    categorie: "basket",
    korteUitleg: "Meet hoe sterk een SKU bijdraagt aan winkelmandvulling en cross-sell activiteit.",
    uitgebreideUitleg: `De BBS (Basket Builder Score) beantwoordt: "Hoe sterk vergroot dit product het gemiddelde mandbedrag van een bestelling?"

Een SKU met hoge BBS wordt vaak samen met andere producten gekocht, verhoogt de gemiddelde bestelwaarde en stimuleert cross-sell. Dit maakt hem strategisch waardevol, ook bij beperkte directe marge.`,
    formule: `BBS =
0.30 × attach_rate
+ 0.20 × co-occurrence_score
+ 0.20 × basket_uplift_genormaliseerd
+ 0.15 × cross_sell_frequentie / 5
+ 0.15 × incrementele_marge_genormaliseerd`,
    interpretatie: `0.75–1.00 → Kritieke Winkelmandvuller (bundels en promoties sterk aanbevolen)
0.55–0.75 → Sterke Winkelmandvuller
0.35–0.55 → Matige Winkelmandvuller
<0.35 → Zwakke basket impact`,
    businessImpact: "SKU's met hoge BBS zijn ideaal voor bundelpromoties. Lage directe marge wordt gecompenseerd door hogere gemiddelde bestelwaarde en cross-sell inkomsten.",
    voorbeeld: "USB-kabel heeft BBS 0.78: wordt bij 62% van laptop-bestellingen toegevoegd, verhoogt mandbedrag gemiddeld €8,40.",
    gerelateerd: ["mas", "sevs", "eps"],
  },

  mas: {
    id: "mas",
    naam: "Margin Amplification Score",
    afkorting: "MAS",
    categorie: "basket",
    korteUitleg: "Meet hoeveel indirecte extra marge een SKU genereert via cross-sell, upsell en herhalingsaankopen.",
    uitgebreideUitleg: `De MAS (Margin Amplification Score) beantwoordt: "Hoeveel marge genereert dit SKU indirect — bovenop zijn eigen directe marge?"

Een SKU kan een lage directe marge hebben maar toch zeer waardevol zijn als hij regelmatig leidt tot aankoop van hogere-marge complementaire producten. Denk aan: een goedkope printer die doorlopende verkoop van cartridges stimuleert.`,
    formule: `MAS =
0.40 × basket_builder_score
+ 0.35 × repeat_contribution_score
+ 0.25 × private_label_bijdrage`,
    interpretatie: `0.70–1.00 → Hoge marge-amplificatie (cross-sell campagnes aanbevolen)
0.40–0.70 → Gemiddelde amplificatie
<0.40 → Beperkte indirecte margebijdrage`,
    businessImpact: "Hoge MAS rechtvaardigt lage of zelfs verlieslatende prijs als acquisitiestrategie voor high-margin follow-up verkopen.",
    gerelateerd: ["bbs", "sevs"],
  },

  sevs: {
    id: "sevs",
    naam: "SKU Ecosystem Value Score",
    afkorting: "SEVS",
    categorie: "ecosysteem",
    korteUitleg: "Totale commerciële waarde van een SKU: directe marge + traffic + basket + repeat + cross-sell + huismerk impact.",
    uitgebreideUitleg: `De SEVS (SKU Ecosystem Value Score) is de meest complete maatstaf voor de commerciële waarde van een SKU. Hij combineert zeven dimensies:

1. Traffic Driver Score — trekt bezoekers aan
2. Basket Builder Score — vergroot manden
3. Margin Amplification Score — genereert indirecte marge
4. Entry Product Score — trekt nieuwe klanten aan
5. Repeat Contribution Score — stimuleert herhalingsaankopen
6. Private Label Contribution — ondersteunt huismerkstrategie
7. Directe margebijdrage — eigen winstgevendheid

Een SKU met hoge SEVS maar lage directe marge is strategisch beschermenswaardig. Pricing alleen op directe marge doet de totale commerciële waarde onrecht.`,
    formule: `SEVS =
0.20 × TDS + 0.18 × BBS + 0.15 × MAS
+ 0.12 × EPS + 0.12 × RCS
+ 0.08 × PLCS + 0.15 × directe_marge_score`,
    interpretatie: `0.72–1.00 → KRITIEK (beschermen ongeacht directe marge)
0.52–0.72 → HOOG (pricing voorzichtig aanpassen)
0.32–0.52 → MEDIUM (regulier beheer)
<0.32 → LAAG (optimalisatie of sanering overwegen)`,
    businessImpact: `SEVS voorkomt dat strategisch waardevolle SKU's worden gesaneerd puur op basis van lage directe marge.
Gebruik SEVS als leidend criterium bij sanering, promotiebudgetallocatie en pricing guards.`,
    gerelateerd: ["tds", "bbs", "mas", "eps"],
  },

  rcs: {
    id: "rcs",
    naam: "Repeat Contribution Score",
    afkorting: "RCS",
    categorie: "basket",
    korteUitleg: "Meet hoe sterk een SKU herhalingsaankopen stimuleert. Hoog = klant komt regelmatig terug voor dit product.",
    uitgebreideUitleg: `De RCS (Repeat Contribution Score) meet in welke mate een SKU bijdraagt aan klantretentie via herhalingsaankopen.

Producten die regelmatig worden herbesteld (verbruiksartikelen, cartridges, papier) hebben een hoge RCS. Dit maakt ze waardevol als aankopingspunt voor een loyale klantrelatie.`,
    interpretatie: `0.65–1.00 → Hoge herhaalbijdrage (prijsstabiliteit aanbevolen)
0.40–0.65 → Gemiddelde herhaalbijdrage
<0.40 → Beperkte herhaalaankoop`,
    businessImpact: "SKU's met hoge RCS verliezen bij prijswijzigingen niet alleen de directe verkoop, maar risiceren ook de loyale klantrelatie.",
    gerelateerd: ["sevs", "mas"],
  },

  // ── BCG ───────────────────────────────────────────────────────────────────

  bcg_intern: {
    id: "bcg_intern",
    naam: "Interne BCG Classificatie",
    categorie: "bcg",
    korteUitleg: "SKU-classificatie op basis van omzetgroei en relatief marktaandeel binnen het eigen portfolio.",
    uitgebreideUitleg: `De Interne BCG Matrix classificeert SKU's op basis van twee dimensies:

**Omzetgroei** — groeit de vraag naar dit product?
**Relatief marktaandeel** — is dit een groot of klein deel van onze omzet?

De vier kwadranten:
- **Ster**: hoge groei, hoog aandeel → investeren en beschermen
- **Cash Cow**: lage groei, hoog aandeel → melken, weinig investeren
- **Question Mark**: hoge groei, laag aandeel → strategische beslissing nodig
- **Dog**: lage groei, laag aandeel → sanering overwegen`,
    interpretatie: `Star → Groeiend en sterk. Pricing ter ondersteuning van marktpositie.
Cash Cow → Stabiel en winstgevend. Marge maximaliseren.
Question Mark → Potentieel. Investeren of afstoten?
Dog → Weinig waarde. Saneren of herpositioneren.`,
    businessImpact: "BCG-classificatie stuurt lange-termijn portfolio-beslissingen: welke SKU's krijgen promotiebudget, pricing-ruimte of worden gesaneerd?",
    gerelateerd: ["bcg_extern", "pricing_power", "sevs"],
  },

  bcg_extern: {
    id: "bcg_extern",
    naam: "Externe BCG Classificatie",
    categorie: "bcg",
    korteUitleg: "BCG-classificatie op basis van marktgroei en prijspositie ten opzichte van de markt.",
    uitgebreideUitleg: `De Externe BCG Matrix plaatst een SKU in de bredere markt door marktgroei en concurrentiepositie te combineren.

In tegenstelling tot de interne BCG wordt hier de externe markt als referentie gebruikt, inclusief concurrentiedata.`,
    interpretatie: `Star: snelgroeiende markt, sterke marktpositie → agressief investeren
Cash Cow: volwassen markt, sterke positie → marge optimaliseren
Question Mark: groeimarkt, zwakke positie → differentiatie zoeken
Dog: krimpende markt, zwakke positie → afbouwen`,
    businessImpact: "Externe BCG helpt bij het bepalen of investeringen in een SKU marktaandeel opleveren of slechts marktkrimp volgen.",
    gerelateerd: ["bcg_intern", "pcis"],
  },

  pricing_power: {
    id: "pricing_power",
    naam: "Pricing Power Score",
    categorie: "bcg",
    korteUitleg: "Meet hoeveel vrijheid er is om de prijs te verhogen zonder significant volume te verliezen.",
    uitgebreideUitleg: `Pricing Power Score combineert elasticiteit, concurrentiedruk (PCIS), merkpositie en BCG-kwadrant tot één score voor pricing-vrijheid.

Hoge pricing power betekent: klanten accepteren een prijsstijging omdat er weinig alternatieven zijn of het product uniek is.`,
    formule: `Pricing Power =
0.35 × (1 – elasticiteit_genormaliseerd)
+ 0.30 × (1 – PCIS)
+ 0.20 × bcg_kwadrant_score
+ 0.15 × merkdifferentiatie_score`,
    interpretatie: `0.70–1.00 → Hoge pricing power (verhogen relatief veilig)
0.40–0.70 → Gemiddelde pricing power
<0.40 → Lage pricing power (verhogen riskant)`,
    businessImpact: "Hoge pricing power = ruimte voor margeoptimalisatie. Lage pricing power = prijsvolger, focus op kostenreductie en mix-shift.",
    gerelateerd: ["pcis", "elasticiteit", "bcg_intern"],
  },

  // ── FORECASTING ───────────────────────────────────────────────────────────

  procurement_opportunity: {
    id: "procurement_opportunity",
    naam: "Inkoop Kans Score",
    categorie: "forecasting",
    korteUitleg: "Meet of er een gunstig moment is voor bulkinkoop op basis van prijstrend en vraagprognose.",
    uitgebreideUitleg: `De Inkoop Kans Score combineert inkoopprijstrend, seizoenspatroon, verwachte vraag en leveranciersomstandigheden om te bepalen of dit een goed moment is voor extra inkoopvolume.

Hoge score = nu inkopen biedt een voordeel ten opzichte van later inkopen.`,
    interpretatie: `0.70–1.00 → Uitstekend inkoopmoment
0.40–0.70 → Acceptabel
<0.40 → Afwachten`,
    businessImpact: "Tijdige inkoop bij hoge kans-score kan significante kosten besparen bij verwachte prijsstijgingen.",
    gerelateerd: ["future_margin_risk"],
  },

  future_margin_risk: {
    id: "future_margin_risk",
    naam: "Toekomstig Marge Risico",
    categorie: "forecasting",
    korteUitleg: "Inschatting van margedruk in de komende 3-6 maanden op basis van inkoopprijstrend en marktdynamiek.",
    uitgebreideUitleg: `Het Toekomstig Marge Risico combineert verwachte inkoopprijsontwikkeling, concurrentiedruk, elasticiteit en seizoenspatronen om een risicoscore te berekenen.

Hoge score = significant risico op margedaling in komende periode.`,
    interpretatie: `0.70–1.00 → Hoog risico (actie vereist: pricing aanpassen of kosten reduceren)
0.30–0.70 → Matig risico
<0.30 → Laag risico`,
    businessImpact: "Hoog toekomstig margerisico signaleert dat pricing-actie of inkoop-onderhandeling op korte termijn nodig is.",
    gerelateerd: ["procurement_opportunity", "ppfs"],
  },

  // ── PROMOTIE ──────────────────────────────────────────────────────────────

  promotion_roi: {
    id: "promotion_roi",
    naam: "Promotie ROI",
    categorie: "promotie",
    korteUitleg: "Verwacht rendement op een promotie: extra marge door volumestijging minus kosten van kortingsverlening.",
    uitgebreideUitleg: `Promotie ROI = (extra marge door volumestijging) / (verloren marge door korting).

Een ROI > 1.0 betekent dat de promotie winstgevend is. Een ROI < 1.0 betekent verlies.`,
    formule: `Promotie ROI =
(volumestijging × huidige_marge) / (volume × kortingsbedrag_per_eenheid)`,
    interpretatie: `>2.0 → Uitstekend rendement
1.0–2.0 → Acceptabel rendement
<1.0 → Verlieslatende promotie`,
    businessImpact: "Promoties met lage ROI zijn alleen gerechtvaardigd als strategische doelen (klantacquisitie, marktaandeel) worden bereikt.",
    gerelateerd: ["breakeven_afzet", "elasticiteit"],
  },

  // ── ALGEMEEN ──────────────────────────────────────────────────────────────

  confidence_score: {
    id: "confidence_score",
    naam: "Advies Betrouwbaarheidsscore",
    categorie: "algemeen",
    korteUitleg: "Hoe zeker is het AI-model over dit prijsadvies? Gebaseerd op datakwaliteit, historische nauwkeurigheid en modelverzekering.",
    uitgebreideUitleg: `De betrouwbaarheidsscore geeft aan in welke mate het AI-pricing model vertrouwen heeft in zijn eigen advies.

Lage betrouwbaarheid treedt op bij:
- Beperkte verkoophistorie (nieuw product)
- Ontbrekende concurrentiedata
- Inconsistente historische data
- Hoge prijsvolatiliteit in het verleden

Bij <40% betrouwbaarheid wordt het advies als 'waarschuwing' gemarkeerd en is handmatige review aanbevolen.`,
    interpretatie: `80–100% → Hoge betrouwbaarheid (advies veilig uitvoeren)
60–80% → Goede betrouwbaarheid
40–60% → Matige betrouwbaarheid (extra review aanbevolen)
<40% → Lage betrouwbaarheid (handmatig beoordelen voor uitvoering)`,
    businessImpact: "Lage betrouwbaarheid betekent niet dat het advies verkeerd is, maar dat een pricing analist het advies handmatig moet bevestigen.",
    gerelateerd: [],
  },

  delta_marge: {
    id: "delta_marge",
    naam: "Margeverandering (Δ Marge)",
    categorie: "marge",
    korteUitleg: "Verwachte verandering in marge-percentage als het prijsadvies wordt opgevolgd. Positief = margeverbetering.",
    uitgebreideUitleg: `Δ Marge toont het verschil in margepercentage tussen de huidige prijs en de aanbevolen prijs, gecorrigeerd voor verwacht volume-effect.

Een positieve Δ Marge betekent dat de prijswijziging de marge verbetert. Een negatieve Δ Marge bij een prijsverlaging kan toch winstgevend zijn als het volume voldoende stijgt.`,
    interpretatie: `Positief: aanbevolen prijs verhoogt marge
Negatief: aanbevolen prijs verlaagt directe marge (check SEVS en BBS voor indirecte waarde)`,
    businessImpact: "Δ Marge is een korte-termijn indicator. Gebruik SEVS en BBS om de totale commerciële impact te beoordelen.",
    gerelateerd: ["elasticiteit", "sevs"],
  },

  attach_rate: {
    id: "attach_rate",
    naam: "Attach-rate",
    categorie: "basket",
    korteUitleg: "Percentage bestellingen waarbij dit product samen met minimaal één ander product wordt besteld.",
    uitgebreideUitleg: `De attach-rate geeft aan hoe vaak een product onderdeel is van een multi-product bestelling.

Een hoge attach-rate betekent dat dit product regelmatig als aanvullend product wordt besteld, wat bijdraagt aan hogere gemiddelde bestelwaarden.`,
    interpretatie: `>60% → Hoge attach-rate (sterk winkelmandvuller-profiel)
40–60% → Gemiddeld
<40% → Laag (vaak als enkel product besteld)`,
    businessImpact: "Hoge attach-rate rechtvaardigt bundelprijzen en cross-sell plaatsingen op productpagina's.",
    gerelateerd: ["bbs", "co_occurrence"],
  },

  co_occurrence: {
    id: "co_occurrence",
    naam: "Co-occurrence Score",
    categorie: "basket",
    korteUitleg: "Hoe vaak dit product samen met de top-5 populairste SKU's in de categorie wordt besteld.",
    uitgebreideUitleg: `De co-occurrence score meet hoe sterk een product verbonden is met de meest populaire SKU's. Een hoge score wijst op een complementair product dat goed past in bestaande bestellingpatronen.`,
    interpretatie: `>0.70 → Sterk co-occurrence (ideaal voor bundels)
0.40–0.70 → Gemiddeld
<0.40 → Beperkt co-occurrence`,
    businessImpact: "Hoge co-occurrence is een signaal voor bundelbouw en cross-sell algoritmes.",
    gerelateerd: ["bbs", "attach_rate"],
  },
};

// ── Hulpfuncties ──────────────────────────────────────────────────────────────

export function getDefinitie(id: string): KpiDefinition | undefined {
  return KPI_DEFINITIES[id.toLowerCase().replace(/[^a-z_]/g, "_")];
}

export function getDefinitiesPerCategorie(cat: KpiCategorie): KpiDefinition[] {
  return Object.values(KPI_DEFINITIES).filter(d => d.categorie === cat);
}

export const ALLE_CATEGORIEEN: { id: KpiCategorie; label: string }[] = [
  { id: "concurrentie", label: "Concurrentie" },
  { id: "pricing",     label: "Pricing & Doorberekenbaarheid" },
  { id: "marge",       label: "Marge & Bescherming" },
  { id: "traffic",     label: "Traffic & Vraag" },
  { id: "basket",      label: "Basket & Cross-sell" },
  { id: "ecosysteem",  label: "Ecosysteemwaarde" },
  { id: "bcg",         label: "BCG Classificatie" },
  { id: "forecasting", label: "Forecasting & Inkoop" },
  { id: "promotie",    label: "Promotie" },
  { id: "algemeen",    label: "Algemeen" },
];
