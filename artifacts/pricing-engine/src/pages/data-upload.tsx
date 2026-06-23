import { useState } from "react";
import { useListUploads } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { Upload, FileSpreadsheet, Loader2, CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronUp, Download } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

const UPLOAD_TYPEN = [
  {
    id: "product_master",
    titel: "Productcatalogus (product_master)",
    beschr: "Volledige Paper_Copy productcatalogus. Accepteert ook pilot-aliassen (own_sku_id, current_sales_price_inc_vat, enz.)",
    endpoint: "/api/uploads/products",
    verplichte_velden: ["sku_id / own_sku_id", "product_name", "cost_price / cost_price_exc_vat", "current_price / current_sales_price_inc_vat"],
    optionele_velden: ["ean", "subcategory", "paper_size", "paper_weight_gsm", "sheets_per_pack", "is_private_label", "is_a_brand", "min_price", "max_price", "lifecycle_status"],
    voorbeeld: "own_sku_id,product_name,brand,category,cost_price_exc_vat,current_sales_price_inc_vat,ean,paper_size,paper_weight_gsm,sheets_per_pack\nPAP001,Double A A4 80g,Double A,Paper,1.80,4.49,8711539000029,A4,80,500",
  },
  {
    id: "sales_history",
    titel: "Verkoopgeschiedenis (sales_history)",
    beschr: "Historisch dagelijks verkoopvolume per SKU. Accepteert revenue_inc_vat / revenue_incl_vat als alias.",
    endpoint: "/api/uploads/sales",
    verplichte_velden: ["date", "sku_id / own_sku_id", "units_sold / quantity_sold", "revenue / revenue_inc_vat"],
    optionele_velden: ["cost / cost_exc_vat", "margin", "margin_pct"],
    voorbeeld: "date,own_sku_id,quantity_sold,revenue_inc_vat,cost_exc_vat,margin_pct\n2026-06-20,PAP001,75,337.00,135.00,0.60",
  },
  {
    id: "own_price_history",
    titel: "Eigen prijshistorie (own_price_history)",
    beschr: "Dagelijkse verkoopprijzen (incl. BTW) en kostprijzen (excl. BTW) per SKU.",
    endpoint: "/api/uploads/prices",
    verplichte_velden: ["date", "sku_id / own_sku_id", "price / price_inc_vat / verkoopprijs_incl_btw"],
    optionele_velden: ["cost_price / cost_price_exc_vat / inkoopprijs"],
    voorbeeld: "date,own_sku_id,price_inc_vat,cost_price_exc_vat\n2026-06-20,PAP001,4.49,1.80",
  },
  {
    id: "competitor_prices",
    titel: "Concurrentenprijzen (competitor_prices)",
    beschr: "Dagelijkse gescrapte of handmatig ingevoerde concurrentenprijzen (incl. BTW).",
    endpoint: "/api/uploads/competitor-prices",
    verplichte_velden: ["date", "sku_id / own_sku_id", "competitor_name / concurrent_naam", "price / competitor_price_inc_vat"],
    optionele_velden: ["url / product_url"],
    voorbeeld: "date,own_sku_id,concurrent_naam,competitor_price_inc_vat,product_url\n2026-06-20,PAP001,Amazon,4.29,https://amazon.nl/...",
  },
  {
    id: "traffic",
    titel: "Traffic & GA4 (traffic)",
    beschr: "Sessies, pageviews, conversies per SKU per dag per kanaal.",
    endpoint: "/api/uploads/traffic",
    verplichte_velden: ["date", "sku_id / own_sku_id", "sessions", "pageviews"],
    optionele_velden: ["add_to_cart", "orders", "conversion_rate", "channel", "device", "unique_visitors", "bounce_rate"],
    voorbeeld: "date,own_sku_id,sessions,pageviews,add_to_cart,orders,conversion_rate,channel\n2026-06-20,PAP001,142,198,23,8,0.056,organic",
  },
  {
    id: "promotions",
    titel: "Promoties (promotions)",
    beschr: "Actieve promoties per SKU met type, korting en looptijd.",
    endpoint: "/api/uploads/promotions",
    verplichte_velden: ["sku_id / own_sku_id", "promotion_type / promotie_type", "discount_value / korting_waarde", "start_date / startdatum"],
    optionele_velden: ["end_date / einddatum", "channel", "description"],
    voorbeeld: "own_sku_id,promotie_type,korting_waarde,startdatum,einddatum,channel\nPAP001,percentage_off,10,2026-07-01,2026-07-07,online",
  },
];

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

function UploadCard({ type }: { type: typeof UPLOAD_TYPEN[0] }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [validating, setValidating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [rapport, setRapport] = useState<ValidationReport | null>(null);
  const [bestand, setBestand] = useState<File | null>(null);
  const [toonVoorbeeld, setToonVoorbeeld] = useState(false);
  const [toonVelden, setToonVelden] = useState(false);

  // Extract the upload_type key from the endpoint URL (e.g. "/api/uploads/competitor-prices" → "competitor-prices")
  const uploadType = type.endpoint.split("/").pop() ?? "products";

  const handleBestand = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const bestandObj = e.target.files?.[0];
    if (!bestandObj) return;
    setBestand(bestandObj);
    setRapport(null);
    if (e.target) e.target.value = "";

    // Validate via backend — authoritative parsing with Python's csv.DictReader
    setValidating(true);
    try {
      const formData = new FormData();
      formData.append("file", bestandObj, bestandObj.name);
      const res = await fetch(`${BASE}/api/uploads/validate?upload_type=${uploadType}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const val: ValidationReport = await res.json();
      setRapport(val);
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
      const res = await fetch(`${BASE}${type.endpoint}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err);
      }
      const result = await res.json();
      toast({
        title: "Import geslaagd",
        description: `${result.rows_processed} rijen verwerkt${result.rows_failed > 0 ? `, ${result.rows_failed} mislukt` : ""}.`,
      });
      queryClient.invalidateQueries({ queryKey: ["/api/uploads"] });
      setRapport(null);
      setBestand(null);
    } catch (err: any) {
      toast({ title: "Import mislukt", description: err.message, variant: "destructive" });
    } finally {
      setUploading(false);
    }
  };

  const downloadTemplate = () => {
    const blob = new Blob([type.voorbeeld], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${type.id}_template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const kanImporteren = bestand && rapport && rapport.missing_fields.length === 0 && (rapport.kan_importeren ?? rapport.rows_valid > 0);

  return (
    <Card className={rapport ? (rapport.rows_failed > 0 ? "border-amber-300" : "border-emerald-300") : ""}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-sm flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4 text-primary" />
              {type.titel}
            </CardTitle>
            <CardDescription className="mt-1 text-xs">{type.beschr}</CardDescription>
          </div>
          <Button variant="ghost" size="sm" className="h-7 text-xs shrink-0" onClick={downloadTemplate}>
            <Download className="w-3 h-3 mr-1" />Template
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <button
          className="text-xs text-muted-foreground flex items-center gap-1 hover:text-foreground"
          onClick={() => setToonVelden(!toonVelden)}
        >
          {toonVelden ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          Verplichte velden ({type.verplichte_velden.length})
        </button>
        {toonVelden && (
          <div className="flex flex-wrap gap-1">
            {type.verplichte_velden.map(v => (
              <Badge key={v} className="text-xs font-mono bg-primary/10 text-primary border-primary/20">{v}</Badge>
            ))}
            {type.optionele_velden.map(v => (
              <Badge key={v} variant="outline" className="text-xs font-mono">{v}</Badge>
            ))}
          </div>
        )}

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
                Ontbrekende verplichte kolommen: {rapport.missing_fields.join(", ")}
              </div>
            )}

            {rapport.duplicate_skus.length > 0 && (
              <div className="text-xs text-amber-600 flex items-start gap-1">
                <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                Dubbele SKU's: {rapport.duplicate_skus.join(", ")}
              </div>
            )}

            {rapport.errors_by_type && Object.keys(rapport.errors_by_type).length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(rapport.errors_by_type).map(([type, count]) => (
                  <span key={type} className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-700 border border-red-200">
                    <XCircle className="w-3 h-3" />
                    {type.replace(/_/g, " ")}: {count}
                  </span>
                ))}
              </div>
            )}

            {rapport.errors.length > 0 && (
              <div className="space-y-1">
                {rapport.errors.slice(0, 5).map((e, i) => (
                  <div key={i} className="text-xs text-red-500">Rij {e.rij}: {e.bericht}</div>
                ))}
                {rapport.errors.length > 5 && (
                  <div className="text-xs text-muted-foreground">+{rapport.errors.length - 5} meer fouten</div>
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
                  Importpreview (eerste {rapport.preview.length} rijen)
                </button>
                {toonVoorbeeld && (
                  <div className="mt-2 overflow-x-auto">
                    <table className="text-xs w-full border-collapse">
                      <thead>
                        <tr>
                          {Object.keys(rapport.preview[0]).map(k => (
                            <th key={k} className="text-left p-1 bg-muted font-mono border border-border/50">{k}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rapport.preview.map((r, i) => (
                          <tr key={i}>
                            {Object.values(r).map((v, j) => (
                              <td key={j} className="p-1 border border-border/50 font-mono truncate max-w-[120px]">{v}</td>
                            ))}
                          </tr>
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
          Upload CSV-bestanden in de 6 pilotformaten. Elk bestand wordt gevalideerd voor import.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {UPLOAD_TYPEN.map((type) => (
          <UploadCard key={type.id} type={type} />
        ))}
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
