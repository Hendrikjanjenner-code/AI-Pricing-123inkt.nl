import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}` });

const DATA_STYLE: Record<string, string> = {
  REAL: "bg-emerald-100 text-emerald-800",
  TEST: "bg-purple-100 text-purple-700",
  MIXED: "bg-amber-100 text-amber-800",
  "N/A": "bg-gray-100 text-gray-500",
};
const DATA_UITLEG: Record<string, string> = {
  REAL: "Gebaseerd op echte platformdata",
  TEST: "Gebaseerd op testdata",
  MIXED: "Combinatie van gemeten data en aannames",
};

export default function Eindevaluatie() {
  const { user } = useAuth();
  const [rapporten, setRapporten] = useState<any[]>([]);
  const [rapport, setRapport] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [fout, setFout] = useState("");
  const canGenerate = user && ["admin", "pricing_manager"].includes(user.role);

  const loadList = useCallback(() => {
    fetch(`${BASE}/api/governance/evaluation`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => {
        setRapporten(d.rapporten || []);
        if (d.rapporten?.length && !rapport) openRapport(d.rapporten[0].id);
      })
      .catch(() => setFout("Rapporten laden mislukt"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { loadList(); }, [loadList]);

  const openRapport = (id: number) => {
    fetch(`${BASE}/api/governance/evaluation/${id}`, { headers: authHeaders() })
      .then(r => r.json()).then(setRapport).catch(() => setFout("Rapport laden mislukt"));
  };

  const genereer = async () => {
    setBusy(true); setFout("");
    const r = await fetch(`${BASE}/api/governance/evaluation/generate`, { method: "POST", headers: authHeaders() });
    setBusy(false);
    if (!r.ok) { const j = await r.json().catch(() => ({})); setFout(typeof j.detail === "string" ? j.detail : "Genereren mislukt"); return; }
    const j = await r.json();
    loadList();
    openRapport(j.id);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Final Technical & Business Evaluation</h1>
          <p className="text-gray-500 mt-1">Genereerbaar eindrapport met de 20 evaluatievragen (§59), met onderscheid tussen echte data en testdata</p>
        </div>
        {canGenerate && (
          <button onClick={genereer} disabled={busy} className="px-4 py-2 text-sm bg-blue-600 text-white rounded disabled:opacity-50">
            {busy ? "Genereren…" : "Nieuw rapport genereren"}
          </button>
        )}
      </div>

      {fout && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{fout}</div>}

      <div className="flex flex-wrap gap-3 text-xs text-gray-600">
        {Object.entries(DATA_UITLEG).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className={`px-2 py-0.5 rounded font-semibold ${DATA_STYLE[k]}`}>{k}</span> {v}
          </span>
        ))}
      </div>

      {rapporten.length > 1 && (
        <select value={rapport?.id || ""} onChange={e => openRapport(Number(e.target.value))} className="border rounded px-2 py-1.5 text-sm">
          {rapporten.map(r => <option key={r.id} value={r.id}>{r.generated_at?.slice(0, 16)} — {r.generated_by}</option>)}
        </select>
      )}

      {!rapport ? (
        <div className="bg-white rounded-xl border shadow-sm p-8 text-gray-500 text-sm">
          Nog geen rapport gegenereerd. {canGenerate ? "Klik op 'Nieuw rapport genereren' om de eindevaluatie op basis van de actuele platformdata op te stellen." : "Vraag een beheerder om het rapport te genereren."}
        </div>
      ) : (
        <div className="bg-white rounded-xl border shadow-sm">
          <div className="p-4 border-b">
            <div className="font-semibold text-gray-900">{rapport.titel}</div>
            <div className="text-xs text-gray-400">Gegenereerd door {rapport.generated_by} op {rapport.generated_at?.slice(0, 16)}</div>
          </div>
          <ol className="divide-y">
            {(rapport.sections || []).map((s: any) => (
              <li key={s.nr} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="font-medium text-gray-900">{s.nr}. {s.vraag}</div>
                  <span className={`px-2 py-0.5 rounded text-xs font-semibold shrink-0 ${DATA_STYLE[s.data_label] || DATA_STYLE["N/A"]}`}>{s.data_label}</span>
                </div>
                <p className="text-sm text-gray-700 mt-1">{s.antwoord}</p>
                {s.details?.gaps && (
                  <ul className="mt-2 text-xs text-gray-500 list-disc pl-5 space-y-0.5">
                    {s.details.gaps.map((g: string, i: number) => <li key={i}>{g}</li>)}
                  </ul>
                )}
                {s.details?.modules && (
                  <div className="mt-2 grid md:grid-cols-2 gap-1">
                    {s.details.modules.map((m: any, i: number) => (
                      <div key={i} className="flex justify-between text-xs bg-gray-50 rounded px-2 py-1">
                        <span>{m.naam}</span><span className="text-gray-500">{m.label} ({m.score})</span>
                      </div>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
