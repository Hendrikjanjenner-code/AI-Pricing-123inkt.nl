import { useState } from "react";
import { useListUploads } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { Upload, FileSpreadsheet, Loader2, CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronUp, Download } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

const TRAFFIC_TEMPLATE = "date,own_sku_id,sessions,pageviews,add_to_cart,orders,conversion_rate,channel\n2026-06-20,PAP001,142,198,23,8,0.056,organic";

const SALES_TEMPLATE = "date,own_sku_id,quantity_sold,revenue,cost,margin_pct\n2026-06-20,PAP001,75,337.00,135.00,0.60";

interface ImportResult {
  rows_processed: number;
  rows_failed: number;
  warnings: string[];
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

function SalesUploadCard() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [validating, setValidating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [rapport, setRapport] = useState<ValidationReport | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [bestand, setBestand] = useState<File | null>(null);
  const [toonVoorbeeld, setToonVoorbeeld] = useState(false);

  const downloadTemplate = () => {
    const blob = new Blob([SALES_TEMPLATE], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "verkoopdata_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleBestand = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBestand(f);
    setRapport(null);
    setImportResult(null);
    if (e.target) e.target.value = "";
    setValidating(true);
    try {
      const formData = new FormData();
      formData.append("file", f, f.name);
      const res = await fetch(`${BASE}/api/uploads/validate?upload_type=sales`, {
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
      const res = await fetch(`${BASE}/api/uploads/sales`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const result = await res.json();
      setImportResult({
        rows_processed: result.rows_processed ?? 0,
        rows_failed: result.rows_failed ?? 0,
        warnings: result.warnings ?? [],
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

  const kanImporteren = bestand && rapport && rapport.missing_fields.length === 0 && (rapport.kan_importeren ?? rapport.rows_valid > 0);

  const cardBorder = importResult
    ? (importResult.rows_failed > 0 ? "border-amber-300" : "border-emerald-300")
    : rapport
      ? (rapport.rows_failed > 0 ? "border-amber-300" : "border-emerald-300")
      : "";

  return (
    <Card className={cardBorder}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5 text-primary" />
              Verkoopdata
            </CardTitle>
            <CardDescription className="mt-1 text-sm">
              Dagelijkse verkoophistorie per SKU: aantallen, omzet, kosten en marge.
              Upload één CSV of XLSX-bestand rechtstreeks vanuit je ERP of exporttool.
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" className="h-7 text-xs shrink-0" onClick={downloadTemplate}>
            <Download className="w-3 h-3 mr-1" />Template
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1">
          {["date", "sku_id / own_sku_id", "quantity_sold", "revenue"].map(v => (
            <Badge key={v} className="text-xs font-mono bg-primary/10 text-primary border-primary/20">{v}</Badge>
          ))}
          {["cost", "margin_pct"].map(v => (
            <Badge key={v} variant="outline" className="text-xs font-mono">{v}</Badge>
          ))}
        </div>

        {importResult && (
          <div className="rounded-md border p-3 space-y-2 bg-muted/30">
            <div className="flex items-center gap-3 text-sm font-medium">
              <span className="text-emerald-600 flex items-center gap-1">
                <CheckCircle2 className="w-4 h-4" />Import voltooid
              </span>
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-emerald-600 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />{importResult.rows_processed} rijen verwerkt
              </span>
              {importResult.rows_failed > 0 && (
                <span className="text-amber-600 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />{importResult.rows_failed} mislukt
                </span>
              )}
            </div>
            {importResult.warnings.length > 0 && (
              <div className="space-y-1">
                {importResult.warnings.slice(0, 3).map((w, i) => (
                  <div key={i} className="text-xs text-amber-600 flex items-start gap-1">
                    <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}
                  </div>
                ))}
                {importResult.warnings.length > 3 && (
                  <div className="text-xs text-muted-foreground">+{importResult.warnings.length - 3} meer waarschuwingen</div>
                )}
              </div>
            )}
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
            {rapport.warnings.length > 0 && (
              <div className="text-xs text-amber-600 flex items-start gap-1">
                <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                {rapport.warnings[0]}{rapport.warnings.length > 1 ? ` (+${rapport.warnings.length - 1} waarschuwingen)` : ""}
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
            accept=".csv,.xlsx"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            onChange={handleBestand}
            disabled={validating || uploading}
          />
          <Button variant="outline" className="w-full text-sm" size="sm" disabled={validating || uploading}>
            {validating
              ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Valideren…</>
              : <><Upload className="mr-2 h-4 w-4" />{bestand ? bestand.name : "CSV of XLSX kiezen"}</>
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
              Sessies, pageviews en conversies per SKU/dag. Exporteer als CSV of XLSX uit Google Analytics 4
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
            accept=".csv,.xlsx"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            onChange={handleBestand}
            disabled={validating || uploading}
          />
          <Button variant="outline" className="w-full text-sm" size="sm" disabled={validating || uploading}>
            {validating
              ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Valideren…</>
              : <><Upload className="mr-2 h-4 w-4" />{bestand ? bestand.name : "CSV of XLSX kiezen"}</>
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
          Upload verkoopdata en GA4-traffic als CSV of XLSX. Elk bestand wordt gevalideerd vóór import.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SalesUploadCard />
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
