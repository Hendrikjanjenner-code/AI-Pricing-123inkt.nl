import { useCallback, useRef } from "react";
import { useGetCostPriorityShops } from "@workspace/api-client-react";
import { useAuth } from "@/lib/auth";
import { useShopId } from "@/hooks/use-shop-id";

/** Pricing's own authorized list; the admin-only shop API is not appropriate here. */
export function useCostPriorityScope() {
  const explicitShopId = useShopId();
  const { user } = useAuth();
  const userKey = String(user?.id ?? user?.username ?? "anon");
  const shopsQuery = useGetCostPriorityShops({
    query: {
      queryKey: ["cost-priority-shops", userKey],
      enabled: !!user,
      staleTime: 30_000,
      retry: 1,
    },
  });
  const shops = (shopsQuery.data?.shops ?? []).filter(shop => shop.active);
  const shop = explicitShopId === undefined
    ? shops.find(s => s.is_default) ?? shops[0]
    : shops.find(s => s.id === explicitShopId);
  const shopId = shop?.id;
  const scopeToken = shopId === undefined ? null : `${userKey}:${shopId}`;
  const current = useRef(scopeToken);
  current.current = scopeToken;
  const isCurrent = useCallback((token: string | null) => token !== null && token === current.current, []);
  return { shops, shop, shopId, userKey, scopeToken, isCurrent, shopsQuery };
}
