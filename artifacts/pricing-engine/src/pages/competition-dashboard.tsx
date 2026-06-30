import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Search, TrendingDown, TrendingUp, Target, AlertTriangle, Circle } from "lucide-react";
import { useState } from "react";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const TRAFFIC_LIGHT: Record<string, { color: string; label: string }> = {
  green:  { color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "Belangrijk" },
  orange: { color: "text-amber-600 bg-amber-50 border-amber-200",       label: "Monitoren" },
  red:    { color: "text-red-600 bg-red-50 border-red-200",             label: "Laag" },
};

const STRATEGIE_COLORS: Record<string, string> = {
  EVERYDAY_LOW_PRICE:  "bg-blue-100 text-blue-700",
  PROMOTION_DRIVEN:    "bg-purple-100 text-purple-700",
  MARKET_SHARE_ATTACK: "bg-red-100 text-red-700",
  MARGIN_PROTECTION:   "bg-emerald-100 text-emerald-700",
  INVENTORY_CLEARANCE: "bg-orange-100 text-orange-700",
  PRICE_FOLLOWER:      "bg-slate-100 text-slate-700",
  PRICE_LEADER:        "bg-yellow-100 text-yellow-700",
};

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 text-muted-foreground shrink-0 truncate">{label}</span>
      <Progress value={value} className="h-1.5 flex-1" />
      <span className="w-7 text-right tabular-nums font-medium">{value?.toFixed(0)}</span>
    </div>
  );
}

export default function CompetitionDashboard() {
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [zoekterm, setZoekterm] = useState("");

  const { data: dashData, isLoading } = useQuery({
    queryKey: ["competition-dashboard", categoryFilter],
    queryFn: () => apiFetch(`/api/competition/dashboard${categoryFilter !== "all" ? `?category=${encodeURIComponent(categoryFilter)}` : ""}`),
  });

  const { data: summary } = useQuery({
    queryKey: ["competition-summary"],
    queryFn: () => apiFetch("/api/competition/summary"),
  });

  const categories = dashData?.categories || [];
  const allCategories = Array.from(new Set(categories.map((c: any) => c.category))) as string[];

  const filteredCategories = categories.filter((cat: any) => {
    if (!zoekterm) return true;
    return cat.competitors?.some((c: any) =>
      c.competitor_name?.toLowerCase().includes(zoekterm.toLowerCase())
    ) || cat.category?.toLowerCase().includes(zoekterm.toLowerCase());
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Competition Intelligence Dashboard</h1>
        <p className="text-muted-foreground mt-1">Top concurrenten per categorie — verkeerslicht, 7 scores, strategie en prijsactiviteit.</p>
      </div>

      {/* KPI cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-1"><Target className="h-4 w-4" /> Gem. PCIS</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-bold">{(summary.avg_pcis * 100).toFixed(0)}</div><p className="text-xs text-muted-foreground">{summary.total_skus_scored} SKU's</p></CardContent>
          </Card>
          <Card className="border-red-200">
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-1"><AlertTriangle className="h-4 w-4 text-red-500" /> Kritiek+Sterk</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-bold text-red-600">{summary.critical_count + summary.strong_count}</div><p className="text-xs text-muted-foreground">{summary.critical_count} kritiek</p></CardContent>
          </Card>
          <Card className="border-amber-200">
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-1"><TrendingDown className="h-4 w-4 text-amber-500" /> Prijsdruk</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-bold text-amber-600">{summary.downward_pressure_count}</div><p className="text-xs text-muted-foreground">SKU's duurder dan markt</p></CardContent>
          </Card>
          <Card className="border-emerald-200">
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-1"><TrendingUp className="h-4 w-4 text-emerald-500" /> Ruimte</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-bold text-emerald-600">{summary.upward_opportunity_count}</div><p className="text-xs text-muted-foreground">SKU's goedkoper dan markt</p></CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Zoek concurrent of categorie..." className="pl-9" value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
        </div>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-52"><SelectValue placeholder="Alle categorieën" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle categorieën</SelectItem>
            {allCategories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-48" />)}</div>
      ) : filteredCategories.length === 0 ? (
        <Card><CardContent className="p-12 text-center text-muted-foreground">Geen data beschikbaar. Voer een discovery-run uit of draai de backfill.</CardContent></Card>
      ) : (
        filteredCategories.map((cat: any) => (
          <Card key={cat.category}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">{cat.category}</CardTitle>
                  <CardDescription>{cat.competitors?.length || 0} concurrenten geanalyseerd</CardDescription>
                </div>
                <Link href={`/competition/categories/${encodeURIComponent(cat.category)}`}>
                  <span className="text-xs text-primary hover:underline cursor-pointer">Categorie-detail →</span>
                </Link>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="border-t">
                <div className="grid grid-cols-12 bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground border-b">
                  <div className="col-span-3">Concurrent</div>
                  <div className="col-span-1 text-center">Status</div>
                  <div className="col-span-3">7 Scores (0–100)</div>
                  <div className="col-span-2 text-right">Strategie</div>
                  <div className="col-span-1 text-right">Assortiment</div>
                  <div className="col-span-2 text-right">Laatste prijs</div>
                </div>
                <div className="divide-y">
                  {(cat.competitors || []).slice(0, 10).map((comp: any) => {
                    const tl = TRAFFIC_LIGHT[comp.traffic_light || "orange"] || TRAFFIC_LIGHT.orange;
                    return (
                      <Link key={comp.competitor_name} href={`/competition/competitors/${encodeURIComponent(comp.competitor_name)}`}>
                        <div className="grid grid-cols-12 items-center px-4 py-3 hover:bg-muted/40 cursor-pointer transition-colors">
                          <div className="col-span-3">
                            <div className="font-medium text-sm">{comp.competitor_name}</div>
                            <div className="text-xs text-muted-foreground">Score: {comp.combined_score?.toFixed(0) ?? "—"}/100</div>
                          </div>
                          <div className="col-span-1 flex justify-center">
                            <Badge variant="outline" className={`text-xs ${tl.color}`}>
                              <Circle className="h-2 w-2 mr-1 fill-current" />{tl.label}
                            </Badge>
                          </div>
                          <div className="col-span-3 space-y-0.5">
                            <ScoreBar label="Relevantie" value={comp.relevance_score || 0} />
                            <ScoreBar label="Coverage" value={comp.coverage_index || 0} />
                            <ScoreBar label="Opportunity" value={comp.opportunity_score || 0} />
                          </div>
                          <div className="col-span-2 text-right">
                            {comp.strategy_type ? (
                              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${STRATEGIE_COLORS[comp.strategy_type] || "bg-slate-100 text-slate-700"}`}>
                                {comp.strategy_label_nl || comp.strategy_type}
                              </span>
                            ) : <span className="text-xs text-muted-foreground">—</span>}
                          </div>
                          <div className="col-span-1 text-right text-xs tabular-nums">
                            {comp.assortment_size ? `${comp.assortment_size} SKU's` : "—"}
                          </div>
                          <div className="col-span-2 text-right text-xs text-muted-foreground">
                            {comp.last_price_change_date || "—"}
                          </div>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
