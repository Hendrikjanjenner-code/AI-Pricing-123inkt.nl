import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { ArrowLeft, Circle, Globe, TrendingUp, ShoppingBag } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const TRAFFIC_LIGHT: Record<string, { color: string; label: string }> = {
  green:  { color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "Belangrijk" },
  orange: { color: "text-amber-600 bg-amber-50 border-amber-200",       label: "Monitoren" },
  red:    { color: "text-red-600 bg-red-50 border-red-200",             label: "Laag" },
};

const SCORE_LABELS = [
  { key: "relevance_score",           label: "Relevantie",    color: "#3b82f6" },
  { key: "coverage_index",            label: "Coverage",      color: "#10b981" },
  { key: "authority_score",           label: "Gezag",         color: "#8b5cf6" },
  { key: "pricing_relevance_score",   label: "Prijs",         color: "#f59e0b" },
  { key: "traffic_relevance_score",   label: "Traffic",       color: "#ef4444" },
  { key: "opportunity_score",         label: "Kans",          color: "#06b6d4" },
];

const STRATEGIE_LABELS: Record<string, string> = {
  EVERYDAY_LOW_PRICE:  "Altijd-Laagste-Prijs",
  PROMOTION_DRIVEN:    "Promotiegedreven",
  MARKET_SHARE_ATTACK: "Marktaandeeloffensief",
  MARGIN_PROTECTION:   "Margebescherming",
  INVENTORY_CLEARANCE: "Opruimingsstrategie",
  PRICE_FOLLOWER:      "Prijsvolger",
  PRICE_LEADER:        "Prijsleider",
};

export default function CompetitorDetail() {
  const { id: competitorName } = useParams<{ id: string }>();
  const name = decodeURIComponent(competitorName || "");

  const { data, isLoading } = useQuery({
    queryKey: ["competitor-detail", name],
    queryFn: () => apiFetch(`/api/competition/competitors/${encodeURIComponent(name)}`),
    enabled: !!name,
  });

  if (isLoading) return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-3 gap-4">{[1,2,3].map(i => <Skeleton key={i} className="h-28" />)}</div>
      <Skeleton className="h-64" />
    </div>
  );

  const { profile, category_scores, strategy } = data || {};
  if (!profile) return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <p className="text-muted-foreground">Geen profiel gevonden voor <strong>{name}</strong>.</p>
      <Link href="/competition/competitors"><Button variant="outline"><ArrowLeft className="h-4 w-4 mr-2" />Terug</Button></Link>
    </div>
  );

  const tl = TRAFFIC_LIGHT[profile.traffic_light || "orange"] || TRAFFIC_LIGHT.orange;

  // Radar data — top categorie scores
  const topCategory = (category_scores || [])[0];
  const radarData = topCategory ? SCORE_LABELS.map(s => ({
    label: s.label,
    value: topCategory[s.key] || 0,
    color: s.color,
  })) : [];

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <Link href="/competition/competitors">
          <Button variant="ghost" size="sm" className="mt-1"><ArrowLeft className="h-4 w-4 mr-1" /> Terug</Button>
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{profile.competitor_name}</h1>
            <Badge variant="outline" className={`text-xs ${tl.color}`}>
              <Circle className="h-2 w-2 mr-1 fill-current" />{tl.label}
            </Badge>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
            <Globe className="h-3.5 w-3.5" />{profile.domain}
            {profile.price_segment && <span className="ml-2 text-xs bg-muted px-2 py-0.5 rounded">{profile.price_segment}</span>}
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Assortiment</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{profile.assortment_size}</div><p className="text-xs text-muted-foreground">{profile.category_breadth} categorieën</p></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Functionele Overlap</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{Math.round((profile.functional_overlap_score || 0) * 100)}%</div><p className="text-xs text-muted-foreground">met ons assortiment</p></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Prijswijzigingen</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{profile.price_change_frequency?.toFixed(1)}/week</div><p className="text-xs text-muted-foreground">Laatste: {profile.last_price_change_date || "—"}</p></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Voorraadbetrouwbaarheid</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{Math.round((profile.in_stock_rate || 0) * 100)}%</div><p className="text-xs text-muted-foreground">gem. leveringstijd {profile.avg_delivery_days?.toFixed(1)} d</p></CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Categoriescores */}
        <Card>
          <CardHeader><CardTitle className="text-base">Categoryscores</CardTitle>
            <CardDescription>7 relevantie-dimensies per categorie (0–100)</CardDescription></CardHeader>
          <CardContent>
            {(category_scores || []).length === 0 ? (
              <p className="text-sm text-muted-foreground">Geen categoryscores beschikbaar.</p>
            ) : (
              <div className="space-y-4">
                {(category_scores || []).slice(0, 3).map((cs: any) => (
                  <div key={cs.category}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-sm">{cs.category}</span>
                      <Badge variant="outline" className={`text-xs ${
                        cs.traffic_light === "green" ? "border-emerald-200 text-emerald-700" :
                        cs.traffic_light === "orange" ? "border-amber-200 text-amber-700" :
                        "border-red-200 text-red-600"
                      }`}>{cs.combined_score?.toFixed(0)}/100</Badge>
                    </div>
                    <div className="space-y-1">
                      {SCORE_LABELS.slice(0, 4).map(sl => (
                        <div key={sl.key} className="flex items-center gap-2 text-xs">
                          <span className="w-20 text-muted-foreground shrink-0">{sl.label}</span>
                          <Progress value={cs[sl.key] || 0} className="h-1.5 flex-1" />
                          <span className="w-6 text-right tabular-nums">{(cs[sl.key] || 0).toFixed(0)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Strategie */}
        <Card>
          <CardHeader><CardTitle className="text-base">Strategie-herkenning</CardTitle>
            <CardDescription>Automatisch herkende prijsstrategie</CardDescription></CardHeader>
          <CardContent>
            {!strategy ? (
              <p className="text-sm text-muted-foreground">Geen strategie-data beschikbaar.</p>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-bold">{strategy.strategy_label_nl || STRATEGIE_LABELS[strategy.strategy_type] || strategy.strategy_type}</span>
                  <Badge variant="outline">{Math.round((strategy.confidence || 0) * 100)}% confidence</Badge>
                </div>
                {strategy.strategy_changed && strategy.previous_strategy_type && (
                  <div className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded p-2">
                    ⚡ Strategie gewijzigd van <strong>{STRATEGIE_LABELS[strategy.previous_strategy_type] || strategy.previous_strategy_type}</strong>
                  </div>
                )}
                <p className="text-sm text-muted-foreground">{strategy.explanation_nl}</p>
                <div className="bg-muted/50 rounded p-3">
                  <p className="text-xs font-medium mb-1">Aanbevolen reactie:</p>
                  <p className="text-sm">{strategy.recommended_action_nl}</p>
                </div>
                <div className="text-xs text-muted-foreground">Analyse periode: {strategy.period_days} dagen · {strategy.data_points} datapunten</div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top merken + categorieën */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle className="text-base">Top Merken</CardTitle></CardHeader>
          <CardContent>
            {(profile.top_brands || []).length === 0 ? (
              <p className="text-sm text-muted-foreground">Geen merkdata beschikbaar.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(profile.top_brands || []).map((b: string, i: number) => (
                  <div key={b} className="flex items-center gap-2 bg-muted rounded-full px-3 py-1 text-sm">
                    <ShoppingBag className="h-3.5 w-3.5 text-muted-foreground" />
                    {b}
                    {i === 0 && <Badge className="ml-1 text-xs h-4" variant="secondary">#1</Badge>}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Prijssegment-verdeling</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-muted-foreground">Budget</span>
                  <span>{Math.round((profile.budget_share_pct || 0) * 100)}%</span>
                </div>
                <Progress value={(profile.budget_share_pct || 0) * 100} className="h-2" />
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-muted-foreground">Midden</span>
                  <span>{Math.round(100 - (profile.premium_share_pct || 0) * 100 - (profile.budget_share_pct || 0) * 100)}%</span>
                </div>
                <Progress value={100 - (profile.premium_share_pct || 0) * 100 - (profile.budget_share_pct || 0) * 100} className="h-2" />
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-muted-foreground">Premium</span>
                  <span>{Math.round((profile.premium_share_pct || 0) * 100)}%</span>
                </div>
                <Progress value={(profile.premium_share_pct || 0) * 100} className="h-2" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
