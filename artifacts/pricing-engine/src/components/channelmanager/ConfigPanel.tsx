import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cmApi, decError, dash } from "@/lib/channelmanager/api";
import type { ChannelConfig } from "@/lib/channelmanager/api";
import { parseConfig } from "@/lib/channelmanager/model";
import type { Overview, Snapshot } from "@/lib/channelmanager/model";
import type { ChannelRule } from "@workspace/api-client-react";
import { DECIMALS, DELIMITERS } from "@/lib/channelmanager/csv";
import { useCmAction } from "@/hooks/use-channelmanager";
import type { CmScope } from "@/hooks/use-channelmanager";
import { ErrorBox, Fact, Facts, Field, HistoryList, RecordLoader, Section, StatusBadge, inputCls } from "./common";

type Rule = ChannelRule;
type RuleKind = Rule["kind"];
type Rounding = NonNullable<ChannelConfig["rounding"]>;
type Canonical = "sku" | "name" | "category" | "target_price";
type Delim = NonNullable<ChannelConfig["delimiter"]>;
type Dec = NonNullable<ChannelConfig["decimal"]>;

export function configOf(s: Snapshot | null): ChannelConfig | null {
  return s ? parseConfig(s).data.config : null;
}

interface OverrideRow { key: string; kind: RuleKind; value: string }
interface Form {
  currency: string; price_basis: "net" | "gross" | ""; vat_rate: string; kind: RuleKind; value: string;
  cat: OverrideRow[]; sku: OverrideRow[]; precision: string; increment: string; rounding: Rounding;
  min_price: string; min_margin: string; max_abs: string; max_pct: string; tolerance: string;
  columns: { header: string; field: Canonical }[]; delimiter: Delim | ""; decimal: Dec | ""; schedule: boolean; hour: string; source: string;
}
/** Geen configuratie: alles leeg; gebruiker moet elke waarde expliciet kiezen. */
const empty: Form = {
  currency: "", price_basis: "", vat_rate: "", kind: "fixed", value: "", cat: [], sku: [], precision: "2", increment: "0.01",
  rounding: "HALF_UP", min_price: "", min_margin: "", max_abs: "", max_pct: "", tolerance: "0",
  columns: [], delimiter: "", decimal: "", schedule: false, hour: "2", source: "",
};
const toRows = (o?: Record<string, Rule>) => Object.entries(o ?? {}).map(([key, r]) => ({ key, kind: r.kind, value: r.value }));
function toForm(c: ChannelConfig | null): Form {
  if (!c) return empty;
  return {
    currency: c.currency ?? "", price_basis: c.price_basis ?? "gross", vat_rate: c.vat_rate ?? "", kind: c.rule.kind, value: c.rule.value,
    cat: toRows(c.category_overrides), sku: toRows(c.sku_overrides), precision: String(c.precision ?? 2), increment: c.increment ?? "0.01",
    rounding: c.rounding ?? "HALF_UP", min_price: c.min_price ?? "", min_margin: c.min_margin ?? "", max_abs: c.max_change_absolute ?? "",
    max_pct: c.max_change_percent ?? "", tolerance: c.readback_tolerance ?? "0",
    columns: Object.entries(c.export_columns ?? {}).map(([header, field]) => ({ header, field })),
    delimiter: c.delimiter ?? "", decimal: c.decimal ?? "", schedule: !!c.schedule_enabled,
    hour: String(c.schedule_hour_utc ?? 2), source: c.schedule_source_shop_id ? String(c.schedule_source_shop_id) : "",
  };
}
const opt = (v: string) => (v.trim() ? v.trim() : null);

export function ConfigPanel({ scope, overview, canPropose, shops }: { scope: CmScope; overview: Overview; canPropose: boolean; shops: { id: number; name: string }[] }) {
  const current: Snapshot | null = overview.config;
  const revision = current?.revision ?? 0;
  const [f, setF] = useState<Form>(() => toForm(configOf(current)));
  const [notes, setNotes] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [view, setView] = useState<number | null>(null);
  const initFor = useRef<string | null>(null);
  const { run, busy, lastError } = useCmAction(scope);
  useEffect(() => {
    const k = `${scope.scopeToken}:${current?.id ?? "none"}`;
    if (initFor.current !== k) { initFor.current = k; setF(toForm(configOf(current))); setConfirmed(false); }
  }, [scope.scopeToken, current]);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => { setConfirmed(false); setF(p => ({ ...p, [k]: v })); };

  const errors = useMemo(() => {
    const e: Record<string, string | null> = {
      currency: /^[A-Z]{3}$/.test(f.currency) ? null : "Drie hoofdletters, bv. EUR",
      vat_rate: decError(f.vat_rate, { required: true, max: 1 }),
      price_basis: f.price_basis ? null : "Kies bruto of netto",
      value: decError(f.value, { required: true, signed: true }),
      precision: /^[0-4]$/.test(f.precision) ? null : "0 t/m 4",
      increment: decError(f.increment, { required: true }) ?? (Number(f.increment) > 0 ? null : "Moet groter dan 0 zijn"),
      min_price: decError(f.min_price), min_margin: decError(f.min_margin, { maxExclusive: 1 }),
      max_abs: decError(f.max_abs), max_pct: decError(f.max_pct), tolerance: decError(f.tolerance),
    };
    f.cat.forEach((r, i) => { e[`cat${i}`] = !r.key.trim() ? "Categorie verplicht" : decError(r.value, { required: true, signed: true }); });
    f.sku.forEach((r, i) => { e[`sku${i}`] = !r.key.trim() ? "SKU verplicht" : decError(r.value, { required: true, signed: true }); });
    const dupe = (rows: { key: string }[]) => new Set(rows.map(r => r.key.trim())).size !== rows.length;
    if (dupe(f.cat)) e.catdupe = "Dubbele categorie"; if (dupe(f.sku)) e.skudupe = "Dubbele SKU";
    f.columns.forEach((c, i) => { e[`col${i}`] = c.header.trim() ? null : "Kolomkop verplicht"; });
    e.hour = /^\d{1,2}$/.test(f.hour) && Number(f.hour) <= 23 ? null : "0 t/m 23";
    if (f.columns.length < 2 || !f.columns.some(c => c.field === "sku")) e.cols = "Exportprofiel vereist minimaal 2 kolommen waaronder SKU";
    if (!f.columns.some(c => c.field === "target_price")) e.cols2 = "Exportprofiel vereist een doelprijs-kolom";
    f.columns.forEach((c, i) => { if (!e[`col${i}`] && (c.header.length > 100 || /^\s*[=+\-@]/.test(c.header))) e[`col${i}`] = "Max 100 tekens, niet beginnen met = + - @"; });
    if (new Set(f.columns.map(c => c.header.trim())).size !== f.columns.length) e.coldupe = "Dubbele kolomkop";
    if (!f.delimiter) e.delim = "Kies een scheidingsteken";
    if (!f.decimal) e.decim = "Kies een decimaalteken";
    if (f.delimiter && f.delimiter === f.decimal) e.sep = "Scheidingsteken en decimaalteken moeten verschillen";
    return e;
  }, [f]);
  const invalid = Object.values(errors).some(Boolean);

  const save = () => {
    const ov = (rows: OverrideRow[]) => Object.fromEntries(rows.map(r => [r.key.trim(), { kind: r.kind, value: r.value.trim() }]));
    if (!f.price_basis || !f.delimiter || !f.decimal) return;
    const config: ChannelConfig = {
      currency: f.currency, price_basis: f.price_basis, vat_rate: f.vat_rate.trim(), rule: { kind: f.kind, value: f.value.trim() },
      category_overrides: ov(f.cat), sku_overrides: ov(f.sku), precision: Number(f.precision), increment: f.increment.trim(), rounding: f.rounding,
      min_price: opt(f.min_price), min_margin: opt(f.min_margin), max_change_absolute: opt(f.max_abs), max_change_percent: opt(f.max_pct),
      readback_tolerance: f.tolerance.trim() || "0",
      export_columns: Object.fromEntries(f.columns.map(c => [c.header.trim(), c.field])),
      delimiter: f.delimiter, decimal: f.decimal, schedule_enabled: f.schedule,
      schedule_hour_utc: Number(f.hour), schedule_source_shop_id: f.source ? Number(f.source) : null,
    };
    void run("config", () => cmApi.saveConfig(scope.shopId, { expected_revision: revision, notes, config }), "Configuratie opgeslagen als nieuwe revisie").then(r => { if (r) { setNotes(""); setConfirmed(false); } });
  };

  const dis = !canPropose;
  const sel = (v: string, on: (v: string) => void, opts: { value: string; label: string }[], id: string) => (
    <select className={inputCls} value={v} onChange={e => on(e.target.value)} disabled={dis} data-testid={id}>{v === "" && <option value="" disabled>— kies —</option>}{opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
  );
  const ruleRows = (k: "cat" | "sku", label: string) => (
    <div className="space-y-2">
      {f[k].map((r, i) => (
        <div key={i} className="flex flex-wrap items-start gap-2">
          <input className={`${inputCls} w-48`} placeholder={label} value={r.key} disabled={dis} onChange={e => set(k, f[k].map((x, j) => j === i ? { ...x, key: e.target.value } : x))} data-testid={`input-${k}-key-${i}`} />
          {sel(r.kind, v => set(k, f[k].map((x, j) => j === i ? { ...x, kind: v as RuleKind } : x)), [{ value: "fixed", label: "Vast bedrag" }, { value: "percentage", label: "Percentage" }], `select-${k}-kind-${i}`)}
          <input className={`${inputCls} w-28`} placeholder="+0.00" value={r.value} disabled={dis} onChange={e => set(k, f[k].map((x, j) => j === i ? { ...x, value: e.target.value } : x))} data-testid={`input-${k}-value-${i}`} />
          <Button size="icon" variant="ghost" disabled={dis} onClick={() => set(k, f[k].filter((_, j) => j !== i))} aria-label="Verwijderen" data-testid={`button-remove-${k}-${i}`}><Trash2 className="h-4 w-4" /></Button>
          {errors[`${k}${i}`] && <span className="text-xs text-destructive self-center">{errors[`${k}${i}`]}</span>}
        </div>
      ))}
      {errors[`${k}dupe`] && <p className="text-xs text-destructive">{errors[`${k}dupe`]}</p>}
      <Button size="sm" variant="outline" disabled={dis} onClick={() => set(k, [...f[k], { key: "", kind: "fixed", value: "" }])} data-testid={`button-add-${k}`}><Plus className="h-3.5 w-3.5 mr-1" />{label}-uitzondering</Button>
    </div>
  );

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        {!current && <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm flex gap-2" data-testid="status-no-config"><AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5" />Deze winkel heeft nog geen configuratie. Sla een eerste revisie op voordat er gerekend kan worden.</div>}
        <Section title="Prijsbasis en valuta">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Valuta" error={errors.currency}><input className={inputCls} value={f.currency} placeholder="EUR" disabled={dis} onChange={e => set("currency", e.target.value.toUpperCase())} maxLength={3} data-testid="input-currency" /></Field>
            <Field label="Prijsbasis" error={errors.price_basis}>{sel(f.price_basis, v => set("price_basis", v as "net" | "gross"), [{ value: "gross", label: "Bruto (incl. btw)" }, { value: "net", label: "Netto (excl. btw)" }], "select-price-basis")}</Field>
            <Field label="Btw-tarief (fractie 0–1)" error={errors.vat_rate} hint="Expliciet invullen; 0 is toegestaan"><input className={inputCls} value={f.vat_rate} placeholder="bv. 0.21" disabled={dis} onChange={e => set("vat_rate", e.target.value)} data-testid="input-vat" /></Field>
          </div>
        </Section>
        <Section title="Prijsregel (shopniveau)">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Soort">{sel(f.kind, v => set("kind", v as RuleKind), [{ value: "fixed", label: "Vast bedrag" }, { value: "percentage", label: "Percentage" }], "select-rule-kind")}</Field>
            <Field label={f.kind === "fixed" ? "Delta (bedrag)" : "Delta (%)"} error={errors.value} hint="Teken + of − toegestaan"><input className={inputCls} value={f.value} disabled={dis} onChange={e => set("value", e.target.value)} placeholder="+1.50" data-testid="input-rule-value" /></Field>
          </div>
          <p className="text-xs text-muted-foreground">Uitzonderingen vervangen alleen de regel. Voorrang: SKU &gt; exacte categorie &gt; shop.</p>
          <div className="grid md:grid-cols-2 gap-4">
            <div><h4 className="text-xs font-semibold mb-2">Categorie-uitzonderingen</h4>{ruleRows("cat", "Categorie")}</div>
            <div><h4 className="text-xs font-semibold mb-2">SKU-uitzonderingen</h4>{ruleRows("sku", "SKU")}</div>
          </div>
        </Section>
        <Section title="Afronding en grenzen">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Precisie (decimalen)" error={errors.precision}><input className={inputCls} value={f.precision} disabled={dis} onChange={e => set("precision", e.target.value)} data-testid="input-precision" /></Field>
            <Field label="Stapgrootte" error={errors.increment}><input className={inputCls} value={f.increment} disabled={dis} onChange={e => set("increment", e.target.value)} data-testid="input-increment" /></Field>
            <Field label="Afrondmodus">{sel(f.rounding, v => set("rounding", v as Rounding), [{ value: "HALF_UP", label: "Half omhoog" }, { value: "HALF_EVEN", label: "Bankiers (half even)" }, { value: "DOWN", label: "Omlaag" }, { value: "UP", label: "Omhoog" }], "select-rounding")}</Field>
            <Field label="Minimumprijs" error={errors.min_price} hint="Optioneel; blokkeert, past niet aan"><input className={inputCls} value={f.min_price} disabled={dis} onChange={e => set("min_price", e.target.value)} data-testid="input-min-price" /></Field>
            <Field label="Minimummarge (fractie)" error={errors.min_margin} hint="Optioneel, bv. 0.15"><input className={inputCls} value={f.min_margin} disabled={dis} onChange={e => set("min_margin", e.target.value)} data-testid="input-min-margin" /></Field>
            <Field label="Max. wijziging (bedrag)" error={errors.max_abs} hint="Optioneel signaal grote delta"><input className={inputCls} value={f.max_abs} disabled={dis} onChange={e => set("max_abs", e.target.value)} data-testid="input-max-abs" /></Field>
            <Field label="Max. wijziging (%)" error={errors.max_pct} hint="Optioneel"><input className={inputCls} value={f.max_pct} disabled={dis} onChange={e => set("max_pct", e.target.value)} data-testid="input-max-pct" /></Field>
            <Field label="DRS-tolerantie" error={errors.tolerance} hint="0 = exact"><input className={inputCls} value={f.tolerance} disabled={dis} onChange={e => set("tolerance", e.target.value)} data-testid="input-tolerance" /></Field>
          </div>
        </Section>
        <Section title="Exportprofiel (CSV)">
          <p className="text-xs text-muted-foreground">Extern formaat voorlopig en niet bevestigd. Koppel elke uitvoerkolomkop expliciet aan een veld.</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Scheidingsteken" error={errors.delim ?? errors.sep}>{sel(f.delimiter, v => set("delimiter", v as Delim), DELIMITERS, "select-export-delimiter")}</Field>
            <Field label="Decimaalteken" error={errors.decim}>{sel(f.decimal, v => set("decimal", v as Dec), DECIMALS, "select-export-decimal")}</Field>
          </div>
          {f.columns.map((c, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <input className={`${inputCls} w-48`} placeholder="Kolomkop in bestand" value={c.header} disabled={dis} onChange={e => set("columns", f.columns.map((x, j) => j === i ? { ...x, header: e.target.value } : x))} data-testid={`input-col-header-${i}`} />
              {sel(c.field, v => set("columns", f.columns.map((x, j) => j === i ? { ...x, field: v as Canonical } : x)), [{ value: "sku", label: "SKU" }, { value: "name", label: "Naam" }, { value: "category", label: "Categorie" }, { value: "target_price", label: "Doelprijs" }], `select-col-field-${i}`)}
              <Button size="icon" variant="ghost" disabled={dis} onClick={() => set("columns", f.columns.filter((_, j) => j !== i))} aria-label="Verwijderen" data-testid={`button-remove-col-${i}`}><Trash2 className="h-4 w-4" /></Button>
              {errors[`col${i}`] && <span className="text-xs text-destructive">{errors[`col${i}`]}</span>}
            </div>
          ))}
          {[errors.cols, errors.cols2, errors.coldupe].filter(Boolean).map(m => <p key={m} className="text-xs text-destructive">{m}</p>)}
          <Button size="sm" variant="outline" disabled={dis} onClick={() => set("columns", [...f.columns, { header: "", field: "sku" }])} data-testid="button-add-col"><Plus className="h-3.5 w-3.5 mr-1" />Kolom</Button>
          {f.columns.length > 0 && (
            <div className="rounded border bg-muted/40 p-2 font-mono text-xs overflow-x-auto" data-testid="text-export-preview">{f.columns.map(c => c.header || "?").join(f.delimiter === "\t" ? " ⇥ " : f.delimiter)}</div>
          )}
        </Section>
        <Section title="Dagelijkse preview-planner">
          <label className="flex items-center gap-3 text-sm">
            <Switch checked={f.schedule} disabled={dis} onCheckedChange={v => set("schedule", v)} data-testid="switch-schedule" />
            Dagelijks (UTC) een preview-berekening klaarzetten op de laatste goedgekeurde basis
          </label>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Uur (UTC)" error={errors.hour}><input className={inputCls} value={f.hour} disabled={dis} onChange={e => set("hour", e.target.value)} data-testid="input-schedule-hour" /></Field>
            <Field label="Bronwinkel basis" hint="Leeg = deze winkel">
              <select className={inputCls} value={f.source} disabled={dis} onChange={e => set("source", e.target.value)} data-testid="select-schedule-source">
                <option value="">Deze winkel</option>{shops.filter(s => s.id !== scope.shopId).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
          </div>
          <p className="text-xs text-muted-foreground">Nooit automatische goedkeuring of export. Staat standaard uit. Draait met de rechten van wie de configuratie het laatst opsloeg.</p>
        </Section>
        <Section title="Opslaan als nieuwe revisie">
          <label className="flex items-start gap-2 text-sm">
            <Checkbox checked={confirmed} disabled={dis || invalid} onCheckedChange={v => setConfirmed(v === true)} data-testid="checkbox-confirm-config" className="mt-0.5" />
            <span>Ik bevestig dat alle waarden hierboven bewust zijn gekozen (ook btw, valuta, prijsbasis en exportprofiel). Externe formaten blijven voorlopig en onbevestigd.</span>
          </label>
          <Textarea placeholder="Toelichting bij deze wijziging" maxLength={2000} value={notes} disabled={dis} onChange={e => setNotes(e.target.value)} data-testid="input-config-notes" />
          <div className="flex items-center gap-3">
            <Button disabled={dis || invalid || !confirmed || !!busy || !notes.trim()} onClick={save} data-testid="button-save-config">{busy ? "Opslaan…" : `Opslaan (op revisie ${revision})`}</Button>
            {!canPropose && <span className="text-xs text-muted-foreground">Vereist recht pricing.propose.</span>}
            {canPropose && invalid && <span className="text-xs text-destructive">Herstel de gemarkeerde velden.</span>}
          </div>
          {lastError && <ErrorBox error={lastError.error} />}
          <p className="text-xs text-muted-foreground">Bij een conflict (iemand anders sloeg intussen op) volgt een melding; herlaad dan de laatste revisie.</p>
        </Section>
      </div>
      <div className="space-y-4">
        <HistoryList scope={scope} kind="config" title="Revisiehistorie" selectedId={view} onSelect={s => setView(s.id)} />
        {view !== null && (
          <Section title="Revisie-inspectie">
            <RecordLoader scope={scope} id={view} parse={parseConfig} onClose={() => setView(null)}>
              {({ snap, data }) => {
                const c = data.config;
                return (<div className="space-y-2">
                  <div className="flex items-center gap-2 text-xs"><StatusBadge status={snap.status} /><span>r{snap.revision} · {snap.created_by}</span></div>
                  <p className="text-xs">{data.notes}</p>
                  <Facts>
                    <Fact label="Regel">{c.rule.kind === "fixed" ? "Vast" : "%"} {c.rule.value}</Fact>
                    <Fact label="Valuta / basis">{c.currency} · {c.price_basis}</Fact>
                    <Fact label="Btw">{c.vat_rate}</Fact>
                    <Fact label="Afronding">{dash(c.precision)} / {dash(c.increment)} / {dash(c.rounding)}</Fact>
                    <Fact label="Min. prijs / marge">{dash(c.min_price)} / {dash(c.min_margin)}</Fact>
                    <Fact label="Max. wijziging">{dash(c.max_change_absolute)} / {dash(c.max_change_percent)}%</Fact>
                    <Fact label="Uitzonderingen">{Object.keys(c.category_overrides ?? {}).length} cat. · {Object.keys(c.sku_overrides ?? {}).length} SKU</Fact>
                    <Fact label="Planner">{c.schedule_enabled ? `aan, ${c.schedule_hour_utc}:00 UTC` : "uit"}</Fact>
                  </Facts>
                  <Button size="sm" variant="outline" disabled={dis} onClick={() => { setF(toForm(c)); setConfirmed(false); }} data-testid="button-load-revision">Laad in formulier</Button>
                </div>);
              }}
            </RecordLoader>

          </Section>
        )}
      </div>
    </div>
  );
}
