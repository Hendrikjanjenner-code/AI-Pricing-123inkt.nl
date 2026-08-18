import { useState, useEffect, useCallback } from "react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";
const authHeaders = () => ({ Authorization: `Bearer ${getToken()}` });

const STATUS_STYLE: Record<string, string> = {
  ok: "bg-green-100 text-green-800",
  degraded: "bg-amber-100 text-amber-800",
  error: "bg-red-100 text-red-800",
  not_used: "bg-gray-100 text-gray-600",
  not_run: "bg-gray-100 text-gray-600",
  none: "bg-gray-100 text-gray-600",
};
const STATUS_LABEL: Record<string, string> = {
  ok: "Gezond", degraded: "Verminderd", error: "Fout",
  not_used: "Niet gebruikt", not_run: "Nog niet uitgevoerd", none: "Geen data",
};

function StatusBadge({ status }: { status?: string }) {
  const s = status || "none";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLE[s] || "bg-gray-100 text-gray-600"}`}>
      {STATUS_LABEL[s] || s}
    </span>
  );
}

const COMPONENT_LABELS: Record<string, string> = {
  applicatie: "Applicatie",
  database: "Database",
  api: "API's",
  ai: "AI-services",
  jobs: "Jobs & modelruns",
  imports: "Data-imports",
  integraties: "Integraties",
};

export default function PlatformHealth() {
  const [data, setData] = useState<any>(null);
  const [errors, setErrors] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [showErrors, setShowErrors] = useState(false);

  const load = useCallback(() => {
    fetch(`${BASE}/api/platform/health`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, [load]);

  const loadErrors = () => {
    setShowErrors(true);
    fetch(`${BASE}/api/platform/health/errors`, { headers: authHeaders() })
      .then(r => r.json()).then(setErrors).catch(() => {});
  };

  if (loading) return <div className="p-8 text-gray-500">Platformstatus laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden platformstatus.</div>;

  const comps = data.componenten || {};
  const perModule = Object.entries(data.api_per_module || {}) as [string, any][];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Platform Health Center</h1>
          <p className="text-gray-500 mt-1">Status van applicatie, database, AI, API's, jobs, integraties en imports</p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={data.overall_status} />
          <button onClick={load} className="text-sm border rounded px-3 py-1.5 hover:bg-gray-50">Vernieuwen</button>
        </div>
      </div>

      {/* Componenten */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Object.entries(comps).map(([key, c]: [string, any]) => (
          <div key={key} className="bg-white rounded-xl border p-4 shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-gray-800">{COMPONENT_LABELS[key] || key}</div>
              <StatusBadge status={c.status} />
            </div>
            <div className="text-xs text-gray-500 space-y-1">
              {key === "database" && c.response_ms != null && <div>Responstijd: {c.response_ms} ms</div>}
              {key === "api" && <>
                <div>{c.requests_last_hour} requests (laatste uur)</div>
                <div>Gem. {c.avg_response_ms} ms · p95 {Math.round(c.p95_response_ms)} ms</div>
                <div>Foutpercentage: {c.error_rate_pct}%</div>
              </>}
              {key === "ai" && <>
                <div>{c.calls_last_24h} AI-calls (24u), {c.failed_last_24h} mislukt</div>
                {c.provider_reachable === false && (
                  <div className="text-red-600 font-medium">⚠ AI-sleutel ongeldig of onbereikbaar</div>
                )}
                {c.provider_reachable === false && c.provider_error && (
                  <div className="text-red-500 break-words">{c.provider_error}</div>
                )}
                {c.provider_reachable === null && (
                  <div className="text-amber-600">Bereikbaarheid nog niet getest</div>
                )}
                {c.provider_reachable === true && (
                  <div className="text-green-700">AI-provider bereikbaar ✓</div>
                )}
              </>}
              {key === "jobs" && <>
                {c.laatste_run && <div>Laatste run: {new Date(c.laatste_run).toLocaleString("nl-NL")}</div>}
                <div>Gefaald (7d): {c.failed_last_7d}</div>
              </>}
              {key === "imports" && <>
                {c.laatste_import && <div>Laatste import: {new Date(c.laatste_import).toLocaleString("nl-NL")}</div>}
                <div>Gefaald (7d): {c.failed_last_7d}</div>
              </>}
              {key === "integraties" && <div>{(c.connectoren || []).length} connectoren geconfigureerd</div>}
              {key === "applicatie" && c.started_at && <div>Gestart: {new Date(c.started_at).toLocaleString("nl-NL")}</div>}
              {c.last_start_error && <div className="text-red-600">{c.last_start_error}</div>}
              {c.message && <div className="text-red-600">{c.message}</div>}
            </div>
          </div>
        ))}
      </div>

      {/* API responstijden per module */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b font-semibold text-gray-800">API-metrics per module (laatste uur)</div>
        {perModule.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">Nog geen requests gemeten.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-500">
              <tr>
                <th className="px-4 py-2">Module</th>
                <th className="px-4 py-2 text-right">Requests</th>
                <th className="px-4 py-2 text-right">Gem. (ms)</th>
                <th className="px-4 py-2 text-right">p95 (ms)</th>
                <th className="px-4 py-2 text-right">Fouten</th>
                <th className="px-4 py-2 text-right">Foutpercentage</th>
              </tr>
            </thead>
            <tbody>
              {perModule.sort((a, b) => b[1].requests_last_hour - a[1].requests_last_hour).map(([m, v]) => (
                <tr key={m} className="border-t">
                  <td className="px-4 py-2 font-medium">{m}</td>
                  <td className="px-4 py-2 text-right">{v.requests_last_hour}</td>
                  <td className="px-4 py-2 text-right">{v.avg_response_ms}</td>
                  <td className="px-4 py-2 text-right">{Math.round(v.p95_response_ms)}</td>
                  <td className="px-4 py-2 text-right">{v.error_count}</td>
                  <td className={`px-4 py-2 text-right ${v.error_rate_pct > 2 ? "text-red-600 font-medium" : ""}`}>{v.error_rate_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Fouten */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <span className="font-semibold text-gray-800">Recente fouten</span>
          <button onClick={loadErrors} className="text-sm border rounded px-3 py-1.5 hover:bg-gray-50">
            Volledige foutdrill-down
          </button>
        </div>
        {(data.recente_fouten || []).length === 0 && !showErrors ? (
          <div className="p-4 text-sm text-gray-500">Geen recente API-fouten. 🎉</div>
        ) : (
          <div className="divide-y">
            {(showErrors && errors ? errors.api_fouten : data.recente_fouten || []).map((e: any, i: number) => (
              <div key={i} className="p-3 text-sm flex flex-wrap gap-x-4 gap-y-1">
                <span className="text-gray-400">{new Date(e.timestamp).toLocaleString("nl-NL")}</span>
                <span className="font-mono text-xs bg-gray-100 rounded px-1.5 py-0.5">{e.correlation_id}</span>
                <span className="font-medium">{e.method} {e.path}</span>
                <span className="text-red-600">HTTP {e.status_code}</span>
                <span className="text-gray-600 w-full">{e.message}</span>
              </div>
            ))}
          </div>
        )}
        {showErrors && errors && (
          <div className="p-4 border-t grid md:grid-cols-2 gap-4 text-sm">
            <div>
              <div className="font-semibold mb-2">Gefaalde modelruns (14d)</div>
              {(errors.gefaalde_modelruns || []).length === 0 ? <div className="text-gray-500">Geen</div> :
                errors.gefaalde_modelruns.map((r: any) => (
                  <div key={r.id} className="mb-1 text-red-700">#{r.id} · {r.started_at && new Date(r.started_at).toLocaleString("nl-NL")} · {r.error_message}</div>
                ))}
            </div>
            <div>
              <div className="font-semibold mb-2">Gefaalde imports (14d)</div>
              {(errors.gefaalde_imports || []).length === 0 ? <div className="text-gray-500">Geen</div> :
                errors.gefaalde_imports.map((j: any) => (
                  <div key={j.id} className="mb-1 text-red-700">#{j.id} · {j.upload_type} · {j.filename} · {j.error_message}</div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
