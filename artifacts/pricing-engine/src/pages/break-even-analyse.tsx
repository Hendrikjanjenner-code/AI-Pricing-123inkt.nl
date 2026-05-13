import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from "recharts";
import { AlertTriangle, TrendingDown, CheckCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const BEDS_COLORS: Record<string, string> = {
  HAALBAAR: "text-emerald-600 bg-emerald-50 border-emerald-200",
  UITDAGEND: "text-yellow-600 bg-yellow-50 border-yellow-200",
  MOEILIJK: "text-orange-600 bg-orange-50 border-orange-200",
  ONMOGELIJK: "text-red-600 bg-red-50 border-red-200",
};

export default function BreakEvenAnalyse() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [simSku, setSimSku] = useState("INK001");
  const [simPrijs, setSimPrijs] = useState("");
  const [simResult, setSimResult] = useState<any>(null);
  const [simLoading, setSimLoading] = useState(false);

  useEffect(() => {
    fetch(`${BASE}/api/break-even`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const simuleer = async () => {
    if (!simSku || !simPrijs) return;
    setSimLoading(true);
    try {
      const res = await fetch(`${BASE}/api/break-even/simuleer`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" },
        body: JSON.stringify({ sku_id: simSku, nieuwe_prijs: parseFloat(simPrijs) }),
      });
      setSimResult(await res.json());
    } finally { setSimLoading(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;

  const bedsBar = (data?.skus || []).map((s: any) => ({
    name: s.sku_id,
    beds: parseFloat(((s.beds_score || 0) * 100).toFixed(1)),
    fill: s.beds_score >= 0.70 ? "#ef4444" : s.beds_score >= 0.45 ? "#f97316" : s.beds_score >= 0.20 ? "#eab308" : "#10b981",
  }));

  const unitsPctBar = (data?.skus || []).map((s: any) => ({
    name: s.sku_id,
    pct: Math.min(200, s.break_even_extra_units_pct || 0),
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Break-even Analyse</h1>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's geanalyseerd", value: data?.totaal_skus ?? 0, icon: TrendingDown, color: "text-primary" },
          { label: "Break-even haalbaar", value: data?.haalbaar_count ?? 0, icon: CheckCircle, color: "text-emerald-600" },
          { label: "Break-even onmogelijk", value: data?.onmogelijk_count ?? 0, icon: XCircle, color: "text-red-600" },
          { label: "Gem. BEDS score", value: `${((data?.gemiddelde_beds ?? 0) * 100).toFixed(0)}%`, icon: AlertTriangle, color: "text-amber-600" },
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
        {/* BEDS grafiek */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Break-even Difficulty Score per SKU</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={bedsBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "BEDS"]} />
              <ReferenceLine y={45} stroke="#f97316" strokeDasharray="3 3" label={{ value: "Uitdagend", position: "right", fontSize: 10 }} />
              <Bar dataKey="beds" radius={[3, 3, 0, 0]}>
                {bedsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Extra afzet grafiek */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Benodigde extra afzet voor break-even (%)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={unitsPctBar}>
              <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "Extra afzet"]} />
              <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3" />
              <Bar dataKey="pct" fill="#3b82f6" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Simulatietool */}
      <div className="bg-card border rounded-lg p-5">
        <h3 className="font-semibold mb-4">Prijsverlagingssimulator</h3>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">SKU-ID</label>
            <Input className="w-32" value={simSku} onChange={e => setSimSku(e.target.value)} placeholder="bv. INK001" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Nieuwe prijs (€)</label>
            <Input className="w-32" type="number" step="0.01" value={simPrijs} onChange={e => setSimPrijs(e.target.value)} placeholder="bv. 15.99" />
          </div>
          <Button onClick={simuleer} disabled={simLoading} className="h-9">
            {simLoading ? "Berekenen…" : "Bereken break-even"}
          </Button>
        </div>

        {simResult && !simResult.error && (
          <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Huidige prijs", value: `€${simResult.huidige_prijs?.toFixed(2)}` },
              { label: "Nieuwe prijs", value: `€${simResult.nieuwe_prijs?.toFixed(2)}`, highlight: true },
              { label: "Prijsverlaging", value: `${simResult.prijswijziging_pct?.toFixed(1)}%`, red: true },
              { label: "Margeverlies/unit", value: `€${simResult.margeverlies_per_unit?.toFixed(2)}` },
              { label: "Break-even extra units", value: simResult.break_even_extra_units ? Math.round(simResult.break_even_extra_units) : "∞" },
              { label: "Break-even extra afzet", value: simResult.break_even_extra_units_pct ? `${simResult.break_even_extra_units_pct.toFixed(0)}%` : "∞" },
              { label: "Break-even extra traffic", value: simResult.break_even_extra_traffic ? Math.round(simResult.break_even_extra_traffic) : "∞" },
              { label: "BEDS moeilijkheid", value: simResult.beds_label },
            ].map((item, i) => (
              <div key={i} className={`rounded p-3 border ${item.red ? "border-red-200 bg-red-50" : item.highlight ? "border-primary/30 bg-primary/5" : "bg-muted/20"}`}>
                <div className="text-xs text-muted-foreground">{item.label}</div>
                <div className={`font-semibold text-sm ${item.red ? "text-red-600" : ""}`}>{item.value}</div>
              </div>
            ))}
            <div className="md:col-span-4 bg-muted/20 rounded p-3 border">
              <div className="text-xs text-muted-foreground mb-1">Toelichting</div>
              <div className="text-sm">{simResult.toelichting_nl}</div>
            </div>
          </div>
        )}
        {simResult?.error && <p className="mt-3 text-sm text-red-600">{simResult.error}</p>}
      </div>

      {/* SKU tabel */}
      {data?.skus?.length > 0 && (
        <div className="bg-card border rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b bg-muted/30">
            <span className="text-sm font-semibold">Break-even Overzicht per SKU</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/20">
                <tr>
                  {["SKU", "Product", "Scenario", "Huidige prijs", "Nieuwe prijs", "Verlaging", "Extra afzet nodig", "Extra traffic", "BEDS", "Advies"].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.skus.map((s: any) => (
                  <tr key={s.sku_id} className="border-t hover:bg-muted/30">
                    <td className="px-3 py-2 font-mono text-xs">{s.sku_id}</td>
                    <td className="px-3 py-2 font-medium max-w-[160px] truncate">{s.naam}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{s.scenario_type}</td>
                    <td className="px-3 py-2 tabular-nums">€{s.huidige_prijs?.toFixed(2)}</td>
                    <td className="px-3 py-2 tabular-nums">€{s.nieuwe_prijs?.toFixed(2)}</td>
                    <td className="px-3 py-2 text-red-600 font-semibold">{s.prijswijziging_pct?.toFixed(1)}%</td>
                    <td className="px-3 py-2">
                      <span className={`font-semibold ${s.break_even_extra_units_pct > 50 ? "text-red-600" : "text-emerald-600"}`}>
                        {s.break_even_extra_units_pct ? `+${s.break_even_extra_units_pct.toFixed(0)}%` : "∞"}
                      </span>
                    </td>
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">
                      {s.break_even_extra_traffic ? Math.round(s.break_even_extra_traffic).toLocaleString("nl-NL") : "∞"}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className={`text-[10px] ${BEDS_COLORS[s.beds_label] || ""}`}>
                        {s.beds_label}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{s.aanbeveling}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
