/**
 * HierarchyFilter (taak #216) — herbruikbare cascading producthiërarchie-filter.
 *
 * - Lazy loading: roots via /tree?depth=1, kinderen via /nodes/{id}/children.
 * - Server-side zoeken via /search.
 * - Multi-select met subtree-semantiek: een geselecteerde parent telt
 *   server-side automatisch alle descendants mee; descendants tonen als
 *   "impliciet geselecteerd".
 * - Breadcrumb (path_names) bij zoekresultaten en actieve selectie.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown, ChevronRight, FolderTree, Loader2, Search, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getAuthHeaders } from "@/lib/auth";
import {
  isNodeSelected,
  toggleNode,
  type HierarchyNodeSelection,
} from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

export interface HierarchyApiNode {
  id: number;
  name: string;
  parent_id: number | null;
  level: number;
  path: string | null;
  path_names: string | null;
  sku_count?: number;
  has_children?: boolean;
  children?: HierarchyApiNode[];
}

async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { headers: getAuthHeaders() });
  if (!resp.ok) throw new Error(`Hiërarchie-API fout (${resp.status})`);
  return resp.json();
}

function toSelection(n: HierarchyApiNode): HierarchyNodeSelection {
  return { id: n.id, name: n.name, path: n.path, pathNames: n.path_names };
}

interface TreeNodeRowProps {
  node: HierarchyApiNode;
  depth: number;
  selection: HierarchyNodeSelection[];
  onToggleSelect: (node: HierarchyApiNode) => void;
}

function TreeNodeRow({ node, depth, selection, onToggleSelect }: TreeNodeRowProps) {
  const [expanded, setExpanded] = useState(false);
  const { data: children, isLoading } = useQuery<HierarchyApiNode[]>({
    queryKey: ["hierarchy-children", node.id],
    queryFn: () => apiGet(`/api/product-hierarchy/nodes/${node.id}/children`),
    enabled: expanded && (node.children === undefined || node.children.length === 0),
    staleTime: 5 * 60 * 1000,
  });
  const kids = node.children && node.children.length > 0 ? node.children : (children ?? []);
  const canExpand = node.has_children !== false;
  const { explicit, implied } = isNodeSelected(selection, toSelection(node));

  return (
    <div>
      <div
        className="flex items-center gap-1.5 py-1 pr-2 rounded hover:bg-accent/50 text-sm"
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
        data-testid={`hierarchy-node-${node.id}`}
      >
        <button
          type="button"
          className="w-5 h-5 flex items-center justify-center text-muted-foreground shrink-0 disabled:opacity-30"
          disabled={!canExpand}
          onClick={() => setExpanded((e) => !e)}
          aria-label={expanded ? "Inklappen" : "Uitklappen"}
        >
          {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : expanded ? <ChevronDown className="w-3.5 h-3.5" />
            : <ChevronRight className="w-3.5 h-3.5" />}
        </button>
        <Checkbox
          checked={explicit || implied}
          disabled={implied}
          onCheckedChange={() => onToggleSelect(node)}
          aria-label={`Selecteer ${node.name}`}
        />
        <button
          type="button"
          className="flex-1 text-left truncate cursor-pointer"
          onClick={() => onToggleSelect(node)}
          title={node.path_names ?? node.name}
        >
          {node.name}
        </button>
        {implied && (
          <span className="text-[10px] text-muted-foreground shrink-0">via parent</span>
        )}
        {typeof node.sku_count === "number" && (
          <Badge variant="secondary" className="text-[10px] px-1.5 shrink-0">
            {node.sku_count}
          </Badge>
        )}
      </div>
      {expanded && kids.map((c) => (
        <TreeNodeRow key={c.id} node={c} depth={depth + 1}
          selection={selection} onToggleSelect={onToggleSelect} />
      ))}
    </div>
  );
}

export interface HierarchyFilterProps {
  selection: HierarchyNodeSelection[];
  onChange: (selection: HierarchyNodeSelection[]) => void;
}

export function HierarchyFilter({ selection, onChange }: HierarchyFilterProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);

  const { data: rootsData, isLoading: rootsLoading } = useQuery<{ roots: HierarchyApiNode[] }>({
    queryKey: ["hierarchy-roots"],
    queryFn: () => apiGet(`/api/product-hierarchy/tree?depth=1`),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const { data: searchData, isFetching: searching } = useQuery<HierarchyApiNode[]>({
    queryKey: ["hierarchy-search", debounced],
    queryFn: () => apiGet(`/api/product-hierarchy/search?q=${encodeURIComponent(debounced)}&limit=50`),
    enabled: open && debounced.length > 0,
    staleTime: 60 * 1000,
  });

  // Hydrateer namen van deep-link-selecties (id zonder metadata).
  const unhydrated = useMemo(() => selection.filter((s) => s.path === null), [selection]);
  useEffect(() => {
    if (unhydrated.length === 0) return;
    let active = true;
    Promise.all(
      unhydrated.map((s) =>
        apiGet<HierarchyApiNode>(`/api/product-hierarchy/nodes/${s.id}`).catch(() => null)
      )
    ).then((nodes) => {
      if (!active) return;
      const byId = new Map(nodes.filter(Boolean).map((n) => [n!.id, n!]));
      if (byId.size === 0) return;
      onChange(selection.map((s) => (byId.has(s.id) ? toSelection(byId.get(s.id)!) : s)));
    });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unhydrated.map((s) => s.id).join(",")]);

  const handleToggle = useCallback((node: HierarchyApiNode) => {
    onChange(toggleNode(selection, toSelection(node)));
  }, [selection, onChange]);

  const roots = rootsData?.roots ?? [];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2" data-testid="hierarchy-filter-trigger">
          <FolderTree className="w-4 h-4" />
          Hiërarchie
          {selection.length > 0 && (
            <Badge variant="secondary" className="px-1.5">{selection.length}</Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-0" align="start">
        <div className="p-2 border-b">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Zoek in de hiërarchie…"
              className="pl-8 h-9"
              data-testid="hierarchy-filter-search"
            />
          </div>
        </div>

        {selection.length > 0 && (
          <div className="px-3 py-2 border-b flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
            {selection.map((s) => (
              <Badge key={s.id} variant="outline" className="gap-1 max-w-full" title={s.pathNames ?? s.name}>
                <span className="truncate">{s.pathNames ?? s.name}</span>
                <button type="button" onClick={() => onChange(selection.filter((x) => x.id !== s.id))}
                  aria-label={`Verwijder ${s.name}`}>
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            ))}
            <Button variant="ghost" size="sm" className="h-5 px-1.5 text-xs"
              onClick={() => onChange([])} data-testid="hierarchy-filter-reset">
              Reset
            </Button>
          </div>
        )}

        <ScrollArea className="h-72">
          <div className="p-1.5">
            {debounced.length > 0 ? (
              searching ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" /> Zoeken…
                </div>
              ) : (searchData ?? []).length === 0 ? (
                <div className="text-sm text-muted-foreground text-center py-8">
                  Geen resultaten voor "{debounced}"
                </div>
              ) : (
                (searchData ?? []).map((n) => {
                  const { explicit, implied } = isNodeSelected(selection, toSelection(n));
                  return (
                    <div key={n.id}
                      className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-accent/50 text-sm">
                      <Checkbox checked={explicit || implied} disabled={implied}
                        onCheckedChange={() => handleToggle(n)}
                        aria-label={`Selecteer ${n.name}`} />
                      <button type="button" className="flex-1 text-left min-w-0"
                        onClick={() => handleToggle(n)}>
                        <div className="truncate">{n.name}</div>
                        {n.path_names && (
                          <div className="text-xs text-muted-foreground truncate">{n.path_names}</div>
                        )}
                      </button>
                    </div>
                  );
                })
              )
            ) : rootsLoading ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin mr-2" /> Laden…
              </div>
            ) : roots.length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-8">
                Geen hiërarchie beschikbaar. Importeer eerst een producthiërarchie.
              </div>
            ) : (
              roots.map((n) => (
                <TreeNodeRow key={n.id} node={n} depth={0}
                  selection={selection} onToggleSelect={handleToggle} />
              ))
            )}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}
