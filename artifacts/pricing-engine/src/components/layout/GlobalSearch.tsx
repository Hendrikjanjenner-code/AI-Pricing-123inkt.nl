/**
 * GlobalSearch (taak #221) — platformbrede zoekbalk in de topbar.
 *
 * Zoekt via GET /api/search over SKU's, productcodes, EAN's, producten,
 * hiërarchie-nodes, categorieën, merken, leveranciers en concurrenten.
 * De backend filtert resultaten op de permissies van de gebruiker.
 * Navigatie per type: producten/merken/hiërarchie zetten de Global Filter
 * Context en gaan naar een relevant scherm; concurrenten gaan naar hun
 * detailpagina.
 */
import { useEffect, useMemo, useState } from "react";
import { useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { Search, Package, FolderTree, Tag, Layers, Truck, Crosshair } from "lucide-react";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { getAuthHeaders } from "@/lib/auth";
import { setGlobalFilters, emptyFilters } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface SearchHit {
  type: string;
  id: string | number;
  label: string;
  sublabel?: string | null;
  path?: string | null;
  level?: number;
}

interface SearchResponse {
  query: string;
  total: number;
  groups: Record<string, SearchHit[]>;
}

const GROUP_LABELS: Record<string, { label: string; icon: typeof Package }> = {
  products: { label: "Producten", icon: Package },
  hierarchy_nodes: { label: "Hiërarchie", icon: FolderTree },
  categories: { label: "Categorieën", icon: Layers },
  brands: { label: "Merken", icon: Tag },
  suppliers: { label: "Leveranciers", icon: Truck },
  competitors: { label: "Concurrenten", icon: Crosshair },
};

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const zoekterm = useDebounced(term, 250);
  const [, navigate] = useLocation();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const { data, isFetching } = useQuery<SearchResponse>({
    queryKey: ["global-search", zoekterm],
    queryFn: async () => {
      const res = await fetch(
        `${BASE}/api/search?q=${encodeURIComponent(zoekterm)}`,
        { headers: getAuthHeaders() },
      );
      if (!res.ok) throw new Error("Zoeken mislukt");
      return res.json();
    },
    enabled: open && zoekterm.trim().length >= 2,
    staleTime: 30_000,
  });

  const groups = useMemo(
    () => Object.entries(data?.groups ?? {}).filter(([, hits]) => hits.length > 0),
    [data],
  );

  const kies = (hit: SearchHit) => {
    setOpen(false);
    setTerm("");
    switch (hit.type) {
      case "product":
        navigate(`/producten/${encodeURIComponent(String(hit.id))}`);
        break;
      case "hierarchy_node":
        setGlobalFilters({
          ...emptyFilters(),
          hierarchy: [{
            id: Number(hit.id), name: hit.label,
            path: hit.path ?? null, pathNames: hit.sublabel ?? null,
          }],
        });
        navigate("/command-center");
        break;
      case "category":
        setGlobalFilters({ ...emptyFilters(), skuQuery: "" });
        navigate(`/competition/categories/${encodeURIComponent(String(hit.id))}`);
        break;
      case "brand":
        setGlobalFilters({ ...emptyFilters(), brands: [String(hit.id)] });
        navigate("/command-center");
        break;
      case "supplier":
        navigate("/kostprijswijziging");
        break;
      case "competitor":
        navigate(`/competition/competitors/${hit.id}`);
        break;
      default:
        break;
    }
  };

  return (
    <>
      <Button
        variant="outline"
        data-testid="button-global-search"
        onClick={() => setOpen(true)}
        className="h-9 gap-2 text-muted-foreground font-normal w-56 justify-start"
      >
        <Search className="w-4 h-4" />
        <span className="flex-1 text-left text-sm truncate">Zoeken…</span>
        <Kbd>⌘K</Kbd>
      </Button>
      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          placeholder="Zoek op SKU, EAN, product, categorie, merk, leverancier of concurrent…"
          value={term}
          onValueChange={setTerm}
          data-testid="input-global-search"
        />
        <CommandList>
          {zoekterm.trim().length < 2 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              Typ minimaal 2 tekens om te zoeken.
            </div>
          ) : (
            <>
              <CommandEmpty>
                {isFetching ? "Zoeken…" : "Geen resultaten gevonden."}
              </CommandEmpty>
              {groups.map(([key, hits]) => {
                const meta = GROUP_LABELS[key] ?? { label: key, icon: Search };
                const Icon = meta.icon;
                return (
                  <CommandGroup key={key} heading={meta.label}>
                    {hits.map((hit) => (
                      <CommandItem
                        key={`${hit.type}-${hit.id}`}
                        value={`${hit.type}-${hit.id}-${hit.label}`}
                        onSelect={() => kies(hit)}
                        data-testid={`search-hit-${hit.type}-${hit.id}`}
                      >
                        <Icon className="w-4 h-4 mr-2 shrink-0 text-muted-foreground" />
                        <div className="flex flex-col overflow-hidden">
                          <span className="truncate">{hit.label}</span>
                          {hit.sublabel && (
                            <span className="text-xs text-muted-foreground truncate">
                              {hit.sublabel}
                            </span>
                          )}
                        </div>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                );
              })}
            </>
          )}
        </CommandList>
      </CommandDialog>
    </>
  );
}
