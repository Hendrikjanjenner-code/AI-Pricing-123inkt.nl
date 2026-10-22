import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Calculator } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cmApi, cmKeys, CmError, dash, fmtDate } from "@/lib/channelmanager/api";
import { parseBasis, parseCalculation, parseExport, parseRun } from "@/lib/channelmanager/model";
import type { CalcData, CalcRow, Overview, Snapshot } from "@/lib/channelmanager/model";
import { useCmAction } from "@/hooks/use-channelmanager";
import type { CmScope } from "@/hooks/use-channelmanager";
import { ErrorBox, Fact, Facts, Field, HistoryList, NotesButton, RecordLoader, RowsTable, Section, StatusBadge, inputCls } from "./common";
import type { Col } from "./common";

const SOURCE_NL = { sku: "SKU-uitzondering", category: "Categorie-uitzondering", shop: "Shopregel" } as const;
export const CALC_COLUMNS: Col<CalcRow>[] = [
  { label: "SKU", cell: r => r.sku, mono: true }, { label: "Categorie", cell: r => dash(r.category) },
  { label: "Basis", cell: r => r.base_price, mono: true }, { label: "Kost", cell: r => dash(r.cost), mono: true },
  { label: "Regelbron", cell: r => SOURCE_NL[r.rule_source] },
  { label: "Regel", cell: r => `${r.rule.kind === "fixed" ? "vast" : "%"} ${r.rule.value}`, mono: true },
  { label: "Doelprijs", cell: r => dash(r.target_price), mono: true },
  { label: "Huidig (bestemming)", cell: r => dash(r.current_price), mono: true },
  { label: "Huidig bron (alleen herkomst)", cell: r => r.source_current_price === undefined ? "—" : dash(r.source_current_price), mono: true },
  { label: "Delta t.o.v. huidig", cell: r => dash(r.current_delta), mono: true },
  { label: "Nettomarge (fractie)", cell: r => dash(r.net_margin), mono: true },
  { label: "Blokkades", cell: r => r.errors.length ? <span className="text-destructive">{r.errors.join("; ")}</span> : "—" },
];

/** Een berekening is "verouderd" als de huidige config of actieve basis niet meer overeenkomt. */
export function isStale(d: CalcData, currentConfigId: number | null, currentBasisId: number | null | undefined): boolean {
  return d.config_id !== currentConfigId || (currentBasisId !== undefined && d.basis_id !== currentBasisId);
}

export function CalcPanel({ scope, overview, shops, canPropose, canApprove, canExport, onExported }: {
  scope: CmScope; overview: Overview; shops: { id: number; name: string }[]; canPropose: boolean; canApprove: boolean; canExport: boolean; onExported: () => void;
}) {
  const [sourceShop, setSourceShop] = useState<number>(scope.shopId);
  const [selected, setSelected] = useState<number | null>(null);
  const { run, busy, lastError } = useCmAction(scope);
  useEffect(() => { setSourceShop(scope.shopId); setSelected(null); }, [scope.scopeToken, scope.shopId]);

  const foreign = sourceShop !== scope.shopId;
  const srcQ = useQuery({
    queryKey: cmKeys.sourceOverview(scope.userKey, scope.shopId, sourceShop),
    queryFn: ({ signal }) => cmApi.overview(sourceShop, signal),
    enabled: foreign, retry: 1,
  });
  const srcBasisSnap: Snapshot | null = foreign ? srcQ.data?.basis ?? null : overview.basis;
  const srcBasis = srcBasisSnap ? parseBasis(srcBasisSnap) : null;
  const configId = overview.config?.id ?? null;
  const stale409 = lastError?.error instanceof CmError && lastError.error.status === 409;

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <Section title="Proefberekening starten">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Field label="Bronwinkel basis" hint="Delen tussen winkels vereist toegang tot beide">
              <select className={inputCls} value={sourceShop} onChange={e => setSourceShop(Number(e.target.value))} data-testid="select-source-shop">
                {shops.map(s => <option key={s.id} value={s.id}>{s.name}{s.id === scope.shopId ? " (deze winkel)" : ""}</option>)}
              </select>
            </Field>
            <div className="text-xs space-y-1 md:col-span-2" data-testid="text-source-basis">
              <div className="text-muted-foreground uppercase tracking-wide font-medium">Actieve goedgekeurde basis</div>
              {foreign && srcQ.isLoading ? <Skeleton className="h-8" /> : srcBasis ? (
                <div>#{srcBasis.snap.id} r{srcBasis.snap.revision} · {srcBasis.data.rows.length} rijen · {srcBasis.data.currency} {srcBasis.data.price_basis} · {fmtDate(srcBasis.snap.created_at)}</div>
              ) : <div className="text-amber-700">Geen goedgekeurde basis in deze bronwinkel.</div>}
            </div>
          </div>
          {srcQ.isError && <ErrorBox error={srcQ.error} onRetry={() => srcQ.refetch()} />}
          <div className="flex items-center gap-3">
            <Button disabled={!canPropose || !srcBasis || !overview.config || !!busy} data-testid="button-calculate"
              onClick={() => { if (srcBasis) void run("calc", () => cmApi.calculate(scope.shopId, { source_shop_id: sourceShop, basis_id: srcBasis.snap.id }), "Berekening klaar").then(s => { if (s) setSelected(parseCalculation(s).snap.id); }); }}>
              <Calculator className="h-4 w-4 mr-1" />{busy === "calc" ? "Rekenen…" : "Bereken"}
            </Button>
            {!overview.config && <span className="text-xs text-amber-700">Sla eerst een configuratie op.</span>}
            {!canPropose && <span className="text-xs text-muted-foreground">Vereist recht pricing.propose.</span>}
          </div>
          {foreign && <p className="text-xs text-amber-700">Basis uit een andere winkel: huidige prijzen van de bron worden niet als huidige prijs van deze winkel gebruikt. Delta en wijzigingsgrenzen kunnen daardoor blokkeren.</p>}
          <p className="text-xs text-muted-foreground">De server rekent met de actieve configuratierevisie; deze pagina rekent niet zelf. Valuta-mismatch tussen basis en configuratie blokkeert de berekening.</p>
          {lastError?.name === "calc" && <ErrorBox error={lastError.error} />}
        </Section>

        {stale409 && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm flex gap-2" data-testid="status-stale"><AlertTriangle className="h-4 w-4 text-destructive mt-0.5" />De server weigerde: configuratie of basis is gewijzigd of de status klopt niet meer. Bereken opnieuw.</div>
        )}

        {selected !== null && (
          <Section title="Resultaat per rij">
            <RecordLoader scope={scope} id={selected} parse={parseCalculation} onClose={() => setSelected(null)}>
              {({ snap, data }) => {
                const stale = isStale(data, configId, data.source_shop_id === scope.shopId ? overview.basis?.id ?? null
                  : data.source_shop_id === sourceShop && srcQ.isSuccess ? srcBasis?.snap.id ?? null : undefined);
                return (
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-3 text-sm">
                      <StatusBadge status={snap.status} /><span>{data.rows.length} rijen</span>
                      {data.blocked_rows > 0 && <span className="text-destructive" data-testid="text-blocked-count">{data.blocked_rows} geblokkeerd</span>}
                      {stale && <span className="text-destructive text-xs" data-testid="text-calc-stale">Verouderd t.o.v. huidige configuratie/basis — herbereken</span>}
                    </div>
                    <Facts>
                      <Fact label="Bronwinkel">{shops.find(s => s.id === data.source_shop_id)?.name ?? data.source_shop_id}</Fact>
                      <Fact label="Basis">#{data.basis_id}</Fact>
                      <Fact label="Configuratie">#{data.config_id}</Fact>
                      <Fact label="Regel shop">{data.config.rule.kind} {data.config.rule.value}</Fact>
                    </Facts>
                    {data.current_price_note && <p className="text-xs text-muted-foreground" data-testid="text-current-price-note">Huidige prijzen: {data.current_price_note}</p>}
                    {data.cost_provenance && <p className="text-xs text-muted-foreground" data-testid="text-cost-provenance">Kosten: {data.cost_provenance.provenance === "PriceShape_unverified" ? "PriceShape (onbevestigd)" : "handmatige CSV/invoer"}, netto, uit basis #{data.cost_provenance.basis_id}. {data.cost_provenance.note}</p>}
                    {data.approval && <p className="text-xs text-emerald-700">Goedgekeurd door {data.approval.by} op {fmtDate(data.approval.at)}: {data.approval.notes}</p>}
                    <RowsTable testid="table-calc" rows={data.rows} columns={CALC_COLUMNS} isBad={r => r.errors.length > 0} />
                    <div className="space-y-1">
                      <div className="text-xs font-semibold">Exportvoorbeeld (eerste 5 rijen, nog geen export)</div>
                      {data.csv_preview !== null
                        ? <pre className="max-h-40 overflow-auto rounded border bg-muted/30 p-2 text-[11px]" data-testid="text-calc-csv-preview">{data.csv_preview}</pre>
                        : <p className="text-xs text-muted-foreground">Geen voorbeeld: berekening bevat geblokkeerde rijen.</p>}
                      <p className="text-[11px] font-mono text-muted-foreground">Kolommen: {Object.entries(data.export_schema).map(([h, f]) => `${h}=${f}`).join(", ")}</p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      {snap.status === "preview" && (
                        <NotesButton label="Berekening goedkeuren" testid="button-approve-calc" busy={busy === "approve"} disabled={!canApprove || data.blocked_rows > 0 || stale}
                          reason={!canApprove ? "Vereist recht pricing.approve." : data.blocked_rows ? "Geblokkeerde rijen voorkomen goedkeuring." : stale ? "Verouderd — herbereken." : null}
                          onSubmit={n => void run("approve", () => cmApi.approveCalc(scope.shopId, snap.id, { notes: n }), "Berekening goedgekeurd")} />
                      )}
                      {snap.status === "approved" && (
                        <NotesButton label="Exportversie maken" testid="button-create-export" variant="secondary" busy={busy === "export"} disabled={!canExport || stale}
                          reason={!canExport ? "Vereist recht pricing.approve." : stale ? "Verouderd — herbereken en keur opnieuw goed." : "Idempotent: per berekening één onveranderlijke export."}
                          onSubmit={n => void run("export", () => cmApi.exportCalc(scope.shopId, snap.id, { notes: n }), "Exportversie beschikbaar").then(x => { if (x) { parseExport(x); onExported(); } })} />
                      )}
                    </div>
                    {lastError && (lastError.name === "approve" || lastError.name === "export") && <ErrorBox error={lastError.error} />}
                  </div>
                );
              }}
            </RecordLoader>
          </Section>
        )}
      </div>
      <div className="space-y-4">
        <HistoryList scope={scope} kind="calculation" title="Berekeningen" selectedId={selected} onSelect={s => setSelected(s.id)} />
        <RunHistory scope={scope} onOpenCalc={setSelected} />
      </div>
    </div>
  );
}

function RunHistory({ scope, onOpenCalc }: { scope: CmScope; onOpenCalc: (id: number) => void }) {
  const [view, setView] = useState<number | null>(null);
  return (
    <>
      <HistoryList scope={scope} kind="run" title="Preview-runs (planner en handmatig)" selectedId={view} onSelect={s => setView(s.id)} />
      {view !== null && (
        <Section title="Run">
          <RecordLoader scope={scope} id={view} parse={parseRun} onClose={() => setView(null)}>
            {({ snap, data }) => (
              <div className="space-y-2 text-xs">
                <StatusBadge status={snap.status} />
                <div>Start {fmtDate(data.started_at)} · einde {fmtDate(data.finished_at)} · bron winkel {data.source_shop_id}</div>
                {data.error && <div className="text-destructive" data-testid="text-run-detail-error">{data.error}</div>}
                {data.calculation_id !== undefined && <Button size="sm" variant="outline" onClick={() => onOpenCalc(data.calculation_id as number)} data-testid="button-open-run-calc">Open berekening #{data.calculation_id}</Button>}
              </div>
            )}
          </RecordLoader>
        </Section>
      )}
    </>
  );
}
