/**
 * Regressietests voor de per-gebruiker favorieten/recents-store (taak #221):
 * een gebruikerswissel of logout terwijl de eerste load nog onderweg is mag
 * nooit de voorkeuren van de vorige gebruiker (terug) in de store zetten.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({ getAuthHeaders: () => ({}) }));

// Node-omgeving: globalThis is een EventTarget en CustomEvent bestaat
// (Node 19+), dus `window` kan naar globalThis wijzen. Vóór de module-import
// zetten, vandaar de dynamische import.
(globalThis as any).window = new EventTarget();
const {
  ensureUserPrefsLoaded, getUserPrefs, resetUserPrefs, toggleFavorite,
} = await import("./user-prefs");

type Deferred = { resolve: (v: unknown) => void };

function mockPrefFetch(): Map<string, Deferred[]> {
  const pending = new Map<string, Deferred[]>();
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const key = String(url).split("/").pop()!;
    return new Promise((resolve) => {
      const list = pending.get(key) ?? [];
      list.push({
        resolve: (value: unknown) =>
          resolve({ ok: true, json: async () => ({ value }) } as Response),
      });
      pending.set(key, list);
    });
  }));
  return pending;
}

function resolveLoad(pending: Map<string, Deferred[]>, favorites: unknown[], idx = 0) {
  pending.get("favorites")![idx].resolve({ items: favorites });
  pending.get("recents")![idx].resolve({ items: [] });
}

describe("user-prefs stale-response isolatie", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    resetUserPrefs();
  });

  it("laadt en reset per gebruiker", async () => {
    const pending = mockPrefFetch();
    const p = ensureUserPrefsLoaded(1);
    resolveLoad(pending, [{ path: "/a", label: "A" }]);
    await p;
    expect(getUserPrefs().favorites).toHaveLength(1);
    resetUserPrefs();
    expect(getUserPrefs().favorites).toHaveLength(0);
    expect(getUserPrefs().loaded).toBe(false);
  });

  it("negeert een load die pas ná logout binnenkomt", async () => {
    const pending = mockPrefFetch();
    const p = ensureUserPrefsLoaded(1);
    resetUserPrefs(); // logout vóór de respons
    resolveLoad(pending, [{ path: "/geheim", label: "Geheim" }]);
    await p;
    expect(getUserPrefs().favorites).toHaveLength(0);
    expect(getUserPrefs().loaded).toBe(false);
  });

  it("laat een trage load van gebruiker 1 de voorkeuren van gebruiker 2 niet overschrijven", async () => {
    const pending = mockPrefFetch();
    const p1 = ensureUserPrefsLoaded(1);           // request-index 0 (traag)
    const p2 = ensureUserPrefsLoaded(2);           // reset + request-index 1
    resolveLoad(pending, [{ path: "/user2", label: "User 2" }], 1);
    await p2;
    expect(getUserPrefs().favorites.map((f) => f.path)).toEqual(["/user2"]);
    // nu komt de oude respons van gebruiker 1 alsnog binnen
    resolveLoad(pending, [{ path: "/user1", label: "User 1" }], 0);
    await p1;
    expect(getUserPrefs().favorites.map((f) => f.path)).toEqual(["/user2"]);
    expect(getUserPrefs().loaded).toBe(true);
  });

  it("toggleFavorite muteert immutabel (nieuwe snapshot per wijziging)", async () => {
    const pending = mockPrefFetch();
    const p = ensureUserPrefsLoaded(1);
    resolveLoad(pending, []);
    await p;
    const before = getUserPrefs();
    toggleFavorite({ path: "/x", label: "X" });
    expect(getUserPrefs()).not.toBe(before);
    expect(getUserPrefs().favorites).toHaveLength(1);
  });
});
