import { describe, expect, it } from "vitest";
import { verwachteMargeverbetering } from "./dashboard-kpis";

describe("verwachteMargeverbetering", () => {
  it("gebruikt total_margin_uplift, niet estimated_margin_impact", () => {
    // Bewust uiteenlopende waarden: een verkeerde koppeling faalt zichtbaar.
    const summary = {
      total_margin_uplift: 1234.56,
      estimated_margin_impact: 98765.43,
    };
    expect(verwachteMargeverbetering(summary)).toBe(1234.56);
  });

  it("toont €0 wanneer er geen uplift is, ook al is er wel totale marge", () => {
    expect(
      verwachteMargeverbetering({
        total_margin_uplift: null,
        estimated_margin_impact: 5000,
      }),
    ).toBe(0);
    expect(verwachteMargeverbetering(undefined)).toBe(0);
  });
});
