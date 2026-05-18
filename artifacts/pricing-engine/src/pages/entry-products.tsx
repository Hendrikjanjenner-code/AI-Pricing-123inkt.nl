import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ScatterChart, Scatter, CartesianGrid, ZAxis } from "recharts";
import { Users, Star, TrendingUp, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const TDS_COLORS: Record<string, string> = {
  "KRITIEK TRAFFIC DRIVER": "text-red-600 bg-red-50 border-red-200",
  "STERK TRAFFIC DRIVER":   "text-orange-600 bg-orange-50 border-orange-200",
  "MATIG TRAFFIC DRIVER":   "text-yellow-600 bg-yellow-50 border-yellow-200",
  "LAAG TRAFFIC DRIVER":    "text-slate-500 bg-slate-50 border-slate-200",
};

export default function EntryProductsAnalyse() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BASE}/api/entry-products`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen entry product data beschikbaar.</div>;

  const epsBar = data.skus.slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    eps: parseFloat((s.entry_product_score * 100).toFixed(1)),
    fill: s.entry_product_score >= 0.70 ? "#ef4444" : s.entry_product_score >= 0.50 ? "#f97316" : s.entry_product_score >= 0.30 ? "#3b82f6" : "#94a3b8",
  }));

  const ncBar = data.skus.slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    nc: s.nieuwe_klanten || 0,
    first: parseFloat(((s.eerste_product_pct || 0) * 100).toFixed(1)),
  }));

  const scatterData = data.skus.map((s: any) => ({
    name: s.sku_id,
    naam: s.naam,
    eps: parseFloat((s.entry_product_score * 100).toFixed(1)),
    tds: parseFloat((s.traffic_driver_score * 100).toFixed(1)),
    nc: s.nieuwe_klanten || 0,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Entry Products Analyse</h1>
      <p className="text-sm text-muted-foreground">
        Welke producten zijn het startpunt van klanttrajecten? Entry products zijn cruciaal voor eerste-indruk pricing.
      </p>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's geanalyseerd", value: data.totaal_skus, icon: Search, color: "text-primary" },
          { label: "Sterke entry products (EPS ≥60%)", value: data.top_entry_count, icon: Star, color: "text-red-600" },
          { label: "Gem. EPS score", value: `${((data.gemiddelde_eps || 0) * 100).toFixed(0)}%`, icon: TrendingUp, color: "text-orange-600" },
          { label: "Totaal nieuwe klanten", value: (data.totaal_nieuwe_klanten || 0).toLocaleString("nl-NL"), icon: Users, color: "text-emerald-600" },
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
        {/* EPS bar */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Entry Product Score (EPS) per SKU</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={epsBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "EPS"]} />
              <Bar dataKey="eps" radius={[3, 3, 0, 0]}>
                {epsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Nieuwe klanten bar */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Nieuwe klant bijdrage per SKU</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={ncBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="nc" name="Nieuwe klanten" fill="#10b981" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Pricing implicaties */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-amber-800 mb-2">Pricing-richtlijn voor Entry Products</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm text-amber-700">
          {[
            { icon: "🚫", title: "Vermijd agressieve verhogingen", desc: "Entry products met hoge EPS nooit meer dan +3% verhogen zonder traffic monitoring." },
            { icon: "💡", title: "Prijs als acquisitiemiddel", desc: "Competitieve entry pricing compenseert via hogere CLV en basket-uitbreiding." },
            { icon: "📊", title: "Monitor conversie-impact", desc: "Prijswijziging op entry products direct koppelen aan conversieratio-monitoring." },
          ].map((item, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-lg">{item.icon}</span>
              <div>
                <div className="font-medium">{item.title}</div>
                <div className="text-xs mt-0.5 opacity-80">{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabel */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30">
          <span className="text-sm font-semibold">Entry Product Ranking</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr>
                {["Rang", "SKU", "Product", "Categorie", "1e product % sessie", "Nieuw klant 1e order %", "Nieuwe klanten", "EPS", "TDS", "Klasse"].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.skus.map((s: any, i: number) => (
                <tr key={s.sku_id} className="border-t hover:bg-muted/30">
                  <td className="px-3 py-2 text-muted-foreground text-xs font-mono">#{i + 1}</td>
                  <td className="px-3 py-2 font-mono text-xs">{s.sku_id}</td>
                  <td className="px-3 py-2 font-medium max-w-[160px] truncate">{s.naam}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{s.categorie}</td>
                  <td className="px-3 py-2 font-semibold">{((s.eerste_product_pct || 0) * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2">{((s.nieuwe_klant_eerste_order_pct || 0) * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2 text-emerald-600 font-medium tabular-nums">{(s.nieuwe_klanten || 0).toLocaleString("nl-NL")}</td>
                  <td className="px-3 py-2">
                    <span className={`font-bold ${s.entry_product_score >= 0.70 ? "text-red-600" : s.entry_product_score >= 0.50 ? "text-orange-600" : s.entry_product_score >= 0.30 ? "text-blue-600" : "text-slate-500"}`}>
                      {(s.entry_product_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`font-semibold ${s.traffic_driver_score >= 0.60 ? "text-emerald-600" : "text-muted-foreground"}`}>
                      {(s.traffic_driver_score * 100).toFixed(0)}%
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
    </div>
  );
}
