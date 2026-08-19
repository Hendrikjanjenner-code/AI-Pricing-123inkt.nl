/**
 * useShopId — leest de actieve shop-scope.
 *
 * Bron-volgorde:
 * 1. ?shop_id=X in de URL (deelbare links winnen altijd)
 * 2. localStorage (keuze via de winkelwissel in de navigatie)
 * Zonder beide defaultt de backend naar de default-shop.
 *
 * Wisselen gebeurt via setActiveShopId(); die schrijft localStorage,
 * werkt de URL-querystring bij en notificeert alle actieve hooks.
 */
import { useSyncExternalStore } from "react";

const STORAGE_KEY = "active_shop_id";
const EVENT = "shop-id-changed";

function parseShopId(raw: string | null): number | undefined {
  if (!raw) return undefined;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) ? n : undefined;
}

/** Huidige shop-id: URL-param eerst, daarna localStorage. */
export function getActiveShopId(): number | undefined {
  if (typeof window === "undefined") return undefined;
  const fromUrl = parseShopId(
    new URLSearchParams(window.location.search).get("shop_id")
  );
  if (fromUrl !== undefined) return fromUrl;
  try {
    return parseShopId(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return undefined;
  }
}

/**
 * Zet de actieve shop. Schrijft localStorage, synchroniseert de
 * URL-querystring (zodat URL-lezende code meekomt) en notificeert hooks.
 */
export function setActiveShopId(shopId: number | undefined): void {
  if (typeof window === "undefined") return;
  try {
    if (shopId === undefined) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, String(shopId));
  } catch {
    // localStorage niet beschikbaar — URL-param blijft werken
  }
  const url = new URL(window.location.href);
  if (shopId === undefined) url.searchParams.delete("shop_id");
  else url.searchParams.set("shop_id", String(shopId));
  window.history.replaceState(null, "", url.toString());
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("popstate", onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("popstate", onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useShopId(): number | undefined {
  return useSyncExternalStore(subscribe, getActiveShopId, () => undefined);
}

/** Bouw een URL-querystring op met de shop_id als die beschikbaar is. */
export function shopParam(shopId: number | undefined): string {
  return shopId !== undefined ? `shop_id=${shopId}` : "";
}

/** Voeg shop_id toe aan bestaande querystring (bijv. "days=30"). */
export function withShop(qs: string, shopId: number | undefined): string {
  if (shopId === undefined) return qs;
  return qs ? `${qs}&shop_id=${shopId}` : `shop_id=${shopId}`;
}
