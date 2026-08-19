import { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  ChevronDown, ChevronRight, Folder, FolderOpen, FolderTree, Loader2,
  Package, RefreshCw, Search, Upload, CheckCircle2, AlertTriangle,
  History, ArrowRight, FileSpreadsheet,
} from "lucide-react";
import { getAuthHeaders, useAuth } from "@/lib/auth";

/* ── Types ─────────────────────────────────────────────────────────────── */

type Node = {
  id: number; name: string; parent_id: number | null; level: number;
  path: string | null; path_names: string | null;
  external_option_id: string | null; is_active: boolean; source: string | null;
  sku_count?: number; children?: Node[]; has_children?: boolean;
};

type Stats = {
  nodes_totaal: number; nodes_actief: number; max_diepte: number; paden: number;
  producten_totaal: number; producten_gekoppeld: number; producten_ongekoppeld: number;
  laatste_import: { job_id: number; bestand: string; voltooid_op: string | null; door: string | null } | null;
};

type WizardState = {
  stap: number; // 1 upload, 2 gevalideerd, 3 impact, 4 toegepast
  jobId?: number;
  upload?: any; validatie?: any; impact?: any; resultaat?: any;
  bezig: boolean; fout?: string;
};

const nf = new Intl.NumberFormat("nl-NL");

/* ── Boomcomponent (lazy) ──────────────────────────────────────────────── */

function TreeRow({ node, depth, expanded, toggle, selectedId, onSelect, childrenMap }: {
  node: Node; depth: number;
  expanded: Set<number>; toggle: (n: Node) => void;
  selectedId: number | null; onSelect: (n: Node) => void;
  childrenMap: Record<number, Node[] | undefined>;
}) {
  const kids = childrenMap[node.id] ?? node.children ?? [];
  const open = expanded.has(node.id);
  const mightHaveKids = node.has_children !== false;
  return (
    <div>
      <div
        className={`flex items-center gap-1.5 py-1 pr-2 rounded-md cursor-pointer text-sm ${
          selectedId === node.id ? "bg-primary/10 text-primary font-medium" : "hover:bg-muted"
        } ${!node.is_active ? "opacity-50" : ""}`}
        style={{ paddingLeft: depth * 16 + 4 }}
        onClick={() => onSelect(node)}
        data-testid={`tree-node-${node.id}`}
      >
        <span onClick={(e) => { e.stopPropagation(); toggle(node); }} className="shrink-0 w-4">
          {mightHaveKids ? (open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />) : null}
        </span>
        {open ? <FolderOpen className="w-4 h-4 text-amber-500 shrink-0" /> : <Folder className="w-4 h-4 text-amber-500 shrink-0" />}
        <span className="truncate">{node.name}</span>
        {node.sku_count != null && node.sku_count > 0 && (
          <Badge variant="secondary" className="ml-auto text-[10px]">{nf.format(node.sku_count)}</Badge>
        )}
      </div>
      {open && kids.map((k) => (
        <TreeRow key={k.id} node={k} depth={depth + 1} expanded={expanded} toggle={toggle}
          selectedId={selectedId} onSelect={onSelect} childrenMap={childrenMap} />
      ))}
    </div>
  );
}

/* ── Pagina ────────────────────────────────────────────────────────────── */

export default function ProductHierarchie() {
  const { user } = useAuth();
  const magMuteren = user && ["admin", "pricing_manager"].includes(user.role);

  const [stats, setStats] = useState<Stats | null>(null);
  const [roots, setRoots] = useState<Node[]>([]);
  const [childrenMap, setChildrenMap] = useState<Record<number, Node[] | undefined>>({});
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<Node | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [producten, setProducten] = useState<any>(null);
  const [breadcrumb, setBreadcrumb] = useState<Node[]>([]);
  const [zoek, setZoek] = useState("");
  const [zoekResultaten, setZoekResultaten] = useState<Node[] | null>(null);
  const [laadBoom, setLaadBoom] = useState(true);
  const [historie, setHistorie] = useState<any[] | null>(null);
  const [wizard, setWizard] = useState<WizardState>({ stap: 1, bezig: false });
  const fileRef = useRef<HTMLInputElement>(null);

  const laadStats = useCallback(async () => {
    const r = await fetch("/api/product-hierarchy/stats", { headers: getAuthHeaders() });
    if (r.ok) setStats(await r.json());
  }, []);

  const laadRoots = useCallback(async () => {
    setLaadBoom(true);
    try {
      const r = await fetch("/api/product-hierarchy/tree?depth=2", { headers: getAuthHeaders() });
      if (r.ok) {
        const d = await r.json();
        setRoots(d.roots || []);
        const map: Record<number, Node[]> = {};
        for (const root of d.roots || []) map[root.id] = root.children || [];
        setChildrenMap(map);
      }
    } finally { setLaadBoom(false); }
  }, []);

  useEffect(() => { laadStats(); laadRoots(); }, [laadStats, laadRoots]);

  const toggle = async (node: Node) => {
    const next = new Set(expanded);
    if (next.has(node.id)) { next.delete(node.id); setExpanded(next); return; }
    next.add(node.id); setExpanded(next);
    if (childrenMap[node.id] === undefined) {
      const r = await fetch(`/api/product-hierarchy/nodes/${node.id}/children`, { headers: getAuthHeaders() });
      if (r.ok) {
        const kids = await r.json();
        setChildrenMap((m) => ({ ...m, [node.id]: kids }));
      }
    }
  };

  const selecteer = async (node: Node) => {
    setSelected(node); setDetail(null); setProducten(null); setBreadcrumb([]);
    const h = { headers: getAuthHeaders() };
    const [d, p, b] = await Promise.all([
      fetch(`/api/product-hierarchy/nodes/${node.id}`, h),
      fetch(`/api/product-hierarchy/nodes/${node.id}/products?include_descendants=true&limit=25`, h),
      fetch(`/api/product-hierarchy/nodes/${node.id}/breadcrumb`, h),
    ]);
    if (d.ok) setDetail(await d.json());
    if (p.ok) setProducten(await p.json());
    if (b.ok) setBreadcrumb((await b.json()).breadcrumb || []);
  };

  const doeZoek = async () => {
    if (!zoek.trim()) { setZoekResultaten(null); return; }
    const r = await fetch(`/api/product-hierarchy/search?q=${encodeURIComponent(zoek)}`, { headers: getAuthHeaders() });
    if (r.ok) setZoekResultaten(await r.json());
  };

  const laadHistorie = async () => {
    const r = await fetch("/api/product-hierarchy/changes?limit=100", { headers: getAuthHeaders() });
    if (r.ok) setHistorie(await r.json());
  };

  /* ── Wizard-acties ── */
  const upload = async (file: File) => {
    setWizard({ stap: 1, bezig: true });
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/product-hierarchy/import/upload", {
        method: "POST", headers: getAuthHeaders(), body: fd,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Upload mislukt");
      setWizard({ stap: 1, bezig: false, jobId: d.job_id, upload: d });
    } catch (e: any) {
      setWizard({ stap: 1, bezig: false, fout: e.message });
    }
  };

  const valideer = async () => {
    setWizard((w) => ({ ...w, bezig: true, fout: undefined }));
    try {
      const r = await fetch(`/api/product-hierarchy/import/${wizard.jobId}/validate`, {
        method: "POST", headers: getAuthHeaders(),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Validatie mislukt");
      const ri = await fetch(`/api/product-hierarchy/import/${wizard.jobId}/impact`, { headers: getAuthHeaders() });
      const imp = ri.ok ? await ri.json() : null;
      setWizard((w) => ({ ...w, stap: 3, bezig: false, validatie: d, impact: imp }));
    } catch (e: any) {
      setWizard((w) => ({ ...w, bezig: false, fout: e.message }));
    }
  };

  const pasToe = async () => {
    setWizard((w) => ({ ...w, bezig: true, fout: undefined }));
    try {
      const r = await fetch(`/api/product-hierarchy/import/${wizard.jobId}/apply`, {
        method: "POST", headers: getAuthHeaders(),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Toepassen mislukt");
      setWizard((w) => ({ ...w, stap: 4, bezig: false, resultaat: d }));
      laadStats(); laadRoots();
    } catch (e: any) {
      setWizard((w) => ({ ...w, bezig: false, fout: e.message }));
    }
  };

  const statCards = stats ? [
    { label: "Nodes (actief)", value: `${nf.format(stats.nodes_actief)} / ${nf.format(stats.nodes_totaal)}` },
    { label: "Max. diepte", value: String(stats.max_diepte) },
    { label: "Paden", value: nf.format(stats.paden) },
    { label: "Producten gekoppeld", value: `${nf.format(stats.producten_gekoppeld)} / ${nf.format(stats.producten_totaal)}` },
    { label: "Ongekoppeld", value: nf.format(stats.producten_ongekoppeld) },
  ] : [];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FolderTree className="w-6 h-6" /> Producthiërarchie
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Eén canonieke producthiërarchie als centrale dimensie van het platform.
            {stats?.laatste_import && (
              <> Laatste import: <span className="font-medium">{stats.laatste_import.bestand}</span>
                {stats.laatste_import.voltooid_op && ` op ${new Date(stats.laatste_import.voltooid_op).toLocaleString("nl-NL")}`}
                {stats.laatste_import.door && ` door ${stats.laatste_import.door}`}.</>
            )}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { laadStats(); laadRoots(); }} data-testid="button-refresh">
          <RefreshCw className="w-4 h-4 mr-1" /> Vernieuwen
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {statCards.map((c) => (
          <Card key={c.label}><CardContent className="p-4">
            <div className="text-xs text-muted-foreground">{c.label}</div>
            <div className="text-xl font-bold" data-testid={`stat-${c.label}`}>{c.value}</div>
          </CardContent></Card>
        ))}
      </div>

      <Tabs defaultValue="beheer" onValueChange={(t) => { if (t === "historie" && historie === null) laadHistorie(); }}>
        <TabsList>
          <TabsTrigger value="beheer" data-testid="tab-beheer">Boom & beheer</TabsTrigger>
          {magMuteren && <TabsTrigger value="import" data-testid="tab-import">Import-wizard</TabsTrigger>}
          <TabsTrigger value="historie" data-testid="tab-historie">Wijzigingshistorie</TabsTrigger>
        </TabsList>

        {/* ── Boom & beheer ── */}
        <TabsContent value="beheer" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Hiërarchieboom</CardTitle>
                <div className="flex gap-2 pt-1">
                  <Input placeholder="Zoek node of optionId…" value={zoek}
                    onChange={(e) => setZoek(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && doeZoek()}
                    data-testid="input-zoek" />
                  <Button variant="secondary" size="icon" onClick={doeZoek}><Search className="w-4 h-4" /></Button>
                </div>
              </CardHeader>
              <CardContent className="max-h-[560px] overflow-auto">
                {zoekResultaten !== null ? (
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                      <span>{zoekResultaten.length} resultaten</span>
                      <Button variant="ghost" size="sm" onClick={() => { setZoekResultaten(null); setZoek(""); }}>Wissen</Button>
                    </div>
                    {zoekResultaten.map((n) => (
                      <div key={n.id} className="p-2 rounded-md hover:bg-muted cursor-pointer text-sm"
                        onClick={() => selecteer(n)} data-testid={`zoek-${n.id}`}>
                        <div className="font-medium">{n.name}</div>
                        <div className="text-xs text-muted-foreground">{n.path_names}</div>
                      </div>
                    ))}
                  </div>
                ) : laadBoom ? (
                  <div className="flex items-center gap-2 text-muted-foreground text-sm p-4">
                    <Loader2 className="w-4 h-4 animate-spin" /> Boom laden…
                  </div>
                ) : roots.length === 0 ? (
                  <div className="text-sm text-muted-foreground p-4">
                    Nog geen hiërarchie. {magMuteren ? "Gebruik de import-wizard om het hiërarchiebestand te laden." : "Vraag een beheerder om het hiërarchiebestand te importeren."}
                  </div>
                ) : (
                  roots.map((r) => (
                    <TreeRow key={r.id} node={r} depth={0} expanded={expanded} toggle={toggle}
                      selectedId={selected?.id ?? null} onSelect={selecteer} childrenMap={childrenMap} />
                  ))
                )}
              </CardContent>
            </Card>

            <Card className="lg:col-span-3">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Node-detail</CardTitle>
                {breadcrumb.length > 0 && (
                  <CardDescription className="flex items-center flex-wrap gap-1">
                    {breadcrumb.map((b, i) => (
                      <span key={b.id} className="flex items-center gap-1">
                        {i > 0 && <ChevronRight className="w-3 h-3" />}
                        <button className="hover:underline" onClick={() => selecteer(b)}>{b.name}</button>
                      </span>
                    ))}
                  </CardDescription>
                )}
              </CardHeader>
              <CardContent>
                {!selected ? (
                  <div className="text-sm text-muted-foreground py-8 text-center">Selecteer een node in de boom.</div>
                ) : !detail ? (
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                ) : (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                      <div><div className="text-xs text-muted-foreground">Naam</div><div className="font-medium">{detail.name}</div></div>
                      <div><div className="text-xs text-muted-foreground">Niveau</div><div>{detail.level}</div></div>
                      <div><div className="text-xs text-muted-foreground">Option-ID</div><div className="font-mono text-xs">{detail.external_option_id || "—"}</div></div>
                      <div><div className="text-xs text-muted-foreground">Status</div>
                        <Badge variant={detail.is_active ? "default" : "secondary"}>{detail.is_active ? "Actief" : "Inactief"}</Badge></div>
                      <div><div className="text-xs text-muted-foreground">Producten (direct)</div><div>{nf.format(detail.sku_count ?? 0)}</div></div>
                      <div><div className="text-xs text-muted-foreground">Incl. onderliggend</div><div>{nf.format(detail.sku_count_incl_descendants ?? 0)}</div></div>
                      <div><div className="text-xs text-muted-foreground">Subniveaus</div><div>{nf.format(detail.descendant_count ?? 0)}</div></div>
                      <div><div className="text-xs text-muted-foreground">Bron</div><div>{detail.source || "—"}</div></div>
                    </div>
                    <div>
                      <div className="text-sm font-medium mb-2 flex items-center gap-1">
                        <Package className="w-4 h-4" /> Producten in deze tak
                        {producten && <span className="text-xs text-muted-foreground font-normal">({nf.format(producten.totaal)} totaal, eerste 25)</span>}
                      </div>
                      {producten?.producten?.length ? (
                        <Table>
                          <TableHeader><TableRow>
                            <TableHead>SKU</TableHead><TableHead>Naam</TableHead>
                            <TableHead>Merk</TableHead><TableHead className="text-right">Prijs</TableHead>
                          </TableRow></TableHeader>
                          <TableBody>
                            {producten.producten.map((p: any) => (
                              <TableRow key={p.sku_id}>
                                <TableCell className="font-mono text-xs">{p.sku_id}</TableCell>
                                <TableCell className="max-w-[280px] truncate">{p.product_name}</TableCell>
                                <TableCell>{p.brand || "—"}</TableCell>
                                <TableCell className="text-right">{p.current_price != null
                                  ? new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(p.current_price) : "—"}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      ) : (
                        <div className="text-sm text-muted-foreground">Geen producten gekoppeld aan deze tak.</div>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ── Import-wizard ── */}
        {magMuteren && (
          <TabsContent value="import" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2"><Upload className="w-4 h-4" /> Hiërarchie importeren</CardTitle>
                <CardDescription>
                  Niet-destructief: upload → kolomdetectie → validatie → impactanalyse → goedkeuring → import.
                  Bestaande koppelingen verdwijnen nooit stilzwijgend; verplaatsingen worden gelogd.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {wizard.fout && (
                  <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 rounded-md p-3">
                    <AlertTriangle className="w-4 h-4 shrink-0" /> {wizard.fout}
                  </div>
                )}

                {/* Stap 1: upload */}
                <div className="flex items-center gap-3">
                  <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
                    onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} data-testid="input-file" />
                  <Button onClick={() => fileRef.current?.click()} disabled={wizard.bezig} data-testid="button-upload">
                    {wizard.bezig && wizard.stap === 1 ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <FileSpreadsheet className="w-4 h-4 mr-1" />}
                    Kies bestand (XLSX/XLS/CSV)
                  </Button>
                  {wizard.upload && (
                    <span className="text-sm text-muted-foreground">
                      {nf.format(wizard.upload.rows_staged)} rijen klaargezet · kolommen: {wizard.upload.kolommen.join(", ")}
                    </span>
                  )}
                </div>

                {/* Preview + mapping */}
                {wizard.upload && wizard.stap < 4 && (
                  <div className="space-y-3">
                    <div className="text-sm">
                      <span className="font-medium">Herkende kolommen:</span>{" "}
                      optionId → <code className="text-xs">{wizard.upload.mapping.option_col || "—"}</code>,{" "}
                      productcode → <code className="text-xs">{wizard.upload.mapping.product_col || "—"}</code>,{" "}
                      pad → <code className="text-xs">{wizard.upload.mapping.path_col || (wizard.upload.mapping.level_cols || []).join(" + ") || "—"}</code>
                      {wizard.upload.mapping.separator && <> (separator „{wizard.upload.mapping.separator}”)</>}
                    </div>
                    <div className="border rounded-md overflow-auto max-h-56">
                      <Table>
                        <TableHeader><TableRow>
                          <TableHead>#</TableHead><TableHead>optionId</TableHead>
                          <TableHead>Productcode</TableHead><TableHead>Pad</TableHead>
                        </TableRow></TableHeader>
                        <TableBody>
                          {wizard.upload.preview.map((r: any) => (
                            <TableRow key={r.row_number}>
                              <TableCell>{r.row_number}</TableCell>
                              <TableCell className="font-mono text-xs">{r.external_option_id || "—"}</TableCell>
                              <TableCell className="font-mono text-xs">{r.product_code || "—"}</TableCell>
                              <TableCell>{(r.path || []).join(" > ")}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                    {wizard.stap < 3 && (
                      <Button onClick={valideer} disabled={wizard.bezig} data-testid="button-valideer">
                        {wizard.bezig ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <ArrowRight className="w-4 h-4 mr-1" />}
                        Valideren & impact bepalen
                      </Button>
                    )}
                  </div>
                )}

                {/* Stap 3: validatie + impact */}
                {wizard.validatie && wizard.stap === 3 && (
                  <div className="space-y-3">
                    <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                      {Object.entries(wizard.validatie.counts).map(([k, v]) => (
                        <Card key={k}><CardContent className="p-3">
                          <div className="text-[11px] text-muted-foreground capitalize">{k.replace("_", " ")}</div>
                          <div className="text-lg font-bold" data-testid={`val-${k}`}>{nf.format(v as number)}</div>
                        </CardContent></Card>
                      ))}
                    </div>
                    {wizard.validatie.warnings?.length > 0 && (
                      <div className="text-xs text-amber-600 space-y-0.5">
                        {wizard.validatie.warnings.slice(0, 10).map((w: string, i: number) => <div key={i}>⚠ {w}</div>)}
                      </div>
                    )}
                    {wizard.impact && (
                      <div className="border rounded-md p-3 text-sm space-y-1">
                        <div className="font-medium">Impactanalyse</div>
                        <div>Nodes: {nf.format(wizard.impact.nodes.nieuw)} nieuw · {nf.format(wizard.impact.nodes.hernoemd)} hernoemd · {nf.format(wizard.impact.nodes.verplaatst)} verplaatst · {nf.format(wizard.impact.nodes.ongewijzigde_paden)} paden ongewijzigd</div>
                        <div>Koppelingen: {nf.format(wizard.impact.assignments.nieuw)} nieuw · {nf.format(wizard.impact.assignments.verplaatst)} verplaatst · {nf.format(wizard.impact.assignments.ongewijzigd)} ongewijzigd · {nf.format(wizard.impact.assignments.niet_gevonden_producten)} producten niet gevonden</div>
                        {(wizard.impact.hernoemd_voorbeelden || []).slice(0, 5).map((h: any, i: number) => (
                          <div key={i} className="text-xs text-muted-foreground">Hernoemd: {h.van} → {h.naar} ({h.option_id})</div>
                        ))}
                        {(wizard.impact.verplaatst_voorbeelden || []).slice(0, 5).map((h: any, i: number) => (
                          <div key={i} className="text-xs text-muted-foreground">Verplaatst: {h.node}: {h.van || "—"} → {h.naar || "—"}</div>
                        ))}
                      </div>
                    )}
                    {wizard.validatie.kan_gedeeltelijk_toepassen && (
                      <div className="text-xs text-red-600" data-testid="text-apply-blocked">
                        Importeren is geblokkeerd zolang er validatiefouten zijn. Corrigeer het bestand en upload opnieuw.
                      </div>
                    )}
                    <Button onClick={pasToe} disabled={wizard.bezig || !wizard.validatie.kan_toepassen} data-testid="button-apply">
                      {wizard.bezig ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-1" />}
                      Goedkeuren & importeren
                    </Button>
                  </div>
                )}

                {/* Stap 4: resultaat */}
                {wizard.resultaat && (
                  <div className="border rounded-md p-4 bg-emerald-50 dark:bg-emerald-950/30 text-sm space-y-1">
                    <div className="font-medium flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                      <CheckCircle2 className="w-4 h-4" /> Import toegepast
                    </div>
                    {Object.entries(wizard.resultaat.stats).map(([k, v]) => (
                      <div key={k}>{k.replace(/_/g, " ")}: <span className="font-medium">{nf.format(v as number)}</span></div>
                    ))}
                    <div className="text-xs text-muted-foreground">{nf.format(wizard.resultaat.wijzigingen_gelogd)} wijzigingen vastgelegd in de historie.</div>
                    <Button variant="outline" size="sm" className="mt-2"
                      onClick={() => setWizard({ stap: 1, bezig: false })}>Nieuwe import</Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}

        {/* ── Historie ── */}
        <TabsContent value="historie" className="mt-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2"><History className="w-4 h-4" /> Wijzigingshistorie</CardTitle>
              <CardDescription>Nieuwe, hernoemde, verplaatste en gedeactiveerde nodes en verplaatste producttoewijzingen.</CardDescription>
            </CardHeader>
            <CardContent>
              {historie === null ? (
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              ) : historie.length === 0 ? (
                <div className="text-sm text-muted-foreground">Nog geen wijzigingen vastgelegd.</div>
              ) : (
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Wanneer</TableHead><TableHead>Type</TableHead>
                    <TableHead>Node/SKU</TableHead><TableHead>Oud</TableHead>
                    <TableHead>Nieuw</TableHead><TableHead>Door</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {historie.map((c) => (
                      <TableRow key={c.id}>
                        <TableCell className="text-xs whitespace-nowrap">{c.created_at ? new Date(c.created_at).toLocaleString("nl-NL") : "—"}</TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px]">{c.change_type}</Badge></TableCell>
                        <TableCell className="font-mono text-xs">{c.sku_id || (c.node_id != null ? `node ${c.node_id}` : "—")}</TableCell>
                        <TableCell className="text-xs max-w-[200px] truncate">{c.old_value ? JSON.stringify(c.old_value) : "—"}</TableCell>
                        <TableCell className="text-xs max-w-[200px] truncate">{c.new_value ? JSON.stringify(c.new_value) : "—"}</TableCell>
                        <TableCell className="text-xs">{c.performed_by || "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
