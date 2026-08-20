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
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";

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

  last_scan?: {
    started_at?: string | null;
    finished_at?: string | null;
    triggered_by?: string;
    status?: string;
    new_or_worse_errors?: number;
    signals_published?: number;

  } | null;
}

interface OutlierExample {
  sku_id: string;
  competitor_name: string;
  price: number | null;
  detail?: Record<string, any> | null;
}

interface OutlierReport {
  run_date: string | null;
  total_observations: number;
  total_excluded: number;
  outlier_threshold?: number;
  by_reason: Record<string, number>;
  by_suspected_cause: Record<string, number>;
  top_competitors: { competitor_name: string; excluded: number }[];
  top_categories: { category: string; excluded: number }[];
  examples: Record<string, OutlierExample[]>;
}

const REASON_LABELS: Record<string, string> = {
  COMPETITOR_IGNORED_OUTLIER: "Prijsuitbijter (afwijking > drempel)",
  COMPETITOR_IGNORED_OUT_OF_STOCK: "Niet op voorraad",
  COMPETITOR_IGNORED_BAD_DELIVERY: "Levertijd te lang",
  COMPETITOR_IGNORED_BAD_MATCH: "Afgekeurde productmatch",
  COMPETITOR_IGNORED_DIFFERENT_PACK_SIZE: "Afwijkende verpakkingsmaat",
  COMPETITOR_IGNORED_LOW_RELEVANCE: "Lage relevantie",
};

const CAUSE_LABELS: Record<string, string> = {
  PACK_SIZE_MULTIPLE: "Vermoedelijk grotere verpakking (veelvoud van mediaan)",
  PACK_SIZE_FRACTION: "Vermoedelijk kleinere verpakking (deel van mediaan)",
  DECIMAL_SHIFT: "Vermoedelijke decimaal-/centenfout",
  VAT_DIFFERENCE: "Vermoedelijk BTW-verschil (±21%)",
  EXTREME_DEVIATION: "Extreme afwijking (mogelijk verkeerde match)",
  ABOVE_THRESHOLD: "Boven drempel, geen herkenbaar patroon",
};

interface ScanRun {
  id: number;
  started_at?: string | null;
  finished_at?: string | null;
  triggered_by?: string;
  status?: string;
  issues_total?: number;
  error_issues?: number;
  warning_issues?: number;
  new_or_worse_errors?: number;
  signals_published?: number;
}

function formatScanTijd(iso?: string | null): string {
  if (!iso) return "onbekend";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleString("nl-NL", { dateStyle: "medium", timeStyle: "short" });
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
  const [scans, setScans] = useState<ScanRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [fout, setFout] = useState<string | null>(null);
  const [outliers, setOutliers] = useState<OutlierReport | null>(null);
  const [openReason, setOpenReason] = useState<string | null>(null);
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
    // Scan-historie apart laden: falen hiervan mag het rapport niet blokkeren.
    try {
      // status=geslaagd: server filtert vóór de limit, zodat mislukte runs
      // de 30 geslaagde trend-datapoints niet verdringen.
      const resp = await fetch(`${BASE}/api/data-quality/scans?limit=30&status=geslaagd`, {
        headers: getAuthHeaders(),
        signal: AbortSignal.timeout(30_000),
      });
      if (resp.ok) {
        const data = await resp.json();
        setScans(Array.isArray(data?.scans) ? data.scans : []);
      }
    } catch {
      // stil: trendkaart toont dan gewoon geen historie
    }
    // Uitbijter-reconciliatie apart laden: falen mag het rapport niet blokkeren.
    try {
      const resp = await fetch(`${BASE}/api/data-quality/outliers`, {
        headers: getAuthHeaders(),
        signal: AbortSignal.timeout(30_000),
      });
      if (resp.ok) setOutliers(await resp.json());
    } catch {
      // stil: sectie toont dan een lege staat
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

  // Trenddata: chronologisch (oudste eerst), alleen afgeronde geslaagde runs
  const trendData = useMemo(() => (
    scans
      .filter((s) => s.status === "geslaagd")
      .slice()
      .reverse()
      .map((s) => ({
        id: s.id,
        tijd: formatScanTijd(s.finished_at ?? s.started_at),
        fouten: s.error_issues ?? 0,
        waarschuwingen: s.warning_issues ?? 0,
        totaal: s.issues_total ?? 0,
      }))
  ), [scans]);

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
          {report?.last_scan && (
            <p className="text-xs text-muted-foreground mt-1" data-testid="text-last-scan">
              Laatste scan: {formatScanTijd(report.last_scan.finished_at ?? report.last_scan.started_at)}
              {" "}({report.last_scan.triggered_by === "scheduler" ? "automatisch" : "handmatig"})
              {typeof report.last_scan.new_or_worse_errors === "number" && report.last_scan.new_or_worse_errors > 0 &&
                ` — ${report.last_scan.new_or_worse_errors} nieuw/verergerd error-issue(s) gemeld`}
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

      {trendData.length >= 2 && (
        <Card data-testid="card-scan-trend">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Scan-historie</CardTitle>
            <CardDescription>
              Trend van fouten en waarschuwingen over de laatste {trendData.length} geslaagde scans.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={trendData} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-muted" />
                  <XAxis dataKey="tijd" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip
                    formatter={(value: any, name: any) => [value, name]}
                    labelFormatter={(label) => `Scan: ${label}`}
                    contentStyle={{ fontSize: 12 }}
                  />
                  <Line type="monotone" dataKey="fouten" name="Fouten" stroke="#dc2626" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="waarschuwingen" name="Waarschuwingen" stroke="#d97706" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="totaal" name="Totaal issues" stroke="#64748b" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      <Card data-testid="card-outlier-reconciliation">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Prijsuitbijters & reconciliatie</CardTitle>
          <CardDescription>
            Uitgesloten concurrentprijzen worden nooit verwijderd, alleen gemarkeerd met een expliciete reden.
            {outliers?.run_date ? ` Laatste scoring-run: ${outliers.run_date}.` : ""}
            {typeof outliers?.outlier_threshold === "number"
              ? ` Actieve uitbijterdrempel: ${(outliers.outlier_threshold * 100).toFixed(0)}% afwijking van de mediaan (instelbaar via de importinstellingen op de connectoren-pagina).`
              : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!outliers || !outliers.run_date ? (
            <p className="text-sm text-muted-foreground" data-testid="text-outliers-empty">
              Nog geen gemarkeerde uitsluitingen — draai eerst een feed-sync/scoring-run.
            </p>
          ) : (
            <>
              <div className="text-sm text-muted-foreground" data-testid="text-outliers-totals">
                <span className="font-semibold text-foreground tabular-nums">{outliers.total_excluded.toLocaleString("nl-NL")}</span>
                {" "}van{" "}
                <span className="tabular-nums">{outliers.total_observations.toLocaleString("nl-NL")}</span>
                {" "}concurrentprijzen uitgesloten van de referentieprijs
                {outliers.total_observations > 0 && (
                  <> ({((outliers.total_excluded / outliers.total_observations) * 100).toFixed(1)}%)</>
                )}.
              </div>

              {/* Totalen per reden + drill-down naar voorbeelden */}
              <div className="grid gap-2">
                {Object.entries(outliers.by_reason).sort((a, b) => b[1] - a[1]).map(([reason, count]) => (
                  <div key={reason} className="rounded-md border border-input">
                    <button
                      type="button"
                      className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-muted/40"
                      onClick={() => setOpenReason(openReason === reason ? null : reason)}
                      data-testid={`button-outlier-reason-${reason}`}
                    >
                      <span>{REASON_LABELS[reason] ?? reason}</span>
                      <span className="flex items-center gap-2">
                        <span className="font-semibold tabular-nums">{count.toLocaleString("nl-NL")}</span>
                        {openReason === reason ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </span>
                    </button>
                    {openReason === reason && (
                      <div className="border-t px-3 py-2 space-y-1.5" data-testid={`panel-outlier-examples-${reason}`}>
                        {(outliers.examples[reason] ?? []).length === 0 ? (
                          <p className="text-xs text-muted-foreground">Geen voorbeelden beschikbaar.</p>
                        ) : (
                          (outliers.examples[reason] ?? []).map((ex, i) => (
                            <div key={i} className="text-xs flex flex-wrap gap-x-3 gap-y-0.5">
                              <span className="font-medium">{ex.sku_id}</span>
                              <span className="text-muted-foreground">{ex.competitor_name}</span>
                              {ex.price != null && <span className="tabular-nums">€ {ex.price.toLocaleString("nl-NL", { minimumFractionDigits: 2 })}</span>}
                              {ex.detail?.median != null && <span className="text-muted-foreground tabular-nums">mediaan € {Number(ex.detail.median).toLocaleString("nl-NL", { minimumFractionDigits: 2 })}</span>}
                              {ex.detail?.deviation_pct != null && <span className="text-muted-foreground tabular-nums">afwijking {ex.detail.deviation_pct}%</span>}
                              {ex.detail?.suspected_cause && <span className="text-amber-700">{CAUSE_LABELS[ex.detail.suspected_cause] ?? ex.detail.suspected_cause}</span>}
                              {ex.detail?.delivery_days != null && <span className="text-muted-foreground tabular-nums">levertijd {ex.detail.delivery_days} dgn</span>}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Vermoedelijke oorzaken van prijsuitbijters */}
              {Object.keys(outliers.by_suspected_cause).length > 0 && (
                <div data-testid="section-outlier-causes">
                  <p className="text-xs font-medium mb-1.5">Vermoedelijke oorzaken van prijsuitbijters</p>
                  <div className="grid gap-1">
                    {Object.entries(outliers.by_suspected_cause).sort((a, b) => b[1] - a[1]).map(([cause, count]) => (
                      <div key={cause} className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">{CAUSE_LABELS[cause] ?? cause}</span>
                        <span className="font-medium tabular-nums">{count.toLocaleString("nl-NL")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Meest geraakte concurrenten / categorieën */}
              <div className="grid md:grid-cols-2 gap-4">
                {outliers.top_competitors.length > 0 && (
                  <div data-testid="section-outlier-competitors">
                    <p className="text-xs font-medium mb-1.5">Meest geraakte concurrenten</p>
                    <div className="grid gap-1">
                      {outliers.top_competitors.map((c) => (
                        <div key={c.competitor_name} className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground truncate">{c.competitor_name}</span>
                          <span className="font-medium tabular-nums">{c.excluded.toLocaleString("nl-NL")}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {outliers.top_categories.length > 0 && (
                  <div data-testid="section-outlier-categories">
                    <p className="text-xs font-medium mb-1.5">Meest geraakte categorieën</p>
                    <div className="grid gap-1">
                      {outliers.top_categories.map((c) => (
                        <div key={c.category} className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground truncate">{c.category}</span>
                          <span className="font-medium tabular-nums">{c.excluded.toLocaleString("nl-NL")}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>

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
