import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp, Euro, AlertTriangle, RefreshCw } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";
import { longRunSignal } from "@/lib/fetch-timeout";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface SkuForecast {
  sku_id: string;
  naam: string;
  categorie: string | null;
  confidence: number;
  trend_pct: number;
  model_version: string | null;
  units?: number;
  units_laag?: number;
  units_hoog?: number;
  revenue?: number;
  margin?: number;
  stock?: number;
}

interface RisicoSignaal {
  id: number;
  type: string;
  severity: string;
  sku_id: string;
  naam: string | null;
  toelichting: string;
  actie: string | null;
  confidence: number;
}

interface Dashboard {
  run_date: string | null;
  horizon: number;
  totalen: {
    units?: number;
    revenue?: number;
    margin?: number;
    skus_met_forecast?: number;
    gem_confidence?: number;
  };
  skus: SkuForecast[];
  risico_signalen: RisicoSignaal[];
}

const SEV_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-blue-100 text-blue-800",
  info: "bg-slate-100 text-slate-800",
};

const RISK_LABELS: Record<string, string> = {
  stock_risk: "Voorraadrisico",
  demand_risk: "Vraagrisico",
  margin_risk: "Margerisico",
  competitor_risk: "Concurrentierisico",
  supplier_risk: "Leveranciersrisico",
};

const eur = (v: number | undefined) =>
  v == null ? "—" : new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(v);

export default function ForecastRisk() {
  const [horizon, setHorizon] = useState<30 | 90>(30);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery<Dashboard>({
    queryKey: ["forecast-dashboard", horizon],
    queryFn: async () => {
      const res = await fetch(`${BASE}/api/forecast/dashboard?horizon=${horizon}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Kon forecast niet laden");
      return res.json();
    },
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${BASE}/api/forecast/run`, { method: "POST", headers: getAuthHeaders(), signal: longRunSignal() });
      if (!res.ok) throw new Error("Run mislukt");
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["forecast-dashboard"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Forecast & Risk</h1>
          <p className="text-muted-foreground mt-1">
            Unit/omzet/marge/voorraad-forecasts met betrouwbaarheidsband en risicosignalen.
            {data?.run_date && <> Laatste run: {data.run_date}.</>}
          </p>
        </div>
        <div className="flex gap-2">
          <div className="flex rounded-md border overflow-hidden">
            {[30, 90].map((h) => (
              <button
                key={h}
                className={`px-3 py-1.5 text-sm ${horizon === h ? "bg-primary text-primary-foreground" : "bg-card"}`}
                onClick={() => setHorizon(h as 30 | 90)}
              >
                {h} dagen
              </button>
            ))}
          </div>
          <Button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
            <RefreshCw className={`w-4 h-4 mr-2 ${runMutation.isPending ? "animate-spin" : ""}`} />
            Herbereken
          </Button>
        </div>
      </div>

      {runMutation.isError && (
        <p className="text-sm text-destructive">Forecast-run mislukt. Probeer het opnieuw.</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <TrendingUp className="w-4 h-4 mr-2" /> Verwachte afzet
          </div>
          <div className="text-3xl font-bold">
            {isLoading ? <Skeleton className="h-8 w-16" /> : (data?.totalen?.units ?? 0).toLocaleString("nl-NL")}
          </div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Euro className="w-4 h-4 mr-2" /> Verwachte omzet
          </div>
          <div className="text-3xl font-bold">{isLoading ? <Skeleton className="h-8 w-24" /> : eur(data?.totalen?.revenue)}</div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Euro className="w-4 h-4 mr-2" /> Verwachte marge
          </div>
          <div className="text-3xl font-bold text-emerald-600">{isLoading ? <Skeleton className="h-8 w-24" /> : eur(data?.totalen?.margin)}</div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <AlertTriangle className="w-4 h-4 mr-2" /> Actieve risico's
          </div>
          <div className="text-3xl font-bold text-orange-600">
            {isLoading ? <Skeleton className="h-8 w-12" /> : data?.risico_signalen?.length ?? 0}
          </div>
        </div>
      </div>

      {!!data?.risico_signalen?.length && (
        <div className="border rounded-md bg-card p-4 space-y-3">
          <h2 className="font-semibold flex items-center">
            <AlertTriangle className="w-4 h-4 mr-2 text-orange-500" /> Risicosignalen
          </h2>
          {data.risico_signalen.map((r) => (
            <div key={r.id} className="flex items-start gap-3 border-b last:border-b-0 pb-3 last:pb-0">
              <Badge variant="secondary" className={SEV_COLORS[r.severity] || ""}>{r.severity}</Badge>
              <div className="flex-1">
                <div className="text-sm font-medium">
                  {RISK_LABELS[r.type] || r.type} — {r.naam || r.sku_id}
                </div>
                <div className="text-sm text-muted-foreground">{r.toelichting}</div>
                {r.actie && <div className="text-xs text-primary mt-1">Actie: {r.actie}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead className="text-right">Afzet ({horizon}d)</TableHead>
              <TableHead className="text-right">Bandbreedte</TableHead>
              <TableHead className="text-right">Omzet</TableHead>
              <TableHead className="text-right">Marge</TableHead>
              <TableHead className="text-right">Eindvoorraad</TableHead>
              <TableHead className="text-right">Trend/30d</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
              <TableHead>Model</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 9 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : !data?.skus?.length ? (
              <TableRow>
                <TableCell colSpan={9} className="h-32 text-center text-muted-foreground">
                  Geen forecasts. Zorg voor voldoende verkoophistorie en klik op Herbereken.
                </TableCell>
              </TableRow>
            ) : (
              data.skus.map((s) => (
                <TableRow key={s.sku_id}>
                  <TableCell>
                    <div className="font-medium">{s.naam}</div>
                    <div className="text-xs text-muted-foreground">{s.sku_id}</div>
                  </TableCell>
                  <TableCell className="text-right font-medium">{(s.units ?? 0).toLocaleString("nl-NL")}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {(s.units_laag ?? 0).toFixed(0)} – {(s.units_hoog ?? 0).toFixed(0)}
                  </TableCell>
                  <TableCell className="text-right">{eur(s.revenue)}</TableCell>
                  <TableCell className="text-right text-emerald-600">{eur(s.margin)}</TableCell>
                  <TableCell className={`text-right ${(s.stock ?? 0) < 0 ? "text-red-600 font-medium" : ""}`}>
                    {s.stock != null ? s.stock.toFixed(0) : "—"}
                  </TableCell>
                  <TableCell className={`text-right ${s.trend_pct < 0 ? "text-red-600" : "text-emerald-600"}`}>
                    {s.trend_pct > 0 ? "+" : ""}{s.trend_pct.toFixed(1)}%
                  </TableCell>
                  <TableCell className="text-right">{(s.confidence * 100).toFixed(0)}%</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{s.model_version || "—"}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
