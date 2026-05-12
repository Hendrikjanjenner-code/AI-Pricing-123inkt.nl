import { useGetModelHealth, useListModelRuns, useTriggerModelRun } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query";
import { Activity, Play, CheckCircle2, AlertCircle, Clock } from "lucide-react";

const STATUS_LABELS: Record<string, string> = {
  healthy: "Gezond",
  degraded: "Verminderd",
  error: "Fout",
  running: "Actief",
};

export default function Modelgezondheid() {
  const { data: health, isLoading: loadingHealth } = useGetModelHealth();
  const { data: runs, isLoading: loadingRuns } = useListModelRuns();
  const triggerMut = useTriggerModelRun();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const handleActiveer = async () => {
    try {
      await triggerMut.mutateAsync();
      toast({ title: "Modelrun gestart" });
      queryClient.invalidateQueries({ queryKey: ["/api/model/health"] });
      queryClient.invalidateQueries({ queryKey: ["/api/model/runs"] });
    } catch {
      toast({ title: "Kon modelrun niet starten", variant: "destructive" });
    }
  };

  const statusKleur = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-emerald-500';
      case 'degraded': return 'text-amber-500';
      case 'error': return 'text-destructive';
      default: return 'text-muted-foreground';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Modelgezondheid & Engine</h1>
          <p className="text-muted-foreground mt-1">Status en uitvoering van het centrale prijsalgoritme.</p>
        </div>
        <Button onClick={handleActiveer} disabled={triggerMut.isPending || health?.status === 'running'}>
          <Play className="h-4 w-4 mr-2" />
          {triggerMut.isPending ? "Starten..." : "Model nu uitvoeren"}
        </Button>
      </div>

      {loadingHealth ? <Skeleton className="h-64 w-full" /> : health && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card className="col-span-1 md:col-span-4 border-primary/20">
            <CardContent className="p-6 flex items-center justify-between">
              <div className="flex items-center gap-6">
                <div className={`w-16 h-16 rounded-full bg-muted flex items-center justify-center`}>
                  <Activity className={`h-8 w-8 ${statusKleur(health.status)}`} />
                </div>
                <div>
                  <div className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Engine-status</div>
                  <div className="text-3xl font-bold flex items-center gap-3">
                    {STATUS_LABELS[health.status] || health.status}
                    <Badge variant="outline" className="text-xs uppercase">{health.model_version}</Badge>
                  </div>
                  <div className="text-sm text-muted-foreground mt-1">
                    Laatste run: {health.last_run_at ? new Date(health.last_run_at).toLocaleString('nl-NL') : 'Nooit'}
                  </div>
                </div>
              </div>
              <div className="flex gap-8 text-right">
                <div>
                  <div className="text-sm text-muted-foreground">SKU's verwerkt</div>
                  <div className="text-2xl font-bold">{health.skus_processed.toLocaleString('nl-NL')}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Gem. betrouwbaarheid</div>
                  <div className="text-2xl font-bold">{(health.avg_confidence * 100).toFixed(1)}%</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="col-span-1 md:col-span-2">
            <CardHeader>
              <CardTitle className="text-destructive flex items-center"><AlertCircle className="w-5 h-5 mr-2" /> Kritieke fouten</CardTitle>
            </CardHeader>
            <CardContent>
              {health.errors.length === 0 ? (
                <div className="text-muted-foreground flex items-center"><CheckCircle2 className="w-4 h-4 mr-2 text-emerald-500" /> Geen actieve fouten</div>
              ) : (
                <ul className="space-y-2">
                  {health.errors.map((e, i) => <li key={i} className="text-sm text-destructive bg-destructive/10 p-2 rounded">{e}</li>)}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="col-span-1 md:col-span-2">
            <CardHeader>
              <CardTitle className="text-amber-500 flex items-center"><AlertCircle className="w-5 h-5 mr-2" /> Waarschuwingen</CardTitle>
            </CardHeader>
            <CardContent>
              {health.warnings.length === 0 ? (
                <div className="text-muted-foreground flex items-center"><CheckCircle2 className="w-4 h-4 mr-2 text-emerald-500" /> Geen waarschuwingen</div>
              ) : (
                <ul className="space-y-2">
                  {health.warnings.map((w, i) => <li key={i} className="text-sm text-amber-700 bg-amber-50 p-2 rounded border border-amber-200">{w}</li>)}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Uitvoeringshistorie</CardTitle>
          <CardDescription>Recente modelruns</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="grid grid-cols-6 border-b bg-muted/50 p-3 text-sm font-medium text-muted-foreground">
            <div className="col-span-2">Gestart om</div>
            <div>Status</div>
            <div className="text-right">Verwerkt</div>
            <div className="text-right">Overgeslagen</div>
            <div className="text-right">Versie</div>
          </div>
          <div className="divide-y max-h-[400px] overflow-y-auto">
            {loadingRuns ? (
              <div className="p-8 text-center"><Skeleton className="h-8 w-full" /></div>
            ) : runs?.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">Geen uitvoeringshistorie.</div>
            ) : runs?.map((run) => (
              <div key={run.id} className="grid grid-cols-6 items-center p-3 text-sm">
                <div className="col-span-2 flex items-center gap-2 text-muted-foreground">
                  <Clock className="w-4 h-4" /> {new Date(run.started_at).toLocaleString('nl-NL')}
                </div>
                <div>
                  {run.status === 'completed' && <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200">Voltooid</Badge>}
                  {run.status === 'running' && <Badge variant="outline" className="bg-blue-50 text-blue-600 border-blue-200">Actief</Badge>}
                  {run.status === 'failed' && <Badge variant="destructive">Mislukt</Badge>}
                </div>
                <div className="text-right font-medium">{run.skus_processed.toLocaleString('nl-NL')}</div>
                <div className="text-right text-muted-foreground">{run.skus_skipped.toLocaleString('nl-NL')}</div>
                <div className="text-right font-mono text-xs">{run.model_version}</div>
                {run.error_message && (
                  <div className="col-span-6 mt-2 text-xs text-destructive bg-destructive/10 p-2 rounded">{run.error_message}</div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
