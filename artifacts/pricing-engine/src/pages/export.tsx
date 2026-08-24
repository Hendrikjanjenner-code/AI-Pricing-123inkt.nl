import { useState } from "react";
import {
  useExportRecommendations,
  getExportRecommendationsQueryKey,
  usePushRecommendationsToDrs,
  useGetExportHistory,
} from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { format } from "date-fns";
import { Download, Send, CheckCircle, AlertTriangle } from "lucide-react";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";

export default function Prijsexport() {
  const [datum, setDatum] = useState(format(new Date(), "yyyy-MM-dd"));
  const { toast } = useToast();
  const gf = useGlobalFilters();
  const filterParams = {
    hierarchy_node_ids: gf.hierarchy.length > 0 ? gf.hierarchy.map((n) => n.id).join(",") : undefined,
    brands: gf.brands.length > 0 ? gf.brands.join(",") : undefined,
    statuses: gf.statuses.length > 0 ? gf.statuses.join(",") : undefined,
    sku_query: gf.skuQuery.trim() !== "" ? gf.skuQuery.trim() : undefined,
  };
  const exportQuery = useExportRecommendations(
    { date: datum, ...filterParams },
    { query: { enabled: false, queryKey: getExportRecommendationsQueryKey({ date: datum, ...filterParams }) } },
  );
  const pushMut = usePushRecommendationsToDrs();
  const { data: history, refetch: refetchHistory } = useGetExportHistory({ limit: 20 });
  const [resultaat, setResultaat] = useState<{ url: string; count: number; filename: string } | null>(null);

  const handleExport = async () => {
    try {
      const { data: res } = await exportQuery.refetch();
      if (!res) throw new Error("Geen resultaat");
      setResultaat({ url: res.download_url, count: res.exported_count, filename: res.filename });
      toast({ title: "Export succesvol aangemaakt" });
    } catch {
      toast({ title: "Export mislukt", variant: "destructive" });
    }
  };

  const handlePushDrs = async () => {
    try {
      const res = await pushMut.mutateAsync({ params: { date: datum } });
      toast({ title: "Naar DRS gepusht", description: `${res.pushed_count} adviezen verwerkt.` });
      refetchHistory();
    } catch (err: any) {
      toast({
        title: "DRS-push mislukt",
        description: err?.body?.detail || "DRS is niet bereikbaar of gaf een fout terug.",
        variant: "destructive",
      });
      refetchHistory();
    }
  };

  const baseUrl = import.meta.env.BASE_URL;
  const downloadHref = (fmt: "csv" | "xlsx" | "xls") => {
    // CSV: gebruik de door de API teruggegeven URL — die bevat de exacte
    // filtercontext waarmee de export is voorbereid.
    if (fmt === "csv" && resultaat?.url) return `${baseUrl}${resultaat.url.replace(/^\//, "")}`;
    const p = new URLSearchParams({ date: datum });
    for (const [k, v] of Object.entries(filterParams)) if (v) p.set(k, v);
    const path = fmt === "csv" ? "download" : `download/${fmt}`;
    return `${baseUrl}api/exports/recommendations/${path}?${p.toString()}`;
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Prijsexport</h1>
        <p className="text-muted-foreground mt-1">Stuur goedgekeurde prijsadviezen naar DRS: via API-push of als bestand.</p>
      </div>

      <GlobalFilterBar />

      <Card>
        <CardHeader>
          <CardTitle>Export aanmaken</CardTitle>
          <CardDescription>Exporteert alle 'goedgekeurde' en 'overschreven' adviezen voor een specifieke datum.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2 max-w-sm">
            <Label htmlFor="datum">Doeldatum</Label>
            <Input id="datum" type="date" value={datum} onChange={(e) => setDatum(e.target.value)} />
          </div>

          <div className="flex flex-wrap gap-3">
            <Button onClick={handleExport} disabled={exportQuery.isFetching}>
              {exportQuery.isFetching ? "Controleren..." : "Export voorbereiden"}
            </Button>
            <Button onClick={handlePushDrs} disabled={pushMut.isPending} variant="default" className="bg-blue-600 hover:bg-blue-700">
              <Send className="w-4 h-4 mr-2" />
              {pushMut.isPending ? "Pushen naar DRS..." : "Push naar DRS (API)"}
            </Button>
          </div>

          {resultaat && (
            <div className="mt-4 p-6 bg-emerald-50 border border-emerald-200 rounded-md">
              <div className="flex items-center gap-3 text-emerald-800 font-medium mb-2">
                <CheckCircle className="w-5 h-5" /> {resultaat.count} goedgekeurde adviezen klaar voor export
              </div>
              <div className="flex flex-wrap gap-3">
                <Button className="bg-emerald-600 hover:bg-emerald-700 text-white" asChild>
                  <a href={downloadHref("csv")} download>
                    <Download className="w-4 h-4 mr-2" /> CSV downloaden
                  </a>
                </Button>
                <Button variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-100" asChild>
                  <a href={downloadHref("xlsx")} download>
                    <Download className="w-4 h-4 mr-2" /> XLSX downloaden
                  </a>
                </Button>
                <Button variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-100" asChild>
                  <a href={downloadHref("xls")} download>
                    <Download className="w-4 h-4 mr-2" /> XLS downloaden
                  </a>
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Exportgeschiedenis</CardTitle>
          <CardDescription>Elke API-push en bestand-download naar DRS, met status en foutdetails.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tijdstip</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Aantal</TableHead>
                <TableHead>Gebruiker</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Foutdetails</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history?.items?.length ? (
                history.items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{entry.timestamp ? format(new Date(entry.timestamp), "dd-MM-yyyy HH:mm") : "-"}</TableCell>
                    <TableCell className="uppercase text-xs font-medium">{entry.export_type}</TableCell>
                    <TableCell>{entry.record_count}</TableCell>
                    <TableCell>{entry.performed_by || "-"}</TableCell>
                    <TableCell>
                      {entry.status === "success" ? (
                        <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
                          <CheckCircle className="w-3 h-3 mr-1" /> Geslaagd
                        </Badge>
                      ) : (
                        <Badge variant="destructive">
                          <AlertTriangle className="w-3 h-3 mr-1" /> Mislukt
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground max-w-xs truncate">{entry.error_details || "-"}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-6">
                    Nog geen exports uitgevoerd.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
