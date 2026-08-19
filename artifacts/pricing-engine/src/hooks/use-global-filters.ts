/**
 * useGlobalFilters — React-binding op de Global Filter Context.
 * Zie src/lib/global-filters.ts voor de storesemantiek.
 */
import { useEffect } from "react";
import { useSyncExternalStore } from "react";
import { useLocation } from "wouter";
import {
  getGlobalFilters,
  subscribeGlobalFilters,
  syncFiltersToUrl,
  emptyFilters,
  type GlobalFilters,
} from "@/lib/global-filters";

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
  }, [location]);
}
