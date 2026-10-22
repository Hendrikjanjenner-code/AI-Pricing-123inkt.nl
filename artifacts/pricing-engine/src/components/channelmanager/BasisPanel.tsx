import { useEffect, useMemo, useState } from "react";
import { FileDown, Plus, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ChannelInputRow } from "@workspace/api-client-react";
import { cmApi, dash, decError, fmtDate } from "@/lib/channelmanager/api";
import type { BasisCsvMapping, BasisMeta, ChannelConfig } from "@/lib/channelmanager/api";
import { parseBasis } from "@/lib/channelmanager/model";
import type { BasisRow, Overview } from "@/lib/channelmanager/model";
import { DECIMALS, DELIMITERS, downloadTemplate, readCsvHeader } from "@/lib/channelmanager/csv";
import { manualRowErrors, toInputRows } from "@/lib/channelmanager/rows";
import { useCmAction } from "@/hooks/use-channelmanager";
import type { CmScope } from "@/hooks/use-channelmanager";
import { ErrorBox, Fact, Facts, Field, HistoryList, NotesButton, RecordLoader, RowsTable, Section, StatusBadge, inputCls } from "./common";

type Delim = NonNullable<ChannelConfig["delimiter"]>;
type Dec = NonNullable<ChannelConfig["decimal"]>;
type FieldKey = keyof BasisCsvMapping;
const FIELDS: { key: FieldKey; label: string; required?: boolean }[] = [
  { key: "sku", label: "SKU", required: true }, { key: "name", label: "Naam" }, { key: "category", label: "Categorie" },
  { key: "base_price", label: "Basisprijs", required: true }, { key: "cost", label: "Kostprijs (netto)" }, { key: "current_price", label: "Huidige prijs" },
];
const PROVENANCE_NL = { manual_csv: "Handmatige CSV / invoer", PriceShape_unverified: "PriceShape (onbevestigd)" } as const;
const blankRow = (): Record<FieldKey, string> => ({ sku: "", name: "", category: "", base_price: "", cost: "", current_price: "" });

interface MetaForm { currency: string; price_basis: "net" | "gross" | ""; vat_rate: string; provenance: BasisMeta["provenance"] | ""; notes: string }

export function BasisPanel({ scope, overview, canPropose, canApprove }: { scope: CmScope; overview: Overview; canPropose: boolean; canApprove: boolean }) {
  const [mode, setMode] = useState<"csv" | "manual">("csv");
  const [meta, setMeta] = useState<MetaForm>({ currency: "", price_basis: "", vat_rate: "", provenance: "", notes: "" });
  const [selected, setSelected] = useState<number | null>(null);
  const { run, busy, lastError } = useCmAction(scope);
  useEffect(() => { setSelected(null); }, [scope.scopeToken]);
  const active = overview.basis ? parseBasis(overview.basis) : null;

  const metaErr = {
    currency: /^[A-Z]{3}$/.test(meta.currency) ? null : "Drie hoofdletters, bv. EUR",
    vat: decError(meta.vat_rate, { required: true, max: 1 }),
    basis: meta.price_basis ? null : "Kies bruto of netto",
    prov: meta.provenance ? null : "Kies de herkomst",
    notes: meta.notes.trim() ? null : "Toelichting verplicht",
  };
  const metaOk = Object.values(metaErr).every(v => !v);
  const body = (): BasisMeta | null => metaOk && meta.price_basis && meta.provenance ? {
    currency: meta.currency, price_basis: meta.price_basis, vat_rate: meta.vat_rate.trim(), cost_basis: "net", provenance: meta.provenance, notes: meta.notes.trim(),
  } : null;
  const staged = (s: unknown) => { if (s) setSelected(parseBasis(s).snap.id); };

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        {active ? (
          <div className="rounded-md border bg-card p-3 text-sm flex flex-wrap items-center gap-3" data-testid="text-active-basis">
            Actieve goedgekeurde basis: <span className="font-mono">#{active.snap.id}</span> r{active.snap.revision} <StatusBadge status={active.snap.status} />
            <span className="text-xs text-muted-foreground">{fmtDate(active.snap.created_at)} · {active.data.rows.length} rijen · {PROVENANCE_NL[active.data.provenance]} · {active.data.currency} {active.data.price_basis === "gross" ? "bruto" : "netto"} btw {active.data.vat_rate}</span>
          </div>
        ) : <p className="text-sm text-muted-foreground" data-testid="text-no-basis">Nog geen goedgekeurde basis voor deze winkel.</p>}

        <Section title="Nieuwe basis klaarzetten" aside={
          <div className="flex rounded-md border p-0.5 text-xs">
            {(["csv", "manual"] as const).map(m => <button key={m} type="button" onClick={() => setMode(m)} className={`px-2.5 py-1 rounded ${mode === m ? "bg-primary text-primary-foreground" : ""}`} data-testid={`tab-basis-${m}`}>{m === "csv" ? "CSV-upload" : "Handmatig scenario"}</button>)}
          </div>
        }>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Valuta" error={metaErr.currency}><input className={inputCls} maxLength={3} placeholder="EUR" value={meta.currency} onChange={e => setMeta({ ...meta, currency: e.target.value.toUpperCase() })} data-testid="input-basis-currency" /></Field>
            <Field label="Prijsbasis invoer" error={metaErr.basis}><select className={inputCls} value={meta.price_basis} onChange={e => setMeta({ ...meta, price_basis: e.target.value as MetaForm["price_basis"] })} data-testid="select-basis-price-basis"><option value="" disabled>— kies —</option><option value="gross">Bruto (incl. btw)</option><option value="net">Netto (excl. btw)</option></select></Field>
            <Field label="Btw-tarief (0–1)" error={metaErr.vat}><input className={inputCls} placeholder="bv. 0.21" value={meta.vat_rate} onChange={e => setMeta({ ...meta, vat_rate: e.target.value })} data-testid="input-basis-vat" /></Field>
            <Field label="Herkomst" error={metaErr.prov}><select className={inputCls} value={meta.provenance} onChange={e => setMeta({ ...meta, provenance: e.target.value as MetaForm["provenance"] })} data-testid="select-provenance"><option value="" disabled>— kies —</option><option value="manual_csv">{PROVENANCE_NL.manual_csv}</option><option value="PriceShape_unverified">{PROVENANCE_NL.PriceShape_unverified}</option></select></Field>
          </div>
          <p className="text-xs text-muted-foreground">Kosten worden altijd als netto vastgelegd. Valuta geldt voor alle prijzen en kosten; geen wisselkoersconversie.</p>
          <Field label="Toelichting / bron" error={meta.notes ? null : metaErr.notes}><Textarea maxLength={2000} value={meta.notes} onChange={e => setMeta({ ...meta, notes: e.target.value })} data-testid="input-basis-notes" /></Field>
          {mode === "csv"
            ? <CsvUpload disabled={!canPropose || !metaOk || !!busy} busy={busy === "csv"} onSubmit={(settings, file) => { const b = body(); if (b) void run("csv", () => cmApi.stageBasisCsv(scope.shopId, { ...b, ...settings }, file), "Basis klaargezet").then(staged); }} />
            : <ManualRows disabled={!canPropose || !metaOk || !!busy} busy={busy === "manual"} onSubmit={rows => { const b = body(); if (b) void run("manual", () => cmApi.stageBasis(scope.shopId, { ...b, rows }), "Scenario klaargezet").then(staged); }} />}
          {!canPropose && <p className="text-xs text-muted-foreground">Vereist recht pricing.propose.</p>}
          {lastError && (lastError.name === "csv" || lastError.name === "manual") && <ErrorBox error={lastError.error} />}
        </Section>

        {selected !== null && (
          <Section title="Klaargezette basis">
            <RecordLoader scope={scope} id={selected} parse={parseBasis} onClose={() => setSelected(null)}>
              {({ snap, data }) => (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-3 text-sm"><StatusBadge status={snap.status} /><span>{data.rows.length} rijen</span><span className="text-xs text-muted-foreground">door {snap.created_by} · {fmtDate(snap.created_at)}</span></div>
                  <Facts>
                    <Fact label="Herkomst">{PROVENANCE_NL[data.provenance]}</Fact>
                    <Fact label="Valuta / basis">{data.currency} · {data.price_basis === "gross" ? "bruto" : "netto"}</Fact>
                    <Fact label="Btw">{data.vat_rate}</Fact>
                    <Fact label="Kostbasis">{data.cost_basis}</Fact>
                  </Facts>
                  <p className="text-xs">{data.notes}</p>
                  {data.approval && <p className="text-xs text-emerald-700" data-testid="text-basis-approval">Goedgekeurd door {data.approval.by} op {fmtDate(data.approval.at)}: {data.approval.notes}</p>}
                  <RowsTable testid="table-basis" rows={data.rows} columns={[
                    { label: "SKU", cell: r => r.sku, mono: true }, { label: "Naam", cell: r => dash(r.name) }, { label: "Categorie", cell: r => dash(r.category) },
                    { label: "Basis", cell: r => r.base_price, mono: true }, { label: "Kost", cell: r => dash(r.cost), mono: true }, { label: "Huidig", cell: r => dash(r.current_price), mono: true },
                  ]} />
                  {snap.status === "staged" && (
                    <NotesButton label="Basis goedkeuren" testid="button-approve-basis" busy={busy === "approve"} disabled={!canApprove}
                      reason={!canApprove ? "Vereist recht pricing.approve." : "Goedkeuren maakt deze versie de actieve basis voor berekeningen."}
                      onSubmit={n => void run("approve", () => cmApi.approveBasis(scope.shopId, snap.id, { notes: n }), "Basis goedgekeurd")} />
                  )}
                  {lastError?.name === "approve" && <ErrorBox error={lastError.error} />}
                </div>
              )}
            </RecordLoader>
          </Section>
        )}
      </div>
      <HistoryList scope={scope} kind="basis" title="Basisversies" selectedId={selected} onSelect={s => setSelected(s.id)} />
    </div>
  );
}

function CsvUpload({ disabled, busy, onSubmit }: { disabled: boolean; busy: boolean; onSubmit: (s: { mapping: BasisCsvMapping; delimiter: Delim; decimal: Dec }, f: File) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [delimiter, setDelimiter] = useState<Delim | "">("");
  const [decimal, setDecimal] = useState<Dec | "">("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<BasisCsvMapping>({});
  useEffect(() => {
    setMapping({});
    if (file && delimiter) void readCsvHeader(file, delimiter).then(setHeaders); else setHeaders([]);
  }, [file, delimiter]);
  const tooBig = !!file && file.size > 2 * 1024 * 1024;
  const missing = FIELDS.filter(f => f.required && !mapping[f.key]);
  const used = Object.values(mapping).filter(Boolean);
  const dupe = new Set(used).size !== used.length;
  const ok = file && delimiter && decimal && delimiter !== decimal && !tooBig && !missing.length && !dupe;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Field label="Bestand" error={tooBig ? "Groter dan 2 MiB" : null} hint="Max 5.000 rijen, 500 tekens per cel"><input type="file" accept=".csv,text/csv" className="text-xs" onChange={e => setFile(e.target.files?.[0] ?? null)} data-testid="input-basis-file" /></Field>
        <Field label="Scheidingsteken" error={file && !delimiter ? "Kies eerst" : null}><select className={inputCls} value={delimiter} onChange={e => setDelimiter(e.target.value as Delim)} data-testid="select-basis-delimiter"><option value="" disabled>— kies —</option>{DELIMITERS.map(d => <option key={d.label} value={d.value}>{d.label}</option>)}</select></Field>
        <Field label="Decimaalteken" error={delimiter && delimiter === decimal ? "Gelijk aan scheidingsteken" : null} hint="Duizendtalscheiding wordt niet ondersteund"><select className={inputCls} value={decimal} onChange={e => setDecimal(e.target.value as Dec)} data-testid="select-basis-decimal"><option value="" disabled>— kies —</option>{DECIMALS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}</select></Field>
        <div className="flex items-end"><Button size="sm" variant="ghost" disabled={!delimiter} onClick={() => delimiter && downloadTemplate("basis", delimiter)} data-testid="button-template-basis"><FileDown className="h-4 w-4 mr-1" />Leeg sjabloon</Button></div>
      </div>
      {file && delimiter && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Bestand <span className="font-mono">{file.name}</span>: {headers.length} kolommen in de kopregel. Koppel elk veld expliciet; er is geen automatische koppeling.</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {FIELDS.map(f => (
              <Field key={f.key} label={`${f.label}${f.required ? " *" : ""}`}>
                <select className={inputCls} value={mapping[f.key] ?? ""} onChange={e => setMapping(m => { const n = { ...m }; if (e.target.value) n[f.key] = e.target.value; else delete n[f.key]; return n; })} data-testid={`select-map-${f.key}`}>
                  <option value="">— niet gekoppeld —</option>{headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </Field>
            ))}
          </div>
          {dupe && <p className="text-xs text-destructive">Een bronkolom is aan meerdere velden gekoppeld.</p>}
          {missing.length > 0 && <p className="text-xs text-muted-foreground">Nog koppelen: {missing.map(m => m.label).join(", ")}</p>}
        </div>
      )}
      <Button disabled={disabled || !ok || busy} onClick={() => { if (file && delimiter && decimal) onSubmit({ mapping, delimiter, decimal }, file); }} data-testid="button-upload-basis">
        <Upload className="h-4 w-4 mr-1" />{busy ? "Uploaden…" : "Uploaden en klaarzetten"}
      </Button>
    </div>
  );
}

function ManualRows({ disabled, busy, onSubmit }: { disabled: boolean; busy: boolean; onSubmit: (rows: ChannelInputRow[]) => void }) {
  const [rows, setRows] = useState([blankRow()]);
  const errs = useMemo(() => manualRowErrors(rows), [rows]);
  const ok = rows.length > 0 && rows.length <= 5000 && errs.every(e => !e.length);
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto"><table className="w-full text-xs">
        <thead><tr>{FIELDS.map(f => <th key={f.key} className="text-left px-1 py-1">{f.label}{f.required ? " *" : ""}</th>)}<th /></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i} className="align-top">
            {FIELDS.map(f => <td key={f.key} className="px-1 py-0.5"><input className={`${inputCls} h-8 w-full min-w-[90px]`} value={r[f.key]} onChange={e => setRows(rows.map((x, j) => j === i ? { ...x, [f.key]: e.target.value } : x))} data-testid={`input-manual-${f.key}-${i}`} /></td>)}
            <td className="px-1"><Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label="Rij verwijderen" data-testid={`button-remove-manual-${i}`}><Trash2 className="h-4 w-4" /></Button></td>
            {errs[i].length > 0 && <td className="text-destructive px-1 py-1 whitespace-nowrap" data-testid={`text-manual-error-${i}`}>{errs[i].join("; ")}</td>}
          </tr>
        ))}</tbody>
      </table></div>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => setRows([...rows, blankRow()])} data-testid="button-add-manual-row"><Plus className="h-3.5 w-3.5 mr-1" />Rij</Button>
        <Button size="sm" disabled={disabled || !ok || busy} onClick={() => onSubmit(toInputRows(rows))} data-testid="button-stage-manual">{busy ? "Bezig…" : "Scenario klaarzetten"}</Button>
      </div>
    </div>
  );
}
