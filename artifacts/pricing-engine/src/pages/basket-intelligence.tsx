import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ScatterChart, Scatter, ZAxis, CartesianGrid } from "recharts";
import { ShoppingCart, TrendingUp, Package, Euro } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const BBS_COLORS: Record<string, string> = {
  "KRITIEK WINKELMANDVULLER": "text-emerald-600 bg-emerald-50 border-emerald-200",
  "STERK WINKELMANDVULLER":   "text-blue-600 bg-blue-50 border-blue-200",
  "MATIG WINKELMANDVULLER":   "text-yellow-600 bg-yellow-50 border-yellow-200",
  "ZWAKKE WINKELMANDVULLER":  "text-slate-500 bg-slate-50 border-slate-200",
};

export default function BasketIntelligenceDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [geselecteerd, setGeselecteerd] = useState<any>(null);

  useEffect(() => {
    fetch(`${BASE}/api/basket-intelligence`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen basket intelligence data beschikbaar.</div>;

  const bbsBar = data.skus.slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    bbs: parseFloat((s.bbs_score * 100).toFixed(1)),
    fill: s.bbs_score >= 0.75 ? "#10b981" : s.bbs_score >= 0.55 ? "#3b82f6" : s.bbs_score >= 0.35 ? "#f59e0b" : "#94a3b8",
  }));

  const attachBar = data.skus.slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    attach: parseFloat(((s.attach_rate || 0) * 100).toFixed(1)),
    uplift: parseFloat((s.basket_uplift_eur || 0).toFixed(2)),
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Basket Intelligence Dashboard</h1>
      <p className="text-sm text-muted-foreground">Welke SKU's vullen winkelwagens en genereren cross-sell omzet?</p>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's geanalyseerd", value: data.totaal_skus, icon: ShoppingCart, color: "text-primary" },
          { label: "Kritieke winkelmandvullers", value: data.kritiek_count, icon: Package, color: "text-emerald-600" },
          { label: "Gem. attach-rate", value: `${((data.gemiddelde_attach_rate || 0) * 100).toFixed(0)}%`, icon: TrendingUp, color: "text-blue-600" },
          { label: "Totale incrementele marge", value: `€${(data.totale_incrementele_marge || 0).toLocaleString("nl-NL", { minimumFractionDigits: 0 })}`, icon: Euro, color: "text-orange-600" },
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
        {/* BBS bar */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Basket Builder Score (BBS) per SKU</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={bbsBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "BBS"]} />
              <Bar dataKey="bbs" radius={[3, 3, 0, 0]}>
                {bbsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Attach-rate + uplift */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Attach-rate (%) per SKU</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={attachBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "Attach-rate"]} />
              <Bar dataKey="attach" fill="#10b981" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Tabel */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30">
          <span className="text-sm font-semibold">Winkelmand-analyse per SKU</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr>
                {["SKU", "Product", "Attach-rate", "Gem. mandwaarde", "Gem. items", "Co-occurrence", "Cross-sell freq.", "Inc. marge", "Basket uplift", "BBS", "Klasse"].map(h => (
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
                  <td className="px-3 py-2 font-medium max-w-[160px] truncate">{s.naam}</td>
                  <td className="px-3 py-2">
                    <span className={`font-semibold ${s.attach_rate >= 0.60 ? "text-emerald-600" : s.attach_rate >= 0.40 ? "text-blue-600" : "text-muted-foreground"}`}>
                      {((s.attach_rate || 0) * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2 tabular-nums">€{(s.gem_mandwaarde || 0).toFixed(2)}</td>
                  <td className="px-3 py-2 tabular-nums">{(s.gem_items || 0).toFixed(1)}</td>
                  <td className="px-3 py-2">{((s.co_occurrence || 0) * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2">{(s.cross_sell_freq || 0).toFixed(1)}×</td>
                  <td className="px-3 py-2 tabular-nums text-emerald-600 font-medium">€{(s.incrementele_marge || 0).toFixed(2)}</td>
                  <td className="px-3 py-2 tabular-nums">€{(s.basket_uplift_eur || 0).toFixed(2)}</td>
                  <td className="px-3 py-2">
                    <span className={`font-bold ${s.bbs_score >= 0.75 ? "text-emerald-600" : s.bbs_score >= 0.55 ? "text-blue-600" : s.bbs_score >= 0.35 ? "text-yellow-600" : "text-slate-500"}`}>
                      {(s.bbs_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={`text-[10px] whitespace-nowrap ${BBS_COLORS[s.bbs_label] || ""}`}>
                      {s.bbs_label?.replace(" WINKELMANDVULLER", "") || "—"}
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
        <div className="bg-card border rounded-lg p-5 space-y-3">
          <h3 className="font-semibold">{geselecteerd.naam} <span className="text-muted-foreground font-normal text-sm">— {geselecteerd.sku_id}</span></h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Attach-rate", value: `${((geselecteerd.attach_rate || 0) * 100).toFixed(0)}%` },
              { label: "Gem. mandwaarde", value: `€${(geselecteerd.gem_mandwaarde || 0).toFixed(2)}` },
              { label: "Incrementele marge", value: `€${(geselecteerd.incrementele_marge || 0).toFixed(2)}` },
              { label: "BBS score", value: `${(geselecteerd.bbs_score * 100).toFixed(0)}%` },
              { label: "Cross-sell freq.", value: `${(geselecteerd.cross_sell_freq || 0).toFixed(1)}×` },
              { label: "Basket uplift EUR", value: `€${(geselecteerd.basket_uplift_eur || 0).toFixed(2)}` },
              { label: "Co-occurrence", value: `${((geselecteerd.co_occurrence || 0) * 100).toFixed(0)}%` },
              { label: "Gem. items per bestelling", value: (geselecteerd.gem_items || 0).toFixed(1) },
            ].map((item, i) => (
              <div key={i} className="bg-muted/20 rounded p-2">
                <div className="text-xs text-muted-foreground">{item.label}</div>
                <div className="font-semibold text-sm">{item.value}</div>
              </div>
            ))}
          </div>
          {geselecteerd.top_co_skus?.length > 0 && (
            <div>
              <div className="text-xs text-muted-foreground mb-1">Meest voorkomende co-SKU's</div>
              <div className="flex flex-wrap gap-2">
                {geselecteerd.top_co_skus.filter(Boolean).map((sku: string) => (
                  <Badge key={sku} variant="secondary" className="text-xs">{sku}</Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
