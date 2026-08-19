import { useState, useEffect, useCallback } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid } from "recharts";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";
const authHeaders = () => ({ Authorization: `Bearer ${getToken()}` });

const TYPE_LABEL: Record<string, string> = {
  api_request: "API-requests", ai_call: "AI-calls", job: "Jobs/compute",
  import: "Imports", db: "Database", compute: "Compute",
};

const eur = (v: number) => `€${(v ?? 0).toLocaleString("nl-NL", { maximumFractionDigits: 2 })}`;
const usd = (v: number) => `$${(v ?? 0).toLocaleString("nl-NL", { maximumFractionDigits: 2 })}`;

const EMPTY_BQ = { total_cost_usd: 0, total_tb: 0, by_module: [] as any[] };

export default function PlatformKosten() {
  const [usage, setUsage] = useState<any>(null);
  const [bqCosts, setBqCosts] = useState<any>(EMPTY_BQ);
  const [scenarios, setScenarios] = useState<any>(null);
  const [assumptions, setAssumptions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [dagen, setDagen] = useState(30);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch(`${BASE}/api/platform/usage?dagen=${dagen}`, { headers: authHeaders() }).then(r => r.json()),
      fetch(`${BASE}/api/platform/costs/scenarios?dagen=${Math.max(dagen, 7)}`, { headers: authHeaders() }).then(r => r.json()),
      fetch(`${BASE}/api/platform/assumptions`, { headers: authHeaders() }).then(r => r.json()),
      // BigQuery-kosten: faalveilig — bij fout of niet-geconfigureerde BQ tonen we nul
      fetch(`${BASE}/api/bigquery/costs?days=${dagen}`, { headers: authHeaders() })
        .then(r => (r.ok ? r.json() : EMPTY_BQ))
        .catch(() => EMPTY_BQ),
    ]).then(([u, s, a, bq]) => {
      setUsage(u); setScenarios(s); setAssumptions(Array.isArray(a) ? a : []);
      setBqCosts(bq && typeof bq === "object" && !bq.error ? bq : EMPTY_BQ);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [dagen]);

  useEffect(() => { load(); }, [load]);

  const saveAssumption = async (key: string) => {
    const value = parseFloat((edit[key] || "").replace(",", "."));
    if (isNaN(value)) return;
    setSaving(key);
    try {
      await fetch(`${BASE}/api/platform/assumptions/${key}`, {
        method: "PUT",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
      });
      setEdit(e => { const n = { ...e }; delete n[key]; return n; });
      load();
    } finally {
      setSaving(null);
    }
  };

  if (loading) return <div className="p-8 text-gray-500">Kostendata laden…</div>;
  if (!usage || !scenarios) return <div className="p-8 text-red-500">Fout bij laden kostendata.</div>;

  const t = usage.totaal || {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Cost & Scalability Dashboard</h1>
          <p className="text-gray-500 mt-1">Werkelijk gemeten gebruik en kosten, met schaal-scenario's per shop</p>
        </div>
        <select value={dagen} onChange={e => setDagen(Number(e.target.value))} className="border rounded px-3 py-1.5 text-sm">
          {[7, 30, 90].map(d => <option key={d} value={d}>Laatste {d} dagen</option>)}
        </select>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {[
          { label: "Gemeten kosten", value: eur(t.kosten_eur), sub: `${dagen} dagen (variabel)` },
          { label: "Usage-records", value: t.records, sub: "gemeten gebeurtenissen" },
          { label: "Modelruns", value: t.modelruns, sub: "in periode" },
          { label: "Import-rijen", value: (t.import_rijen ?? 0).toLocaleString("nl-NL"), sub: "verwerkt" },
          { label: "Database", value: `${t.database_gb ?? "?"} GB`, sub: `${eur(t.database_kosten_eur_maand)} p/maand` },
          { label: "BigQuery-query's", value: usd(bqCosts.total_cost_usd), sub: `${(bqCosts.total_tb ?? 0).toLocaleString("nl-NL", { maximumFractionDigits: 4 })} TB gescand · ${dagen} dagen` },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border p-4 shadow-sm">
            <div className="text-2xl font-bold text-gray-900">{k.value}</div>
            <div className="text-sm font-medium text-gray-700">{k.label}</div>
            <div className="text-xs text-gray-400">{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Kosten per type */}
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-3">Gebruik per type</h3>
          <table className="w-full text-sm">
            <thead className="text-left text-gray-500">
              <tr><th className="py-1">Type</th><th className="py-1 text-right">Aantal</th><th className="py-1 text-right">Tokens</th><th className="py-1 text-right">Duur (s)</th><th className="py-1 text-right">Kosten</th></tr>
            </thead>
            <tbody>
              {(usage.per_type || []).map((r: any) => (
                <tr key={r.usage_type} className="border-t">
                  <td className="py-1.5">{TYPE_LABEL[r.usage_type] || r.usage_type}</td>
                  <td className="py-1.5 text-right">{r.aantal.toLocaleString("nl-NL")}</td>
                  <td className="py-1.5 text-right">{(r.tokens_in + r.tokens_out).toLocaleString("nl-NL")}</td>
                  <td className="py-1.5 text-right">{r.duur_seconden.toLocaleString("nl-NL")}</td>
                  <td className="py-1.5 text-right">{eur(r.kosten_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Kostentrend */}
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-3">Kostentrend per dag (€)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={usage.kosten_trend || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="datum" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: any) => [`€${Number(v).toFixed(4)}`, "Kosten"]} />
              <Line type="monotone" dataKey="kosten_eur" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Per module */}
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-3">Gebruik per module</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={(usage.per_module || []).slice(0, 10)} layout="vertical" margin={{ left: 40 }}>
              <XAxis type="number" tick={{ fontSize: 10 }} />
              <YAxis type="category" dataKey="module" tick={{ fontSize: 11 }} width={110} />
              <Tooltip />
              <Bar dataKey="aantal" fill="#8b5cf6" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* BigQuery-kosten per module */}
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-3">BigQuery-querykosten per module</h3>
          {(bqCosts.by_module || []).length === 0 ? (
            <div className="text-sm text-gray-400">Geen BigQuery-query's in deze periode (of BigQuery niet geconfigureerd).</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-500">
                <tr><th className="py-1">Module</th><th className="py-1 text-right">Query's</th><th className="py-1 text-right">TB gescand</th><th className="py-1 text-right">Kosten (USD)</th></tr>
              </thead>
              <tbody>
                {(bqCosts.by_module || []).map((r: any) => (
                  <tr key={r.module} className="border-t">
                    <td className="py-1.5">{r.module}</td>
                    <td className="py-1.5 text-right">{(r.query_count ?? 0).toLocaleString("nl-NL")}</td>
                    <td className="py-1.5 text-right">{(r.total_tb ?? 0).toLocaleString("nl-NL", { maximumFractionDigits: 4 })}</td>
                    <td className="py-1.5 text-right">{usd(r.total_cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="text-xs text-gray-400 mt-2">{bqCosts.pricing_note || "$6.25/TB (on-demand EU)"}</div>
        </div>

        {/* Per gebruiker/shop */}
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-3">Gebruik per gebruiker & shop</h3>
          <div className="text-xs text-gray-500 mb-2">Per shop: {(usage.per_shop || []).map((s: any) => `shop ${s.shop_id}: ${s.aantal}`).join(" · ") || "geen data"}</div>
          <table className="w-full text-sm">
            <thead className="text-left text-gray-500"><tr><th className="py-1">Gebruiker</th><th className="py-1 text-right">Requests</th><th className="py-1 text-right">Kosten</th></tr></thead>
            <tbody>
              {(usage.per_gebruiker || []).slice(0, 8).map((r: any) => (
                <tr key={r.username} className="border-t">
                  <td className="py-1.5">{r.username}</td>
                  <td className="py-1.5 text-right">{r.aantal.toLocaleString("nl-NL")}</td>
                  <td className="py-1.5 text-right">{eur(r.kosten_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Scenario's */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b">
          <div className="font-semibold text-gray-800">Schaal-scenario's: 1 / 5 / 10 shops × LOW / EXPECTED / HIGH gebruik</div>
          <div className="text-xs text-gray-500 mt-1">
            Centrale kosten: {eur(scenarios.centrale_kosten_eur_maand)}/maand · Variabel per shop (EXPECTED): {eur(scenarios.variabele_kosten_per_shop_eur_maand_expected)}/maand
            · Basis: gemeten gebruik {eur(scenarios.gemeten_basis?.geextrapoleerd_eur_maand)}/maand
            {(scenarios.gemeten_basis?.bigquery_kosten_eur_maand ?? 0) > 0 && (
              <> · incl. BigQuery {eur(scenarios.gemeten_basis.bigquery_kosten_eur_maand)}/maand</>
            )}
          </div>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-gray-500">
            <tr>
              <th className="px-4 py-2">Shops</th><th className="px-4 py-2">Gebruiksniveau</th>
              <th className="px-4 py-2 text-right">Centraal €/mnd</th>
              <th className="px-4 py-2 text-right">Variabel €/mnd</th>
              <th className="px-4 py-2 text-right">Totaal €/mnd</th>
              <th className="px-4 py-2 text-right">Per shop €/mnd</th>
            </tr>
          </thead>
          <tbody>
            {(scenarios.scenarios || []).map((s: any, i: number) => (
              <tr key={i} className={`border-t ${s.gebruiksniveau === "EXPECTED" ? "bg-indigo-50/50" : ""}`}>
                <td className="px-4 py-2 font-medium">{s.shops}</td>
                <td className="px-4 py-2">{s.gebruiksniveau}</td>
                <td className="px-4 py-2 text-right">{eur(s.centrale_kosten_eur_maand)}</td>
                <td className="px-4 py-2 text-right">{eur(s.variabele_kosten_eur_maand)}</td>
                <td className="px-4 py-2 text-right font-semibold">{eur(s.totale_kosten_eur_maand)}</td>
                <td className="px-4 py-2 text-right">{eur(s.kosten_per_shop_eur_maand)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Aannames */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b">
          <div className="font-semibold text-gray-800">Aannames (zichtbaar & bewerkbaar)</div>
          <div className="text-xs text-gray-500 mt-1">Elke berekening hierboven gebruikt deze expliciete aannames. Pas ze aan zodra werkelijke cijfers bekend zijn.</div>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-gray-500">
            <tr><th className="px-4 py-2">Aanname</th><th className="px-4 py-2">Categorie</th><th className="px-4 py-2 text-right">Waarde</th><th className="px-4 py-2">Eenheid</th><th className="px-4 py-2">Bron</th><th className="px-4 py-2"></th></tr>
          </thead>
          <tbody>
            {assumptions.map((a: any) => (
              <tr key={a.key} className="border-t align-top">
                <td className="px-4 py-2">
                  <div className="font-medium">{a.label}</div>
                  <div className="text-xs text-gray-400">{a.description}</div>
                </td>
                <td className="px-4 py-2">{a.category}</td>
                <td className="px-4 py-2 text-right">
                  {edit[a.key] !== undefined ? (
                    <input className="border rounded px-2 py-0.5 w-28 text-right" value={edit[a.key]}
                      onChange={e => setEdit(prev => ({ ...prev, [a.key]: e.target.value }))} />
                  ) : a.value.toLocaleString("nl-NL", { maximumFractionDigits: 6 })}
                </td>
                <td className="px-4 py-2">{a.unit}</td>
                <td className="px-4 py-2">{a.source}</td>
                <td className="px-4 py-2 text-right">
                  {edit[a.key] !== undefined ? (
                    <button onClick={() => saveAssumption(a.key)} disabled={saving === a.key}
                      className="text-xs bg-indigo-600 text-white rounded px-2 py-1">{saving === a.key ? "..." : "Opslaan"}</button>
                  ) : (
                    <button onClick={() => setEdit(prev => ({ ...prev, [a.key]: String(a.value) }))}
                      className="text-xs border rounded px-2 py-1 hover:bg-gray-50">Wijzig</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
