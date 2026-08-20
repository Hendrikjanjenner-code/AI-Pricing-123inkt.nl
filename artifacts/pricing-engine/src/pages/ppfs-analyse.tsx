import { useState, useEffect } from "react";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const PPFS_COLORS: Record<string, string> = {
  STERK: "text-emerald-600 bg-emerald-50 border-emerald-200",
  GOED: "text-blue-600 bg-blue-50 border-blue-200",
  MATIG: "text-yellow-600 bg-yellow-50 border-yellow-200",
  RISICOVOL: "text-red-600 bg-red-50 border-red-200",
};

const ADVICE_NL: Record<string, string> = {
  FULL_PASS_THROUGH: "Volledig doorberekenen",
  PARTIAL_PASS_THROUGH: "Gedeeltelijk doorberekenen",
  TEST_PRICE_INCREASE: "Voorzichtig verhogen/testen",
  NO_PASS_THROUGH: "Niet doorberekenen — risico",
};

export default function PpfsAnalyse() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [liveSku, setLiveSku] = useState("PAP001");
  const [livePct, setLivePct] = useState("15");
  const [liveResult, setLiveResult] = useState<any>(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);

  useEffect(() => {
    setLoading(true);
    const url = `${BASE}/api/ppfs`;
    fetch(url + (fp !== "" ? (url.includes("?") ? "&" : "?") + fp : ""), { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [fp]);

  const berekenLive = async () => {
    setLiveLoading(true);
    try {
      const res = await fetch(`${BASE}/api/ppfs/sku/${liveSku}?cost_change_pct=${livePct}`, {
        headers: { Authorization: `Bearer ${getToken()}` }
      });
      setLiveResult(await res.json());
    } finally { setLiveLoading(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Laden…</div>;
  if (!data?.skus?.length) return <div className="text-muted-foreground p-8">Geen PPFS data beschikbaar.</div>;

  const ppfsBar = data.skus.slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    ppfs: parseFloat((s.ppfs_score * 100).toFixed(1)),
    fill: s.ppfs_score >= 0.75 ? "#10b981" : s.ppfs_score >= 0.55 ? "#3b82f6" : s.ppfs_score >= 0.35 ? "#f59e0b" : "#ef4444",
  }));

  const verdeling = data.verdeling || {};
  const verdelingData = Object.entries(verdeling).map(([k, v]: any) => ({ name: k, value: v }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Price Pass-through Analyse (PPFS)</h1>
      <p className="text-sm text-muted-foreground">Hoe realistisch is het om een inkoopprijsstijging door te berekenen aan de klant?</p>
      <GlobalFilterBar />

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "SKU's geanalyseerd", value: data.totaal_skus },
          { label: "Sterk (volledig doorberekenen)", value: data.sterk_count, color: "text-emerald-600" },
          { label: "Risicovol (niet doorberekenen)", value: data.risicovol_count, color: "text-red-600" },
          { label: "Gem. doorberekeenbaarheid", value: `${(data.gemiddelde_ppfs * 100).toFixed(0)}%`, color: "text-primary" },
        ].map((kpi, i) => (
          <div key={i} className="bg-card border rounded-lg p-4">
            <div className="text-xs text-muted-foreground mb-1">{kpi.label}</div>
            <div className={`text-2xl font-bold ${kpi.color || "text-foreground"}`}>{kpi.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* PPFS bar */}
        <div className="lg:col-span-2 bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">PPFS per SKU (doorberekenbaarheid)</h3>
          <ResponsiveContainer width="100%" height={220}>
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

        {/* Verdeling */}
        <div className="bg-card border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">Verdeling PPFS klassen</h3>
          <div className="space-y-3">
            {[
              { label: "Sterk", key: "STERK", color: "bg-emerald-500" },
              { label: "Goed", key: "GOED", color: "bg-blue-500" },
              { label: "Matig", key: "MATIG", color: "bg-yellow-500" },
              { label: "Risicovol", key: "RISICOVOL", color: "bg-red-500" },
            ].map(item => {
              const count = verdeling[item.key] || 0;
              const pct = data.totaal_skus > 0 ? (count / data.totaal_skus) * 100 : 0;
              return (
                <div key={item.key}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">{item.label}</span>
                    <span className="font-medium">{count} SKU's</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <div className={`${item.color} h-2 rounded-full`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Live PPFS calculator */}
      <div className="bg-card border rounded-lg p-5">
        <h3 className="font-semibold mb-3">Live PPFS Calculator</h3>
        <p className="text-sm text-muted-foreground mb-4">Bereken real-time de doorberekenbaarheid van een inkoopprijswijziging voor een specifiek SKU.</p>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">SKU-ID</label>
            <Input className="w-32" value={liveSku} onChange={e => setLiveSku(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Inkoopwijziging (%)</label>
            <Input className="w-28" type="number" value={livePct} onChange={e => setLivePct(e.target.value)} />
          </div>
          <Button onClick={berekenLive} disabled={liveLoading} className="h-9">
            {liveLoading ? "Berekenen…" : "Bereken PPFS"}
          </Button>
        </div>

        {liveResult && !liveResult.detail && (
          <div className="mt-5 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { label: "PPFS score", value: `${(liveResult.ppfs_score * 100).toFixed(0)}%` },
              { label: "Klasse", value: liveResult.ppfs_label },
              { label: "Elasticiteit factor", value: `${(liveResult.elasticity_score * 100).toFixed(0)}%` },
              { label: "BCG factor", value: `${(liveResult.bcg_factor * 100).toFixed(0)}%` },
              { label: "Concurrentiedruk", value: `${(liveResult.competition_pressure * 100).toFixed(0)}%` },
              { label: "Voorstel", value: `+${liveResult.proposed_price_change_pct?.toFixed(1)}%` },
            ].map((item, i) => (
              <div key={i} className="bg-muted/20 rounded p-3 border">
                <div className="text-xs text-muted-foreground">{item.label}</div>
                <div className="font-semibold text-sm">{item.value}</div>
              </div>
            ))}
            <div className="md:col-span-3 lg:col-span-6 bg-blue-50 border border-blue-200 rounded p-3">
              <div className="text-xs text-blue-600 font-medium mb-1">Advies</div>
              <div className="text-sm">{liveResult.toelichting_nl}</div>
            </div>
          </div>
        )}
      </div>

      {/* SKU tabel */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30">
          <span className="text-sm font-semibold">PPFS Overzicht — alle SKU's</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr>
                {["SKU", "Product", "Inkoopwijziging", "Voorstel", "Doorberekening", "Elasticiteit", "Pricing Power", "Concurrentiedruk", "PPFS", "Klasse", "Advies"].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.skus.map((s: any) => (
                <tr key={s.sku_id} className="border-t hover:bg-muted/30">
                  <td className="px-3 py-2 font-mono text-xs">{s.sku_id}</td>
                  <td className="px-3 py-2 max-w-[150px] truncate font-medium">{s.naam}</td>
                  <td className="px-3 py-2 text-orange-600 font-semibold">+{s.inkoopwijziging_pct?.toFixed(1)}%</td>
                  <td className="px-3 py-2 font-semibold">+{s.voorstel_pct?.toFixed(1)}%</td>
                  <td className="px-3 py-2">{(s.doorberekening_ratio * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2">{(s.elasticiteit * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2">{(s.pricing_power * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2">{(s.concurrentiedruk * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2">
                    <span className={`font-bold ${s.ppfs_score >= 0.7 ? "text-emerald-600" : s.ppfs_score >= 0.5 ? "text-blue-600" : s.ppfs_score >= 0.35 ? "text-yellow-600" : "text-red-600"}`}>
                      {(s.ppfs_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={`text-[10px] ${PPFS_COLORS[s.ppfs_label] || ""}`}>
                      {s.ppfs_label}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-xs">{ADVICE_NL[s.aanbeveling] || s.aanbeveling}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
