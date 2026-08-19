/**
 * Management-drilldown (taak #221) — KPI's per hiërarchieniveau met
 * doordrillen en cross-shop vergelijking (waar geautoriseerd).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronRight, FolderTree, Home, Store, TrendingUp, AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InfoTooltip } from "@/components/InfoTooltip";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface NodeInfo {
  id: number; name: string; level: number;
  path: string | null; path_names: string | null;
}
interface KpiRow {
  sku_count: number; revenue_ytd: number; margin_ytd: number;
  margin_pct: number | null; opportunities: number; risks: number;
}
type ChildRow = NodeInfo & KpiRow & { has_children: boolean };
interface DrilldownResponse {
  node: NodeInfo | null;
  breadcrumb: NodeInfo[];
  totals: KpiRow | null;
  children: ChildRow[];
}
interface ShopRow extends KpiRow {
  shop_id: number; shop_code: string; shop_name: string; country: string | null;
}

const eur = (n: number) =>
  new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

function KpiCells({ row }: { row: KpiRow }) {
  return (
    <>
      <TableCell className="text-right tabular-nums">{row.sku_count}</TableCell>
      <TableCell className="text-right tabular-nums">{eur(row.revenue_ytd)}</TableCell>
      <TableCell className="text-right tabular-nums">{eur(row.margin_ytd)}</TableCell>
      <TableCell className="text-right tabular-nums">
        {row.margin_pct != null ? `${row.margin_pct}%` : "—"}
      </TableCell>
      <TableCell className="text-right">
        {row.opportunities > 0
          ? <Badge variant="secondary" className="gap-1"><TrendingUp className="w-3 h-3" />{row.opportunities}</Badge>
          : <span className="text-muted-foreground">0</span>}
      </TableCell>
      <TableCell className="text-right">
        {row.risks > 0
          ? <Badge variant="destructive" className="gap-1"><AlertTriangle className="w-3 h-3" />{row.risks}</Badge>
          : <span className="text-muted-foreground">0</span>}
      </TableCell>
    </>
  );
}

function KpiHeader() {
  return (
    <TableRow>
      <TableHead>Niveau</TableHead>
      <TableHead className="text-right">SKU's</TableHead>
      <TableHead className="text-right">Omzet (YTD)</TableHead>
      <TableHead className="text-right">Marge (YTD)</TableHead>
      <TableHead className="text-right">Marge %</TableHead>
      <TableHead className="text-right">Kansen</TableHead>
      <TableHead className="text-right">Risico's</TableHead>
    </TableRow>
  );
}

export default function ManagementDrilldown() {
  const [nodeId, setNodeId] = useState<number | null>(null);

  const { data, isLoading } = useQuery<DrilldownResponse>({
    queryKey: ["/api/management/drilldown", nodeId],
    queryFn: async () => {
      const qs = nodeId != null ? `?node_id=${nodeId}` : "";
      const res = await fetch(`${BASE}/api/management/drilldown${qs}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Drilldown laden mislukt");
      return res.json();
    },
  });

  const { data: shopData, isLoading: shopsLoading } = useQuery<{ shops: ShopRow[] }>({
    queryKey: ["/api/management/drilldown/shops", nodeId],
    queryFn: async () => {
      const qs = nodeId != null ? `?node_id=${nodeId}` : "";
      const res = await fetch(`${BASE}/api/management/drilldown/shops${qs}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Shopvergelijking laden mislukt");
      return res.json();
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            Management-drilldown
            <InfoTooltip inline={{
              naam: "Management-drilldown",
              korteUitleg: "KPI's per hiërarchieniveau, met doordrillen tot op SKU-groepniveau.",
              uitgebreideUitleg: "Omzet, marge, open kansen (prijsadviezen die op besluit wachten) en risico's (actieve high/critical-signalen) worden per niveau van de canonieke producthiërarchie geaggregeerd. Klik op een niveau om door te drillen; het tabblad Shops vergelijkt dezelfde KPI's per winkel (alleen winkels waartoe je geautoriseerd bent).",
              interpretatie: "Elke rij toont het subtotaal van dat hiërarchieniveau inclusief alle onderliggende niveaus.",
              businessImpact: "Snel zien welke delen van het assortiment omzet en marge dragen — en waar kansen en risico's zich concentreren.",
            }} />
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Omzet, marge, kansen en risico's per hiërarchieniveau — klik om door te drillen.
          </p>
        </div>
      </div>

      {/* Breadcrumb over de hiërarchie */}
      <div className="flex items-center gap-1 text-sm flex-wrap" data-testid="drilldown-breadcrumb">
        <Button variant={nodeId == null ? "secondary" : "ghost"} size="sm"
          className="gap-1 h-7" onClick={() => setNodeId(null)} data-testid="drilldown-root">
          <Home className="w-3.5 h-3.5" /> Alles
        </Button>
        {(data?.breadcrumb ?? []).map((b) => (
          <span key={b.id} className="flex items-center gap-1">
            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
            <Button
              variant={nodeId === b.id ? "secondary" : "ghost"} size="sm" className="h-7"
              onClick={() => setNodeId(b.id)} data-testid={`drilldown-crumb-${b.id}`}
            >
              {b.name}
            </Button>
          </span>
        ))}
      </div>

      <Tabs defaultValue="hierarchy">
        <TabsList>
          <TabsTrigger value="hierarchy" data-testid="tab-hierarchy">Hiërarchie</TabsTrigger>
          <TabsTrigger value="shops" data-testid="tab-shops">Shops vergelijken</TabsTrigger>
        </TabsList>

        <TabsContent value="hierarchy">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <FolderTree className="w-4 h-4" />
                {data?.node ? data.node.name : "Topniveaus"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <Skeleton className="h-40 w-full" />
              ) : (
                <Table>
                  <TableHeader><KpiHeader /></TableHeader>
                  <TableBody>
                    {data?.totals && (
                      <TableRow className="font-semibold bg-muted/40" data-testid="drilldown-totals">
                        <TableCell>Totaal — {data.node?.name}</TableCell>
                        <KpiCells row={data.totals} />
                      </TableRow>
                    )}
                    {(data?.children ?? []).map((c) => (
                      <TableRow key={c.id} data-testid={`drilldown-row-${c.id}`}>
                        <TableCell>
                          <button
                            type="button"
                            className={`flex items-center gap-1.5 ${c.has_children ? "hover:underline font-medium" : "cursor-default"}`}
                            onClick={() => c.has_children && setNodeId(c.id)}
                            data-testid={`drilldown-node-${c.id}`}
                          >
                            {c.name}
                            {c.has_children && <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
                          </button>
                        </TableCell>
                        <KpiCells row={c} />
                      </TableRow>
                    ))}
                    {(data?.children ?? []).length === 0 && !data?.totals && (
                      <TableRow>
                        <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                          Geen hiërarchieniveaus gevonden.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="shops">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Store className="w-4 h-4" />
                Cross-shop vergelijking{data?.node ? ` — ${data.node.name}` : ""}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {shopsLoading ? (
                <Skeleton className="h-40 w-full" />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Shop</TableHead>
                      <TableHead className="text-right">SKU's</TableHead>
                      <TableHead className="text-right">Omzet (YTD)</TableHead>
                      <TableHead className="text-right">Marge (YTD)</TableHead>
                      <TableHead className="text-right">Marge %</TableHead>
                      <TableHead className="text-right">Kansen</TableHead>
                      <TableHead className="text-right">Risico's</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(shopData?.shops ?? []).map((s) => (
                      <TableRow key={s.shop_id} data-testid={`drilldown-shop-${s.shop_id}`}>
                        <TableCell className="font-medium">
                          {s.shop_name}
                          {s.country && <span className="text-muted-foreground text-xs ml-2">{s.country}</span>}
                        </TableCell>
                        <KpiCells row={s} />
                      </TableRow>
                    ))}
                    {(shopData?.shops ?? []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                          Geen shops beschikbaar binnen je autorisatie.
                        </TableCell>
                      </TableRow>
                    )}
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
