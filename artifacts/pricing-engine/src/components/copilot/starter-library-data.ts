import type { CopilotStarter } from "@workspace/api-client-react";

/**
 * Fail-safe kopie van de gecureerde starterbibliotheek. Deze houdt Copilot
 * bruikbaar als /copilot/status tijdelijk niet bereikbaar is. De server blijft
 * gezaghebbend voor rechten en weigert een starter alsnog indien nodig.
 */
export const FALLBACK_STARTERS: CopilotStarter[] = [
  {
    key: "competitors-attention", module_key: "competition", module_label: "Concurrentie",
    title: "Belangrijkste concurrenten",
    question: "Welke concurrenten zijn binnen mijn huidige selectie het belangrijkst en waarom?",
    description: "Rangschikt concurrenten op invloed en licht de belangrijkste factoren toe.",
    required_function: "get_competitor_ranking", available: true,
  },
  {
    key: "position-one-room", module_key: "competition", module_label: "Concurrentie",
    title: "Positie 1 en prijsruimte",
    question: "Waar staan wij op positie 1 en waar kunnen we veilig verhogen?",
    description: "Zoekt producten waar de eigen prijs marktleider is en duidt prijsruimte.",
    required_function: "get_portfolio_price_position", available: true,
  },
  {
    key: "more-expensive", module_key: "competition", module_label: "Concurrentie",
    title: "Duurder dan de markt",
    question: "Bij welke producten zijn wij duurder dan onze belangrijkste concurrenten?",
    description: "Brengt ongunstige prijsposities binnen de actieve selectie in beeld.",
    required_function: "get_portfolio_price_position", available: true,
  },
  {
    key: "price-winner", module_key: "competition", module_label: "Concurrentie",
    title: "Wie wint op prijs?",
    question: "Welke concurrent wint het vaakst op prijs binnen deze categorie?",
    description: "Vergelijkt de prijspositie van aanbieders binnen de huidige categorie.",
    required_function: "get_competitor_ranking", available: true,
  },
  {
    key: "excluded-prices", module_key: "competition", module_label: "Concurrentie",
    title: "Uitgesloten prijzen",
    question: "Welke uitgesloten concurrentprijzen beïnvloeden de vergelijking niet?",
    description: "Legt uit welke observaties buiten de betrouwbare vergelijking vallen.",
    required_function: "get_price_position", available: true,
  },
  {
    key: "margin-loss", module_key: "pricing", module_label: "Pricing & aanbevelingen",
    title: "Margeverlies vinden", question: "Waar verliezen we op dit moment marge?",
    description: "Toont de grootste margedalingen en waar actie nodig is.",
    required_function: "get_margin_erosion", available: true,
  },
  {
    key: "private-label", module_key: "assortment", module_label: "Assortiment & substitutie",
    title: "Huismerkpotentie", question: "Welke producten hebben de grootste huismerkpotentie?",
    description: "Vindt producten met kansrijke huismerkalternatieven.",
    required_function: "get_private_label_potential", available: true,
  },
  {
    key: "promotion", module_key: "sales", module_label: "Verkoop, marge & break-even",
    title: "Effectieve promoties", question: "Welke promotie werkte het afgelopen kwartaal het best?",
    description: "Vergelijkt gemeten uplift en incrementele marge.",
    required_function: "get_promotion_effectiveness", available: true,
  },
  {
    key: "supplier-risk", module_key: "forecast", module_label: "Voorraad, forecast & inkoop",
    title: "Leveranciersrisico", question: "Bij welke leveranciers lopen we margerisico?",
    description: "Brengt inkooprisico en margedruk per leverancier of product in beeld.",
    required_function: "get_supplier_risk", available: true,
  },
  {
    key: "active-signals", module_key: "data_quality", module_label: "Data quality & imports",
    title: "Dataproblemen met impact",
    question: "Welke actieve signalen vragen nu aandacht en op welke data zijn ze gebaseerd?",
    description: "Vat actuele signalen en hun brondata samen.",
    required_function: "get_active_signals", available: true,
  },
  {
    key: "opportunities", module_key: "management", module_label: "Management & kansen",
    title: "Grootste kansen", question: "Wat zijn nu onze grootste commerciële kansen?",
    description: "Rangschikt kansen uit de centrale Opportunity Engine.",
    required_function: "get_opportunities", available: true,
  },
];

export const FALLBACK_QUESTIONS = FALLBACK_STARTERS
  .filter((starter) => starter.module_key === "competition")
  .map((starter) => starter.question);