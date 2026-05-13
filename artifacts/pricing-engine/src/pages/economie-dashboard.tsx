import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const ERNST_BADGE: Record<string, string> = {
  KRITIEK: "bg-red-100 text-red-800 border border-red-200",
  HOOG: "bg-orange-100 text-orange-800 border border-orange-200",
  GEMIDDELD: "bg-yellow-100 text-yellow-800 border border-yellow-200",
  LAAG: "bg-green-100 text-green-800 border border-green-200",
};
const ERNST_COLOR: Record<string, string> = {
  KRITIEK: "#ef4444",
  HOOG: "#f97316",
  GEMIDDELD: "#eab308",
  LAAG: "#22c55e",
};
const TYPE_ICON: Record<string, string> = {
  RAW_MATERIAL: "⛏️",
  TRANSPORT: "🚢",
  CURRENCY: "💱",
  GEOPOLITICAL: "🌍",
  INFLATION: "📈",
  SUPPLY_CHAIN: "⛓️",
  PANDEMIC: "🦠",
};

export default function EconomieDashboard() {
  const [data, setData] = useState<any>(null);
  const [impact, setImpact] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any>(null);
  const [ernstFilter, setErnstFilter] = useState("all");

  useEffect(() => {
    Promise.all([
      fetch(`${BASE}/api/economie`, { headers: { Authorization: `Bearer ${getToken()}` } }).then(r => r.json()),
      fetch(`${BASE}/api/economie/impact`, { headers: { Authorization: `Bearer ${getToken()}` } }).then(r => r.json()),
    ]).then(([d, imp]) => {
      setData(d);
      setImpact(imp);
      if (d.signalen?.length) setSelected(d.signalen[0]);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-gray-500">Economische data laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden.</div>;

  const signalen: any[] = (data.signalen || []).filter((s: any) =>
    ernstFilter === "all" || s.ernst === ernstFilter
  );

  const impactBar = (impact?.impact_per_type || []).map((t: any) => ({
    name: t.type,
    prijsimpact: Math.abs(t.totale_prijsimpact_pct || 0),
    margeimpact: Math.abs(t.totale_margeimpact_pct || 0),
  }));

  const severityBar = [
    { name: "Kritiek", count: data.kritiek_count || 0, fill: "#ef4444" },
    { name: "Hoog", count: data.hoog_count || 0, fill: "#f97316" },
    { name: "Gemiddeld", count: data.gemiddeld_count || 0, fill: "#eab308" },
    { name: "Laag", count: data.laag_count || 0, fill: "#22c55e" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Economic Intelligence</h1>
        <p className="text-gray-500 mt-1">Externe economische signalen — impact op pricing, procurement en marges</p>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Actieve signalen", value: data.totaal_actieve_signalen },
          { label: "Kritiek", value: data.kritiek_count, red: data.kritiek_count > 0 },
          { label: "Hoog risico", value: data.hoog_count, orange: data.hoog_count > 0 },
          { label: "Max. prijsimpact", value: `+${(data.maximale_prijsimpact_pct || 0).toFixed(1)}%`, red: data.maximale_prijsimpact_pct > 10 },
          { label: "Gem. margeimpact", value: `${(data.gemiddelde_margeimpact_pct || 0).toFixed(1)}%`, red: data.gemiddelde_margeimpact_pct < -5 },
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
          <h3 className="font-semibold text-gray-800 mb-4">Ernst verdeling</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={severityBar} layout="vertical" margin={{ left: 20, right: 20 }}>
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 12 }} width={70} />
              <Tooltip formatter={(v: any) => [v, "signalen"]} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {severityBar.map((e, i) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">Prijsimpact per type (%)</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={impactBar} margin={{ top: 4, right: 8, left: 0, bottom: 20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${Number(v).toFixed(1)}%`, ""]} />
              <Bar dataKey="prijsimpact" name="Prijsimpact" fill="#ef4444" radius={[3, 3, 0, 0]} />
              <Bar dataKey="margeimpact" name="Margeimpact" fill="#f97316" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Signalen + detail */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Signalen lijst */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="p-4 border-b flex gap-3">
            <select className="border rounded px-3 py-1.5 text-sm" value={ernstFilter} onChange={e => setErnstFilter(e.target.value)}>
              <option value="all">Alle ernst</option>
              <option value="KRITIEK">Kritiek</option>
              <option value="HOOG">Hoog</option>
              <option value="GEMIDDELD">Gemiddeld</option>
              <option value="LAAG">Laag</option>
            </select>
          </div>
          <div className="divide-y divide-gray-100 max-h-[420px] overflow-y-auto">
            {signalen.map((s: any) => (
              <div
                key={s.id}
                className={`p-4 cursor-pointer hover:bg-gray-50 ${selected?.id === s.id ? "bg-indigo-50" : ""}`}
                onClick={() => setSelected(s)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{TYPE_ICON[s.type] || "⚠️"}</span>
                    <span className="font-medium text-sm text-gray-900">{s.naam}</span>
                  </div>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${ERNST_BADGE[s.ernst] || ""}`}>{s.ernst}</span>
                </div>
                <div className="mt-1 text-xs text-gray-500 flex gap-3">
                  <span>📍 {s.regio}</span>
                  <span>📊 Prijsimpact: +{(s.prijsimpact_pct || 0).toFixed(1)}%</span>
                  <span>📉 Margeimpact: {(s.margeimpact_pct || 0).toFixed(1)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="bg-white rounded-xl border shadow-sm p-5 space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-xl font-bold text-gray-900">{TYPE_ICON[selected.type] || "⚠️"} {selected.naam}</div>
                <div className="text-sm text-gray-500 mt-0.5">{selected.regio} · {selected.type}</div>
              </div>
              <span className={`inline-flex px-3 py-1 rounded-full text-sm font-medium ${ERNST_BADGE[selected.ernst] || ""}`}>{selected.ernst}</span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Huidige waarde", value: `${selected.huidige_waarde} ${selected.eenheid}` },
                { label: "Baseline", value: `${selected.baseline_waarde} ${selected.eenheid}` },
                { label: "Verandering", value: `${selected.verandering_pct > 0 ? "+" : ""}${(selected.verandering_pct || 0).toFixed(1)}%`, red: selected.verandering_pct > 0 },
                { label: "Inkoop urgentie", value: selected.inkoop_urgentie },
              ].map(i => (
                <div key={i.label} className="bg-gray-50 rounded-lg p-3">
                  <div className="text-xs text-gray-500">{i.label}</div>
                  <div className={`font-semibold text-sm ${(i as any).red ? "text-red-600" : "text-gray-900"}`}>{i.value}</div>
                </div>
              ))}
            </div>

            <div>
              <div className="text-xs font-medium text-gray-500 uppercase mb-1">Beschrijving</div>
              <p className="text-sm text-gray-700">{selected.beschrijving}</p>
            </div>

            <div className="bg-orange-50 rounded-lg p-3 border border-orange-100">
              <div className="text-xs font-medium text-orange-700 uppercase mb-1">Aanbevolen actie</div>
              <p className="text-sm text-orange-800">{selected.aanbeveling}</p>
            </div>

            <div className="text-xs text-gray-400">Geldig tot: {selected.geldig_tot || "onbekend"}</div>
          </div>
        )}
      </div>

      {/* Directe actie */}
      {impact?.direct_actie_vereist?.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <h3 className="font-semibold text-red-800 mb-3">⚠️ Directe actie vereist</h3>
          <div className="space-y-2">
            {impact.direct_actie_vereist.map((a: any, i: number) => (
              <div key={i} className="flex items-start gap-2 text-sm">
                <span className="text-red-500 font-bold">→</span>
                <div>
                  <span className="font-medium text-red-800">{a.signaal}</span>
                  <span className="text-red-700"> — {a.aanbeveling}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
