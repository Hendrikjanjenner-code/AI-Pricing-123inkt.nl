import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const BCG_BADGE: Record<string, string> = {
  STAR: "bg-yellow-100 text-yellow-800",
  CASH_COW: "bg-green-100 text-green-800",
  QUESTION_MARK: "bg-blue-100 text-blue-800",
  DOG: "bg-red-100 text-red-800",
};
const BCG_ICON: Record<string, string> = {
  STAR: "⭐",
  CASH_COW: "🐄",
  QUESTION_MARK: "❓",
  DOG: "🐕",
};
const TRIGGER_BADGE: Record<string, string> = {
  SKU_MOVED_TO_STAR: "bg-yellow-50 text-yellow-700 border border-yellow-200",
  SKU_MOVED_TO_DOG: "bg-red-50 text-red-700 border border-red-200",
  CATEGORY_MOVED_TO_CASH_COW: "bg-green-50 text-green-700 border border-green-200",
  PRIVATE_LABEL_BECAME_STAR: "bg-yellow-50 text-yellow-700 border border-yellow-200",
  PRICING_POWER_DECLINING: "bg-orange-50 text-orange-700 border border-orange-200",
  DEMAND_SHIFT_DETECTED: "bg-purple-50 text-purple-700 border border-purple-200",
};

export default function BcgTransities() {
  const [data, setData] = useState<any>(null);
  const [alerts, setAlerts] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any>(null);
  const [toFilter, setToFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");

  useEffect(() => {
    Promise.all([
      fetch(`${BASE}/api/bcg-transities`, { headers: { Authorization: `Bearer ${getToken()}` } }).then(r => r.json()),
      fetch(`${BASE}/api/bcg-transities/alerts`, { headers: { Authorization: `Bearer ${getToken()}` } }).then(r => r.json()),
    ]).then(([d, al]) => {
      setData(d);
      setAlerts(al);
      if (d.transities?.length) setSelected(d.transities[0]);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-gray-500">BCG transities laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden.</div>;

  const transities: any[] = (data.transities || []).filter((t: any) => {
    const matchTo = toFilter === "all" || t.naar === toFilter;
    const matchType = typeFilter === "all" || t.entiteit_type === typeFilter;
    return matchTo && matchType;
  });

  const klasseBar = [
    { name: "→ Star", count: data.naar_star || 0, fill: "#eab308" },
    { name: "→ Cash Cow", count: data.naar_cash_cow || 0, fill: "#22c55e" },
    { name: "→ Question?", count: data.naar_question_mark || 0, fill: "#3b82f6" },
    { name: "→ Dog", count: data.naar_dog || 0, fill: "#ef4444" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">BCG Transities</h1>
        <p className="text-gray-500 mt-1">BCG classificatiewijzigingen — wanneer, waarom, welk effect en aanbevolen actie</p>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Totaal transities", value: data.totaal },
          { label: "→ Star", value: data.naar_star, yellow: true },
          { label: "→ Dog", value: data.naar_dog, red: data.naar_dog > 0 },
          { label: "→ Cash Cow", value: data.naar_cash_cow, green: true },
          { label: "Totale omzetimpact", value: `€${(Math.abs(data.totale_omzetimpact_eur || 0)).toLocaleString("nl-NL", { maximumFractionDigits: 0 })}`, red: (data.totale_omzetimpact_eur || 0) < 0 },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border p-4 shadow-sm">
            <div className={`text-2xl font-bold ${(k as any).red ? "text-red-600" : (k as any).yellow ? "text-yellow-500" : (k as any).green ? "text-green-600" : "text-gray-900"}`}>{k.value}</div>
            <div className="text-sm font-medium text-gray-700">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Grafiek + Alerts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">Transities per doelklasse</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={klasseBar} layout="vertical" margin={{ left: 20, right: 20 }}>
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 12 }} width={80} />
              <Tooltip formatter={(v: any) => [v, "transities"]} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {klasseBar.map((e, i) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {alerts && (
          <div className="bg-white rounded-xl border p-4 shadow-sm">
            <h3 className="font-semibold text-gray-800 mb-3">Actieve alerts (30 dagen)</h3>
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: "Positief", value: alerts.positief_count, color: "text-green-600" },
                { label: "Negatief", value: alerts.negatief_count, color: "text-red-600" },
                { label: "Monitoren", value: alerts.aandacht_count, color: "text-blue-600" },
              ].map(k => (
                <div key={k.label} className="text-center">
                  <div className={`text-2xl font-bold ${k.color}`}>{k.value}</div>
                  <div className="text-xs text-gray-500">{k.label}</div>
                </div>
              ))}
            </div>
            <div className="space-y-2 max-h-[140px] overflow-y-auto">
              {(alerts.alerts || []).map((a: any, i: number) => (
                <div key={i} className={`flex items-center justify-between text-xs p-2 rounded ${
                  a.urgentie === "HOOG" ? "bg-red-50" : a.urgentie === "POSITIEF" ? "bg-green-50" : "bg-blue-50"
                }`}>
                  <span className="font-medium">{BCG_ICON[a.naar]} {a.entiteit} ({a.van} → {a.naar})</span>
                  <span className={a.omzet_impact_eur < 0 ? "text-red-600" : "text-green-600"}>
                    {a.omzet_impact_eur > 0 ? "+" : ""}€{Math.abs(a.omzet_impact_eur).toLocaleString("nl-NL", { maximumFractionDigits: 0 })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Transities lijst + Detail */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="p-3 border-b flex gap-2">
            <select className="border rounded px-2 py-1.5 text-sm flex-1" value={toFilter} onChange={e => setToFilter(e.target.value)}>
              <option value="all">Alle doelklassen</option>
              <option value="STAR">→ Star</option>
              <option value="CASH_COW">→ Cash Cow</option>
              <option value="QUESTION_MARK">→ Question Mark</option>
              <option value="DOG">→ Dog</option>
            </select>
            <select className="border rounded px-2 py-1.5 text-sm" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
              <option value="all">Alle types</option>
              <option value="SKU">SKU</option>
              <option value="CATEGORY">Categorie</option>
            </select>
          </div>
          <div className="divide-y divide-gray-100 max-h-[400px] overflow-y-auto">
            {transities.map((t: any) => (
              <div
                key={t.id}
                className={`p-4 cursor-pointer hover:bg-gray-50 ${selected?.id === t.id ? "bg-indigo-50" : ""}`}
                onClick={() => setSelected(t)}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm">{t.naam}</span>
                  <span className="text-xs text-gray-400">{t.datum}</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${BCG_BADGE[t.van] || ""}`}>{BCG_ICON[t.van]} {t.van}</span>
                  <span className="text-gray-400">→</span>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${BCG_BADGE[t.naar] || ""}`}>{BCG_ICON[t.naar]} {t.naar}</span>
                  <span className={`ml-auto text-xs font-semibold ${t.omzet_impact_eur < 0 ? "text-red-600" : "text-green-600"}`}>
                    {t.omzet_impact_eur > 0 ? "+" : ""}€{Math.abs(t.omzet_impact_eur).toLocaleString("nl-NL", { maximumFractionDigits: 0 })}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {selected && (
          <div className="bg-white rounded-xl border shadow-sm p-5 space-y-4">
            <div>
              <h3 className="text-lg font-bold text-gray-900">{selected.naam}</h3>
              <div className="text-xs text-gray-500">{selected.entiteit_type} · {selected.categorie} · {selected.datum}</div>
            </div>

            <div className="flex items-center gap-4">
              <div className="text-center">
                <div className={`inline-flex px-3 py-1.5 rounded-lg text-sm font-medium ${BCG_BADGE[selected.van] || ""}`}>{BCG_ICON[selected.van]} {selected.van}</div>
                <div className="text-xs text-gray-400 mt-1">Groei: {Math.round((selected.van_groei || 0) * 100)}%</div>
              </div>
              <div className="text-2xl text-gray-400">→</div>
              <div className="text-center">
                <div className={`inline-flex px-3 py-1.5 rounded-lg text-sm font-medium ${BCG_BADGE[selected.naar] || ""}`}>{BCG_ICON[selected.naar]} {selected.naar}</div>
                <div className="text-xs text-gray-400 mt-1">Groei: {Math.round((selected.naar_groei || 0) * 100)}%</div>
              </div>
            </div>

            <div>
              <span className={`inline-flex px-3 py-1 rounded-full text-xs font-medium ${TRIGGER_BADGE[selected.trigger_code] || "bg-gray-100 text-gray-700"}`}>
                {selected.trigger_code}
              </span>
            </div>

            <div>
              <div className="text-xs font-medium text-gray-500 uppercase mb-1">Oorzaak</div>
              <p className="text-sm text-gray-700">{selected.oorzaak}</p>
            </div>

            <div className="bg-gray-50 rounded-lg p-3">
              <div className="text-xs font-medium text-gray-500 uppercase mb-1">Business impact</div>
              <p className="text-sm text-gray-700">{selected.impact}</p>
              <div className={`text-lg font-bold mt-1 ${selected.omzet_impact_eur < 0 ? "text-red-600" : "text-green-600"}`}>
                {selected.omzet_impact_eur > 0 ? "+" : ""}€{Math.abs(selected.omzet_impact_eur).toLocaleString("nl-NL", { maximumFractionDigits: 0 })}
              </div>
            </div>

            <div className="bg-indigo-50 rounded-lg p-3 border border-indigo-100">
              <div className="text-xs font-medium text-indigo-600 uppercase mb-1">Aanbevolen actie</div>
              <p className="text-sm text-indigo-800">{selected.aanbeveling}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
