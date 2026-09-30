import { describe, expect, it } from "vitest";
import { verwachteMargeverbetering, verwachteOmzetImpact, verwachteMargeImpact } from "./dashboard-kpis";

describe("verwachteMargeverbetering", () => {
  it("gebruikt total_margin_uplift, niet estimated_margin_impact", () => {
    const summary = { total_margin_uplift: 1234.56, estimated_margin_impact: 98765.43 };
    expect(verwachteMargeverbetering(summary)).toBe(1234.56);
  });

  it("geeft null (onbekend) bij ontbrekende uplift, nooit een misleidende nul", () => {
    expect(verwachteMargeverbetering({ total_margin_uplift: null, estimated_margin_impact: 5000 })).toBeNull();
    expect(verwachteMargeverbetering(undefined)).toBeNull();
  });

  it("behoudt een echte nul", () => {
    expect(verwachteMargeverbetering({ total_margin_uplift: 0 })).toBe(0);
  });
});

describe("nullable monetaire samenvatting", () => {
  it("geeft null voor ontbrekende omzet/marge", () => {
    expect(verwachteOmzetImpact({ estimated_revenue_impact: null })).toBeNull();
    expect(verwachteMargeImpact(undefined)).toBeNull();
    expect(verwachteMargeImpact({ estimated_margin_impact: 12.5 })).toBe(12.5);
  });
});
