/**
 * Globale shop-scope voor alle API-verkeer.
 *
 * Patcht `window.fetch` één keer bij app-start zodat elke same-origin
 * `/api/...`-request automatisch de actieve `shop_id` meekrijgt (uit de
 * URL-param of de winkelwissel in de navigatie). Zo blijft élk scherm —
 * ook pagina's die zelf geen useShopId gebruiken en de gegenereerde
 * API-client — consistent binnen de gekozen winkel, en volstaat één
 * queryClient.invalidateQueries() na het wisselen.
 *
 * Regels:
 * - alleen paden die met /api/ beginnen (same-origin);
 * - nooit overschrijven als de caller zelf al een shop_id meegeeft;
 * - auth-endpoints blijven ongemoeid (niet shop-gebonden).
 */
import { getActiveShopId } from "@/hooks/use-shop-id";

const EXCLUDED_PREFIXES = ["/api/auth/"];

/** Pure helper (los testbaar): voeg shop_id toe aan een API-URL. */
export function scopeApiUrl(url: string, shopId: number | undefined): string {
  if (shopId === undefined) return url;
  let path: string;
  try {
    path = new URL(url, "http://local").pathname;
  } catch {
    return url;
  }
  if (!path.startsWith("/api/") && path !== "/api") return url;
  if (EXCLUDED_PREFIXES.some((p) => path.startsWith(p))) return url;
  const [base, query = ""] = url.split("?");
  const params = new URLSearchParams(query);
  if (params.has("shop_id")) return url;
  params.set("shop_id", String(shopId));
  return `${base}?${params.toString()}`;
}

let installed = false;

export function installShopScopedFetch(): void {
  if (installed || typeof window === "undefined" || typeof window.fetch !== "function") {
    return;
  }
  installed = true;

  const originalFetch = window.fetch.bind(window);

  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const shopId = getActiveShopId();
    if (shopId === undefined) return originalFetch(input, init);

    if (typeof input === "string" || input instanceof URL) {
      // Alleen relatieve/same-origin URL's scopen; absolute externe URL's ongemoeid.
      const asString = input.toString();
      const isSameOrigin =
        asString.startsWith("/") || asString.startsWith(window.location.origin);
      if (isSameOrigin) {
        return originalFetch(scopeApiUrl(asString, shopId), init);
      }
      return originalFetch(input, init);
    }
    // Request-object: URL herbouwen met scope, overige opties behouden.
    if (input instanceof Request) {
      const scoped = scopeApiUrl(input.url, shopId);
      if (scoped !== input.url) {
        return originalFetch(new Request(scoped, input), init);
      }
    }
    return originalFetch(input, init);
  };
}
