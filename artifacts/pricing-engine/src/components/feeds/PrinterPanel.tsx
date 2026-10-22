import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, Pause, Play, Power, Save, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCmAction } from "@/hooks/use-channelmanager";
import type { CmScope } from "@/hooks/use-channelmanager";
import { ErrorBox, Field, inputCls } from "@/components/channelmanager/common";
import { fmtDate } from "@/lib/channelmanager/api";
import { CALC_STATE_NL, DEFAULT_RULES, KIND_NL, PRINTER_LABELS, STATUS_NL, feedApi, feedKeys, printerApi } from "@/lib/feeds/api";
import type { PriceRow, PrinterLabel, PrinterSnap, PrinterConfig, ConditionalRule } from "@/lib/feeds/api";
import { PriceCsvMapper } from "./PriceCsvMapper";

type ExportField = "sku" | "shop_id" | "label" | "target_price";
const EXPORT_FIELDS: ExportField[] = ["sku", "shop_id", "label", "target_price"];
const DEFAULT_COLS: [string, ExportField][] = [["Productcode", "sku"], ["Shop", "shop_id"], ["Prijs", "target_price"]];

function Step({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-card" data-testid={`step-printer-${n}`}>
      <header className="flex items-center gap-3 border-b px-4 py-2.5">
        <span className={`flex h-6 w-6 items-center justify-center rounded-full font-mono text-[11px] ${done ? "bg-emerald-600 text-white" : "bg-muted text-muted-foreground"}`}>{n}</span>
        <h3 className="text-sm font-semibold">{title}</h3>
      </header>
      <div className="space-y-3 p-4 text-sm">{children}</div>
    </section>
  );
}
function SnapLine({ snap, id }: { snap: PrinterSnap | null; id: string }) {
  return <div className="text-xs text-muted-foreground" data-testid={`text-printer-${id}`}>{snap
    ? <>Laatste: <span className="font-mono">#{snap.id}</span> · {STATUS_NL[snap.status]} · {fmtDate(snap.created_at)}{snap.created_by ? ` · ${snap.created_by}` : ""}</>
    : "Nog niets vastgelegd."}</div>;
}

export function PrinterPanel({ scope, shops, canPropose, canApprove }: { scope: CmScope; shops: { id: number; name: string }[]; canPropose: boolean; canApprove: boolean }) {
  const sid = scope.shopId;
  const q = useQuery({ queryKey: feedKeys.printer(scope.userKey, sid), queryFn: ({ signal }) => printerApi.state(sid, signal), retry: 1 });
  if (q.isLoading) return <div className="space-y-3"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>;
  if (q.isError || !q.data) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  // Remount the form whenever a new config revision is saved so it re-initialises from the server.
  return <PrinterWorkflow key={q.data.config?.id ?? 0} scope={scope} shops={shops} canPropose={canPropose} canApprove={canApprove} st={q.data} />;
}

function PrinterWorkflow({ scope, shops, canPropose, canApprove, st }: {
  scope: CmScope; shops: { id: number; name: string }[]; canPropose: boolean; canApprove: boolean; st: NonNullable<Awaited<ReturnType<typeof printerApi.state>>>;
}) {
  const sid = scope.shopId;
  const fq = useQuery({ queryKey: feedKeys.profiles(scope.userKey, sid), queryFn: ({ signal }) => feedApi.profiles(sid, signal), retry: 1 });
  const { run, busy, lastError } = useCmAction(scope);
  const saved = st.config?.data.config ?? null;

  const [sm, setSm] = useState<Record<PrinterLabel, string>>(() => Object.fromEntries(PRINTER_LABELS.map(l => [l, saved?.shops[l] ? String(saved.shops[l]) : ""])) as Record<PrinterLabel, string>);
  const [idTransform, setIdTransform] = useState<"exact" | "nl_six_digits">(saved?.id_transform ?? "exact");
  const [tConfirmed, setTConfirmed] = useState(!!saved?.transformation_confirmed);
  const [mapConfirmed, setMapConfirmed] = useState(!!saved?.mapping_confirmed);
  const [currency, setCurrency] = useState(saved?.currency ?? "EUR");
  const [basis, setBasis] = useState<"net" | "gross">(saved?.price_basis ?? "gross");
  const [vatRate, setVatRate] = useState(saved?.vat_rate ?? "");
  const [cols, setCols] = useState<[string, ExportField][]>(saved?.export_columns ? Object.entries(saved.export_columns) : DEFAULT_COLS);
  const [rules, setRules] = useState<Record<string, ConditionalRule>>(() => ({ ...DEFAULT_RULES, ...(saved?.rules ?? {}) }));
  const [notes, setNotes] = useState("");
  const [confirmActivate, setConfirmActivate] = useState(false);
  const [preRows, setPreRows] = useState<PriceRow[] | null>(null);
  const [rbRows, setRbRows] = useState<PriceRow[] | null>(null);
  const [adviceProfile, setAdviceProfile] = useState<number | "">("");
  const [semantics, setSemantics] = useState(false);
  const [ack, setAck] = useState(false);

  const active = !!saved?.active;
  const savedShops = useMemo(() => (saved?.shops ?? {}) as Partial<Record<PrinterLabel, number>>, [saved]);
  const adviceProfiles = (fq.data ?? []).filter(p => p.purpose === "advice" && p.active && p.current_version_id !== null);
  const ap = adviceProfiles.find(p => p.id === adviceProfile);
  const calc = st.calculation;
  const calcRows = calc?.data.rows ?? []; const warnings = calc?.data.warnings ?? []; const blocks = calc?.data.blocks ?? [];
  const approvalFresh = !!st.approval && st.approval.data.calculation_id === calc?.id;
  const exp = st.export; const rb = st.readback;
  const rbForExport = !!rb && rb.data.export_id === exp?.id;

  const ids = Object.values(sm).filter(Boolean);
  const shopErr = !sm["123inkt"] ? "123inkt is verplicht" : new Set(ids).size !== ids.length ? "Elke winkel mag maar één keer gekoppeld zijn" : null;
  const vatErr = !/^\d+(\.\d+)?$/.test(vatRate) || Number(vatRate) > 1 ? "Fractie tussen 0 en 1, bv. 0.21" : null;
  const curErr = /^[A-Z]{3}$/.test(currency) ? null : "Drie hoofdletters, bv. EUR";
  const colFields = cols.map(c => c[1]);
  const colErr = !(["sku", "shop_id", "target_price"] as ExportField[]).every(f => colFields.includes(f)) ? "Plaktabel vereist sku, shop_id en target_price"
    : cols.some(([h]) => !h.trim() || h.length > 100) ? "Elke kolom heeft een kop nodig" : cols.length > 10 ? "Maximaal 10 kolommen" : null;
  const notesErr = notes.trim() ? null : "Notitie is verplicht voor elke actie (audit)";
  const ruleErr = Object.entries(rules).filter(([l]) => sm[l as PrinterLabel]).some(([, r]) =>
    [r.threshold, r.lower_offset, r.upper_offset, r.multiplier, r.lower_tail, r.upper_tail].some(v => v !== undefined && !/^\d*\.?\d+$/.test(v))) ? "Regelparameters: niet-negatieve decimalen met punt" : null;
  const formErr = ruleErr || shopErr || vatErr || curErr || colErr || (idTransform !== "exact" && !tConfirmed ? "Bevestig de ID-transformatie" : null);

  function buildConfig(activeFlag: boolean): PrinterConfig {
    return {
      active: activeFlag, mapping_confirmed: mapConfirmed, currency, price_basis: basis, vat_rate: vatRate,
      shops: Object.fromEntries(Object.entries(sm).filter(([, v]) => v).map(([k, v]) => [k, Number(v)])),
      id_transform: idTransform, transformation_confirmed: idTransform !== "exact" && tConfirmed,
      export_columns: Object.fromEntries(cols.map(([h, f]) => [h.trim(), f])),
      rules: Object.fromEntries(Object.entries(rules).filter(([l]) => sm[l as PrinterLabel])),
    };
  }
  const saveConfig = (activeFlag: boolean, msg: string) =>
    void run("config", () => printerApi.saveConfig(sid, { expected_revision: st.config?.revision ?? 0, notes: notes.trim(), config: buildConfig(activeFlag) }), msg);
  const sortKeys = (v: unknown): unknown => Array.isArray(v) ? v.map(sortKeys) : v && typeof v === "object"
    ? Object.fromEntries(Object.entries(v as Record<string, unknown>).sort(([x], [y]) => x.localeCompare(y)).map(([k, x]) => [k, sortKeys(x)])) : v;
  const configDirty = !saved || JSON.stringify(sortKeys(buildConfig(active))) !== JSON.stringify(sortKeys({ ...saved, rules: Object.fromEntries(Object.entries({ ...DEFAULT_RULES, ...(saved.rules ?? {}) }).filter(([l]) => saved.shops[l])) }));

  return (
    <div className="space-y-4" data-testid="panel-printer">
      <div className="flex flex-wrap gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
        <span>Printerregels volgens het werkboek. DRS-plakcompatibiliteit: <strong data-testid="text-drs-compat">onbevestigd</strong>. Live schrijven naar DRS: <strong data-testid="text-live-write">{st.live_write ? "aan" : "uit"}</strong>. Downloaden betekent alleen: bestand aangemaakt.</span>
      </div>
      <Field label="Notitie bij volgende actie (verplicht, audit)" error={notesErr}><input className={inputCls} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Waarom deze stap" data-testid="input-printer-notes" /></Field>

      <Step n={1} title="Winkelmapping, profiel en activering" done={active}>
        <div className="flex flex-wrap items-center gap-2">
          <SnapLine snap={st.config} id="config" />
          <span data-testid="status-printer-active" className={`rounded border px-1.5 py-0.5 text-[11px] font-medium ${active ? "border-emerald-600/30 bg-emerald-500/10 text-emerald-700" : "border-border bg-muted text-muted-foreground"}`}>{active ? "Profiel actief" : "Profiel inactief"}</span>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {PRINTER_LABELS.map(l => (
            <Field key={l} label={l} hint={l === "123inkt" ? "Verplicht (basis)" : "Optioneel"}>
              <select className={inputCls} value={sm[l]} disabled={!canPropose} onChange={e => setSm({ ...sm, [l]: e.target.value })} data-testid={`select-printer-shop-${l}`}>
                <option value="">Niet gekoppeld</option>
                {shops.map(x => <option key={x.id} value={x.id}>{x.name} (#{x.id})</option>)}
              </select>
            </Field>
          ))}
        </div>
        {shopErr && <p className="text-xs text-destructive">{shopErr}</p>}
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="Valuta" error={curErr}><input className={inputCls} value={currency} disabled={!canPropose} onChange={e => setCurrency(e.target.value.toUpperCase())} data-testid="input-printer-currency" /></Field>
          <Field label="Prijsbasis"><select className={inputCls} value={basis} disabled={!canPropose} onChange={e => setBasis(e.target.value as "net" | "gross")} data-testid="select-printer-basis"><option value="gross">Bruto (incl. btw)</option><option value="net">Netto (excl. btw)</option></select></Field>
          <Field label="Btw als fractie" error={vatErr}><input className={inputCls} value={vatRate} disabled={!canPropose} onChange={e => setVatRate(e.target.value)} placeholder="0.21" data-testid="input-printer-vat" /></Field>
          <Field label="Product-ID-transformatie">
            <select className={inputCls} value={idTransform} disabled={!canPropose} onChange={e => setIdTransform(e.target.value as "exact" | "nl_six_digits")} data-testid="select-printer-id-transform">
              <option value="exact">Exact (geen transformatie)</option><option value="nl_six_digits">nl + zes cijfers (werkboekprofiel)</option>
            </select></Field>
        </div>
        <div className="flex flex-wrap gap-4 text-xs">
          {idTransform === "nl_six_digits" && <label className="flex items-center gap-2"><input type="checkbox" checked={tConfirmed} onChange={e => setTConfirmed(e.target.checked)} data-testid="check-transform-confirmed" />ID-transformatie bevestigd</label>}
          <label className="flex items-center gap-2"><input type="checkbox" checked={mapConfirmed} onChange={e => setMapConfirmed(e.target.checked)} data-testid="check-mapping-confirmed" />Naam-naar-shop-ID-mapping bevestigd</label>
        </div>
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Doelwinkelregels (P = goedgekeurd 123inkt-advies)</div>
          <div className="overflow-auto rounded border"><table className="w-full text-xs" data-testid="table-printer-rules">
            <thead className="bg-muted"><tr>{["Winkel", "Drempel", "Opslag < drempel", "Opslag vanaf drempel", "Factor", "Eerst afronden op heel getal", "Staart <", "Staart vanaf"].map(h => <th key={h} className="px-2 py-1 text-left font-medium">{h}</th>)}</tr></thead>
            <tbody>
              <tr className="border-t text-muted-foreground"><td className="px-2 py-1">123inkt</td><td colSpan={7} className="px-2 py-1">Altijd P (basis), alleen als de 123inkt-preprijs niet 0 is</td></tr>
              {PRINTER_LABELS.filter(l => l !== "123inkt").map(l => {
                const r = rules[l]; const on = !!sm[l];
                const set = (k: keyof ConditionalRule, v: string | boolean) => setRules({ ...rules, [l]: { ...r, [k]: v } });
                const num = (k: "threshold" | "lower_offset" | "upper_offset" | "multiplier" | "lower_tail" | "upper_tail") =>
                  <td className="px-1 py-0.5"><input className={`${inputCls} h-7 w-20`} value={r[k] ?? ""} disabled={!canPropose || !on} onChange={e => set(k, e.target.value)} data-testid={`input-rule-${l}-${k}`} /></td>;
                return (
                  <tr key={l} className={`border-t ${on ? "" : "opacity-50"}`}>
                    <td className="px-2 py-1">{l}{!on && " (niet gekoppeld)"}</td>
                    {num("threshold")}{num("lower_offset")}{num("upper_offset")}{num("multiplier")}
                    <td className="px-2"><input type="checkbox" checked={!!r.round_inner_integer} disabled={!canPropose || !on} onChange={e => set("round_inner_integer", e.target.checked)} data-testid={`check-rule-${l}-round`} /></td>
                    {num("lower_tail")}{num("upper_tail")}
                  </tr>
                );
              })}
            </tbody>
          </table></div>
          <p className="mt-1 text-[11px] text-muted-foreground">Doelprijs = HALF_UP op 2 decimalen van (P + opslag) x factor, optioneel eerst HALF_UP op heel getal, plus staart. Standaardwaarden zijn exact het werkboek. {ruleErr && <span className="text-destructive">{ruleErr}</span>}</p>
          <Button size="sm" variant="ghost" disabled={!canPropose} onClick={() => setRules({ ...DEFAULT_RULES })} data-testid="button-reset-rules">Werkboekstandaard herstellen</Button>
        </div>
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Plaktabel (kolomkop → veld)</div>
          {cols.map(([h, f], i) => (
            <div key={i} className="mb-1 flex gap-2">
              <input className={`${inputCls} flex-1`} value={h} disabled={!canPropose} onChange={e => setCols(cols.map((r, j) => j === i ? [e.target.value, r[1]] : r))} data-testid={`input-export-col-${i}`} />
              <select className={`${inputCls} flex-1`} value={f} disabled={!canPropose} onChange={e => setCols(cols.map((r, j) => j === i ? [r[0], e.target.value as ExportField] : r))} data-testid={`select-export-field-${i}`}>
                {EXPORT_FIELDS.map(x => <option key={x} value={x}>{x}</option>)}
              </select>
              <Button size="sm" variant="ghost" disabled={!canPropose} onClick={() => setCols(cols.filter((_, j) => j !== i))} data-testid={`button-remove-export-col-${i}`}>Weg</Button>
            </div>
          ))}
          <Button size="sm" variant="ghost" disabled={!canPropose || cols.length >= 10} onClick={() => setCols([...cols, ["", "label"]])} data-testid="button-add-export-col">Kolom toevoegen</Button>
          {colErr && <p className="text-xs text-destructive">{colErr}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <Button size="sm" variant="outline" disabled={!canPropose || !!formErr || !!notesErr || !!busy} onClick={() => saveConfig(false, "Config opgeslagen als concept (inactief)")} data-testid="button-save-printer-config">
            <Save className="mr-1 h-3.5 w-3.5" />Opslaan als concept (inactief)</Button>
          {active ? (
            <Button size="sm" variant="outline" disabled={!canPropose || !!notesErr || !!busy} onClick={() => saveConfig(false, "Printerprofiel gedeactiveerd")} data-testid="button-deactivate-printer">
              <Pause className="mr-1 h-3.5 w-3.5" />Deactiveren</Button>
          ) : <>
            <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={confirmActivate} onChange={e => setConfirmActivate(e.target.checked)} data-testid="check-confirm-activate" />
              Ik bevestig: deze regels gelden voor de gekoppelde winkels; andere winkelregels blijven ongewijzigd.</label>
            <Button size="sm" className="bg-emerald-700 text-white hover:bg-emerald-800" disabled={!canPropose || !!formErr || !!notesErr || !mapConfirmed || !confirmActivate || !!busy}
              onClick={() => saveConfig(true, "Printerprofiel geactiveerd")} data-testid="button-activate-printer">
              <Power className="mr-1 h-3.5 w-3.5" />Opslaan en activeren</Button>
          </>}
          {active && configDirty && <span className="text-[11px] text-amber-700">Wijzigingen opslaan maakt het profiel inactief; activeer daarna opnieuw.</span>}
        </div>
        <p className="text-[11px] text-muted-foreground">Elke opgeslagen config maakt bestaande preprijzen, adviesgoedkeuring en berekeningen ongeldig voor nieuwe export. Oude exports behouden hun herkomst.</p>
      </Step>

      <Step n={2} title="Prijzen pre wijziging" done={!!st.pre && st.pre.data.config_id === st.config?.id}>
        <SnapLine snap={st.pre} id="pre" />
        {st.pre && st.pre.data.config_id !== st.config?.id && <p className="text-xs text-amber-700">Deze pre-prijzen horen bij een eerdere config. Leg ze opnieuw vast.</p>}
        {st.pre && <p className="text-xs text-muted-foreground">{st.pre.data.rows.length} prijsrijen, {st.pre.data.duplicates} identieke duplicaten.</p>}
        {!st.config ? <p className="text-xs text-muted-foreground">Sla eerst de winkelmapping op.</p> : <>
          <PriceCsvMapper id="pre" label="Huidige shopprijzen (Prijzen pre wijziging)" shops={savedShops} onRows={setPreRows} />
          <Button size="sm" disabled={!canPropose || !preRows?.length || !!notesErr || !!busy} onClick={() => preRows && void run("pre", () => printerApi.pre(sid, { notes: notes.trim(), rows: preRows }), "Pre-prijzen vastgelegd")} data-testid="button-save-pre">
            <Upload className="mr-1 h-3.5 w-3.5" />{preRows ? `${preRows.length} pre-prijzen vastleggen` : "Pre-prijzen vastleggen"}</Button>
        </>}
        <p className="text-[11px] text-muted-foreground">Ontbrekende cellen blokkeren de berekening; prijs 0 bij een doelwinkel slaat die winkel over.</p>
      </Step>

      <Step n={3} title="PriceShape-advies goedkeuren" done={!!st.advice && st.advice.data.config_id === st.config?.id}>
        <SnapLine snap={st.advice} id="advice" />
        {st.advice && <p className="text-xs text-muted-foreground">Feed #{st.advice.data.profile_id} versie {st.advice.data.version_id} · {st.advice.data.rows.length} adviezen{st.advice.data.config_id !== st.config?.id ? " · hoort bij eerdere config, keur opnieuw goed" : ""}</p>}
        {!active ? <p className="text-xs text-muted-foreground">Activeer eerst het printerprofiel.</p>
          : fq.isError ? <ErrorBox error={fq.error} onRetry={() => fq.refetch()} />
          : !adviceProfiles.length ? <p className="text-xs text-amber-700" data-testid="status-no-advice-feed">Geen actieve advieskoppeling met huidige versie. Stel die in onder Feeds & koppelingen.</p> : (
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Actieve advieskoppeling">
              <select className={inputCls} value={adviceProfile} onChange={e => setAdviceProfile(e.target.value ? Number(e.target.value) : "")} data-testid="select-advice-profile">
                <option value="">Kies</option>{adviceProfiles.map(p => <option key={p.id} value={p.id}>{p.name} · versie {p.current_version_id}</option>)}
              </select></Field>
            <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={semantics} onChange={e => setSemantics(e.target.checked)} data-testid="check-advice-semantics" />
              Valuta ({saved?.currency}), prijsbasis ({saved?.price_basis === "net" ? "netto" : "bruto"}) en eenheid van dit advies komen overeen</label>
            <Button size="sm" disabled={!canApprove || !ap || !semantics || !!notesErr || !!busy}
              onClick={() => ap && void run("advice", () => printerApi.advice(sid, { profile_id: ap.id, version_id: ap.current_version_id as number, semantics_confirmed: true, notes: notes.trim() }), "Advies goedgekeurd als basis")} data-testid="button-approve-advice">
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />Advies goedkeuren</Button>
          </div>
        )}
      </Step>

      <Step n={4} title="Berekenen en goedkeuren" done={approvalFresh}>
        <SnapLine snap={calc} id="calculation" />
        <Button size="sm" disabled={!canPropose || !active || !st.advice || !st.pre || !!notesErr || !!busy}
          onClick={() => st.advice && void run("calc", () => printerApi.calculate(sid, { advice_snapshot_id: st.advice!.id, notes: notes.trim() }), "Berekening klaar")} data-testid="button-printer-calculate">
          <Play className="mr-1 h-3.5 w-3.5" />Berekenen met advies #{st.advice?.id ?? "—"}</Button>
        {calc && <>
          <div className="flex flex-wrap gap-3 text-xs">
            <span>{calcRows.length} rijen</span>
            <span className={blocks.length ? "text-destructive" : ""} data-testid="text-calc-blocks">{blocks.length} blokkades</span>
            <span className={warnings.length ? "text-amber-700" : ""} data-testid="text-calc-warnings">{warnings.length} wijzigingen &gt;20%</span>
            <span>{calc.data.pre_duplicates} dubbele pre · {calc.data.advice_duplicates} dubbele adviezen · {calc.data.pre_only_products.length} alleen in pre</span>
          </div>
          {blocks.length > 0 && <ul className="max-h-32 list-disc overflow-auto pl-4 text-xs text-destructive">{blocks.slice(0, 100).map((b, i) => <li key={i}>{b.sku} · shop #{b.shop_id}: {CALC_STATE_NL[b.reason]}</li>)}</ul>}
          {warnings.length > 0 && <ul className="max-h-32 list-disc overflow-auto pl-4 text-xs text-amber-700">{warnings.slice(0, 100).map((w, i) => <li key={i}>{w.sku}: wijziging groter dan 20% ten opzichte van 123inkt-preprijs</li>)}</ul>}
          <div className="max-h-80 overflow-auto rounded border"><table className="w-full text-xs" data-testid="table-printer-calc">
            <thead className="sticky top-0 bg-muted"><tr>{["Product", "Bron-ID", "Winkel", "Advies", "Pre", "Doelprijs", "Status"].map(h => <th key={h} className="px-2 py-1 text-left">{h}</th>)}</tr></thead>
            <tbody>{calcRows.slice(0, 500).map((r, i) => (
              <tr key={i} className={`border-t ${r.state === "ready" ? "" : r.state === "zero_target_pre_price_suppressed" ? "text-muted-foreground" : "bg-destructive/5"}`}>
                <td className="px-2 py-0.5 font-mono">{r.sku}</td><td className="px-2 py-0.5 font-mono">{r.source_id}</td><td className="px-2 py-0.5">{r.label} #{r.shop_id}</td>
                <td className="px-2 py-0.5 font-mono">{r.advice}</td>
                <td className="px-2 py-0.5 font-mono">{r.current_price ?? <span className="text-destructive">ontbreekt</span>}</td>
                <td className="px-2 py-0.5 font-mono">{r.target_price ?? "—"}</td><td className="px-2 py-0.5">{CALC_STATE_NL[r.state]}</td>
              </tr>))}</tbody>
          </table></div>
          {calcRows.length > 500 && <p className="text-[11px] text-muted-foreground">Eerste 500 van {calcRows.length} rijen; het werkboek bevat alles.</p>}
          <div className="flex flex-wrap items-center gap-3">
            {warnings.length > 0 && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} data-testid="check-ack-warnings" />Wijzigingen boven 20% beoordeeld</label>}
            <Button size="sm" className="bg-emerald-700 text-white hover:bg-emerald-800" disabled={!canApprove || calc.status === "blocked" || (warnings.length > 0 && !ack) || approvalFresh || !!notesErr || !!busy}
              onClick={() => void run("approve", () => printerApi.approve(sid, calc.id, { notes: notes.trim(), acknowledge_warnings: ack }), "Berekening goedgekeurd")} data-testid="button-printer-approve">
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />{approvalFresh ? `Goedgekeurd (#${st.approval?.id})` : "Berekening goedkeuren"}</Button>
          </div>
        </>}
      </Step>

      <Step n={5} title="Werkboek exporteren" done={!!exp && exp.data.calculation_id === calc?.id}>
        <SnapLine snap={exp} id="export" />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={!canApprove || !approvalFresh || !!notesErr || !!busy} onClick={() => st.approval && void run("export", () => printerApi.export(sid, st.approval!.id, { notes: notes.trim() }), "Werkboek aangemaakt")} data-testid="button-printer-export">
            <FileSpreadsheet className="mr-1 h-3.5 w-3.5" />XLSX aanmaken</Button>
          {exp && <Button size="sm" variant="outline" disabled={!canApprove || !!busy} onClick={() => void run("download", () => printerApi.download(sid, exp.id))} data-testid="button-printer-download">
            <Download className="mr-1 h-3.5 w-3.5" />{exp.data.filename}</Button>}
        </div>
        {exp && <p className="text-[11px] text-muted-foreground">Export #{exp.id} van berekening #{exp.data.calculation_id} · feedversie {exp.data.feed_version_id} · sha256 <span className="font-mono">{exp.data.sha256.slice(0, 20)}…</span> · aangemaakt, niet verwerkt tot terugleescontrole.</p>}
      </Step>

      <Step n={6} title="Terugleescontrole (prijzen na wijziging)" done={rb?.status === "confirmed" && rbForExport}>
        <SnapLine snap={rb} id="readback" />
        {rb && <div className={`space-y-1 rounded border p-2 text-xs ${rb.status === "confirmed" ? "border-emerald-600/30 bg-emerald-500/5 text-emerald-800" : "border-destructive/30 bg-destructive/5 text-destructive"}`} data-testid="status-readback">
          <div>{rb.status === "confirmed" ? "Bevestigd: alle geëxporteerde doelprijzen komen overeen. Overige producten vallen buiten deze exportcontrole." : "Niet bevestigd."} {!rbForExport && `(hoort bij export #${rb.data.export_id}, niet de laatste)`}</div>
          {rb.data.filename && <Button size="sm" variant="outline" className="h-7" disabled={!canApprove || !!busy} onClick={() => void run("rbdl", () => printerApi.downloadReadback(sid, rb.id))} data-testid="button-download-readback">
            <Download className="mr-1 h-3 w-3" />Gecontroleerd werkboek: {rb.data.filename}</Button>}
          <div>{rb.data.checks.filter(c => c.state === "matched").length} overeenkomend · {rb.data.checks.filter(c => c.state === "mismatch").length} afwijkend · {rb.data.checks.filter(c => c.state === "missing").length} ontbrekend · {rb.data.extra_rows.length} buiten exportscope · {rb.data.duplicates} duplicaten</div>
          {rb.data.checks.some(c => c.state !== "matched") && (
            <div className="max-h-40 overflow-auto rounded border bg-background text-foreground"><table className="w-full font-mono text-[11px]">
              <thead className="sticky top-0 bg-muted"><tr><th className="px-2 text-left">sku</th><th className="px-2 text-left">shop</th><th className="px-2 text-right">verwacht</th><th className="px-2 text-right">werkelijk</th><th className="px-2 text-right">verschil</th><th className="px-2 text-left">status</th></tr></thead>
              <tbody>{rb.data.checks.filter(c => c.state !== "matched").slice(0, 200).map((c, i) => <tr key={i} className="border-t"><td className="px-2">{c.sku}</td><td className="px-2">{c.shop_id}</td><td className="px-2 text-right">{c.expected}</td><td className="px-2 text-right">{c.actual ?? "ontbreekt"}</td><td className="px-2 text-right">{c.difference ?? "—"}</td><td className="px-2">{c.state === "missing" ? "ontbreekt" : "afwijkend"}</td></tr>)}</tbody>
            </table></div>
          )}
        </div>}
        {!exp ? <p className="text-xs text-muted-foreground">Nog geen export om tegen te controleren.</p> : <>
          <PriceCsvMapper id="readback" label="Werkelijke prijzen na verwerking (Prijzen na wijziging)" shops={savedShops} onRows={setRbRows} />
          <Button size="sm" disabled={!canApprove || !rbRows?.length || !!notesErr || !!busy} onClick={() => rbRows && void run("readback", () => printerApi.readback(sid, exp.id, { notes: notes.trim(), rows: rbRows }), "Terugleescontrole vastgelegd")} data-testid="button-printer-readback">
            <Upload className="mr-1 h-3.5 w-3.5" />Controleren tegen export #{exp.id}</Button>
        </>}
      </Step>

      {lastError && <ErrorBox error={lastError.error} />}

      <History scope={scope} first={st} />
    </div>
  );
}

function HistoryRows({ items }: { items: PrinterSnap[] }) {
  return <>{items.map(h => (
    <tr key={h.id} className="border-t" data-testid={`row-printer-history-${h.id}`}><td className="px-3 py-1 font-mono">#{h.id}</td><td className="px-3 py-1">{KIND_NL[h.kind]}</td>
      <td className="px-3 py-1">{STATUS_NL[h.status]}</td><td className="px-3 py-1">{fmtDate(h.created_at)}</td><td className="px-3 py-1 text-muted-foreground">{h.created_by ?? ""}</td>
      <td className="px-3 py-1 text-muted-foreground">{h.data.notes}</td></tr>
  ))}</>;
}
function HistoryPage({ scope, before, isLast, onMore }: { scope: CmScope; before: number; isLast: boolean; onMore: (n: number) => void }) {
  const q = useQuery({ queryKey: feedKeys.printerHistory(scope.userKey, scope.shopId, before), queryFn: ({ signal }) => printerApi.state(scope.shopId, signal, before), retry: 1 });
  if (q.isLoading) return <tr><td colSpan={6} className="px-3 py-2"><Skeleton className="h-6" /></td></tr>;
  if (q.isError || !q.data) return <tr><td colSpan={6} className="px-3 py-2"><ErrorBox error={q.error} onRetry={() => q.refetch()} /></td></tr>;
  const d = q.data;
  return <><HistoryRows items={d.history} />{isLast && d.has_more && d.next_before_id && <tr><td colSpan={6} className="px-3 py-2"><Button size="sm" variant="ghost" onClick={() => onMore(d.next_before_id as number)} data-testid="button-history-more">Ouder laden</Button></td></tr>}</>;
}
function History({ scope, first }: { scope: CmScope; first: { history: PrinterSnap[]; has_more: boolean; next_before_id: number | null } }) {
  const [pages, setPages] = useState<number[]>([]);
  return (
    <section className="rounded-lg border bg-card">
      <header className="border-b px-4 py-2.5 text-sm font-semibold">Geschiedenis</header>
      <div className="max-h-96 overflow-auto"><table className="w-full text-xs" data-testid="table-printer-history"><tbody>
        <HistoryRows items={first.history} />
        {!first.history.length && <tr><td className="px-3 py-3 text-muted-foreground">Nog geen geschiedenis.</td></tr>}
        {pages.map((b, i) => <HistoryPage key={b} scope={scope} before={b} isLast={i === pages.length - 1} onMore={n => setPages(p => [...p, n])} />)}
        {!pages.length && first.has_more && first.next_before_id && <tr><td colSpan={6} className="px-3 py-2"><Button size="sm" variant="ghost" onClick={() => setPages([first.next_before_id as number])} data-testid="button-history-more">Ouder laden</Button></td></tr>}
      </tbody></table></div>
    </section>
  );
}
