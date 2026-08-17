import { useState, useEffect, useCallback } from "react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";
const authHeaders = () => ({ Authorization: `Bearer ${getToken()}` });

const eur = (v: number | null | undefined) =>
  v == null ? "—" : `€${v.toLocaleString("nl-NL", { maximumFractionDigits: 0 })}`;

const SCENARIO_STYLE: Record<string, string> = {
  Conservative: "border-gray-300",
  Expected: "border-indigo-400 ring-1 ring-indigo-200",
  Ambitious: "border-emerald-300",
};

export default function PlatformBusinesscase() {
  const [data, setData] = useState<any>(null);
  const [shops, setShops] = useState(1);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${BASE}/api/platform/business-case?shops=${shops}`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [shops]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) return <div className="p-8 text-gray-500">Businesscase laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden businesscase.</div>;

  const k = data.kosten || {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Businesscase per shop</h1>
          <p className="text-gray-500 mt-1">
            Kosten, verwachte waarde, ROI en payback — alle waarden zijn <span className="font-medium">ESTIMATED</span> op basis van de zichtbare aannames hieronder.
          </p>
        </div>
        <label className="text-sm flex items-center gap-2">
          Aantal shops:
          <select value={shops} onChange={e => setShops(Number(e.target.value))} className="border rounded px-3 py-1.5">
            {[1, 2, 3, 5, 10].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </div>

      {/* Kosten per shop */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Setup (eenmalig)", value: eur(k.setup_eur_per_shop), sub: "per shop" },
          { label: "Maandkosten", value: eur(k.maandkosten_eur_per_shop), sub: "per shop (incl. centraal aandeel)" },
          { label: "Jaarkosten", value: eur(k.jaarkosten_eur_per_shop), sub: "per shop" },
          { label: "Centrale kosten", value: eur(k.centrale_kosten_eur_maand), sub: "per maand, gedeeld" },
          { label: "Variabel per shop", value: eur(k.variabele_kosten_eur_maand_per_shop), sub: "per maand" },
        ].map(c => (
          <div key={c.label} className="bg-white rounded-xl border p-4 shadow-sm">
            <div className="text-xl font-bold text-gray-900">{c.value}</div>
            <div className="text-sm font-medium text-gray-700">{c.label}</div>
            <div className="text-xs text-gray-400">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Scenario's */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {(data.scenarios || []).map((s: any) => (
          <div key={s.scenario} className={`bg-white rounded-xl border-2 p-5 shadow-sm space-y-3 ${SCENARIO_STYLE[s.scenario] || ""}`}>
            <div>
              <div className="text-lg font-bold text-gray-900">{s.scenario}</div>
              <div className="text-xs text-gray-500">{s.uitleg}</div>
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">Waarde per maand</span><span className="font-semibold">{eur(s.waarde_eur_maand)}</span></div>
              <div className="flex justify-between pl-3"><span className="text-gray-400">· tijdsbesparing</span><span>{eur(s.waarvan_tijdsbesparing_eur_maand)}</span></div>
              <div className="flex justify-between pl-3"><span className="text-gray-400">· marge-impact</span><span>{eur(s.waarvan_marge_impact_eur_maand)}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Omzet-impact p/mnd</span><span>{eur(s.omzet_impact_eur_maand)}</span></div>
              <div className="flex justify-between border-t pt-1.5"><span className="text-gray-500">Netto waarde p/mnd</span>
                <span className={`font-semibold ${s.netto_waarde_eur_maand >= 0 ? "text-emerald-600" : "text-red-600"}`}>{eur(s.netto_waarde_eur_maand)}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">ROI jaar 1</span>
                <span className={`font-semibold ${(s.roi_jaar1_pct ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"}`}>{s.roi_jaar1_pct != null ? `${s.roi_jaar1_pct}%` : "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Payback</span>
                <span className="font-semibold">{s.payback_maanden ? `${s.payback_maanden} mnd` : "—"}</span></div>
            </div>
          </div>
        ))}
      </div>

      {/* Aannames */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b">
          <div className="font-semibold text-gray-800">Gebruikte aannames (§64.11)</div>
          <div className="text-xs text-gray-500 mt-1">Deze businesscase is een schatting. Pas aannames aan via het Cost & Scalability Dashboard.</div>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-gray-500">
            <tr><th className="px-4 py-2">Aanname</th><th className="px-4 py-2 text-right">Waarde</th><th className="px-4 py-2">Eenheid</th><th className="px-4 py-2">Bron</th></tr>
          </thead>
          <tbody>
            {(data.aannames || []).map((a: any) => (
              <tr key={a.key} className="border-t">
                <td className="px-4 py-2">
                  <div className="font-medium">{a.label}</div>
                  <div className="text-xs text-gray-400">{a.description}</div>
                </td>
                <td className="px-4 py-2 text-right">{a.value.toLocaleString("nl-NL", { maximumFractionDigits: 4 })}</td>
                <td className="px-4 py-2">{a.unit}</td>
                <td className="px-4 py-2">{a.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
