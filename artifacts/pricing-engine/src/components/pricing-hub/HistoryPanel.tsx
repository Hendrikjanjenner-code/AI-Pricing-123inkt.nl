import { History } from "lucide-react";
import type { CostPriorityVersion } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function HistoryPanel({ versions, isLoading, isError, onRetry }: {
  versions: CostPriorityVersion[] | undefined; isLoading: boolean; isError: boolean; onRetry: () => void;
}) {
  return (
    <div className="rounded-lg border bg-card">
      <div className="flex items-center gap-2 border-b px-4 py-3"><History className="h-4 w-4" /><h2 className="font-semibold">Versiehistorie</h2></div>
      <div className="p-3 text-sm" data-testid="list-history">
        {isLoading && <Skeleton className="h-16 w-full" />}
        {isError && <div className="flex items-center gap-2 text-destructive" data-testid="status-history-error">Historie laden mislukt <Button size="sm" variant="outline" onClick={onRetry} data-testid="button-retry-history">Opnieuw</Button></div>}
        {versions && versions.length === 0 && <div className="text-muted-foreground" data-testid="status-history-empty">Nog geen geactiveerde versies — de Excel-default is van kracht.</div>}
        {versions?.map(v => (
          <details key={v.version_id} className="border-b py-2 last:border-0" data-testid={`row-history-${v.version_id}`}>
            <summary className="cursor-pointer">
              <span className="font-mono text-xs font-semibold">Revisie {v.revision}</span>
              <span className="ml-2 text-xs text-muted-foreground">{new Date(v.activated_at).toLocaleString("nl-NL")} · {v.activated_by} · {v.input_kind === "workbook" ? "werkboek" : "handmatig"} · {v.row_count} regels</span>
            </summary>
            <div className="mt-1 space-y-0.5 pl-2 text-xs">
              <div>Print: {v.rules.print.join(" → ")}</div>
              <div>Overige: {v.rules.other.join(" → ")}</div>
              {Object.entries(v.rules.categories).map(([k, o]) => <div key={k}>{k}: {o.join(" → ")}</div>)}
              {v.rules.custom_source && <div className="text-muted-foreground">Vijfde bron: {v.rules.custom_source}</div>}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}
