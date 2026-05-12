import { useState, useEffect } from "react";
import { SidebarLayout } from "@/components/layout/SidebarLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  Download, Play, RotateCcw, RefreshCw, CheckCircle2, XCircle,
  Shield, FileText, Zap, AlertTriangle
} from "lucide-react";
import { getAuthToken } from "@/lib/auth";
import { useAuth } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

async function apiFetch(path: string, options?: RequestInit) {
  const token = getAuthToken();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(options?.headers || {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const MODE_LABELS: Record<string, string> = {
  MANUAL_EXPORT: "CSV export",
  DRY_RUN: "Dry run",
  API_PUSH_READY: "API push (demo)",
  BLOCKED_BY_GUARDRAIL: "Geblokkeerd",
};

const MODE_ICON: Record<string, React.ReactElement> = {
  MANUAL_EXPORT: <FileText className="w-4 h-4 text-blue-500" />,
  DRY_RUN: <Play className="w-4 h-4 text-slate-500" />,
  API_PUSH_READY: <Zap className="w-4 h-4 text-green-500" />,
  BLOCKED_BY_GUARDRAIL: <Shield className="w-4 h-4 text-red-500" />,
};

const STATUS_KLEUR: Record<string, string> = {
  aangemaakt: "bg-blue-100 text-blue-800",
  geëxporteerd: "bg-green-100 text-green-800",
  verstuurd_demo: "bg-green-100 text-green-800",
  teruggedraaid: "bg-slate-100 text-slate-700",
  geblokkeerd: "bg-red-100 text-red-800",
};

export default function Uitvoering() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [jobs, setJobs] = useState<any>(null);
  const [gekozenJob, setGekozenJob] = useState<any>(null);
  const [jobLines, setJobLines] = useState<any>(null);
  const [laden, setLaden] = useState(true);
  const [ladenLines, setLadenLines] = useState(false);
  const [actie, setActie] = useState<string | null>(null);

  const isManager = ["admin", "pricing_manager"].includes(user?.role || "");

  useEffect(() => { laadJobs(); }, []);

  async function laadJobs() {
    setLaden(true);
    try {
      const j = await apiFetch("/api/execution/jobs");
      setJobs(j);
    } catch { toast({ title: "Fout bij laden", variant: "destructive" }); }
    setLaden(false);
  }

  async function laadJobLines(job_id: number) {
    setLadenLines(true);
    setGekozenJob(job_id);
    try {
      const l = await apiFetch(`/api/execution/jobs/${job_id}/lines`);
      setJobLines(l);
    } catch { toast({ title: "Fout", variant: "destructive" }); }
    setLadenLines(false);
  }

  async function dryRun() {
    setActie("dry");
    try {
      const r = await apiFetch("/api/execution/dry-run", { method: "POST", body: JSON.stringify({}) });
      toast({ title: "Dry run voltooid", description: `${r.approved_count} goedgekeurd, ${r.rejected_count} afgewezen door guardrails` });
      laadJobs();
    } catch (e: any) {
      toast({ title: "Dry run mislukt", description: e.message, variant: "destructive" });
    }
    setActie(null);
  }

  async function exportCsv() {
    setActie("csv");
    try {
      const token = getAuthToken();
      const res = await fetch(`${BASE}/api/execution/export-csv`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `prijswijzigingen_${new Date().toISOString().slice(0, 10)}.csv`; a.click();
      URL.revokeObjectURL(url);
      toast({ title: "CSV geëxporteerd" });
      laadJobs();
    } catch (e: any) {
      toast({ title: "Export mislukt", description: e.message, variant: "destructive" });
    }
    setActie(null);
  }

  async function apiPush() {
    setActie("push");
    try {
      const r = await apiFetch("/api/execution/push", { method: "POST", body: JSON.stringify({}) });
      toast({ title: "API push gesimuleerd", description: `${r.push_resultaat?.geslaagd || 0} prijzen verstuurd (demo)` });
      laadJobs();
    } catch (e: any) {
      toast({ title: "Push mislukt", description: e.message, variant: "destructive" });
    }
    setActie(null);
  }

  async function rollback(job_id: number) {
    setActie(`rollback-${job_id}`);
    try {
      const r = await apiFetch(`/api/execution/rollback/${job_id}`, { method: "POST" });
      toast({ title: "Teruggedraaid", description: `${r.teruggezet} SKU's teruggezet` });
      laadJobs();
      if (gekozenJob === job_id) laadJobLines(job_id);
    } catch { toast({ title: "Rollback mislukt", variant: "destructive" }); }
    setActie(null);
  }

  return (
    <SidebarLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Uitvoering Prijswijzigingen</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Voer goedgekeurde prijsadviezen uit. Alle wijzigingen vereisen approval en worden gelogd.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={laadJobs}><RefreshCw className="w-4 h-4 mr-2" />Vernieuwen</Button>
        </div>

        {/* Acties */}
        {isManager && (
          <div className="grid grid-cols-3 gap-4">
            <Card className="border-dashed">
              <CardContent className="pt-4 text-center space-y-3">
                <Play className="w-8 h-8 mx-auto text-slate-400" />
                <div>
                  <div className="font-medium text-sm">Dry run</div>
                  <div className="text-xs text-muted-foreground">Simuleer uitvoering zonder prijswijziging</div>
                </div>
                <Button size="sm" variant="outline" className="w-full" onClick={dryRun} disabled={actie === "dry"}>
                  {actie === "dry" ? "Bezig..." : "Dry run starten"}
                </Button>
              </CardContent>
            </Card>
            <Card className="border-dashed">
              <CardContent className="pt-4 text-center space-y-3">
                <Download className="w-8 h-8 mx-auto text-blue-500" />
                <div>
                  <div className="font-medium text-sm">CSV exporteren</div>
                  <div className="text-xs text-muted-foreground">Download prijswijzigingen als CSV-bestand</div>
                </div>
                <Button size="sm" className="w-full" onClick={exportCsv} disabled={actie === "csv"}>
                  {actie === "csv" ? "Exporteren..." : "Exporteren"}
                </Button>
              </CardContent>
            </Card>
            <Card className="border-dashed">
              <CardContent className="pt-4 text-center space-y-3">
                <Zap className="w-8 h-8 mx-auto text-green-500" />
                <div>
                  <div className="font-medium text-sm">API push (demo)</div>
                  <div className="text-xs text-muted-foreground">Simuleer API-push naar e-commerce systeem</div>
                </div>
                <Button size="sm" variant="outline" className="w-full" onClick={apiPush} disabled={actie === "push"}>
                  {actie === "push" ? "Bezig..." : "Push simuleren"}
                </Button>
              </CardContent>
            </Card>
          </div>
        )}

        <div className="grid grid-cols-2 gap-6">
          {/* Jobs lijst */}
          <div>
            <h2 className="text-sm font-semibold mb-3">Uitvoering-jobs</h2>
            {laden ? <Skeleton className="h-64 w-full" /> : (
              <div className="space-y-2">
                {jobs?.jobs?.map((j: any) => (
                  <div key={j.job_id}
                    className={`border rounded-md p-3 cursor-pointer transition-colors ${gekozenJob === j.job_id ? "border-primary bg-primary/5" : "hover:bg-muted/30"}`}
                    onClick={() => laadJobLines(j.job_id)}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        {MODE_ICON[j.execution_mode] || <FileText className="w-4 h-4 text-muted-foreground" />}
                        <span className="font-medium text-sm">{MODE_LABELS[j.execution_mode] || j.execution_mode}</span>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STATUS_KLEUR[j.status] || "bg-slate-100 text-slate-700"}`}>
                        {j.status}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground flex gap-3">
                      <span>{new Date(j.created_at).toLocaleString("nl-NL")}</span>
                      <span>{j.created_by}</span>
                      <span className="text-green-600">{j.approved_count} goedgekeurd</span>
                      {j.rejected_count > 0 && <span className="text-red-500">{j.rejected_count} afgewezen</span>}
                    </div>
                    {isManager && j.status !== "teruggedraaid" && (
                      <Button size="sm" variant="ghost" className="mt-1 h-6 text-xs text-red-500 px-1"
                        onClick={e => { e.stopPropagation(); rollback(j.job_id); }}
                        disabled={actie === `rollback-${j.job_id}`}>
                        <RotateCcw className="w-3 h-3 mr-1" />Terugdraaien
                      </Button>
                    )}
                  </div>
                ))}
                {!jobs?.jobs?.length && (
                  <div className="border rounded-md p-8 text-center text-muted-foreground text-sm">
                    <FileText className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    Nog geen uitvoering-jobs
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Job detail */}
          <div>
            <h2 className="text-sm font-semibold mb-3">
              {gekozenJob ? `Prijsregels job #${gekozenJob}` : "Selecteer een job"}
            </h2>
            {!gekozenJob ? (
              <div className="border rounded-md p-8 text-center text-muted-foreground text-sm">
                Klik op een job om de prijsregels te bekijken
              </div>
            ) : ladenLines ? <Skeleton className="h-64 w-full" /> : (
              <div className="rounded-md border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>SKU</TableHead>
                      <TableHead className="text-right">Oud</TableHead>
                      <TableHead className="text-right">Nieuw</TableHead>
                      <TableHead className="text-right">Δ%</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobLines?.lines?.map((l: any) => (
                      <TableRow key={l.line_id}>
                        <TableCell>
                          <div className="text-xs font-medium truncate max-w-[120px]">{l.product_naam}</div>
                          <div className="text-[10px] font-mono text-muted-foreground">{l.sku_id}</div>
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm">
                          {l.old_price ? `€${l.old_price.toFixed(2)}` : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm font-semibold">
                          {l.new_price ? `€${l.new_price.toFixed(2)}` : "—"}
                        </TableCell>
                        <TableCell className={`text-right text-sm font-mono ${(l.change_pct || 0) < 0 ? "text-red-600" : "text-green-600"}`}>
                          {l.change_pct != null ? `${l.change_pct > 0 ? "+" : ""}${l.change_pct.toFixed(1)}%` : "—"}
                        </TableCell>
                        <TableCell>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                            l.status === "goedgekeurd" ? "bg-green-100 text-green-800" :
                            l.status === "teruggedraaid" ? "bg-slate-100 text-slate-700" :
                            "bg-red-100 text-red-800"
                          }`}>{l.status}</span>
                        </TableCell>
                      </TableRow>
                    ))}
                    {!jobLines?.lines?.length && (
                      <TableRow><TableCell colSpan={5} className="text-center py-6 text-muted-foreground text-sm">Geen regels</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </div>
      </div>
    </SidebarLayout>
  );
}
