import { useState, useEffect } from "react";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell, PolarRadiusAxis } from "recharts";
import { Layers, Shield, TrendingUp, AlertTriangle, Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { InfoTooltip } from "@/components/InfoTooltip";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const SEVS_COLORS: Record<string, string> = {
  KRITIEK: "text-red-600 bg-red-50 border-red-200",
  HOOG:    "text-orange-600 bg-orange-50 border-orange-200",
  MEDIUM:  "text-blue-600 bg-blue-50 border-blue-200",
  LAAG:    "text-slate-500 bg-slate-50 border-slate-200",
};

const ROL_LABELS: Record<string, string> = {
  TRAFFIC_DRIVER:       "Traffic Driver",
  BASKET_BUILDER:       "Winkelmandvuller",
  MARGIN_DRIVER:        "Margebijdrager",
  RETENTION_DRIVER:     "Retentie Driver",
  PORTFOLIO_DRIVER:     "Portfolio Driver",
  PRIVATE_LABEL_DRIVER: "Huismerk Driver",
};

const ROL_COLORS: Record<string, string> = {
  TRAFFIC_DRIVER:       "bg-blue-100 text-blue-700 border-blue-200",
  BASKET_BUILDER:       "bg-emerald-100 text-emerald-700 border-emerald-200",
  MARGIN_DRIVER:        "bg-orange-100 text-orange-700 border-orange-200",
  RETENTION_DRIVER:     "bg-purple-100 text-purple-700 border-purple-200",
  PORTFOLIO_DRIVER:     "bg-yellow-100 text-yellow-700 border-yellow-200",
  PRIVATE_LABEL_DRIVER: "bg-pink-100 text-pink-700 border-pink-200",
};

export default function SkuEcosysteem() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [geselecteerd, setGeselecteerd] = useState<any>(null);

  useEffect(() => {
    fetch(`${BASE}/api/sku-ecosystem`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen ecosysteem data beschikbaar.</div>;

  const sevsBar = data.skus.slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    sevs: parseFloat((s.ecosystem_value_score * 100).toFixed(1)),
    fill: s.ecosystem_value_score >= 0.72 ? "#ef4444" : s.ecosystem_value_score >= 0.52 ? "#f97316" : s.ecosystem_value_score >= 0.32 ? "#3b82f6" : "#94a3b8",
  }));

  const rolVerdeling = Object.entries(data.rol_verdeling || {}).map(([k, v]: any) => ({
    name: ROL_LABELS[k] || k,
    count: v,
  }));

  const radarData = geselecteerd ? [
    { subject: "Traffic", A: geselecteerd.traffic_driver_score * 100 },
    { subject: "Basket", A: geselecteerd.basket_builder_score * 100 },
    { subject: "Marge", A: geselecteerd.margin_amplification_score * 100 },
    { subject: "Entry", A: geselecteerd.entry_product_score * 100 },
    { subject: "Repeat", A: geselecteerd.repeat_contribution_score * 100 },
    { subject: "Huismerk", A: geselecteerd.private_label_contribution * 100 },
  ] : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          SKU Ecosysteem Dashboard
          <InfoTooltip definitieId="sevs" />
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Totale commerciële waarde per SKU — niet alleen directe marge, maar ook traffic, basket, repeat en cross-sell bijdrage.
        </p>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's geanalyseerd", value: data.totaal_skus, icon: Layers, color: "text-primary" },
          { label: "Strategisch kritiek", value: data.kritiek_count, icon: Shield, color: "text-red-600" },
          { label: "Lage ecosysteemwaarde", value: data.laag_count, icon: AlertTriangle, color: "text-slate-500" },
          { label: "Gem. SEVS score", value: `${((data.gemiddelde_sevs || 0) * 100).toFixed(0)}%`, icon: Star, color: "text-orange-600" },
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* SEVS bar */}
        <div className="lg:col-span-2 bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">SKU Ecosystem Value Score (SEVS)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={sevsBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "SEVS"]} />
              <Bar dataKey="sevs" radius={[3, 3, 0, 0]}>
                {sevsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Rolverdeling */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">SKU-rol verdeling</h3>
          <div className="space-y-2">
            {rolVerdeling.map((item) => (
              <div key={item.name} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{item.name}</span>
                <span className="font-semibold">{item.count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* SKU tabel */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30">
          <span className="text-sm font-semibold">SKU Ecosysteem Ranking (klik voor detail)</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr>
                {["SKU", "Product", "TDS", "BBS", "MAS", "EPS", "Repeat", "Huismerk", "SEVS", "Label", "Primaire rol", "Advies"].map(h => (
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
                  {[
                    s.traffic_driver_score, s.basket_builder_score, s.margin_amplification_score,
                    s.entry_product_score, s.repeat_contribution_score, s.private_label_contribution,
                  ].map((score, i) => (
                    <td key={i} className="px-3 py-2">
                      <span className={`text-xs font-medium ${score >= 0.65 ? "text-emerald-600" : score >= 0.40 ? "text-blue-600" : "text-muted-foreground"}`}>
                        {(score * 100).toFixed(0)}%
                      </span>
                    </td>
                  ))}
                  <td className="px-3 py-2">
                    <span className={`font-bold ${s.ecosystem_value_score >= 0.72 ? "text-red-600" : s.ecosystem_value_score >= 0.52 ? "text-orange-600" : s.ecosystem_value_score >= 0.32 ? "text-blue-600" : "text-slate-500"}`}>
                      {(s.ecosystem_value_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={`text-[10px] ${SEVS_COLORS[s.sevs_label] || ""}`}>{s.sevs_label}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={`text-[10px] ${ROL_COLORS[s.primaire_rol] || ""}`}>
                      {ROL_LABELS[s.primaire_rol] || s.primaire_rol}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{s.bescherming_advies?.replace(/_/g, " ").toLowerCase()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail: radar + uitleg */}
      {geselecteerd && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-card border rounded-lg p-5">
            <h3 className="font-semibold mb-1">{geselecteerd.naam}</h3>
            <p className="text-sm text-muted-foreground mb-4">{geselecteerd.strategische_noot}</p>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "SEVS", value: `${(geselecteerd.ecosystem_value_score * 100).toFixed(0)}%` },
                { label: "Traffic Driver", value: `${(geselecteerd.traffic_driver_score * 100).toFixed(0)}%` },
                { label: "Winkelmandvuller", value: `${(geselecteerd.basket_builder_score * 100).toFixed(0)}%` },
                { label: "Herhaalaankoop", value: `${(geselecteerd.repeat_contribution_score * 100).toFixed(0)}%` },
                { label: "Pricing gevoeligheid", value: geselecteerd.pricing_gevoeligheid },
                { label: "Bescherming advies", value: geselecteerd.bescherming_advies?.replace(/_/g, " ") },
              ].map((item, i) => (
                <div key={i} className="bg-muted/20 rounded p-2">
                  <div className="text-xs text-muted-foreground">{item.label}</div>
                  <div className="font-semibold text-sm">{item.value}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {[geselecteerd.primaire_rol, ...(geselecteerd.secundaire_rollen || [])].filter(Boolean).map((rol: string) => (
                <Badge key={rol} variant="outline" className={`text-xs ${ROL_COLORS[rol] || ""}`}>
                  {ROL_LABELS[rol] || rol}
                </Badge>
              ))}
            </div>
          </div>
          <div className="bg-card border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-2">Ecosysteem score profiel</h3>
            <ResponsiveContainer width="100%" height={220}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9 }} />
                <Radar name="Score" dataKey="A" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
