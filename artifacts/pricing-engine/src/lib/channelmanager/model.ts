/**
 * Exacte vormen van Snapshot.data zoals routes/channelmanager.py en
 * services/channelmanager.py ze opslaan. Parsers controleren de vorm en
 * gooien bij afwijking een expliciete fout — geen stille terugvaloptie.
 */
import type {
  ChannelChannelConfig, ChannelRule, ChannelSchedulerOutput, ChannelSnapshotOutput,
} from "@workspace/api-client-react";

export type Snapshot = ChannelSnapshotOutput;

export class ShapeError extends Error {
  constructor(what: string) { super(`Onverwachte serverrespons: ${what}`); }
}
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const strOrNull = (v: unknown) => v === null || isStr(v);
function need(cond: boolean, what: string): asserts cond { if (!cond) throw new ShapeError(what); }

export const STATUS = {
  config: ["active"],
  basis: ["staged", "approved"],
  calculation: ["preview", "approved"],
  export: ["exported"],
  readback: ["matched", "partial"],
  run: ["running", "success", "failed"],
} as const;

function snap(s: unknown, kind: keyof typeof STATUS): Snapshot {
  need(isObj(s) && isNum(s.id) && isNum(s.revision) && isStr(s.status) && isStr(s.created_at) && isObj(s.data), `${kind}-snapshot`);
  need(s.kind === kind, `verwacht soort ${kind}, kreeg ${String(s.kind)}`);
  need((STATUS[kind] as readonly string[]).includes(s.status as string), `onbekende status ${String(s.status)} voor ${kind}`);
  return s as unknown as Snapshot;
}
function rule(r: unknown): ChannelRule {
  need(isObj(r) && (r.kind === "fixed" || r.kind === "percentage") && isStr(r.value), "regel");
  return r as unknown as ChannelRule;
}

export interface Approval { by: string; notes: string; at: string }
function approval(a: unknown): Approval | null {
  if (a === undefined) return null;
  need(isObj(a) && isStr(a.by) && isStr(a.notes) && isStr(a.at), "goedkeuring");
  return a as unknown as Approval;
}

// ---- config ---------------------------------------------------------------
export interface ConfigData { notes: string; expected_revision: number; config: ChannelChannelConfig }
export function parseConfig(s: unknown): { snap: Snapshot; data: ConfigData } {
  const x = snap(s, "config"); const d = x.data as Record<string, unknown>;
  need(isStr(d.notes) && isNum(d.expected_revision) && isObj(d.config), "config.data");
  const c = d.config as Record<string, unknown>;
  need(isStr(c.currency) && (c.price_basis === "net" || c.price_basis === "gross") && isStr(c.vat_rate), "config.data.config");
  rule(c.rule);
  need(isObj(c.export_columns) && isStr(c.delimiter) && isStr(c.decimal) && typeof c.schedule_enabled === "boolean" && isNum(c.schedule_hour_utc), "config exportprofiel/planner");
  return { snap: x, data: d as unknown as ConfigData };
}

// ---- basis ---------------------------------------------------------------
export interface BasisData {
  currency: string; price_basis: "net" | "gross"; vat_rate: string; cost_basis: "net";
  provenance: "manual_csv" | "PriceShape_unverified"; notes: string; rows: BasisRow[];
  approval: Approval | null;
}
export interface BasisRow { sku: string; name: string; category: string; base_price: string; cost: string | null; current_price: string | null }
export function parseBasis(s: unknown): { snap: Snapshot; data: BasisData } {
  const x = snap(s, "basis"); const d = x.data as Record<string, unknown>;
  need(isStr(d.currency) && isStr(d.vat_rate) && isStr(d.provenance) && isStr(d.notes) && Array.isArray(d.rows), "basis.data");
  for (const r of d.rows as unknown[]) need(isObj(r) && isStr(r.sku) && isStr(r.name) && isStr(r.category) && isStr(r.base_price) && strOrNull(r.cost) && strOrNull(r.current_price), "basisrij");
  return { snap: x, data: { ...(d as any), approval: approval(d.approval) } };
}

// ---- calculation -----------------------------------------------------------
export interface CalcRow extends BasisRow {
  rule_source: "sku" | "category" | "shop"; rule: ChannelRule;
  target_price: string | null; current_delta: string | null; net_margin: string | null; errors: string[];
  /** Alleen bij basis uit een andere winkel: huidige prijs van de bron, nooit de bestemming. */
  source_current_price?: string | null;
}
export interface CostProvenance { source_shop_id: number; basis_id: number; provenance: string; cost_basis: "net"; note: string }
export interface CalcData {
  source_shop_id: number; basis_id: number; config_id: number; config: ChannelChannelConfig; rows: CalcRow[];
  export_schema: Record<string, string>; csv_preview: string | null; blocked_rows: number; approval: Approval | null;
  /** Ontbreekt bij berekeningen van vóór deze backendversie. */
  current_price_note?: string; cost_provenance?: CostProvenance;
}
function calcRow(r: unknown): CalcRow {
  need(isObj(r) && isStr(r.sku) && isStr(r.base_price) && ["sku", "category", "shop"].includes(r.rule_source as string)
    && strOrNull(r.target_price) && strOrNull(r.current_delta) && strOrNull(r.net_margin)
    && Array.isArray(r.errors) && (r.errors as unknown[]).every(isStr)
    && (r.source_current_price === undefined || strOrNull(r.source_current_price)), "berekeningsrij");
  rule(r.rule);
  return r as unknown as CalcRow;
}
function calcData(d: Record<string, unknown>): CalcData {
  need(isNum(d.source_shop_id) && isNum(d.basis_id) && isNum(d.config_id) && isObj(d.config) && Array.isArray(d.rows)
    && isObj(d.export_schema) && strOrNull(d.csv_preview) && isNum(d.blocked_rows), "berekening.data");
  need(d.current_price_note === undefined || isStr(d.current_price_note), "berekening.current_price_note");
  need(d.cost_provenance === undefined || (isObj(d.cost_provenance) && isStr(d.cost_provenance.note) && isStr(d.cost_provenance.provenance)), "berekening.cost_provenance");
  return { ...(d as any), rows: (d.rows as unknown[]).map(calcRow), approval: approval(d.approval) };
}
export function parseCalculation(s: unknown): { snap: Snapshot; data: CalcData } {
  const x = snap(s, "calculation");
  return { snap: x, data: calcData(x.data as Record<string, unknown>) };
}

// ---- export ----------------------------------------------------------------
export interface ExportData extends CalcData { calculation_id: number; notes: string; csv: string; schema: Record<string, string>; fingerprint: string; processed: boolean }
export function parseExport(s: unknown): { snap: Snapshot; data: ExportData } {
  const x = snap(s, "export"); const d = x.data as Record<string, unknown>;
  need(isNum(d.calculation_id) && isStr(d.csv) && isObj(d.schema) && isStr(d.fingerprint) && typeof d.processed === "boolean", "export.data");
  return { snap: x, data: { ...calcData(d), calculation_id: d.calculation_id as number, notes: String(d.notes ?? ""), csv: d.csv as string, schema: d.schema as Record<string, string>, fingerprint: d.fingerprint as string, processed: d.processed as boolean } };
}

// ---- readback --------------------------------------------------------------
export interface ReadbackCompare { sku: string; target_price: string; actual_price: string | null; matched: boolean }
export interface ReadbackData {
  export_id: number; source_shop_id: number; fingerprint: string; rows: ReadbackCompare[];
  received_rows: { sku: string; actual_price: string | null }[];
  missing: string[]; unexpected: string[]; duplicates: string[]; matched_count: number; processed: boolean;
}
export function parseReadback(s: unknown): { snap: Snapshot; data: ReadbackData } {
  const x = snap(s, "readback"); const d = x.data as Record<string, unknown>;
  const strs = (v: unknown) => Array.isArray(v) && v.every(isStr);
  need(isNum(d.export_id) && isStr(d.fingerprint) && Array.isArray(d.rows) && Array.isArray(d.received_rows)
    && strs(d.missing) && strs(d.unexpected) && strs(d.duplicates) && isNum(d.matched_count) && typeof d.processed === "boolean", "terugmelding.data");
  for (const r of d.rows as unknown[]) need(isObj(r) && isStr(r.sku) && isStr(r.target_price) && strOrNull(r.actual_price) && typeof r.matched === "boolean", "vergelijkingsrij");
  return { snap: x, data: d as unknown as ReadbackData };
}

/** Buckets afgeleid uit de serverlijsten; "afwijkend" = aanwezig, uniek, niet gematcht. */
export function readbackBuckets(d: ReadbackData) {
  const dup = new Set(d.duplicates);
  const mismatch = d.rows.filter(r => !r.matched && r.actual_price !== null && !dup.has(r.sku));
  return {
    matching: d.rows.filter(r => r.matched).map(r => r.sku),
    missing: d.missing, mismatch: mismatch.map(r => r.sku), unexpected: d.unexpected, duplicate: d.duplicates,
    mismatchRows: mismatch,
  };
}

// ---- run -------------------------------------------------------------------
export interface RunData { source_shop_id: number; timezone: string; started_at: string; finished_at?: string; calculation_id?: number; error?: string }
export function parseRun(s: unknown): { snap: Snapshot; data: RunData } {
  const x = snap(s, "run"); const d = x.data as Record<string, unknown>;
  need(isNum(d.source_shop_id) && isStr(d.started_at), "run.data");
  return { snap: x, data: d as unknown as RunData };
}

// ---- overview --------------------------------------------------------------
export const QUEUE_KEYS = ["staged", "preview", "approved", "exported", "partial", "failed", "running"] as const;
export const COUNT_KEYS = ["basis", "calculation", "export", "readback", "run"] as const;
export interface Overview {
  config: Snapshot | null; basis: Snapshot | null; last_run: Snapshot | null; history_limit: number;
  external_formats: string; schedule_timezone: string; can_propose: boolean; can_approve: boolean; can_export: boolean;
  queues: Record<(typeof QUEUE_KEYS)[number], number>; counts: Record<(typeof COUNT_KEYS)[number], number>;
  scheduler: ChannelSchedulerOutput;
}
export function parseOverview(o: unknown): Overview {
  need(isObj(o), "overzicht");
  need(typeof o.can_propose === "boolean" && typeof o.can_approve === "boolean" && typeof o.can_export === "boolean", "overzicht.rechten");
  need(isObj(o.queues) && QUEUE_KEYS.every(k => isNum((o.queues as any)[k])), "overzicht.queues");
  need(isObj(o.counts) && COUNT_KEYS.every(k => isNum((o.counts as any)[k])), "overzicht.counts");
  need(isStr(o.external_formats) && isStr(o.schedule_timezone), "overzicht.formaten");
  const sc = o.scheduler;
  need(isObj(sc) && typeof sc.running === "boolean" && typeof sc.available === "boolean" && typeof sc.disabled === "boolean"
    && isStr(sc.mode) && isNum(sc.poll_interval_seconds) && isStr(sc.timezone) && strOrNull(sc.reason) && strOrNull(sc.last_poll_at) && strOrNull(sc.last_error), "overzicht.scheduler");
  return {
    config: o.config === null ? null : parseConfig(o.config).snap,
    basis: o.basis === null ? null : parseBasis(o.basis).snap,
    last_run: o.last_run === null ? null : parseRun(o.last_run).snap,
    history_limit: o.history_limit as number, external_formats: o.external_formats as string, schedule_timezone: o.schedule_timezone as string,
    can_propose: o.can_propose as boolean, can_approve: o.can_approve as boolean, can_export: o.can_export as boolean,
    queues: o.queues as Overview["queues"], counts: o.counts as Overview["counts"], scheduler: sc as unknown as ChannelSchedulerOutput,
  };
}
