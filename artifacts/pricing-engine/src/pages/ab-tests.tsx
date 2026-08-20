import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { TrendingUp, TrendingDown, Activity, Percent, Users2 } from "lucide-react";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

function withFp(url: string, fp: string) {
  return url + (fp !== "" ? (url.includes("?") ? "&" : "?") + fp : "");
}

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

function DeltaBadge({ value, suffix = "" }: { value: number; suffix?: string }) {
  const positief = value >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-sm font-semibold ${positief ? "text-emerald-600" : "text-red-600"}`}>
      {positief ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
      {positief ? "+" : "-"}{Math.abs(value).toLocaleString("nl-NL", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}{suffix}
    </span>
  );
}

export default function AbTestMonitor() {
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);

  const { data: tests, isLoading: ladenTests } = useQuery({
    queryKey: ["ab-tests", fp],
    queryFn: () => apiFetch(withFp("/api/ab-tests", fp)),
  });

  const [geselecTestId, setGeselecTestId] = useState<number | null>(null);
  const testId = geselecTestId ?? (tests?.[0]?.id ?? null);

  const { data: detail, isLoading: ladenDetail } = useQuery({
    queryKey: ["ab-test-detail", testId, fp],
    queryFn: () => apiFetch(withFp(`/api/ab-tests/${testId}`, fp)),
    enabled: !!testId,
  });

  if (ladenTests) return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-3 gap-4">{[1,2,3].map(i => <Skeleton key={i} className="h-28" />)}</div>
      <Skeleton className="h-72" />
    </div>
  );

  const test = detail?.test;
  const samenvatting = detail?.summary;
  const categorieSplitsing: any[] = detail?.category_breakdown || [];
  const skuResultaten: any[] = detail?.sku_results || [];

  const vergelijking = [
    { maatstaf: "Omzet", AI: samenvatting?.ai_revenue_uplift ?? 0, Controle: samenvatting?.control_revenue_uplift ?? 0 },
    { maatstaf: "Marge", AI: samenvatting?.ai_margin_uplift ?? 0, Controle: samenvatting?.control_margin_uplift ?? 0 },
  ];

  const betrouwbaarheid = (samenvatting?.statistical_confidence ?? 0) * 100;
  const betrouwbaarheidLabel =
    betrouwbaarheid >= 90 ? "Hoge betrouwbaarheid" :
    betrouwbaarheid >= 70 ? "Gemiddelde betrouwbaarheid" :
    "Lage betrouwbaarheid";
  const betrouwbaarheidKleur =
    betrouwbaarheid >= 90 ? "text-emerald-600" :
    betrouwbaarheid >= 70 ? "text-amber-600" : "text-red-600";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">A/B-testmonitor</h1>
          <p className="text-muted-foreground mt-1">AI-pricing vs. statische controlegroep — prestaties.</p>
          <div className="mt-3"><GlobalFilterBar /></div>
        </div>
        {tests && tests.length > 1 && (
          <div className="flex gap-2">
            {tests.map((t: any) => (
              <button key={t.id} onClick={() => setGeselecTestId(t.id)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
                  (geselecTestId ?? tests[0].id) === t.id
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-card border-border text-muted-foreground hover:bg-muted"
                }`}>
                {t.name}
              </button>
            ))}
          </div>
        )}
      </div>

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
                  {test.status === "active" ? "Actief" : test.status}
                </Badge>
                <span>{test.start_date} → {test.end_date || "lopend"}</span>
                <span>{test.ai_group_sku_count + test.control_group_sku_count} SKU's totaal</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {ladenDetail ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : samenvatting && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Margeverbetering — AI</CardTitle>
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-emerald-600">+€{samenvatting.ai_margin_uplift.toFixed(0)}</div>
                <p className="text-xs text-muted-foreground mt-1">Controle: +€{samenvatting.control_margin_uplift.toFixed(0)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Omzetverbetering — AI</CardTitle>
                <Activity className="h-4 w-4 text-primary" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">+€{samenvatting.ai_revenue_uplift.toFixed(0)}</div>
                <p className="text-xs text-muted-foreground mt-1">Controle: +€{samenvatting.control_revenue_uplift.toFixed(0)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Conversieverbetering — AI</CardTitle>
                <Percent className="h-4 w-4 text-primary" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {samenvatting.ai_conversion_lift_pct >= 0 ? "+" : ""}{samenvatting.ai_conversion_lift_pct.toFixed(1)}%
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Controle: {samenvatting.control_conversion_lift_pct >= 0 ? "+" : ""}{samenvatting.control_conversion_lift_pct.toFixed(1)}%
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Statistische betrouwbaarheid</CardTitle>
                <Users2 className="h-4 w-4 text-primary" />
              </CardHeader>
              <CardContent>
                <div className={`text-2xl font-bold ${betrouwbaarheidKleur}`}>{betrouwbaarheid.toFixed(0)}%</div>
                <p className="text-xs text-muted-foreground mt-1">{betrouwbaarheidLabel}</p>
              </CardContent>
            </Card>
          </div>

          <Card className={betrouwbaarheid >= 90 ? "border-emerald-300" : betrouwbaarheid >= 70 ? "border-amber-300" : "border-red-200"}>
            <CardContent className="pt-4 pb-4">
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="font-medium">Statistische betrouwbaarheid</span>
                <span className={`font-bold ${betrouwbaarheidKleur}`}>{betrouwbaarheid.toFixed(1)}% · {betrouwbaarheidLabel}</span>
              </div>
              <Progress value={betrouwbaarheid} className="h-3" />
              <p className="text-xs text-muted-foreground mt-2">
                Op basis van margeverbeteringsvariantie per SKU over {samenvatting.ai_sku_count} AI- en {samenvatting.control_sku_count} controleSKU's.
              </p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Omzet- en margeverbeteringen</CardTitle>
                <CardDescription>Cumulatieve verbetering t.o.v. basislijn over 30 dagen (€)</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={vergelijking} barCategoryGap={30}>
                    <XAxis dataKey="maatstaf" />
                    <YAxis tickFormatter={v => `€${v.toFixed(0)}`} />
                    <Tooltip formatter={(v: number) => [`€${v.toFixed(2)}`, ""]} />
                    <Legend formatter={v => v === "AI" ? "AI" : "Controle"} />
                    <Bar dataKey="AI" fill="#10b981" radius={[4,4,0,0]} />
                    <Bar dataKey="Controle" fill="#94a3b8" radius={[4,4,0,0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Margeverbetering per categorie</CardTitle>
                <CardDescription>AI vs. Controle per categorie (€)</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={categorieSplitsing} layout="vertical" barCategoryGap={20}>
                    <XAxis type="number" tickFormatter={v => `€${v}`} tick={{ fontSize: 10 }} />
                    <YAxis type="category" dataKey="category" tick={{ fontSize: 10 }} width={90} />
                    <Tooltip formatter={(v: number) => [`€${v.toFixed(2)}`, ""]} />
                    <Legend formatter={v => v === "ai_margin_uplift" ? "AI" : "Controle"} />
                    <Bar dataKey="ai_margin_uplift" name="ai_margin_uplift" fill="#10b981" radius={[0,3,3,0]} />
                    <Bar dataKey="control_margin_uplift" name="control_margin_uplift" fill="#94a3b8" radius={[0,3,3,0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Resultaten per SKU</CardTitle>
              <CardDescription>Margeverbetering per SKU t.o.v. basislijn (30 dagen)</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <div className="border-t">
                <div className="grid grid-cols-10 border-b bg-muted/50 px-4 py-2 text-xs font-medium text-muted-foreground">
                  <div className="col-span-3">SKU / Product</div>
                  <div className="col-span-1">Groep</div>
                  <div className="text-right">Basisprijs</div>
                  <div className="text-right">Huidige prijs</div>
                  <div className="col-span-2 text-right">Margeverbetering</div>
                  <div className="col-span-2 text-right">Omzetverbetering</div>
                </div>
                <div className="divide-y max-h-[400px] overflow-y-auto">
                  {skuResultaten
                    .sort((a, b) => b.margin_uplift - a.margin_uplift)
                    .map((r: any) => (
                      <div key={r.id} className="grid grid-cols-10 items-center px-4 py-2.5 text-sm">
                        <div className="col-span-3">
                          <div className="font-medium truncate pr-2">{r.product_name}</div>
                          <div className="text-xs text-muted-foreground">{r.sku_id}</div>
                        </div>
                        <div className="col-span-1">
                          <Badge variant="outline" className={r.group_type === "AI"
                            ? "text-xs bg-emerald-50 text-emerald-700 border-emerald-300"
                            : "text-xs bg-slate-50 text-slate-600 border-slate-300"}>
                            {r.group_type === "AI" ? "AI" : "Controle"}
                          </Badge>
                        </div>
                        <div className="text-right tabular-nums text-xs text-muted-foreground">€{r.baseline_price?.toFixed(2)}</div>
                        <div className={`text-right tabular-nums text-xs font-medium ${r.current_price !== r.baseline_price ? "text-primary" : "text-muted-foreground"}`}>
                          €{r.current_price?.toFixed(2)}
                        </div>
                        <div className={`col-span-2 text-right tabular-nums text-sm font-semibold ${r.margin_uplift > 0 ? "text-emerald-600" : r.margin_uplift < 0 ? "text-red-600" : "text-muted-foreground"}`}>
                          {r.margin_uplift > 0 ? "+" : ""}€{r.margin_uplift.toFixed(2)}
                        </div>
                        <div className={`col-span-2 text-right tabular-nums text-xs ${r.revenue_uplift > 0 ? "text-emerald-600" : r.revenue_uplift < 0 ? "text-red-600" : "text-muted-foreground"}`}>
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
