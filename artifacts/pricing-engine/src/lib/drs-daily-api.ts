/**
 * API-laag voor DRS-dagimport, identiteitsherstel en marge-inzicht.
 * Contracten: .local/drs-daily-api-contract.md, drs-resolution-api-contract.md,
 * drs-margin-api-contract.md. Codes (productcode/EAN/OEM) blijven altijd strings
 * zodat voorloopnullen behouden blijven.
 */
import { getAuthHeaders } from "@/lib/auth";

export const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
export const DEFAULT_TIMEOUT_MS = 15_000;
export const LONG_TIMEOUT_MS = 180_000;

import type {
  DrsDailyPreview, DrsDailyRevalidation, DrsDailyResult, DrsMappingResult, DrsDailyError,
  DrsProductCandidate, DrsUnresolvedRow, DrsUnresolvedPage, DrsProductPage,
  DrsResolutionAction, DrsResolutionImpact, DrsResolutionResult,
  DrsMarginInsight, DrsMarginRun, DrsMarginSourceStatus,
} from "@workspace/api-client-react";

// Gegenereerde DTO's (OpenAPI) zijn de bron van waarheid.
export type DailyError = DrsDailyError;
export type MappingResult = DrsMappingResult;
export type ConfirmResult = DrsDailyResult;
/** Stage/preview; na hervalidatie bevat hij ook de vergelijkingsvelden. */
export type DailyPreview = DrsDailyPreview & Partial<Pick<DrsDailyRevalidation, "previous_stage_id" | "previous_error_count" | "resolved_error_count">>;
export type Candidate = DrsProductCandidate;
export type UnresolvedItem = DrsUnresolvedRow;
export type UnresolvedPage = DrsUnresolvedPage;
export type ResolutionAction = DrsResolutionAction;
export type ResolutionPreview = DrsResolutionImpact;
export type ResolutionConfirm = DrsResolutionResult;
export type SourceStatus = DrsMarginSourceStatus;
export type MarginRun = DrsMarginRun;
export type MarginInsight = DrsMarginInsight;

export class ApiError extends Error { status?: number; constructor(m: string, s?: number) { super(m); this.status = s; } }

function detailMessage(body: any, text: string, status: number): string {
  const d = body?.detail;
  const msg = typeof d === "string" ? d : d?.message || (d ? JSON.stringify(d) : text) || `HTTP ${status}`;
  return msg.length > 500 ? msg.slice(0, 500) + "..." : msg;
}

/** Fetch met expliciete timeout (overschrijft de globale 15s alleen waar nodig). */
export async function drsFetch<T = any>(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
      credentials: "include",
      headers: { ...getAuthHeaders(), ...(init.headers || {}) } as HeadersInit,
    });
    const text = await res.text();
    let body: any = null;
    try { body = text ? JSON.parse(text) : null; } catch { /* geen json */ }
    if (!res.ok) throw new ApiError(detailMessage(body, text, res.status), res.status);
    return body as T;
  } catch (e: any) {
    if (e?.name === "TimeoutError" || e?.name === "AbortError") {
      throw new ApiError(`De server reageerde niet binnen ${Math.round(timeoutMs / 1000)} seconden. Controleer de status voordat u het opnieuw probeert.`);
    }
    throw e;
  }
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, {
    signal: AbortSignal.timeout(LONG_TIMEOUT_MS), credentials: "include", headers: getAuthHeaders() as HeadersInit,
  });
  if (!res.ok) {
    const text = await res.text();
    let body: any = null; try { body = JSON.parse(text); } catch { /* */ }
    throw new ApiError(detailMessage(body, text, res.status), res.status);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const enc = (v: string | number) => encodeURIComponent(String(v));
const stagePath = (id: string | number) => `/api/uploads/drs-daily/${enc(id)}`;

export const drsApi = {
  getStage: (id: string | number, shopId: number) => drsFetch<DailyPreview>(`${stagePath(id)}?shop_id=${shopId}`),
  preview: (fd: FormData) => drsFetch<DailyPreview>("/api/uploads/drs-daily/preview", { method: "POST", body: fd }, LONG_TIMEOUT_MS),
  confirm: (id: string | number, shopId: number, confirmMapping: boolean) =>
    drsFetch<ConfirmResult>(`${stagePath(id)}/confirm?shop_id=${shopId}`, json({ confirm_mapping: confirmMapping }), LONG_TIMEOUT_MS),
  confirmMappings: (id: string | number, shopId: number) =>
    drsFetch<MappingResult>(`${stagePath(id)}/confirm-mappings?shop_id=${shopId}`, json({ confirm_mapping: true }), LONG_TIMEOUT_MS),
  unresolved: (id: string | number, shopId: number, offset: number, limit: number, q = "") =>
    drsFetch<UnresolvedPage>(`${stagePath(id)}/unresolved?shop_id=${shopId}&offset=${offset}&limit=${limit}${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`),
  exportUnresolved: (id: string | number, shopId: number) =>
    downloadFile(`${stagePath(id)}/unresolved/export?shop_id=${shopId}`, `drs-onopgelost-${id}.csv`),
  products: (id: string | number, shopId: number, q: string, offset = 0, limit = 20) =>
    drsFetch<DrsProductPage>(`${stagePath(id)}/products?shop_id=${shopId}&q=${encodeURIComponent(q)}&offset=${offset}&limit=${limit}`),
  resolutionPreview: (id: string | number, shopId: number, actions: ResolutionAction[]) =>
    drsFetch<ResolutionPreview>(`${stagePath(id)}/resolution-preview?shop_id=${shopId}`, json({ actions }), LONG_TIMEOUT_MS),
  resolutionConfirm: (id: string | number, shopId: number, resolutionId: string) =>
    drsFetch<ResolutionConfirm>(`${stagePath(id)}/resolution-confirm?shop_id=${shopId}`, json({ resolution_id: resolutionId, confirm: true }), LONG_TIMEOUT_MS),
  revalidate: (id: string | number, shopId: number) =>
    drsFetch<DrsDailyRevalidation>(`${stagePath(id)}/revalidate?shop_id=${shopId}`, { method: "POST" }, LONG_TIMEOUT_MS),
  marginInsight: (shopId: number, filterQs: string) =>
    drsFetch<MarginInsight>(`/api/dashboard/margin-insight?shop_id=${shopId}${filterQs ? `&${filterQs}` : ""}`),
  marginRecalculate: (shopId: number) =>
    drsFetch<MarginRun>(`/api/dashboard/margin-recalculate?shop_id=${shopId}`, { method: "POST" }),
};

function json(body: unknown): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

/** Bedragen kunnen als decimale string binnenkomen (Decimal); ongeldig blijft null. */
export const toNum = (v: number | string | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
};
export const eur = (n: number) => new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(n);
export const num = (n: number) => new Intl.NumberFormat("nl-NL").format(n);
/** Null blijft zichtbaar als "onbekend", nooit als 0. */
export const eurOrDash = (v: number | string | null | undefined) => { const n = toNum(v); return n === null ? "Onbekend" : eur(n); };
export const dt = (s?: string | null) => (s ? new Date(s).toLocaleString("nl-NL") : "onbekend");

export type ImportPhase = "blocked" | "ready" | "mappings_only" | "confirmed" | "confirmed_missing";
export function importPhase(p: DailyPreview, resultMissing: boolean): ImportPhase {
  if (p.result || p.status === "confirmed") return p.result ? "confirmed" : resultMissing ? "confirmed_missing" : "confirmed";
  if (p.mapping_result) return "mappings_only";
  return p.status === "blocked" ? "blocked" : "ready";
}
