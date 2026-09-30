import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp, History, Database, RotateCcw, AlertTriangle } from "lucide-react";
import { useMarginInsight } from "@/hooks/use-margin-insight";
import { eurOrDash, num, dt, type MarginInsight } from "@/lib/drs-daily-api";
import { RecalcControl } from "./recalc-control";

const SOURCE_LABEL: Record<MarginInsight["source"]["status"], string> = {
  none: "Geen DRS-dagimport",
  blocked: "Alleen geblokkeerde preview",
  preview: "Preview, niet bevestigd",
  mappings_only: "Alleen koppelingen vastgelegd",
  confirmed: "Verkoop verwerkt",
};
const EXPECTED_LABEL: Record<MarginInsight["expected"]["status"], [string, string]> = {
  fresh: ["Actueel", "bg-emerald-50 text-emerald-700 border-emerald-200"],
  partial: ["Gedeeltelijke dekking", "bg-amber-50 text-amber-800 border-amber-200"],
  stale: ["Verouderd", "bg-amber-50 text-amber-800 border-amber-200"],
  unavailable: ["Niet beschikbaar", "bg-muted text-muted-foreground"],
};
const n = (v?: number | null) => (v === null || v === undefined ? "onbekend" : num(v));

function Stat({ label, value, id, tone }: { label: string; value: string; id: string; tone?: string }) {
  return (
    <div className="rounded-md border p-3">
      <div className={`text-lg font-semibold tabular-nums ${tone ?? ""}`} data-testid={`text-margin-${id}`}>{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export function MarginInsightCard({ filterQs = "" }: { filterQs?: string }) {
  const { query, recalculate, starting, shop, shopsQuery } = useMarginInsight(filterQs);
  const d = query.data;

  return (
    <Card className="col-span-full" data-testid="card-margin-insight">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex flex-wrap items-center gap-2">
          <Database className="h-5 w-5 text-primary" />Van DRS-verkoop naar marge
          {shop && <Badge variant="outline" className="text-xs" data-testid="badge-margin-shop">{shop.name}</Badge>}
          {d && <Badge variant="outline" className="text-xs" data-testid="status-margin-source">{SOURCE_LABEL[d.source.status]}</Badge>}
        </CardTitle>
        <CardDescription>Verwachte uplift uit prijsadviezen en gerealiseerde historische marge staan bewust los van elkaar.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {(query.isLoading || shopsQuery.isLoading) && <div className="grid gap-3 md:grid-cols-2"><Skeleton className="h-40" /><Skeleton className="h-40" /></div>}
        {!shop && !shopsQuery.isLoading && <p className="text-sm text-amber-700">Geen geautoriseerde winkel beschikbaar.</p>}
        {query.isError && (
          <div className="rounded-md border border-red-200 bg-red-50/50 p-3 text-sm text-red-800 flex flex-wrap items-center gap-2" data-testid="text-margin-error">
            <AlertTriangle className="h-4 w-4" />Marge-inzicht laden mislukt: {(query.error as Error).message}
            <Button size="sm" variant="outline" onClick={() => query.refetch()} data-testid="button-margin-retry"><RotateCcw className="mr-1 h-4 w-4" />Opnieuw</Button>
          </div>
        )}
        {d && (
          <>
            <div className="text-xs text-muted-foreground" data-testid="text-margin-source">
              Bron: {d.source.period_start && d.source.period_end ? `${d.source.period_start} t/m ${d.source.period_end}` : "geen bevestigde periode"}
              {d.source.confirmed_at && ` · bevestigd ${dt(d.source.confirmed_at)}`}
              {d.source.sales_rows !== null && d.source.sales_rows !== undefined && ` · ${num(d.source.sales_rows)} verkoopregels`}
              {d.source.latest_attempt_status && d.source.latest_attempt_status !== d.source.status && ` · nieuwste poging: ${d.source.latest_attempt_status} (wist bevestigde verkoop niet)`}
            </div>
            <RecalcControl insight={d} starting={starting} onRecalculate={recalculate} shopName={shop?.name} />

            <div className="grid gap-4 lg:grid-cols-2">
              <section className="rounded-lg border p-4 space-y-3" data-testid="section-expected">
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-emerald-600" />
                  <h3 className="text-sm font-semibold">Verwachte margeverbetering</h3>
                  <Badge className={`text-xs ${EXPECTED_LABEL[d.expected.status][1]}`} data-testid="status-expected">{EXPECTED_LABEL[d.expected.status][0]}</Badge>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Stat id="uplift" label={`Som advieseffecten per ${d.expected.horizon_days ?? 1} dag`} value={eurOrDash(d.expected.margin_uplift)} tone={d.expected.margin_uplift === null ? "text-muted-foreground" : "text-emerald-700"} />
                  <Stat id="expected-margin" label="Verwachte marge" value={eurOrDash(d.expected.margin)} />
                </div>
                <ul className="text-xs text-muted-foreground space-y-0.5">
                  <li>Volumeperiode: {d.expected.volume_period_start && d.expected.volume_period_end ? `${d.expected.volume_period_start} t/m ${d.expected.volume_period_end} (${n(d.expected.volume_days)} dagen)` : "onbekend"}</li>
                  <li>Dekking: {n(d.expected.covered_skus)} van {n(d.expected.eligible_skus)} artikelen</li>
                  <li>Zonder volume: {n(d.expected.missing_volume_skus)} · zonder kosten: {n(d.expected.missing_cost_skus)} · menselijk besluit behouden: {n(d.expected.preserved_decision_skus)}</li>
                </ul>
                {d.expected.margin_uplift === null && <p className="text-xs text-amber-700">Geen bedrag: volumes, kosten of actuele adviezen ontbreken. Dit is niet hetzelfde als nul.</p>}
                {d.expected.status === "stale" && <p className="text-xs text-amber-700">Adviezen zijn niet met de nieuwste bevestigde verkoop berekend; start een herberekening.</p>}
                {!!d.expected.assumptions?.length && <ul className="list-disc pl-4 text-xs text-muted-foreground">{d.expected.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>}
              </section>

              <section className="rounded-lg border p-4 space-y-3" data-testid="section-actual">
                <div className="flex items-center gap-2">
                  <History className="h-4 w-4 text-primary" />
                  <h3 className="text-sm font-semibold">Gerealiseerde marge (historisch)</h3>
                  <Badge variant="outline" className={`text-xs ${d.actual.status === "complete" ? "text-emerald-700" : "text-amber-700"}`} data-testid="status-actual">{d.actual.status === "complete" ? "Kosten volledig" : "Kosten onvolledig"}</Badge>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Stat id="actual-revenue" label="Omzet excl. btw" value={eurOrDash(d.actual.revenue)} />
                  <Stat id="actual-margin" label="Marge periode" value={eurOrDash(d.actual.margin)} tone={d.actual.margin === null ? "text-muted-foreground" : ""} />
                  <Stat id="comparison-margin" label="Marge vergelijkingsperiode" value={eurOrDash(d.actual.comparison_margin)} tone={d.actual.comparison_margin === null ? "text-muted-foreground" : ""} />
                  <Stat id="margin-change" label="Verschil" value={eurOrDash(d.actual.margin_change)}
                    tone={d.actual.margin_change === null ? "text-muted-foreground" : d.actual.margin_change >= 0 ? "text-emerald-700" : "text-red-700"} />
                </div>
                <ul className="text-xs text-muted-foreground space-y-0.5">
                  <li>Periode: {d.actual.period_start ?? "?"} t/m {d.actual.period_end ?? "?"}</li>
                  <li>Vergelijkingsbasis: {d.actual.comparison_start ?? "?"} t/m {d.actual.comparison_end ?? "?"}</li>
                  <li>Verkoopregels: {n(d.actual.sales_rows)} · zonder historische kostprijs: {n(d.actual.missing_cost_rows)}</li>
                  <li>Vergelijkingsperiode: {n(d.actual.comparison_sales_rows)} regels · zonder historische kostprijs: {n(d.actual.comparison_missing_cost_rows)}</li>
                </ul>
                {(d.actual.status !== "complete" || d.actual.margin === null || d.actual.comparison_margin === null) && (
                  <p className="text-xs text-amber-700" data-testid="text-actual-limitation">
                    {d.actual.explanation || "Historische kostprijzen ontbreken; de huidige inkoopprijs wordt niet als historische waarheid gebruikt."}
                  </p>
                )}
              </section>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
