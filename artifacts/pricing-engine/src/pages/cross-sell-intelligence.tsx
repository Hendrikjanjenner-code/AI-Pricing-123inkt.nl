import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { ArrowRightLeft, TrendingUp, Euro, Link } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

export default function CrossSellIntelligence() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [detailSku, setDetailSku] = useState<string>("");
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    fetch(`${BASE}/api/cross-sell`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const laadDetail = async (skuId: string) => {
    setDetailLoading(true);
    setDetailSku(skuId);
    try {
      const res = await fetch(`${BASE}/api/cross-sell/sku/${skuId}`, {
        headers: { Authorization: `Bearer ${getToken()}` }
      });
      setDetail(await res.json());
    } finally { setDetailLoading(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen cross-sell data beschikbaar.</div>;

  const ampBar = data.skus.slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    amp: Math.min(120, s.cross_sell_amplificatie_pct || 0),
    fill: s.cross_sell_amplificatie_pct >= 50 ? "#10b981" : s.cross_sell_amplificatie_pct >= 20 ? "#3b82f6" : "#94a3b8",
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Cross-sell Intelligence</h1>
      <p className="text-sm text-muted-foreground">Welke SKU's genereren extra marge via cross-sell en upsell patronen?</p>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's met cross-sell", value: data.totaal_skus_met_cross_sell, icon: Link, color: "text-primary" },
          { label: "Totale incrementele marge", value: `€${(data.totale_incrementele_marge || 0).toFixed(0)}`, icon: Euro, color: "text-emerald-600" },
          { label: "Gem. amplificatie", value: `${((data.skus || []).reduce((a: number, s: any) => a + (s.cross_sell_amplificatie_pct || 0), 0) / Math.max(1, data.skus?.length)).toFixed(0)}%`, icon: TrendingUp, color: "text-blue-600" },
          { label: "SKU's met >50% amplificatie", value: (data.skus || []).filter((s: any) => s.cross_sell_amplificatie_pct >= 50).length, icon: ArrowRightLeft, color: "text-orange-600" },
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

      {/* Grafiek */}
      <div className="bg-card border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3">Cross-sell Marge Amplificatie per SKU (%)</h3>
        <p className="text-xs text-muted-foreground mb-3">Percentage extra marge bovenop directe SKU-marge via cross-sell</p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={ampBar}>
            <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
            <YAxis tick={{ fontSize: 11 }} unit="%" />
            <Tooltip formatter={(v: any) => [`${v}%`, "Amplificatie"]} />
            <Bar dataKey="amp" radius={[3, 3, 0, 0]}>
              {ampBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Tabel */}
        <div className="lg:col-span-2 bg-card border rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b bg-muted/30">
            <span className="text-sm font-semibold">Cross-sell kansen per SKU (klik voor partners)</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/20">
                <tr>
                  {["SKU", "Product", "Attach-rate", "Inc. marge", "Amplificatie", "# Partners", "Top partner"].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.skus.map((s: any) => (
                  <tr key={s.sku_id}
                    className={`border-t cursor-pointer hover:bg-muted/30 transition-colors ${detailSku === s.sku_id ? "bg-primary/5" : ""}`}
                    onClick={() => laadDetail(s.sku_id)}
                  >
                    <td className="px-3 py-2 font-mono text-xs">{s.sku_id}</td>
                    <td className="px-3 py-2 font-medium max-w-[160px] truncate">{s.naam}</td>
                    <td className="px-3 py-2">{((s.attach_rate || 0) * 100).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-emerald-600 font-medium">€{(s.incrementele_marge || 0).toFixed(2)}</td>
                    <td className="px-3 py-2">
                      <span className={`font-bold ${s.cross_sell_amplificatie_pct >= 50 ? "text-emerald-600" : s.cross_sell_amplificatie_pct >= 20 ? "text-blue-600" : "text-muted-foreground"}`}>
                        +{(s.cross_sell_amplificatie_pct || 0).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-3 py-2">{s.aantal_cross_sell_skus}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground max-w-[140px] truncate">{s.top_partner || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Detail cross-sell */}
        <div className="bg-card border rounded-lg p-4">
          {detailLoading && <div className="text-center text-muted-foreground py-8">Laden…</div>}
          {!detailLoading && !detail && (
            <div className="text-center text-muted-foreground py-8 text-sm">
              Klik op een SKU voor cross-sell partners
            </div>
          )}
          {!detailLoading && detail && !detail.error && (
            <div className="space-y-3">
              <h3 className="font-semibold text-sm">{detail.naam}</h3>
              <div className="space-y-1 text-sm">
                {[
                  { label: "Attach-rate", value: `${((detail.attach_rate || 0) * 100).toFixed(0)}%` },
                  { label: "Inc. marge", value: `€${(detail.incrementele_marge || 0).toFixed(2)}` },
                  { label: "Amplificatie", value: `+${(detail.cross_sell_amplificatie_pct || 0).toFixed(0)}%` },
                  { label: "Directe marge", value: `€${(detail.directe_marge_eur || 0).toFixed(2)}` },
                ].map((item, i) => (
                  <div key={i} className="flex justify-between">
                    <span className="text-muted-foreground">{item.label}</span>
                    <span className="font-medium">{item.value}</span>
                  </div>
                ))}
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded p-2 text-xs text-blue-700">
                {detail.toelichting_nl}
              </div>
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-2">Top Cross-sell Partners</div>
                <div className="space-y-2">
                  {(detail.top_cross_sell_skus || []).map((p: any) => (
                    <div key={p.partner_sku_id} className="bg-muted/20 rounded p-2">
                      <div className="text-xs font-medium truncate">{p.partner_naam}</div>
                      <div className="flex justify-between text-xs text-muted-foreground mt-0.5">
                        <span>Affinity: {(p.affinity_score * 100).toFixed(0)}%</span>
                        <span>Marge: €{(p.partner_marge_eur || 0).toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                  {(!detail.top_cross_sell_skus || detail.top_cross_sell_skus.length === 0) && (
                    <div className="text-xs text-muted-foreground">Geen cross-sell partners gevonden</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
