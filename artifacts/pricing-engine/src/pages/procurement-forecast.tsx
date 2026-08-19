import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const SIG_BADGE: Record<string, string> = {
  URGENT_BUY: "bg-red-100 text-red-800",
  BUY_NOW: "bg-orange-100 text-orange-800",
  MARGIN_RISK: "bg-yellow-100 text-yellow-800",
  MONITOR: "bg-blue-100 text-blue-800",
  STABLE: "bg-green-100 text-green-800",
};
const SIG_LABEL: Record<string, string> = {
  URGENT_BUY: "Urgente inkoop",
  BUY_NOW: "Nu inkopen",
  MARGIN_RISK: "Margerisico",
  MONITOR: "Monitoren",
  STABLE: "Stabiel",
};

export default function ProcurementForecast() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoek, setZoek] = useState("");
  const [sortBy, setSortBy] = useState("pos");

  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  useEffect(() => {
    setLoading(true);
    fetch(`${BASE}/api/procurement${filterQs ? `?${filterQs}` : ""}`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [filterQs]);

  if (loading) return <div className="p-8 text-gray-500">Procurement data laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden.</div>;

  const skus: any[] = [...(data.skus || [])]
    .filter((s: any) => !zoek || s.naam?.toLowerCase().includes(zoek.toLowerCase()) || s.sku_id?.toLowerCase().includes(zoek.toLowerCase()))
    .sort((a: any, b: any) => {
      if (sortBy === "pos") return b.pos - a.pos;
      if (sortBy === "fmr") return b.fmr - a.fmr;
      return b.prijswijziging_90d_pct - a.prijswijziging_90d_pct;
    });

  const posBar = [...(data.skus || [])].slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    pos: Math.round((s.pos || 0) * 100),
    fmr: Math.round((s.fmr || 0) * 100),
  }));

  const prijsBar = [...(data.skus || [])]
    .sort((a: any, b: any) => b.prijswijziging_90d_pct - a.prijswijziging_90d_pct)
    .slice(0, 10)
    .map((s: any) => ({
      name: s.sku_id,
      pct: s.prijswijziging_90d_pct || 0,
      fill: s.prijswijziging_90d_pct > 10 ? "#ef4444" : s.prijswijziging_90d_pct > 5 ? "#f97316" : "#22c55e",
    }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Procurement Forecast</h1>
        <p className="text-gray-500 mt-1">Inkoopkansen (POS) en toekomstig margerisico (FMR) per SKU — 30 en 90 dagen horizon</p>
      </div>

      <GlobalFilterBar />

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Totaal SKU's", value: data.totaal_skus },
          { label: "Gem. POS", value: `${Math.round((data.gemiddelde_pos || 0) * 100)}%` },
          { label: "Gem. FMR", value: `${Math.round((data.gemiddelde_fmr || 0) * 100)}%`, red: data.gemiddelde_fmr > 0.6 },
          { label: "Nu inkopen", value: data.koop_nu_count, orange: true },
          { label: "Aanbevolen investering", value: `€${(data.totale_aanbevolen_investering_eur || 0).toLocaleString("nl-NL", { maximumFractionDigits: 0 })}` },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border p-4 shadow-sm">
            <div className={`text-2xl font-bold ${(k as any).red ? "text-red-600" : (k as any).orange ? "text-orange-500" : "text-gray-900"}`}>{k.value}</div>
            <div className="text-sm font-medium text-gray-700">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Grafieken */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">POS vs FMR per SKU (%)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={posBar} margin={{ top: 4, right: 8, left: 0, bottom: 20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any, name: string) => [`${v}%`, name === "pos" ? "Inkoopkans (POS)" : "Margerisico (FMR)"]} />
              <Bar dataKey="pos" name="POS" fill="#6366f1" radius={[3, 3, 0, 0]} />
              <Bar dataKey="fmr" name="FMR" fill="#f97316" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">Verwachte prijsstijging 90d (%)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={prijsBar} margin={{ top: 4, right: 8, left: 0, bottom: 20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${Number(v).toFixed(1)}%`, "Prijswijziging"]} />
              <Bar dataKey="pct" radius={[3, 3, 0, 0]}>
                {prijsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* SKU tabel */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b flex gap-3">
          <input className="border rounded px-3 py-1.5 text-sm flex-1" placeholder="Zoek SKU of naam…" value={zoek} onChange={e => setZoek(e.target.value)} />
          <select className="border rounded px-3 py-1.5 text-sm" value={sortBy} onChange={e => setSortBy(e.target.value)}>
            <option value="pos">Sorteer: Inkoopkans (POS)</option>
            <option value="fmr">Sorteer: Margerisico (FMR)</option>
            <option value="prijs">Sorteer: Prijsstijging 90d</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">SKU</th>
                <th className="px-4 py-3 text-left">Naam</th>
                <th className="px-4 py-3 text-right">Huid. inkoopprijs</th>
                <th className="px-4 py-3 text-right">Forecast 90d</th>
                <th className="px-4 py-3 text-right">Stijging 90d</th>
                <th className="px-4 py-3 text-right">POS</th>
                <th className="px-4 py-3 text-right">FMR</th>
                <th className="px-4 py-3 text-right">Order qty</th>
                <th className="px-4 py-3 text-left">Signaal</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {skus.map((s: any) => (
                <tr key={s.sku_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">{s.sku_id}</td>
                  <td className="px-4 py-3 font-medium max-w-[180px] truncate">{s.naam}</td>
                  <td className="px-4 py-3 text-right">€{(s.huidige_inkoopprijs || 0).toFixed(2)}</td>
                  <td className="px-4 py-3 text-right">€{(s.forecast_prijs_90d || 0).toFixed(2)}</td>
                  <td className={`px-4 py-3 text-right font-semibold ${s.prijswijziging_90d_pct > 10 ? "text-red-600" : s.prijswijziging_90d_pct > 5 ? "text-orange-500" : "text-green-600"}`}>
                    +{(s.prijswijziging_90d_pct || 0).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-indigo-600">{Math.round((s.pos || 0) * 100)}%</td>
                  <td className={`px-4 py-3 text-right font-semibold ${s.fmr > 0.65 ? "text-red-600" : "text-gray-700"}`}>{Math.round((s.fmr || 0) * 100)}%</td>
                  <td className="px-4 py-3 text-right">{s.aanbevolen_order || 0}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${SIG_BADGE[s.signaal_code] || "bg-gray-100 text-gray-700"}`}>
                      {SIG_LABEL[s.signaal_code] || s.signaal_code}
                    </span>
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
