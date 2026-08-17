import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}` });

export default function DocsCenter() {
  const { user } = useAuth();
  const [pages, setPages] = useState<any[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [doc, setDoc] = useState<any>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [fout, setFout] = useState("");
  const canEdit = user && ["admin", "pricing_manager", "analyst"].includes(user.role);

  useEffect(() => {
    fetch(`${BASE}/api/governance/docs`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => {
        setPages(d.paginas || []);
        if (d.paginas?.length) setActive(d.paginas[0].slug);
      })
      .catch(() => setFout("Documentatie laden mislukt"));
  }, []);

  const loadDoc = useCallback((slug: string) => {
    setEditing(false);
    fetch(`${BASE}/api/governance/docs/${slug}`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => { setDoc(d); setDraft(d.content_md || ""); })
      .catch(() => setFout("Pagina laden mislukt"));
  }, []);

  useEffect(() => { if (active) loadDoc(active); }, [active, loadDoc]);

  const save = async () => {
    setFout("");
    const r = await fetch(`${BASE}/api/governance/docs/${doc.slug}`, {
      method: "PUT",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ content_md: draft }),
    });
    if (!r.ok) { setFout("Opslaan mislukt"); return; }
    setEditing(false);
    loadDoc(doc.slug);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Platformdocumentatie</h1>
        <p className="text-gray-500 mt-1">Centrale documentatieomgeving (§58) — bewerkbaar, zodat de documentatie met de applicatie meegroeit</p>
      </div>
      {fout && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{fout}</div>}
      <div className="flex gap-4">
        <nav className="w-56 shrink-0 bg-white rounded-xl border shadow-sm p-2 h-fit">
          {pages.map(p => (
            <button key={p.slug} onClick={() => setActive(p.slug)}
              className={`block w-full text-left px-3 py-1.5 rounded text-sm ${active === p.slug ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-50"}`}>
              {p.titel}
            </button>
          ))}
        </nav>
        <div className="flex-1 bg-white rounded-xl border shadow-sm p-5 min-h-[300px]">
          {!doc ? <div className="text-gray-500">Selecteer een hoofdstuk…</div> : (
            <>
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">{doc.titel}</h2>
                  {doc.updated_by && <div className="text-xs text-gray-400">Laatst bijgewerkt door {doc.updated_by} op {doc.updated_at?.slice(0, 16)}</div>}
                </div>
                {canEdit && !editing && <button onClick={() => setEditing(true)} className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50">Bewerken</button>}
              </div>
              {editing ? (
                <div>
                  <textarea value={draft} onChange={e => setDraft(e.target.value)} rows={18}
                            className="w-full border rounded p-3 text-sm font-mono" />
                  <div className="flex justify-end gap-2 mt-2">
                    <button onClick={() => { setEditing(false); setDraft(doc.content_md || ""); }} className="px-3 py-1.5 text-sm border rounded">Annuleren</button>
                    <button onClick={save} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded">Opslaan</button>
                  </div>
                </div>
              ) : (
                <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap">{doc.content_md || "Nog geen inhoud — klik op Bewerken om dit hoofdstuk te vullen."}</div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
