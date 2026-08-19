/**
 * Persoonlijke UI-voorkeuren (taak #221): favorieten en recent gebruikte
 * pagina's, per gebruiker bewaard via /api/me/preferences/{key}.
 *
 * Zelfde patroon als de Global Filter Context: module-singleton store met
 * subscribe/notify zodat sidebar en andere componenten live meebewegen.
 * De server is de bron van waarheid; lokale mutaties worden optimistisch
 * toegepast en daarna gepersisteerd.
 */
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const EVENT = "user-prefs-changed";

export interface FavoriteEntry {
  path: string;
  label: string;
}

export interface RecentEntry {
  path: string;
  label: string;
  /** ISO-tijdstip van laatste bezoek. */
  at: string;
}

interface PrefsState {
  favorites: FavoriteEntry[];
  recents: RecentEntry[];
  loaded: boolean;
}

// Immutabel snapshot: elke mutatie vervangt het object zodat
// useSyncExternalStore wijzigingen ziet (Object.is-vergelijking).
let state: PrefsState = { favorites: [], recents: [], loaded: false };
const MAX_RECENTS = 8;

function notify() {
  state = { ...state };
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function subscribeUserPrefs(cb: () => void): () => void {
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}

export function getUserPrefs(): PrefsState {
  return state;
}

async function fetchPref(key: string): Promise<any> {
  const res = await fetch(`${BASE}/api/me/preferences/${key}`, { headers: getAuthHeaders() });
  if (!res.ok) return null;
  const data = await res.json();
  return data?.value ?? null;
}

async function savePref(key: string, value: unknown): Promise<void> {
  try {
    await fetch(`${BASE}/api/me/preferences/${key}`, {
      method: "PUT",
      headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(value),
    });
  } catch {
    /* voorkeuren zijn best-effort; UI blijft werken zonder persistentie */
  }
}

let loadPromise: Promise<void> | null = null;
let loadedForUser: string | null = null;
// Generatieteller: elke reset/gebruikerswissel verhoogt hem, zodat een nog
// lopende fetch van een vorige gebruiker zijn (stale) resultaat niet meer op
// de store mag toepassen na logout of nadat de nieuwe gebruiker geladen is.
let generation = 0;

/**
 * Laadt favorieten + recents éénmalig per gebruiker (na login).
 * Een andere `userId` dan de vorige lading reset de store eerst, zodat een
 * gebruikerswissel in dezelfde browsersessie nooit andermans favorieten toont.
 */
export function ensureUserPrefsLoaded(userId: string | number): Promise<void> {
  const uid = String(userId);
  if (loadedForUser !== null && loadedForUser !== uid) {
    resetUserPrefs();
  }
  loadedForUser = uid;
  if (!loadPromise) {
    const gen = generation;
    loadPromise = (async () => {
      const [fav, rec] = await Promise.all([fetchPref("favorites"), fetchPref("recents")]);
      if (gen !== generation) return; // reset/gebruikerswissel intussen — negeren
      state.favorites = Array.isArray(fav?.items) ? fav.items : [];
      state.recents = Array.isArray(rec?.items) ? rec.items : [];
      state.loaded = true;
      notify();
    })().catch(() => {
      if (gen !== generation) return;
      state.loaded = true;
      notify();
    });
  }
  return loadPromise;
}

/** Reset (bij logout/gebruikerswissel). */
export function resetUserPrefs(): void {
  generation += 1; // maakt in-flight loads van de vorige gebruiker ongeldig
  state.favorites = [];
  state.recents = [];
  state.loaded = false;
  loadPromise = null;
  loadedForUser = null;
  notify();
}

export function isFavorite(path: string): boolean {
  return state.favorites.some((f) => f.path === path);
}

export function toggleFavorite(entry: FavoriteEntry): void {
  if (isFavorite(entry.path)) {
    state.favorites = state.favorites.filter((f) => f.path !== entry.path);
  } else {
    state.favorites = [...state.favorites, entry];
  }
  notify();
  void savePref("favorites", { items: state.favorites });
}

/** Registreer een paginabezoek in de recents-lijst (dedupe, max 8). */
export function recordRecentVisit(entry: Omit<RecentEntry, "at">): void {
  if (!state.loaded) return;
  const at = new Date().toISOString();
  const rest = state.recents.filter((r) => r.path !== entry.path);
  state.recents = [{ ...entry, at }, ...rest].slice(0, MAX_RECENTS);
  notify();
  void savePref("recents", { items: state.recents });
}
