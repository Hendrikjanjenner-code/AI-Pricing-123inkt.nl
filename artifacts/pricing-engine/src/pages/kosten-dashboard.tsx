import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from "recharts";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const SIGNAL_BADGE: Record<string, string> = {
  MARGIN_CRITICAL: "bg-red-100 text-red-800",
  MARGIN_LOW: "bg-orange-100 text-orange-800",
  COST_RISING: "bg-yellow-100 text-yellow-800",
  HEALTHY: "bg-green-100 text-green-800",
};
const SIGNAL_LABEL: Record<string, string> = {
  MARGIN_CRITICAL: "Kritieke marge",
  MARGIN_LOW: "Lage marge",
  COST_RISING: "Kosten stijgend",
  HEALTHY: "Gezond",
};

const KOSTEN_COLORS = ["#6366f1","#8b5cf6","#a78bfa","#c4b5fd","#ddd6fe","#ede9fe","#f5f3ff","#f0fdf4","#bbf7d0"];

export default function KostenDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoek, setZoek] = useState("");
  const [signaalFilter, setSignaalFilter] = useState("all");

  useEffect(() => {
    fetch(`${BASE}/api/kosten`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-gray-500">Kosten laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden kostendata.</div>;

  const kv = data.kostenverdeling || {};
  const kostenPie = [
    { name: "Inkoop", value: kv.inkoop || 0 },
    { name: "Transport", value: kv.transport || 0 },
    { name: "Dropshipping", value: kv.dropshipping || 0 },
    { name: "Fulfilment", value: kv.fulfilment || 0 },
    { name: "Verpakking", value: kv.verpakking || 0 },
    { name: "Personeel", value: kv.personeel || 0 },
    { name: "Marketplace", value: kv.marketplace || 0 },
    { name: "Retouren", value: kv.retouren || 0 },
    { name: "Overhead", value: kv.overhead || 0 },
  ].filter(i => i.value > 0);

  const skus: any[] = (data.skus || [])
    .filter((s: any) => {
      const matchZoek = !zoek || s.naam?.toLowerCase().includes(zoek.toLowerCase()) || s.sku_id?.toLowerCase().includes(zoek.toLowerCase());
      const matchSig = signaalFilter === "all" || s.signaal === signaalFilter;
      return matchZoek && matchSig;
    });

  const margeBar = [...(data.skus || [])].slice(0, 12).map((s: any) => ({
    name: s.sku_id,
    marge: s.netto_marge_pct,
    fill: s.netto_marge_pct < 5 ? "#ef4444" : s.netto_marge_pct < 12 ? "#f97316" : "#22c55e",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Kosten Intelligence</h1>
        <p className="text-gray-500 mt-1">Volledige kostenstructuur per SKU — directe en indirecte kosten</p>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Totaal SKU's", value: data.totaal_skus, sub: "geanalyseerd" },
          { label: "Gem. netto marge", value: `${(data.gemiddelde_netto_marge_pct || 0).toFixed(1)}%`, sub: "over alle SKU's", red: data.gemiddelde_netto_marge_pct < 12 },
          { label: "Kritieke marge", value: data.kritieke_marge_count, sub: "< 5% netto", red: data.kritieke_marge_count > 0 },
          { label: "Lage marge", value: data.lage_marge_count, sub: "< 12% netto", red: data.lage_marge_count > 3 },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border p-4 shadow-sm">
            <div className={`text-2xl font-bold ${k.red ? "text-red-600" : "text-gray-900"}`}>{k.value}</div>
            <div className="text-sm font-medium text-gray-700">{k.label}</div>
            <div className="text-xs text-gray-400">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Grafieken */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">Netto marge per SKU (%)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={margeBar} margin={{ top: 4, right: 8, left: 0, bottom: 20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${Number(v).toFixed(1)}%`, "Netto marge"]} />
              <Bar dataKey="marge" radius={[3, 3, 0, 0]}>
                {margeBar.map((e, i) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">Kostenverdeling (gem. per eenheid €)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={kostenPie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {kostenPie.map((_: any, i: number) => <Cell key={i} fill={KOSTEN_COLORS[i % KOSTEN_COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v: any) => [`€${Number(v).toFixed(3)}`, ""]} />
            </PieChart>
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
          <select
            className="border rounded px-3 py-1.5 text-sm"
            value={signaalFilter}
            onChange={e => setSignaalFilter(e.target.value)}
          >
            <option value="all">Alle signalen</option>
            <option value="MARGIN_CRITICAL">Kritieke marge</option>
            <option value="MARGIN_LOW">Lage marge</option>
            <option value="COST_RISING">Kosten stijgend</option>
            <option value="HEALTHY">Gezond</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">SKU</th>
                <th className="px-4 py-3 text-left">Naam</th>
                <th className="px-4 py-3 text-left">Categorie</th>
                <th className="px-4 py-3 text-right">Verkoopprijs</th>
                <th className="px-4 py-3 text-right">Totale kosten</th>
                <th className="px-4 py-3 text-right">Netto marge</th>
                <th className="px-4 py-3 text-left">Signaal</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {skus.map((s: any) => (
                <tr key={s.sku_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{s.sku_id}</td>
                  <td className="px-4 py-3 font-medium text-gray-900 max-w-[200px] truncate">{s.naam}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{s.categorie}</td>
                  <td className="px-4 py-3 text-right">€{(s.verkoopprijs || 0).toFixed(2)}</td>
                  <td className="px-4 py-3 text-right">€{(s.totale_kosten || 0).toFixed(2)}</td>
                  <td className={`px-4 py-3 text-right font-semibold ${s.netto_marge_pct < 5 ? "text-red-600" : s.netto_marge_pct < 12 ? "text-orange-500" : "text-green-600"}`}>
                    {(s.netto_marge_pct || 0).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${SIGNAL_BADGE[s.signaal] || "bg-gray-100 text-gray-600"}`}>
                      {SIGNAL_LABEL[s.signaal] || s.signaal}
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
