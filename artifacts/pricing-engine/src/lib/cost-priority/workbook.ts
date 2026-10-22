/**
 * Werkboek-preview. Eigen fetch met eigen 180s-signaal: de gegenereerde
 * client hanteert een globale 15s-timeout die grote uploads zou afbreken.
 * URL komt uit de gegenereerde Orval-helper.
 */
import { getPreviewCostPriorityWorkbookUrl } from "@workspace/api-client-react";
import type { CostPriorityPreview, CostPriorityRules } from "@workspace/api-client-react";
import { getAuthHeaders } from "@/lib/auth";

export const UPLOAD_TIMEOUT_MS = 180_000;
export const MAX_WORKBOOK_BYTES = 2 * 1024 * 1024;

export class WorkbookError extends Error {
  constructor(public status: number, public data: { detail?: unknown } | null, message: string) { super(message); }
}

export function workbookFileError(file: File | null): string | null {
  if (!file) return "Kies een .xlsx-werkboek.";
  if (!file.name.toLowerCase().endsWith(".xlsx")) return "Alleen .xlsx-werkboeken worden ondersteund.";
  if (file.size > MAX_WORKBOOK_BYTES) return "Werkboek is groter dan 2 MB.";
  return null;
}

export async function previewWorkbook(args: {
  shopId: number; file: File; baseRevision: number; rules: CostPriorityRules; signal?: AbortSignal;
}): Promise<CostPriorityPreview> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(new DOMException("Timeout", "TimeoutError")), UPLOAD_TIMEOUT_MS);
  const onOuter = () => ctrl.abort(args.signal?.reason);
  args.signal?.addEventListener("abort", onOuter, { once: true });
  try {
    const fd = new FormData();
    fd.append("draft", JSON.stringify({ base_revision: args.baseRevision, rules: args.rules }));
    fd.append("file", args.file);
    let res: Response;
    try {
      res = await fetch(getPreviewCostPriorityWorkbookUrl(args.shopId), {
        method: "POST", body: fd, headers: getAuthHeaders(), credentials: "include", signal: ctrl.signal,
      });
    } catch (e) {
      if (ctrl.signal.reason instanceof DOMException && ctrl.signal.reason.name === "TimeoutError") {
        throw new DOMException("Timeout", "TimeoutError");
      }
      throw e;
    }
    if (!res.ok) {
      let data: { detail?: unknown } | null = null;
      try { data = await res.json(); } catch { /* geen json */ }
      throw new WorkbookError(res.status, data, typeof data?.detail === "string" ? data.detail : `Fout ${res.status}`);
    }
    return (await res.json()) as CostPriorityPreview;
  } finally {
    clearTimeout(timer);
    args.signal?.removeEventListener("abort", onOuter);
  }
}
