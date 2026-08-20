import { useState, useEffect } from "react";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from "recharts";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const OCS_BADGE: Record<string, string> = {
  LAAG: "bg-green-100 text-green-800",
  GEMIDDELD: "bg-blue-100 text-blue-800",
  HOOG: "bg-orange-100 text-orange-800",
  KRITIEK: "bg-red-100 text-red-800",
};
const OCS_COLOR: Record<string, string> = {
  LAAG: "#22c55e",
  GEMIDDELD: "#3b82f6",
  HOOG: "#f97316",
  KRITIEK: "#ef4444",
};

export default function OperationeleComplexiteit() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any>(null);
  const [zoek, setZoek] = useState("");
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);

  useEffect(() => {
    setLoading(true);
    const url = `${BASE}/api/kosten/operationeel`;
    fetch(url + (fp !== "" ? (url.includes("?") ? "&" : "?") + fp : ""), { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json())
      .then(d => {
        setData(d);
        if (d.skus?.length) setSelected(d.skus[0]);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [fp]);

  if (loading) return <div className="p-8 text-gray-500">OCS laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden.</div>;

  const skus: any[] = (data.skus || []).filter((s: any) =>
    !zoek || s.naam?.toLowerCase().includes(zoek.toLowerCase()) || s.sku_id?.toLowerCase().includes(zoek.toLowerCase())
  );

  const radarData = selected ? [
    { subject: "Picktijd", score: Math.round((selected.pick_time || 0) * 100) },
    { subject: "Verpakking", score: Math.round((selected.packaging_time || 0) * 100) },
    { subject: "Retourdruk", score: Math.round((selected.retourdruk || 0) * 100) },
    { subject: "Klantenservice", score: Math.round((selected.klantenservice || 0) * 100) },
    { subject: "Handling", score: Math.round((selected.handling || 0) * 100) },
    { subject: "Personeel", score: Math.round((selected.personeelskosten || 0) * 100) },
  ] : [];

  const ocsBar = (data.skus || []).slice(0, 14).map((s: any) => ({
    name: s.sku_id,
    ocs: Math.round((s.ocs_score || 0) * 100),
    fill: OCS_COLOR[s.ocs_label] || "#6366f1",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Operationele Complexiteit</h1>
        <p className="text-gray-500 mt-1">Activity-Based Costing (ABC) — OCS per SKU op 8 factoren</p>
      </div>
      <GlobalFilterBar />

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Totaal SKU's", value: data.totaal_skus },
          { label: "Gem. OCS", value: `${Math.round((data.gemiddelde_ocs || 0) * 100)}%` },
          { label: "Kritiek", value: data.kritiek_count, red: data.kritiek_count > 0 },
          { label: "Hoog", value: data.hoog_count, orange: data.hoog_count > 3 },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border p-4 shadow-sm">
            <div className={`text-2xl font-bold ${(k as any).red ? "text-red-600" : (k as any).orange ? "text-orange-500" : "text-gray-900"}`}>{k.value}</div>
            <div className="text-sm font-medium text-gray-700">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Grafiek + Radar */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">OCS score per SKU (%)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={ocsBar} margin={{ top: 4, right: 8, left: 0, bottom: 20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, "OCS"]} />
              <Bar dataKey="ocs" radius={[3, 3, 0, 0]}>
                {ocsBar.map((e: any, i: number) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-2">
            Radaranalyse — {selected?.naam || "—"}
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <RadarChart data={radarData}>
              <PolarGrid />
              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10 }} />
              <Radar dataKey="score" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Tabel */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b">
          <input
            className="border rounded px-3 py-1.5 text-sm w-full"
            placeholder="Zoek op SKU of naam…"
            value={zoek}
            onChange={e => setZoek(e.target.value)}
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">SKU</th>
                <th className="px-4 py-3 text-left">Naam</th>
                <th className="px-4 py-3 text-left">Categorie</th>
                <th className="px-4 py-3 text-right">OCS score</th>
                <th className="px-4 py-3 text-left">Niveau</th>
                <th className="px-4 py-3 text-right">Personeelskosten/eenheid</th>
                <th className="px-4 py-3 text-left">Aanbeveling</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {skus.map((s: any) => (
                <tr
                  key={s.sku_id}
                  className={`hover:bg-gray-50 cursor-pointer ${selected?.sku_id === s.sku_id ? "bg-indigo-50" : ""}`}
                  onClick={() => setSelected(s)}
                >
                  <td className="px-4 py-3 font-mono text-xs">{s.sku_id}</td>
                  <td className="px-4 py-3 font-medium max-w-[180px] truncate">{s.naam}</td>
                  <td className="px-4 py-3 text-xs text-gray-500">{s.categorie}</td>
                  <td className="px-4 py-3 text-right font-semibold">{Math.round((s.ocs_score || 0) * 100)}%</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${OCS_BADGE[s.ocs_label] || ""}`}>{s.ocs_label}</span>
                  </td>
                  <td className="px-4 py-3 text-right">€{(s.personeelskosten || 0).toFixed(3)}</td>
                  <td className="px-4 py-3 text-xs text-gray-600 max-w-[220px] truncate">{s.aanbeveling}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
