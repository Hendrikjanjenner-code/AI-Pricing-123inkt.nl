/**
 * Pricing Hub — kostprioriteit (stap 1). Pure helpers rond het contract
 * `/api/cost-priority/{shop_id}` (zie gegenereerde Orval-types).
 * Bron-ID's zijn exacte labels; wijzig de schrijfwijze nooit.
 */
import type {
  CostPriorityRules, CostPriorityScenario, CostPrioritySelection, CostPriorityPreview,
} from "@workspace/api-client-react";

export const STOCKPRICE = "Stockprice";
export const ABCLEV = "ABCLev";
export const AB = "AB";
export const MARKET = "123inkt.nl Marktprijs";
export const BASE_SOURCES = [STOCKPRICE, ABCLEV, AB, MARKET] as const;

export const SOURCE_INFO: Record<string, { title: string; uitleg: string }> = {
  [STOCKPRICE]: { title: "Stockprice", uitleg: "Voorraadwaarde-inkoopprijs (Excel-kolom Stockprice)." },
  [ABCLEV]: { title: "ABCLev", uitleg: "Inkoopprijs volgens de ABC-leverancier (Excel-kolom ABCLev)." },
  [AB]: { title: "AB", uitleg: "Inkoopprijs van de standaardleverancier (Excel-kolom AB)." },
  [MARKET]: { title: "123inkt.nl Marktprijs", uitleg: "Marktprijs als terugval. Dit is geen geverifieerde historische kostprijs." },
};

export const DEFAULT_PRINT = [STOCKPRICE, ABCLEV, AB, MARKET];
export const DEFAULT_OTHER = [STOCKPRICE, AB, ABCLEV, MARKET];

export function excelDefaultRules(): CostPriorityRules {
  return { print: [...DEFAULT_PRINT], other: [...DEFAULT_OTHER], custom_source: null, categories: {} };
}

export function sourcesOf(rules: CostPriorityRules): string[] {
  return [...BASE_SOURCES, ...(rules.custom_source ? [rules.custom_source] : [])];
}

/** Doel van een volgorde: Print, Overige of een exacte categorie-override. */
export type Target = { kind: "print" } | { kind: "other" } | { kind: "category"; name: string };
export const targetKey = (t: Target) => (t.kind === "category" ? `cat:${t.name}` : t.kind);
export function parseTargetKey(k: string): Target {
  return k.startsWith("cat:") ? { kind: "category", name: k.slice(4) } : k === "print" ? { kind: "print" } : { kind: "other" };
}

export function orderOf(rules: CostPriorityRules, t: Target): string[] {
  if (t.kind === "print") return rules.print;
  if (t.kind === "other") return rules.other;
  return rules.categories[t.name] ?? [];
}

/** Zelfde regel als backend `order_for`: override exact, daarna Print case-insensitive, anders Overige. */
export function orderForCategory(rules: CostPriorityRules, category: string): string[] {
  if (Object.prototype.hasOwnProperty.call(rules.categories, category)) return rules.categories[category];
  return category.toLowerCase() === "print" ? rules.print : rules.other;
}

export function withOrder(rules: CostPriorityRules, t: Target, order: string[]): CostPriorityRules {
  if (t.kind === "print") return { ...rules, print: order };
  if (t.kind === "other") return { ...rules, other: order };
  return { ...rules, categories: { ...rules.categories, [t.name]: order } };
}

export function moveItem<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const next = list.slice();
  const [it] = next.splice(from, 1);
  next.splice(to, 0, it);
  return next;
}

export function validateCustomName(name: string, rules: CostPriorityRules): string | null {
  if (!name) return "Naam is verplicht.";
  if (name.trim() !== name) return "Geen spaties aan begin of eind.";
  if (name.length > 80) return "Maximaal 80 tekens.";
  if ((BASE_SOURCES as readonly string[]).includes(name)) return "Deze naam is al een standaardbron.";
  if (rules.custom_source && rules.custom_source !== name) return null;
  return null;
}

/** Vijfde bron toevoegen/hernoemen: achteraan in elke volgorde (of op dezelfde plek bij hernoemen). */
export function setCustomSource(rules: CostPriorityRules, name: string): CostPriorityRules {
  const old = rules.custom_source;
  const fix = (o: string[]) => (old ? o.map(s => (s === old ? name : s)) : [...o, name]);
  return {
    print: fix(rules.print), other: fix(rules.other), custom_source: name,
    categories: Object.fromEntries(Object.entries(rules.categories).map(([k, v]) => [k, fix(v)])),
  };
}

export function removeCustomSource(rules: CostPriorityRules): CostPriorityRules {
  const old = rules.custom_source;
  if (!old) return rules;
  const fix = (o: string[]) => o.filter(s => s !== old);
  return {
    print: fix(rules.print), other: fix(rules.other), custom_source: null,
    categories: Object.fromEntries(Object.entries(rules.categories).map(([k, v]) => [k, fix(v)])),
  };
}

export function addCategoryOverride(rules: CostPriorityRules, name: string): CostPriorityRules {
  if (Object.prototype.hasOwnProperty.call(rules.categories, name)) return rules;
  return { ...rules, categories: { ...rules.categories, [name]: [...orderForCategory(rules, name)] } };
}
export function removeCategoryOverride(rules: CostPriorityRules, name: string): CostPriorityRules {
  const { [name]: _drop, ...rest } = rules.categories;
  void _drop;
  return { ...rules, categories: rest };
}

/** Reset naar Excel-default, met behoud van een geconfigureerde vijfde bron (achteraan). */
export function resetToExcelDefault(rules: CostPriorityRules): CostPriorityRules {
  const base = excelDefaultRules();
  return rules.custom_source ? setCustomSource(base, rules.custom_source) : base;
}

export function rulesEqual(a: CostPriorityRules, b: CostPriorityRules): boolean {
  return canonical(a) === canonical(b);
}
export function canonical(r: CostPriorityRules): string {
  const cats = Object.keys(r.categories).sort().map(k => [k, r.categories[k]]);
  return JSON.stringify([r.print, r.other, r.custom_source ?? null, cats]);
}

/** Fingerprint van alles waar een preview op rust; elke wijziging maakt het token ongeldig. */
export function previewFingerprint(p: { userKey: string; shopId: number | undefined; revision: number | undefined; rules: CostPriorityRules; inputSig: string }) {
  return JSON.stringify([p.userKey, p.shopId ?? null, p.revision ?? null, canonical(p.rules), p.inputSig]);
}

// ---------------------------------------------------------------------------
// Handmatige scenario's
// ---------------------------------------------------------------------------
export interface ManualRow { id: string; category: string; values: Record<string, string> }

export function emptyManualRow(n: number, category = "Print"): ManualRow {
  return { id: `scenario-${n}`, category, values: {} };
}

/** Bouwt contract-rijen. Lege velden → null (ontbrekend, blokkeert activatie; 0 moet expliciet). */
export function toScenarioRows(rows: ManualRow[], sources: string[]): CostPriorityScenario[] {
  return rows.map(r => ({
    row_id: r.id.trim(),
    category: r.category,
    values: Object.fromEntries(sources.map(s => {
      const raw = (r.values[s] ?? "").trim();
      return [s, raw === "" ? null : raw.replace(",", ".")];
    })),
  }));
}

export function manualRowsError(rows: ManualRow[]): string | null {
  if (rows.length === 0) return "Voeg minimaal één scenario toe.";
  if (rows.length > 500) return "Maximaal 500 scenario's.";
  const ids = rows.map(r => r.id.trim());
  if (ids.some(i => !i)) return "Elk scenario heeft een regel-ID nodig.";
  if (new Set(ids).size !== ids.length) return "Regel-ID's moeten uniek zijn.";
  return null;
}

// ---------------------------------------------------------------------------
// Response-adaptatie
// ---------------------------------------------------------------------------
export const TRACE_STATUS: Record<string, string> = {
  zero_skipped: "0 — overgeslagen",
  first_nonzero: "gekozen (eerste niet-nul)",
  final_fallback: "gekozen (laatste prioriteit)",
  missing_or_invalid: "ontbreekt of ongeldig",
};
export const REASON_LABEL: Record<string, string> = {
  first_nonzero: "Eerste bron met waarde groter dan 0",
  final_fallback: "Laatste prioriteit (ook bij 0 gekozen)",
  input_error: "Invoerfout — geen keuze mogelijk",
  current_input_incomplete: "Huidige keuze niet te vergelijken: brongegevens ontbreken",
};
export const traceStatusLabel = (s: string) => TRACE_STATUS[s] ?? s;
export const reasonLabel = (s: string) => REASON_LABEL[s] ?? s;

export function formatEur(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(n);
}

export function selectionChanged(a: CostPrioritySelection, b: CostPrioritySelection) {
  if (a.value === null || b.value === null) return false;
  return a.source !== b.source || a.value !== b.value;
}

export interface PreviewSummary { total: number; changed: number; rowErrors: number; fallbacks: number; inputErrors: number }
export function summarizePreview(p: CostPriorityPreview): PreviewSummary {
  return {
    total: p.rows.length,
    changed: p.rows.filter(r => selectionChanged(r.current, r.proposed)).length,
    rowErrors: p.rows.filter(r => r.errors.length > 0).length,
    fallbacks: p.rows.filter(r => r.proposed.fallback_warning).length,
    inputErrors: p.rows.filter(r => r.proposed.reason === "input_error").length,
  };
}

export const isMarket = (s: string | null | undefined) => s === MARKET;

/** Voor weergave: welke categorieën uit de preview vallen onder welk doel. */
export function describeTarget(t: Target): string {
  if (t.kind === "print") return "Print (hoofdletterongevoelig)";
  if (t.kind === "other") return "Overige categorieën";
  return `Categorie "${t.name}" (exacte naam)`;
}

/** Zet een API-fout om in een Nederlandstalige melding + type. */
export function describeApiError(e: unknown): { kind: "conflict" | "validation" | "forbidden" | "timeout" | "other"; message: string } {
  const err = e as { status?: number; data?: { detail?: unknown }; message?: string; name?: string };
  const detail = err?.data?.detail;
  const text = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join("; ") : err?.message || "Onbekende fout";
  if (err?.name === "TimeoutError") return { kind: "timeout", message: "De upload duurde langer dan 180 seconden en is afgebroken." };
  if (err?.status === 409) return { kind: "conflict", message: text };
  if (err?.status === 422 || err?.status === 413) return { kind: "validation", message: text };
  if (err?.status === 403) return { kind: "forbidden", message: "Je hebt hiervoor geen rechten in deze winkel." };
  return { kind: "other", message: text };
}
