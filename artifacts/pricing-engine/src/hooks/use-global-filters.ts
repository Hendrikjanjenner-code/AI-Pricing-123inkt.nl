/**
 * useGlobalFilters — React-binding op de Global Filter Context.
 * Zie src/lib/global-filters.ts voor de storesemantiek.
 */
import { useEffect } from "react";
import { useSyncExternalStore } from "react";
import { useLocation } from "wouter";
import { getAuthHeaders } from "@/lib/auth";
import {
  getGlobalFilters,
  setGlobalFilters,
  subscribeGlobalFilters,
  syncFiltersToUrl,
  emptyFilters,
  type GlobalFilters,
  type HierarchyNodeSelection,
} from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

/**
 * Hydrateer + valideer een uit de URL gelezen cascade-keten (taak #301).
 * Deep-links dragen alleen node-ids (f_cat); namen/paden en de
 * parent/child-validatie komen server-side uit POST /product-filters/
 * resolve-scope. Een ongeldige keten wordt veilig gecorrigeerd: de
 * categorie- en productfilters worden gewist (nooit gemengde data).
 */
let hydratedSignature: string | null = null;

async function hydrateCategoryPath(): Promise<void> {
  const f = getGlobalFilters();
  const needsHydration =
    f.categoryPath.some((n) => n.path === null) ||
    (f.product !== null && f.product.label === f.product.skuId);
  if (!needsHydration) return;
  const signature =
    f.categoryPath.map((n) => n.id).join(",") + "|" + (f.product?.skuId ?? "");
  if (signature === hydratedSignature) return;
  hydratedSignature = signature;

  const keys = ["main_category_id", "subcategory_id",
    "sub_subcategory_id", "sub_sub_subcategory_id"] as const;
  const body: Record<string, unknown> = {};
  f.categoryPath.slice(0, 4).forEach((n, i) => { body[keys[i]] = n.id; });
  if (f.product) body.sku_id = f.product.skuId;
  try {
    const resp = await fetch(`${BASE}/api/product-filters/resolve-scope`, {
      method: "POST",
      headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (resp.ok) {
      const scope = await resp.json();
      const levels: HierarchyNodeSelection[] =
        (Array.isArray(scope.levels) ? scope.levels : []).map(
          (l: { id: number; name: string; path: string | null; path_names?: string | null }) =>
            ({ id: l.id, name: l.name, path: l.path, pathNames: l.path_names }));
      setGlobalFilters({
        categoryPath: levels,
        product: scope.product
          ? { skuId: scope.product.sku_id, label: scope.product.label }
          : null,
      });
    } else if (resp.status === 422) {
      // Ongeldige keten in de deep-link: veilig corrigeren door te wissen.
      setGlobalFilters({ categoryPath: [], product: null });
    }
  } catch {
    // Netwerkfout: placeholder-namen blijven staan; volgende mount probeert opnieuw.
    hydratedSignature = null;
  }
}

const SERVER_SNAPSHOT = emptyFilters();

export function useGlobalFilters(): GlobalFilters {
  return useSyncExternalStore(
    subscribeGlobalFilters,
    getGlobalFilters,
    () => SERVER_SNAPSHOT
  );
}

/**
 * Houdt de URL in sync na SPA-navigatie: wouter-links laten querystrings
 * vallen, dus na elke locatiewissel schrijven we de actieve context terug
 * zodat de deep-link deelbaar blijft.
 */
export function useFilterUrlSync(): void {
  const [location] = useLocation();
  useEffect(() => {
    syncFiltersToUrl();
    void hydrateCategoryPath();
  }, [location]);
}
