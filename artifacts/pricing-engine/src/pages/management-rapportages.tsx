import { useState, useEffect } from "react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

const TYPE_BADGE: Record<string, string> = {
  DAGELIJKS: "bg-blue-100 text-blue-800",
  WEKELIJKS: "bg-purple-100 text-purple-800",
  MAANDELIJKS: "bg-indigo-100 text-indigo-800",
};
const TYPE_ICON: Record<string, string> = {
  DAGELIJKS: "📅",
  WEKELIJKS: "📆",
  MAANDELIJKS: "🗓️",
};

export default function ManagementRapportages() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any>(null);
  const [generating, setGenerating] = useState(false);
  const [typeFilter, setTypeFilter] = useState("all");

  const load = () => {
    setLoading(true);
    fetch(`${BASE}/api/rapportages`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json())
      .then(d => {
        setData(d);
        if (d.rapportages?.length && !selected) setSelected(d.rapportages[0]);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const genereer = async () => {
    setGenerating(true);
    await fetch(`${BASE}/api/rapportages/genereer`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    setGenerating(false);
    load();
  };

  const exportRapportage = async (id: number) => {
    const res = await fetch(`${BASE}/api/rapportages/export/${id}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    const blob = await res.json();
    const url = URL.createObjectURL(new Blob([JSON.stringify(blob, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `rapportage_${id}.json`;
    a.click();
  };

  if (loading && !data) return <div className="p-8 text-gray-500">Rapportages laden…</div>;

  const rapportages: any[] = (data?.rapportages || []).filter((r: any) =>
    typeFilter === "all" || r.type === typeFilter
  );

  const kpiEntries = selected?.kpis ? Object.entries(selected.kpis) : [];
  const alerts: any[] = selected?.alerts || [];
  const inzichten: any[] = selected?.inzichten || [];
  const aanbevelingen: any[] = selected?.aanbevelingen || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Management Rapportages</h1>
          <p className="text-gray-500 mt-1">Automatisch gegenereerde dagelijkse, wekelijkse en maandelijkse rapportages</p>
        </div>
        <button
          onClick={genereer}
          disabled={generating}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {generating ? "Genereren…" : "Genereer rapportages"}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Lijst */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="p-3 border-b">
            <select className="border rounded px-3 py-1.5 text-sm w-full" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
              <option value="all">Alle types</option>
              <option value="DAGELIJKS">Dagelijks</option>
              <option value="WEKELIJKS">Wekelijks</option>
              <option value="MAANDELIJKS">Maandelijks</option>
            </select>
          </div>
          <div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">
            {rapportages.length === 0 && (
              <div className="p-4 text-sm text-gray-500 text-center">
                Geen rapportages. Klik op "Genereer" om te starten.
              </div>
            )}
            {rapportages.map((r: any) => (
              <div
                key={r.id}
                className={`p-4 cursor-pointer hover:bg-gray-50 ${selected?.id === r.id ? "bg-indigo-50 border-l-2 border-indigo-500" : ""}`}
                onClick={() => setSelected(r)}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TYPE_BADGE[r.type] || ""}`}>
                    {TYPE_ICON[r.type]} {r.type}
                  </span>
                  {r.geexporteerd && <span className="text-xs text-gray-400">Geëxporteerd</span>}
                </div>
                <div className="text-sm font-medium text-gray-900 mt-1">{r.rapport_datum}</div>
                <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{r.samenvatting}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Detail */}
        <div className="md:col-span-2 space-y-4">
          {!selected ? (
            <div className="bg-white rounded-xl border p-8 text-center text-gray-400">Selecteer een rapportage</div>
          ) : (
            <>
              <div className="bg-white rounded-xl border shadow-sm p-5">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h2 className="text-lg font-bold text-gray-900">{selected.titel}</h2>
                    <p className="text-sm text-gray-500 mt-1">{selected.samenvatting}</p>
                  </div>
                  <button
                    onClick={() => exportRapportage(selected.id)}
                    className="px-3 py-1.5 border rounded text-xs font-medium text-gray-600 hover:bg-gray-50"
                  >
                    Exporteer JSON
                  </button>
                </div>

                {/* KPI's */}
                {kpiEntries.length > 0 && (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
                    {kpiEntries.map(([key, v]: any) => (
                      <div key={key} className="bg-gray-50 rounded-lg p-3">
                        <div className="text-xs text-gray-500">{v.label}</div>
                        <div className="text-xl font-bold text-gray-900">
                          {v.waarde}{v.eenheid && <span className="text-sm font-normal text-gray-500 ml-0.5">{v.eenheid}</span>}
                        </div>
                        {v.delta != null && (
                          <div className={`text-xs ${v.delta < 0 ? "text-red-500" : "text-green-500"}`}>
                            {v.delta > 0 ? "+" : ""}{v.delta}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Alerts */}
              {alerts.length > 0 && (
                <div className="bg-white rounded-xl border shadow-sm p-5">
                  <h3 className="font-semibold text-gray-800 mb-3">⚠️ Alerts</h3>
                  <div className="space-y-2">
                    {alerts.map((a: any, i: number) => (
                      <div key={i} className={`flex items-center gap-3 p-3 rounded-lg ${a.ernst === "KRITIEK" ? "bg-red-50" : "bg-orange-50"}`}>
                        <span className={`font-bold text-xs px-2 py-0.5 rounded ${a.ernst === "KRITIEK" ? "bg-red-100 text-red-800" : "bg-orange-100 text-orange-800"}`}>{a.ernst}</span>
                        <span className="text-sm text-gray-700">{a.bericht}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Inzichten */}
              {inzichten.length > 0 && (
                <div className="bg-white rounded-xl border shadow-sm p-5">
                  <h3 className="font-semibold text-gray-800 mb-3">💡 Inzichten</h3>
                  <div className="space-y-3">
                    {inzichten.map((ins: any, i: number) => (
                      <div key={i} className="border-l-2 border-indigo-300 pl-3">
                        <div className="text-xs font-semibold text-indigo-600 uppercase">{ins.sectie}</div>
                        <p className="text-sm text-gray-700 mt-0.5">{ins.tekst}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Aanbevelingen */}
              {aanbevelingen.length > 0 && (
                <div className="bg-white rounded-xl border shadow-sm p-5">
                  <h3 className="font-semibold text-gray-800 mb-3">✅ Aanbevelingen</h3>
                  <div className="space-y-2">
                    {aanbevelingen.map((a: any, i: number) => (
                      <div key={i} className="flex items-start gap-2">
                        <span className={`text-xs px-2 py-0.5 rounded font-medium flex-shrink-0 ${a.prioriteit === "HOOG" ? "bg-orange-100 text-orange-700" : "bg-blue-100 text-blue-700"}`}>{a.prioriteit}</span>
                        <span className="text-sm text-gray-700">{a.actie}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
