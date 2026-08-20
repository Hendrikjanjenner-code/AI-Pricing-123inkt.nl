import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  CheckCircle2, ChevronDown, ChevronUp, Loader2, RefreshCw, XCircle,
  Settings, BarChart3, Save, X as XIcon, Plus, Trash2,
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { getAuthHeaders } from "@/lib/auth";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

// ─── Types ───────────────────────────────────────────────────────────────────

interface Overview {
  total_skus: number;
  skus_scored: number;
  avg_completeness_pct: number;
  avg_quality_score: number;
  low_completeness_count: number;
  pending_suggestions: number;
  last_run_date: string | null;
  channels: {
    code: string; name: string; min_completeness_pct: number;
    skus_scored: number; skus_ready: number; avg_completeness_pct: number;
  }[];
}

interface CompletenessRow {
  sku_id: string;
  product_name: string;
  brand?: string;
  category?: string;
  channel_code: string | null;
  completeness_pct: number;
  quality_score: number;
  channel_ready: boolean;
  missing_attributes: string[];
  quality_issues: { code: string; bericht: string }[];
}

interface ContentAttribute {
  code: string;
  name: string;
  source_owner: string;
  is_required: boolean;
  value: string | null;
  value_source: string | null;
}

interface AttrDef {
  id: number; code: string; name: string; data_type: string;
  unit: string | null; source_owner: string; is_required: boolean;
  weight: number; dim_product_field: string | null; active: boolean;
}

interface Channel {
  id: number; code: string; name: string;
  required_attribute_codes: string[];
  min_completeness_pct: number; active: boolean;
}

interface Family {
  id: number; code: string; name: string;
  category_patterns: string[];
  active: boolean; product_count: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function pctBadge(pct: number) {
  const cls = pct >= 80
    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : pct >= 60
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-red-50 text-red-600 border-red-200";
  return <Badge className={`${cls} text-xs`}>{pct.toFixed(0)}%</Badge>;
}

function sourceBadge(source?: string | null) {
  if (!source) return <span className="text-muted-foreground text-xs">—</span>;
  const kleur: Record<string, string> = {
    DRS: "bg-blue-50 text-blue-700 border-blue-200",
    Leverancier: "bg-purple-50 text-purple-700 border-purple-200",
    Handmatig: "bg-slate-50 text-slate-700 border-slate-200",
    AI: "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
  return <Badge className={`${kleur[source] ?? ""} text-xs`}>{source}</Badge>;
}

async function patchApi(path: string, body: object): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
}

async function postApi(path: string, body: object): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
}

async function deleteApi(path: string): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
    signal: AbortSignal.timeout(30_000),
  });
}

// ─── DetailRij: expanded product attributes ───────────────────────────────────

function DetailRij({ row }: { row: CompletenessRow }) {
  const [attrs, setAttrs] = useState<ContentAttribute[] | null>(null);
  const [laden, setLaden] = useState(false);

  useEffect(() => {
    let actief = true;
    setLaden(true);
    fetch(`${BASE}/api/pim/products/${encodeURIComponent(row.sku_id)}/content`, {
      headers: getAuthHeaders(), signal: AbortSignal.timeout(30_000),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (actief) setAttrs(d.attributes ?? []); })
      .catch(() => { if (actief) setAttrs([]); })
      .finally(() => { if (actief) setLaden(false); });
    return () => { actief = false; };
  }, [row.sku_id]);

  return (
    <TableRow>
      <TableCell colSpan={7} className="bg-muted/30">
        {laden ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Attributen laden…
          </div>
        ) : (
          <div className="space-y-3 py-2">
            {row.missing_attributes.length > 0 && (
              <div className="text-sm">
                <span className="font-medium">Ontbrekend: </span>
                {row.missing_attributes.map((m) => (
                  <Badge key={m} variant="outline" className="mr-1 text-xs text-red-600 border-red-200">{m}</Badge>
                ))}
              </div>
            )}
            {row.quality_issues.length > 0 && (
              <div className="text-sm">
                <span className="font-medium">Kwaliteitsissues: </span>
                {row.quality_issues.map((q, i) => (
                  <span key={i} className="mr-2 text-amber-700">{q.bericht}</span>
                ))}
              </div>
            )}
            <div className="grid grid-cols-1 gap-1 md:grid-cols-2 lg:grid-cols-3">
              {(attrs ?? []).map((a) => (
                <div key={a.code} className="flex items-center justify-between rounded border bg-background px-2 py-1 text-sm">
                  <span className="truncate">
                    {a.name}
                    {a.is_required && <span className="text-red-500"> *</span>}
                  </span>
                  <span className="ml-2 flex items-center gap-2">
                    <span className="max-w-[160px] truncate text-muted-foreground">{a.value ?? "—"}</span>
                    {sourceBadge(a.value_source ?? (a.value ? a.source_owner : null))}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}

// ─── Nieuw-toevoegen forms ────────────────────────────────────────────────────

function NieuwAttribuutForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [naam, setNaam] = useState("");
  const [dataType, setDataType] = useState("text");
  const [eigenaar, setEigenaar] = useState("Handmatig");
  const [vereist, setVereist] = useState(false);
  const [gewicht, setGewicht] = useState("1");
  const [saving, setSaving] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  function reset() {
    setCode(""); setNaam(""); setDataType("text"); setEigenaar("Handmatig");
    setVereist(false); setGewicht("1"); setFout(null);
  }

  async function aanmaken() {
    setSaving(true);
    setFout(null);
    try {
      const res = await postApi("/api/pim/attributes", {
        code: code.trim(), name: naam.trim(), data_type: dataType,
        source_owner: eigenaar, is_required: vereist,
        weight: parseFloat(gewicht) || 1,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      reset();
      setOpen(false);
      onCreated();
    } catch (e: any) {
      setFout(e?.message ?? "Aanmaken mislukt");
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Plus className="mr-1 h-4 w-4" /> Nieuw attribuut
      </Button>
    );
  }

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-2">
      <div className="text-sm font-medium">Nieuw attribuut</div>
      {fout && <div className="text-sm text-red-600">{fout}</div>}
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <div className="text-xs text-muted-foreground mb-1">Code</div>
          <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="bijv. kleur" className="h-8 text-sm w-36" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Naam</div>
          <Input value={naam} onChange={(e) => setNaam(e.target.value)} placeholder="bijv. Kleur" className="h-8 text-sm w-44" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Type</div>
          <Select value={dataType} onValueChange={setDataType}>
            <SelectTrigger className="h-8 text-xs w-28"><SelectValue /></SelectTrigger>
            <SelectContent>
              {["text", "number", "boolean", "select"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Eigenaar</div>
          <Select value={eigenaar} onValueChange={setEigenaar}>
            <SelectTrigger className="h-8 text-xs w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              {["DRS", "Leverancier", "Handmatig", "AI"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col items-start">
          <div className="text-xs text-muted-foreground mb-1">Vereist</div>
          <Switch checked={vereist} onCheckedChange={setVereist} />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Gewicht</div>
          <Input type="number" min="0.1" step="0.1" value={gewicht} onChange={(e) => setGewicht(e.target.value)} className="h-8 text-sm w-20" />
        </div>
        <div className="flex gap-1">
          <Button size="sm" className="h-8" onClick={aanmaken} disabled={saving || !code.trim() || !naam.trim()}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Toevoegen"}
          </Button>
          <Button size="sm" variant="ghost" className="h-8" onClick={() => { reset(); setOpen(false); }} disabled={saving}>
            Annuleer
          </Button>
        </div>
      </div>
    </div>
  );
}

function NieuwChannelForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [naam, setNaam] = useState("");
  const [codesStr, setCodesStr] = useState("");
  const [drempel, setDrempel] = useState("80");
  const [saving, setSaving] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  function reset() {
    setCode(""); setNaam(""); setCodesStr(""); setDrempel("80"); setFout(null);
  }

  async function aanmaken() {
    setSaving(true);
    setFout(null);
    try {
      const codes = codesStr.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean);
      const res = await postApi("/api/pim/channels", {
        code: code.trim(), name: naam.trim(),
        required_attribute_codes: codes,
        min_completeness_pct: parseFloat(drempel) || 0,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      reset();
      setOpen(false);
      onCreated();
    } catch (e: any) {
      setFout(e?.message ?? "Aanmaken mislukt");
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Plus className="mr-1 h-4 w-4" /> Nieuw channel
      </Button>
    );
  }

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-2">
      <div className="text-sm font-medium">Nieuw channel</div>
      {fout && <div className="text-sm text-red-600">{fout}</div>}
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <div className="text-xs text-muted-foreground mb-1">Code</div>
          <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="bijv. marketplace" className="h-8 text-sm w-36" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Naam</div>
          <Input value={naam} onChange={(e) => setNaam(e.target.value)} placeholder="bijv. Marketplace" className="h-8 text-sm w-44" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Vereiste attributen</div>
          <Input value={codesStr} onChange={(e) => setCodesStr(e.target.value)} placeholder="code1, code2, ..." className="h-8 text-xs w-64" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Drempel (%)</div>
          <Input type="number" min="0" max="100" step="1" value={drempel} onChange={(e) => setDrempel(e.target.value)} className="h-8 text-sm w-20" />
        </div>
        <div className="flex gap-1">
          <Button size="sm" className="h-8" onClick={aanmaken} disabled={saving || !code.trim() || !naam.trim()}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Toevoegen"}
          </Button>
          <Button size="sm" variant="ghost" className="h-8" onClick={() => { reset(); setOpen(false); }} disabled={saving}>
            Annuleer
          </Button>
        </div>
      </div>
    </div>
  );
}

function NieuweFamilieForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [naam, setNaam] = useState("");
  const [patternsStr, setPatternsStr] = useState("");
  const [saving, setSaving] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  function reset() {
    setCode(""); setNaam(""); setPatternsStr(""); setFout(null);
  }

  async function aanmaken() {
    setSaving(true);
    setFout(null);
    try {
      const patterns = patternsStr.split(",").map((s) => s.trim()).filter(Boolean);
      const res = await postApi("/api/pim/families", {
        code: code.trim(), name: naam.trim(),
        category_patterns: patterns,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      reset();
      setOpen(false);
      onCreated();
    } catch (e: any) {
      setFout(e?.message ?? "Aanmaken mislukt");
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Plus className="mr-1 h-4 w-4" /> Nieuwe familie
      </Button>
    );
  }

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-2">
      <div className="text-sm font-medium">Nieuwe familie</div>
      {fout && <div className="text-sm text-red-600">{fout}</div>}
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <div className="text-xs text-muted-foreground mb-1">Code</div>
          <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="bijv. papier" className="h-8 text-sm w-36" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Naam</div>
          <Input value={naam} onChange={(e) => setNaam(e.target.value)} placeholder="bijv. Papier" className="h-8 text-sm w-44" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Categoriepatronen</div>
          <Input value={patternsStr} onChange={(e) => setPatternsStr(e.target.value)} placeholder="Papier, Kopieerpapier, ..." className="h-8 text-xs w-64" />
        </div>
        <div className="flex gap-1">
          <Button size="sm" className="h-8" onClick={aanmaken} disabled={saving || !code.trim() || !naam.trim()}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Toevoegen"}
          </Button>
          <Button size="sm" variant="ghost" className="h-8" onClick={() => { reset(); setOpen(false); }} disabled={saving}>
            Annuleer
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── AttributenBeheer ─────────────────────────────────────────────────────────

function AttributenBeheer({ attrs, onChange }: { attrs: AttrDef[]; onChange: () => void }) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<Partial<AttrDef>>({});
  const [saving, setSaving] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  function startEdit(a: AttrDef) {
    setEditing(a.id);
    setDraft({ name: a.name, is_required: a.is_required, weight: a.weight, source_owner: a.source_owner, active: a.active });
    setFout(null);
  }

  async function opslaan(id: number) {
    setSaving(true);
    setFout(null);
    try {
      const res = await patchApi(`/api/pim/attributes/${id}`, draft);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setEditing(null);
      onChange();
    } catch (e: any) {
      setFout(e?.message ?? "Opslaan mislukt");
    } finally {
      setSaving(false);
    }
  }

  const [verwijderen, setVerwijderen] = useState<number | null>(null);

  async function verwijder(a: AttrDef) {
    if (!window.confirm(`Attribuut '${a.code}' definitief verwijderen? Dit kan niet ongedaan worden gemaakt.`)) return;
    setVerwijderen(a.id);
    setFout(null);
    try {
      const res = await deleteApi(`/api/pim/attributes/${a.id}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      onChange();
    } catch (e: any) {
      setFout(e?.message ?? "Verwijderen mislukt");
    } finally {
      setVerwijderen(null);
    }
  }

  const SOURCES = ["DRS", "Leverancier", "Handmatig", "AI"];

  return (
    <div className="space-y-2">
      {fout && <div className="text-sm text-red-600">{fout}</div>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Code</TableHead>
            <TableHead>Naam</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Eigenaar</TableHead>
            <TableHead>Vereist</TableHead>
            <TableHead>Gewicht</TableHead>
            <TableHead>Actief</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {attrs.map((a) => {
            const isEditing = editing === a.id;
            return (
              <TableRow key={a.id} className={!a.active ? "opacity-50" : ""}>
                <TableCell className="font-mono text-xs">{a.code}</TableCell>
                <TableCell>
                  {isEditing ? (
                    <Input
                      value={draft.name ?? ""}
                      onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                      className="h-7 text-sm w-40"
                    />
                  ) : a.name}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{a.data_type}{a.unit ? ` (${a.unit})` : ""}</TableCell>
                <TableCell>
                  {isEditing ? (
                    <Select
                      value={draft.source_owner ?? a.source_owner}
                      onValueChange={(v) => setDraft((d) => ({ ...d, source_owner: v }))}
                    >
                      <SelectTrigger className="h-7 text-xs w-32"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {SOURCES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  ) : sourceBadge(a.source_owner)}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <Switch
                      checked={draft.is_required ?? a.is_required}
                      onCheckedChange={(v) => setDraft((d) => ({ ...d, is_required: v }))}
                    />
                  ) : (
                    a.is_required
                      ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      : <span className="text-muted-foreground text-xs">—</span>
                  )}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <Input
                      type="number" min="0.1" step="0.1"
                      value={draft.weight ?? a.weight}
                      onChange={(e) => setDraft((d) => ({ ...d, weight: parseFloat(e.target.value) || d.weight }))}
                      className="h-7 text-sm w-20"
                    />
                  ) : <span className="text-sm">{a.weight}</span>}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <Switch
                      checked={draft.active ?? a.active}
                      onCheckedChange={(v) => setDraft((d) => ({ ...d, active: v }))}
                    />
                  ) : (
                    a.active
                      ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      : <XCircle className="h-4 w-4 text-red-400" />
                  )}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <div className="flex gap-1">
                      <Button size="sm" variant="default" className="h-7 px-2" onClick={() => opslaan(a.id)} disabled={saving}>
                        {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setEditing(null)} disabled={saving}>
                        <XIcon className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => startEdit(a)}>
                        Bewerk
                      </Button>
                      <Button
                        size="sm" variant="ghost"
                        className="h-7 px-2 text-red-500 hover:text-red-600"
                        onClick={() => verwijder(a)}
                        disabled={verwijderen === a.id}
                        title="Verwijder attribuut"
                        data-testid={`button-delete-attribute-${a.id}`}
                      >
                        {verwijderen === a.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                      </Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ─── ChannelsBeheer ───────────────────────────────────────────────────────────

function ChannelsBeheer({
  channels, allAttrCodes, onChange,
}: { channels: Channel[]; allAttrCodes: string[]; onChange: () => void }) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<Partial<Channel & { codesStr: string }>>({});
  const [saving, setSaving] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  function startEdit(c: Channel) {
    setEditing(c.id);
    setDraft({
      name: c.name,
      required_attribute_codes: c.required_attribute_codes,
      codesStr: (c.required_attribute_codes ?? []).join(", "),
      min_completeness_pct: c.min_completeness_pct,
      active: c.active,
    });
    setFout(null);
  }

  async function opslaan(id: number) {
    setSaving(true);
    setFout(null);
    try {
      // Parse codesStr back to array
      const codes = (draft.codesStr ?? "")
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await patchApi(`/api/pim/channels/${id}`, {
        name: draft.name,
        required_attribute_codes: codes,
        min_completeness_pct: draft.min_completeness_pct,
        active: draft.active,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setEditing(null);
      onChange();
    } catch (e: any) {
      setFout(e?.message ?? "Opslaan mislukt");
    } finally {
      setSaving(false);
    }
  }

  const [verwijderen, setVerwijderen] = useState<number | null>(null);

  async function verwijder(c: Channel) {
    if (!window.confirm(`Channel '${c.code}' definitief verwijderen? Dit kan niet ongedaan worden gemaakt.`)) return;
    setVerwijderen(c.id);
    setFout(null);
    try {
      const res = await deleteApi(`/api/pim/channels/${c.id}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      onChange();
    } catch (e: any) {
      setFout(e?.message ?? "Verwijderen mislukt");
    } finally {
      setVerwijderen(null);
    }
  }

  return (
    <div className="space-y-2">
      {fout && <div className="text-sm text-red-600">{fout}</div>}
      <p className="text-xs text-muted-foreground">
        Geldige attribuutcodes: <span className="font-mono">{allAttrCodes.join(", ")}</span>
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Code</TableHead>
            <TableHead>Naam</TableHead>
            <TableHead>Vereiste attributen</TableHead>
            <TableHead>Drempel (%)</TableHead>
            <TableHead>Actief</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {channels.map((c) => {
            const isEditing = editing === c.id;
            return (
              <TableRow key={c.id} className={!c.active ? "opacity-50" : ""}>
                <TableCell className="font-mono text-xs">{c.code}</TableCell>
                <TableCell>
                  {isEditing ? (
                    <Input
                      value={draft.name ?? ""}
                      onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                      className="h-7 text-sm w-36"
                    />
                  ) : c.name}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <Input
                      value={draft.codesStr ?? ""}
                      onChange={(e) => setDraft((d) => ({ ...d, codesStr: e.target.value }))}
                      className="h-7 text-xs w-72"
                      placeholder="code1, code2, ..."
                    />
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {(c.required_attribute_codes ?? []).map((code) => (
                        <Badge key={code} variant="outline" className="text-xs font-mono">{code}</Badge>
                      ))}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <Input
                      type="number" min="0" max="100" step="1"
                      value={draft.min_completeness_pct ?? c.min_completeness_pct}
                      onChange={(e) => setDraft((d) => ({ ...d, min_completeness_pct: parseFloat(e.target.value) || 0 }))}
                      className="h-7 text-sm w-20"
                    />
                  ) : `${c.min_completeness_pct}%`}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <Switch
                      checked={draft.active ?? c.active}
                      onCheckedChange={(v) => setDraft((d) => ({ ...d, active: v }))}
                    />
                  ) : (
                    c.active
                      ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      : <XCircle className="h-4 w-4 text-red-400" />
                  )}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <div className="flex gap-1">
                      <Button size="sm" variant="default" className="h-7 px-2" onClick={() => opslaan(c.id)} disabled={saving}>
                        {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setEditing(null)} disabled={saving}>
                        <XIcon className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => startEdit(c)}>
                        Bewerk
                      </Button>
                      <Button
                        size="sm" variant="ghost"
                        className="h-7 px-2 text-red-500 hover:text-red-600"
                        onClick={() => verwijder(c)}
                        disabled={verwijderen === c.id}
                        title="Verwijder channel"
                        data-testid={`button-delete-channel-${c.id}`}
                      >
                        {verwijderen === c.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                      </Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ─── FamiliesBeheer ───────────────────────────────────────────────────────────

function FamiliesBeheer({ families, onChange }: { families: Family[]; onChange: () => void }) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<{ name: string; patternsStr: string; active: boolean }>({
    name: "", patternsStr: "", active: true,
  });
  const [saving, setSaving] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  function startEdit(f: Family) {
    setEditing(f.id);
    setDraft({
      name: f.name,
      patternsStr: (f.category_patterns ?? []).join(", "),
      active: f.active,
    });
    setFout(null);
  }

  async function opslaan(id: number) {
    setSaving(true);
    setFout(null);
    try {
      const patterns = draft.patternsStr
        .split(/,/)
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await patchApi(`/api/pim/families/${id}`, {
        name: draft.name,
        category_patterns: patterns,
        active: draft.active,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setEditing(null);
      onChange();
    } catch (e: any) {
      setFout(e?.message ?? "Opslaan mislukt");
    } finally {
      setSaving(false);
    }
  }

  const [verwijderen, setVerwijderen] = useState<number | null>(null);

  async function verwijder(f: Family) {
    if (!window.confirm(`Familie '${f.code}' definitief verwijderen? Dit kan niet ongedaan worden gemaakt.`)) return;
    setVerwijderen(f.id);
    setFout(null);
    try {
      const res = await deleteApi(`/api/pim/families/${f.id}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      onChange();
    } catch (e: any) {
      setFout(e?.message ?? "Verwijderen mislukt");
    } finally {
      setVerwijderen(null);
    }
  }

  return (
    <div className="space-y-2">
      {fout && <div className="text-sm text-red-600">{fout}</div>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Code</TableHead>
            <TableHead>Naam</TableHead>
            <TableHead>Categoriepatronen</TableHead>
            <TableHead>Producten</TableHead>
            <TableHead>Actief</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {families.map((f) => {
            const isEditing = editing === f.id;
            return (
              <TableRow key={f.id} className={!f.active ? "opacity-50" : ""}>
                <TableCell className="font-mono text-xs">{f.code}</TableCell>
                <TableCell>
                  {isEditing ? (
                    <Input
                      value={draft.name}
                      onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                      className="h-7 text-sm w-36"
                    />
                  ) : f.name}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <Input
                      value={draft.patternsStr}
                      onChange={(e) => setDraft((d) => ({ ...d, patternsStr: e.target.value }))}
                      className="h-7 text-xs w-64"
                      placeholder="Papier, Kopieerpapier, ..."
                    />
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {(f.category_patterns ?? []).map((p) => (
                        <Badge key={p} variant="outline" className="text-xs">{p}</Badge>
                      ))}
                    </div>
                  )}
                </TableCell>
                <TableCell className="text-sm">{f.product_count}</TableCell>
                <TableCell>
                  {isEditing ? (
                    <Switch
                      checked={draft.active}
                      onCheckedChange={(v) => setDraft((d) => ({ ...d, active: v }))}
                    />
                  ) : (
                    f.active
                      ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      : <XCircle className="h-4 w-4 text-red-400" />
                  )}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <div className="flex gap-1">
                      <Button size="sm" variant="default" className="h-7 px-2" onClick={() => opslaan(f.id)} disabled={saving}>
                        {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setEditing(null)} disabled={saving}>
                        <XIcon className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => startEdit(f)}>
                        Bewerk
                      </Button>
                      <Button
                        size="sm" variant="ghost"
                        className="h-7 px-2 text-red-500 hover:text-red-600"
                        onClick={() => verwijder(f)}
                        disabled={verwijderen === f.id}
                        title="Verwijder familie"
                        data-testid={`button-delete-family-${f.id}`}
                      >
                        {verwijderen === f.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                      </Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ─── BeheerTab ────────────────────────────────────────────────────────────────

function BeheerTab() {
  const [attrs, setAttrs] = useState<AttrDef[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [families, setFamilies] = useState<Family[]>([]);
  const [laden, setLaden] = useState(true);
  const [fout, setFout] = useState<string | null>(null);
  const [sectie, setSectie] = useState<"attributen" | "channels" | "families">("attributen");

  const laad = useCallback(async () => {
    setLaden(true);
    setFout(null);
    try {
      const [aRes, cRes, fRes] = await Promise.all([
        fetch(`${BASE}/api/pim/attributes`, { headers: getAuthHeaders(), signal: AbortSignal.timeout(30_000) }),
        fetch(`${BASE}/api/pim/channels`, { headers: getAuthHeaders(), signal: AbortSignal.timeout(30_000) }),
        fetch(`${BASE}/api/pim/families`, { headers: getAuthHeaders(), signal: AbortSignal.timeout(30_000) }),
      ]);
      if (!aRes.ok || !cRes.ok || !fRes.ok) throw new Error("Laden mislukt");
      setAttrs(await aRes.json());
      setChannels(await cRes.json());
      setFamilies(await fRes.json());
    } catch (e: any) {
      setFout(e?.message ?? "Onbekende fout");
    } finally {
      setLaden(false);
    }
  }, []);

  useEffect(() => { laad(); }, [laad]);

  const allAttrCodes = attrs.map((a) => a.code);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(["attributen", "channels", "families"] as const).map((s) => (
          <Button
            key={s}
            variant={sectie === s ? "default" : "outline"}
            size="sm"
            onClick={() => setSectie(s)}
            className="capitalize"
          >
            {s === "attributen" ? `Attributen (${attrs.length})` :
             s === "channels" ? `Channels (${channels.length})` :
             `Families (${families.length})`}
          </Button>
        ))}
      </div>

      {fout && <div className="text-sm text-red-600">{fout}</div>}

      {laden ? (
        <div className="space-y-2">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
      ) : (
        <>
          {sectie === "attributen" && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">
                  Attribuutdefinities
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    — stel in welke attributen vereist zijn, hun gewicht en eigenaar
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <NieuwAttribuutForm onCreated={laad} />
                <AttributenBeheer attrs={attrs} onChange={laad} />
              </CardContent>
            </Card>
          )}

          {sectie === "channels" && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">
                  Channels
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    — stel vereiste attributen en completeness-drempel per channel in
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <NieuwChannelForm onCreated={laad} />
                <ChannelsBeheer channels={channels} allAttrCodes={allAttrCodes} onChange={laad} />
              </CardContent>
            </Card>
          )}

          {sectie === "families" && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">
                  Productfamilies
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    — koppel categorieën automatisch aan families via patroonmatch
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <NieuweFamilieForm onCreated={laad} />
                <FamiliesBeheer families={families} onChange={laad} />
              </CardContent>
            </Card>
          )}
        </>
      )}

      <p className="text-xs text-muted-foreground">
        Na aanpassingen: klik op "Herbereken scores" in het Overzicht-tabblad om de completeness-scores bij te werken.
      </p>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PimContent() {
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [rows, setRows] = useState<CompletenessRow[]>([]);
  const [totaal, setTotaal] = useState(0);
  const [laden, setLaden] = useState(true);
  const [herberekenen, setHerberekenen] = useState(false);
  const [fout, setFout] = useState<string | null>(null);
  const [kanaal, setKanaal] = useState<string>("overall");
  const [zoek, setZoek] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [tab, setTab] = useState<"overzicht" | "beheer">("overzicht");

  const laad = useCallback(async () => {
    setLaden(true);
    setFout(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (kanaal !== "overall") params.set("channel", kanaal);
      if (zoek.trim()) params.set("search", zoek.trim());
      let overviewUrl = `${BASE}/api/pim/overview`;
      if (fp !== "") overviewUrl += overviewUrl.includes("?") ? `&${fp}` : `?${fp}`;
      let completenessUrl = `${BASE}/api/pim/completeness?${params}`;
      if (fp !== "") completenessUrl += completenessUrl.includes("?") ? `&${fp}` : `?${fp}`;
      const [ovRes, listRes] = await Promise.all([
        fetch(overviewUrl, { headers: getAuthHeaders(), signal: AbortSignal.timeout(60_000) }),
        fetch(completenessUrl, { headers: getAuthHeaders(), signal: AbortSignal.timeout(60_000) }),
      ]);
      if (!ovRes.ok || !listRes.ok) throw new Error("Laden mislukt");
      const ov = await ovRes.json();
      const list = await listRes.json();
      setOverview(ov);
      setRows(list.items ?? []);
      setTotaal(list.total ?? 0);
    } catch (e: any) {
      setFout(e?.message ?? "Onbekende fout");
    } finally {
      setLaden(false);
    }
  }, [kanaal, zoek, fp]);

  useEffect(() => { laad(); }, [laad]);

  const herbereken = async () => {
    setHerberekenen(true);
    try {
      const res = await fetch(`${BASE}/api/pim/recompute`, {
        method: "POST", headers: getAuthHeaders(), signal: AbortSignal.timeout(120_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await laad();
    } catch (e: any) {
      setFout(e?.message ?? "Herberekenen mislukt");
    } finally {
      setHerberekenen(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Content Completeness (PIM)</h1>
          <p className="text-sm text-muted-foreground">
            Productcontent-volledigheid en -kwaliteit per SKU en per channel, met bron-eigenaarschap per veld.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {tab === "overzicht" && (
            <Button onClick={herbereken} disabled={herberekenen} variant="outline">
              {herberekenen ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Herbereken scores
            </Button>
          )}
        </div>
      </div>

      <GlobalFilterBar />

      {/* Tab switcher */}
      <div className="flex gap-2 border-b pb-0">
        <button
          onClick={() => setTab("overzicht")}
          className={`flex items-center gap-1.5 px-3 pb-2 text-sm font-medium border-b-2 transition-colors ${
            tab === "overzicht"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <BarChart3 className="h-4 w-4" />
          Overzicht
        </button>
        <button
          onClick={() => setTab("beheer")}
          className={`flex items-center gap-1.5 px-3 pb-2 text-sm font-medium border-b-2 transition-colors ${
            tab === "beheer"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Settings className="h-4 w-4" />
          Beheer
        </button>
      </div>

      {/* Overzicht tab */}
      {tab === "overzicht" && (
        <>
          {overview && (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Card><CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">Gem. completeness</CardTitle></CardHeader>
                <CardContent><div className="text-2xl font-semibold">{overview.avg_completeness_pct.toFixed(1)}%</div></CardContent></Card>
              <Card><CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">Gem. kwaliteit</CardTitle></CardHeader>
                <CardContent><div className="text-2xl font-semibold">{overview.avg_quality_score.toFixed(1)}</div></CardContent></Card>
              <Card><CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">Onder 60%</CardTitle></CardHeader>
                <CardContent><div className="text-2xl font-semibold">{overview.low_completeness_count}</div></CardContent></Card>
              <Card><CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">Open AI-suggesties</CardTitle></CardHeader>
                <CardContent><div className="text-2xl font-semibold">{overview.pending_suggestions}</div></CardContent></Card>
            </div>
          )}

          {overview && overview.channels.length > 0 && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {overview.channels.map((ch) => (
                <Card key={ch.code}>
                  <CardHeader className="pb-1">
                    <CardTitle className="text-sm font-medium">Channel readiness — {ch.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between text-sm">
                    <span>{ch.skus_ready} van {ch.skus_scored} SKU's ready (drempel {ch.min_completeness_pct}%)</span>
                    {pctBadge(ch.avg_completeness_pct)}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          <Card>
            <CardHeader className="pb-2">
              <div className="flex flex-wrap items-center gap-3">
                <Select value={kanaal} onValueChange={setKanaal}>
                  <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="overall">Totaal (alle attributen)</SelectItem>
                    {(overview?.channels ?? []).map((c) => (
                      <SelectItem key={c.code} value={c.code}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  placeholder="Zoek op SKU of naam…"
                  value={zoek}
                  onChange={(e) => setZoek(e.target.value)}
                  className="w-64"
                />
                <span className="text-sm text-muted-foreground">{totaal} SKU's</span>
              </div>
            </CardHeader>
            <CardContent>
              {fout && <div className="mb-3 text-sm text-red-600">{fout}</div>}
              {laden ? (
                <div className="space-y-2">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
              ) : rows.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  Geen scores gevonden. Klik op "Herbereken scores" om de contentlaag te vullen vanuit de productmaster.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>SKU</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead>Merk</TableHead>
                      <TableHead>Completeness</TableHead>
                      <TableHead>Kwaliteit</TableHead>
                      <TableHead>{kanaal !== "overall" ? "Ready" : "Ontbrekend"}</TableHead>
                      <TableHead className="w-8" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((r) => (
                      <>
                        <TableRow
                          key={r.sku_id}
                          className="cursor-pointer"
                          onClick={() => setOpen(open === r.sku_id ? null : r.sku_id)}
                        >
                          <TableCell className="font-mono text-xs">{r.sku_id}</TableCell>
                          <TableCell className="max-w-[280px] truncate">{r.product_name}</TableCell>
                          <TableCell>{r.brand ?? "—"}</TableCell>
                          <TableCell>{pctBadge(r.completeness_pct)}</TableCell>
                          <TableCell>{r.quality_score.toFixed(0)}</TableCell>
                          <TableCell>
                            {kanaal !== "overall" ? (
                              r.channel_ready
                                ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                                : <XCircle className="h-4 w-4 text-red-500" />
                            ) : (
                              <span className="text-xs text-muted-foreground">{r.missing_attributes.length} veld(en)</span>
                            )}
                          </TableCell>
                          <TableCell>{open === r.sku_id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</TableCell>
                        </TableRow>
                        {open === r.sku_id && <DetailRij key={`${r.sku_id}-detail`} row={r} />}
                      </>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Beheer tab */}
      {tab === "beheer" && <BeheerTab />}
    </div>
  );
}
