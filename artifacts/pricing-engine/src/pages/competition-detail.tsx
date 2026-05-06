import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ReferenceLine
} from "recharts";
import { ArrowLeft, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";

const CLASS_COLORS: Record<string, string> = {
  Critical: "bg-red-500/15 text-red-700 border-red-300",
  Strong: "bg-orange-500/15 text-orange-700 border-orange-300",
  Influence: "bg-amber-500/15 text-amber-700 border-amber-300",
  Monitor: "bg-blue-500/15 text-blue-700 border-blue-300",
  Ignore: "bg-slate-100 text-slate-500 border-slate-200",
};

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.json());
}

const SUB_SCORE_LABELS: Record<string, string> = {
  product_comparability_score: "Comparability",
  price_sensitivity_score: "Price Sensitivity",
  substitution_score: "Substitution Risk",
  competitor_relevance_score: "Comp. Relevance",
  competitor_price_reliability_score: "Price Reliability",
  basket_dependency_score: "Basket Dependency",
  strategic_importance_score: "Strategic Importance",
};

const EXCLUSION_LABELS: Record<string, string> = {
  COMPETITOR_IGNORED_OUT_OF_STOCK: "Out of stock",
  COMPETITOR_IGNORED_BAD_MATCH: "Bad match confidence",
  COMPETITOR_IGNORED_OUTLIER: "Outlier price (>30% deviation)",
  COMPETITOR_IGNORED_LOW_RELEVANCE: "Low relevance",
  COMPETITOR_IGNORED_DIFFERENT_PACK_SIZE: "Different pack size",
  COMPETITOR_IGNORED_BAD_DELIVERY: "Unacceptable delivery",
};

export default function CompetitionDetail() {
  const params = useParams<{ sku_id: string }>();
  const skuId = params.sku_id;

  const { data, isLoading } = useQuery({
    queryKey: ["competition-detail", skuId],
    queryFn: () => apiFetch(`/api/competition/skus/${skuId}`),
    enabled: !!skuId,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  const { product, competition_score: score, competitor_detail } = data || {};

  if (!product || !score) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <p className="text-muted-foreground">No competition data found for <strong>{skuId}</strong>.</p>
        <Link href="/competition"><Button variant="outline"><ArrowLeft className="h-4 w-4 mr-2" />Back</Button></Link>
      </div>
    );
  }

  // Build sub-score list for bar chart and radar
  const subScores = Object.entries(SUB_SCORE_LABELS).map(([key, label]) => ({
    label,
    key,
    value: score[key] || 0,
  }));

  // Radar data
  const radarData = subScores.map((s) => ({
    subject: s.label,
    value: Math.round(s.value * 100),
    fullMark: 100,
  }));

  const included = (competitor_detail || []).filter((c: any) => !c.is_excluded);
  const excluded = (competitor_detail || []).filter((c: any) => c.is_excluded);

  const piColor =
    score.price_index > 1.03 ? "text-emerald-600" :
    score.price_index < 0.97 ? "text-red-600" : "text-foreground";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link href="/competition">
          <Button variant="ghost" size="sm" className="mt-1">
            <ArrowLeft className="h-4 w-4 mr-1" />Back
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{product.product_name}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
            <span>{product.sku_id}</span>
            <span>·</span>
            <span>{product.brand}</span>
            <span>·</span>
            <span>{product.category}</span>
            {product.is_a_brand && <Badge variant="outline" className="text-xs">A-Brand</Badge>}
            {product.is_private_label && <Badge variant="outline" className="text-xs">Private Label</Badge>}
          </div>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">PCIS Score</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{(score.pcis_score * 100).toFixed(0)}</div>
            <div className="mt-1">
              <Badge variant="outline" className={`text-xs ${CLASS_COLORS[score.competition_class] || ""}`}>
                {score.competition_class}
              </Badge>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Price Index</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-3xl font-bold ${piColor}`}>
              {score.price_index?.toFixed(3) ?? "—"}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {score.price_index > 1.03 ? "Priced above market" :
               score.price_index < 0.97 ? "Priced below market" : "At market level"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Own Price</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">€{product.current_price?.toFixed(2)}</div>
            <p className="text-xs text-muted-foreground mt-1">
              Ref: {score.reference_price ? `€${score.reference_price.toFixed(2)}` : "n/a"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Competitors</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{score.competitors_used}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {score.competitors_excluded} excluded
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Sub-scores + radar */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Bar chart sub-scores */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">PCIS Sub-Scores</CardTitle>
            <CardDescription>Seven weighted signals that make up the PCIS</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {subScores.map((s) => (
              <div key={s.key}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-muted-foreground">{s.label}</span>
                  <span className="font-medium tabular-nums">{(s.value * 100).toFixed(0)}</span>
                </div>
                <Progress
                  value={s.value * 100}
                  className="h-2"
                />
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Radar chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Score Radar</CardTitle>
            <CardDescription>Visual overview of all 7 dimensions</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radarData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
                <PolarGrid />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10 }} />
                <Radar
                  name="Score"
                  dataKey="value"
                  stroke="hsl(var(--primary))"
                  fill="hsl(var(--primary))"
                  fillOpacity={0.2}
                />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Competitor table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Competitor Price Detail</CardTitle>
          <CardDescription>
            Reference price: {score.reference_price ? `€${score.reference_price.toFixed(2)}` : "n/a"} (weighted median of included prices)
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="border-t">
            <div className="grid grid-cols-6 border-b bg-muted/50 px-4 py-2 text-xs font-medium text-muted-foreground">
              <div className="col-span-2">Competitor</div>
              <div className="text-right">Price</div>
              <div className="text-right">vs Own</div>
              <div className="text-right">vs Ref</div>
              <div className="text-right">Status</div>
            </div>
            {[...included, ...excluded].length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">No recent competitor data available.</div>
            ) : (
              <div className="divide-y">
                {[...included, ...excluded].map((c: any, i: number) => (
                  <div key={i} className={`grid grid-cols-6 items-center px-4 py-3 text-sm ${c.is_excluded ? "opacity-50 bg-muted/30" : ""}`}>
                    <div className="col-span-2 font-medium">{c.competitor_name}</div>
                    <div className="text-right tabular-nums">€{c.price?.toFixed(2) ?? "—"}</div>
                    <div className={`text-right tabular-nums text-xs font-medium ${
                      c.price_vs_own_pct > 0 ? "text-emerald-600" : c.price_vs_own_pct < 0 ? "text-red-600" : "text-muted-foreground"
                    }`}>
                      {c.price_vs_own_pct != null ? `${c.price_vs_own_pct > 0 ? "+" : ""}${c.price_vs_own_pct.toFixed(1)}%` : "—"}
                    </div>
                    <div className={`text-right tabular-nums text-xs font-medium ${
                      c.price_vs_reference_pct > 0 ? "text-emerald-600" : c.price_vs_reference_pct < 0 ? "text-red-600" : "text-muted-foreground"
                    }`}>
                      {c.price_vs_reference_pct != null ? `${c.price_vs_reference_pct > 0 ? "+" : ""}${c.price_vs_reference_pct.toFixed(1)}%` : "—"}
                    </div>
                    <div className="flex justify-end">
                      {c.is_excluded ? (
                        <span className="flex items-center gap-1 text-xs text-amber-600">
                          <XCircle className="h-3.5 w-3.5" />
                          {EXCLUSION_LABELS[c.exclusion_reason] || "Excluded"}
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-emerald-600">
                          <CheckCircle2 className="h-3.5 w-3.5" />Included
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Exclusion reasons summary */}
      {Object.keys(score.excluded_reasons || {}).length > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Competitor Exclusion Reasons
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {Object.entries(score.excluded_reasons || {}).map(([code, count]) => (
                <div key={code} className="flex items-center gap-2 text-sm">
                  <Badge variant="outline" className="bg-amber-100 text-amber-700 border-amber-300 text-xs">
                    {String(count)}×
                  </Badge>
                  <span className="text-muted-foreground">{EXCLUSION_LABELS[code] || code}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
