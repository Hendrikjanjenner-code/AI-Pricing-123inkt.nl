import { useState, useEffect, useCallback } from "react";
import { Link } from "wouter";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}` });

const eur = (v: number | null | undefined) =>
  v == null ? "—" : `€${Number(v).toLocaleString("nl-NL", { maximumFractionDigits: 0 })}`;
const num = (v: number | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("nl-NL"));

type DrillState = { kpi: string; titel: string } | null;

function Kpi({ label, value, onDrill, accent }: { label: string; value: string | number; onDrill?: () => void; accent?: string }) {
  return (
    <button
      onClick={onDrill}
      disabled={!onDrill}
      className={`text-left bg-white rounded-xl border shadow-sm p-4 w-full ${onDrill ? "hover:border-blue-400 hover:shadow cursor-pointer" : "cursor-default"}`}
      title={onDrill ? "Klik voor drill-down naar categorie / merk / SKU" : undefined}
    >
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${accent || "text-gray-900"}`}>{value}</div>
      {onDrill && <div className="text-[11px] text-blue-500 mt-1">Drill-down ▸</div>}
    </button>
  );
}

function Sectie({ titel, children }: { titel: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">{titel}</h2>
      {children}
    </div>
  );
}

function DrillDown({ drill, onClose, filterQs }: { drill: NonNullable<DrillState>; onClose: () => void; filterQs: string }) {
  const [level, setLevel] = useState<"category" | "brand" | "sku">("category");
  const [category, setCategory] = useState<string | null>(null);
  const [brand, setBrand] = useState<string | null>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [unit, setUnit] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const p = new URLSearchParams({ kpi: drill.kpi, level });
    if (category) p.set("category", category);
    if (brand) p.set("brand", brand);
    const qs = [p.toString(), filterQs].filter(Boolean).join("&");
    fetch(`${BASE}/api/command-center/drilldown?${qs}`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => { setRows(d.rows || []); setUnit(d.unit || ""); setLoading(false); })
      .catch(() => setLoading(false));
  }, [drill.kpi, level, category, brand, filterQs]);

  useEffect(() => { load(); }, [load]);

  const drillInto = (key: string) => {
    if (level === "category") { setCategory(key); setLevel("brand"); }
    else if (level === "brand") { setBrand(key); setLevel("sku"); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[85vh] overflow-auto" onClick={e => e.stopPropagation()}>
        <div className="p-4 border-b flex items-center justify-between sticky top-0 bg-white">
          <div>
            <div className="font-semibold text-gray-900">Drill-down: {drill.titel}</div>
            <div className="text-xs text-gray-500 mt-0.5">
              <button className="text-blue-600 hover:underline" onClick={() => { setLevel("category"); setCategory(null); setBrand(null); }}>Management</button>
              {category && <> → <button className="text-blue-600 hover:underline" onClick={() => { setLevel("brand"); setBrand(null); }}>{category}</button></>}
              {brand && <> → {brand}</>}
              <span className="ml-2 text-gray-400">niveau: {level === "category" ? "categorie" : level === "brand" ? "merk" : "SKU"}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl px-2">✕</button>
        </div>
        {loading ? (
          <div className="p-8 text-gray-500">Laden…</div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-gray-500">Geen data op dit niveau.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-500">
              <tr>
                <th className="px-4 py-2">{level === "category" ? "Categorie" : level === "brand" ? "Merk" : "SKU"}</th>
                <th className="px-4 py-2 text-right">Waarde</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-2">
                    {level === "sku" ? (
                      <Link href={`/skus/${encodeURIComponent(r.key)}`} className="text-blue-600 hover:underline">
                        {r.key}{r.product_name ? ` — ${r.product_name}` : ""}
                      </Link>
                    ) : (
                      <button className="text-blue-600 hover:underline" onClick={() => drillInto(r.key)}>{r.key}</button>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right font-medium">{unit === "EUR" ? eur(r.value) : num(r.value)}</td>
                  <td className="px-4 py-2 text-xs text-gray-500">
                    {r.units != null && `${num(r.units)} stuks`}
                    {r.avg_confidence != null && ` conf. ${(r.avg_confidence * 100).toFixed(0)}%`}
                    {r.expected_margin_uplift != null && ` uplift ${eur(r.expected_margin_uplift)}`}
                    {r.expected_value_eur != null && ` waarde ${eur(r.expected_value_eur)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function CommandCenter() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [drill, setDrill] = useState<DrillState>(null);

  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  useEffect(() => {
    setLoading(true);
    fetch(`${BASE}/api/command-center/summary${filterQs ? `?${filterQs}` : ""}`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [filterQs]);

  if (loading) return <div className="p-8 text-gray-500">Command Center laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden van het Command Center.</div>;

  const { vandaag, deze_week, financieel, ai, blokken } = data;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Commercial Command Center</h1>
        <p className="text-gray-500 mt-1">Eén managementoverzicht — klik op een KPI om door te drillen naar categorie, merk en SKU (peildatum {data.peildatum})</p>
      </div>

      <GlobalFilterBar />

      <Sectie titel="Today">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <Kpi label="Opportunities" value={num(vandaag.opportunities)} onDrill={() => setDrill({ kpi: "opportunities", titel: "Opportunities" })} />
          <Kpi label="Risico's" value={num(vandaag.risks)} accent="text-red-600" onDrill={() => setDrill({ kpi: "risks", titel: "Risico's" })} />
          <Kpi label="Concurrentwijzigingen" value={num(vandaag.competitor_changes)} />
          <Kpi label="Marge-issues" value={num(vandaag.margin_issues)} accent="text-amber-600" onDrill={() => setDrill({ kpi: "margin", titel: "Marge" })} />
          <Kpi label="Leverancierswaarschuwingen" value={num(vandaag.supplier_warnings)} />
          <Kpi label="Trafficwijzigingen" value={num(vandaag.traffic_changes)} />
        </div>
      </Sectie>

      <Sectie titel="This week">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <Kpi label="Prijsacties (pending)" value={num(deze_week.pricing_actions)} onDrill={() => setDrill({ kpi: "recommendations", titel: "Prijsaanbevelingen" })} />
          <Kpi label="Promotiekansen" value={num(deze_week.promotion_opportunities)} />
          <Kpi label="Huismerkkansen" value={num(deze_week.huismerk_opportunities)} />
          <Kpi label="Klantrisico's" value={num(deze_week.customer_risks)} accent="text-red-600" />
        </div>
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="p-3 border-b text-sm font-semibold text-gray-800">Beste kansen deze week</div>
          {deze_week.best_opportunities?.length ? (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-500">
                <tr><th className="px-4 py-2">Kans</th><th className="px-4 py-2">Type</th><th className="px-4 py-2 text-right">Verwachte waarde</th><th className="px-4 py-2 text-right">Prioriteit</th><th className="px-4 py-2">Urgentie</th></tr>
              </thead>
              <tbody>
                {deze_week.best_opportunities.map((o: any) => (
                  <tr key={o.id} className="border-t">
                    <td className="px-4 py-2">{o.titel || o.entity_name || o.entity_id}</td>
                    <td className="px-4 py-2 text-gray-500">{o.type}</td>
                    <td className="px-4 py-2 text-right">{eur(o.expected_value_eur)}</td>
                    <td className="px-4 py-2 text-right">{num(o.priority_score)}</td>
                    <td className="px-4 py-2"><span className={`px-2 py-0.5 rounded text-xs ${o.urgency === "critical" || o.urgency === "high" ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-600"}`}>{o.urgency}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="p-4 text-sm text-gray-500">Geen open kansen.</div>}
        </div>
      </Sectie>

      <Sectie titel="Financial">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Kpi label="Omzet (7 dagen)" value={eur(financieel.sales_7d)} onDrill={() => setDrill({ kpi: "sales", titel: "Omzet" })} />
          <Kpi label="Marge (7 dagen)" value={eur(financieel.margin_7d)} onDrill={() => setDrill({ kpi: "margin", titel: "Marge" })} />
          <Kpi label="Margeverandering" value={financieel.margin_change_pct == null ? "—" : `${financieel.margin_change_pct > 0 ? "+" : ""}${financieel.margin_change_pct}%`}
               accent={financieel.margin_change_pct != null && financieel.margin_change_pct < 0 ? "text-red-600" : "text-emerald-600"} />
          <Kpi label="Forecast omzet (30 d.)" value={eur(financieel.forecast_revenue)} />
        </div>
      </Sectie>

      <Sectie titel="AI">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <Kpi label="Aanbevelingen" value={num(ai.recommendations)} onDrill={() => setDrill({ kpi: "recommendations", titel: "Aanbevelingen" })} />
          <Kpi label="Goedkeuringen open" value={num(ai.approvals_pending)} accent="text-amber-600" />
          <Kpi label="Gem. confidence" value={`${Math.round((ai.avg_confidence || 0) * 100)}%`} />
        </div>
      </Sectie>

      <Sectie titel="Managementblokken (§50)">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            ["COMMERCIAL", [["Sales", eur(blokken.commercial.sales)], ["Marge", eur(blokken.commercial.margin)], ["Kansen", num(blokken.commercial.opportunities)], ["Risico's", num(blokken.commercial.risks)]]],
            ["COMPETITION", [["Concurrenten", num(blokken.competition.main_competitors)], ["Wijzigingen", num(blokken.competition.changes)], ["Dreigingen", num(blokken.competition.threats)]]],
            ["PRICING", [["Aanbevolen acties", num(blokken.pricing.recommended_actions)], ["Margekansen", eur(blokken.pricing.margin_opportunities_eur)]]],
            ["CUSTOMERS", [["Waardescores", num(blokken.customers.value_scores)], ["Churn-risico", num(blokken.customers.churn_risks)], ["Switching", num(blokken.customers.switching)]]],
            ["OPERATIONS", [["Leveranciersrisico's", num(blokken.operations.supplier_risks)], ["Voorraadrisico's", num(blokken.operations.stock_risks)]]],
            ["AI", [["Aanbevelingen", num(blokken.ai.recommendations)], ["Confidence", `${Math.round((blokken.ai.confidence || 0) * 100)}%`], ["Open goedkeuringen", num(blokken.ai.pending_approvals)]]],
            ["PLATFORM", [["Datakwaliteit", `${Math.round((blokken.platform.data_quality_score || 0) * 100)}%`], ["Open DQ-issues", num(blokken.platform.open_dq_issues)], ["Integraties OK", `${blokken.platform.integrations_ok}/${blokken.platform.integrations_total}`], ["Security", blokken.platform.security_status]]],
            ["BUSINESSCASE", [["Kosten (30 d.)", eur(blokken.businesscase.cost_30d_eur)], ["Kosten per shop", eur(blokken.businesscase.cost_per_shop_eur)], ["Gemeten waarde", eur(blokken.businesscase.measured_value_eur)], ["ROI", blokken.businesscase.roi_pct == null ? "—" : `${blokken.businesscase.roi_pct}%`]]],
          ].map(([titel, rows]: any) => (
            <div key={titel} className="bg-white rounded-xl border shadow-sm p-4">
              <div className="text-xs font-bold text-gray-400 tracking-wide mb-2">{titel}</div>
              <dl className="space-y-1.5">
                {rows.map(([k, v]: any) => (
                  <div key={k} className="flex justify-between text-sm">
                    <dt className="text-gray-500">{k}</dt>
                    <dd className="font-medium text-gray-900">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </Sectie>

      {drill && <DrillDown drill={drill} onClose={() => setDrill(null)} filterQs={filterQs} />}
    </div>
  );
}
