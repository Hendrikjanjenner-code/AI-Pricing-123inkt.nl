import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, Cell
} from "recharts";
import { TrendingUp, TrendingDown, Activity, Percent, Users2 } from "lucide-react";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.json());
}

const fmt = (v: number, prefix = "€") =>
  `${prefix}${Math.abs(v).toLocaleString("en-EU", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

function DeltaBadge({ value, suffix = "" }: { value: number; suffix?: string }) {
  const positive = value >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-sm font-semibold ${positive ? "text-emerald-600" : "text-red-600"}`}>
      {positive ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
      {positive ? "+" : "-"}{fmt(value, "")}
      {suffix}
    </span>
  );
}

export default function AbTests() {
  const { data: tests, isLoading: loadingTests } = useQuery({
    queryKey: ["ab-tests"],
    queryFn: () => apiFetch("/api/ab-tests"),
  });

  const [selectedTestId, setSelectedTestId] = useState<number | null>(null);

  const testId = selectedTestId ?? (tests?.[0]?.id ?? null);

  const { data: detail, isLoading: loadingDetail } = useQuery({
    queryKey: ["ab-test-detail", testId],
    queryFn: () => apiFetch(`/api/ab-tests/${testId}`),
    enabled: !!testId,
  });

  if (loadingTests) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-3 gap-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>
        <Skeleton className="h-72" />
      </div>
    );
  }

  const test = detail?.test;
  const summary = detail?.summary;
  const catBreakdown: any[] = detail?.category_breakdown || [];
  const skuResults: any[] = detail?.sku_results || [];

  // Data for the comparison bar chart
  const comparisonData = [
    {
      metric: "Revenue",
      AI: summary?.ai_revenue_uplift ?? 0,
      Control: summary?.control_revenue_uplift ?? 0,
    },
    {
      metric: "Margin",
      AI: summary?.ai_margin_uplift ?? 0,
      Control: summary?.control_margin_uplift ?? 0,
    },
  ];

  const convData = [
    { metric: "Conversion Lift", AI: summary?.ai_conversion_lift_pct ?? 0, Control: summary?.control_conversion_lift_pct ?? 0 },
  ];

  const confidence = (summary?.statistical_confidence ?? 0) * 100;
  const confidenceLabel =
    confidence >= 90 ? "High confidence" :
    confidence >= 70 ? "Moderate confidence" :
    "Low confidence";
  const confidenceColor =
    confidence >= 90 ? "text-emerald-600" :
    confidence >= 70 ? "text-amber-600" : "text-red-600";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">A/B Test Monitor</h1>
          <p className="text-muted-foreground mt-1">AI pricing vs. static control group performance.</p>
        </div>
        {tests && tests.length > 1 && (
          <div className="flex gap-2">
            {tests.map((t: any) => (
              <button
                key={t.id}
                onClick={() => setSelectedTestId(t.id)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
                  (selectedTestId ?? tests[0].id) === t.id
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-card border-border text-muted-foreground hover:bg-muted"
                }`}
              >
                {t.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Test header */}
      {test && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="pt-5">
            <div className="flex items-start justify-between flex-wrap gap-4">
              <div>
                <h2 className="font-semibold text-base">{test.name}</h2>
                <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{test.description}</p>
              </div>
              <div className="flex flex-col items-end gap-1 text-sm text-muted-foreground">
                <Badge variant="outline" className={test.status === "active" ? "border-emerald-300 text-emerald-600 bg-emerald-50" : ""}>
                  {test.status}
                </Badge>
                <span>{test.start_date} → {test.end_date || "ongoing"}</span>
                <span>{test.ai_group_sku_count + test.control_group_sku_count} total SKUs</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {loadingDetail ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : summary && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Margin Uplift — AI</CardTitle>
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-emerald-600">+€{summary.ai_margin_uplift.toFixed(0)}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Control: +€{summary.control_margin_uplift.toFixed(0)}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Revenue Uplift — AI</CardTitle>
                <Activity className="h-4 w-4 text-primary" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">+€{summary.ai_revenue_uplift.toFixed(0)}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Control: +€{summary.control_revenue_uplift.toFixed(0)}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Conversion Lift — AI</CardTitle>
                <Percent className="h-4 w-4 text-primary" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {summary.ai_conversion_lift_pct >= 0 ? "+" : ""}{summary.ai_conversion_lift_pct.toFixed(1)}%
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Control: {summary.control_conversion_lift_pct >= 0 ? "+" : ""}{summary.control_conversion_lift_pct.toFixed(1)}%
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Statistical Confidence</CardTitle>
                <Users2 className="h-4 w-4 text-primary" />
              </CardHeader>
              <CardContent>
                <div className={`text-2xl font-bold ${confidenceColor}`}>{confidence.toFixed(0)}%</div>
                <p className="text-xs text-muted-foreground mt-1">{confidenceLabel}</p>
              </CardContent>
            </Card>
          </div>

          {/* Confidence bar */}
          <Card className={confidence >= 90 ? "border-emerald-300" : confidence >= 70 ? "border-amber-300" : "border-red-200"}>
            <CardContent className="pt-4 pb-4">
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="font-medium">Statistical Confidence</span>
                <span className={`font-bold ${confidenceColor}`}>{confidence.toFixed(1)}% · {confidenceLabel}</span>
              </div>
              <Progress value={confidence} className="h-3" />
              <p className="text-xs text-muted-foreground mt-2">
                Based on per-SKU margin uplift variance across {summary.ai_sku_count} AI and {summary.control_sku_count} control SKUs.
              </p>
            </CardContent>
          </Card>

          {/* Charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Revenue & Margin Uplift</CardTitle>
                <CardDescription>30-day cumulative uplift vs. baseline (€)</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={comparisonData} barCategoryGap={30}>
                    <XAxis dataKey="metric" />
                    <YAxis tickFormatter={(v) => `€${v.toFixed(0)}`} />
                    <Tooltip formatter={(v: number) => [`€${v.toFixed(2)}`, ""]} />
                    <Legend />
                    <Bar dataKey="AI" fill="#10b981" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Control" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Margin Uplift by Category</CardTitle>
                <CardDescription>AI vs Control per category (€)</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={catBreakdown} layout="vertical" barCategoryGap={20}>
                    <XAxis type="number" tickFormatter={(v) => `€${v}`} tick={{ fontSize: 10 }} />
                    <YAxis type="category" dataKey="category" tick={{ fontSize: 10 }} width={90} />
                    <Tooltip formatter={(v: number) => [`€${v.toFixed(2)}`, ""]} />
                    <Legend />
                    <Bar dataKey="ai_margin_uplift" name="AI" fill="#10b981" radius={[0, 3, 3, 0]} />
                    <Bar dataKey="control_margin_uplift" name="Control" fill="#94a3b8" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          {/* SKU results table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Per-SKU Results</CardTitle>
              <CardDescription>30-day margin and revenue uplift vs. baseline per SKU</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <div className="border-t">
                <div className="grid grid-cols-10 border-b bg-muted/50 px-4 py-2 text-xs font-medium text-muted-foreground">
                  <div className="col-span-3">SKU / Product</div>
                  <div className="col-span-1">Group</div>
                  <div className="text-right">Baseline P</div>
                  <div className="text-right">Current P</div>
                  <div className="col-span-2 text-right">Margin Uplift</div>
                  <div className="col-span-2 text-right">Revenue Uplift</div>
                </div>
                <div className="divide-y max-h-[400px] overflow-y-auto">
                  {skuResults
                    .sort((a, b) => b.margin_uplift - a.margin_uplift)
                    .map((r: any) => (
                      <div key={r.id} className="grid grid-cols-10 items-center px-4 py-2.5 text-sm">
                        <div className="col-span-3">
                          <div className="font-medium truncate pr-2">{r.product_name}</div>
                          <div className="text-xs text-muted-foreground">{r.sku_id}</div>
                        </div>
                        <div className="col-span-1">
                          <Badge
                            variant="outline"
                            className={r.group_type === "AI"
                              ? "text-xs bg-emerald-50 text-emerald-700 border-emerald-300"
                              : "text-xs bg-slate-50 text-slate-600 border-slate-300"}
                          >
                            {r.group_type}
                          </Badge>
                        </div>
                        <div className="text-right tabular-nums text-xs text-muted-foreground">
                          €{r.baseline_price?.toFixed(2)}
                        </div>
                        <div className={`text-right tabular-nums text-xs font-medium ${
                          r.current_price !== r.baseline_price ? "text-primary" : "text-muted-foreground"
                        }`}>
                          €{r.current_price?.toFixed(2)}
                        </div>
                        <div className={`col-span-2 text-right tabular-nums text-sm font-semibold ${
                          r.margin_uplift > 0 ? "text-emerald-600" : r.margin_uplift < 0 ? "text-red-600" : "text-muted-foreground"
                        }`}>
                          {r.margin_uplift > 0 ? "+" : ""}{r.margin_uplift >= 0 ? "" : "-"}€{Math.abs(r.margin_uplift).toFixed(2)}
                        </div>
                        <div className={`col-span-2 text-right tabular-nums text-xs ${
                          r.revenue_uplift > 0 ? "text-emerald-600" : r.revenue_uplift < 0 ? "text-red-600" : "text-muted-foreground"
                        }`}>
                          {r.revenue_uplift > 0 ? "+" : ""}€{r.revenue_uplift.toFixed(2)}
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
