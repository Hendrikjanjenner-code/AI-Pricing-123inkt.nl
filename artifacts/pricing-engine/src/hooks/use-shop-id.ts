/**
 * useShopId — leest de actieve shop-scope uit de URL-querystring.
 *
 * Gebruik: ?shop_id=2 in de URL → alle API-calls geven die shop-id mee,
 * zodat dashboards per winkel gescheiden blijven.
 * Zonder querystring defaultt de backend naar de default-shop.
 */
import { useLocation } from "wouter";

export function useShopId(): number | undefined {
  const [location] = useLocation();
  // wouter geeft alleen het pad; zoekparams zitten in window.location.search
  const params = new URLSearchParams(
    typeof window !== "undefined" ? window.location.search : ""
  );
  const raw = params.get("shop_id");
  if (!raw) return undefined;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) ? n : undefined;
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
