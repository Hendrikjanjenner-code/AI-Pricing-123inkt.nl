import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TrendingUp, PackageX, Percent, Activity } from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  CartesianGrid, Legend, AreaChart, Area, ReferenceLine,
} from "recharts";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => {
    if (!r.ok) throw new Error(`API-fout (${r.status})`);
    return r.json();
  });
}

const EVENT_LABELS: Record<string, { label: string; cls: string }> = {
  PRICE_CHANGE: { label: "Prijswijziging", cls: "bg-blue-100 text-blue-700" },
  PROMO_START:  { label: "Promo gestart", cls: "bg-purple-100 text-purple-700" },
  PROMO_END:    { label: "Promo beëindigd", cls: "bg-slate-100 text-slate-700" },
};

const LINE_COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#be185d"];

export default function CompetitionTrends() {
  const [days, setDays] = useState("30");
  const [eventType, setEventType] = useState("all");

  const { data: priceTrend, isLoading: loadingTrend } = useQuery({
    queryKey: ["comp-trend-price-index", days],
    queryFn: () => apiFetch(`/api/competition/trends/price-index?days=${days}`),
  });
  const { data: coverage } = useQuery({
    queryKey: ["comp-coverage-latest"],
    queryFn: () => apiFetch("/api/competition/coverage"),
  });
  const { data: coverageTrend } = useQuery({
    queryKey: ["comp-coverage-trend"],
    queryFn: () => apiFetch("/api/competition/trends/coverage?days=90"),
  });
  const { data: availability } = useQuery({
    queryKey: ["comp-availability", days],
    queryFn: () => apiFetch(`/api/competition/availability?days=${days}`),
  });
  const { data: events } = useQuery({
    queryKey: ["comp-events", days, eventType],
    queryFn: () => apiFetch(
      `/api/competition/events?days=${days}${eventType !== "all" ? `&event_type=${eventType}` : ""}&page_size=100`),
  });

  const series = priceTrend?.series || [];
  const latest = series[series.length - 1];

  // Coverage: totaalregels
  const coverageTotals = (coverage?.items || []).filter((i: any) => i.category === null)
    .sort((a: any, b: any) => (b.coverage_pct || 0) - (a.coverage_pct || 0));

  // Coverage-trend naar chartdata (datum → {competitor: pct})
  const covComps = Object.keys(coverageTrend?.competitors || {});
  const covByDate: Record<string, any> = {};
  covComps.forEach(c => (coverageTrend.competitors[c] || []).forEach((p: any) => {
    covByDate[p.date] = { ...(covByDate[p.date] || { date: p.date }), [c]: p.coverage_pct };
  }));
  const covChart = Object.values(covByDate).sort((a: any, b: any) => a.date.localeCompare(b.date));

  // Beschikbaarheid naar chartdata
  const availComps = Object.keys(availability?.competitors || {});
  const availByDate: Record<string, any> = {};
  availComps.forEach(c => (availability.competitors[c] || []).forEach((p: any) => {
    availByDate[p.date] = {
      ...(availByDate[p.date] || { date: p.date }),
      [c]: p.in_stock_rate != null ? Math.round(p.in_stock_rate * 100) : null,
    };
  }));
  const availChart = Object.values(availByDate).sort((a: any, b: any) => a.date.localeCompare(b.date));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Concurrentietrends</h1>
          <p className="text-muted-foreground text-sm">
            Prijsindex, volatiliteit, dekking, beschikbaarheid en gedetecteerde events
          </p>
        </div>
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="14">14 dagen</SelectItem>
            <SelectItem value="30">30 dagen</SelectItem>
            <SelectItem value="90">90 dagen</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* KPI-kaarten */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium">Prijsindex (nu)</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">
              {latest ? latest.avg_price_index.toFixed(3) : "—"}
            </div>
            <p className="text-xs text-muted-foreground">&lt; 1.0 = wij zijn goedkoper</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium">Goedkoper dan markt</CardTitle>
            <Percent className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">
              {latest?.pct_cheaper != null ? `${latest.pct_cheaper}%` : "—"}
            </div>
            <p className="text-xs text-muted-foreground">aandeel waarnemingen</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium">Volatiliteit</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">
              {latest ? latest.volatility.toFixed(3) : "—"}
            </div>
            <p className="text-xs text-muted-foreground">variatiecoëfficiënt prijsindex</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium">Events ({days}d)</CardTitle>
            <PackageX className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">{events?.total ?? "—"}</div>
            <p className="text-xs text-muted-foreground">prijswijzigingen & promo's</p>
          </CardContent>
        </Card>
      </div>

      {/* Prijsindex + positie */}
      <Card>
        <CardHeader>
          <CardTitle>Prijsindex & positie</CardTitle>
          <CardDescription>Gemiddelde prijsindex (eigen prijs / concurrentprijs) en % waarnemingen waar wij goedkoper zijn</CardDescription>
        </CardHeader>
        <CardContent className="h-72">
          {loadingTrend ? <Skeleton className="h-full w-full" /> : series.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nog geen trenddata beschikbaar.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={11} />
                <YAxis yAxisId="idx" domain={["auto", "auto"]} fontSize={11} />
                <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} fontSize={11} unit="%" />
                <Tooltip />
                <Legend />
                <ReferenceLine yAxisId="idx" y={1} stroke="#94a3b8" strokeDasharray="4 4" />
                <Line yAxisId="idx" dataKey="avg_price_index" name="Prijsindex" stroke="#2563eb" dot={false} strokeWidth={2} />
                <Line yAxisId="pct" dataKey="pct_cheaper" name="% goedkoper" stroke="#059669" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Dekking */}
        <Card>
          <CardHeader>
            <CardTitle>Assortimentsdekking per concurrent</CardTitle>
            <CardDescription>
              Aandeel van ons assortiment dat de concurrent ook voert (uit AI-matches, afgekeurde matches uitgesloten)
              {coverage?.run_date ? ` — stand ${coverage.run_date}` : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {coverageTotals.length === 0 && (
              <p className="text-sm text-muted-foreground">Nog geen dekkingsdata — draai de competition-intelligence run.</p>
            )}
            {coverageTotals.map((c: any) => (
              <div key={c.competitor_name} className="flex items-center gap-3 text-sm">
                <span className="w-40 truncate">{c.competitor_name}</span>
                <div className="flex-1 h-2 rounded bg-muted overflow-hidden">
                  <div className="h-full bg-blue-600" style={{ width: `${Math.min(100, c.coverage_pct || 0)}%` }} />
                </div>
                <span className="w-24 text-right tabular-nums">
                  {c.matched_products}/{c.own_products} ({(c.coverage_pct || 0).toFixed(1)}%)
                </span>
              </div>
            ))}
            {covChart.length > 1 && (
              <div className="h-48 pt-2">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={covChart}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" fontSize={10} />
                    <YAxis fontSize={10} unit="%" />
                    <Tooltip />
                    {covComps.map((c, i) => (
                      <Line key={c} dataKey={c} stroke={LINE_COLORS[i % LINE_COLORS.length]} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Beschikbaarheid */}
        <Card>
          <CardHeader>
            <CardTitle>Beschikbaarheid concurrenten</CardTitle>
            <CardDescription>Dagelijks % van het gevolgde aanbod op voorraad</CardDescription>
          </CardHeader>
          <CardContent className="h-72">
            {availChart.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nog geen beschikbaarheidsdata.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={availChart}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" fontSize={10} />
                  <YAxis domain={[0, 100]} fontSize={10} unit="%" />
                  <Tooltip />
                  <Legend />
                  {availComps.map((c, i) => (
                    <Area key={c} dataKey={c} name={c} stroke={LINE_COLORS[i % LINE_COLORS.length]}
                          fill={LINE_COLORS[i % LINE_COLORS.length]} fillOpacity={0.08} />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Events */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Gedetecteerde events</CardTitle>
            <CardDescription>Prijswijzigingen en promoties van concurrenten</CardDescription>
          </div>
          <Select value={eventType} onValueChange={setEventType}>
            <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle events</SelectItem>
              <SelectItem value="PRICE_CHANGE">Prijswijzigingen</SelectItem>
              <SelectItem value="PROMO_START">Promo gestart</SelectItem>
              <SelectItem value="PROMO_END">Promo beëindigd</SelectItem>
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          {(events?.items || []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Geen events in deze periode.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3">Datum</th>
                    <th className="py-2 pr-3">Type</th>
                    <th className="py-2 pr-3">Product</th>
                    <th className="py-2 pr-3">Concurrent</th>
                    <th className="py-2 pr-3 text-right">Van</th>
                    <th className="py-2 pr-3 text-right">Naar</th>
                    <th className="py-2 pr-3 text-right">Δ%</th>
                  </tr>
                </thead>
                <tbody>
                  {events.items.map((e: any) => (
                    <tr key={e.id} className="border-b last:border-0">
                      <td className="py-2 pr-3 whitespace-nowrap">{e.event_date}</td>
                      <td className="py-2 pr-3">
                        <Badge variant="secondary" className={EVENT_LABELS[e.event_type]?.cls}>
                          {EVENT_LABELS[e.event_type]?.label || e.event_type}
                        </Badge>
                      </td>
                      <td className="py-2 pr-3 max-w-56 truncate">{e.product_name || e.sku_id}</td>
                      <td className="py-2 pr-3">{e.competitor_name}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {e.old_price != null ? `€${e.old_price.toFixed(2)}` : "—"}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {e.new_price != null ? `€${e.new_price.toFixed(2)}` : "—"}
                      </td>
                      <td className={`py-2 pr-3 text-right tabular-nums font-medium ${
                        (e.change_pct || 0) < 0 ? "text-red-600" : "text-emerald-600"}`}>
                        {e.change_pct != null ? `${e.change_pct > 0 ? "+" : ""}${e.change_pct.toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
