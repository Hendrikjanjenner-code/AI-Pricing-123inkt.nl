/**
 * Global Filter Context (taak #216) — centrale filterstate voor alle modules.
 *
 * Ontwerp (zelfde patroon als use-shop-id):
 * - De store is de bron van waarheid en overleeft navigatie tussen modules
 *   (module-singleton + sessionStorage).
 * - De URL draagt de filters als deelbare deep-link (`f_hn`, `f_brand`,
 *   `f_days`, `f_sku`). Bij het laden wint de URL; zonder URL-params wordt de
 *   opgeslagen context hersteld en terug de URL in geschreven.
 * - Autorisatie blijft server-side afgedwongen: de URL stuurt alleen
 *   filterwensen mee, de API bepaalt wat de gebruiker mag zien.
 * - Parent-selectie in de hiërarchie telt server-side automatisch alle
 *   descendants mee; client-side worden geselecteerde descendants van een
 *   geselecteerde parent weggesnoeid (pruneDescendants).
 */

export interface HierarchyNodeSelection {
  id: number;
  name: string;
  /** Gematerialiseerd intern pad ("/1/7/23/"); basis voor descendant-logica. */
  path: string | null;
  /** Leesbaar pad ("Tuin > Gereedschap") voor breadcrumb/chips. */
  pathNames?: string | null;
}

export interface GlobalFilters {
  hierarchy: HierarchyNodeSelection[];
  brands: string[];
  /** Periode in dagen (null = standaardperiode van het scherm). */
  periodDays: number | null;
  skuQuery: string;
}

export const FILTER_PARAM_KEYS = ["f_hn", "f_brand", "f_days", "f_sku"] as const;
const STORAGE_KEY = "global_filter_context_v1";
const EVENT = "global-filters-changed";

export function emptyFilters(): GlobalFilters {
  return { hierarchy: [], brands: [], periodDays: null, skuQuery: "" };
}

export function hasActiveFilters(f: GlobalFilters): boolean {
  return f.hierarchy.length > 0 || f.brands.length > 0 ||
    f.periodDays !== null || f.skuQuery.trim() !== "";
}

/** Is `node` een descendant van `maybeAncestor` (o.b.v. gematerialiseerd pad)? */
export function isDescendantOf(
  node: HierarchyNodeSelection, maybeAncestor: HierarchyNodeSelection
): boolean {
  if (!node.path || !maybeAncestor.path) return false;
  return node.path !== maybeAncestor.path && node.path.startsWith(maybeAncestor.path);
}

/**
 * Snoei descendants weg van reeds geselecteerde parents: de server telt
 * descendants automatisch mee, dus alleen de hoogste geselecteerde nodes
 * blijven over.
 */
export function pruneDescendants(
  selection: HierarchyNodeSelection[]
): HierarchyNodeSelection[] {
  return selection.filter(
    (n) => !selection.some((other) => isDescendantOf(n, other))
  );
}

/** Is de node (impliciet of expliciet) geselecteerd? */
export function isNodeSelected(
  selection: HierarchyNodeSelection[], node: HierarchyNodeSelection
): { explicit: boolean; implied: boolean } {
  const explicit = selection.some((s) => s.id === node.id);
  const implied = !explicit && selection.some((s) => isDescendantOf(node, s));
  return { explicit, implied };
}

/** Toggle een hiërarchie-node in de selectie (met descendant-snoei). */
export function toggleNode(
  selection: HierarchyNodeSelection[], node: HierarchyNodeSelection
): HierarchyNodeSelection[] {
  if (selection.some((s) => s.id === node.id)) {
    return selection.filter((s) => s.id !== node.id);
  }
  return pruneDescendants([...selection, node]);
}

// ── (De)serialisatie van/naar URL-parameters ────────────────────────────────

export function writeFiltersToParams(f: GlobalFilters, params: URLSearchParams): void {
  FILTER_PARAM_KEYS.forEach((k) => params.delete(k));
  if (f.hierarchy.length > 0) {
    params.set("f_hn", f.hierarchy.map((n) => n.id).join(","));
  }
  if (f.brands.length > 0) {
    params.set(
      "f_brand",
      f.brands
        .map((b) => encodeURIComponent(b).replace(/~/g, "%7E"))
        .join("~")
    );
  }
  if (f.periodDays !== null) params.set("f_days", String(f.periodDays));
  if (f.skuQuery.trim() !== "") params.set("f_sku", f.skuQuery.trim());
}

export function paramsHaveFilters(params: URLSearchParams): boolean {
  return FILTER_PARAM_KEYS.some((k) => params.has(k));
}

/**
 * Lees filters uit URL-params. `known` levert reeds bekende node-metadata
 * (naam/pad) zodat chips direct kloppen; onbekende nodes krijgen een
 * placeholder-naam en worden later via de API gehydrateerd.
 */
export function readFiltersFromParams(
  params: URLSearchParams,
  known: HierarchyNodeSelection[] = []
): GlobalFilters {
  const byId = new Map(known.map((n) => [n.id, n]));
  const hierarchy: HierarchyNodeSelection[] = (params.get("f_hn") || "")
    .split(",")
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => Number.isFinite(n))
    .map((id) => byId.get(id) ?? { id, name: `#${id}`, path: null });
  const brands = (params.get("f_brand") || "")
    .split("~")
    .map((s) => decodeURIComponent(s))
    .filter((s) => s !== "");
  const rawDays = params.get("f_days");
  const periodDays = rawDays && /^\d+$/.test(rawDays) ? parseInt(rawDays, 10) : null;
  const skuQuery = params.get("f_sku") || "";
  return { hierarchy, brands, periodDays, skuQuery };
}

/** Querystring-fragment voor API-aanroepen (server-side descendant-expansie). */
export function apiFilterParams(f: GlobalFilters): string {
  const p = new URLSearchParams();
  if (f.hierarchy.length > 0) {
    p.set("hierarchy_node_ids", f.hierarchy.map((n) => n.id).join(","));
  }
  if (f.brands.length > 0) p.set("brands", f.brands.join(","));
  return p.toString();
}

// ── Store (module-singleton + sessionStorage + URL-sync) ────────────────────

function loadStored(): GlobalFilters | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return {
      hierarchy: Array.isArray(parsed.hierarchy) ? parsed.hierarchy : [],
      brands: Array.isArray(parsed.brands) ? parsed.brands : [],
      periodDays: typeof parsed.periodDays === "number" ? parsed.periodDays : null,
      skuQuery: typeof parsed.skuQuery === "string" ? parsed.skuQuery : "",
    };
  } catch {
    return null;
  }
}

function initialState(): GlobalFilters {
  if (typeof window === "undefined") return emptyFilters();
  const params = new URLSearchParams(window.location.search);
  const stored = loadStored();
  if (paramsHaveFilters(params)) {
    // Deep-link wint; bekende metadata uit de opgeslagen context hergebruiken.
    return readFiltersFromParams(params, stored?.hierarchy ?? []);
  }
  return stored ?? emptyFilters();
}

let state: GlobalFilters = initialState();

function persist(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // sessionStorage niet beschikbaar — URL-sync blijft werken
  }
}

/** Schrijf de actieve filters (terug) naar de URL zonder navigatie. */
export function syncFiltersToUrl(): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  writeFiltersToParams(state, url.searchParams);
  window.history.replaceState(window.history.state, "", url.toString());
}

export function getGlobalFilters(): GlobalFilters {
  return state;
}

export function setGlobalFilters(patch: Partial<GlobalFilters>): void {
  state = { ...state, ...patch };
  if (patch.hierarchy) state.hierarchy = pruneDescendants(patch.hierarchy);
  persist();
  syncFiltersToUrl();
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EVENT));
}

export function clearGlobalFilters(): void {
  state = emptyFilters();
  persist();
  syncFiltersToUrl();
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EVENT));
}

export function subscribeGlobalFilters(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onPop = () => {
    // Terug/vooruit-navigatie: URL is leidend als die filters bevat.
    const params = new URLSearchParams(window.location.search);
    if (paramsHaveFilters(params)) {
      state = readFiltersFromParams(params, state.hierarchy);
      persist();
    }
    onChange();
  };
  window.addEventListener(EVENT, onChange);
  window.addEventListener("popstate", onPop);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("popstate", onPop);
  };
}

/** Alleen voor tests: reset de module-state deterministisch. */
export function __resetGlobalFiltersForTests(next?: GlobalFilters): void {
  state = next ?? emptyFilters();
}
