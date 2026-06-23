import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertCircle, CheckCircle2, Circle, FileSpreadsheet, Loader2, RefreshCw, Server, Zap } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const VEREISTE_VELDEN = [
  { veld: "sessions", type: "integer", beschr: "Sessies per SKU / categorie / dag", verplicht: true },
  { veld: "pageviews", type: "integer", beschr: "Paginaweergaven per SKU", verplicht: true },
  { veld: "add_to_cart", type: "integer", beschr: "Toevoegingen aan winkelwagen", verplicht: true },
  { veld: "orders", type: "integer", beschr: "Bestellingen vanuit deze pagina", verplicht: true },
  { veld: "conversion_rate", type: "float", beschr: "Conversieratio (orders / sessions)", verplicht: true },
  { veld: "channel", type: "string", beschr: "Verkeerskanaal: organic / paid / direct / email / social", verplicht: true },
  { veld: "device", type: "string", beschr: "Apparaattype: desktop / mobile / tablet", verplicht: false },
  { veld: "landing_page", type: "string", beschr: "Landingspagina-URL of slug (bv. /paper-a4-80g)", verplicht: false },
];

const CHECKLIST = [
  { item: "GA4-property ID opgehaald uit Google Analytics-beheercentrum" },
  { item: "Service account aangemaakt in Google Cloud Console met GA4 Viewer-recht" },
  { item: "Service account JSON-sleutelbestand veilig opgeslagen als omgevingsvariabele" },
  { item: "SKU's gemapt op GA4 item_id of pagina-slug (veldmapping gedocumenteerd)" },
  { item: "Testquery: 7 dagen traffic voor 5 test-SKU's succesvol opgehaald" },
  { item: "Go-live: Dagelijkse sync ingesteld voor volledige Paper_Copy catalogus" },
];

const CSV_VOORBEELD = `datum,sku_id,sessions,pageviews,add_to_cart,orders,conversion_rate,channel,device
2026-06-20,PAP001,142,198,23,8,0.056,organic,desktop
2026-06-20,PAP001,67,89,9,3,0.045,paid,mobile
2026-06-20,PAP002,88,112,15,5,0.057,organic,desktop`;

type ConnStatus = {
  configured: boolean;
  reachable: boolean;
  status: "ok" | "not_configured" | "unreachable" | "auth_error" | "error";
  message: string;
};

type SyncResult = {
  status: "ok" | "not_configured" | "error" | "skipped";
  message: string;
  counts: Record<string, number>;
};

function StatusDot({ status }: { status: ConnStatus["status"] | undefined }) {
  if (!status) return <div className="w-2 h-2 rounded-full bg-gray-300 animate-pulse" />;
  const colors: Record<string, string> = {
    ok: "bg-emerald-500",
    not_configured: "bg-gray-400",
    unreachable: "bg-red-500",
    auth_error: "bg-amber-500",
    error: "bg-red-500",
  };
  return <div className={`w-2 h-2 rounded-full ${colors[status] ?? "bg-gray-400"}`} />;
}

export default function Ga4Integratie() {
  const [connStatus, setConnStatus] = useState<ConnStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);

  const fetchStatus = async () => {
    setLoadingStatus(true);
    try {
      const resp = await fetch("/api/admin/sync/status", { headers: getAuthHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        setConnStatus(data.ga4 as ConnStatus);
      }
    } catch {
      /* netwerk niet beschikbaar */
    } finally {
      setLoadingStatus(false);
    }
  };

  const triggerSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const resp = await fetch("/api/admin/sync", {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (resp.ok) {
        const data = await resp.json();
        setSyncResult(data.ga4 as SyncResult);
        await fetchStatus();
      }
    } catch {
      setSyncResult({ status: "error", message: "Netwerkfout bij starten sync.", counts: {} });
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const statusLabel: Record<string, string> = {
    ok: "Verbonden",
    not_configured: "Niet geconfigureerd",
    unreachable: "Niet bereikbaar",
    auth_error: "Authenticatiefout",
    error: "Fout",
  };

  const isConnected = connStatus?.status === "ok";
  const checklist = CHECKLIST.map((c, i) => ({ ...c, gereed: isConnected && i < 4 }));

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">GA4 Integratie</h1>
          <p className="text-muted-foreground mt-1">
            Google Analytics 4 — sessies, conversies en traffic-kanalen per SKU koppelen.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchStatus}
            disabled={loadingStatus}
          >
            {loadingStatus ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            <span className="ml-1.5">Vernieuwen</span>
          </Button>
          <Button
            size="sm"
            onClick={triggerSync}
            disabled={syncing || !connStatus?.configured}
            title={!connStatus?.configured ? "Configureer GA4_PROPERTY_ID en GA4_SERVICE_ACCOUNT_KEY eerst" : ""}
          >
            {syncing ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Zap className="w-3.5 h-3.5" />
            )}
            <span className="ml-1.5">Nu synchroniseren</span>
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Server className="w-4 h-4 text-muted-foreground" />
              Verbindingsstatus
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              {loadingStatus ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
              ) : (
                <StatusDot status={connStatus?.status} />
              )}
              <span className={`font-medium ${isConnected ? "text-emerald-600" : "text-muted-foreground"}`}>
                {loadingStatus
                  ? "Controleren…"
                  : connStatus
                  ? statusLabel[connStatus.status] ?? connStatus.status
                  : "Niet gekoppeld"}
              </span>
            </div>
            {connStatus && !loadingStatus && (
              <p className="text-xs text-muted-foreground mt-2">{connStatus.message}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4 text-muted-foreground" />
              Huidige methode
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isConnected ? (
              <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">GA4 Data API v1</Badge>
            ) : (
              <Badge className="bg-blue-50 text-blue-600 border-blue-200">CSV Import</Badge>
            )}
            <p className="text-xs text-muted-foreground mt-2">
              {isConnected
                ? "Directe API-koppeling actief via service account. Klik 'Nu synchroniseren' voor een handmatige pull."
                : "Exporteer GA4-data als CSV en upload via Gegevensintegratie → Traffic."}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-muted-foreground" />
              Omgevingsvariabelen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {["GA4_PROPERTY_ID", "GA4_SERVICE_ACCOUNT_KEY"].map((v) => (
                <div key={v} className="flex items-center gap-2">
                  <div className={`w-1.5 h-1.5 rounded-full ${connStatus?.configured ? "bg-emerald-500" : "bg-gray-300"}`} />
                  <span className="text-xs font-mono text-muted-foreground">{v}</span>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              GA4_SERVICE_ACCOUNT_KEY: volledige JSON-string van het service account sleutelbestand.
            </p>
          </CardContent>
        </Card>
      </div>

      {syncResult && (
        <Card className={syncResult.status === "ok" ? "border-emerald-200 bg-emerald-50/50" : syncResult.status === "not_configured" ? "border-amber-200 bg-amber-50/50" : "border-red-200 bg-red-50/50"}>
          <CardHeader className="pb-2">
            <CardTitle className={`text-base ${syncResult.status === "ok" ? "text-emerald-700" : syncResult.status === "not_configured" ? "text-amber-700" : "text-red-700"}`}>
              Synchronisatieresultaat GA4
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm mb-2">{syncResult.message}</p>
            {Object.keys(syncResult.counts).length > 0 && (
              <div className="flex gap-4 flex-wrap">
                {Object.entries(syncResult.counts).map(([k, v]) => (
                  <div key={k} className="text-xs text-muted-foreground">
                    <span className="font-medium">{v}</span> {k.replace(/_/g, " ")}
                  </div>
                ))}
          </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Vereiste datavelden (8)</CardTitle>
          <CardDescription>
            Deze velden worden verwacht per SKU per dag, gesegmenteerd op kanaal en apparaat.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Veldnaam</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Omschrijving</TableHead>
                <TableHead>Verplicht</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {VEREISTE_VELDEN.map((v) => (
                <TableRow key={v.veld}>
                  <TableCell className="font-mono text-sm">{v.veld}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs font-mono">{v.type}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">{v.beschr}</TableCell>
                  <TableCell>
                    {v.verplicht
                      ? <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Verplicht</Badge>
                      : <Badge variant="outline" className="text-xs">Optioneel</Badge>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>CSV-voorbeeldformaat</CardTitle>
          <CardDescription>
            Gebruik dit formaat bij handmatige CSV-export uit GA4 Looker Studio of Data Export.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="bg-muted rounded-md p-4 text-xs font-mono overflow-x-auto whitespace-pre">
{CSV_VOORBEELD}
          </pre>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Technische checklist</CardTitle>
          <CardDescription>
            Doorloop deze stappen om de GA4 API-koppeling in te stellen.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {checklist.map((item, i) => (
              <li key={i} className="flex items-start gap-3">
                <div className="mt-0.5 shrink-0">
                  {item.gereed
                    ? <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    : <Circle className="w-5 h-5 text-muted-foreground/50" />}
                </div>
                <div>
                  <span className="text-sm font-medium mr-2 text-muted-foreground">Stap {i + 1}</span>
                  <span className="text-sm">{item.item}</span>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      {!isConnected && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-amber-700">
              <AlertCircle className="w-4 h-4" />
              Tijdelijke werkwijze
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-amber-700">
              Exporteer traffic-data wekelijks uit GA4 (Verkennen → Exporteren → CSV) en upload via{" "}
              <strong>Gegevensintegratie → Traffic</strong>. Stel{" "}
              <code className="bg-amber-100 px-1 rounded text-xs">GA4_PROPERTY_ID</code> en{" "}
              <code className="bg-amber-100 px-1 rounded text-xs">GA4_SERVICE_ACCOUNT_KEY</code>{" "}
              in als omgevingsvariabelen om de directe API-koppeling te activeren.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
