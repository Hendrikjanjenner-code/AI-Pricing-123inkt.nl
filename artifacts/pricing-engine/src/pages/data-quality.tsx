import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Info,
  Loader2, RefreshCw, ShieldAlert, UserCircle2, XCircle,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface QualityIssue {
  id?: number;
  issue_code: string;
  title?: string;
  message: string;
  severity: "error" | "warning" | "info";
  source?: string;
  module?: string;
  affected_count: number;
  business_impact?: string;
  suggested_action?: string;
  owner?: string | null;
  status?: string;
  first_detected_at?: string | null;
}

interface QualityReport {
  overall_score: number;
  total_skus: number;
  issues: QualityIssue[];
  counts?: { errors: number; warnings: number; info: number; open: number; in_behandeling: number };
  last_scan_at?: string | null;
  last_scheduled_scan_at?: string | null;
  last_scheduled_scan_status?: string | null;
}

const STATUS_OPTIES = [
  { value: "open", label: "Open" },
  { value: "in_behandeling", label: "In behandeling" },
  { value: "genegeerd", label: "Genegeerd" },
  { value: "opgelost", label: "Opgelost" },
];

function severityBadge(sev: string) {
  if (sev === "error") return <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Fout</Badge>;
  if (sev === "warning") return <Badge className="bg-amber-50 text-amber-700 border-amber-200 text-xs">Waarschuwing</Badge>;
  return <Badge className="bg-blue-50 text-blue-600 border-blue-200 text-xs">Info</Badge>;
}

function statusBadge(status?: string) {
  switch (status) {
    case "in_behandeling":
      return <Badge className="bg-blue-50 text-blue-600 border-blue-200 text-xs">In behandeling</Badge>;
    case "genegeerd":
      return <Badge variant="outline" className="text-xs">Genegeerd</Badge>;
    case "opgelost":
      return <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">Opgelost</Badge>;
    default:
      return <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Open</Badge>;
  }
}

function IssueRij({ issue, onUpdate }: { issue: QualityIssue; onUpdate: (id: number, patch: { owner?: string; status?: string }) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [ownerDraft, setOwnerDraft] = useState(issue.owner ?? "");
  const [busy, setBusy] = useState(false);

  const doUpdate = async (patch: { owner?: string; status?: string }) => {
    if (issue.id == null) return;
    setBusy(true);
    try {
      await onUpdate(issue.id, patch);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <TableRow className="cursor-pointer hover:bg-muted/40" onClick={() => setOpen((v) => !v)}>
        <TableCell>{severityBadge(issue.severity)}</TableCell>
        <TableCell className="font-medium text-sm">{issue.title ?? issue.issue_code}</TableCell>
        <TableCell><Badge variant="outline" className="text-xs">{issue.source ?? "—"}</Badge></TableCell>
        <TableCell className="text-sm text-muted-foreground">{issue.module ?? "—"}</TableCell>
        <TableCell className="text-right text-sm font-mono">{issue.affected_count.toLocaleString("nl-NL")}</TableCell>
        <TableCell className="text-sm">
          {issue.owner ? (
            <span className="flex items-center gap-1"><UserCircle2 className="w-3.5 h-3.5 text-muted-foreground" />{issue.owner}</span>
          ) : <span className="text-muted-foreground">—</span>}
        </TableCell>
        <TableCell>{statusBadge(issue.status)}</TableCell>
        <TableCell className="w-8 text-muted-foreground">
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableCell colSpan={8}>
            <div className="p-3 space-y-3 text-sm">
              <p>{issue.message}</p>
              {issue.business_impact && (
                <div className="flex gap-2">
                  <ShieldAlert className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-medium">Business impact: </span>
                    <span className="text-muted-foreground">{issue.business_impact}</span>
                  </div>
                </div>
              )}
              {issue.suggested_action && (
                <div className="flex gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-medium">Aanbevolen actie: </span>
                    <span className="text-muted-foreground">{issue.suggested_action}</span>
                  </div>
                </div>
              )}
              {issue.first_detected_at && (
                <p className="text-xs text-muted-foreground">
                  Eerst gedetecteerd: {new Date(issue.first_detected_at).toLocaleString("nl-NL")}
                </p>
              )}
              {issue.id != null && (
                <div className="flex flex-wrap items-end gap-3 pt-1" onClick={(e) => e.stopPropagation()}>
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Eigenaar</label>
                    <div className="flex gap-2">
                      <Input
                        value={ownerDraft}
                        onChange={(e) => setOwnerDraft(e.target.value)}
                        placeholder="gebruikersnaam"
                        className="h-8 w-44 text-sm"
                      />
                      <Button size="sm" variant="outline" className="h-8" disabled={busy}
                        onClick={() => doUpdate({ owner: ownerDraft })}>
                        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Toewijzen"}
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Status</label>
                    <Select value={issue.status ?? "open"} onValueChange={(v) => doUpdate({ status: v })}>
                      <SelectTrigger className="h-8 w-44 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {STATUS_OPTIES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

export default function DataQuality() {
  const [report, setReport] = useState<QualityReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [fout, setFout] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState("alle");
  const [bronFilter, setBronFilter] = useState("alle");
  const [statusFilter, setStatusFilter] = useState("actief");

  const laad = useCallback(async () => {
    setLoading(true);
    setFout(null);
    try {
      const resp = await fetch(`${BASE}/api/data-quality`, {
        headers: getAuthHeaders(),
        signal: AbortSignal.timeout(60_000),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setReport(await resp.json());
    } catch (e: any) {
      setFout(e?.message ?? "Onbekende fout");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { laad(); }, [laad]);

  const updateIssue = async (id: number, patch: { owner?: string; status?: string }) => {
    const resp = await fetch(`${BASE}/api/data-quality/issues/${id}`, {
      method: "PATCH",
      headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (resp.ok) {
      const updated = await resp.json();
      setReport((prev) => prev ? {
        ...prev,
        issues: prev.issues.map((i) => (i.id === id ? { ...i, owner: updated.owner, status: updated.status } : i)),
      } : prev);
    }
  };

  const issues = report?.issues ?? [];
  const bronnen = useMemo(() => Array.from(new Set(issues.map((i) => i.source).filter(Boolean))) as string[], [issues]);

  const gefilterd = issues.filter((i) => {
    if (severityFilter !== "alle" && i.severity !== severityFilter) return false;
    if (bronFilter !== "alle" && i.source !== bronFilter) return false;
    if (statusFilter === "actief" && (i.status === "opgelost" || i.status === "genegeerd")) return false;
    if (statusFilter !== "alle" && statusFilter !== "actief" && i.status !== statusFilter) return false;
    return true;
  });

  const errors = issues.filter((i) => i.severity === "error" && i.status !== "opgelost" && i.status !== "genegeerd").length;
  const warns = issues.filter((i) => i.severity === "warning" && i.status !== "opgelost" && i.status !== "genegeerd").length;

  if (loading && !report) {
    return <div className="space-y-4"><Skeleton className="h-24 w-full" /><Skeleton className="h-96 w-full" /></div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Data Quality Center</h1>
          <p className="text-muted-foreground mt-1">
            Alle datakwaliteits-detecties met severity, business impact, aanbevolen actie en eigenaar-workflow.
          </p>
          {report?.last_scan_at && (
            <p className="text-xs text-muted-foreground mt-1" data-testid="text-last-scan">
              Laatste scan: {new Date(report.last_scan_at).toLocaleString("nl-NL")}
              {" · "}
              Laatste nachtelijke scan:{" "}
              {report.last_scheduled_scan_at
                ? `${new Date(report.last_scheduled_scan_at).toLocaleString("nl-NL")}${report.last_scheduled_scan_status === "fout" ? " (mislukt)" : ""}`
                : "nog niet uitgevoerd"}
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={laad} disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
          Vernieuwen
        </Button>
      </div>

      {fout && (
        <Card className="border-red-200">
          <CardContent className="pt-6 text-sm text-red-600 flex items-center gap-2">
            <XCircle className="w-4 h-4" /> Rapport laden mislukt: {fout}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Algehele datakwaliteit</CardTitle></CardHeader>
          <CardContent>
            <div className={`text-3xl font-bold ${(report?.overall_score ?? 0) >= 80 ? "text-emerald-600" : (report?.overall_score ?? 0) >= 60 ? "text-amber-600" : "text-red-600"}`}>
              {report?.overall_score ?? 0}%
            </div>
            <p className="text-xs text-muted-foreground mt-1">{report?.total_skus?.toLocaleString("nl-NL")} SKU's beoordeeld</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><XCircle className="w-4 h-4 text-red-500" />Fouten</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-bold text-red-600">{errors}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-amber-500" />Waarschuwingen</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-bold text-amber-600">{warns}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><Info className="w-4 h-4 text-blue-500" />In behandeling</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-bold text-blue-600">{issues.filter((i) => i.status === "in_behandeling").length}</div></CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <CardTitle>Kwaliteitsissues</CardTitle>
              <CardDescription>Klik op een issue voor impact, aanbevolen actie en workflow.</CardDescription>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[150px] h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="actief">Actieve issues</SelectItem>
                  <SelectItem value="alle">Alle statussen</SelectItem>
                  {STATUS_OPTIES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={severityFilter} onValueChange={setSeverityFilter}>
                <SelectTrigger className="w-[150px] h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="alle">Alle severities</SelectItem>
                  <SelectItem value="error">Fout</SelectItem>
                  <SelectItem value="warning">Waarschuwing</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                </SelectContent>
              </Select>
              <Select value={bronFilter} onValueChange={setBronFilter}>
                <SelectTrigger className="w-[150px] h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="alle">Alle bronnen</SelectItem>
                  {bronnen.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {gefilterd.length === 0 ? (
            <div className="p-10 text-center text-muted-foreground flex flex-col items-center gap-2">
              <CheckCircle2 className="w-8 h-8 text-emerald-500" />
              Geen datakwaliteitsproblemen gevonden voor deze filters.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Severity</TableHead>
                  <TableHead>Issue</TableHead>
                  <TableHead>Bron</TableHead>
                  <TableHead>Module</TableHead>
                  <TableHead className="text-right">Records</TableHead>
                  <TableHead>Eigenaar</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {gefilterd.map((issue) => (
                  <IssueRij key={issue.issue_code} issue={issue} onUpdate={updateIssue} />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
