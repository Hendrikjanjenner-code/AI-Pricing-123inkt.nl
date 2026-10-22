/**
 * Typed adapters for Hub feeds (.local/hub-feeds-api.md) and the printer
 * workflow (.local/printer-api.md). Hand-written until OpenAPI codegen covers
 * these routes; errors use the Channelmanager CmError so ErrorBox/errText work.
 * Query keys live under the Channelmanager shop prefix so useCmAction's
 * scoped invalidation refreshes them after every mutation.
 */
import { getAuthHeaders } from "@/lib/auth";
import { CmError, detailLines } from "@/lib/channelmanager/api";
import type {
  HubFeedsBuildInput, HubFeedsProfileInput, PrinterWorkflowAdviceInput, PrinterWorkflowApproveInput, PrinterWorkflowCalculateInput,
  PrinterWorkflowConfigInput, PrinterWorkflowNotes, PrinterWorkflowPriceRow, PrinterWorkflowPricesInput, PrinterWorkflowPrinterConfig,
} from "@workspace/api-client-react";
/** Generated PrinterConfig predates `rules`; extend until codegen includes it. */
export interface ConditionalRule {
  threshold?: string; lower_offset: string; upper_offset: string; multiplier?: string;
  round_inner_integer?: boolean; lower_tail?: string; upper_tail?: string;
}
export type PrinterConfig = PrinterWorkflowPrinterConfig & { rules?: Record<string, ConditionalRule> };
export const DEFAULT_RULES: Record<string, Required<ConditionalRule>> = {
  Printerland: { threshold: "50", lower_offset: "6", upper_offset: "5", multiplier: "1", round_inner_integer: false, lower_tail: "0", upper_tail: "0" },
  Printabout: { threshold: "50", lower_offset: "1.50", upper_offset: ".50", multiplier: "1", round_inner_integer: false, lower_tail: "0", upper_tail: "0" },
  Sneltoner: { threshold: "50", lower_offset: "3", upper_offset: "2", multiplier: "1", round_inner_integer: false, lower_tail: "0", upper_tail: "0" },
  Tonershop: { threshold: "50", lower_offset: "2", upper_offset: "1", multiplier: "1.1", round_inner_integer: true, lower_tail: "2.99", upper_tail: "1.99" },
};

export type FeedPurpose = "cost" | "products" | "advice" | "cost_output";
export const PURPOSE_NL: Record<FeedPurpose, string> = {
  cost: "Kostprijsbron (DRS)", products: "Productreferentie", advice: "PriceShape-adviezen", cost_output: "Uitgaande Hub-costfeed",
};

export interface FeedConfig {
  has_url?: boolean;
  has_bearer_token?: boolean;
  url?: string;
  bearer_token?: string;
  mode?: "sources" | "reference";
  mapping?: Record<string, string>;
  type_mapping?: Record<string, string>;
  vat_rate?: string;
  vat_basis?: "inc" | "exc";
  unit_confirmed?: boolean;
  complete_snapshot_confirmed?: boolean;
  minimum_rows?: number;
  interval_minutes?: number;
  custom_source?: string;
  [k: string]: unknown;
}
export interface FeedProfile {
  id: number; shop_id: number; name: string; purpose: FeedPurpose; revision: number; active: boolean;
  config: FeedConfig;
  validated_version_id: number | null; current_version_id: number | null; released_version_id: number | null;
  last_attempt: string | null; last_success: string | null; last_error: string | null; created_at: string;
}
export interface FeedReport {
  errors?: unknown[]; warnings?: unknown[]; duplicate_rows?: number; distinct_products?: number; [k: string]: unknown;
}
export interface FeedVersion {
  id: number; profile_id: number; config_revision: number; status: "valid" | "invalid"; sha256: string;
  row_count: number; report: FeedReport; created_at: string; records?: Record<string, unknown>[];
}

/** Snapshot envelope as returned by routes/channelmanager.dump. */
export interface Envelope<K extends string, S extends string, D> {
  id: number; shop_id: number; kind: K; revision: number; status: S; created_at: string; created_by: string | null; data: D;
}
export type CalcState = "ready" | "missing_basis_pre_price" | "zero_basis_comparison_price" | "advice_below_20_do_not_adjust"
  | "missing_target_pre_price" | "zero_target_pre_price_suppressed";
export const CALC_STATE_NL: Record<CalcState, string> = {
  ready: "Klaar", missing_basis_pre_price: "123inkt-preprijs ontbreekt", zero_basis_comparison_price: "123inkt-preprijs is 0 (geen vergelijking)",
  advice_below_20_do_not_adjust: "Advies onder EUR 20: niet aanpassen", missing_target_pre_price: "Preprijs doelwinkel ontbreekt",
  zero_target_pre_price_suppressed: "Doelwinkel preprijs 0: overgeslagen",
};
export interface CalcRow { sku: string; source_id: string; shop_id: number; label: PrinterLabel; advice: string; current_price: string | null; target_price: string | null; state: CalcState }
export interface CheckRow { sku: string; shop_id: number; expected: string; actual: string | null; difference: string | null; state: "missing" | "matched" | "mismatch" }
export const PRINTER_LABELS = ["123inkt", "Printerland", "Printabout", "Sneltoner", "Tonershop"] as const;
export type PrinterLabel = (typeof PRINTER_LABELS)[number];
type Prov = { config_id: number; notes: string };
export type PConfig = Envelope<"printer_config", "draft", { config: PrinterConfig; notes: string }>;
export type PPre = Envelope<"printer_pre", "draft", Prov & { rows: PriceRow[]; duplicates: number }>;
export type PAdvice = Envelope<"printer_advice", "approved", Prov & { profile_id: number; version_id: number; rows: Record<string, unknown>[]; semantics: Record<string, string> }>;
export type PCalc = Envelope<"printer_calculation", "blocked" | "calculated", Prov & {
  rows: CalcRow[]; warnings: { sku: string; reason: "change_over_20_percent" }[]; blocks: { sku: string; shop_id: number; reason: CalcState }[];
  pre_duplicates: number; advice_duplicates: number; pre_only_products: string[]; pre_id: number; advice_id: number;
}>;
export type PApproval = Envelope<"printer_approval", "approved", Prov & { calculation_id: number; acknowledge_warnings: boolean }>;
export type PExport = Envelope<"printer_export", "created", Prov & {
  pre_id: number; advice_id: number; calculation_id: number; approval_id: number; feed_version_id: number; status: "created_not_processed";
  sha256: string; filename: string; rows: CalcRow[]; drs_compatibility: "unconfirmed";
}>;
export type PReadback = Envelope<"printer_readback", "confirmed" | "mismatch", Prov & {
  checks: CheckRow[]; extra_rows: { sku: string; shop_id: number }[]; duplicates: number; confirmed: boolean; export_id: number; export_sha256: string; rows: PriceRow[];
  sha256?: string; filename?: string;
}>;
export type PrinterSnap = PConfig | PPre | PAdvice | PCalc | PApproval | PExport | PReadback;
export interface PrinterState {
  config: PConfig | null; pre: PPre | null; advice: PAdvice | null; calculation: PCalc | null;
  approval: PApproval | null; export: PExport | null; readback: PReadback | null;
  history: PrinterSnap[]; has_more: boolean; next_before_id: number | null; drs_compatibility: "unconfirmed"; live_write: false;
}
export const KIND_NL: Record<string, string> = {
  printer_config: "Config", printer_pre: "Pre-prijzen", printer_advice: "Advies", printer_calculation: "Berekening",
  printer_approval: "Goedkeuring", printer_export: "Export", printer_readback: "Terugleescontrole",
};
export const STATUS_NL: Record<string, string> = {
  draft: "Vastgelegd", approved: "Goedgekeurd", blocked: "Geblokkeerd", calculated: "Berekend", created: "Aangemaakt, niet verwerkt",
  confirmed: "Bevestigd", mismatch: "Afwijkingen",
};
export type PriceRow = PrinterWorkflowPriceRow;


const TIMEOUT = 120_000;
async function call(path: string, init: RequestInit & { raw?: boolean } = {}, outer?: AbortSignal): Promise<unknown> {
  const t = AbortSignal.timeout(TIMEOUT);
  const signal = outer ? AbortSignal.any([t, outer]) : t;
  const headers: Record<string, string> = { ...getAuthHeaders() };
  if (typeof init.body === "string") headers["content-type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, headers, credentials: "include", signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError") throw new CmError(0, "De server reageerde niet binnen 120 seconden.", []);
    throw e;
  }
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* geen json */ }
    const lines = detailLines(body);
    throw new CmError(res.status, lines.join("\n") || res.statusText || `HTTP ${res.status}`, lines);
  }
  if (init.raw) return res;
  return res.json();
}
const json = (method: string, path: string, body?: unknown) =>
  call(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

function list<T>(v: unknown, key: string): T[] {
  const arr = (v as Record<string, unknown> | null)?.[key];
  if (!Array.isArray(arr)) throw new CmError(-1, `Onverwacht antwoord: '${key}' ontbreekt`, []);
  return arr as T[];
}

/** Download Response als bestand; bestandsnaam uit Content-Disposition. */
export async function saveResponse(resPromise: Promise<unknown>, fallback: string) {
  const res = (await resPromise) as Response;
  const cd = res.headers.get("content-disposition") ?? "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : fallback;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return name;
}

const H = "/hub-feeds";
export const feedKeys = {
  profiles: (u: string, s: number) => ["channelmanager", u, s, "hub-feeds", "profiles"] as const,
  versions: (u: string, s: number, p: number) => ["channelmanager", u, s, "hub-feeds", "versions", p] as const,
  version: (u: string, s: number, p: number, v: number) => ["channelmanager", u, s, "hub-feeds", "version", p, v] as const,
  printer: (u: string, s: number) => ["channelmanager", u, s, "printer"] as const,
  printerHistory: (u: string, s: number, before: number) => ["channelmanager", u, s, "printer", "history", before] as const,
};

export const feedApi = {
  profiles: async (s: number, sig?: AbortSignal) => list<FeedProfile>(await call(`${H}/${s}/profiles`, {}, sig), "profiles"),
  create: (s: number, body: HubFeedsProfileInput) =>
    json("POST", `${H}/${s}/profiles`, body) as Promise<FeedProfile>,
  update: (s: number, id: number, body: HubFeedsProfileInput) =>
    json("PUT", `${H}/${s}/profiles/${id}`, body) as Promise<FeedProfile>,
  upload: (s: number, id: number, file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return call(`${H}/${s}/profiles/${id}/upload`, { method: "POST", body: fd }) as Promise<FeedVersion>;
  },
  test: (s: number, id: number) => json("POST", `${H}/${s}/profiles/${id}/test`) as Promise<FeedVersion>,
  activate: (s: number, id: number, version_id: number) => json("POST", `${H}/${s}/profiles/${id}/activate`, { version_id }) as Promise<FeedProfile>,
  pause: (s: number, id: number) => json("POST", `${H}/${s}/profiles/${id}/pause`) as Promise<FeedProfile>,
  versions: async (s: number, id: number, sig?: AbortSignal) => list<FeedVersion>(await call(`${H}/${s}/profiles/${id}/versions`, {}, sig), "versions"),
  version: (s: number, id: number, v: number, sig?: AbortSignal) => call(`${H}/${s}/profiles/${id}/versions/${v}`, {}, sig) as Promise<FeedVersion>,
  downloadVersion: (s: number, id: number, v: number) => saveResponse(call(`${H}/${s}/profiles/${id}/versions/${v}/download`, { raw: true }), `feed-${id}-v${v}.csv`),
  build: (s: number, id: number, body: HubFeedsBuildInput) => json("POST", `${H}/${s}/profiles/${id}/build`, body) as Promise<FeedVersion>,
  token: (s: number, id: number) => json("POST", `${H}/${s}/profiles/${id}/token`) as Promise<{ token: string; feed_path: string; authentication: string; shown_once: true }>,
  compare: (s: number, cost: number, products: number, sig?: AbortSignal) =>
    call(`${H}/${s}/compare?cost_profile_id=${cost}&products_profile_id=${products}`, {}, sig) as Promise<{
      cost_version_id: number; products_version_id: number; cost_only: string[]; products_only: string[]; matched_products: number; cost_rows: number; products_rows: number }>,
  release: (s: number, id: number, version_id: number) => json("POST", `${H}/${s}/profiles/${id}/release`, { version_id }) as Promise<FeedProfile>,
  downloadFeed: (s: number, id: number) => saveResponse(call(`${H}/${s}/profiles/${id}/feed`, { raw: true }), `hub-costfeed-${id}.csv`),
  feedPath: (s: number, id: number) => `/api${H}/${s}/profiles/${id}/feed`,
};

const P = "/channelmanager/printer";
export const printerApi = {
  state: (s: number, sig?: AbortSignal, beforeId?: number) => call(`${P}/${s}${beforeId ? `?before_id=${beforeId}&limit=50` : ""}`, {}, sig) as Promise<PrinterState>,
  saveConfig: (s: number, body: Omit<PrinterWorkflowConfigInput, "config"> & { config: PrinterConfig }) => json("PUT", `${P}/${s}/config`, body) as Promise<PConfig>,
  pre: (s: number, body: PrinterWorkflowPricesInput) => json("POST", `${P}/${s}/pre`, body) as Promise<PPre>,
  advice: (s: number, body: PrinterWorkflowAdviceInput) => json("POST", `${P}/${s}/advice`, body) as Promise<PAdvice>,
  calculate: (s: number, body: PrinterWorkflowCalculateInput) => json("POST", `${P}/${s}/calculate`, body) as Promise<PCalc>,
  approve: (s: number, calcId: number, body: PrinterWorkflowApproveInput) => json("POST", `${P}/${s}/approve/${calcId}`, body) as Promise<PApproval>,
  export: (s: number, approvalId: number, body: PrinterWorkflowNotes) => json("POST", `${P}/${s}/export/${approvalId}`, body) as Promise<PExport>,
  download: (s: number, exportId: number) => saveResponse(call(`${P}/${s}/download/${exportId}`, { raw: true }), `printer_prijs_aanpassingen_${exportId}.xlsx`),
  downloadReadback: (s: number, id: number) => saveResponse(call(`${P}/${s}/readback/${id}/download`, { raw: true }), `printer_readback_${id}.xlsx`),
  readback: (s: number, exportId: number, body: PrinterWorkflowPricesInput) => json("POST", `${P}/${s}/readback/${exportId}`, body) as Promise<PReadback>,
};
