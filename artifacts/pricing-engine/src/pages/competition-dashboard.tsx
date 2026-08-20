import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Search, TrendingDown, TrendingUp, Target, AlertTriangle, Circle, Minus, Sparkles, Ban, RefreshCw, Loader2 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useState } from "react";
import { useShopId, withShop } from "@/hooks/use-shop-id";
import { useAuth } from "@/lib/auth";
import { useEngineRun } from "@/lib/use-engine-run";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

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

function RankSparkline({ points }: { points: { run_date: string; rank: number }[] }) {
  if (!points || points.length < 2) return null;
  const w = 72, h = 20, pad = 2;
  const ranks = points.map(p => p.rank ?? 0);
  const min = Math.min(...ranks), max = Math.max(...ranks);
  const span = Math.max(1, max - min);
  // Lagere rank = beter = hoger in de grafiek
  const xy = points.map((p, i) => {
    const x = pad + (i * (w - 2 * pad)) / (points.length - 1);
    const y = pad + (((p.rank ?? 0) - min) / span) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const improving = ranks[ranks.length - 1] < ranks[0];
  const worsening = ranks[ranks.length - 1] > ranks[0];
  const color = improving ? "#059669" : worsening ? "#ef4444" : "#94a3b8";
  return (
    <svg width={w} height={h} className="shrink-0" aria-label="rank-verloop">
      <polyline points={xy.join(" ")} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 text-muted-foreground shrink-0 truncate">{label}</span>
      <Progress value={value} className="h-1.5 flex-1" />
      <span className="w-7 text-right tabular-nums font-medium">{value?.toFixed(0)}</span>
    </div>
  );
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("nl-NL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function CompetitionDashboard() {
  const shopId = useShopId();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canRunRankings = user?.role === "admin" || user?.role === "pricing_manager";
  const [zoekterm, setZoekterm] = useState("");

  // Global Filter Context (taak #263): hiërarchie/merk gaan als queryparams
  // mee; de server expandeert parent-selecties naar alle descendants.
  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);
  const withFilters = (p: URLSearchParams) => {
    new URLSearchParams(filterQs).forEach((v, k) => p.set(k, v));
    return p;
  };

  const { data: dashData, isLoading } = useQuery({
    queryKey: ["competition-dashboard", shopId, filterQs],
    queryFn: () => {
      const p = new URLSearchParams();
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      const qs = withFilters(p).toString();
      return apiFetch(`/api/competition/dashboard${qs ? `?${qs}` : ""}`);
    },
  });

  const { data: summary } = useQuery({
    queryKey: ["competition-summary", shopId, filterQs],
    queryFn: () => {
      const p = new URLSearchParams();
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      const qs = withFilters(p).toString();
      return apiFetch(`/api/competition/summary${qs ? `?${qs}` : ""}`);
    },
  });

  const [rankScope, setRankScope] = useState("overall");
  const [rankFilters, setRankFilters] = useState<Record<string, string>>({});
  const setRankFilter = (key: string, value: string) =>
    setRankFilters(f => {
      const next = { ...f };
      if (!value || value === "__all__") delete next[key];
      else next[key] = value;
      return next;
    });
  const { data: rankData, isLoading: rankLoading } = useQuery({
    queryKey: ["competition-rankings", rankScope, shopId, rankFilters, filterQs],
    queryFn: () => {
      const p = new URLSearchParams({ scope: rankScope });
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      Object.entries(rankFilters).forEach(([k, v]) => p.set(k, v));
      return apiFetch(`/api/competition/rankings?${withFilters(p)}`);
    },
  });
  const rankings = rankData?.rankings || [];
  const { start: startRankingsRun, isRunning: rankingsRunning, error: rankingsRunError } = useEngineRun({
    runUrl: `${BASE}/api/competition/rankings/run${shopId !== undefined ? `?shop_id=${shopId}` : ""}`,
    onCompleted: () => {
      queryClient.invalidateQueries({ queryKey: ["competition-rankings"] });
      queryClient.invalidateQueries({ queryKey: ["competition-rankings-history"] });
    },
  });
  const [openHistory, setOpenHistory] = useState<string | null>(null);
  const { data: histData } = useQuery({
    queryKey: ["competition-rankings-history", rankScope, shopId, filterQs],
    queryFn: () => {
      const p = new URLSearchParams({ scope: rankScope });
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      return apiFetch(`/api/competition/rankings/history?${withFilters(p)}`);
    },
    enabled: rankings.length > 0,
  });
  const rankHistory: Record<string, { run_date: string; rank: number }[]> = histData?.history || {};
  const rankScopes: string[] = rankData?.scopes?.length ? rankData.scopes : ["overall"];

  const categories = dashData?.categories || [];

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

      <GlobalFilterBar />

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

      {/* Uitsluitingen per reden (laatste scoring-run) */}
      {summary && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-1"><Ban className="h-4 w-4 text-muted-foreground" /> Uitgesloten concurrentprijzen</CardTitle>
            <CardDescription>
              Per reden uitgesloten van de referentieprijs{summary.last_run_date ? ` — laatste run van ${summary.last_run_date}` : ""}. Een plotselinge stijging kan wijzen op feedproblemen of een te strenge drempel (import-instellingen op de connectoren-pagina).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4" data-testid="exclusion-breakdown">
              <div>
                <div className="text-2xl font-bold tabular-nums" data-testid="excluded-out-of-stock">{summary.excluded_by_reason?.COMPETITOR_IGNORED_OUT_OF_STOCK ?? 0}</div>
                <p className="text-xs text-muted-foreground">Niet op voorraad</p>
              </div>
              <div>
                <div className="text-2xl font-bold tabular-nums" data-testid="excluded-bad-delivery">{summary.excluded_by_reason?.COMPETITOR_IGNORED_BAD_DELIVERY ?? 0}</div>
                <p className="text-xs text-muted-foreground">Levertijd te lang</p>
              </div>
              <div>
                <div className="text-2xl font-bold tabular-nums" data-testid="excluded-outlier">{summary.excluded_by_reason?.COMPETITOR_IGNORED_OUTLIER ?? 0}</div>
                <p className="text-xs text-muted-foreground">Prijsuitbijter</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Concurrent-rankings (drie-scoremodel) */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                Concurrent-rankings
                {rankData?.stale && (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-amber-500/10 text-amber-700 border-amber-300" data-testid="badge-rankings-stale">
                    verouderd — nieuwe feed-sync sinds laatste berekening
                  </Badge>
                )}
                {rankData?.score_basis === "hierarchy_nodes" && (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-blue-500/10 text-blue-700 border-blue-300" data-testid="badge-rankings-node-scores">
                    node-specifieke scores voor de geselecteerde hiërarchie
                  </Badge>
                )}
              </CardTitle>
              <CardDescription data-testid="text-rankings-freshness">
                Rank, Competition Relevance, Price Relevance en Influence per concurrent
                {rankData?.computed_at ? ` — berekend op ${formatDateTime(rankData.computed_at)}` : rankData?.run_date ? ` — run van ${rankData.run_date}` : ""}
                {rankData?.last_feed_sync_at ? ` · laatste feed-sync ${formatDateTime(rankData.last_feed_sync_at)}` : ""}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Select value={rankScope} onValueChange={setRankScope}>
                <SelectTrigger className="w-52"><SelectValue placeholder="Scope" /></SelectTrigger>
                <SelectContent>
                  {rankScopes.map(s => (
                    <SelectItem key={s} value={s}>{s === "overall" ? "Totaal (overall)" : s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {canRunRankings && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={startRankingsRun}
                  disabled={rankingsRunning}
                  data-testid="button-run-rankings"
                >
                  {rankingsRunning
                    ? (<><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Bezig met berekenen...</>)
                    : (<><RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Bereken rankings</>)}
                </Button>
              )}
            </div>
          </div>
          {rankingsRunError && (
            <p className="text-xs text-red-600 mt-2" data-testid="text-rankings-run-error">
              Herberekening mislukt: {rankingsRunError}
            </p>
          )}
          {rankData?.changed && (
            <div className="mt-2 flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs text-blue-800" data-testid="banner-rankings-changed">
              <Sparkles className="h-3.5 w-3.5 shrink-0" />
              De ranking is gewijzigd t.o.v. de vorige berekening — verschuivingen zijn per concurrent gemarkeerd (▲ omhoog, ▼ omlaag, ✦ nieuw).
            </div>
          )}
          {/* Server-side rankingfilters (taak #248) */}
          <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="rankings-filters">
            {([
              ["company_size", "Bedrijfsomvang", ["micro", "klein", "midden", "groot", "enterprise"]],
              ["geographic_scale", "Geografische schaal", ["lokaal", "nationaal", "regionaal_eu", "europees", "globaal"]],
              ["country", "Land", ["NL", "BE", "DE", "FR", "UK"]],
              ["customer_model", "Klantfocus", ["B2C", "B2B", "hybride"]],
              ["market_role", "Competition DNA", ["prijsagressor", "assortimentsbreedte", "servicekampioen", "nichespecialist", "marketplace", "premiummerk"]],
              ["fulfilment_model", "Fulfilment", ["stockholding", "dropship", "hybrid", "marketplace"]],
              ["financial_health", "Financial health", ["gezond", "aandacht", "zwak", "unknown"]],
              ["min_business_strength", "Min. business strength", ["25", "50", "75"]],
              ["min_procurement_power", "Min. procurement power", ["25", "50", "75"]],
              ["min_data_completeness", "Min. data confidence %", ["25", "50", "75"]],
            ] as [string, string, string[]][]).map(([key, label, opts]) => (
              <Select key={key} value={rankFilters[key] || "__all__"} onValueChange={v => setRankFilter(key, v)}>
                <SelectTrigger className="h-7 w-auto min-w-36 text-xs" data-testid={`filter-${key}`}>
                  <SelectValue placeholder={label} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">{label}: alle</SelectItem>
                  {opts.map(o => <SelectItem key={o} value={o}>{label.startsWith("Min.") ? `≥ ${o}` : o}</SelectItem>)}
                </SelectContent>
              </Select>
            ))}
            {Object.keys(rankFilters).length > 0 && (
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setRankFilters({})} data-testid="button-clear-rank-filters">
                Wis filters
              </Button>
            )}
            {rankData?.total != null && (
              <span className="text-xs text-muted-foreground ml-auto" data-testid="text-rankings-total">
                {rankData.total} concurrent{rankData.total === 1 ? "" : "en"}
                {rankData?.score_basis === "hierarchy_nodes" && rankData?.unmapped_observations > 0 && (
                  <span className="ml-2 text-amber-700" data-testid="text-rankings-unmapped">
                    · {rankData.unmapped_observations} waarneming{rankData.unmapped_observations === 1 ? "" : "en"} zonder hiërarchie-mapping (tellen niet mee)
                  </span>
                )}
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="border-t">
            <div className="grid grid-cols-12 bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground border-b">
              <div className="col-span-1">Rank</div>
              <div className="col-span-4">Concurrent</div>
              <div className="col-span-2 text-right">Comp. relevance</div>
              <div className="col-span-2 text-right">Price relevance</div>
              <div className="col-span-2 text-right">Influence</div>
              <div className="col-span-1 text-right">Totaal</div>
            </div>
            {rankLoading ? (
              <div className="p-8 text-center text-sm text-muted-foreground">Laden...</div>
            ) : rankings.length === 0 ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                Nog geen rankings beschikbaar. Draai de rankings-engine om deze lijst te vullen.
              </div>
            ) : (
              <TooltipProvider delayDuration={150}>
                <div className="divide-y max-h-[420px] overflow-y-auto">
                  {rankings.map((r: any) => {
                    const basis = r.evidence?.influence_basis;
                    const hist = rankHistory[r.competitor_name] || [];
                    const isOpen = openHistory === r.competitor_name;
                    return (
                      <div key={`${r.rank}-${r.competitor_name}`}>
                      <div className="grid grid-cols-12 items-center px-4 py-2.5 text-sm">
                        <div className="col-span-1 flex items-center gap-1 tabular-nums font-medium">
                          {r.rank}
                          {r.trend === "up" && (
                            <span className="flex items-center gap-0.5 text-emerald-600" title={`Gestegen: was #${r.previous_rank}`} data-testid={`rank-delta-${r.competitor_name}`}>
                              <TrendingUp className="h-3.5 w-3.5" />
                              <span className="text-[10px]">+{r.previous_rank - r.rank}</span>
                            </span>
                          )}
                          {r.trend === "down" && (
                            <span className="flex items-center gap-0.5 text-red-500" title={`Gedaald: was #${r.previous_rank}`} data-testid={`rank-delta-${r.competitor_name}`}>
                              <TrendingDown className="h-3.5 w-3.5" />
                              <span className="text-[10px]">-{r.rank - r.previous_rank}</span>
                            </span>
                          )}
                          {r.trend === "stable" && <Minus className="h-3.5 w-3.5 text-muted-foreground" />}
                          {r.trend === "new" && (
                            <span className="flex items-center gap-0.5 text-blue-500" title="Nieuw in de ranking" data-testid={`rank-delta-${r.competitor_name}`}>
                              <Sparkles className="h-3.5 w-3.5" />
                              <span className="text-[10px]">nieuw</span>
                            </span>
                          )}
                        </div>
                        <div className="col-span-4 flex items-center gap-2 min-w-0">
                          <Link href={`/competition/competitors/${encodeURIComponent(r.competitor_name)}`}>
                            <span className="font-medium truncate hover:underline cursor-pointer">{r.competitor_name}</span>
                          </Link>
                          {hist.length >= 2 && (
                            <button
                              type="button"
                              onClick={() => setOpenHistory(isOpen ? null : r.competitor_name)}
                              className="flex items-center gap-1 rounded px-1 py-0.5 hover:bg-muted"
                              title="Toon rank-verloop over eerdere runs"
                              data-testid={`button-rank-history-${r.competitor_name}`}
                            >
                              <RankSparkline points={hist} />
                            </button>
                          )}
                        </div>
                        <div className="col-span-2 text-right tabular-nums text-xs">
                          {((r.competition_relevance_score || 0) * 100).toFixed(0)}
                        </div>
                        <div className="col-span-2 text-right tabular-nums text-xs">
                          {((r.price_relevance_score || 0) * 100).toFixed(0)}
                        </div>
                        <div className="col-span-2 flex items-center justify-end gap-1.5">
                          <span className="tabular-nums text-xs">{((r.influence_score || 0) * 100).toFixed(0)}</span>
                          {basis === "profiel" && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-amber-500/10 text-amber-700 border-amber-300 cursor-help">
                                  profiel-baseline
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent side="left" className="max-w-xs text-xs">
                                {r.explanation || "Influence-score op basis van profiel; er is nog geen prijshistorie beschikbaar."}
                              </TooltipContent>
                            </Tooltip>
                          )}
                          {basis === "geen_data" && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-slate-100 text-slate-500 border-slate-200 cursor-help">
                                  geen data
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent side="left" className="max-w-xs text-xs">
                                {r.explanation || "Geen prijshistorie of profieldata beschikbaar voor de Influence-score."}
                              </TooltipContent>
                            </Tooltip>
                          )}
                          {basis === "prijshistorie" && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-emerald-500/10 text-emerald-700 border-emerald-300 cursor-help">
                                  prijshistorie
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent side="left" className="max-w-xs text-xs">
                                {r.explanation || "Influence-score op basis van werkelijke prijshistorie."}
                              </TooltipContent>
                            </Tooltip>
                          )}
                        </div>
                        <div className="col-span-1 text-right tabular-nums font-semibold">
                          {((r.combined_score || 0) * 100).toFixed(0)}
                        </div>
                      </div>
                      {isOpen && hist.length >= 2 && (
                        <div className="px-4 pb-3 bg-muted/30" data-testid={`panel-rank-history-${r.competitor_name}`}>
                          <div className="text-xs text-muted-foreground pt-2 pb-1.5">
                            Rank-verloop over de laatste {hist.length} runs (lager = beter)
                          </div>
                          <div className="flex flex-wrap gap-x-4 gap-y-1">
                            {hist.map((hp, i) => {
                              const prev = i > 0 ? hist[i - 1].rank : null;
                              const delta = prev !== null ? prev - hp.rank : 0;
                              return (
                                <div key={hp.run_date} className="flex items-center gap-1 text-xs tabular-nums">
                                  <span className="text-muted-foreground">{hp.run_date}</span>
                                  <span className="font-medium">#{hp.rank}</span>
                                  {prev !== null && delta > 0 && <TrendingUp className="h-3 w-3 text-emerald-600" />}
                                  {prev !== null && delta < 0 && <TrendingDown className="h-3 w-3 text-red-500" />}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      </div>
                    );
                  })}
                </div>
              </TooltipProvider>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Zoeken (categoriekeuze loopt via de globale hiërarchiefilter) */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Zoek concurrent of categorie..." className="pl-9" value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
        </div>
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
