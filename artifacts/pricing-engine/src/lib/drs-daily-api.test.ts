import { describe, expect, it } from "vitest";
import { eurOrDash, toNum, importPhase, type DailyPreview } from "./drs-daily-api";

const base = { status: "blocked", result: null, mapping_result: null } as unknown as DailyPreview;

describe("drs-daily-api helpers", () => {
  it("toont onbekend voor null, geen nul", () => {
    expect(eurOrDash(null)).toBe("Onbekend");
    expect(toNum("12.50")).toBe(12.5);
    expect(toNum("abc")).toBeNull();
  });
  it("onderscheidt preview, mapping-only en verwerkt", () => {
    expect(importPhase(base, false)).toBe("blocked");
    expect(importPhase({ ...base, mapping_result: { stage_id: "1", mapped: 3, sales_written: 0, unresolved: 2 } }, false)).toBe("mappings_only");
    expect(importPhase({ ...base, status: "confirmed" } as DailyPreview, true)).toBe("confirmed_missing");
  });
});
