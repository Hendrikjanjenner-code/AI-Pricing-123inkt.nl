import { useState } from "react";
import { useListUploads } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { Upload, FileSpreadsheet, Loader2, CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronUp, Download, Archive } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

const BULK_TEMPLATE_BESTANDEN = [
  {
    naam: "products.csv",
    inhoud: "own_sku_id,product_name,brand,category,cost_price_exc_vat,current_sales_price_inc_vat,ean,min_price,max_price\nPAP001,Double A A4 80g,Double A,Paper,1.80,4.49,8711539000029,3.00,6.00",
  },
  {
    naam: "sales.csv",
    inhoud: "date,own_sku_id,quantity_sold,revenue_inc_vat,cost_exc_vat,margin_pct\n2026-06-20,PAP001,75,337.00,135.00,0.60",
  },
  {
    naam: "prices.csv",
    inhoud: "date,own_sku_id,price_inc_vat,cost_price_exc_vat\n2026-06-20,PAP001,4.49,1.80",
  },
  {
    naam: "competitor_prices.csv",
    inhoud: "date,own_sku_id,concurrent_naam,competitor_price_inc_vat,product_url\n2026-06-20,PAP001,Amazon,4.29,https://amazon.nl/...",
  },
  {
    naam: "promotions.csv",
    inhoud: "own_sku_id,promotie_type,korting_waarde,startdatum,einddatum,channel\nPAP001,percentage_off,10,2026-07-01,2026-07-07,online",
  },
];

const TRAFFIC_TEMPLATE = "date,own_sku_id,sessions,pageviews,add_to_cart,orders,conversion_rate,channel\n2026-06-20,PAP001,142,198,23,8,0.056,organic";

interface BulkResultaat {
  bestand: string;
  type: string;
  status: string;
  rows_processed?: number;
  rows_failed?: number;
  warnings?: string[];
  reden?: string;
}

interface BulkRapport {
  bestanden: number;
  totaal_verwerkt: number;
  totaal_mislukt: number;
  resultaten: BulkResultaat[];
}

interface ValidationReport {
  job_id?: number;
  upload_type?: string;
  rows_total: number;
  rows_valid: number;
  rows_failed: number;
  errors: Array<{ rij: number; veld: string; type?: string; bericht: string }>;
  errors_by_type?: Record<string, number>;
  missing_fields: string[];
  duplicate_skus: string[];
  preview: Record<string, string>[];
  warnings: string[];
  kan_importeren?: boolean;
}

function downloadZipTemplate() {
  import("jszip").then(({ default: JSZip }) => {
    const zip = new JSZip();
    BULK_TEMPLATE_BESTANDEN.forEach(f => zip.file(f.naam, f.inhoud));
    zip.generateAsync({ type: "blob" }).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "bulk_import_template.zip";
      a.click();
      URL.revokeObjectURL(url);
    });
  }).catch(() => {
    const content = BULK_TEMPLATE_BESTANDEN.map(f => `=== ${f.naam} ===\n${f.inhoud}`).join("\n\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "bulk_import_templates.txt";
    a.click();
    URL.revokeObjectURL(url);
  });
}

function BulkUploadCard() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const [bestand, setBestand] = useState<File | null>(null);
  const [rapport, setRapport] = useState<BulkRapport | null>(null);

  const handleBestand = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBestand(f);
    setRapport(null);
    if (e.target) e.target.value = "";
  };

  const handleImporteer = async () => {
    if (!bestand) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", bestand, bestand.name);
      const res = await fetch(`${BASE}/api/uploads/bulk`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const result: BulkRapport = await res.json();
      setRapport(result);
      queryClient.invalidateQueries({ queryKey: ["/api/uploads"] });
      toast({
        title: "Import geslaagd",
        description: `${result.totaal_verwerkt} rijen verwerkt uit ${result.bestanden} bestanden.`,
      });
    } catch (err: any) {
      toast({ title: "Import mislukt", description: err.message, variant: "destructive" });
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card className={rapport ? (rapport.totaal_mislukt > 0 ? "border-amber-300" : "border-emerald-300") : ""}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Archive className="h-5 w-5 text-primary" />
              Totaalimport (ZIP)
            </CardTitle>
            <CardDescription className="mt-1 text-sm">
              Upload één ZIP-bestand met al je data. Bevat CSV's voor producten, verkoophistorie,
              prijshistorie, concurrentenprijzen en promoties. De tool herkent elk bestand automatisch.
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" className="h-7 text-xs shrink-0" onClick={downloadZipTemplate}>
            <Download className="w-3 h-3 mr-1" />Voorbeeld ZIP
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="rounded-md bg-muted/40 border px-4 py-3 text-xs space-y-1 text-muted-foreground">
          <p className="font-medium text-foreground mb-1">Welke CSV's kun je meenemen in de ZIP?</p>
          {[
            ["products.csv", "Productcatalogus — sku_id, product_name, cost_price, current_price"],
            ["sales.csv", "Verkoophistorie — date, sku_id, quantity_sold, revenue"],
            ["prices.csv", "Eigen prijshistorie — date, sku_id, price_inc_vat"],
            ["competitor_prices.csv", "Concurrentenprijzen — date, sku_id, concurrent_naam, prijs"],
            ["promotions.csv", "Promoties — sku_id, promotie_type, korting, startdatum"],
          ].map(([naam, beschr]) => (
            <div key={naam} className="flex gap-2">
              <span className="font-mono shrink-0">{naam}</span>
              <span className="text-muted-foreground/70">— {beschr}</span>
            </div>
          ))}
          <p className="pt-1 text-muted-foreground/60">Bestandsnamen hoeven niet exact overeen te komen — de tool kijkt ook naar de kolomnamen.</p>
        </div>

        {rapport && (
          <div className="rounded-md border p-3 space-y-3 bg-muted/30">
            <div className="flex items-center gap-4 text-sm font-medium">
              <span>{rapport.bestanden} bestanden verwerkt</span>
              <span className="text-emerald-600 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />{rapport.totaal_verwerkt} rijen geïmporteerd
              </span>
              {rapport.totaal_mislukt > 0 && (
                <span className="text-amber-600 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />{rapport.totaal_mislukt} mislukt
                </span>
              )}
            </div>
            <div className="space-y-2">
              {rapport.resultaten.map((r, i) => (
                <div key={i} className="flex items-start justify-between gap-2 text-xs border-t pt-2 first:border-t-0 first:pt-0">
                  <div>
                    <span className="font-mono text-foreground">{r.bestand}</span>
                    {r.type !== "onbekend" && (
                      <Badge variant="outline" className="ml-2 text-[10px] py-0">{r.type}</Badge>
                    )}
                    {r.reden && <p className="text-amber-600 mt-0.5">{r.reden}</p>}
                    {r.warnings && r.warnings.length > 0 && (
                      <p className="text-muted-foreground mt-0.5">{r.warnings[0]}{r.warnings.length > 1 ? ` (+${r.warnings.length - 1})` : ""}</p>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    {r.status === "voltooid" && (
                      <span className="text-emerald-600 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />{r.rows_processed} rijen
                      </span>
                    )}
                    {r.status === "mislukt" && <span className="text-red-500 flex items-center gap-1"><XCircle className="w-3 h-3" />Mislukt</span>}
                    {r.status === "overgeslagen" && <span className="text-muted-foreground">Overgeslagen</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>

      <CardFooter className="flex gap-2 flex-wrap">
        <div className="relative flex-1">
          <Input
            type="file"
            accept=".zip"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            onChange={handleBestand}
            disabled={uploading}
          />
          <Button variant="outline" className="w-full text-sm" size="sm" disabled={uploading}>
            {uploading
              ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Importeren…</>
              : <><Archive className="mr-2 h-4 w-4" />{bestand ? bestand.name : "ZIP kiezen"}</>
            }
          </Button>
        </div>
        {bestand && !uploading && (
          <Button size="sm" onClick={handleImporteer} className="shrink-0">
            <Upload className="mr-2 h-4 w-4" />Importeer
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}

function TrafficUploadCard() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [validating, setValidating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [rapport, setRapport] = useState<ValidationReport | null>(null);
  const [bestand, setBestand] = useState<File | null>(null);
  const [toonVoorbeeld, setToonVoorbeeld] = useState(false);

  const downloadTemplate = () => {
    const blob = new Blob([TRAFFIC_TEMPLATE], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "traffic_ga4_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleBestand = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBestand(f);
    setRapport(null);
    if (e.target) e.target.value = "";
    setValidating(true);
    try {
      const formData = new FormData();
      formData.append("file", f, f.name);
      const res = await fetch(`${BASE}/api/uploads/validate?upload_type=traffic`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      setRapport(await res.json());
    } catch (err: any) {
      toast({ title: "Validatiefout", description: err.message, variant: "destructive" });
      setBestand(null);
    } finally {
      setValidating(false);
    }
  };

  const handleImporteer = async () => {
    if (!bestand) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", bestand, bestand.name);
      const res = await fetch(`${BASE}/api/uploads/traffic`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const result = await res.json();
      toast({ title: "Import geslaagd", description: `${result.rows_processed} rijen verwerkt.` });
      queryClient.invalidateQueries({ queryKey: ["/api/uploads"] });
      setRapport(null);
      setBestand(null);
    } catch (err: any) {
      toast({ title: "Import mislukt", description: err.message, variant: "destructive" });
    } finally {
      setUploading(false);
    }
  };

  const kanImporteren = bestand && rapport && rapport.missing_fields.length === 0 && (rapport.kan_importeren ?? rapport.rows_valid > 0);

  return (
    <Card className={rapport ? (rapport.rows_failed > 0 ? "border-amber-300" : "border-emerald-300") : ""}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5 text-primary" />
              Traffic & GA4
            </CardTitle>
            <CardDescription className="mt-1 text-sm">
              Sessies, pageviews en conversies per SKU/dag. Exporteer dit rechtstreeks uit Google Analytics 4
              of upload handmatig totdat de GA4-koppeling actief is.
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" className="h-7 text-xs shrink-0" onClick={downloadTemplate}>
            <Download className="w-3 h-3 mr-1" />Template
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1">
          {["date", "sku_id / own_sku_id", "sessions", "pageviews"].map(v => (
            <Badge key={v} className="text-xs font-mono bg-primary/10 text-primary border-primary/20">{v}</Badge>
          ))}
          {["add_to_cart", "orders", "conversion_rate", "channel"].map(v => (
            <Badge key={v} variant="outline" className="text-xs font-mono">{v}</Badge>
          ))}
        </div>

        {rapport && (
          <div className="rounded-md border p-3 space-y-2 bg-muted/30">
            <div className="flex items-center gap-3 text-sm">
              <span className="text-muted-foreground">Totaal:</span>
              <span className="font-medium">{rapport.rows_total} rijen</span>
              {rapport.rows_valid > 0 && (
                <span className="text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" />{rapport.rows_valid} geldig
                </span>
              )}
              {rapport.rows_failed > 0 && (
                <span className="text-red-500 flex items-center gap-1">
                  <XCircle className="w-3 h-3" />{rapport.rows_failed} ongeldig
                </span>
              )}
            </div>
            {rapport.missing_fields.length > 0 && (
              <div className="text-xs text-red-600 flex items-start gap-1">
                <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                Ontbrekende kolommen: {rapport.missing_fields.join(", ")}
              </div>
            )}
            {rapport.errors.length > 0 && (
              <div className="space-y-1">
                {rapport.errors.slice(0, 3).map((e, i) => (
                  <div key={i} className="text-xs text-red-500">Rij {e.rij}: {e.bericht}</div>
                ))}
                {rapport.errors.length > 3 && (
                  <div className="text-xs text-muted-foreground">+{rapport.errors.length - 3} meer fouten</div>
                )}
              </div>
            )}
            {rapport.preview.length > 0 && (
              <div>
                <button
                  className="text-xs text-muted-foreground flex items-center gap-1 hover:text-foreground"
                  onClick={() => setToonVoorbeeld(!toonVoorbeeld)}
                >
                  {toonVoorbeeld ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                  Preview ({rapport.preview.length} rijen)
                </button>
                {toonVoorbeeld && (
                  <div className="mt-2 overflow-x-auto">
                    <table className="text-xs w-full border-collapse">
                      <thead>
                        <tr>{Object.keys(rapport.preview[0]).map(k => (
                          <th key={k} className="text-left p-1 bg-muted font-mono border border-border/50">{k}</th>
                        ))}</tr>
                      </thead>
                      <tbody>
                        {rapport.preview.map((r, i) => (
                          <tr key={i}>{Object.values(r).map((v, j) => (
                            <td key={j} className="p-1 border border-border/50 font-mono truncate max-w-[120px]">{v}</td>
                          ))}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="flex gap-2 flex-wrap">
        <div className="relative flex-1">
          <Input
            type="file"
            accept=".csv"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            onChange={handleBestand}
            disabled={validating || uploading}
          />
          <Button variant="outline" className="w-full text-sm" size="sm" disabled={validating || uploading}>
            {validating
              ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Valideren…</>
              : <><Upload className="mr-2 h-4 w-4" />{bestand ? bestand.name : "CSV kiezen"}</>
            }
          </Button>
        </div>
        {rapport && kanImporteren && (
          <Button size="sm" onClick={handleImporteer} disabled={uploading} className="shrink-0">
            {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
            Importeer {rapport.rows_valid} rijen
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}

export default function Gegevensintegratie() {
  const { data: uploads, isLoading } = useListUploads();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Gegevensintegratie</h1>
        <p className="text-muted-foreground mt-1">
          Upload alle operationele data in één ZIP, of importeer GA4-traffic apart.
          Elk bestand wordt automatisch herkend — geen handmatige typekeuze nodig.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <BulkUploadCard />
        <TrafficUploadCard />
      </div>

      <div>
        <h2 className="text-lg font-bold mb-4">Recente importtaken</h2>
        <div className="border rounded-md bg-card">
          <div className="grid grid-cols-6 border-b bg-muted/50 p-3 text-sm font-medium text-muted-foreground">
            <div className="col-span-2">Bestandsnaam</div>
            <div>Type</div>
            <div>Status</div>
            <div className="text-right">Verwerkt / Mislukt</div>
            <div className="text-right">Datum</div>
          </div>
          <div className="divide-y">
            {isLoading ? (
              <div className="p-8 text-center text-muted-foreground">Laden...</div>
            ) : !uploads?.length ? (
              <div className="p-8 text-center text-muted-foreground">Geen recente uploads.</div>
            ) : uploads.map((job) => (
              <div key={job.id} className="grid grid-cols-6 items-center p-3 text-sm">
                <div className="col-span-2 font-medium truncate pr-4">{job.filename}</div>
                <div className="capitalize text-muted-foreground text-xs">{job.upload_type?.replace(/_/g, ' ')}</div>
                <div>
                  {job.status === 'completed' && <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200 text-xs">Voltooid</Badge>}
                  {job.status === 'processing' && <Badge variant="outline" className="bg-blue-50 text-blue-600 border-blue-200 text-xs">Verwerking</Badge>}
                  {job.status === 'failed' && <Badge variant="destructive" className="text-xs">Mislukt</Badge>}
                  {job.status === 'pending' && <Badge variant="secondary" className="text-xs">In wachtrij</Badge>}
                </div>
                <div className="text-right tabular-nums">
                  <span className="text-emerald-600">{job.rows_processed}</span>
                  {" / "}
                  <span className={job.rows_failed > 0 ? "text-destructive" : ""}>{job.rows_failed}</span>
                </div>
                <div className="text-right text-muted-foreground tabular-nums text-xs">
                  {new Date(job.created_at).toLocaleString('nl-NL')}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
