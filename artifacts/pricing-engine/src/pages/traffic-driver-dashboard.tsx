import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ScatterChart, Scatter, ZAxis } from "recharts";
import { TrendingUp, Users, Search, Megaphone, Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const TDS_COLORS: Record<string, string> = {
  "KRITIEK TRAFFIC DRIVER": "text-red-600 bg-red-50 border-red-200",
  "STERK TRAFFIC DRIVER":   "text-orange-600 bg-orange-50 border-orange-200",
  "MATIG TRAFFIC DRIVER":   "text-yellow-600 bg-yellow-50 border-yellow-200",
  "LAAG TRAFFIC DRIVER":    "text-slate-500 bg-slate-50 border-slate-200",
};

export default function TrafficDriverDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [geselecteerd, setGeselecteerd] = useState<any>(null);

  useEffect(() => {
    fetch(`${BASE}/api/traffic-driver`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen traffic driver data beschikbaar.</div>;

  const tdsBar = data.skus.slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    tds: parseFloat((s.traffic_driver_score * 100).toFixed(1)),
    fill: s.traffic_driver_score >= 0.80 ? "#ef4444" : s.traffic_driver_score >= 0.60 ? "#f97316" : s.traffic_driver_score >= 0.40 ? "#eab308" : "#94a3b8",
  }));

  const trafficBar = data.skus.slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    seo: s.seo_traffic || 0,
    sea: s.sea_traffic || 0,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Traffic Driver Dashboard</h1>
      <p className="text-sm text-muted-foreground">Welke SKU's genereren traffic naar 123inkt.nl en trekken nieuwe klanten aan?</p>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Totaal SKU's", value: data.totaal_skus, icon: Search, color: "text-primary" },
          { label: "Kritieke traffic drivers", value: data.kritiek_count, icon: Star, color: "text-red-600" },
          { label: "Sterke traffic drivers", value: data.sterk_count, icon: TrendingUp, color: "text-orange-600" },
          { label: "Totaal SEO traffic", value: (data.totaal_seo_traffic || 0).toLocaleString("nl-NL"), icon: Search, color: "text-blue-600" },
          { label: "Nieuwe klanten (gesimuleerd)", value: (data.totaal_nieuwe_klanten || 0).toLocaleString("nl-NL"), icon: Users, color: "text-emerald-600" },
        ].map((kpi, i) => (
          <div key={i} className="bg-card border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <kpi.icon className={`w-4 h-4 ${kpi.color}`} />
              <span className="text-xs text-muted-foreground">{kpi.label}</span>
            </div>
            <div className={`text-xl font-bold ${kpi.color}`}>{kpi.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* TDS bar */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Traffic Driver Score (TDS) per SKU</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={tdsBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "TDS"]} />
              <Bar dataKey="tds" radius={[3, 3, 0, 0]}>
                {tdsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* SEO vs SEA */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">SEO vs SEA traffic per SKU</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={trafficBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="seo" name="SEO" fill="#3b82f6" stackId="a" />
              <Bar dataKey="sea" name="SEA" fill="#a78bfa" stackId="a" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* SKU tabel */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30">
          <span className="text-sm font-semibold">Traffic Driver Ranking — alle SKU's</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr>
                {["Rang", "SKU", "Product", "SEO Traffic", "SEA Traffic", "Zoekvolume", "Nieuwe klanten", "1e product %", "TDS", "EPS", "Klasse"].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.skus.map((s: any, i: number) => (
                <tr key={s.sku_id}
                  className={`border-t cursor-pointer hover:bg-muted/30 transition-colors ${geselecteerd?.sku_id === s.sku_id ? "bg-primary/5" : ""}`}
                  onClick={() => setGeselecteerd(geselecteerd?.sku_id === s.sku_id ? null : s)}
                >
                  <td className="px-3 py-2 text-muted-foreground text-xs font-mono">#{i + 1}</td>
                  <td className="px-3 py-2 font-mono text-xs">{s.sku_id}</td>
                  <td className="px-3 py-2 font-medium max-w-[160px] truncate">{s.naam}</td>
                  <td className="px-3 py-2 tabular-nums">{(s.seo_traffic || 0).toLocaleString("nl-NL")}</td>
                  <td className="px-3 py-2 tabular-nums">{(s.sea_traffic || 0).toLocaleString("nl-NL")}</td>
                  <td className="px-3 py-2 tabular-nums">{(s.zoekvolume || 0).toLocaleString("nl-NL")}</td>
                  <td className="px-3 py-2 tabular-nums text-emerald-600 font-medium">{(s.nieuwe_klanten || 0).toLocaleString("nl-NL")}</td>
                  <td className="px-3 py-2">{((s.eerste_product_pct || 0) * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2">
                    <span className={`font-bold ${s.traffic_driver_score >= 0.80 ? "text-red-600" : s.traffic_driver_score >= 0.60 ? "text-orange-600" : s.traffic_driver_score >= 0.40 ? "text-yellow-600" : "text-slate-500"}`}>
                      {(s.traffic_driver_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`font-semibold ${s.entry_product_score >= 0.60 ? "text-emerald-600" : "text-muted-foreground"}`}>
                      {(s.entry_product_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={`text-[10px] whitespace-nowrap ${TDS_COLORS[s.tds_label] || ""}`}>
                      {s.tds_label?.replace(" TRAFFIC DRIVER", "") || "—"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail */}
      {geselecteerd && (
        <div className="bg-card border rounded-lg p-5 space-y-3">
          <h3 className="font-semibold">{geselecteerd.naam} <span className="text-muted-foreground font-normal text-sm">— {geselecteerd.sku_id}</span></h3>
          <p className="text-sm text-muted-foreground">{geselecteerd.toelichting_nl}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "TDS (traffic driver)", value: `${(geselecteerd.traffic_driver_score * 100).toFixed(0)}%` },
              { label: "EPS (entry product)", value: `${(geselecteerd.entry_product_score * 100).toFixed(0)}%` },
              { label: "SEO traffic", value: (geselecteerd.seo_traffic || 0).toLocaleString("nl-NL") },
              { label: "Nieuwe klanten", value: (geselecteerd.nieuwe_klanten || 0).toLocaleString("nl-NL") },
              { label: "Organic visibility", value: `${((geselecteerd.organic_visibility || 0) * 100).toFixed(0)}%` },
              { label: "Extern zoekvolume", value: (geselecteerd.zoekvolume || 0).toLocaleString("nl-NL") },
              { label: "Eerste product sessie", value: `${((geselecteerd.eerste_product_pct || 0) * 100).toFixed(0)}%` },
              { label: "Totaal traffic", value: (geselecteerd.totaal_traffic || 0).toLocaleString("nl-NL") },
            ].map((item, i) => (
              <div key={i} className="bg-muted/20 rounded p-2">
                <div className="text-xs text-muted-foreground">{item.label}</div>
                <div className="font-semibold text-sm">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
