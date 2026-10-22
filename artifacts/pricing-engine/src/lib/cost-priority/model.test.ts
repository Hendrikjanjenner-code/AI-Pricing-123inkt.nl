import { describe, it, expect } from "vitest";
import type { CostPriorityConfiguration, CostPriorityPreview } from "@workspace/api-client-react";
import {
  excelDefaultRules, orderForCategory, setCustomSource, removeCustomSource, addCategoryOverride,
  removeCategoryOverride, resetToExcelDefault, withOrder, moveItem, previewFingerprint, rulesEqual,
  toScenarioRows, manualRowsError, summarizePreview, traceStatusLabel, reasonLabel, formatEur,
  describeApiError, sourcesOf, MARKET,
} from "./model";

// Momentopname van een echte GET-respons (revision 0 = impliciete Excel-default).
const config: CostPriorityConfiguration = {
  shop_id: 3, revision: 0, can_edit: true, scope: "configuration_only",
  sources: ["Stockprice", "ABCLev", "AB", "123inkt.nl Marktprijs"],
  rules: { print: ["Stockprice", "ABCLev", "AB", "123inkt.nl Marktprijs"], other: ["Stockprice", "AB", "ABCLev", "123inkt.nl Marktprijs"], custom_source: null, categories: {} },
};

// Momentopname van een preview-respons volgens services/cost_priority.select().
const preview: CostPriorityPreview = {
  preview_token: "tok", shop_id: 3, base_revision: 0, input_kind: "manual", errors: [], can_activate: true,
  expires_at: "2025-01-01T10:30:00Z", rules: config.rules,
  rows: [
    { row_id: "A1", category: "print", values: { Stockprice: "0", ABCLev: "4.10", AB: "3.90", [MARKET]: "6" },
      current: { source: "ABCLev", value: "4.10", reason: "first_nonzero", fallback_warning: false, trace: [
        { priority: 1, source: "Stockprice", value: "0", status: "zero_skipped" }, { priority: 2, source: "ABCLev", value: "4.10", status: "first_nonzero" }] },
      proposed: { source: "AB", value: "3.90", reason: "first_nonzero", fallback_warning: false, trace: [] }, errors: [] },
    { row_id: "B2", category: "Kantoor", values: { Stockprice: "0", ABCLev: "0", AB: "0", [MARKET]: "0" },
      current: { source: MARKET, value: "0", reason: "final_fallback", fallback_warning: true, trace: [] },
      proposed: { source: MARKET, value: "0", reason: "final_fallback", fallback_warning: true, trace: [] }, errors: [] },
    { row_id: "C3", category: "Kantoor", values: { Stockprice: null, ABCLev: "1", AB: "1", [MARKET]: "1" },
      current: { source: null, value: null, reason: "input_error", fallback_warning: false, trace: [] },
      proposed: { source: null, value: null, reason: "input_error", fallback_warning: false, trace: [] },
      errors: ["Stockprice: missing; supply explicit zero if unavailable"] },
  ],
};

describe("cost-priority model", () => {
  it("Excel-default exact", () => {
    expect(rulesEqual(excelDefaultRules(), config.rules)).toBe(true);
  });
  it("order_for: override exact, Print case-insensitive", () => {
    let r = addCategoryOverride(config.rules, "Toner");
    r = withOrder(r, { kind: "category", name: "Toner" }, moveItem(r.categories.Toner, 3, 0));
    expect(orderForCategory(r, "PRINT")).toEqual(config.rules.print);
    expect(orderForCategory(r, "Toner")[0]).toBe(MARKET);
    expect(orderForCategory(r, "toner")).toEqual(config.rules.other);
    expect(removeCategoryOverride(r, "Toner").categories).toEqual({});
  });
  it("vijfde bron toevoegen, hernoemen, verwijderen", () => {
    let r = setCustomSource(config.rules, "Contractprijs");
    expect(r.print).toHaveLength(5);
    expect(r.print[4]).toBe("Contractprijs");
    r = setCustomSource(r, "Contract 2025");
    expect(r.other[4]).toBe("Contract 2025");
    expect(sourcesOf(r)).toHaveLength(5);
    expect(resetToExcelDefault(r).print).toEqual([...config.rules.print, "Contract 2025"]);
    expect(removeCustomSource(r)).toEqual(config.rules);
  });
  it("handmatige rijen: leeg = null, komma = punt, 0 blijft 0", () => {
    const rows = toScenarioRows([{ id: "x", category: "Print", values: { Stockprice: "0", AB: "3,5" } }], sourcesOf(config.rules));
    expect(rows[0].values).toEqual({ Stockprice: "0", ABCLev: null, AB: "3.5", [MARKET]: null });
    expect(manualRowsError([{ id: "a", category: "", values: {} }, { id: "a", category: "", values: {} }])).toMatch(/uniek/);
  });
  it("fingerprint verandert bij elke wijziging", () => {
    const b = { userKey: "u", shopId: 3, revision: 0, rules: config.rules, inputSig: "m" };
    const f = previewFingerprint(b);
    expect(previewFingerprint({ ...b, shopId: 4 })).not.toBe(f);
    expect(previewFingerprint({ ...b, revision: 1 })).not.toBe(f);
    expect(previewFingerprint({ ...b, inputSig: "n" })).not.toBe(f);
    expect(previewFingerprint({ ...b, rules: setCustomSource(b.rules, "X") })).not.toBe(f);
  });
  it("preview-samenvatting en labels", () => {
    expect(summarizePreview(preview)).toEqual({ total: 3, changed: 1, rowErrors: 1, fallbacks: 1, inputErrors: 1 });
    expect(traceStatusLabel("zero_skipped")).toMatch(/overgeslagen/);
    expect(reasonLabel("final_fallback")).toMatch(/ook bij 0/);
    expect(formatEur("3.90")).toContain("3,90");
    expect(formatEur(null)).toBe("—");
  });
  it("API-fouten", () => {
    expect(describeApiError({ status: 409, data: { detail: "stale" } }).kind).toBe("conflict");
    expect(describeApiError({ status: 422, data: { detail: [{ msg: "x" }] } })).toEqual({ kind: "validation", message: "x" });
    expect(describeApiError({ name: "TimeoutError" }).kind).toBe("timeout");
  });
});
