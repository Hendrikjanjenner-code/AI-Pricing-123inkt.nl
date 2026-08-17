import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}` });

const STATUS_NL: Record<string, string> = { open: "Open", in_progress: "In uitvoering", done: "Gereed", wont_do: "Vervalt" };
const TYPE_NL: Record<string, string> = {
  missing_functionality: "Ontbrekende functionaliteit", bug: "Bug",
  improvement: "Verbetering", test: "Test", documentation: "Documentatie",
};
const PRIO_STYLE: Record<string, string> = {
  critical: "bg-red-100 text-red-700", high: "bg-orange-100 text-orange-700",
  medium: "bg-amber-100 text-amber-700", low: "bg-gray-100 text-gray-600",
};

const LEEG = { module_key: "", title: "", description: "", item_type: "missing_functionality", priority: "medium", owner: "", dependencies: "", data_sources: "", tests: "", business_value: "" };
const LEEG_PROMPT = { module_key: "", title: "", prompt_text: "", notes: "" };

export default function DevBacklog() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"backlog" | "prompts">("backlog");
  const [items, setItems] = useState<any[]>([]);
  const [prompts, setPrompts] = useState<any[]>([]);
  const [modules, setModules] = useState<any[]>([]);
  const [filterModule, setFilterModule] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<any>(LEEG);
  const [promptForm, setPromptForm] = useState<any>(LEEG_PROMPT);
  const [showPromptForm, setShowPromptForm] = useState(false);
  const [openPrompt, setOpenPrompt] = useState<number | null>(null);
  const [fout, setFout] = useState("");
  const canEdit = user && ["admin", "pricing_manager", "analyst"].includes(user.role);

  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (filterModule) p.set("module_key", filterModule);
    if (filterStatus) p.set("status", filterStatus);
    fetch(`${BASE}/api/governance/backlog?${p}`, { headers: authHeaders() })
      .then(r => r.json()).then(d => setItems(d.items || [])).catch(() => {});
    fetch(`${BASE}/api/governance/prompts${filterModule ? `?module_key=${filterModule}` : ""}`, { headers: authHeaders() })
      .then(r => r.json()).then(d => setPrompts(d.prompts || [])).catch(() => {});
  }, [filterModule, filterStatus]);

  useEffect(() => {
    fetch(`${BASE}/api/governance/modules`, { headers: authHeaders() })
      .then(r => r.json()).then(d => setModules(d.modules || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const post = async (path: string, body: any, done: () => void) => {
    setFout("");
    const r = await fetch(`${BASE}/api/governance/${path}`, {
      method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) { const j = await r.json().catch(() => ({})); setFout(typeof j.detail === "string" ? j.detail : "Opslaan mislukt"); return; }
    done(); load();
  };

  const setStatus = async (item: any, status: string) => {
    await fetch(`${BASE}/api/governance/backlog/${item.id}`, {
      method: "PUT", headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    load();
  };

  const moduleName = (key: string) => modules.find(m => m.module_key === key)?.naam || key;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Development Backlog & Prompt Library</h1>
          <p className="text-gray-500 mt-1">Per module: status, prioriteit, eigenaar, afhankelijkheden en promptversies (§48)</p>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            {tab === "backlog"
              ? <button onClick={() => setShowForm(true)} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded">+ Backlog-item</button>
              : <button onClick={() => setShowPromptForm(true)} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded">+ Promptversie</button>}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex border rounded overflow-hidden text-sm">
          {(["backlog", "prompts"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-1.5 ${tab === t ? "bg-blue-600 text-white" : "bg-white text-gray-600"}`}>
              {t === "backlog" ? `Backlog (${items.length})` : `Prompt Library (${prompts.length})`}
            </button>
          ))}
        </div>
        <select value={filterModule} onChange={e => setFilterModule(e.target.value)} className="border rounded px-2 py-1.5 text-sm">
          <option value="">Alle modules</option>
          {modules.map(m => <option key={m.module_key} value={m.module_key}>{m.naam}</option>)}
        </select>
        {tab === "backlog" && (
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="border rounded px-2 py-1.5 text-sm">
            <option value="">Alle statussen</option>
            {Object.entries(STATUS_NL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        )}
      </div>

      {fout && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{fout}</div>}

      {tab === "backlog" ? (
        <div className="bg-white rounded-xl border shadow-sm overflow-x-auto">
          {items.length === 0 ? <div className="p-6 text-sm text-gray-500">Geen backlog-items. Voeg het eerste item toe.</div> : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-500">
                <tr>
                  <th className="px-4 py-2">Item</th><th className="px-4 py-2">Module</th>
                  <th className="px-4 py-2">Type</th><th className="px-4 py-2">Prioriteit</th>
                  <th className="px-4 py-2">Eigenaar</th><th className="px-4 py-2">Afhankelijkheden</th>
                  <th className="px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map(i => (
                  <tr key={i.id} className="border-t align-top">
                    <td className="px-4 py-2">
                      <div className="font-medium text-gray-900">{i.title}</div>
                      {i.description && <div className="text-xs text-gray-500 mt-0.5">{i.description}</div>}
                      {i.business_value && <div className="text-xs text-emerald-700 mt-0.5">Waarde: {i.business_value}</div>}
                    </td>
                    <td className="px-4 py-2 text-gray-600">{moduleName(i.module_key)}</td>
                    <td className="px-4 py-2 text-gray-600">{TYPE_NL[i.item_type] || i.item_type}</td>
                    <td className="px-4 py-2"><span className={`px-2 py-0.5 rounded text-xs ${PRIO_STYLE[i.priority]}`}>{i.priority}</span></td>
                    <td className="px-4 py-2 text-gray-600">{i.owner || "—"}</td>
                    <td className="px-4 py-2 text-gray-500 text-xs">{i.dependencies || "—"}</td>
                    <td className="px-4 py-2">
                      {canEdit ? (
                        <select value={i.status} onChange={e => setStatus(i, e.target.value)} className="border rounded px-1.5 py-1 text-xs">
                          {Object.entries(STATUS_NL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </select>
                      ) : STATUS_NL[i.status] || i.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {prompts.length === 0 ? <div className="bg-white rounded-xl border p-6 text-sm text-gray-500">Nog geen prompts opgeslagen. Bewaar promptversies per module zodat ze herbruikbaar blijven.</div> :
            prompts.map(p => (
              <div key={p.id} className="bg-white rounded-xl border shadow-sm">
                <button className="w-full flex items-center justify-between p-3 text-left" onClick={() => setOpenPrompt(openPrompt === p.id ? null : p.id)}>
                  <div className="min-w-0">
                    <span className="font-medium text-gray-900">{p.title}</span>
                    <span className="ml-2 text-xs text-gray-400">v{p.version} · {moduleName(p.module_key)} · {p.created_by} · {p.created_at?.slice(0, 10)}</span>
                  </div>
                  <span className="text-gray-400">{openPrompt === p.id ? "▴" : "▾"}</span>
                </button>
                {openPrompt === p.id && (
                  <div className="border-t p-3">
                    <pre className="text-xs bg-gray-50 rounded p-3 whitespace-pre-wrap">{p.prompt_text}</pre>
                    {p.notes && <div className="text-xs text-gray-500 mt-2">Notities: {p.notes}</div>}
                  </div>
                )}
              </div>
            ))}
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[85vh] overflow-auto p-5 space-y-2" onClick={e => e.stopPropagation()}>
            <div className="font-semibold text-gray-900 mb-2">Nieuw backlog-item</div>
            <select value={form.module_key} onChange={e => setForm({ ...form, module_key: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm">
              <option value="">Kies module…</option>
              {modules.map(m => <option key={m.module_key} value={m.module_key}>{m.naam}</option>)}
            </select>
            <input placeholder="Titel *" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            <textarea placeholder="Omschrijving" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} rows={2} className="w-full border rounded px-2 py-1.5 text-sm" />
            <div className="flex gap-2">
              <select value={form.item_type} onChange={e => setForm({ ...form, item_type: e.target.value })} className="flex-1 border rounded px-2 py-1.5 text-sm">
                {Object.entries(TYPE_NL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} className="flex-1 border rounded px-2 py-1.5 text-sm">
                {["low", "medium", "high", "critical"].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <input placeholder="Eigenaar" value={form.owner} onChange={e => setForm({ ...form, owner: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            <input placeholder="Afhankelijkheden" value={form.dependencies} onChange={e => setForm({ ...form, dependencies: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            <input placeholder="Databronnen" value={form.data_sources} onChange={e => setForm({ ...form, data_sources: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            <input placeholder="Tests" value={form.tests} onChange={e => setForm({ ...form, tests: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            <input placeholder="Businesswaarde" value={form.business_value} onChange={e => setForm({ ...form, business_value: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setShowForm(false)} className="px-3 py-1.5 text-sm border rounded">Annuleren</button>
              <button onClick={() => post("backlog", form, () => { setShowForm(false); setForm(LEEG); })} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded">Opslaan</button>
            </div>
          </div>
        </div>
      )}

      {showPromptForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowPromptForm(false)}>
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[85vh] overflow-auto p-5 space-y-2" onClick={e => e.stopPropagation()}>
            <div className="font-semibold text-gray-900 mb-1">Nieuwe promptversie</div>
            <p className="text-xs text-gray-500">Zelfde module + titel verhoogt automatisch het versienummer; eerdere versies blijven bewaard.</p>
            <select value={promptForm.module_key} onChange={e => setPromptForm({ ...promptForm, module_key: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm">
              <option value="">Kies module…</option>
              {modules.map(m => <option key={m.module_key} value={m.module_key}>{m.naam}</option>)}
            </select>
            <input placeholder="Titel *" value={promptForm.title} onChange={e => setPromptForm({ ...promptForm, title: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            <textarea placeholder="Prompttekst *" value={promptForm.prompt_text} onChange={e => setPromptForm({ ...promptForm, prompt_text: e.target.value })} rows={8} className="w-full border rounded px-2 py-1.5 text-sm font-mono" />
            <input placeholder="Notities" value={promptForm.notes} onChange={e => setPromptForm({ ...promptForm, notes: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setShowPromptForm(false)} className="px-3 py-1.5 text-sm border rounded">Annuleren</button>
              <button onClick={() => post("prompts", promptForm, () => { setShowPromptForm(false); setPromptForm(LEEG_PROMPT); })} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded">Opslaan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
