/**
 * Kanaalregister-client (contract .local/channel-registry-api.md).
 * Requestbodies getypeerd met gegenereerde ChannelDirectory-types; responses lokaal geparsed.
 * Zelfde 90s-fetch als cmApi; responses worden vormgecontroleerd.
 */
import type { ChannelDirectoryChannelOutput, ChannelDirectoryReorder, ChannelDirectoryNewChannel, ChannelDirectoryRevision, ChannelDirectorySetup, ChannelDirectoryVisibility } from "@workspace/api-client-react";
import { getAuthHeaders } from "@/lib/auth";
import { CmError, detailLines } from "./api";

export type ChannelStatus = "setup" | "ready" | "active" | "paused" | "needs_validation" | "restricted";
export interface Mapping { source_productcode: string; target_productcode: string }
/** Gebaseerd op gegenereerde ChannelDirectoryChannelOutput; id is een UUID-string. */
export interface Channel extends Omit<ChannelDirectoryChannelOutput, "status" | "external_connected"> {
  external_connected: boolean;
  id: string; name: string; domain: string; hidden: boolean; status: ChannelStatus;
  target_shop_id: number | null; product_profile_id: number | null; mappings: Mapping[]; mapping_confirmed: boolean;
  mapped_products: number | null; last_success_at: string | null; validation_errors: string[]; validated_at: string | null;
  can_edit: boolean; can_activate: boolean;
}
export interface Registry { revision: number; channels: Channel[]; can_edit: boolean; can_activate: boolean }
export interface ChannelDraft { target_shop_id: number | null; product_profile_id: number | null; mappings: Mapping[]; mapping_confirmed: boolean }

const STATUSES: ChannelStatus[] = ["setup", "ready", "active", "paused", "needs_validation", "restricted"];
const fail = (m: string): never => { throw new CmError(0, `Onverwacht antwoord van de server: ${m}`, []); };

function parseChannel(v: unknown): Channel {
  const c = v as Partial<Channel> | null;
  if (!c || typeof c.id !== "string" || !c.id || typeof c.name !== "string") return fail("kanaal zonder id/naam");
  if (!STATUSES.includes(c.status as ChannelStatus)) return fail(`onbekende status ${String(c.status)}`);
  const mappings = Array.isArray(c.mappings) ? c.mappings.map(m => ({ source_productcode: String(m?.source_productcode ?? ""), target_productcode: String(m?.target_productcode ?? "") })) : [];
  return {
    external_connected: (c as { external_connected?: unknown }).external_connected === true,
    id: c.id, name: c.name, domain: String(c.domain ?? ""), hidden: !!c.hidden, status: c.status as ChannelStatus,
    target_shop_id: typeof c.target_shop_id === "number" ? c.target_shop_id : null,
    product_profile_id: typeof c.product_profile_id === "number" ? c.product_profile_id : null,
    mappings, mapping_confirmed: !!c.mapping_confirmed,
    mapped_products: typeof c.mapped_products === "number" ? c.mapped_products : null,
    last_success_at: typeof c.last_success_at === "string" ? c.last_success_at : null,
    validation_errors: Array.isArray(c.validation_errors) ? c.validation_errors.map(String) : [],
    validated_at: typeof c.validated_at === "string" ? c.validated_at : null,
    can_edit: !!c.can_edit, can_activate: !!c.can_activate,
  };
}
export function parseRegistry(v: unknown): Registry {
  const r = v as Partial<Registry> | null;
  if (!r || typeof r.revision !== "number" || !Array.isArray(r.channels)) return fail("register zonder revisie/kanalen");
  return { revision: r.revision, channels: r.channels.map(parseChannel), can_edit: !!r.can_edit, can_activate: !!r.can_activate };
}

const BASE = "/api/channelmanager/channels";
async function raw(path: string, method = "GET", body?: unknown, outer?: AbortSignal): Promise<unknown> {
  const timeout = AbortSignal.timeout(90_000);
  const signal = outer ? AbortSignal.any([timeout, outer]) : timeout;
  const headers: Record<string, string> = { ...getAuthHeaders() };
  if (body !== undefined) headers["content-type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, credentials: "include", signal, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError") throw new CmError(0, "De server reageerde niet binnen 90 seconden.", []);
    throw e;
  }
  if (!res.ok) {
    let b: unknown = null;
    try { b = await res.json(); } catch { /* geen json */ }
    const lines = detailLines(b);
    throw new CmError(res.status, lines.join("\n") || res.statusText || `HTTP ${res.status}`, lines);
  }
  return res.json();
}
const call = async (path: string, method = "GET", body?: unknown, outer?: AbortSignal) => parseRegistry(await raw(path, method, body, outer));

export const regKeys = { list: (u: string, s: number) => ["channelmanager", u, s, "registry"] as const };
export const regApi = {
  list: (s: number, sig?: AbortSignal) => call(`/${s}`, "GET", undefined, sig),
  add: (s: number, rev: number, name: string, domain: string) => call(`/${s}`, "POST", { expected_revision: rev, name, domain } satisfies ChannelDirectoryNewChannel),
  save: (s: number, rev: number, id: string, d: ChannelDraft) => call(`/${s}/${id}`, "PUT", { expected_revision: rev, ...d } satisfies ChannelDirectorySetup),
  validate: (s: number, rev: number, id: string) => call(`/${s}/${id}/validate`, "POST", { expected_revision: rev } satisfies ChannelDirectoryRevision),
  activate: (s: number, rev: number, id: string) => call(`/${s}/${id}/activate`, "POST", { expected_revision: rev } satisfies ChannelDirectoryRevision),
  pause: (s: number, rev: number, id: string) => call(`/${s}/${id}/pause`, "POST", { expected_revision: rev } satisfies ChannelDirectoryRevision),
  visibility: (s: number, rev: number, id: string, hidden: boolean) => call(`/${s}/${id}/visibility`, "POST", { expected_revision: rev, hidden } satisfies ChannelDirectoryVisibility),
  /** Zet een kanaalbasis klaar (staged, nooit goedgekeurd) in de doelwinkel; geeft legacy snapshot terug. */
  prepareBasis: async (s: number, rev: number, id: string) => {
    const snap = await raw(`/${s}/${id}/prepare-basis`, "POST", { expected_revision: rev } satisfies ChannelDirectoryRevision) as { id?: unknown; revision?: unknown; status?: unknown } | null;
    if (!snap || typeof snap.id !== "number") return fail("basis-snapshot zonder id");
    return { id: snap.id, revision: typeof snap.revision === "number" ? snap.revision : null, status: String(snap.status ?? "") };
  },
  reorder: (s: number, rev: number, ids: string[]) => call(`/${s}/reorder`, "POST", { expected_revision: rev, channel_ids: ids } satisfies ChannelDirectoryReorder),
};

export const CH_STATUS: Record<ChannelStatus, { label: string; cls: string }> = {
  setup: { label: "Nog in te stellen", cls: "bg-amber-100 text-amber-900 border-amber-200" },
  ready: { label: "Gevalideerd", cls: "bg-sky-100 text-sky-900 border-sky-200" },
  active: { label: "Intern actief", cls: "bg-emerald-100 text-emerald-900 border-emerald-200" },
  paused: { label: "Gepauzeerd", cls: "bg-stone-200 text-stone-800 border-stone-300" },
  needs_validation: { label: "Opnieuw valideren", cls: "bg-orange-100 text-orange-900 border-orange-200" },
  restricted: { label: "Geen toegang", cls: "bg-muted text-muted-foreground border-border" },
};

/** Puntkomma-CSV source_productcode;target_productcode. Codes blijven strings (voorloopnullen). */
export function parseMappingCsv(text: string): { rows: Mapping[]; errors: string[] } {
  const rows: Mapping[] = []; const errors: string[] = [];
  text.replace(/^\uFEFF/, "").split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return;
    const parts = line.split(";").map(p => p.trim().replace(/^"(.*)"$/, "$1"));
    if (i === 0 && /source_productcode/i.test(parts[0] ?? "")) return;
    if (parts.length !== 2 || !parts[0] || !parts[1]) { errors.push(`Regel ${i + 1}: verwacht twee waarden gescheiden door ';'`); return; }
    rows.push({ source_productcode: parts[0], target_productcode: parts[1] });
  });
  return { rows, errors };
}
export function mappingErrors(rows: Mapping[]): string[] {
  const errs: string[] = []; const seen = new Set<string>();
  rows.forEach((r, i) => {
    if (!r.source_productcode.trim() || !r.target_productcode.trim()) errs.push(`Rij ${i + 1}: beide codes zijn verplicht`);
    const k = r.source_productcode.trim();
    if (k && seen.has(k)) errs.push(`Rij ${i + 1}: broncode ${k} komt dubbel voor`);
    seen.add(k);
  });
  return errs;
}
