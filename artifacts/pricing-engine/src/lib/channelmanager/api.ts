/**
 * Channelmanager-client. Paden en request-types komen uit de gegenereerde
 * OpenAPI-types (@workspace/api-client-react). Eigen fetch alleen omdat
 * customFetch een globale 15s-timeout combineert met elk signaal; hier geldt
 * 90s plus het annuleersignaal van React Query. Responses worden altijd door
 * de parsers in ./model gecontroleerd.
 */
import type {
  ChannelBasisInput, ChannelCalculationInput, ChannelChannelConfig, ChannelConfigInput,
  ChannelNotes,
} from "@workspace/api-client-react";
import { getAuthHeaders } from "@/lib/auth";
import { ShapeError, parseOverview } from "./model";
import type { Overview, Snapshot } from "./model";

export type { ChannelChannelConfig as ChannelConfig };
export type SnapshotKind = "config" | "basis" | "calculation" | "export" | "readback" | "run";
export type BasisMeta = Omit<ChannelBasisInput, "rows">;
export type BasisCsvMapping = Partial<Record<"sku" | "name" | "category" | "base_price" | "cost" | "current_price", string>>;
export interface BasisCsvSettings extends BasisMeta { mapping: BasisCsvMapping; delimiter: ChannelChannelConfig["delimiter"]; decimal: ChannelChannelConfig["decimal"] }
export interface ReadbackSettings {
  mapping: { sku: string; actual_price: string };
  delimiter: NonNullable<ChannelChannelConfig["delimiter"]>; decimal: NonNullable<ChannelChannelConfig["decimal"]>;
  currency: string; price_basis: ChannelChannelConfig["price_basis"]; vat_rate: string;
}

const BASE = "/api/channelmanager";
const TIMEOUT = 90_000;

export class CmError extends Error {
  constructor(public status: number, message: string, public lines: string[]) { super(message); }
}

/** FastAPI-detail: string, of lijst {loc,msg} (422). Altijd leesbare regels. */
export function detailLines(body: unknown): string[] {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  if (Array.isArray(d)) return d.map(x => {
    const e = x as { loc?: unknown[]; msg?: string };
    const loc = Array.isArray(e.loc) ? e.loc.filter(p => p !== "body").join(" › ") : "";
    return `${loc ? `${loc}: ` : ""}${e.msg ?? String(x)}`;
  });
  return [];
}

async function call(path: string, init: RequestInit & { raw?: boolean } = {}, outer?: AbortSignal): Promise<unknown> {
  const timeout = AbortSignal.timeout(TIMEOUT);
  const signal = outer ? AbortSignal.any([timeout, outer]) : timeout;
  const headers: Record<string, string> = { ...getAuthHeaders() };
  if (typeof init.body === "string") headers["content-type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers, credentials: "include", signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError") throw new CmError(0, "De server reageerde niet binnen 90 seconden.", []);
    throw e;
  }
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* geen json */ }
    const lines = detailLines(body);
    throw new CmError(res.status, lines.join("\n") || res.statusText || `HTTP ${res.status}`, lines);
  }
  if (init.raw) return res.blob();
  return res.json();
}
const post = (path: string, body: unknown) => call(path, { method: "POST", body: JSON.stringify(body) });
const multipart = (path: string, settings: unknown, file: File) => {
  const fd = new FormData(); fd.append("settings", JSON.stringify(settings)); fd.append("file", file);
  return call(path, { method: "POST", body: fd });
};

export const cmKeys = {
  shop: (u: string, s: number) => ["channelmanager", u, s] as const,
  overview: (u: string, s: number) => ["channelmanager", u, s, "overview"] as const,
  sourceOverview: (u: string, s: number, src: number) => ["channelmanager", u, s, "source-overview", src] as const,
  history: (u: string, s: number, kind: SnapshotKind, offset: number) => ["channelmanager", u, s, "history", kind, offset] as const,
  record: (u: string, s: number, id: number) => ["channelmanager", u, s, "record", id] as const,
};

function snapshotList(v: unknown): { items: Snapshot[]; has_more: boolean } {
  const o = v as { items?: unknown; has_more?: unknown };
  if (!o || !Array.isArray(o.items) || typeof o.has_more !== "boolean") throw new ShapeError("historie");
  return o as { items: Snapshot[]; has_more: boolean };
}

export const cmApi = {
  overview: async (s: number, sig?: AbortSignal): Promise<Overview> => parseOverview(await call(`/${s}/overview`, {}, sig)),
  history: async (s: number, kind: SnapshotKind, offset: number, limit: number, sig?: AbortSignal) =>
    snapshotList(await call(`/${s}/history?kind=${kind}&offset=${offset}&limit=${limit}`, {}, sig)),
  record: (s: number, id: number, sig?: AbortSignal) => call(`/${s}/records/${id}`, {}, sig),
  saveConfig: (s: number, body: ChannelConfigInput) => post(`/${s}/config`, body),
  stageBasis: (s: number, body: ChannelBasisInput) => post(`/${s}/basis`, body),
  stageBasisCsv: (s: number, settings: BasisCsvSettings, file: File) => multipart(`/${s}/basis-csv`, settings, file),
  approveBasis: (s: number, id: number, body: ChannelNotes) => post(`/${s}/basis/${id}/approve`, body),
  calculate: (s: number, body: ChannelCalculationInput) => post(`/${s}/calculate`, body),
  approveCalc: (s: number, id: number, body: ChannelNotes) => post(`/${s}/calculations/${id}/approve`, body),
  exportCalc: (s: number, id: number, body: ChannelNotes) => post(`/${s}/calculations/${id}/export`, body),
  download: (s: number, id: number) => call(`/${s}/exports/${id}/download`, { raw: true }) as Promise<Blob>,
  readback: (s: number, id: number, settings: ReadbackSettings, file: File) => multipart(`/${s}/exports/${id}/readback`, settings, file),
  run: (s: number) => call(`/${s}/run`, { method: "POST" }),
};

export function errLines(e: unknown): { title: string; lines: string[] } {
  if (e instanceof CmError) {
    const t: Record<number, string> = {
      403: "Geen recht voor deze actie", 404: "Niet gevonden of buiten je winkelbereik",
      409: "Conflict of verouderd: herlaad of herbereken eerst", 413: "Bestand te groot", 422: "Validatiefout", 0: "Time-out",
    };
    return { title: t[e.status] ?? `Serverfout (${e.status})`, lines: e.lines.length ? e.lines : [e.message] };
  }
  return { title: "Fout", lines: [e instanceof Error ? e.message : String(e)] };
}
export function errText(e: unknown): string { const x = errLines(e); return `${x.title}: ${x.lines.join("; ")}`; }

/** Validatie van decimale strings; teken +/- toegestaan waar `signed`. Grenzen inclusief tenzij maxExclusive. */
export function decError(v: string, opts: { signed?: boolean; required?: boolean; max?: number; maxExclusive?: number } = {}): string | null {
  const t = v.trim();
  if (!t) return opts.required ? "Verplicht" : null;
  const re = opts.signed ? /^[+-]?\d+(\.\d+)?$/ : /^\d+(\.\d+)?$/;
  if (!re.test(t)) return opts.signed ? "Decimaal met punt, bv. -2.50 of +5" : "Niet-negatief decimaal met punt, bv. 0.21";
  if ((t.split(".")[1]?.length ?? 0) > 12) return "Maximaal 12 decimalen";
  const n = Number(t);
  if (opts.max !== undefined && n > opts.max) return `Maximaal ${opts.max}`;
  if (opts.maxExclusive !== undefined && n >= opts.maxExclusive) return `Moet kleiner zijn dan ${opts.maxExclusive}`;
  return null;
}

export const fmtDate = (s?: string | null) => s ? new Date(s).toLocaleString("nl-NL", { dateStyle: "short", timeStyle: "short" }) : "—";
export const dash = (v: string | number | null | undefined) => v === null || v === undefined || v === "" ? "—" : String(v);
