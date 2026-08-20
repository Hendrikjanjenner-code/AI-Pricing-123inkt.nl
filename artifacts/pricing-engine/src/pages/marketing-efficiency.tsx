import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const SIG_BADGE: Record<string, string> = {
  LOW_ROAS: "bg-red-100 text-red-800",
  HIGH_CAC: "bg-orange-100 text-orange-800",
  MARKETING_DEPENDENT: "bg-yellow-100 text-yellow-800",
  EFFICIENT: "bg-green-100 text-green-800",
  NORMAAL: "bg-blue-100 text-blue-800",
};

export default function MarketingEfficiency() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoek, setZoek] = useState("");
  const [sortBy, setSortBy] = useState("roas");
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);

  useEffect(() => {
    setLoading(true);
    const url = `${BASE}/api/kosten/marketing`;
    fetch(url + (fp !== "" ? (url.includes("?") ? "&" : "?") + fp : ""), { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [fp]);

  if (loading) return <div className="p-8 text-gray-500">Marketing data laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden.</div>;

  const skus: any[] = [...(data.skus || [])]
    .filter((s: any) => !zoek || s.naam?.toLowerCase().includes(zoek.toLowerCase()) || s.sku_id?.toLowerCase().includes(zoek.toLowerCase()))
    .sort((a: any, b: any) => {
      if (sortBy === "roas") return b.roas - a.roas;
      if (sortBy === "cac") return a.cac - b.cac;
      if (sortBy === "mds") return b.marketing_dependency - a.marketing_dependency;
      return b.contribution_margin_pct - a.contribution_margin_pct;
    });

  const roasBar = [...(data.skus || [])].slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    roas: s.roas,
    fill: s.roas >= 5 ? "#22c55e" : s.roas >= 3 ? "#f97316" : "#ef4444",
  }));

  const effBar = [...(data.skus || [])].slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    seo: Math.round((s.seo_efficiency || 0) * 100),
    sea: Math.round((s.sea_efficiency || 0) * 100),
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Marketing Efficiency</h1>
        <p className="text-gray-500 mt-1">CAC, ROAS, SEO/SEA efficiëntie en contributie marge per SKU</p>
      </div>
      <GlobalFilterBar />

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Gem. ROAS", value: `${(data.gemiddelde_roas || 0).toFixed(2)}×`, ok: data.gemiddelde_roas >= 3 },
          { label: "Gem. CAC", value: `€${(data.gemiddelde_cac || 0).toFixed(2)}`, ok: data.gemiddelde_cac < 5 },
          { label: "SEO Efficiency", value: `${Math.round((data.gemiddelde_seo_efficiency || 0) * 100)}%` },
          { label: "SEA Efficiency", value: `${Math.round((data.gemiddelde_sea_efficiency || 0) * 100)}%` },
          { label: "Totale marketingkosten", value: `€${(data.totale_marketing_kosten || 0).toFixed(0)}`, sub: "vandaag" },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border p-4 shadow-sm">
            <div className={`text-2xl font-bold ${k.ok === false ? "text-red-600" : k.ok === true ? "text-green-600" : "text-gray-900"}`}>{k.value}</div>
            <div className="text-sm font-medium text-gray-700">{k.label}</div>
            {(k as any).sub && <div className="text-xs text-gray-400">{(k as any).sub}</div>}
          </div>
        ))}
      </div>

      {/* Grafieken */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">ROAS per SKU</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={roasBar} margin={{ top: 4, right: 8, left: 0, bottom: 20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: 11 }} unit="×" />
              <Tooltip formatter={(v: any) => [`${Number(v).toFixed(2)}×`, "ROAS"]} />
              <Bar dataKey="roas" radius={[3, 3, 0, 0]}>
                {roasBar.map((e, i) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">SEO vs SEA efficiency (%)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={effBar} margin={{ top: 4, right: 8, left: 0, bottom: 20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, ""]} />
              <Bar dataKey="seo" name="SEO" fill="#6366f1" radius={[3, 3, 0, 0]} />
              <Bar dataKey="sea" name="SEA" fill="#a78bfa" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* SKU tabel */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b flex flex-col sm:flex-row gap-3">
          <input
            className="border rounded px-3 py-1.5 text-sm flex-1"
            placeholder="Zoek op SKU of naam…"
            value={zoek}
            onChange={e => setZoek(e.target.value)}
          />
          <select className="border rounded px-3 py-1.5 text-sm" value={sortBy} onChange={e => setSortBy(e.target.value)}>
            <option value="roas">Sorteer: ROAS (hoog → laag)</option>
            <option value="cac">Sorteer: CAC (laag → hoog)</option>
            <option value="mds">Sorteer: Marketing dependency</option>
            <option value="cm">Sorteer: Contributie marge</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">SKU</th>
                <th className="px-4 py-3 text-left">Naam</th>
                <th className="px-4 py-3 text-right">ROAS</th>
                <th className="px-4 py-3 text-right">CAC</th>
                <th className="px-4 py-3 text-right">SEO Eff.</th>
                <th className="px-4 py-3 text-right">SEA Eff.</th>
                <th className="px-4 py-3 text-right">Dep. score</th>
                <th className="px-4 py-3 text-right">CM%</th>
                <th className="px-4 py-3 text-left">Signaal</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {skus.map((s: any) => (
                <tr key={s.sku_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">{s.sku_id}</td>
                  <td className="px-4 py-3 max-w-[180px] truncate font-medium text-gray-900">{s.naam}</td>
                  <td className={`px-4 py-3 text-right font-semibold ${s.roas < 2 ? "text-red-600" : s.roas >= 5 ? "text-green-600" : "text-orange-500"}`}>{(s.roas || 0).toFixed(2)}×</td>
                  <td className="px-4 py-3 text-right">€{(s.cac || 0).toFixed(2)}</td>
                  <td className="px-4 py-3 text-right">{Math.round((s.seo_efficiency || 0) * 100)}%</td>
                  <td className="px-4 py-3 text-right">{Math.round((s.sea_efficiency || 0) * 100)}%</td>
                  <td className="px-4 py-3 text-right">{Math.round((s.marketing_dependency || 0) * 100)}%</td>
                  <td className={`px-4 py-3 text-right font-semibold ${s.contribution_margin_pct < 0 ? "text-red-600" : "text-green-600"}`}>{(s.contribution_margin_pct || 0).toFixed(1)}%</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${SIG_BADGE[s.signaal] || "bg-gray-100 text-gray-600"}`}>
                      {s.signaal}
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

