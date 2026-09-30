import { useCallback, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useShopId } from "@/hooks/use-shop-id";
import { useAuth, getAuthHeaders } from "@/lib/auth";
import { BASE } from "@/lib/drs-daily-api";

export interface ShopRow { id: number; name: string; is_default: boolean; active: boolean }

/**
 * Effectieve winkel (expliciete keuze of default-sentinel) + gebruikersscope.
 * `isCurrent(token)` beschermt ELKE asynchrone respons tegen een wissel van
 * winkel of gebruiker tijdens de request.
 */
export function useDrsScope() {
  const explicitShopId = useShopId();
  const { user } = useAuth();
  const shopsQuery = useQuery<{ shops: ShopRow[] }>({
    queryKey: ["/api/shops"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/api/shops`, { headers: getAuthHeaders() as HeadersInit });
      if (!res.ok) throw new Error("Winkels laden mislukt");
      return res.json();
    },
    staleTime: 5 * 60 * 1000,
  });
  const activeShops = (shopsQuery.data?.shops ?? []).filter(s => s.active);
  const shop: ShopRow | undefined = explicitShopId !== undefined
    ? activeShops.find(s => s.id === explicitShopId) ?? (shopsQuery.isSuccess ? undefined : { id: explicitShopId, name: `Winkel #${explicitShopId}`, is_default: false, active: true })
    : activeShops.find(s => s.is_default) ?? activeShops[0];
  const shopId = shop?.id;
  const userKey = String(user?.id ?? user?.username ?? "anon");
  const scopeToken = shopId !== undefined ? `${userKey}:${shopId}` : null;

  const tokenRef = useRef(scopeToken);
  useEffect(() => { tokenRef.current = scopeToken; }, [scopeToken]);
  const isCurrent = useCallback((token: string | null) => token !== null && tokenRef.current === token, []);

  return { shop, shopId, userKey, scopeToken, isCurrent, shopsQuery };
}
