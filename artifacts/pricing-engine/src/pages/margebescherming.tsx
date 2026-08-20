import { useState, useEffect } from "react";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from "recharts";
import { Shield, AlertTriangle, TrendingDown, TrendingUp } from "lucide-react";
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

const ADVICE_NL: Record<string, string> = {
  FULL_PASS_THROUGH: "Volledig doorberekenen",
  PARTIAL_PASS_THROUGH: "Gedeeltelijk doorberekenen",
  NO_PASS_THROUGH: "Niet doorberekenen",
  TEST_PRICE_INCREASE: "Voorzichtig verhogen",
  PROTECT_MARGIN: "Marge beschermen",
  PUSH_TRAFFIC_INSTEAD: "Traffic verhogen",
  MAINTAIN_PRICE: "Prijs handhaven",
};

export default function Margebescherming() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [geselecteerd, setGeselecteerd] = useState<any>(null);
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);

  useEffect(() => {
    setLoading(true);
    const url = `${BASE}/api/margebescherming`;
    fetch(url + (fp !== "" ? (url.includes("?") ? "&" : "?") + fp : ""), { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [fp]);

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen margebeschermingsdata beschikbaar.</div>;

  const mpsBar = data.skus.slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    mps: parseFloat(((s.mps_score || 0) * 100).toFixed(1)),
    fill: s.mps_score >= 0.7 ? "#10b981" : s.mps_score >= 0.45 ? "#3b82f6" : s.mps_score >= 0.25 ? "#f59e0b" : "#ef4444",
  }));

  const verdelingData = Object.entries(data.aanbeveling_verdeling || {}).map(([k, v]: any) => ({
    name: ADVICE_NL[k] || k,
    count: v,
  }));

  const radarData = geselecteerd ? [
    { subject: "Marge", A: (geselecteerd.netto_marge_pct / 50) * 100 },
    { subject: "PPFS", A: geselecteerd.ppfs_score * 100 },
    { subject: "MPS", A: geselecteerd.mps_score * 100 },
    { subject: "Inkoopschok", A: Math.max(0, 100 - geselecteerd.inkoopwijziging_pct * 3) },
  ] : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Margebescherming Dashboard</h1>
      <GlobalFilterBar />

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's geanalyseerd", value: data.totaal_skus, icon: Shield, color: "text-primary" },
          { label: "Kritieke marge-SKU's", value: data.kritiek_count, icon: AlertTriangle, color: "text-red-600" },
          { label: "Beschermde SKU's", value: data.beschermd_count, icon: TrendingUp, color: "text-emerald-600" },
          { label: "Gem. netto marge", value: `${(data.gemiddelde_netto_marge || 0).toFixed(1)}%`, icon: TrendingDown, color: "text-blue-600" },
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
        {/* MPS grafiek */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Margin Protection Score (MPS) per SKU</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={mpsBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "MPS"]} />
              <Bar dataKey="mps" radius={[3, 3, 0, 0]}>
                {mpsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Aanbeveling verdeling */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Aanbeveling verdeling</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={verdelingData} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={140} />
              <Tooltip formatter={(v: any) => [v, "SKU's"]} />
              <Bar dataKey="count" fill="#3b82f6" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* SKU tabel */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30">
          <span className="text-sm font-semibold">Margebescherming per SKU</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr>
                {["SKU", "Product", "Categorie", "Inkoopwijziging", "Netto marge", "PPFS", "MPS", "Risico", "Advies", "Toelichting"].map(h => (
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
                  <td className="px-3 py-2 font-medium max-w-[150px] truncate">{s.naam}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{s.categorie}</td>
                  <td className="px-3 py-2 text-orange-600 font-semibold">+{s.inkoopwijziging_pct?.toFixed(1)}%</td>
                  <td className="px-3 py-2 tabular-nums">{s.netto_marge_pct?.toFixed(1)}%</td>
                  <td className="px-3 py-2">
                    <span className={`font-bold ${s.ppfs_score >= 0.7 ? "text-emerald-600" : s.ppfs_score >= 0.45 ? "text-blue-600" : "text-red-600"}`}>
                      {(s.ppfs_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`font-bold ${s.mps_score >= 0.7 ? "text-emerald-600" : s.mps_score >= 0.4 ? "text-yellow-600" : "text-red-600"}`}>
                      {(s.mps_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={`text-[10px] ${SEVERITY_COLORS[s.severity] || ""}`}>
                      {s.severity}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-xs">{ADVICE_NL[s.aanbeveling] || s.aanbeveling}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground max-w-[200px] truncate" title={s.reden_nl}>{s.reden_nl}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail radar */}
      {geselecteerd && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-card border rounded-lg p-5">
            <h3 className="font-semibold mb-1">{geselecteerd.naam}</h3>
            <p className="text-sm text-muted-foreground mb-4">{geselecteerd.reden_nl}</p>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Inkoopwijziging", value: `+${geselecteerd.inkoopwijziging_pct?.toFixed(1)}%` },
                { label: "Netto marge", value: `${geselecteerd.netto_marge_pct?.toFixed(1)}%` },
                { label: "PPFS doorberekening", value: `${(geselecteerd.ppfs_score * 100).toFixed(0)}%` },
                { label: "MPS margebescherming", value: `${(geselecteerd.mps_score * 100).toFixed(0)}%` },
              ].map((item, i) => (
                <div key={i} className="bg-muted/20 rounded p-2">
                  <div className="text-xs text-muted-foreground">{item.label}</div>
                  <div className="font-semibold">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-card border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-2">Score profiel</h3>
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                <Radar name="Score" dataKey="A" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
