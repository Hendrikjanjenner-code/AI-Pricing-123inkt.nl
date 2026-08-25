/**
 * CascadingProductFilter (taak #301) — vijf afhankelijke filtervelden:
 * Hoofdcategorie → Subcategorie → Sub-Subcategorie → Sub-Sub-Subcategorie →
 * Product.
 *
 * Regels:
 * - Elk niveau toont uitsluitend children van het gekozen bovenliggende
 *   niveau (server-side geleverd; nooit client-side uit een volledige boom).
 * - Een wijziging op een niveau reset alle diepere niveaus + product.
 * - Een direct gekozen product vult de categorieniveaus automatisch in
 *   (via POST /product-filters/resolve-scope).
 * - Ondiepere paden: een niveau zonder children blijft disabled met de
 *   hint "Geen subcategorieën" — er hoeft geen fictief niveau gekozen te
 *   worden (voorkeur B uit de bouwopdracht).
 * - Productzoek is debounced en server-side gelimiteerd.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getAuthHeaders } from "@/lib/auth";
import {
  setGlobalFilters,
  setCategoryLevelPath,
  type GlobalFilters,
  type HierarchyNodeSelection,
} from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

export const CATEGORY_LEVEL_LABELS = [
  "Hoofdcategorie", "Subcategorie", "Sub-Subcategorie", "Sub-Sub-Subcategorie",
] as const;

interface FilterNode {
  id: number;
  name: string;
  level: number;
  path: string | null;
  path_names: string | null;
}

interface FilterProduct {
  sku_id: string;
  name: string;
  label: string;
}

async function fetchJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, { headers: getAuthHeaders() });
  if (!resp.ok) throw new Error("Filteropties laden mislukt");
  return resp.json();
}

const LEVEL_ENDPOINTS = [
  () => `${BASE}/api/product-filters/main-categories`,
  (parentId: number) =>
    `${BASE}/api/product-filters/subcategories?main_category_id=${parentId}`,
  (parentId: number) =>
    `${BASE}/api/product-filters/sub-subcategories?subcategory_id=${parentId}`,
  (parentId: number) =>
    `${BASE}/api/product-filters/sub-sub-subcategories?sub_subcategory_id=${parentId}`,
] as const;

function toSelection(n: FilterNode): HierarchyNodeSelection {
  return { id: n.id, name: n.name, path: n.path, pathNames: n.path_names };
}

function useDebounced(value: string, ms = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/** Eén doorzoekbaar categorieniveau. */
function CategoryLevelSelect({
  filters, levelIndex,
}: { filters: GlobalFilters; levelIndex: number }) {
  const [open, setOpen] = useState(false);
  const [zoek, setZoek] = useState("");
  const label = CATEGORY_LEVEL_LABELS[levelIndex];
  const parent = levelIndex === 0 ? null : filters.categoryPath[levelIndex - 1] ?? null;
  const selected = filters.categoryPath[levelIndex] ?? null;
  const enabled = levelIndex === 0 || parent !== null;

  const { data, isLoading } = useQuery<{ items: FilterNode[] }>({
    queryKey: ["product-filter-level", levelIndex, parent?.id ?? null],
    queryFn: () =>
      fetchJson(
        levelIndex === 0
          ? LEVEL_ENDPOINTS[0]()
          : LEVEL_ENDPOINTS[levelIndex]!(parent!.id)
      ),
    enabled: enabled && open,
    staleTime: 5 * 60 * 1000,
  });
  const items = data?.items ?? [];
  const gefilterd = useMemo(
    () => items.filter((n) => n.name.toLowerCase().includes(zoek.toLowerCase())),
    [items, zoek]
  );

  const kies = (node: FilterNode | null) => {
    setGlobalFilters({
      categoryPath: setCategoryLevelPath(
        filters.categoryPath, levelIndex, node ? toSelection(node) : null),
      product: null, // cascade-regel: wijziging reset ook de productkeuze
    });
    setOpen(false);
    setZoek("");
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline" size="sm" disabled={!enabled}
          className="gap-1 max-w-[190px] justify-between"
          title={!enabled ? `Kies eerst ${CATEGORY_LEVEL_LABELS[levelIndex - 1]}` : undefined}
          data-testid={`cascade-level-${levelIndex}`}
        >
          <span className="truncate">
            {selected ? selected.name : label}
          </span>
          <ChevronsUpDown className="w-3.5 h-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2" align="start">
        <Input value={zoek} onChange={(e) => setZoek(e.target.value)}
          placeholder={`Zoek ${label.toLowerCase()}…`} className="h-8 mb-2" />
        <ScrollArea className="h-56">
          {isLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-6">
              Geen {levelIndex === 0 ? "hoofdcategorieën" : "subcategorieën"}
            </div>
          ) : (
            <>
              {selected && (
                <button type="button"
                  className="w-full text-left text-sm py-1.5 px-1 rounded hover:bg-accent/50 text-muted-foreground"
                  onClick={() => kies(null)}>
                  — {label} wissen —
                </button>
              )}
              {gefilterd.map((n) => (
                <button key={n.id} type="button"
                  className="w-full flex items-center gap-2 text-left text-sm py-1.5 px-1 rounded hover:bg-accent/50"
                  onClick={() => kies(n)}
                  data-testid={`cascade-option-${n.id}`}>
                  <Check className={`w-3.5 h-3.5 shrink-0 ${selected?.id === n.id ? "" : "invisible"}`} />
                  <span className="truncate">{n.name}</span>
                </button>
              ))}
            </>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

/** Doorzoekbaar Product-veld binnen de gekozen categorieketen. */
function ProductSelect({ filters }: { filters: GlobalFilters }) {
  const [open, setOpen] = useState(false);
  const [zoek, setZoek] = useState("");
  const debounced = useDebounced(zoek);
  const pathIds = filters.categoryPath.map((n) => n.id);

  const { data, isLoading } = useQuery<{ items: FilterProduct[] }>({
    queryKey: ["product-filter-products", pathIds.join(","), debounced],
    queryFn: () => {
      const p = new URLSearchParams();
      const keys = ["main_category_id", "subcategory_id",
        "sub_subcategory_id", "sub_sub_subcategory_id"] as const;
      pathIds.forEach((id, i) => p.set(keys[i], String(id)));
      if (debounced.trim()) p.set("search", debounced.trim());
      return fetchJson(`${BASE}/api/product-filters/products?${p.toString()}`);
    },
    enabled: open,
    staleTime: 60 * 1000,
  });
  const items = data?.items ?? [];

  const kiesProduct = async (p: FilterProduct | null) => {
    setOpen(false);
    setZoek("");
    if (p === null) {
      setGlobalFilters({ product: null });
      return;
    }
    // Direct gekozen product: categorieniveaus automatisch laten invullen.
    try {
      const resp = await fetch(`${BASE}/api/product-filters/resolve-scope`, {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ sku_id: p.sku_id }),
      });
      if (resp.ok) {
        const scope = await resp.json();
        const levels: FilterNode[] = Array.isArray(scope.levels) ? scope.levels : [];
        setGlobalFilters({
          product: { skuId: p.sku_id, label: p.label },
          categoryPath: levels.map(toSelection),
        });
        return;
      }
    } catch {
      // resolve-scope niet bereikbaar — productselectie blijft gewoon werken
    }
    setGlobalFilters({ product: { skuId: p.sku_id, label: p.label } });
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm"
          className="gap-1 max-w-[220px] justify-between"
          data-testid="cascade-product-trigger">
          <span className="truncate">
            {filters.product ? filters.product.label : "Product"}
          </span>
          <ChevronsUpDown className="w-3.5 h-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-2" align="start">
        <Input value={zoek} onChange={(e) => setZoek(e.target.value)}
          placeholder="Zoek op naam, SKU, EAN of OEM…" className="h-8 mb-2"
          data-testid="cascade-product-search" />
        <ScrollArea className="h-64">
          {isLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-6">
              Geen producten gevonden
            </div>
          ) : (
            <>
              {filters.product && (
                <button type="button"
                  className="w-full text-left text-sm py-1.5 px-1 rounded hover:bg-accent/50 text-muted-foreground"
                  onClick={() => kiesProduct(null)}>
                  — Product wissen —
                </button>
              )}
              {items.map((p) => (
                <button key={p.sku_id} type="button"
                  className="w-full flex items-center gap-2 text-left text-sm py-1.5 px-1 rounded hover:bg-accent/50"
                  onClick={() => kiesProduct(p)}
                  data-testid={`cascade-product-${p.sku_id}`}>
                  <Check className={`w-3.5 h-3.5 shrink-0 ${filters.product?.skuId === p.sku_id ? "" : "invisible"}`} />
                  <span className="truncate">{p.label}</span>
                </button>
              ))}
            </>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

export function CascadingProductFilter({ filters }: { filters: GlobalFilters }) {
  return (
    <>
      {CATEGORY_LEVEL_LABELS.map((_, i) => (
        <CategoryLevelSelect key={i} filters={filters} levelIndex={i} />
      ))}
      <ProductSelect filters={filters} />
    </>
  );
}
