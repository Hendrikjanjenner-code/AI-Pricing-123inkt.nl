import { useState, useEffect } from "react";
import { useListUploads } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import {
  Upload, FileSpreadsheet, Loader2, CheckCircle2, XCircle,
  AlertTriangle, ChevronDown, ChevronUp, Download, Database,
  Clock, Package, Truck, TrendingUp, ArrowRight, ArrowLeft,
  ShieldAlert, History, RefreshCw, Wifi, WifiOff,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const TOKEN = () => localStorage.getItem("auth_token");

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

interface DrsValidation {
  bestandsnaam: string;
  sales: { rows_total: number; rows_valid: number; rows_failed: number; missing_columns: string[] };
  hierarchy: { rows_total: number; rows_valid: number; rows_failed: number; missing_columns: string[] };
  duplicate_skus: string[];
  errors: Array<{ tab: string; rij: number; veld: string; type: string; bericht: string }>;
  errors_by_type: Record<string, number>;
  warnings: string[];
  kan_importeren: boolean;
}

interface DrsImportResult {
  job_id: number;
  mode?: string;
  skus_created: number;
  skus_updated: number;
  skus_skipped?: number;
  skus_deleted?: number;
  hierarchy_created: number;
  hierarchy_updated: number;
  categories_created: number;
  categories_updated: number;
  rows_processed: number;
  warnings: string[];
  message: string;
}

const IMPORT_MODE_LABELS: Record<string, string> = {
  aanvullen: "Aanvullen (alleen nieuwe SKU's toevoegen)",
  updaten: "Updaten (standaard — nieuw toevoegen, bestaand bijwerken)",
  vervangen: "Volledig vervangen (verwijdert SKU's uit deze bron die niet in het bestand staan)",
};

// ── DRS Import Wizard ──────────────────────────────────────────────────────

function DrsWizardCard() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [stap, setStap] = useState<1 | 2 | 3>(1);
  const [validating, setValidating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [bestand, setBestand] = useState<File | null>(null);
  const [validatie, setValidatie] = useState<DrsValidation | null>(null);
  const [resultaat, setResultaat] = useState<DrsImportResult | null>(null);
  const [mode, setMode] = useState<"aanvullen" | "updaten" | "vervangen">("updaten");
  const [confirmPhrase, setConfirmPhrase] = useState("");
  const DRS_REPLACE_PHRASE = "VERVANG ALLE DRS DATA";

  const handleBestand = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".xlsx") && !f.name.toLowerCase().endsWith(".xls")) {
      toast({ title: "Verkeerd bestandstype", description: "Alleen XLSX- of XLS-bestanden worden ondersteund voor DRS import.", variant: "destructive" });
      return;
    }
    setBestand(f);
    setValidatie(null);
    setResultaat(null);
    setStap(1);
    setMode("updaten");
    setConfirmPhrase("");
    if (e.target) e.target.value = "";
    setValidating(true);
    try {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const res = await fetch(`${BASE}/api/uploads/drs/validate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN()}` },
        body: fd,
      });
      if (!res.ok) {
        const text = await res.text();
        let detail = text;
        try { detail = JSON.parse(text)?.detail || text; } catch {}
        throw new Error(detail.length > 400 ? detail.slice(0, 400) + "…" : detail);
      }
      const data: DrsValidation = await res.json();
      setValidatie(data);
      if (data.kan_importeren) setStap(2);
    } catch (err: any) {
      toast({ title: "Validatiefout", description: err.message, variant: "destructive" });
      setBestand(null);
    } finally {
      setValidating(false);
    }
  };

  const handleImporteer = async () => {
    if (!bestand) return;
    if (mode === "vervangen" && confirmPhrase !== DRS_REPLACE_PHRASE) {
      toast({ title: "Bevestiging vereist", description: `Typ exact: '${DRS_REPLACE_PHRASE}'`, variant: "destructive" });
      return;
    }
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", bestand, bestand.name);
      fd.append("mode", mode);
      if (mode === "vervangen") fd.append("confirm_phrase", confirmPhrase);
      const res = await fetch(`${BASE}/api/uploads/drs`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN()}` },
        body: fd,
      });
      if (!res.ok) {
        const text = await res.text();
        let detail = text;
        try { detail = JSON.parse(text)?.detail || text; } catch {}
        throw new Error(detail.length > 400 ? detail.slice(0, 400) + "…" : detail);
      }
      const data: DrsImportResult = await res.json();
      setResultaat(data);
      setStap(3);
      queryClient.invalidateQueries({ queryKey: ["/api/uploads"] });
    } catch (err: any) {
      toast({ title: "Import mislukt", description: err.message, variant: "destructive" });
    } finally {
      setImporting(false);
    }
  };

  const reset = () => {
    setStap(1);
    setBestand(null);
    setValidatie(null);
    setResultaat(null);
    setMode("updaten");
    setConfirmPhrase("");
  };

  const stapKleur = (n: number) =>
    stap > n ? "bg-emerald-500 text-white" : stap === n ? "bg-primary text-white" : "bg-muted text-muted-foreground";

  const hasErrors = validatie && (
    validatie.sales.missing_columns.length > 0 ||
    validatie.hierarchy.missing_columns.length > 0 ||
    validatie.errors.filter(e => e.type !== "inactief_artikel" && e.type !== "ontbrekend_merk" && e.type !== "ontbrekende_hierarchie").length > 0
  );

  return (
    <Card className={`col-span-full ${stap === 3 && resultaat ? "border-emerald-300" : stap === 2 ? "border-primary/40" : hasErrors ? "border-red-300" : ""}`}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="h-5 w-5 text-primary" />
              DRS Datareport
              <Badge className="bg-primary/10 text-primary border-primary/20 text-xs">Primaire databron</Badge>
            </CardTitle>
            <CardDescription className="mt-1 text-sm">
              Importeer het dagelijkse DRS Datareport als XLSX met tabbladen <strong>Sales</strong> en <strong>Hierarchy</strong>.
              SKU's, categorieën en de volledige hiërarchieboom worden automatisch gesynchroniseerd.
            </CardDescription>
          </div>
        </div>

        {/* Stap-indicator */}
        <div className="flex items-center gap-2 mt-3">
          {[
            { n: 1, label: "Bestand & validatie" },
            { n: 2, label: "Bevestig import" },
            { n: 3, label: "Resultaat" },
          ].map(({ n, label }, i) => (
            <div key={n} className="flex items-center gap-2">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${stapKleur(n)}`}>
                {stap > n ? <CheckCircle2 className="w-4 h-4" /> : n}
              </div>
              <span className={`text-xs ${stap === n ? "font-medium" : "text-muted-foreground"}`}>{label}</span>
              {i < 2 && <ArrowRight className="w-3 h-3 text-muted-foreground shrink-0" />}
            </div>
          ))}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Stap 1: Bestand kiezen + validatierapport */}
        {stap === 1 && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-1">
              {["Sales", "Hierarchy"].map(tab => (
                <Badge key={tab} className="text-xs font-mono bg-primary/10 text-primary border-primary/20">
                  Tabblad: {tab}
                </Badge>
              ))}
              {["productcode", "productnaam", "verkoopprijs", "inkoopprijs"].map(v => (
                <Badge key={v} variant="outline" className="text-xs font-mono">{v}</Badge>
              ))}
            </div>

            {validatie && (
              <div className="rounded-md border p-3 space-y-3 bg-muted/30">
                <div className="text-sm font-medium">Validatierapport: {validatie.bestandsnaam}</div>

                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="space-y-1">
                    <div className="font-medium text-xs text-muted-foreground">Tabblad Sales</div>
                    <div className="flex items-center gap-2">
                      <span>{validatie.sales.rows_total} rijen</span>
                      {validatie.sales.rows_valid > 0 && (
                        <span className="text-emerald-600 flex items-center gap-0.5 text-xs">
                          <CheckCircle2 className="w-3 h-3" />{validatie.sales.rows_valid} geldig
                        </span>
                      )}
                      {validatie.sales.rows_failed > 0 && (
                        <span className="text-amber-600 flex items-center gap-0.5 text-xs">
                          <AlertTriangle className="w-3 h-3" />{validatie.sales.rows_failed} aandacht
                        </span>
                      )}
                    </div>
                    {validatie.sales.missing_columns.length > 0 && (
                      <div className="text-xs text-red-600 flex items-start gap-1">
                        <XCircle className="w-3 h-3 mt-0.5 shrink-0" />
                        Kolommen ontbreken: {validatie.sales.missing_columns.join(", ")}
                      </div>
                    )}
                  </div>
                  <div className="space-y-1">
                    <div className="font-medium text-xs text-muted-foreground">Tabblad Hierarchy</div>
                    <div className="flex items-center gap-2">
                      <span>{validatie.hierarchy.rows_total} knooppunten</span>
                      {validatie.hierarchy.rows_valid > 0 && (
                        <span className="text-emerald-600 flex items-center gap-0.5 text-xs">
                          <CheckCircle2 className="w-3 h-3" />{validatie.hierarchy.rows_valid} geldig
                        </span>
                      )}
                    </div>
                    {validatie.hierarchy.missing_columns.length > 0 && (
                      <div className="text-xs text-red-600 flex items-start gap-1">
                        <XCircle className="w-3 h-3 mt-0.5 shrink-0" />
                        Kolommen ontbreken: {validatie.hierarchy.missing_columns.join(", ")}
                      </div>
                    )}
                  </div>
                </div>

                {validatie.duplicate_skus.length > 0 && (
                  <div className="text-xs text-amber-600 flex items-start gap-1">
                    <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                    {validatie.duplicate_skus.length} dubbele productcode(s): {validatie.duplicate_skus.slice(0, 3).join(", ")}
                    {validatie.duplicate_skus.length > 3 ? ` +${validatie.duplicate_skus.length - 3} meer` : ""}
                  </div>
                )}

                {Object.keys(validatie.errors_by_type).length > 0 && (
                  <div className="space-y-1">
                    <div className="text-xs font-medium text-muted-foreground">Gevonden meldingen:</div>
                    {Object.entries(validatie.errors_by_type).map(([type, count]) => (
                      <div key={type} className="flex items-center gap-2 text-xs">
                        <Badge variant="outline" className="text-xs py-0 font-mono">{type}</Badge>
                        <span className="text-muted-foreground">{count} rijen</span>
                      </div>
                    ))}
                  </div>
                )}

                {validatie.warnings.length > 0 && (
                  <div className="space-y-1">
                    {validatie.warnings.slice(0, 2).map((w, i) => (
                      <div key={i} className="text-xs text-amber-600 flex items-start gap-1">
                        <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}
                      </div>
                    ))}
                  </div>
                )}

                {validatie.kan_importeren && (
                  <div className="text-xs text-emerald-600 flex items-center gap-1 font-medium">
                    <CheckCircle2 className="w-4 h-4" /> Bestand is klaar voor import
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Stap 2: Samenvatting bevestigen */}
        {stap === 2 && validatie && (
          <div className="rounded-md border p-4 space-y-3 bg-primary/5 border-primary/20">
            <div className="text-sm font-medium">Importoverzicht — {validatie.bestandsnaam}</div>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="space-y-1">
                <div className="text-2xl font-bold text-primary">{validatie.sales.rows_valid}</div>
                <div className="text-xs text-muted-foreground">SKU's te importeren</div>
              </div>
              <div className="space-y-1">
                <div className="text-2xl font-bold text-primary">{validatie.hierarchy.rows_valid}</div>
                <div className="text-xs text-muted-foreground">Hiërarchiepunten</div>
              </div>
              <div className="space-y-1">
                <div className="text-2xl font-bold text-amber-500">{validatie.errors.length}</div>
                <div className="text-xs text-muted-foreground">Meldingen (worden overgeslagen)</div>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Bestaande SKU's worden bijgewerkt via upsert. Nieuwe SKU's worden aangemaakt.
              Alle wijzigingen worden gelogd in het auditlogboek.
            </p>

            <div className="space-y-3 border-t pt-3">
              <Label className="text-sm font-medium">Importmodus</Label>
              <RadioGroup value={mode} onValueChange={(v) => setMode(v as any)}>
                {(["aanvullen", "updaten", "vervangen"] as const).map(m => (
                  <div key={m} className="flex items-start gap-2">
                    <RadioGroupItem value={m} id={`drs-${m}`} className="mt-0.5" />
                    <Label htmlFor={`drs-${m}`} className="text-sm font-normal cursor-pointer">{IMPORT_MODE_LABELS[m]}</Label>
                  </div>
                ))}
              </RadioGroup>

              {mode === "vervangen" && (
                <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3 space-y-2">
                  <div className="text-xs text-amber-700 flex items-start gap-1 font-medium">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    Deze actie verwijdert alle bestaande DRS-SKU's die niet in dit bestand voorkomen.
                    Typ ter bevestiging exact: <code className="font-mono">{DRS_REPLACE_PHRASE}</code>
                  </div>
                  <Input
                    value={confirmPhrase}
                    onChange={e => setConfirmPhrase(e.target.value)}
                    placeholder={DRS_REPLACE_PHRASE}
                    className="font-mono text-sm"
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Stap 3: Resultaat */}
        {stap === 3 && resultaat && (
          <div className="rounded-md border p-4 space-y-3 bg-emerald-50/50 border-emerald-200">
            <div className="text-sm font-medium text-emerald-700 flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5" />DRS import geslaagd ({resultaat.mode || "updaten"})
            </div>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="space-y-1">
                <div className="text-xl font-bold text-emerald-600">{resultaat.skus_created + resultaat.skus_updated}</div>
                <div className="text-xs text-muted-foreground">SKU's ({resultaat.skus_created} nieuw, {resultaat.skus_updated} bijgewerkt)</div>
              </div>
              <div className="space-y-1">
                <div className="text-xl font-bold text-emerald-600">{resultaat.hierarchy_created + resultaat.hierarchy_updated}</div>
                <div className="text-xs text-muted-foreground">Hiërarchie-knooppunten</div>
              </div>
              <div className="space-y-1">
                <div className="text-xl font-bold text-emerald-600">{resultaat.categories_created + resultaat.categories_updated}</div>
                <div className="text-xs text-muted-foreground">Categorieën gesynchroniseerd</div>
              </div>
            </div>
            {((resultaat.skus_skipped ?? 0) > 0 || (resultaat.skus_deleted ?? 0) > 0) && (
              <div className="flex gap-4 text-xs text-muted-foreground">
                {(resultaat.skus_skipped ?? 0) > 0 && <span>{resultaat.skus_skipped} overgeslagen</span>}
                {(resultaat.skus_deleted ?? 0) > 0 && <span className="text-red-500">{resultaat.skus_deleted} verwijderd (vervangen-modus)</span>}
              </div>
            )}
            {resultaat.warnings.length > 0 && (
              <div className="space-y-1">
                {resultaat.warnings.slice(0, 3).map((w, i) => (
                  <div key={i} className="text-xs text-amber-600 flex items-start gap-1">
                    <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}
                  </div>
                ))}
                {resultaat.warnings.length > 3 && (
                  <div className="text-xs text-muted-foreground">+{resultaat.warnings.length - 3} meer waarschuwingen</div>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="flex gap-2 flex-wrap">
        {stap === 1 && (
          <div className="relative flex-1">
            <Input
              type="file"
              accept=".xlsx,.xls"
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              onChange={handleBestand}
              disabled={validating}
            />
            <Button variant="outline" className="w-full text-sm" size="sm" disabled={validating}>
              {validating
                ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Valideren…</>
                : <><Upload className="mr-2 h-4 w-4" />{bestand ? bestand.name : "XLSX of XLS kiezen (Sales + Hierarchy)"}</>
              }
            </Button>
          </div>
        )}

        {stap === 1 && validatie?.kan_importeren && (
          <Button size="sm" onClick={() => setStap(2)} className="shrink-0">
            Volgende stap <ArrowRight className="ml-1 h-4 w-4" />
          </Button>
        )}

        {stap === 2 && (
          <>
            <Button variant="outline" size="sm" onClick={() => setStap(1)}>
              <ArrowLeft className="mr-1 h-4 w-4" />Terug
            </Button>
            <Button
              size="sm"
              onClick={handleImporteer}
              disabled={importing || (mode === "vervangen" && confirmPhrase !== DRS_REPLACE_PHRASE)}
              className="ml-auto"
            >
              {importing
                ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Importeren…</>
                : <><CheckCircle2 className="mr-2 h-4 w-4" />Bevestig import {validatie?.sales.rows_valid} SKU's</>
              }
            </Button>
          </>
        )}

        {stap === 3 && (
          <Button variant="outline" size="sm" onClick={reset}>
            Nieuwe import
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}

// ── PriceShape connector & upload wizard ────────────────────────────────────

interface PriceShapeConnection {
  configured: boolean;
  reachable: boolean;
  status: string;
  message: string;
}

interface PriceShapeValidation {
  job_id: number;
  bestandsnaam: string;
  samenvatting: {
    rijen_totaal: number; rijen_geldig: number; rijen_ongeldig: number;
    unieke_concurrenten: number; skus_niet_gevonden: number;
  };
  errors: Array<{ rij: number; veld: string; type?: string; bericht: string }>;
  errors_by_type: Record<string, number>;
  warnings: string[];
  skus_niet_gevonden: string[];
  kan_importeren: boolean;
  preview: Record<string, string>[];
}

interface PriceShapeImportResult {
  job_id: number;
  mode: string;
  created: number;
  updated: number;
  skipped: number;
  removed: number;
  rows_processed: number;
  warnings: string[];
  skus_niet_gevonden: string[];
  message: string;
}

interface PriceShapeJobRow {
  id: number;
  filename: string;
  source: string;
  file_type: string | null;
  import_mode: string | null;
  status: string;
  rows_processed: number;
  rows_failed: number;
  error_message: string | null;
  warnings: string[];
  uploaded_by: string;
  created_at: string;
  completed_at: string | null;
}

const PRICESHAPE_REPLACE_PHRASE = "VERVANG ALLE PRICESHAPE DATA";

const PS_STATUS_BADGE: Record<string, { label: string; className: string }> = {
  nieuw: { label: "Nieuw", className: "bg-muted text-muted-foreground border-muted" },
  gevalideerd: { label: "Gevalideerd", className: "bg-blue-50 text-blue-600 border-blue-200" },
  geimporteerd: { label: "Geïmporteerd", className: "bg-emerald-50 text-emerald-600 border-emerald-200" },
  bijgewerkt: { label: "Bijgewerkt", className: "bg-emerald-50 text-emerald-600 border-emerald-200" },
  opgeslagen: { label: "Opgeslagen", className: "bg-emerald-50 text-emerald-600 border-emerald-200" },
  fout: { label: "Fout", className: "bg-red-50 text-red-600 border-red-200" },
};

async function priceshapeFetch(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...(init?.headers || {}), Authorization: `Bearer ${TOKEN()}` },
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed?.detail === "string" ? parsed.detail : (parsed?.detail?.message || JSON.stringify(parsed?.detail) || text);
    } catch {}
    throw new Error(detail.length > 500 ? detail.slice(0, 500) + "…" : detail);
  }
  return res.json();
}

function PriceShapeWizardCard() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [connection, setConnection] = useState<PriceShapeConnection | null>(null);
  const [connectionLoading, setConnectionLoading] = useState(true);
  const [jobs, setJobs] = useState<PriceShapeJobRow[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);

  const [bestand, setBestand] = useState<File | null>(null);
  const [validating, setValidating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [rapport, setRapport] = useState<PriceShapeValidation | null>(null);
  const [resultaat, setResultaat] = useState<PriceShapeImportResult | null>(null);
  const [mode, setMode] = useState<"aanvullen" | "updaten" | "vervangen">("updaten");
  const [confirmPhrase, setConfirmPhrase] = useState("");

  const laadConnection = async () => {
    setConnectionLoading(true);
    try {
      setConnection(await priceshapeFetch("/api/uploads/priceshape/connection"));
    } catch (e: any) {
      toast({ title: "Verbindingsstatus laden mislukt", description: e.message, variant: "destructive" });
    } finally {
      setConnectionLoading(false);
    }
  };

  const laadJobs = async () => {
    setJobsLoading(true);
    try {
      setJobs(await priceshapeFetch("/api/uploads/priceshape/jobs"));
    } catch (e: any) {
      toast({ title: "Importlog laden mislukt", description: e.message, variant: "destructive" });
    } finally {
      setJobsLoading(false);
    }
  };

  useEffect(() => { laadConnection(); laadJobs(); }, []);

  const handleBestand = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.toLowerCase().match(/\.(csv|xlsx|xls)$/)) {
      toast({ title: "Verkeerd bestandstype", description: "Alleen CSV-, XLSX- of XLS-bestanden worden ondersteund.", variant: "destructive" });
      return;
    }
    setBestand(f);
    setRapport(null);
    setResultaat(null);
    setMode("updaten");
    setConfirmPhrase("");
    if (e.target) e.target.value = "";

    setValidating(true);
    try {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const data = await priceshapeFetch("/api/uploads/priceshape/validate", { method: "POST", body: fd });
      setRapport(data);
      laadJobs();
    } catch (err: any) {
      toast({ title: "Validatiefout", description: err.message, variant: "destructive" });
      setBestand(null);
    } finally {
      setValidating(false);
    }
  };

  const handleImporteer = async () => {
    if (!bestand) return;
    if (mode === "vervangen" && confirmPhrase !== PRICESHAPE_REPLACE_PHRASE) {
      toast({ title: "Bevestiging vereist", description: `Typ exact: '${PRICESHAPE_REPLACE_PHRASE}'`, variant: "destructive" });
      return;
    }
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", bestand, bestand.name);
      fd.append("mode", mode);
      if (mode === "vervangen") fd.append("confirm_phrase", confirmPhrase);
      const data = await priceshapeFetch("/api/uploads/priceshape/import", { method: "POST", body: fd });
      setResultaat(data);
      toast({ title: "Import voltooid", description: data.message });
      laadJobs();
      queryClient.invalidateQueries({ queryKey: ["/api/uploads"] });
    } catch (err: any) {
      toast({ title: "Import mislukt", description: err.message, variant: "destructive" });
    } finally {
      setImporting(false);
    }
  };

  const reset = () => {
    setBestand(null);
    setRapport(null);
    setResultaat(null);
    setMode("updaten");
    setConfirmPhrase("");
  };

  const previewKolommen = rapport?.preview?.length ? Object.keys(rapport.preview[0]) : [];

  return (
    <Card className={`col-span-full ${rapport ? (rapport.kan_importeren ? "border-emerald-300" : "border-red-300") : ""}`}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="h-5 w-5 text-primary" />
              PriceShape
              <Badge className="bg-primary/10 text-primary border-primary/20 text-xs">Concurrentiedata</Badge>
              {connectionLoading ? (
                <Badge variant="outline" className="text-xs">Verbinding controleren…</Badge>
              ) : connection?.reachable ? (
                <Badge className="bg-emerald-50 text-emerald-600 border-emerald-200 text-xs flex items-center gap-1">
                  <Wifi className="w-3 h-3" />Verbonden
                </Badge>
              ) : connection?.configured ? (
                <Badge className="bg-amber-50 text-amber-600 border-amber-200 text-xs flex items-center gap-1">
                  <WifiOff className="w-3 h-3" />Niet bereikbaar
                </Badge>
              ) : (
                <Badge variant="outline" className="text-xs flex items-center gap-1 text-muted-foreground">
                  <WifiOff className="w-3 h-3" />Niet geconfigureerd
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="mt-1 text-sm">
              Importeer concurrentieprijzen van PriceShape als CSV, XLSX of XLS. Rijen matchen op
              SKU, EAN of OEM/MPN. Kolommen: sku/ean/oem, competitor_name, competitor_price, timestamp.
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" className="h-7 text-xs shrink-0" onClick={() => { laadConnection(); laadJobs(); }}>
            <RefreshCw className="w-3 h-3 mr-1" />Vernieuwen
          </Button>
        </div>
        {connection && !connectionLoading && (
          <p className="text-xs text-muted-foreground">{connection.message}</p>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-1">
          {["sku / ean / oem", "competitor_name", "competitor_price", "timestamp"].map(v => (
            <Badge key={v} className="text-xs font-mono bg-primary/10 text-primary border-primary/20">{v}</Badge>
          ))}
          {["import_source"].map(v => (
            <Badge key={v} variant="outline" className="text-xs font-mono">{v}</Badge>
          ))}
        </div>

        {validating && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />Bestand wordt gevalideerd…
          </div>
        )}

        {rapport && (
          <div className="rounded-md border p-4 space-y-3 bg-muted/30">
            <div className="text-sm font-medium">Validatierapport: {rapport.bestandsnaam}</div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
              <div><div className="text-lg font-bold">{rapport.samenvatting.rijen_totaal}</div><div className="text-xs text-muted-foreground">Rijen totaal</div></div>
              <div><div className="text-lg font-bold text-emerald-600">{rapport.samenvatting.rijen_geldig}</div><div className="text-xs text-muted-foreground">Geldig</div></div>
              <div><div className="text-lg font-bold text-red-500">{rapport.samenvatting.rijen_ongeldig}</div><div className="text-xs text-muted-foreground">Ongeldig</div></div>
              <div><div className="text-lg font-bold">{rapport.samenvatting.unieke_concurrenten}</div><div className="text-xs text-muted-foreground">Concurrenten</div></div>
              <div><div className="text-lg font-bold text-amber-500">{rapport.samenvatting.skus_niet_gevonden}</div><div className="text-xs text-muted-foreground">SKU's niet gevonden</div></div>
            </div>

            {rapport.skus_niet_gevonden.length > 0 && (
              <div className="text-xs text-amber-600 flex items-start gap-1">
                <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                Niet gevonden: {rapport.skus_niet_gevonden.slice(0, 5).join(", ")}
                {rapport.skus_niet_gevonden.length > 5 ? ` +${rapport.skus_niet_gevonden.length - 5} meer` : ""}
              </div>
            )}

            {Object.keys(rapport.errors_by_type).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {Object.entries(rapport.errors_by_type).map(([type, count]) => (
                  <Badge key={type} variant="outline" className="text-xs font-mono">{type}: {count}</Badge>
                ))}
              </div>
            )}

            {rapport.warnings.length > 0 && (
              <div className="space-y-1">
                {rapport.warnings.slice(0, 5).map((w, i) => (
                  <div key={i} className="text-xs text-amber-600 flex items-start gap-1">
                    <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}
                  </div>
                ))}
              </div>
            )}

            {rapport.kan_importeren ? (
              <div className="text-xs text-emerald-600 flex items-center gap-1 font-medium">
                <CheckCircle2 className="w-4 h-4" /> Bestand is klaar voor import
              </div>
            ) : (
              <div className="text-xs text-red-600 flex items-center gap-1 font-medium">
                <XCircle className="w-4 h-4" /> Los eerst de foutmeldingen op voordat je importeert
              </div>
            )}
          </div>
        )}

        {previewKolommen.length > 0 && (
          <div className="space-y-2">
            <div className="text-sm font-medium">Voorbeeld — eerste {rapport!.preview.length} rijen</div>
            <div className="border rounded-md overflow-x-auto max-h-56">
              <Table>
                <TableHeader>
                  <TableRow>
                    {previewKolommen.map(k => <TableHead key={k} className="whitespace-nowrap text-xs font-mono">{k}</TableHead>)}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rapport!.preview.map((row, i) => (
                    <TableRow key={i}>
                      {previewKolommen.map(k => (
                        <TableCell key={k} className="whitespace-nowrap text-xs">{row[k] || "—"}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}

        {rapport?.kan_importeren && !resultaat && (
          <div className="space-y-3 border-t pt-4">
            <Label className="text-sm font-medium">Importmodus</Label>
            <RadioGroup value={mode} onValueChange={(v) => setMode(v as any)}>
              {(["aanvullen", "updaten", "vervangen"] as const).map(m => (
                <div key={m} className="flex items-start gap-2">
                  <RadioGroupItem value={m} id={`ps-${m}`} className="mt-0.5" />
                  <Label htmlFor={`ps-${m}`} className="text-sm font-normal cursor-pointer">{IMPORT_MODE_LABELS[m]}</Label>
                </div>
              ))}
            </RadioGroup>

            {mode === "vervangen" && (
              <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3 space-y-2">
                <div className="text-xs text-amber-700 flex items-start gap-1 font-medium">
                  <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
                  Deze actie verwijdert alle bestaande PriceShape-concurrentieprijzen die niet in dit bestand voorkomen.
                  Typ ter bevestiging exact: <code className="font-mono">{PRICESHAPE_REPLACE_PHRASE}</code>
                </div>
                <Input
                  value={confirmPhrase}
                  onChange={e => setConfirmPhrase(e.target.value)}
                  placeholder={PRICESHAPE_REPLACE_PHRASE}
                  className="font-mono text-sm"
                />
              </div>
            )}
          </div>
        )}

        {resultaat && (
          <div className="rounded-md border p-4 space-y-2 bg-emerald-50/50 border-emerald-200">
            <div className="text-sm font-medium text-emerald-700 flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5" />{resultaat.message}
            </div>
            <div className="grid grid-cols-4 gap-4 text-sm">
              <div><div className="text-xl font-bold text-emerald-600">{resultaat.created}</div><div className="text-xs text-muted-foreground">Nieuw</div></div>
              <div><div className="text-xl font-bold text-emerald-600">{resultaat.updated}</div><div className="text-xs text-muted-foreground">Bijgewerkt</div></div>
              <div><div className="text-xl font-bold text-muted-foreground">{resultaat.skipped}</div><div className="text-xs text-muted-foreground">Overgeslagen</div></div>
              <div><div className="text-xl font-bold text-red-500">{resultaat.removed}</div><div className="text-xs text-muted-foreground">Verwijderd</div></div>
            </div>
          </div>
        )}
      </CardContent>

      <CardFooter className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[240px]">
          <Input
            type="file"
            accept=".csv,.xlsx,.xls"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            onChange={handleBestand}
            disabled={validating || importing}
          />
          <Button variant="outline" className="w-full text-sm" size="sm" disabled={validating || importing}>
            {validating
              ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Valideren…</>
              : <><Upload className="mr-2 h-4 w-4" />{bestand ? bestand.name : "CSV, XLSX of XLS kiezen"}</>
            }
          </Button>
        </div>

        {rapport?.kan_importeren && !resultaat && (
          <Button
            size="sm"
            onClick={handleImporteer}
            disabled={importing || (mode === "vervangen" && confirmPhrase !== PRICESHAPE_REPLACE_PHRASE)}
            className="ml-auto"
          >
            {importing
              ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Importeren…</>
              : <><CheckCircle2 className="mr-2 h-4 w-4" />Import uitvoeren</>
            }
          </Button>
        )}

        {resultaat && (
          <Button variant="outline" size="sm" onClick={reset} className="ml-auto">
            Nieuwe import
          </Button>
        )}
      </CardFooter>

      {jobs.length > 0 && (
        <CardContent className="pt-0">
          <div className="border-t pt-4">
            <div className="text-sm font-medium flex items-center gap-2 mb-2">
              <History className="w-4 h-4" />PriceShape-importlog
            </div>
            <div className="border rounded-md overflow-x-auto max-h-64">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Bestand</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Modus</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Verwerkt</TableHead>
                    <TableHead className="text-right">Mislukt</TableHead>
                    <TableHead>Door</TableHead>
                    <TableHead className="text-right">Datum</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobsLoading ? (
                    <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground text-xs py-4">Laden…</TableCell></TableRow>
                  ) : jobs.slice(0, 10).map(job => {
                    const badge = PS_STATUS_BADGE[job.status] || { label: job.status, className: "" };
                    return (
                      <TableRow key={job.id}>
                        <TableCell className="text-xs font-medium truncate max-w-[160px]">{job.filename}</TableCell>
                        <TableCell className="text-xs uppercase text-muted-foreground">{job.file_type || "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{job.import_mode || "—"}</TableCell>
                        <TableCell><Badge variant="outline" className={`text-xs ${badge.className}`}>{badge.label}</Badge></TableCell>
                        <TableCell className="text-right text-xs tabular-nums">{job.rows_processed}</TableCell>
                        <TableCell className="text-right text-xs tabular-nums">
                          <span className={job.rows_failed > 0 ? "text-red-500" : ""}>{job.rows_failed}</span>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{job.uploaded_by}</TableCell>
                        <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                          {new Date(job.created_at).toLocaleString("nl-NL")}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ── Standard upload card (reusable) ────────────────────────────────────────

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
        headers: { Authorization: `Bearer ${TOKEN()}` },
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
        headers: { Authorization: `Bearer ${TOKEN()}` },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const result = await res.json();
      setImportResult({ rows_processed: result.rows_processed ?? 0, rows_failed: result.rows_failed ?? 0, warnings: result.warnings ?? [] });
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
    <Card className={importResult ? (importResult.rows_failed > 0 ? "border-amber-300" : "border-emerald-300") : rapport ? (rapport.rows_failed > 0 ? "border-amber-300" : "border-emerald-300") : ""}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5 text-primary" />
              Verkoopdata
            </CardTitle>
            <CardDescription className="mt-1 text-sm">
              Dagelijkse verkoophistorie per SKU: aantallen, omzet, kosten en marge.
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
              <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-4 h-4" />Import voltooid</span>
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />{importResult.rows_processed} rijen verwerkt</span>
              {importResult.rows_failed > 0 && (
                <span className="text-amber-600 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{importResult.rows_failed} mislukt</span>
              )}
            </div>
            {importResult.warnings.length > 0 && (
              <div className="space-y-1">
                {importResult.warnings.slice(0, 3).map((w, i) => (
                  <div key={i} className="text-xs text-amber-600 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}</div>
                ))}
                {importResult.warnings.length > 3 && <div className="text-xs text-muted-foreground">+{importResult.warnings.length - 3} meer waarschuwingen</div>}
              </div>
            )}
          </div>
        )}
        {rapport && (
          <div className="rounded-md border p-3 space-y-2 bg-muted/30">
            <div className="flex items-center gap-3 text-sm">
              <span className="text-muted-foreground">Totaal:</span>
              <span className="font-medium">{rapport.rows_total} rijen</span>
              {rapport.rows_valid > 0 && <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />{rapport.rows_valid} geldig</span>}
              {rapport.rows_failed > 0 && <span className="text-red-500 flex items-center gap-1"><XCircle className="w-3 h-3" />{rapport.rows_failed} ongeldig</span>}
            </div>
            {rapport.missing_fields.length > 0 && (
              <div className="text-xs text-red-600 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />Ontbrekende kolommen: {rapport.missing_fields.join(", ")}</div>
            )}
            {rapport.errors.length > 0 && (
              <div className="space-y-1">
                {rapport.errors.slice(0, 3).map((e, i) => <div key={i} className="text-xs text-red-500">Rij {e.rij}: {e.bericht}</div>)}
                {rapport.errors.length > 3 && <div className="text-xs text-muted-foreground">+{rapport.errors.length - 3} meer fouten</div>}
              </div>
            )}
            {rapport.preview.length > 0 && (
              <div>
                <button className="text-xs text-muted-foreground flex items-center gap-1 hover:text-foreground" onClick={() => setToonVoorbeeld(!toonVoorbeeld)}>
                  {toonVoorbeeld ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}Preview ({rapport.preview.length} rijen)
                </button>
                {toonVoorbeeld && (
                  <div className="mt-2 overflow-x-auto">
                    <table className="text-xs w-full border-collapse">
                      <thead><tr>{Object.keys(rapport.preview[0]).map(k => <th key={k} className="text-left p-1 bg-muted font-mono border border-border/50">{k}</th>)}</tr></thead>
                      <tbody>{rapport.preview.map((r, i) => <tr key={i}>{Object.values(r).map((v, j) => <td key={j} className="p-1 border border-border/50 font-mono truncate max-w-[120px]">{v}</td>)}</tr>)}</tbody>
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
          <Input type="file" accept=".csv,.xlsx" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" onChange={handleBestand} disabled={validating || uploading} />
          <Button variant="outline" className="w-full text-sm" size="sm" disabled={validating || uploading}>
            {validating ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Valideren…</> : <><Upload className="mr-2 h-4 w-4" />{bestand ? bestand.name : "CSV of XLSX kiezen"}</>}
          </Button>
        </div>
        {rapport && kanImporteren && (
          <Button size="sm" onClick={handleImporteer} disabled={uploading} className="shrink-0">
            {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}Importeer {rapport.rows_valid} rijen
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
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
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
    setImportResult(null);
    if (e.target) e.target.value = "";
    setValidating(true);
    try {
      const formData = new FormData();
      formData.append("file", f, f.name);
      const res = await fetch(`${BASE}/api/uploads/validate?upload_type=traffic`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN()}` },
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
        headers: { Authorization: `Bearer ${TOKEN()}` },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const result = await res.json();
      setImportResult({ rows_processed: result.rows_processed ?? 0, rows_failed: result.rows_failed ?? 0, warnings: result.warnings ?? [] });
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
    <Card className={importResult ? (importResult.rows_failed > 0 ? "border-amber-300" : "border-emerald-300") : rapport ? (rapport.rows_failed > 0 ? "border-amber-300" : "border-emerald-300") : ""}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5 text-primary" />
              Traffic & GA4
            </CardTitle>
            <CardDescription className="mt-1 text-sm">
              Sessies, pageviews en conversies per SKU/dag. Exporteer als CSV of XLSX uit Google Analytics 4.
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
        {importResult && (
          <div className="rounded-md border p-3 space-y-2 bg-muted/30">
            <div className="flex items-center gap-3 text-sm font-medium">
              <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-4 h-4" />Import voltooid</span>
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />{importResult.rows_processed} rijen verwerkt</span>
              {importResult.rows_failed > 0 && (
                <span className="text-amber-600 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{importResult.rows_failed} mislukt</span>
              )}
            </div>
            {importResult.warnings.length > 0 && (
              <div className="space-y-1">
                {importResult.warnings.slice(0, 3).map((w, i) => (
                  <div key={i} className="text-xs text-amber-600 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}</div>
                ))}
                {importResult.warnings.length > 3 && <div className="text-xs text-muted-foreground">+{importResult.warnings.length - 3} meer waarschuwingen</div>}
              </div>
            )}
          </div>
        )}
        {rapport && (
          <div className="rounded-md border p-3 space-y-2 bg-muted/30">
            <div className="flex items-center gap-3 text-sm">
              <span className="text-muted-foreground">Totaal:</span>
              <span className="font-medium">{rapport.rows_total} rijen</span>
              {rapport.rows_valid > 0 && <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />{rapport.rows_valid} geldig</span>}
              {rapport.rows_failed > 0 && <span className="text-red-500 flex items-center gap-1"><XCircle className="w-3 h-3" />{rapport.rows_failed} ongeldig</span>}
            </div>
            {rapport.missing_fields.length > 0 && (
              <div className="text-xs text-red-600 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />Ontbrekende kolommen: {rapport.missing_fields.join(", ")}</div>
            )}
            {rapport.errors.length > 0 && (
              <div className="space-y-1">
                {rapport.errors.slice(0, 3).map((e, i) => <div key={i} className="text-xs text-red-500">Rij {e.rij}: {e.bericht}</div>)}
                {rapport.errors.length > 3 && <div className="text-xs text-muted-foreground">+{rapport.errors.length - 3} meer fouten</div>}
              </div>
            )}
            {rapport.preview.length > 0 && (
              <div>
                <button className="text-xs text-muted-foreground flex items-center gap-1 hover:text-foreground" onClick={() => setToonVoorbeeld(!toonVoorbeeld)}>
                  {toonVoorbeeld ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}Preview ({rapport.preview.length} rijen)
                </button>
                {toonVoorbeeld && (
                  <div className="mt-2 overflow-x-auto">
                    <table className="text-xs w-full border-collapse">
                      <thead><tr>{Object.keys(rapport.preview[0]).map(k => <th key={k} className="text-left p-1 bg-muted font-mono border border-border/50">{k}</th>)}</tr></thead>
                      <tbody>{rapport.preview.map((r, i) => <tr key={i}>{Object.values(r).map((v, j) => <td key={j} className="p-1 border border-border/50 font-mono truncate max-w-[120px]">{v}</td>)}</tr>)}</tbody>
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
          <Input type="file" accept=".csv,.xlsx" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" onChange={handleBestand} disabled={validating || uploading} />
          <Button variant="outline" className="w-full text-sm" size="sm" disabled={validating || uploading}>
            {validating ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Valideren…</> : <><Upload className="mr-2 h-4 w-4" />{bestand ? bestand.name : "CSV of XLSX kiezen"}</>}
          </Button>
        </div>
        {rapport && kanImporteren && (
          <Button size="sm" onClick={handleImporteer} disabled={uploading} className="shrink-0">
            {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}Importeer {rapport.rows_valid} rijen
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}

// ── Placeholder cards for upcoming integrations ──────────────────────────

interface PlaceholderCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  fields: string[];
}

function PlaceholderCard({ title, description, icon, fields }: PlaceholderCardProps) {
  return (
    <Card className="opacity-70 border-dashed">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              {icon}
              {title}
              <Badge variant="outline" className="text-xs bg-muted text-muted-foreground">Binnenkort beschikbaar</Badge>
            </CardTitle>
            <CardDescription className="mt-1 text-sm">{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1">
          {fields.map(v => (
            <Badge key={v} variant="outline" className="text-xs font-mono text-muted-foreground">{v}</Badge>
          ))}
        </div>
      </CardContent>
      <CardFooter>
        <Button variant="outline" size="sm" disabled className="w-full text-muted-foreground">
          <Clock className="mr-2 h-4 w-4" />Koppeling in voorbereiding
        </Button>
      </CardFooter>
    </Card>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function Gegevensintegratie() {
  const { data: uploads, isLoading } = useListUploads();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Gegevensintegratie</h1>
        <p className="text-muted-foreground mt-1">
          Importeer DRS Datareport als primaire databron, of upload aanvullende datasets handmatig als CSV of XLSX.
        </p>
      </div>

      {/* DRS wizard — full width */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Primaire databron</h2>
        <DrsWizardCard />
      </div>

      {/* PriceShape connector — full width */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Concurrentiedata (PriceShape)</h2>
        <PriceShapeWizardCard />
      </div>

      {/* Secondary uploads */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Aanvullende data</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <SalesUploadCard />
          <TrafficUploadCard />
        </div>
      </div>

      {/* Placeholder cards */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Toekomstige koppelingen</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-4">
          <PlaceholderCard
            title="Promoties"
            icon={<TrendingUp className="h-4 w-4 text-muted-foreground" />}
            description="Dagelijkse promotie- en kortingsdata per SKU."
            fields={["sku_id", "promotion_type", "discount_pct", "channel", "start_date"]}
          />
          <PlaceholderCard
            title="Leveranciersdata"
            icon={<Package className="h-4 w-4 text-muted-foreground" />}
            description="Inkoopprijzen, levertijden en MOQ per leverancier."
            fields={["sku_id", "supplier_id", "purchase_price", "lead_time_days", "moq"]}
          />
          <PlaceholderCard
            title="Logistieke kosten"
            icon={<Truck className="h-4 w-4 text-muted-foreground" />}
            description="Pick-, pak-, verzend- en retourkosten per SKU."
            fields={["sku_id", "pick_cost", "pack_cost", "ship_cost", "return_cost"]}
          />
          <PlaceholderCard
            title="Marketingkosten"
            icon={<TrendingUp className="h-4 w-4 text-muted-foreground" />}
            description="SEO- en SEA-kosten, ROAS en CAC per SKU/dag."
            fields={["sku_id", "seo_cost", "sea_cost", "roas", "cac"]}
          />
        </div>
      </div>

      {/* Recent import jobs */}
      <div>
        <h2 className="text-lg font-bold mb-4">Recente importtaken</h2>
        <div className="border rounded-md bg-card">
          <div className="grid grid-cols-7 border-b bg-muted/50 p-3 text-sm font-medium text-muted-foreground">
            <div className="col-span-2">Bestandsnaam</div>
            <div>Type</div>
            <div>Status</div>
            <div className="text-right">Verwerkt / Mislukt</div>
            <div className="text-right">Duplicaten</div>
            <div className="text-right">Datum</div>
          </div>
          <div className="divide-y">
            {isLoading ? (
              <div className="p-8 text-center text-muted-foreground">Laden...</div>
            ) : !uploads?.length ? (
              <div className="p-8 text-center text-muted-foreground">Geen recente uploads.</div>
            ) : uploads.map((job) => (
              <div key={job.id} className="grid grid-cols-7 items-center p-3 text-sm">
                <div className="col-span-2 font-medium truncate pr-4">{job.filename}</div>
                <div className="capitalize text-muted-foreground text-xs">
                  {job.upload_type === "drs"
                    ? <Badge className="bg-primary/10 text-primary border-primary/20 text-xs">DRS</Badge>
                    : job.upload_type?.replace(/_/g, " ")}
                </div>
                <div>
                  {job.status === "completed" && <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200 text-xs">Voltooid</Badge>}
                  {job.status === "processing" && <Badge variant="outline" className="bg-blue-50 text-blue-600 border-blue-200 text-xs">Verwerking</Badge>}
                  {job.status === "failed" && <Badge variant="destructive" className="text-xs">Mislukt</Badge>}
                  {job.status === "pending" && <Badge variant="secondary" className="text-xs">In wachtrij</Badge>}
                </div>
                <div className="text-right tabular-nums">
                  <span className="text-emerald-600">{job.rows_processed}</span>
                  {" / "}
                  <span className={job.rows_failed > 0 ? "text-destructive" : ""}>{job.rows_failed}</span>
                </div>
                <div className="text-right tabular-nums">
                  {((job as any).rows_duplicates ?? 0) > 0 ? (
                    <Badge
                      className="bg-amber-500/10 text-amber-700 border-amber-200 text-xs"
                      title="Rijen overgeslagen als duplicaat binnen dit bestand"
                    >
                      {(job as any).rows_duplicates} overgeslagen
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </div>
                <div className="text-right text-muted-foreground tabular-nums text-xs">
                  {new Date(job.created_at).toLocaleString("nl-NL")}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
