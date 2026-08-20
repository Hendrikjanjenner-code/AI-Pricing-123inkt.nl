import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { AlertTriangle, TrendingUp, TrendingDown, Shield, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const SEVERITY_COLORS: Record<string, string> = {
  KRITIEK: "text-red-600 bg-red-50 border-red-200",
  HOOG: "text-orange-600 bg-orange-50 border-orange-200",
  MEDIUM: "text-yellow-600 bg-yellow-50 border-yellow-200",
  LAAG: "text-emerald-600 bg-emerald-50 border-emerald-200",
};

const ADVICE_LABELS: Record<string, string> = {
  FULL_PASS_THROUGH: "Volledig doorberekenen",
  PARTIAL_PASS_THROUGH: "Gedeeltelijk doorberekenen",
  NO_PASS_THROUGH: "Niet doorberekenen",
  TEST_PRICE_INCREASE: "Voorzichtig testen",
  PROTECT_MARGIN: "Marge beschermen",
  PUSH_TRAFFIC_INSTEAD: "Traffic verhogen",
};

export default function KostprijswijzigingDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [geselecteerd, setGeselecteerd] = useState<any>(null);
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);

  useEffect(() => {
    setLoading(true);
    const url = `${BASE}/api/kostprijswijziging`;
    fetch(url + (fp !== "" ? (url.includes("?") ? "&" : "?") + fp : ""), { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [fp]);

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen kostprijswijzigingen beschikbaar.</div>;

  const barData = data.skus.slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    wijziging: parseFloat(s.wijziging_pct.toFixed(1)),
    fill: s.wijziging_pct >= 15 ? "#ef4444" : s.wijziging_pct >= 8 ? "#f97316" : "#eab308",
  }));

  const ppfsBar = data.skus.slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    ppfs: parseFloat((s.ppfs_score * 100).toFixed(1)),
    fill: s.ppfs_score >= 0.75 ? "#10b981" : s.ppfs_score >= 0.50 ? "#3b82f6" : s.ppfs_score >= 0.35 ? "#f59e0b" : "#ef4444",
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Inkoopprijswijziging Analyse</h1>
      <GlobalFilterBar />

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's geanalyseerd", value: data.totaal_skus, icon: Shield, color: "text-blue-600" },
          { label: "Kritiek risico", value: data.kritiek_count, icon: AlertTriangle, color: "text-red-600" },
          { label: "Volledig doorberekenen", value: data.vol_doorberekenen_count, icon: TrendingUp, color: "text-emerald-600" },
          { label: "Gem. PPFS score", value: `${(data.gemiddelde_ppfs * 100).toFixed(0)}%`, icon: TrendingDown, color: "text-primary" },
        ].map((kpi, i) => (
          <div key={i} className="bg-card border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <kpi.icon className={`w-4 h-4 ${kpi.color}`} />
              <span className="text-xs text-muted-foreground">{kpi.label}</span>
            </div>
            <div className={`text-2xl font-bold ${kpi.color}`}>{kpi.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Grafiek: kostprijswijziging */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Inkoopprijswijziging per SKU (%)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={barData}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "Wijziging"]} />
              <Bar dataKey="wijziging" radius={[3, 3, 0, 0]}>
                {barData.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Grafiek: PPFS score */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Doorberekenbaarheid PPFS (%)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={ppfsBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "PPFS"]} />
              <Bar dataKey="ppfs" radius={[3, 3, 0, 0]}>
                {ppfsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* SKU tabel */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30">
          <span className="text-sm font-semibold">SKU Overzicht — Kostprijswijzigingen</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr>
                {["SKU-ID", "Product", "Categorie", "Inkoopprijs oud", "Inkoopprijs nieuw", "Wijziging", "Netto marge", "PPFS", "MPS", "Risico", "Advies"].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.skus.map((s: any) => (
                <tr key={s.sku_id}
                  className={`border-t cursor-pointer hover:bg-muted/30 transition-colors ${geselecteerd?.sku_id === s.sku_id ? "bg-primary/5" : ""}`}
                  onClick={() => setGeselecteerd(geselecteerd?.sku_id === s.sku_id ? null : s)}
                >
                  <td className="px-3 py-2 font-mono text-xs">{s.sku_id}</td>
                  <td className="px-3 py-2 font-medium max-w-[160px] truncate" title={s.naam}>{s.naam}</td>
                  <td className="px-3 py-2 text-muted-foreground text-xs">{s.categorie}</td>
                  <td className="px-3 py-2 tabular-nums">€{s.inkoopprijs_oud.toFixed(2)}</td>
                  <td className="px-3 py-2 tabular-nums font-medium">€{s.inkoopprijs_nieuw.toFixed(2)}</td>
                  <td className="px-3 py-2">
                    <span className={`flex items-center gap-1 font-semibold tabular-nums ${s.wijziging_pct >= 0 ? "text-red-600" : "text-emerald-600"}`}>
                      {s.wijziging_pct >= 0 ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                      {Math.abs(s.wijziging_pct).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-3 py-2 tabular-nums">{s.netto_marge.toFixed(1)}%</td>
                  <td className="px-3 py-2">
                    <span className={`font-semibold ${s.ppfs_score >= 0.7 ? "text-emerald-600" : s.ppfs_score >= 0.45 ? "text-blue-600" : "text-red-600"}`}>
                      {(s.ppfs_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`font-semibold ${s.mps_score >= 0.6 ? "text-emerald-600" : s.mps_score >= 0.35 ? "text-yellow-600" : "text-red-600"}`}>
                      {(s.mps_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={`text-[10px] ${SEVERITY_COLORS[s.severity] || ""}`}>
                      {s.severity}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className="text-[10px]">
                      {ADVICE_LABELS[s.aanbeveling] || s.aanbeveling}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail panel */}
      {geselecteerd && (
        <div className="bg-card border rounded-lg p-5 space-y-2">
          <h3 className="font-semibold">{geselecteerd.naam} <span className="text-muted-foreground font-normal text-sm">— {geselecteerd.sku_id}</span></h3>
          <p className="text-sm text-muted-foreground">{geselecteerd.reden_nl}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
            {[
              { label: "Inkoopprijswijziging", value: `+${geselecteerd.wijziging_pct?.toFixed(1)}%` },
              { label: "PPFS (doorbereken.)", value: `${(geselecteerd.ppfs_score * 100).toFixed(0)}%` },
              { label: "MPS (margebescherming)", value: `${(geselecteerd.mps_score * 100).toFixed(0)}%` },
              { label: "Netto marge", value: `${geselecteerd.netto_marge?.toFixed(1)}%` },
            ].map((item, i) => (
              <div key={i} className="bg-muted/20 rounded p-2">
                <div className="text-xs text-muted-foreground">{item.label}</div>
                <div className="font-semibold">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
