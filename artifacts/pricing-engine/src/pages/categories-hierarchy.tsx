import { useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ChevronDown,
  ChevronRight,
  Folder,
  FolderOpen,
  Layers,
  Package,
  RefreshCw,
  Loader2,
  Search,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

type HierarchyNode = {
  id: number;
  name: string;
  parent_id: number | null;
  level: number;
  path: string | null;
  module: string | null;
  sku_count: number;
  children: HierarchyNode[];
};

type Product = {
  sku_id: string;
  product_name: string;
  brand: string | null;
  category: string | null;
  subcategory: string | null;
  current_price: number | null;
  cost_price: number | null;
};

type SelectedNode = {
  node: HierarchyNode;
  category: string;
  subcategory: string | null;
};

const fmtBedrag = (v: number | null | undefined) =>
  v != null ? new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(v) : "—";

const LEVEL_LABELS: Record<number, string> = {
  1: "Categorie",
  2: "Subcategorie",
  3: "Sub-subcategorie",
};

function countNodes(nodes: HierarchyNode[]): number {
  return nodes.reduce((acc, n) => acc + 1 + countNodes(n.children || []), 0);
}

function TreeNode({
  node,
  parentCategory,
  expanded,
  toggle,
  selectedId,
  onSelect,
  depth,
}: {
  node: HierarchyNode;
  parentCategory: string | null;
  expanded: Set<number>;
  toggle: (id: number) => void;
  selectedId: number | null;
  onSelect: (sel: SelectedNode) => void;
  depth: number;
}) {
  const hasChildren = (node.children?.length ?? 0) > 0;
  const isOpen = expanded.has(node.id);
  const isSelected = selectedId === node.id;

  // Niveau 1 = categorie zelf; niveau 2 = subcategorie binnen parent-categorie.
  const category = node.level === 1 ? node.name : parentCategory ?? node.name;
  const subcategory = node.level === 2 ? node.name : null;
  const selectable = node.level <= 2 && node.sku_count > 0;

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm transition-colors ${
          isSelected ? "bg-primary/10 text-primary" : "hover:bg-muted/60"
        }`}
        style={{ paddingLeft: `${depth * 18 + 8}px` }}
      >
        <button
          type="button"
          onClick={() => hasChildren && toggle(node.id)}
          className={`shrink-0 ${hasChildren ? "text-muted-foreground hover:text-foreground" : "opacity-0 pointer-events-none"}`}
          aria-label={isOpen ? "Inklappen" : "Uitklappen"}
        >
          {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>

        {node.level === 1 ? (
          isOpen ? <FolderOpen className="h-4 w-4 shrink-0 text-amber-500" /> : <Folder className="h-4 w-4 shrink-0 text-amber-500" />
        ) : node.level === 2 ? (
          <Layers className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <Package className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
        )}

        <button
          type="button"
          disabled={!selectable}
          onClick={() => selectable && onSelect({ node, category, subcategory })}
          className={`flex-1 min-w-0 text-left truncate ${selectable ? "cursor-pointer" : "cursor-default"} ${isSelected ? "font-semibold" : ""}`}
          title={node.path || node.name}
        >
          {node.name}
        </button>

        <Badge variant="outline" className="text-[10px] py-0 font-normal shrink-0">
          {LEVEL_LABELS[node.level] ?? `Niv. ${node.level}`}
        </Badge>

        {node.module && (
          <Badge variant="secondary" className="text-[10px] py-0 font-normal shrink-0 max-w-[160px] truncate" title={node.module}>
            {node.module}
          </Badge>
        )}

        <span
          className={`shrink-0 tabular-nums text-xs rounded-full px-2 py-0.5 ${
            node.sku_count > 0 ? "bg-muted text-foreground/80" : "text-muted-foreground/50"
          }`}
          title="Aantal SKU's"
        >
          {node.sku_count}
        </span>
      </div>

      {hasChildren && isOpen && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              parentCategory={category}
              expanded={expanded}
              toggle={toggle}
              selectedId={selectedId}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function CategoryHierarchy() {
  const [tree, setTree] = useState<HierarchyNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [zoek, setZoek] = useState("");

  const fetchTree = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/categories/hierarchy", { headers: getAuthHeaders() });
      if (!resp.ok) throw new Error(`Status ${resp.status}`);
      const data = await resp.json();
      const roots: HierarchyNode[] = data.tree || [];
      setTree(roots);
      // Standaard: hoofdcategorieën uitgeklapt
      setExpanded(new Set(roots.map((r) => r.id)));
    } catch (e) {
      setError("Kon de categorieënhiërarchie niet laden.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTree();
  }, []);

  const toggle = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const collectIds = (nodes: HierarchyNode[], acc: number[] = []): number[] => {
    for (const n of nodes) {
      acc.push(n.id);
      if (n.children?.length) collectIds(n.children, acc);
    }
    return acc;
  };

  const expandAll = () => setExpanded(new Set(collectIds(tree)));
  const collapseAll = () => setExpanded(new Set());

  const onSelect = async (sel: SelectedNode) => {
    setSelected(sel);
    setZoek("");
    setLoadingProducts(true);
    setProducts([]);
    try {
      const params = new URLSearchParams({ page: "1", page_size: "500", category: sel.category });
      if (sel.subcategory) params.set("subcategory", sel.subcategory);
      const resp = await fetch(`/api/products?${params.toString()}`, { headers: getAuthHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        setProducts(data.items || []);
      }
    } catch {
      /* netwerkfout — laat lege lijst zien */
    } finally {
      setLoadingProducts(false);
    }
  };

  const totalNodes = useMemo(() => countNodes(tree), [tree]);
  const totalSkus = useMemo(
    () => tree.reduce((acc, n) => acc + (n.sku_count || 0), 0),
    [tree],
  );

  const zichtbareProducten = products.filter((p) => {
    if (!zoek) return true;
    const q = zoek.toLowerCase();
    return (
      p.sku_id.toLowerCase().includes(q) ||
      p.product_name.toLowerCase().includes(q) ||
      (p.brand || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Categorieënhiërarchie</h1>
          <p className="text-muted-foreground mt-1">
            Blader door de DRS-categorieboom en bekijk het aantal SKU's per knoop. Klik op een (sub)categorie om de bijbehorende producten te tonen.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchTree} disabled={loading}>
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          <span className="ml-1.5">Vernieuwen</span>
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Boom */}
        <Card className="lg:col-span-3">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">DRS-categorieboom</CardTitle>
                <CardDescription>
                  {loading ? "Laden…" : `${totalNodes} knopen · ${totalSkus} SKU's`}
                </CardDescription>
              </div>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={expandAll} disabled={loading || tree.length === 0}>
                  Alles uitklappen
                </Button>
                <Button variant="ghost" size="sm" onClick={collapseAll} disabled={loading || tree.length === 0}>
                  Inklappen
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-7 w-full" />
                ))}
              </div>
            ) : error ? (
              <div className="text-sm text-red-600 py-8 text-center">{error}</div>
            ) : tree.length === 0 ? (
              <div className="text-sm text-muted-foreground py-8 text-center">
                Geen categorieënhiërarchie gevonden.
              </div>
            ) : (
              <div className="-mx-2">
                {tree.map((node) => (
                  <TreeNode
                    key={node.id}
                    node={node}
                    parentCategory={null}
                    expanded={expanded}
                    toggle={toggle}
                    selectedId={selected?.node.id ?? null}
                    onSelect={onSelect}
                    depth={0}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Producten in geselecteerde tak */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              {selected ? selected.node.name : "Producten"}
            </CardTitle>
            <CardDescription>
              {selected
                ? selected.subcategory
                  ? `${selected.category} › ${selected.subcategory}`
                  : selected.category
                : "Selecteer een categorie in de boom om de SKU's te bekijken."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!selected ? (
              <div className="text-sm text-muted-foreground py-12 text-center">
                Klik op een (sub)categorie links om de bijbehorende producten te tonen.
              </div>
            ) : loadingProducts ? (
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : products.length === 0 ? (
              <div className="text-sm text-muted-foreground py-12 text-center">
                Geen producten in deze tak.
              </div>
            ) : (
              <div className="space-y-3">
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Filter binnen tak…"
                    className="pl-9"
                    value={zoek}
                    onChange={(e) => setZoek(e.target.value)}
                  />
                </div>
                <div className="text-xs text-muted-foreground">
                  {zichtbareProducten.length} van {products.length} SKU's
                </div>
                <div className="border rounded-md max-h-[480px] overflow-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>SKU</TableHead>
                        <TableHead>Naam</TableHead>
                        <TableHead className="text-right">Prijs</TableHead>
                        <TableHead></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {zichtbareProducten.map((p) => (
                        <TableRow key={p.sku_id} className="group">
                          <TableCell className="font-mono text-xs">{p.sku_id}</TableCell>
                          <TableCell className="max-w-[180px] truncate" title={p.product_name}>
                            <div>{p.product_name}</div>
                            {p.brand && <div className="text-[10px] text-muted-foreground">{p.brand}</div>}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{fmtBedrag(p.current_price)}</TableCell>
                          <TableCell className="text-right">
                            <Link href={`/producten/${p.sku_id}`}>
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground group-hover:text-foreground">
                                <ChevronRight className="h-4 w-4" />
                              </Button>
                            </Link>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
