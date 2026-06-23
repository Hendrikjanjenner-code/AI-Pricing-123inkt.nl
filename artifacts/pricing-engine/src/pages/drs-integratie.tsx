import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertCircle, CheckCircle2, Circle, FileSpreadsheet, Loader2, RefreshCw, Server, Zap } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const VEREISTE_VELDEN = [
  { veld: "product_id", type: "string", beschr: "Interne product-ID in DRS", verplicht: true },
  { veld: "sku_code", type: "string", beschr: "EAN / artikelnummer", verplicht: true },
  { veld: "description", type: "string", beschr: "Productomschrijving", verplicht: true },
  { veld: "category_code", type: "string", beschr: "Categoriecode", verplicht: true },
  { veld: "cost_price", type: "decimal", beschr: "Inkoopprijs excl. BTW", verplicht: true },
  { veld: "selling_price", type: "decimal", beschr: "Huidige verkoopprijs incl. BTW", verplicht: true },
  { veld: "stock_qty", type: "integer", beschr: "Actuele voorraad", verplicht: true },
  { veld: "sales_qty_7d", type: "integer", beschr: "Verkopen afgelopen 7 dagen", verplicht: false },
  { veld: "sales_qty_30d", type: "integer", beschr: "Verkopen afgelopen 30 dagen", verplicht: false },
  { veld: "last_sale_date", type: "date", beschr: "Datum laatste verkoop (YYYY-MM-DD)", verplicht: false },
  { veld: "supplier_id", type: "string", beschr: "Leverancier-ID", verplicht: false },
];

const CHECKLIST = [
  { item: "Verbinding: DRS API-endpoint beschikbaar en bereikbaar vanuit deze omgeving" },
  { item: "Authenticatie: API-sleutel of OAuth2-token verkregen van DRS-beheerder" },
  { item: "Veldmapping: DRS-velden gemapt naar intern schema (zie tabel)" },
  { item: "Testimport: Klein subset (10 SKU's) succesvol geïmporteerd" },
  { item: "Go-live: Volledige Paper_Copy catalogus geïmporteerd en gevalideerd" },
];

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

export default function DrsIntegratie() {
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
        setConnStatus(data.drs as ConnStatus);
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
        setSyncResult(data.drs as SyncResult);
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
  const checklist = CHECKLIST.map((c, i) => ({ ...c, gereed: isConnected && i < 3 }));

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">DRS Integratie</h1>
          <p className="text-muted-foreground mt-1">
            Dynamisch Retail Systeem — productdata, verkopen en voorraad importeren.
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
            title={!connStatus?.configured ? "Configureer DRS_API_URL en DRS_API_KEY eerst" : ""}
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
              <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">DRS REST API</Badge>
            ) : (
              <Badge className="bg-blue-50 text-blue-600 border-blue-200">CSV Import</Badge>
            )}
            <p className="text-xs text-muted-foreground mt-2">
              {isConnected
                ? "Directe API-koppeling actief. Klik 'Nu synchroniseren' voor een handmatige pull."
                : "Gebruik de Gegevensintegratie-pagina om DRS-data handmatig te uploaden als CSV."}
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
              {["DRS_API_URL", "DRS_API_KEY", "DRS_TENANT_ID"].map((v) => (
                <div key={v} className="flex items-center gap-2">
                  <div className={`w-1.5 h-1.5 rounded-full ${connStatus?.configured ? "bg-emerald-500" : "bg-gray-300"}`} />
                  <span className="text-xs font-mono text-muted-foreground">{v}</span>
                  {v === "DRS_TENANT_ID" && <Badge variant="outline" className="text-xs py-0">optioneel</Badge>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {syncResult && (
        <Card className={syncResult.status === "ok" ? "border-emerald-200 bg-emerald-50/50" : syncResult.status === "not_configured" ? "border-amber-200 bg-amber-50/50" : "border-red-200 bg-red-50/50"}>
          <CardHeader className="pb-2">
            <CardTitle className={`text-base ${syncResult.status === "ok" ? "text-emerald-700" : syncResult.status === "not_configured" ? "text-amber-700" : "text-red-700"}`}>
              Synchronisatieresultaat DRS
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
          <CardTitle>Vereiste datavelden</CardTitle>
          <CardDescription>
            Deze velden worden verwacht vanuit DRS bij een API-koppeling of CSV-export.
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
          <CardTitle>Technische checklist</CardTitle>
          <CardDescription>
            Doorloop deze stappen om de DRS API-koppeling in te stellen.
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
              Zolang de DRS API-koppeling nog niet is gerealiseerd, exporteer data handmatig uit DRS als CSV
              en upload via <strong>Gegevensintegratie → Productcatalogus / Verkoopdata / Voorraad</strong>.
              Stel <code className="bg-amber-100 px-1 rounded text-xs">DRS_API_URL</code> en{" "}
              <code className="bg-amber-100 px-1 rounded text-xs">DRS_API_KEY</code> in als
              omgevingsvariabelen om de directe koppeling te activeren.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
