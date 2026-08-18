import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle2, XCircle, Clock, Play, Tag } from "lucide-react";
import { useShopId } from "@/hooks/use-shop-id";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  completed: { label: "Voltooid",   color: "text-emerald-600 bg-emerald-50 border-emerald-200", icon: CheckCircle2 },
  running:   { label: "Bezig",     color: "text-blue-600 bg-blue-50 border-blue-200",           icon: Clock },
  failed:    { label: "Mislukt",   color: "text-red-600 bg-red-50 border-red-200",               icon: XCircle },
};

function formatDuration(start: string, end: string) {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function CompetitionDiscoveryLog() {
  const shopId = useShopId();

  const { data, isLoading } = useQuery({
    queryKey: ["competition-discovery-log", shopId],
    queryFn: () => apiFetch(`/api/competition/discovery-log?${shopId !== undefined ? `shop_id=${shopId}&` : ""}page_size=20`),
  });

  // Discovery-queue statistieken per run
  const { data: queueData } = useQuery({
    queryKey: ["competition-discovery-queue-all", shopId],
    queryFn: () => apiFetch(`/api/competition/discovery?${shopId !== undefined ? `shop_id=${shopId}&` : ""}page_size=200`),
  });

  const runs = data?.items || [];
  const queueItems = queueData?.items || [];

  // Groepeer queue-items per run_id
  const queueByRun: Record<string, any[]> = {};
  for (const item of queueItems) {
    if (item.run_id) {
      queueByRun[item.run_id] = queueByRun[item.run_id] || [];
      queueByRun[item.run_id].push(item);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Discovery Log</h1>
        <p className="text-muted-foreground mt-1">Historie van alle competitor discovery-runs — parameters, resultaten en statistieken per run.</p>
      </div>

      {/* Samenvatting */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Totale runs</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{data?.total ?? 0}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Geslaagd</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-emerald-600">{runs.filter((r: any) => r.status === "completed").length}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Totaal gevonden</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{runs.reduce((s: number, r: any) => s + (r.candidates_found || 0), 0)}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Nieuw gevonden</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-blue-600">{runs.reduce((s: number, r: any) => s + (r.candidates_new || 0), 0)}</div></CardContent>
        </Card>
      </div>

      {isLoading ? (
        <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-40" />)}</div>
      ) : runs.length === 0 ? (
        <Card><CardContent className="p-12 text-center text-muted-foreground">
          Geen discovery-runs gevonden. Start een run via de "Concurrent Discovery" pagina.
        </CardContent></Card>
      ) : (
        <div className="space-y-4">
          {runs.map((run: any) => {
            const statusConfig = STATUS_CONFIG[run.status] || STATUS_CONFIG.running;
            const StatusIcon = statusConfig.icon;
            const runQueueItems = queueByRun[run.run_id] || [];
            const approved = runQueueItems.filter((i: any) => i.status === "APPROVED").length;
            const rejected = runQueueItems.filter((i: any) => i.status === "REJECTED").length;
            const proposed = runQueueItems.filter((i: any) => i.status === "PROPOSED").length;

            return (
              <Card key={run.run_id}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-3">
                        <CardTitle className="text-base font-mono text-sm">{run.run_id}</CardTitle>
                        <Badge variant="outline" className={`text-xs ${statusConfig.color}`}>
                          <StatusIcon className="h-3 w-3 mr-1" />{statusConfig.label}
                        </Badge>
                      </div>
                      <CardDescription className="mt-1">
                        Gestart: {run.started_at ? new Date(run.started_at).toLocaleString("nl-NL") : "—"}
                        {run.completed_at && ` · Duur: ${formatDuration(run.started_at, run.completed_at)}`}
                      </CardDescription>
                    </div>
                    <div className="text-right">
                      <div className="text-xl font-bold">{run.candidates_found}</div>
                      <div className="text-xs text-muted-foreground">gevonden</div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                    <div>
                      <div className="text-lg font-semibold text-blue-600">{run.candidates_new ?? "—"}</div>
                      <div className="text-xs text-muted-foreground">Nieuw</div>
                    </div>
                    <div>
                      <div className="text-lg font-semibold text-emerald-600">{approved || run.candidates_approved || 0}</div>
                      <div className="text-xs text-muted-foreground">Goedgekeurd</div>
                    </div>
                    <div>
                      <div className="text-lg font-semibold text-red-600">{rejected || run.candidates_rejected || 0}</div>
                      <div className="text-xs text-muted-foreground">Afgewezen</div>
                    </div>
                    <div>
                      <div className="text-lg font-semibold text-amber-600">{proposed}</div>
                      <div className="text-xs text-muted-foreground">In behandeling</div>
                    </div>
                  </div>

                  {/* Parameters */}
                  {run.parameters && Object.keys(run.parameters).length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-1">Parameters:</p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(run.parameters).map(([k, v]) => (
                          <span key={k} className="text-xs bg-muted px-2 py-0.5 rounded">
                            {k}: {String(v)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Categorieën */}
                  {(run.categories_searched || []).length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      <Tag className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
                      {run.categories_searched.map((cat: string) => (
                        <span key={cat} className="text-xs bg-muted px-1.5 py-0.5 rounded">{cat}</span>
                      ))}
                    </div>
                  )}

                  {run.error_message && (
                    <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2">
                      ❌ {run.error_message}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
