import { AlertTriangle } from "lucide-react";
import type { CostPriorityPreview, CostPrioritySelection } from "@workspace/api-client-react";
import { Badge } from "@/components/ui/badge";
import { formatEur, isMarket, reasonLabel, selectionChanged, summarizePreview, traceStatusLabel } from "@/lib/cost-priority/model";

function SelectionCell({ sel, testId }: { sel: CostPrioritySelection; testId: string }) {
  return (
    <div data-testid={testId}>
      {sel.source ? <span className="font-medium">{sel.source}</span> : <span className="text-destructive">Geen keuze</span>}
      <span className="ml-2 font-mono">{formatEur(sel.value)}</span>
      <div className="text-[11px] text-muted-foreground">{reasonLabel(sel.reason)}</div>
      {sel.fallback_warning && sel.reason !== "current_input_incomplete" && (
        <div className="text-[11px] text-amber-700">
          {isMarket(sel.source) ? "Marktterugval — geen geverifieerde historische kostprijs" : "Terugval op laatste prioriteit"}
        </div>
      )}
    </div>
  );
}

export function PreviewResults({ preview, stale }: { preview: CostPriorityPreview; stale: boolean }) {
  const sum = summarizePreview(preview);
  return (
    <div className={`rounded-lg border bg-card ${stale ? "opacity-60" : ""}`} data-testid="section-preview">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <h2 className="font-semibold">Preview-resultaat <span className="text-xs font-normal text-muted-foreground">({preview.input_kind === "workbook" ? "werkboek" : "handmatig"})</span></h2>
        <span className="text-xs text-muted-foreground" data-testid="text-preview-summary">
          {sum.total} regels · {sum.changed} anders dan huidig · {sum.fallbacks} terugval · {sum.rowErrors} met invoerfout
        </span>
      </div>
      {preview.errors.length > 0 && (
        <div className="space-y-1 border-b bg-destructive/5 px-4 py-2 text-xs text-destructive" data-testid="list-preview-errors">
          {preview.errors.map((e, i) => <div key={i} className="flex gap-1"><AlertTriangle className="h-3 w-3 shrink-0" />{e}</div>)}
        </div>
      )}
      {!preview.can_activate && (
        <div className="border-b px-4 py-2 text-xs text-destructive" data-testid="status-preview-blocked">Deze preview kan niet worden geactiveerd. Los de invoerfouten op en bereken opnieuw.</div>
      )}
      {preview.rows.length === 0 ? (
        <div className="p-6 text-center text-sm text-muted-foreground" data-testid="status-preview-no-rows">Geen regels in deze invoer.</div>
      ) : (
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-muted text-xs text-muted-foreground">
              <tr><th className="p-2 text-left">Regel</th><th className="p-2 text-left">Nieuw (concept)</th><th className="p-2 text-left">Huidig actief</th><th className="p-2 text-left">Afweging per prioriteit</th></tr>
            </thead>
            <tbody>
              {preview.rows.map(r => {
                const changed = selectionChanged(r.current, r.proposed);
                return (
                  <tr key={r.row_id} className={`border-t align-top ${changed ? "bg-amber-50 dark:bg-amber-950/20" : ""}`} data-testid={`row-preview-${r.row_id}`}>
                    <td className="p-2">
                      <div className="font-mono text-xs">{r.row_id}</div>
                      <div className="text-[11px] text-muted-foreground">{r.category || "(geen categorie)"}</div>
                      {changed && <Badge variant="outline" className="mt-1 border-amber-500 text-[10px] text-amber-700" data-testid={`badge-changed-${r.row_id}`}>Gewijzigd</Badge>}
                    </td>
                    <td className="p-2"><SelectionCell sel={r.proposed} testId={`text-proposed-${r.row_id}`} /></td>
                    <td className="p-2"><SelectionCell sel={r.current} testId={`text-current-${r.row_id}`} /></td>
                    <td className="p-2 text-xs" data-testid={`text-trace-${r.row_id}`}>
                      {r.proposed.trace.map(t => (
                        <div key={t.priority} className={t.status === "zero_skipped" ? "text-muted-foreground" : ""}>
                          Prio {t.priority} {t.source}: {formatEur(t.value)} — {traceStatusLabel(t.status)}
                        </div>
                      ))}
                      {r.errors.map((e, i) => <div key={i} className="text-destructive" data-testid={`text-row-error-${r.row_id}-${i}`}>{e}</div>)}
                      {r.warnings?.map((warning, i) => <div key={`warning-${i}`} className="text-amber-700" data-testid={`text-row-warning-${r.row_id}-${i}`}>{warning}</div>)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
