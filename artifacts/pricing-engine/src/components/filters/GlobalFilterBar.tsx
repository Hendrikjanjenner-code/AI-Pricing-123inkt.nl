/**
 * GlobalFilterBar (taak #216) — vaste filterbalk boven dashboards.
 *
 * - Toont de Global Filter Context (hiërarchie, merk, periode, SKU-zoek).
 * - ACTIVE CONTEXT-blok met chips per actieve selectie + "alle filters wissen".
 * - Responsive: op kleine schermen zit alles in een drawer (Sheet).
 * - De context wordt centraal beheerd (src/lib/global-filters.ts) en blijft
 *   dus behouden bij navigatie tussen modules.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Filter, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger,
} from "@/components/ui/sheet";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getAuthHeaders } from "@/lib/auth";
import { InfoTooltip } from "@/components/InfoTooltip";
import { SavedViewsMenu } from "@/components/filters/SavedViewsMenu";
import {
  CascadingProductFilter, CATEGORY_LEVEL_LABELS,
} from "@/components/filters/CascadingProductFilter";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import {
  clearGlobalFilters,
  hasActiveFilters,
  setGlobalFilters,
  type GlobalFilters,
} from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

const PERIOD_OPTIONS = [
  { value: "7", label: "Laatste 7 dagen" },
  { value: "30", label: "Laatste 30 dagen" },
  { value: "90", label: "Laatste 90 dagen" },
  { value: "365", label: "Laatste jaar" },
];

function BrandFilter({ filters }: { filters: GlobalFilters }) {
  const [open, setOpen] = useState(false);
  const { data } = useQuery<{ merken: string[] }>({
    queryKey: ["filter-options-brands"],
    queryFn: async () => {
      const resp = await fetch(`${BASE}/api/category-hierarchy/filter-options`, {
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error("Filteropties laden mislukt");
      return resp.json();
    },
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });
  const merken = data?.merken ?? [];
  const [zoek, setZoek] = useState("");
  const gefilterd = useMemo(
    () => merken.filter((m) => m.toLowerCase().includes(zoek.toLowerCase())),
    [merken, zoek]
  );
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2" data-testid="brand-filter-trigger">
          Merk
          {filters.brands.length > 0 && (
            <Badge variant="secondary" className="px-1.5">{filters.brands.length}</Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2" align="start">
        <Input value={zoek} onChange={(e) => setZoek(e.target.value)}
          placeholder="Zoek merk…" className="h-8 mb-2" />
        <ScrollArea className="h-56">
          {gefilterd.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-6">Geen merken</div>
          ) : gefilterd.map((m) => (
            <label key={m} className="flex items-center gap-2 py-1.5 px-1 text-sm rounded hover:bg-accent/50 cursor-pointer">
              <Checkbox
                checked={filters.brands.includes(m)}
                onCheckedChange={(c) => setGlobalFilters({
                  brands: c ? [...filters.brands, m] : filters.brands.filter((b) => b !== m),
                })}
              />
              <span className="truncate">{m}</span>
            </label>
          ))}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

export const STATUS_OPTIONS = [
  { value: "active", label: "Actief" },
  { value: "new", label: "Nieuw" },
  { value: "end_of_life", label: "Einde levensduur" },
  { value: "discontinued", label: "Stopgezet" },
] as const;

export function statusLabel(value: string): string {
  return STATUS_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

function StatusFilter({ filters }: { filters: GlobalFilters }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2" data-testid="status-filter-trigger">
          Status
          {filters.statuses.length > 0 && (
            <Badge variant="secondary" className="px-1.5">{filters.statuses.length}</Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-2" align="start">
        {STATUS_OPTIONS.map((o) => (
          <label key={o.value}
            className="flex items-center gap-2 py-1.5 px-1 text-sm rounded hover:bg-accent/50 cursor-pointer">
            <Checkbox
              checked={filters.statuses.includes(o.value)}
              onCheckedChange={(c) => setGlobalFilters({
                statuses: c
                  ? [...filters.statuses, o.value]
                  : filters.statuses.filter((s) => s !== o.value),
              })}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </PopoverContent>
    </Popover>
  );
}

function FilterControls({ filters }: { filters: GlobalFilters }) {
  return (
    <>
      <CascadingProductFilter filters={filters} />
      <BrandFilter filters={filters} />
      <StatusFilter filters={filters} />
      <Select
        value={filters.periodDays !== null ? String(filters.periodDays) : "standaard"}
        onValueChange={(v) =>
          setGlobalFilters({ periodDays: v === "standaard" ? null : parseInt(v, 10) })}
      >
        <SelectTrigger className="h-9 w-[168px]" data-testid="period-filter">
          <SelectValue placeholder="Periode" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="standaard">Standaardperiode</SelectItem>
          {PERIOD_OPTIONS.map((o) => (
            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        value={filters.skuQuery}
        onChange={(e) => setGlobalFilters({ skuQuery: e.target.value })}
        placeholder="SKU / product…"
        className="h-9 w-40"
        data-testid="sku-filter-input"
      />
    </>
  );
}

/** Korte samenvatting van de actieve context, voor paginatitels e.d. */
export function activeContextSummary(filters: GlobalFilters): string | null {
  const parts: string[] = [];
  if (filters.hierarchy.length > 0) {
    parts.push(filters.hierarchy.map((h) => h.name).join(", "));
  }
  if (filters.categoryPath.length > 0) {
    parts.push(filters.categoryPath.map((n) => n.name).join(" > "));
  }
  if (filters.product !== null) parts.push(filters.product.label);
  if (filters.brands.length > 0) parts.push(filters.brands.join(", "));
  if (filters.statuses.length > 0) {
    parts.push(filters.statuses.map(statusLabel).join(", "));
  }
  if (filters.periodDays !== null) parts.push(`${filters.periodDays} dagen`);
  if (filters.skuQuery.trim()) parts.push(`"${filters.skuQuery.trim()}"`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

function ActiveContextBlock({ filters }: { filters: GlobalFilters }) {
  if (!hasActiveFilters(filters)) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t mt-2"
      data-testid="active-context-block">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mr-1">
        Active context
      </span>
      {filters.hierarchy.map((h) => (
        <Badge key={`h-${h.id}`} variant="secondary" className="gap-1" title={h.pathNames ?? h.name}>
          {h.name}
          <button type="button" aria-label={`Verwijder ${h.name}`}
            onClick={() => setGlobalFilters({
              hierarchy: filters.hierarchy.filter((x) => x.id !== h.id),
            })}>
            <X className="w-3 h-3" />
          </button>
        </Badge>
      ))}
      {filters.categoryPath.map((n, i) => (
        <Badge key={`c-${n.id}`} variant="secondary" className="gap-1"
          title={`${CATEGORY_LEVEL_LABELS[i]}: ${n.pathNames ?? n.name}`}>
          {n.name}
          <button type="button" aria-label={`Verwijder ${CATEGORY_LEVEL_LABELS[i]} ${n.name}`}
            onClick={() => setGlobalFilters({
              // Cascade-regel: dit niveau én alles eronder + product wissen.
              categoryPath: filters.categoryPath.slice(0, i),
              product: null,
            })}>
            <X className="w-3 h-3" />
          </button>
        </Badge>
      ))}
      {filters.product !== null && (
        <Badge variant="secondary" className="gap-1" title={filters.product.label}>
          {filters.product.label}
          <button type="button" aria-label="Verwijder product"
            onClick={() => setGlobalFilters({ product: null })}>
            <X className="w-3 h-3" />
          </button>
        </Badge>
      )}
      {filters.brands.map((b) => (
        <Badge key={`b-${b}`} variant="secondary" className="gap-1">
          {b}
          <button type="button" aria-label={`Verwijder merk ${b}`}
            onClick={() => setGlobalFilters({ brands: filters.brands.filter((x) => x !== b) })}>
            <X className="w-3 h-3" />
          </button>
        </Badge>
      ))}
      {filters.statuses.map((s) => (
        <Badge key={`s-${s}`} variant="secondary" className="gap-1">
          {statusLabel(s)}
          <button type="button" aria-label={`Verwijder status ${statusLabel(s)}`}
            onClick={() => setGlobalFilters({ statuses: filters.statuses.filter((x) => x !== s) })}>
            <X className="w-3 h-3" />
          </button>
        </Badge>
      ))}
      {filters.periodDays !== null && (
        <Badge variant="secondary" className="gap-1">
          Laatste {filters.periodDays} dagen
          <button type="button" aria-label="Verwijder periode"
            onClick={() => setGlobalFilters({ periodDays: null })}>
            <X className="w-3 h-3" />
          </button>
        </Badge>
      )}
      {filters.skuQuery.trim() !== "" && (
        <Badge variant="secondary" className="gap-1">
          SKU: {filters.skuQuery.trim()}
          <button type="button" aria-label="Verwijder SKU-zoekterm"
            onClick={() => setGlobalFilters({ skuQuery: "" })}>
            <X className="w-3 h-3" />
          </button>
        </Badge>
      )}
      <Button variant="ghost" size="sm" className="h-6 px-2 text-xs"
        onClick={() => clearGlobalFilters()} data-testid="clear-all-filters">
        Alle filters wissen
      </Button>
    </div>
  );
}

export function GlobalFilterBar() {
  const filters = useGlobalFilters();
  // URL-sync gebeurt centraal in SidebarLayout (op elke route gemount).
  const actief = hasActiveFilters(filters);

  return (
    <div className="rounded-lg border bg-card px-4 py-3 mb-6" data-testid="global-filter-bar">
      {/* Desktop */}
      <div className="hidden md:flex flex-wrap items-center gap-2">
        <Filter className="w-4 h-4 text-muted-foreground shrink-0" />
        <InfoTooltip definitieId="global_filter_context" />
        <FilterControls filters={filters} />
        <InfoTooltip definitieId="product_hierarchy" />
        <div className="ml-auto flex items-center gap-2">
          {actief && (
            <Button variant="ghost" size="sm" className="text-xs"
              onClick={() => clearGlobalFilters()}>
              Alle filters wissen
            </Button>
          )}
          <SavedViewsMenu />
        </div>
      </div>

      {/* Mobiel: drawer */}
      <div className="flex md:hidden items-center gap-2">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2" data-testid="filter-drawer-trigger">
              <Filter className="w-4 h-4" />
              Filters
              {actief && <Badge variant="secondary" className="px-1.5">actief</Badge>}
            </Button>
          </SheetTrigger>
          <SheetContent side="bottom" className="max-h-[80vh] overflow-y-auto">
            <SheetHeader>
              <SheetTitle>Filters</SheetTitle>
              <SheetDescription className="sr-only">
                Globale filtercontext voor alle dashboards
              </SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-3 pt-4 [&>*]:w-full">
              <FilterControls filters={filters} />
              {actief && (
                <Button variant="outline" size="sm" onClick={() => clearGlobalFilters()}>
                  Alle filters wissen
                </Button>
              )}
            </div>
          </SheetContent>
        </Sheet>
      </div>

      <ActiveContextBlock filters={filters} />
    </div>
  );
}
