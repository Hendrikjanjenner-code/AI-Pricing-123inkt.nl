import { useEffect, useState } from "react";
import { Download, FileDown, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cmApi, decError, fmtDate } from "@/lib/channelmanager/api";
import type { ChannelConfig } from "@/lib/channelmanager/api";
import { parseExport, parseReadback, readbackBuckets } from "@/lib/channelmanager/model";
import type { ExportData, Overview, ReadbackCompare, ReadbackData, Snapshot } from "@/lib/channelmanager/model";
import { DECIMALS, DELIMITERS, downloadTemplate, readCsvHeader, saveBlob } from "@/lib/channelmanager/csv";
import { useCmAction } from "@/hooks/use-channelmanager";
import type { CmScope } from "@/hooks/use-channelmanager";
import { ErrorBox, Fact, Facts, Field, HistoryList, RecordLoader, RowsTable, Section, StatusBadge, inputCls } from "./common";

type Delim = NonNullable<ChannelConfig["delimiter"]>;
type Dec = NonNullable<ChannelConfig["decimal"]>;
type Bucket = "matching" | "missing" | "mismatch" | "unexpected" | "duplicate";
const BUCKETS: { key: Bucket; label: string; tone: string }[] = [
  { key: "matching", label: "Overeenkomend", tone: "text-emerald-700" }, { key: "missing", label: "Ontbrekend", tone: "text-amber-700" },
  { key: "mismatch", label: "Afwijkend", tone: "text-destructive" }, { key: "unexpected", label: "Onverwacht", tone: "text-amber-700" },
  { key: "duplicate", label: "Dubbel", tone: "text-destructive" },
];

export function ExportPanel({ scope, canPropose, canExport, focusId }: { scope: CmScope; overview: Overview; canPropose: boolean; canExport: boolean; focusId: number }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [readbackView, setReadbackView] = useState<number | null>(null);
  useEffect(() => { setSelected(null); setReadbackView(null); }, [scope.scopeToken, focusId]);
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
          Exportformaat en DRS-terugleesformaat zijn voorlopig en extern niet bevestigd. Downloaden markeert een export nooit als verwerkt; alleen een volledig overeenkomende DRS-terugmelding (status "Volledig overeenkomend") bewijst verwerking.
        </div>
        {selected === null ? <p className="text-sm text-muted-foreground" data-testid="text-pick-export">Kies rechts een exportversie om kolommen te bekijken, te downloaden of een DRS-terugmelding te vergelijken.</p> : (
          <Section title="Exportversie">
            <RecordLoader scope={scope} id={selected} parse={parseExport} onClose={() => setSelected(null)}>
              {x => <ExportDetail scope={scope} exp={x} canPropose={canPropose} canExport={canExport} onReadback={id => setReadbackView(id)} />}
            </RecordLoader>
          </Section>
        )}
        {readbackView !== null && (
          <Section title="DRS-vergelijking">
            <RecordLoader scope={scope} id={readbackView} parse={parseReadback} onClose={() => setReadbackView(null)}>
              {x => <ReadbackDetail snap={x.snap} data={x.data} />}
            </RecordLoader>
          </Section>
        )}
      </div>
      <div className="space-y-4">
        <HistoryList scope={scope} kind="export" title="Exportversies (onveranderlijk)" selectedId={selected} onSelect={s => setSelected(s.id)} />
        <HistoryList scope={scope} kind="readback" title="DRS-terugmeldingen" selectedId={readbackView} onSelect={s => setReadbackView(s.id)} />
      </div>
    </div>
  );
}

function ExportDetail({ scope, exp, canPropose, canExport, onReadback }: { scope: CmScope; exp: { snap: Snapshot; data: ExportData }; canPropose: boolean; canExport: boolean; onReadback: (id: number) => void }) {
  const { snap, data } = exp;
  const { run, busy, lastError } = useCmAction(scope);
  const lines = data.csv.split(/\r?\n/).filter(Boolean);
  const download = () => void run("download", async () => {
    const blob = await cmApi.download(scope.shopId, snap.id);
    saveBlob(blob, `channel-export-${snap.id}.csv`);
    return true;
  });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <StatusBadge status={snap.status} />
        <span className={`text-xs ${data.processed ? "text-emerald-700" : "text-muted-foreground"}`} data-testid="text-export-processed">{data.processed ? "Verwerking bewezen" : "Verwerking niet bewezen"}</span>
        <Button size="sm" onClick={download} disabled={!canExport || !!busy} data-testid="button-download-export"><Download className="h-4 w-4 mr-1" />{busy === "download" ? "Downloaden…" : "Download CSV"}</Button>
        {!canExport && <span className="text-xs text-muted-foreground">Download vereist pricing.approve.</span>}
      </div>
      <Facts>
        <Fact label="Vingerafdruk (sha256)"><span data-testid="text-fingerprint">{data.fingerprint}</span></Fact>
        <Fact label="Berekening">#{data.calculation_id}</Fact>
        <Fact label="Basis / configuratie">#{data.basis_id} / #{data.config_id}</Fact>
        <Fact label="Aangemaakt">{fmtDate(snap.created_at)} · {snap.created_by}</Fact>
      </Facts>
      <p className="text-xs">{data.notes}</p>
      <p className="text-[11px] font-mono text-muted-foreground">Kolommen: {Object.entries(data.schema).map(([h, f]) => `${h}=${f}`).join(", ")} · {data.rows.length} rijen</p>
      <div className="max-h-60 overflow-auto rounded border bg-muted/30 p-2 font-mono text-[11px] leading-relaxed" data-testid="text-export-csv-preview">
        {lines.slice(0, 30).map((l, i) => <div key={i} className={i === 0 ? "font-semibold" : ""}>{l}</div>)}
        {lines.length > 30 && <div className="text-muted-foreground">… {lines.length - 30} regels meer</div>}
      </div>
      {lastError && <ErrorBox error={lastError.error} />}
      <ReadbackUpload scope={scope} exportId={snap.id} config={data.config} canPropose={canPropose} onDone={onReadback} />
    </div>
  );
}

function ReadbackUpload({ scope, exportId, config, canPropose, onDone }: { scope: CmScope; exportId: number; config: ChannelConfig; canPropose: boolean; onDone: (id: number) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [delimiter, setDelimiter] = useState<Delim | "">("");
  const [decimal, setDecimal] = useState<Dec | "">("");
  const [currency, setCurrency] = useState("");
  const [basis, setBasis] = useState<"net" | "gross" | "">("");
  const [vat, setVat] = useState("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [sku, setSku] = useState(""); const [price, setPrice] = useState("");
  const { run, busy, lastError } = useCmAction(scope);
  useEffect(() => { setSku(""); setPrice(""); if (file && delimiter) void readCsvHeader(file, delimiter).then(setHeaders); else setHeaders([]); }, [file, delimiter]);
  const vatErr = decError(vat, { required: true, max: 1 });
  const ok = !!file && !!sku && !!price && sku !== price && /^[A-Z]{3}$/.test(currency) && !!basis && !vatErr && !!delimiter && !!decimal && delimiter !== decimal && file.size <= 2 * 1024 * 1024;
  return (
    <div className="space-y-3 border-t pt-3">
      <h4 className="text-sm font-semibold">DRS-terugmelding vergelijken met deze export</h4>
      <p className="text-xs text-muted-foreground">Valuta, prijsbasis en btw moeten exact gelijk zijn aan de export ({config.currency}, {config.price_basis === "gross" ? "bruto" : "netto"}, btw {config.vat_rate}); vul ze expliciet in zoals ze in het DRS-bestand staan. Tolerantie: {config.readback_tolerance ?? "0"}.</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Field label="Bestand"><input type="file" accept=".csv,text/csv" className="text-xs" onChange={e => setFile(e.target.files?.[0] ?? null)} data-testid="input-readback-file" /></Field>
        <Field label="Scheidingsteken"><select className={inputCls} value={delimiter} onChange={e => setDelimiter(e.target.value as Delim)} data-testid="select-readback-delimiter"><option value="" disabled>— kies —</option>{DELIMITERS.map(d => <option key={d.label} value={d.value}>{d.label}</option>)}</select></Field>
        <Field label="Decimaalteken" error={delimiter && delimiter === decimal ? "Gelijk aan scheidingsteken" : null}><select className={inputCls} value={decimal} onChange={e => setDecimal(e.target.value as Dec)} data-testid="select-readback-decimal"><option value="" disabled>— kies —</option>{DECIMALS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}</select></Field>
        <div className="flex items-end"><Button size="sm" variant="ghost" disabled={!delimiter} onClick={() => delimiter && downloadTemplate("readback", delimiter)} data-testid="button-template-readback"><FileDown className="h-4 w-4 mr-1" />Leeg sjabloon</Button></div>
        <Field label="Valuta"><input className={inputCls} maxLength={3} placeholder="EUR" value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())} data-testid="input-readback-currency" /></Field>
        <Field label="Prijsbasis"><select className={inputCls} value={basis} onChange={e => setBasis(e.target.value as "net" | "gross")} data-testid="select-readback-basis"><option value="" disabled>— kies —</option><option value="gross">Bruto</option><option value="net">Netto</option></select></Field>
        <Field label="Btw-tarief (0–1)" error={vat ? vatErr : null}><input className={inputCls} placeholder="bv. 0.21" value={vat} onChange={e => setVat(e.target.value)} data-testid="input-readback-vat" /></Field>
      </div>
      {file && delimiter && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Kolom SKU *"><select className={inputCls} value={sku} onChange={e => setSku(e.target.value)} data-testid="select-readback-sku"><option value="">— kies —</option>{headers.map(h => <option key={h} value={h}>{h}</option>)}</select></Field>
          <Field label="Kolom werkelijke prijs *" error={sku && sku === price ? "Andere kolom kiezen" : null}><select className={inputCls} value={price} onChange={e => setPrice(e.target.value)} data-testid="select-readback-price"><option value="">— kies —</option>{headers.map(h => <option key={h} value={h}>{h}</option>)}</select></Field>
        </div>
      )}
      <Button disabled={!canPropose || !ok || !!busy} data-testid="button-upload-readback"
        onClick={() => { if (file && delimiter && decimal && basis) void run("readback", () => cmApi.readback(scope.shopId, exportId, { mapping: { sku, actual_price: price }, delimiter, decimal, currency, price_basis: basis, vat_rate: vat.trim() }, file), "Terugmelding vergeleken").then(s => { if (s) onDone(parseReadback(s).snap.id); }); }}>
        <Upload className="h-4 w-4 mr-1" />{busy ? "Vergelijken…" : "Uploaden en vergelijken"}
      </Button>
      {!canPropose && <p className="text-xs text-muted-foreground">Vereist recht pricing.propose.</p>}
      {lastError && <ErrorBox error={lastError.error} />}
    </div>
  );
}

export function ReadbackDetail({ snap, data }: { snap: Snapshot; data: ReadbackData }) {
  const [open, setOpen] = useState<Bucket | null>(null);
  const b = readbackBuckets(data);
  const bySku = new Map(data.rows.map(r => [r.sku, r]));
  const received = new Map<string, string | null>();
  data.received_rows.forEach(r => received.set(r.sku, r.actual_price));
  const rowsFor = (k: Bucket): ReadbackCompare[] => k === "mismatch" ? b.mismatchRows
    : b[k].map(sku => bySku.get(sku) ?? { sku, target_price: "", actual_price: received.get(sku) ?? null, matched: false });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <StatusBadge status={snap.status} />
        <span className="text-xs text-muted-foreground">export #{data.export_id} · {fmtDate(snap.created_at)} · {snap.created_by}</span>
        <span className={`text-xs ${data.processed ? "text-emerald-700" : "text-amber-700"}`} data-testid="text-readback-processed">{data.processed ? "Verwerking bewezen" : "Niet bewezen: gedeeltelijk of afwijkend"}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {BUCKETS.map(x => (
          <button key={x.key} type="button" onClick={() => setOpen(open === x.key ? null : x.key)} className={`rounded border p-2 text-left ${open === x.key ? "ring-2 ring-ring" : ""}`} data-testid={`button-bucket-${x.key}`}>
            <div className="text-[11px] text-muted-foreground">{x.label}</div>
            <div className={`text-lg font-semibold tabular-nums ${x.tone}`}>{b[x.key].length}</div>
          </button>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">{data.matched_count} van {data.rows.length} exportregels overeenkomend · {data.received_rows.length} regels ontvangen · vingerafdruk {data.fingerprint.slice(0, 12)}…</p>
      {open && <RowsTable testid={`table-bucket-${open}`} rows={rowsFor(open)} columns={[
        { label: "SKU", cell: r => r.sku, mono: true }, { label: "Verwacht", cell: r => r.target_price || "—", mono: true },
        { label: "Werkelijk", cell: r => r.actual_price ?? "—", mono: true },
        { label: "Status", cell: r => r.matched ? "overeenkomend" : "niet overeenkomend" },
      ]} />}
    </div>
  );
}
