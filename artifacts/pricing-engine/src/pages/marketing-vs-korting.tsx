import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, Legend } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TrendingUp, Megaphone, Tag, Zap } from "lucide-react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const STRAT_LABELS: Record<string, { label: string; color: string; icon: any }> = {
  PUSH_TRAFFIC_INSTEAD: { label: "Marketing slimmer", color: "text-emerald-600 bg-emerald-50 border-emerald-200", icon: Megaphone },
  PUSH_SEO: { label: "SEO verhogen", color: "text-blue-600 bg-blue-50 border-blue-200", icon: TrendingUp },
  PUSH_SEA: { label: "SEA verhogen", color: "text-purple-600 bg-purple-50 border-purple-200", icon: Zap },
  REDUCE_PRICE: { label: "Prijsverlaging", color: "text-orange-600 bg-orange-50 border-orange-200", icon: Tag },
  TEST_PRICE_INCREASE: { label: "Test verhogen", color: "text-yellow-600 bg-yellow-50 border-yellow-200", icon: TrendingUp },
};

export default function MarketingVsKorting() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [simSku, setSimSku] = useState("INK001");
  const [simVerlaging, setSimVerlaging] = useState("-10");
  const [simSeo, setSimSeo] = useState("500");
  const [simSea, setSimSea] = useState("500");
  const [simResult, setSimResult] = useState<any>(null);
  const [simLoading, setSimLoading] = useState(false);

  useEffect(() => {
    fetch(`${BASE}/api/marketing-vs-korting`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const simuleer = async () => {
    setSimLoading(true);
    try {
      const res = await fetch(`${BASE}/api/marketing-vs-korting/simuleer`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          sku_id: simSku,
          prijsverlaging_pct: parseFloat(simVerlaging),
          extra_seo_budget: parseFloat(simSeo),
          extra_sea_budget: parseFloat(simSea),
        }),
      });
      setSimResult(await res.json());
    } finally { setSimLoading(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen MEDS data beschikbaar.</div>;

  const medsBar = data.skus.slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    meds: parseFloat((s.meds_score * 100).toFixed(1)),
    fill: s.meds_score >= 0.65 ? "#10b981" : s.meds_score >= 0.40 ? "#3b82f6" : "#f97316",
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Marketing vs. Korting Simulator</h1>
      <p className="text-sm text-muted-foreground">Vergelijk of extra marketing of een prijsverlaging meer marge en omzet oplevert.</p>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's geanalyseerd", value: data.totaal_skus, icon: TrendingUp },
          { label: "Marketing slimmer", value: data.marketing_beter_count, icon: Megaphone, color: "text-emerald-600" },
          { label: "Prijsverlaging slimmer", value: data.korting_beter_count, icon: Tag, color: "text-orange-600" },
          { label: "Gem. MEDS score", value: `${(data.gemiddelde_meds * 100).toFixed(0)}%`, icon: Zap, color: "text-primary" },
        ].map((kpi, i) => (
          <div key={i} className="bg-card border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <kpi.icon className={`w-4 h-4 ${kpi.color || "text-muted-foreground"}`} />
              <span className="text-xs text-muted-foreground">{kpi.label}</span>
            </div>
            <div className={`text-2xl font-bold ${kpi.color || "text-foreground"}`}>{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* MEDS grafiek */}
      <div className="bg-card border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-1">Marketing Efficiency vs Discount Score (MEDS)</h3>
        <p className="text-xs text-muted-foreground mb-3">&gt;65% = marketing slimmer · &lt;40% = korting slimmer</p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={medsBar}>
            <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
            <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
            <Tooltip formatter={(v: any) => [`${v}%`, "MEDS"]} />
            <Bar dataKey="meds" radius={[3, 3, 0, 0]}>
              {medsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Simulator */}
      <div className="bg-card border rounded-lg p-5">
        <h3 className="font-semibold mb-1">Scenario Simulator</h3>
        <p className="text-sm text-muted-foreground mb-4">Vergelijk prijsverlaging vs. SEO vs. SEA voor één SKU.</p>
        <div className="flex flex-wrap gap-3 items-end">
          {[
            { label: "SKU-ID", val: simSku, set: setSimSku, type: "text", w: "w-28" },
            { label: "Prijsverlaging (%)", val: simVerlaging, set: setSimVerlaging, type: "number", w: "w-28" },
            { label: "Extra SEO budget (€)", val: simSeo, set: setSimSeo, type: "number", w: "w-32" },
            { label: "Extra SEA budget (€)", val: simSea, set: setSimSea, type: "number", w: "w-32" },
          ].map((f, i) => (
            <div key={i}>
              <label className="text-xs text-muted-foreground block mb-1">{f.label}</label>
              <Input className={f.w} type={f.type} value={f.val} onChange={e => f.set(e.target.value)} />
            </div>
          ))}
          <Button onClick={simuleer} disabled={simLoading} className="h-9">
            {simLoading ? "Simuleren…" : "Simuleer scenario's"}
          </Button>
        </div>

        {simResult && !simResult.detail && (
          <div className="mt-5 space-y-4">
            {/* Huidige situatie */}
            <div className="bg-muted/20 rounded p-3 border">
              <div className="text-xs font-medium text-muted-foreground mb-2">Huidige situatie — {simResult.naam}</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {[
                  { label: "Verkoopprijs", value: `€${simResult.huidig?.prijs?.toFixed(2)}` },
                  { label: "Afzet", value: `${simResult.huidig?.afzet} units` },
                  { label: "Omzet", value: `€${simResult.huidig?.omzet?.toFixed(0)}` },
                  { label: "Marge", value: `${simResult.huidig?.marge_pct?.toFixed(1)}%` },
                ].map((item, i) => (
                  <div key={i}>
                    <div className="text-xs text-muted-foreground">{item.label}</div>
                    <div className="font-semibold text-sm">{item.value}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Scenario vergelijking */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { title: "Scenario A — Prijsverlaging", data: simResult.scenario_a_prijsverlaging, color: "border-orange-200 bg-orange-50/50" },
                { title: "Scenario B — Extra SEO", data: simResult.scenario_b_seo, color: "border-blue-200 bg-blue-50/50" },
                { title: "Scenario C — Extra SEA", data: simResult.scenario_c_sea, color: "border-purple-200 bg-purple-50/50" },
              ].map((sc, i) => (
                <div key={i} className={`rounded-lg border p-4 ${sc.color}`}>
                  <div className="text-sm font-semibold mb-3">{sc.title}</div>
                  <div className="space-y-1.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Verwachte omzet</span>
                      <span className="font-medium">€{sc.data?.expected_revenue?.toFixed(0)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Verwachte marge</span>
                      <span className="font-medium">€{sc.data?.expected_margin_eur?.toFixed(0)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Marge %</span>
                      <span className="font-medium">{sc.data?.expected_margin?.toFixed(1)}%</span>
                    </div>
                    {sc.data?.expected_roas && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">ROAS</span>
                        <span className="font-medium">{sc.data?.expected_roas?.toFixed(2)}×</span>
                      </div>
                    )}
                    {sc.data?.expected_traffic && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Traffic</span>
                        <span className="font-medium">{sc.data?.expected_traffic?.toLocaleString("nl-NL")}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* MEDS conclusie */}
            <div className="bg-card border rounded p-4 flex items-start gap-3">
              <div className="flex-1">
                <div className="text-xs text-muted-foreground mb-1">MEDS Conclusie</div>
                <div className="font-semibold">{simResult.toelichting_nl}</div>
              </div>
              <Badge variant="outline" className={`text-sm ${STRAT_LABELS[simResult.aanbeveling]?.color || ""}`}>
                {STRAT_LABELS[simResult.aanbeveling]?.label || simResult.aanbeveling}
              </Badge>
            </div>
          </div>
        )}
      </div>

      {/* SKU overzicht */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30">
          <span className="text-sm font-semibold">MEDS Overzicht per SKU</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr>
                {["SKU", "Product", "Verwachte omzet", "Verwachte marge %", "ROAS", "MEDS score", "Aanbeveling"].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.skus.map((s: any) => {
                const strat = STRAT_LABELS[s.aanbeveling];
                return (
                  <tr key={s.sku_id} className="border-t hover:bg-muted/30">
                    <td className="px-3 py-2 font-mono text-xs">{s.sku_id}</td>
                    <td className="px-3 py-2 font-medium max-w-[160px] truncate">{s.naam}</td>
                    <td className="px-3 py-2 tabular-nums">€{s.verwachte_omzet?.toFixed(0)}</td>
                    <td className="px-3 py-2">{s.verwachte_marge_pct?.toFixed(1)}%</td>
                    <td className="px-3 py-2">{s.verwachte_roas?.toFixed(2)}×</td>
                    <td className="px-3 py-2">
                      <span className={`font-bold ${s.meds_score >= 0.65 ? "text-emerald-600" : s.meds_score >= 0.40 ? "text-blue-600" : "text-orange-600"}`}>
                        {(s.meds_score * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className={`text-[10px] ${strat?.color || ""}`}>
                        {strat?.label || s.aanbeveling}
                      </Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
