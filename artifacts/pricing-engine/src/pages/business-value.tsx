import { useState, useEffect, useCallback } from "react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";
const authHeaders = () => ({ Authorization: `Bearer ${getToken()}` });

const LABEL_STYLE: Record<string, string> = {
  REALIZED: "bg-emerald-100 text-emerald-800",
  MEASURED: "bg-blue-100 text-blue-800",
  ESTIMATED: "bg-amber-100 text-amber-800",
  SIMULATED: "bg-purple-100 text-purple-800",
};
const LABEL_UITLEG: Record<string, string> = {
  REALIZED: "Daadwerkelijk gerealiseerd en doorgevoerd",
  MEASURED: "Direct gemeten in het platform",
  ESTIMATED: "Geschat op basis van expliciete aannames",
  SIMULATED: "Gesimuleerd scenario, niet gemeten",
};

function ValueBadge({ label }: { label: string }) {
  return <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${LABEL_STYLE[label] || "bg-gray-100"}`} title={LABEL_UITLEG[label]}>{label}</span>;
}

const fmt = (v: number, unit?: string) =>
  unit === "EUR" ? `€${v.toLocaleString("nl-NL", { maximumFractionDigits: 0 })}` : `${v.toLocaleString("nl-NL")} ${unit || ""}`;

export default function BusinessValue() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [dagen, setDagen] = useState(30);
  const [showBaselineForm, setShowBaselineForm] = useState(false);
  const [showMeasureForm, setShowMeasureForm] = useState(false);
  const [bl, setBl] = useState({ metric_key: "", label: "", baseline_value: "", unit: "", description: "" });
  const [ms, setMs] = useState({ metric_key: "", label: "", value: "", unit: "", value_label: "MEASURED", explanation: "" });
  const [fout, setFout] = useState("");

  const load = useCallback(() => {
    fetch(`${BASE}/api/platform/business-value/summary?dagen=${dagen}`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [dagen]);

  useEffect(() => { load(); }, [load]);

  const post = async (path: string, body: any, reset: () => void) => {
    setFout("");
    const r = await fetch(`${BASE}/api/platform/business-value/${path}`, {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setFout(typeof j.detail === "string" ? j.detail : "Opslaan mislukt — controleer de velden.");
      return;
    }
    reset(); load();
  };

  if (loading) return <div className="p-8 text-gray-500">Business value laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden business value.</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Business Value-meting</h1>
          <p className="text-gray-500 mt-1">Baseline vs. gemeten waarde — met expliciete hardheidslabels</p>
        </div>
        <select value={dagen} onChange={e => setDagen(Number(e.target.value))} className="border rounded px-3 py-1.5 text-sm">
          {[7, 30, 90].map(d => <option key={d} value={d}>Laatste {d} dagen</option>)}
        </select>
      </div>

      {/* Label legenda */}
      <div className="flex flex-wrap gap-3 text-xs text-gray-600">
        {(data.waarde_labels || []).map((l: string) => (
          <span key={l} className="flex items-center gap-1.5"><ValueBadge label={l} /> {LABEL_UITLEG[l]}</span>
        ))}
      </div>

      {fout && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{fout}</div>}

      {/* Automatische metingen */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b font-semibold text-gray-800">Automatisch gemeten platformgebruik ({dagen} dagen)</div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-gray-500">
            <tr><th className="px-4 py-2">Metric</th><th className="px-4 py-2 text-right">Waarde</th><th className="px-4 py-2">Label</th><th className="px-4 py-2">Toelichting</th></tr>
          </thead>
          <tbody>
            {(data.automatische_metingen || []).map((m: any) => (
              <tr key={m.metric_key} className="border-t">
                <td className="px-4 py-2 font-medium">{m.label}</td>
                <td className="px-4 py-2 text-right">{fmt(m.value, m.unit)}</td>
                <td className="px-4 py-2"><ValueBadge label={m.value_label} /></td>
                <td className="px-4 py-2 text-xs text-gray-500">{m.explanation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Baselines */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="p-4 border-b flex items-center justify-between">
            <span className="font-semibold text-gray-800">Baselines (nulmeting)</span>
            <button onClick={() => setShowBaselineForm(v => !v)} className="text-sm border rounded px-3 py-1.5 hover:bg-gray-50">+ Baseline</button>
          </div>
          {showBaselineForm && (
            <div className="p-4 border-b grid grid-cols-2 gap-2 text-sm bg-gray-50">
              <input placeholder="metric_key (bv. uren_prijsonderzoek)" className="border rounded px-2 py-1.5" value={bl.metric_key} onChange={e => setBl({ ...bl, metric_key: e.target.value })} />
              <input placeholder="Label" className="border rounded px-2 py-1.5" value={bl.label} onChange={e => setBl({ ...bl, label: e.target.value })} />
              <input placeholder="Baseline-waarde" className="border rounded px-2 py-1.5" value={bl.baseline_value} onChange={e => setBl({ ...bl, baseline_value: e.target.value })} />
              <input placeholder="Eenheid (uur/week, EUR/maand)" className="border rounded px-2 py-1.5" value={bl.unit} onChange={e => setBl({ ...bl, unit: e.target.value })} />
              <input placeholder="Beschrijving" className="border rounded px-2 py-1.5 col-span-2" value={bl.description} onChange={e => setBl({ ...bl, description: e.target.value })} />
              <button className="bg-indigo-600 text-white rounded px-3 py-1.5 col-span-2"
                onClick={() => post("baselines", { ...bl, baseline_value: parseFloat(bl.baseline_value.replace(",", ".")) },
                  () => { setBl({ metric_key: "", label: "", baseline_value: "", unit: "", description: "" }); setShowBaselineForm(false); })}>
                Baseline opslaan
              </button>
            </div>
          )}
          {(data.baselines || []).length === 0 ? <div className="p-4 text-sm text-gray-500">Nog geen baselines vastgelegd. Leg de nulmeting vast om besparing te kunnen aantonen.</div> : (
            <table className="w-full text-sm">
              <tbody>
                {data.baselines.map((b: any) => (
                  <tr key={b.id} className="border-t">
                    <td className="px-4 py-2">
                      <div className="font-medium">{b.label}</div>
                      <div className="text-xs text-gray-400">{b.description}</div>
                    </td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">{fmt(b.baseline_value, b.unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Handmatige metingen */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="p-4 border-b flex items-center justify-between">
            <span className="font-semibold text-gray-800">Handmatige metingen</span>
            <button onClick={() => setShowMeasureForm(v => !v)} className="text-sm border rounded px-3 py-1.5 hover:bg-gray-50">+ Meting</button>
          </div>
          {showMeasureForm && (
            <div className="p-4 border-b grid grid-cols-2 gap-2 text-sm bg-gray-50">
              <input placeholder="metric_key" className="border rounded px-2 py-1.5" value={ms.metric_key} onChange={e => setMs({ ...ms, metric_key: e.target.value })} />
              <input placeholder="Label" className="border rounded px-2 py-1.5" value={ms.label} onChange={e => setMs({ ...ms, label: e.target.value })} />
              <input placeholder="Waarde" className="border rounded px-2 py-1.5" value={ms.value} onChange={e => setMs({ ...ms, value: e.target.value })} />
              <input placeholder="Eenheid" className="border rounded px-2 py-1.5" value={ms.unit} onChange={e => setMs({ ...ms, unit: e.target.value })} />
              <select className="border rounded px-2 py-1.5" value={ms.value_label} onChange={e => setMs({ ...ms, value_label: e.target.value })}>
                {(data.waarde_labels || []).map((l: string) => <option key={l} value={l}>{l}</option>)}
              </select>
              <input placeholder="Toelichting (verplicht bij ESTIMATED/SIMULATED)" className="border rounded px-2 py-1.5" value={ms.explanation} onChange={e => setMs({ ...ms, explanation: e.target.value })} />
              <button className="bg-indigo-600 text-white rounded px-3 py-1.5 col-span-2"
                onClick={() => post("measurements", { ...ms, value: parseFloat(ms.value.replace(",", ".")) },
                  () => { setMs({ metric_key: "", label: "", value: "", unit: "", value_label: "MEASURED", explanation: "" }); setShowMeasureForm(false); })}>
                Meting opslaan
              </button>
            </div>
          )}
          {(data.handmatige_metingen || []).length === 0 ? <div className="p-4 text-sm text-gray-500">Nog geen handmatige metingen.</div> : (
            <table className="w-full text-sm">
              <tbody>
                {data.handmatige_metingen.map((m: any) => (
                  <tr key={m.id} className="border-t">
                    <td className="px-4 py-2">
                      <div className="font-medium">{m.label}</div>
                      <div className="text-xs text-gray-400">{m.explanation}</div>
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-right">{fmt(m.value, m.unit)}</td>
                    <td className="px-4 py-2"><ValueBadge label={m.value_label} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
