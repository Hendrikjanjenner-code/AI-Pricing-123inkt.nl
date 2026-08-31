/**
 * Selectors voor de dashboard-KPI-kaarten.
 *
 * De samenvattings-API levert zowel `total_margin_uplift` (som van
 * `expected_margin_uplift` per advies — de verwachte margeVERBETERING) als
 * `estimated_margin_impact` (som van `expected_margin` — de verwachte totale
 * marge). De kaart "Verwachte margeverbetering" moet ALTIJD de uplift tonen;
 * deze selector legt die koppeling vast zodat een regressietest het verschil
 * bewaakt (zie dashboard-kpis.test.ts).
 */
export interface DashboardSummaryLike {
  total_margin_uplift?: number | null;
  estimated_margin_impact?: number | null;
}

export function verwachteMargeverbetering(
  summary: DashboardSummaryLike | null | undefined,
): number {
  return summary?.total_margin_uplift ?? 0;
}
