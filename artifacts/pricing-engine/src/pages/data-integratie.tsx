import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { useListUploads, useGetExportHistory, useGetDataQuality, useGetDashboardSummary } from "@workspace/api-client-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertTriangle, CheckCircle2, Database, FileSpreadsheet, FileText,
  Package, Percent, RefreshCw, Server, ShieldAlert, XCircle, Zap,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

type ConnStatus = {
  configured: boolean;
  reachable: boolean;
  status: "ok" | "not_configured" | "unreachable" | "auth_error" | "error";
  message: string;
};

const OK_STATUSSEN = new Set(["geimporteerd", "bijgewerkt", "opgeslagen", "completed"]);
const FOUT_STATUSSEN = new Set(["fout", "failed"]);

function statusBadge(status: string | undefined) {
  if (!status) return <Badge variant="outline" className="text-xs">Onbekend</Badge>;
  if (OK_STATUSSEN.has(status)) {
    return <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">Geslaagd</Badge>;
  }
  if (FOUT_STATUSSEN.has(status)) {
    return <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Fout</Badge>;
  }
  if (status === "processing" || status === "nieuw" || status === "concept" || status === "gevalideerd") {
    return <Badge className="bg-blue-50 text-blue-600 border-blue-200 text-xs">Bezig</Badge>;
  }
  return <Badge variant="outline" className="text-xs">{status}</Badge>;
}

function formatDatum(iso: string | null | undefined) {
  if (!iso) return "Nooit";
  try {
    return new Date(iso).toLocaleString("nl-NL", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

interface DataSourceRow {
  key: string;
  label: string;
  kind: string;
  connection_status: string;
  configured: boolean;
  last_sync_at: string | null;
  next_sync_at: string | null;
  sync_schedule: string;
  records: number;
  records_label: string;
  newest_data_date: string | null;
  freshness_days: number | null;
  warnings_recent: number;
  failed_jobs_recent: number;
  rows_failed_recent: number;
  quality_score: number;
  open_issues: number;
  last_test_message?: string | null;
  last_job?: any;
  last_failed_job?: { id: number; status: string; failed_at: string | null; reason: string | null } | null;
}

function verbindingBadge(status: string, configured: boolean) {
  if (!configured || status === "not_configured") {
    return <Badge variant="outline" className="text-xs text-muted-foreground">Niet gekoppeld</Badge>;
  }
  if (status === "ok") return <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">Verbonden</Badge>;
  if (status === "unknown") return <Badge className="bg-blue-50 text-blue-600 border-blue-200 text-xs">Geconfigureerd</Badge>;
  if (status === "auth_error") return <Badge className="bg-amber-50 text-amber-700 border-amber-200 text-xs">Authenticatiefout</Badge>;
  if (status === "unreachable") return <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Niet bereikbaar</Badge>;
  return <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Fout</Badge>;
}

function freshnessCel(days: number | null) {
  if (days === null || days === undefined) return <span className="text-muted-foreground">—</span>;
  const kleur = days <= 1 ? "text-emerald-600" : days <= 3 ? "text-amber-600" : "text-red-600";
  return <span className={`font-medium ${kleur}`}>{days === 0 ? "vandaag" : `${days} d`}</span>;
}

function kwaliteitCel(score: number, openIssues: number) {
  const kleur = score >= 90 ? "text-emerald-600" : score >= 70 ? "text-amber-600" : "text-red-600";
  return (
    <div className="flex items-center gap-2">
      <span className={`font-medium ${kleur}`}>{score}%</span>
      {openIssues > 0 && <span className="text-xs text-muted-foreground">({openIssues} issues)</span>}
    </div>
  );
}

type VerbindingStatus = "ok" | "not_configured" | "unreachable" | "auth_error" | "error";

interface BronKaart {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  laatsteJob: any | null;
  overrideStatus?: VerbindingStatus;
  overrideMessage?: string;
  connStatus?: VerbindingStatus;
  connMessage?: string;
  nietGekoppeld?: boolean;
  mislukteJob?: any | null;
}

const VERBINDING_LABEL: Record<VerbindingStatus, string> = {
  ok: "Verbinding OK",
  not_configured: "Nog niet gekoppeld",
  unreachable: "Niet bereikbaar",
  auth_error: "Authenticatiefout",
  error: "Verbindingsfout",
};

function BronStatusCard({ kaart }: { kaart: BronKaart }) {
  const Icon = kaart.icon;
  const status = kaart.overrideStatus
    ?? (kaart.laatsteJob ? (OK_STATUSSEN.has(kaart.laatsteJob.status) ? "ok" : FOUT_STATUSSEN.has(kaart.laatsteJob.status) ? "error" : "unreachable") : "not_configured");

  const kleur = status === "ok" ? "border-emerald-200" : status === "not_configured" ? "border-dashed opacity-80" : "border-red-200";
  const dotKleur = status === "ok" ? "bg-emerald-500" : status === "not_configured" ? "bg-gray-400" : status === "auth_error" ? "bg-amber-500" : "bg-red-500";
  const labelKleur = status === "ok" ? "text-emerald-600" : status === "not_configured" ? "text-muted-foreground" : "text-red-600";
  const labelTekst = status === "ok" ? "OK" : status === "not_configured" ? "Nog niet gekoppeld" : status === "auth_error" ? "Authenticatiefout" : status === "unreachable" ? "Niet bereikbaar" : "Fout";

  return (
    <Card className={kleur}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Icon className="w-4 h-4 text-muted-foreground" />
          {kaart.label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${dotKleur}`} />
          <span className={`text-sm font-medium ${labelKleur}`}>{labelTekst}</span>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Laatste update: {formatDatum(kaart.laatsteJob?.completed_at ?? kaart.laatsteJob?.created_at)}
        </p>
        {kaart.laatsteJob && (
          <p className="text-xs text-muted-foreground mt-1">
            {kaart.laatsteJob.rows_processed} rijen verwerkt
            {kaart.laatsteJob.rows_failed > 0 && `, ${kaart.laatsteJob.rows_failed} mislukt`}
          </p>
        )}
        {kaart.overrideMessage && (
          <p className="text-xs text-muted-foreground mt-1">{kaart.overrideMessage}</p>
        )}
        {kaart.mislukteJob && (
          <p className="text-xs text-red-600 mt-1" title={kaart.mislukteJob.error_message ?? undefined}>
            Mislukte poging: {formatDatum(kaart.mislukteJob.completed_at ?? kaart.mislukteJob.created_at)}
            {kaart.mislukteJob.error_message ? ` — ${String(kaart.mislukteJob.error_message).slice(0, 160)}` : ""}
          </p>
        )}
        {kaart.connStatus && (
          <p className={`text-xs mt-1 ${kaart.connStatus === "ok" ? "text-emerald-600" : "text-muted-foreground"}`}>
            {VERBINDING_LABEL[kaart.connStatus]}
            {kaart.connMessage && kaart.connStatus !== "ok" ? ` — ${kaart.connMessage}` : ""}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function KpiCard({ icon: Icon, label, value, kleur }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string | number; kleur?: string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-md ${kleur ?? "bg-primary/10 text-primary"}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-xs text-muted-foreground">{label}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const HISTORY_PAGE_SIZE = 200;
const HISTORY_MAX_LIMIT = 500;

export default function DataIntegratie() {
  const [drsStatus, setDrsStatus] = useState<ConnStatus | null>(null);
  const [priceshapeStatus, setPriceshapeStatus] = useState<ConnStatus | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);
  const [bronFilter, setBronFilter] = useState<string>("alle");
  const [statusFilter, setStatusFilter] = useState<string>("alle");
  const [historyLimit, setHistoryLimit] = useState<number>(HISTORY_PAGE_SIZE);
  const [bronnen, setBronnen] = useState<DataSourceRow[] | null>(null);
  const [bronnenLoading, setBronnenLoading] = useState(true);

  const laadBronnen = useCallback(async () => {
    setBronnenLoading(true);
    try {
      const resp = await fetch(`${BASE}/api/data-sources`, {
        headers: getAuthHeaders(),
        signal: AbortSignal.timeout(60_000),
      });
      if (resp.ok) {
        const data = await resp.json();
        setBronnen(data.sources as DataSourceRow[]);
      }
    } catch {
      /* backend niet bereikbaar */
    } finally {
      setBronnenLoading(false);
    }
  }, []);

  useEffect(() => { laadBronnen(); }, [laadBronnen]);

  const { data: uploads, isLoading: uploadsLoading, isFetching: uploadsFetching } = useListUploads({ limit: historyLimit });
  const { data: exportHistory, isLoading: exportLoading } = useGetExportHistory({ limit: 100 });
  const { data: dataQuality } = useGetDataQuality();
  const { data: dashboardSummary } = useGetDashboardSummary();

  const fetchConnStatus = async () => {
    setLoadingConn(true);
    try {
      const resp = await fetch(`${BASE}/api/admin/sync/status`, { headers: getAuthHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        setDrsStatus(data.drs as ConnStatus);
      }
    } catch {
      /* geen toegang tot admin/sync — gebruiker is mogelijk geen admin */
    }
    try {
      const resp = await fetch(`${BASE}/api/uploads/priceshape/connection`, { headers: getAuthHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        setPriceshapeStatus(data as ConnStatus);
      }
    } catch {
      /* netwerk niet beschikbaar */
    } finally {
      setLoadingConn(false);
    }
  };

  useEffect(() => {
    fetchConnStatus();
  }, []);

  const jobs: any[] = (uploads as any[]) ?? [];

  const laatsteVoorBron = (predicate: (j: any) => boolean) => {
    const gefilterd = jobs.filter(predicate);
    if (gefilterd.length === 0) return null;
    return gefilterd.reduce((a, b) => (new Date(a.created_at) > new Date(b.created_at) ? a : b));
  };

  // PriceShape-kaart: ook de (automatische) feed-syncs meenemen, zodat een
  // mislukte poging van de scheduler zichtbaar is naast de laatste succesvolle sync.
  const isPriceShapeJob = (j: any) => j.source === "PriceShape" || j.upload_type === "api_sync_priceshape";
  const laatstePriceShape = laatsteVoorBron(isPriceShapeJob);
  const laatstePriceShapeMislukt = laatsteVoorBron((j) => isPriceShapeJob(j) && FOUT_STATUSSEN.has(j.status));
  const laatsteDrs = laatsteVoorBron((j) => j.source === "DRS");
  const laatsteExcel = laatsteVoorBron((j) => j.source === "Handmatig" && ["xlsx", "xls"].includes(j.file_type));
  const laatsteCsv = laatsteVoorBron((j) => j.source === "Handmatig" && j.file_type === "csv");
  const laatsteApiSync = laatsteVoorBron((j) => j.source === "API-Sync");

  const bronKaarten: BronKaart[] = [
    {
      key: "priceshape",
      label: "PriceShape",
      icon: Server,
      laatsteJob: laatstePriceShape,
      mislukteJob: laatstePriceShapeMislukt,
      connStatus: loadingConn ? undefined : (priceshapeStatus?.status ?? "not_configured"),
      connMessage: priceshapeStatus?.message,
    },
    { key: "drs", label: "DRS Datareport", icon: Database, laatsteJob: laatsteDrs },
    { key: "excel", label: "Excel-upload", icon: FileSpreadsheet, laatsteJob: laatsteExcel },
    { key: "csv", label: "CSV-upload", icon: FileText, laatsteJob: laatsteCsv },
    {
      key: "api-sync",
      label: "API-synchronisatie (DRS)",
      icon: Zap,
      laatsteJob: laatsteApiSync,
      // Zolang er nog nooit een API-sync heeft gedraaid, valt de kaart terug
      // op de live verbindingscheck zodat "Nog niet gekoppeld" direct zichtbaar is.
      overrideStatus: laatsteApiSync ? undefined : (loadingConn ? undefined : (drsStatus?.status ?? "not_configured")),
      overrideMessage: laatsteApiSync ? undefined : drsStatus?.message,
      connStatus: laatsteApiSync && !loadingConn ? (drsStatus?.status ?? "not_configured") : undefined,
      connMessage: laatsteApiSync ? drsStatus?.message : undefined,
    },
  ];

  const totaalWaarschuwingen = jobs.reduce((som, j) => som + ((j.warnings?.length) ?? 0), 0);
  const totaalFouten = jobs.reduce((som, j) => som + (j.rows_failed ?? 0), 0);
  const totaalBijgewerkt = jobs.reduce((som, j) => som + (j.rows_processed ?? 0), 0);
  const totaalProducten = (dataQuality as any)?.total_skus ?? (dashboardSummary as any)?.total_skus ?? 0;
  const totaalConcurrentiePrijzen = (dashboardSummary as any)?.total_competitor_prices ?? 0;

  const bronOpties = useMemo(() => {
    const set = new Set(jobs.map((j) => j.source).filter(Boolean));
    return Array.from(set) as string[];
  }, [jobs]);

  const statusOpties = useMemo(() => {
    const set = new Set(jobs.map((j) => j.status).filter(Boolean));
    return Array.from(set) as string[];
  }, [jobs]);

  const gefilterdeJobs = jobs.filter((j) => {
    if (bronFilter !== "alle" && j.source !== bronFilter) return false;
    if (statusFilter !== "alle" && j.status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Data Integratie</h1>
          <p className="text-muted-foreground mt-1">
            Bronoverstijgend overzicht van alle databronnen: PriceShape, DRS, Excel/CSV-uploads en API-synchronisaties.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <CardTitle>Integratiecentrum — alle databronnen</CardTitle>
              <CardDescription>
                Uniforme status per bron: verbinding, laatste/volgende sync, records, fouten, freshness en datakwaliteit.
                Connectors beheer je op de <Link href="/connectoren" className="text-primary hover:underline">connector-pagina</Link>.
              </CardDescription>
            </div>
            <button type="button" onClick={laadBronnen} className="text-xs text-primary hover:underline" disabled={bronnenLoading}>
              {bronnenLoading ? "Laden..." : "Vernieuwen"}
            </button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {bronnenLoading && !bronnen ? (
            <div className="p-6"><Skeleton className="h-48 w-full" /></div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Bron</TableHead>
                  <TableHead>Verbinding</TableHead>
                  <TableHead>Laatste sync</TableHead>
                  <TableHead>Volgende sync</TableHead>
                  <TableHead className="text-right">Records</TableHead>
                  <TableHead className="text-right">Waarschuwingen</TableHead>
                  <TableHead className="text-right">Fouten</TableHead>
                  <TableHead>Freshness</TableHead>
                  <TableHead>Kwaliteit</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(bronnen ?? []).map((b) => (
                  <TableRow key={b.key}>
                    <TableCell>
                      <div className="font-medium text-sm">{b.label}</div>
                      <div className="text-xs text-muted-foreground">{b.kind === "api" ? "API-connector" : "Handmatige upload"}</div>
                    </TableCell>
                    <TableCell>{verbindingBadge(b.connection_status, b.configured)}</TableCell>
                    <TableCell className="text-sm">
                      {formatDatum(b.last_sync_at)}
                      {b.last_failed_job && (
                        <div className="text-xs text-red-600 mt-0.5" title={b.last_failed_job.reason ?? undefined}>
                          Mislukte poging: {formatDatum(b.last_failed_job.failed_at)}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {b.next_sync_at ? formatDatum(b.next_sync_at) : <span className="text-muted-foreground">{b.sync_schedule === "handmatig" ? "Handmatig" : "—"}</span>}
                    </TableCell>
                    <TableCell className="text-right text-sm">
                      <span className="font-mono">{b.records.toLocaleString("nl-NL")}</span>
                      <span className="text-xs text-muted-foreground ml-1">{b.records_label}</span>
                    </TableCell>
                    <TableCell className="text-right text-sm">
                      {b.warnings_recent > 0 ? <span className="text-amber-600">{b.warnings_recent}</span> : 0}
                    </TableCell>
                    <TableCell className="text-right text-sm">
                      {b.failed_jobs_recent > 0 ? <span className="text-red-600">{b.failed_jobs_recent}</span> : 0}
                    </TableCell>
                    <TableCell className="text-sm">{freshnessCel(b.freshness_days)}</TableCell>
                    <TableCell className="text-sm">{kwaliteitCel(b.quality_score, b.open_issues)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        {bronKaarten.map((k) => (
          <BronStatusCard key={k.key} kaart={k} />
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KpiCard icon={Package} label="Producten" value={totaalProducten.toLocaleString("nl-NL")} />
        <KpiCard icon={Percent} label="Concurrentieprijzen" value={totaalConcurrentiePrijzen.toLocaleString("nl-NL")} />
        <KpiCard icon={RefreshCw} label="Bijgewerkte rijen" value={totaalBijgewerkt.toLocaleString("nl-NL")} kleur="bg-blue-50 text-blue-600" />
        <KpiCard icon={XCircle} label="Fouten" value={totaalFouten.toLocaleString("nl-NL")} kleur="bg-red-50 text-red-600" />
        <KpiCard icon={AlertTriangle} label="Waarschuwingen" value={totaalWaarschuwingen.toLocaleString("nl-NL")} kleur="bg-amber-50 text-amber-600" />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <CardTitle>Volledige importgeschiedenis</CardTitle>
              <CardDescription>Alle imports uit alle bronnen, filterbaar op bron en status.</CardDescription>
            </div>
            <div className="flex gap-2">
              <Select value={bronFilter} onValueChange={setBronFilter}>
                <SelectTrigger className="w-[160px] h-8 text-xs">
                  <SelectValue placeholder="Bron" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="alle">Alle bronnen</SelectItem>
                  {bronOpties.map((b) => (
                    <SelectItem key={b} value={b}>{b}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[160px] h-8 text-xs">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="alle">Alle statussen</SelectItem>
                  {statusOpties.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {uploadsLoading ? (
            <div className="p-6"><Skeleton className="h-64 w-full" /></div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tijdstip</TableHead>
                  <TableHead>Bron</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Bestand</TableHead>
                  <TableHead>Batch-ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Verwerkt</TableHead>
                  <TableHead className="text-right">Mislukt</TableHead>
                  <TableHead className="text-right">Duplicaten</TableHead>
                  <TableHead className="text-right">Waarschuwingen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {gefilterdeJobs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={10} className="text-center text-muted-foreground py-8">
                      Geen imports gevonden voor deze filters.
                    </TableCell>
                  </TableRow>
                ) : (
                  gefilterdeJobs.map((j) => (
                    <TableRow key={j.id}>
                      <TableCell className="text-sm">{formatDatum(j.created_at)}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs">{j.source ?? "Onbekend"}</Badge>
                      </TableCell>
                      <TableCell className="text-sm font-mono text-xs">{j.upload_type}</TableCell>
                      <TableCell className="text-sm truncate max-w-[200px]" title={j.filename}>{j.filename}</TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground" title={j.batch_id ?? undefined}>
                        {j.batch_id ? j.batch_id.slice(0, 8) : "—"}
                      </TableCell>
                      <TableCell>{statusBadge(j.status)}</TableCell>
                      <TableCell className="text-right text-sm">{j.rows_processed}</TableCell>
                      <TableCell className="text-right text-sm">
                        {j.rows_failed > 0 ? <span className="text-red-600">{j.rows_failed}</span> : j.rows_failed}
                      </TableCell>
                      <TableCell className="text-right text-sm">
                        {(j.rows_duplicates ?? 0) > 0 ? <span className="text-amber-600">{j.rows_duplicates}</span> : 0}
                      </TableCell>
                      <TableCell className="text-right text-sm">
                        {(j.warnings?.length ?? 0) > 0 ? (
                          <span className="text-amber-600">{j.warnings.length}</span>
                        ) : 0}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
          {!uploadsLoading && jobs.length > 0 && (
            <div className="flex items-center justify-between px-4 py-3 border-t text-xs text-muted-foreground">
              <span>
                {jobs.length} van maximaal {historyLimit} imports geladen
                {historyLimit >= HISTORY_MAX_LIMIT && jobs.length >= HISTORY_MAX_LIMIT
                  ? " (limiet bereikt — filter op bron/status om verder te verfijnen)"
                  : ""}
              </span>
              {jobs.length >= historyLimit && historyLimit < HISTORY_MAX_LIMIT && (
                <button
                  type="button"
                  onClick={() => setHistoryLimit((n) => Math.min(n + HISTORY_PAGE_SIZE, HISTORY_MAX_LIMIT))}
                  disabled={uploadsFetching}
                  className="text-primary hover:underline disabled:opacity-50"
                >
                  {uploadsFetching ? "Laden..." : "Meer laden"}
                </button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-primary" />
            Exportgeschiedenis
          </CardTitle>
          <CardDescription>Pushes en downloads van goedgekeurde prijsadviezen richting DRS.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {exportLoading ? (
            <div className="p-6"><Skeleton className="h-32 w-full" /></div>
          ) : ((exportHistory as any)?.items ?? []).length === 0 ? (
            <div className="p-8 text-center text-muted-foreground flex flex-col items-center">
              <CheckCircle2 className="w-8 h-8 text-muted-foreground/40 mb-2" />
              Nog geen exports uitgevoerd.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tijdstip</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Uitgevoerd door</TableHead>
                  <TableHead className="text-right">Aantal records</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {((exportHistory as any)?.items ?? []).slice(0, 20).map((e: any) => (
                  <TableRow key={e.id}>
                    <TableCell className="text-sm">{formatDatum(e.timestamp)}</TableCell>
                    <TableCell><Badge variant="outline" className="text-xs font-mono">{e.export_type}</Badge></TableCell>
                    <TableCell className="text-sm">{e.performed_by ?? "-"}</TableCell>
                    <TableCell className="text-right text-sm">{e.record_count}</TableCell>
                    <TableCell>
                      {e.status === "success"
                        ? <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">Geslaagd</Badge>
                        : <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Mislukt</Badge>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
