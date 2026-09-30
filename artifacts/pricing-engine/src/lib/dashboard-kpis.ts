/**
 * Selectors voor de dashboard-KPI-kaarten.
 *
 * De kaart "Verwachte margeverbetering" toont ALTIJD `total_margin_uplift`
 * (som van expected_margin_uplift), nooit `estimated_margin_impact`.
 * Ontbrekende data levert `null` op (weergave "Onbekend"), nooit een
 * misleidende nul.
 */
export interface DashboardSummaryLike {
  total_margin_uplift?: number | null;
  estimated_margin_impact?: number | null;
}

export function verwachteMargeverbetering(
  summary: DashboardSummaryLike | null | undefined,
): number | null {
  const v = summary?.total_margin_uplift;
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

const nullableEur = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

export interface DashboardMoneyLike extends DashboardSummaryLike { estimated_revenue_impact?: number | null }
/** Verwachte omzet-/marge-impact: nullable, nooit stil 0. */
export const verwachteOmzetImpact = (s: DashboardMoneyLike | null | undefined) => nullableEur(s?.estimated_revenue_impact);
export const verwachteMargeImpact = (s: DashboardMoneyLike | null | undefined) => nullableEur(s?.estimated_margin_impact);
