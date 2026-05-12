import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { TrendingDown, TrendingUp, AlertTriangle, CheckCircle2, XCircle, RefreshCw, Play, Bell } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

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

const ALERT_TYPE_NL: Record<string, string> = {
  COMPETITOR_PRICE_DROPPED: "Prijs gedaald",
  COMPETITOR_PRICE_INCREASED: "Prijs gestegen",
  LOW_PRICE_LOW_STOCK_RELIABILITY: "Lage prijs + lage CSRS",
  COMPETITOR_OUT_OF_STOCK: "Uit voorraad",
  COMPETITOR_BACK_IN_STOCK: "Terug op voorraad",
  COMPETITOR_LISTING_DISAPPEARED: "Listing verdwenen",
  COMPETITOR_NEW_ENTRY: "Nieuwe concurrent",
  COMPETITOR_PRICE_OUTLIER: "Prijsuitbijter",
  COMPETITOR_DELIVERY_WORSENED: "Levering verslechterd",
  COMPETITOR_STOCK_RELIABILITY_DECLINED: "CSRS gedaald",
};

const ALERT_ICON: Record<string, React.ReactElement> = {
  COMPETITOR_PRICE_DROPPED: <TrendingDown className="w-4 h-4 text-red-500" />,
  COMPETITOR_PRICE_INCREASED: <TrendingUp className="w-4 h-4 text-green-600" />,
  LOW_PRICE_LOW_STOCK_RELIABILITY: <AlertTriangle className="w-4 h-4 text-amber-500" />,
  COMPETITOR_OUT_OF_STOCK: <XCircle className="w-4 h-4 text-slate-400" />,
  COMPETITOR_BACK_IN_STOCK: <CheckCircle2 className="w-4 h-4 text-green-500" />,
  COMPETITOR_LISTING_DISAPPEARED: <XCircle className="w-4 h-4 text-red-400" />,
  COMPETITOR_NEW_ENTRY: <Bell className="w-4 h-4 text-blue-500" />,
  COMPETITOR_PRICE_OUTLIER: <AlertTriangle className="w-4 h-4 text-orange-500" />,
};

const SEVERITY_VARIANT: Record<string, string> = {
  hoog: "bg-red-100 text-red-800",
  middel: "bg-amber-100 text-amber-800",
  laag: "bg-slate-100 text-slate-700",
};

export default function ConcurrentieMonitoring() {
  const { toast } = useToast();
  const [data, setData] = useState<any>(null);
  const [laden, setLaden] = useState(true);
  const [alertType, setAlertType] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [resolved, setResolved] = useState("false");
  const [runBezig, setRunBezig] = useState(false);

  useEffect(() => { laadData(); }, [alertType, severity, resolved]);

  async function laadData() {
    setLaden(true);
    try {
      const params = new URLSearchParams();
      if (alertType !== "all") params.set("alert_type", alertType);
      if (severity !== "all") params.set("severity", severity);
      if (resolved !== "all") params.set("resolved", resolved);
      const d = await apiFetch(`/api/monitoring/alerts?${params}`);
      setData(d);
    } catch { toast({ title: "Fout bij laden", variant: "destructive" }); }
    setLaden(false);
  }

  async function runMonitoring() {
    setRunBezig(true);
    try {
      const r = await apiFetch("/api/monitoring/run", { method: "POST", body: JSON.stringify({}) });
      toast({ title: "Monitoring uitgevoerd", description: `${r.alerts_gegenereerd} alerts gegenereerd` });
      laadData();
    } catch { toast({ title: "Monitoring mislukt", variant: "destructive" }); }
    setRunBezig(false);
  }

  async function oplossen(alert_id: number) {
    try {
      await apiFetch(`/api/monitoring/resolve/${alert_id}`, { method: "POST" });
      toast({ title: "Alert opgelost" });
      laadData();
    } catch { toast({ title: "Fout", variant: "destructive" }); }
  }

  const samenvatting = data?.samenvatting || {};
  const hoofd_alerts = [
    { type: "COMPETITOR_PRICE_DROPPED", label: "Prijsdalingen", kleur: "text-red-600" },
    { type: "LOW_PRICE_LOW_STOCK_RELIABILITY", label: "Lage prijs + lage CSRS", kleur: "text-amber-600" },
    { type: "COMPETITOR_OUT_OF_STOCK", label: "Uit voorraad", kleur: "text-slate-600" },
    { type: "COMPETITOR_PRICE_OUTLIER", label: "Uitbijters", kleur: "text-orange-600" },
    { type: "COMPETITOR_NEW_ENTRY", label: "Nieuwe concurrenten", kleur: "text-blue-600" },
    { type: "COMPETITOR_LISTING_DISAPPEARED", label: "Listings verdwenen", kleur: "text-slate-500" },
  ];

  return (
    <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Concurrentie Monitoring</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Realtime alerts voor prijswijzigingen, voorraad en betrouwbaarheid van concurrenten.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={laadData}><RefreshCw className="w-4 h-4 mr-2" />Vernieuwen</Button>
            <Button size="sm" onClick={runMonitoring} disabled={runBezig}>
              <Play className="w-4 h-4 mr-2" />{runBezig ? "Bezig..." : "Monitoring uitvoeren"}
            </Button>
          </div>
        </div>

        {/* Alert-samenvatting */}
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
          {hoofd_alerts.map(a => (
            <Card key={a.type} className="cursor-pointer hover:shadow-sm transition-shadow"
              onClick={() => setAlertType(alertType === a.type ? "all" : a.type)}>
              <CardContent className="pt-3 pb-3 text-center">
                <div className={`text-2xl font-bold ${a.kleur}`}>{samenvatting[a.type] || 0}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{a.label}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Filters */}
        <div className="flex gap-3 bg-card border p-3 rounded-md">
          <Select value={alertType} onValueChange={setAlertType}>
            <SelectTrigger className="w-52"><SelectValue placeholder="Alle alert-types" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle types</SelectItem>
              {Object.entries(ALERT_TYPE_NL).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger className="w-36"><SelectValue placeholder="Ernst" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle ernst</SelectItem>
              <SelectItem value="hoog">Hoog</SelectItem>
              <SelectItem value="middel">Middel</SelectItem>
              <SelectItem value="laag">Laag</SelectItem>
            </SelectContent>
          </Select>
          <Select value={resolved} onValueChange={setResolved}>
            <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="false">Openstaand</SelectItem>
              <SelectItem value="true">Opgelost</SelectItem>
              <SelectItem value="all">Alle</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Alert-tabel */}
        {laden ? <Skeleton className="h-64 w-full" /> : (
          <div className="rounded-md border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8"></TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>SKU / Product</TableHead>
                  <TableHead>Concurrent</TableHead>
                  <TableHead>Melding</TableHead>
                  <TableHead>Ernst</TableHead>
                  <TableHead>Datum</TableHead>
                  <TableHead className="text-right">Actie</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.alerts?.map((a: any) => (
                  <TableRow key={a.alert_id} className={a.resolved ? "opacity-50" : ""}>
                    <TableCell>{ALERT_ICON[a.alert_type] || <Bell className="w-4 h-4 text-muted-foreground" />}</TableCell>
                    <TableCell className="text-xs font-medium">{ALERT_TYPE_NL[a.alert_type] || a.alert_type}</TableCell>
                    <TableCell>
                      {a.own_sku_id && (
                        <>
                          <div className="text-sm font-medium truncate max-w-[160px]">{a.product_naam || a.own_sku_id}</div>
                          <div className="text-xs text-muted-foreground font-mono">{a.own_sku_id}</div>
                        </>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{a.concurrent || "—"}</TableCell>
                    <TableCell className="text-sm max-w-[240px]">{a.message}</TableCell>
                    <TableCell>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${SEVERITY_VARIANT[a.severity] || ""}`}>
                        {a.severity}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{a.date}</TableCell>
                    <TableCell className="text-right">
                      {!a.resolved && (
                        <Button size="sm" variant="ghost" className="h-7 text-xs text-green-600" onClick={() => oplossen(a.alert_id)}>
                          <CheckCircle2 className="w-3 h-3 mr-1" />Oplossen
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {!data?.alerts?.length && (
                  <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                    <Bell className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    Geen alerts gevonden
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>
            {data?.totaal > 0 && (
              <div className="p-3 text-xs text-muted-foreground border-t bg-muted/20">
                {data.totaal} alerts totaal
              </div>
            )}
          </div>
        )}
    </div>
  );
}
