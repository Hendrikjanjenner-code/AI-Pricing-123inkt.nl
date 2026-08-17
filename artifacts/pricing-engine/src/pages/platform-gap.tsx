import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}` });

const PRIO_STYLE: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-gray-100 text-gray-600",
};

const LABEL_STYLE: Record<string, string> = {
  "Concept": "bg-gray-100 text-gray-600",
  "Prototype": "bg-slate-100 text-slate-700",
  "Integrated Prototype": "bg-blue-100 text-blue-700",
  "POC Ready": "bg-indigo-100 text-indigo-700",
  "Pilot Ready": "bg-violet-100 text-violet-700",
  "Production Candidate": "bg-amber-100 text-amber-800",
  "Production Ready": "bg-emerald-100 text-emerald-800",
};

const CRITERIA_NL: Record<string, string> = {
  functionality: "Functionaliteit", integration: "Integratie", data_quality: "Datakwaliteit",
  tests: "Tests", security: "Security", performance: "Performance",
  auditability: "Auditbaarheid", monitoring: "Monitoring",
  documentation: "Documentatie", human_control: "Menselijke controle",
};

function ScoreEditor({ mod, onSaved, onClose }: { mod: any; onSaved: () => void; onClose: () => void }) {
  const [scores, setScores] = useState<Record<string, number>>({ ...mod.readiness_scores });
  const [gap, setGap] = useState(mod.gap || "");
  const [priority, setPriority] = useState(mod.priority);
  const [saving, setSaving] = useState(false);
  const [fout, setFout] = useState("");

  const save = async () => {
    setSaving(true); setFout("");
    const r = await fetch(`${BASE}/api/governance/modules/${mod.id}`, {
      method: "PUT",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ readiness_scores: scores, gap, priority }),
    });
    setSaving(false);
    if (!r.ok) { const j = await r.json().catch(() => ({})); setFout(typeof j.detail === "string" ? j.detail : "Opslaan mislukt"); return; }
    onSaved(); onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[85vh] overflow-auto p-5" onClick={e => e.stopPropagation()}>
        <div className="font-semibold text-gray-900 mb-3">Readiness-scores — {mod.naam}</div>
        {Object.keys(CRITERIA_NL).map(c => (
          <div key={c} className="flex items-center gap-3 mb-2">
            <label className="w-44 text-sm text-gray-600">{CRITERIA_NL[c]}</label>
            <input type="range" min={0} max={100} value={scores[c] ?? 0}
                   onChange={e => setScores(s => ({ ...s, [c]: Number(e.target.value) }))} className="flex-1" />
            <span className="w-10 text-right text-sm font-medium">{scores[c] ?? 0}</span>
          </div>
        ))}
        <div className="mt-3">
          <label className="text-sm text-gray-600">Gap (wat ontbreekt)</label>
          <textarea value={gap} onChange={e => setGap(e.target.value)} rows={2} className="w-full border rounded px-2 py-1.5 text-sm mt-1" />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <label className="text-sm text-gray-600">Prioriteit</label>
          <select value={priority} onChange={e => setPriority(e.target.value)} className="border rounded px-2 py-1 text-sm">
            {["low", "medium", "high", "critical"].map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        {fout && <div className="text-red-600 text-sm mt-2">{fout}</div>}
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-3 py-1.5 text-sm border rounded">Annuleren</button>
          <button onClick={save} disabled={saving} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded disabled:opacity-50">{saving ? "Opslaan…" : "Opslaan"}</button>
        </div>
      </div>
    </div>
  );
}

export default function PlatformGap() {
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const [edit, setEdit] = useState<any>(null);
  const [fout, setFout] = useState("");

  const canEdit = user && ["admin", "pricing_manager"].includes(user.role);
  const isAdmin = user?.role === "admin";

  const load = useCallback(() => {
    fetch(`${BASE}/api/governance/modules`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const approve = async (m: any, revoke = false) => {
    setFout("");
    const r = await fetch(`${BASE}/api/governance/modules/${m.id}/${revoke ? "revoke-production" : "approve-production"}`, {
      method: "POST", headers: authHeaders(),
    });
    if (!r.ok) { const j = await r.json().catch(() => ({})); setFout(typeof j.detail === "string" ? j.detail : "Actie mislukt"); return; }
    load();
  };

  if (loading) return <div className="p-8 text-gray-500">Gap Dashboard laden…</div>;
  if (!data) return <div className="p-8 text-red-500">Fout bij laden van het Gap Dashboard.</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Platform Gap Dashboard</h1>
        <p className="text-gray-500 mt-1">Expected feature vs. huidige implementatie vs. gap vs. prioriteit — met production-readiness per module (§46/§49)</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {(data.labels || []).map((l: string) => (
          <span key={l} className={`px-2 py-1 rounded text-xs font-medium ${LABEL_STYLE[l]}`}>
            {l}: {data.per_label?.[l] || 0}
          </span>
        ))}
      </div>

      {fout && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{fout}</div>}

      <div className="space-y-3">
        {data.modules.map((m: any) => (
          <div key={m.id} className="bg-white rounded-xl border shadow-sm">
            <button className="w-full flex items-center justify-between p-4 text-left" onClick={() => setOpen(open === m.id ? null : m.id)}>
              <div className="flex items-center gap-3 min-w-0">
                <span className="font-semibold text-gray-900">{m.naam}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ${LABEL_STYLE[m.readiness_label]}`}>{m.readiness_label}</span>
                <span className={`px-2 py-0.5 rounded text-xs shrink-0 ${PRIO_STYLE[m.priority]}`}>{m.priority}</span>
                {!m.uses_real_data && <span className="px-2 py-0.5 rounded text-xs bg-purple-100 text-purple-700 shrink-0">testdata</span>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <div className="w-28 bg-gray-100 rounded-full h-2 hidden md:block">
                  <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${m.readiness_score_avg}%` }} />
                </div>
                <span className="text-sm font-medium text-gray-700 w-10 text-right">{m.readiness_score_avg}</span>
                <span className="text-gray-400">{open === m.id ? "▴" : "▾"}</span>
              </div>
            </button>
            {open === m.id && (
              <div className="border-t p-4 grid md:grid-cols-3 gap-4 text-sm">
                <div><div className="text-xs font-semibold text-gray-400 uppercase mb-1">Expected feature</div><p className="text-gray-700">{m.expected_feature}</p></div>
                <div><div className="text-xs font-semibold text-gray-400 uppercase mb-1">Huidige implementatie</div><p className="text-gray-700">{m.current_implementation}</p></div>
                <div><div className="text-xs font-semibold text-gray-400 uppercase mb-1">Gap</div><p className="text-gray-700">{m.gap || "—"}</p></div>
                <div className="md:col-span-3">
                  <div className="text-xs font-semibold text-gray-400 uppercase mb-2">§46-criteria</div>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                    {Object.keys(CRITERIA_NL).map(c => (
                      <div key={c} className="flex justify-between bg-gray-50 rounded px-2 py-1 text-xs">
                        <span className="text-gray-500">{CRITERIA_NL[c]}</span>
                        <span className="font-medium">{m.readiness_scores?.[c] ?? 0}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="md:col-span-3 flex flex-wrap items-center gap-2">
                  {canEdit && <button onClick={() => setEdit(m)} className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50">Scores bewerken</button>}
                  {isAdmin && m.readiness_label === "Production Candidate" && (
                    <button onClick={() => approve(m)} className="px-3 py-1.5 text-sm bg-emerald-600 text-white rounded">Goedkeuren voor productie</button>
                  )}
                  {isAdmin && m.readiness_label === "Production Ready" && (
                    <button onClick={() => approve(m, true)} className="px-3 py-1.5 text-sm border border-red-300 text-red-600 rounded">Goedkeuring intrekken</button>
                  )}
                  {m.production_approved_by && (
                    <span className="text-xs text-gray-500">Goedgekeurd door {m.production_approved_by} op {m.production_approved_at?.slice(0, 10)}</span>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {edit && <ScoreEditor mod={edit} onSaved={load} onClose={() => setEdit(null)} />}
    </div>
  );
}
