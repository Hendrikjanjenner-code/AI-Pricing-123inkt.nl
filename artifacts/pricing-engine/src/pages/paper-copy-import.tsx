import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useToast } from "@/hooks/use-toast";
import { useAuth, getAuthToken } from "@/lib/auth";
import {
  Upload, FileSpreadsheet, Loader2, CheckCircle2, XCircle, AlertTriangle,
  Database, Package, Tag, TrendingUp, Euro, Trash2, ShieldAlert, History, RefreshCw,
} from "lucide-react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface ValidatieRapport {
  job_id: number;
  bestandsnaam: string;
  samenvatting: {
    rijen_totaal: number; rijen_geldig: number; rijen_ongeldig: number;
    actief: number; inactief: number; unieke_merken: number;
    met_ean: number; zonder_ean: number; met_oem: number; zonder_oem: number;
  };
  missing_columns: string[];
  duplicate_productcodes: string[];
  errors: Array<{ rij: number; veld: string; type?: string; bericht: string }>;
  errors_by_type: Record<string, number>;
  warnings: string[];
  kan_importeren: boolean;
  preview: Record<string, string>[];
}

interface ImportResultaat {
  job_id: number; mode: string; created: number; updated: number;
  skipped: number; removed: number; rows_processed: number;
  warnings: string[]; summary: SummaryData; message: string;
}

interface SummaryData {
  total_products: number; active: number; inactive: number; unique_brands: number;
  oem_articles: number; compatible_huismerk_articles: number;
  missing_ean: number; missing_oem: number; avg_sales_price: number | null;
  total_ytd_revenue: number; total_ytd_margin: number; total_ytd_units: number;
}

interface ImportJobRow {
  id: number; filename: string; status: string; import_mode: string | null;
  rows_processed: number; rows_failed: number; error_message: string | null;
  warnings: string[]; uploaded_by: string; created_at: string; completed_at: string | null;
}

const MODE_LABELS: Record<string, string> = {
  aanvullen: "Aanvullen (alleen nieuwe productcodes toevoegen)",
  updaten: "Updaten op productcode (standaard — nieuw toevoegen, bestaand bijwerken)",
  vervangen: "Volledig vervangen (verwijdert Paper_Copy-producten die niet in het bestand staan)",
};

const REPLACE_PHRASE = "VERVANG ALLE PAPER_COPY PRODUCTEN";
const DELETE_PHRASE = "VERWIJDER ALLE PRODUCTDATA";

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  gevalideerd: { label: "Gevalideerd", className: "bg-blue-50 text-blue-600 border-blue-200" },
  opgeslagen: { label: "Opgeslagen", className: "bg-emerald-50 text-emerald-600 border-emerald-200" },
  fout: { label: "Fout", className: "bg-red-50 text-red-600 border-red-200" },
  processing: { label: "Bezig", className: "bg-amber-50 text-amber-600 border-amber-200" },
};

async function authFetch(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...(init?.headers || {}), Authorization: `Bearer ${getAuthToken()}` },
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed?.detail === "string" ? parsed.detail : (parsed?.detail?.message || JSON.stringify(parsed?.detail) || text);
    } catch {
      // gebruik ruwe tekst
    }
    throw new Error(detail.length > 500 ? detail.slice(0, 500) + "…" : detail);
  }
  return res.json();
}

function StatCard({ label, value, icon: Icon, kleur = "default" }: {
  label: string; value: string | number | null; icon: React.ElementType;
  kleur?: "groen" | "rood" | "default";
}) {
  const kleuren: Record<string, string> = {
    groen: "text-emerald-600", rood: "text-red-500", default: "text-foreground",
  };
  return (
    <Card>
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardDescription className="text-xs font-medium uppercase tracking-wide">{label}</CardDescription>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${kleuren[kleur]}`}>{value ?? "—"}</div>
      </CardContent>
    </Card>
  );
}

export default function PaperCopyImport() {
  const { toast } = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [bestand, setBestand] = useState<File | null>(null);
  const [validating, setValidating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [rapport, setRapport] = useState<ValidatieRapport | null>(null);
  const [resultaat, setResultaat] = useState<ImportResultaat | null>(null);
  const [mode, setMode] = useState<"aanvullen" | "updaten" | "vervangen">("updaten");
  const [confirmPhrase, setConfirmPhrase] = useState("");

  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [jobs, setJobs] = useState<ImportJobRow[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);

  const [deleteBevestig, setDeleteBevestig] = useState("");
  const [deleteBezig, setDeleteBezig] = useState(false);

  const laadSummary = async () => {
    setSummaryLoading(true);
    try {
      setSummary(await authFetch("/api/uploads/paper-copy/summary"));
    } catch (e: any) {
      toast({ title: "Samenvatting laden mislukt", description: e.message, variant: "destructive" });
    } finally {
      setSummaryLoading(false);
    }
  };

  const laadJobs = async () => {
    setJobsLoading(true);
    try {
      const d = await authFetch("/api/uploads/paper-copy/jobs");
      setJobs(d.jobs || []);
    } catch (e: any) {
      toast({ title: "Importlog laden mislukt", description: e.message, variant: "destructive" });
    } finally {
      setJobsLoading(false);
    }
  };

  useEffect(() => { laadSummary(); laadJobs(); }, []);

  const handleBestand = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".xlsx")) {
      toast({ title: "Verkeerd bestandstype", description: "Alleen XLSX-bestanden worden ondersteund.", variant: "destructive" });
      return;
    }
    setBestand(f);
    setRapport(null);
    setResultaat(null);
    setConfirmPhrase("");
    if (e.target) e.target.value = "";

    setValidating(true);
    try {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const data = await authFetch("/api/uploads/paper-copy/validate", { method: "POST", body: fd });
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
    if (mode === "vervangen" && confirmPhrase !== REPLACE_PHRASE) {
      toast({ title: "Bevestiging vereist", description: `Typ exact: '${REPLACE_PHRASE}'`, variant: "destructive" });
      return;
    }
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", bestand, bestand.name);
      fd.append("mode", mode);
      if (mode === "vervangen") fd.append("confirm_phrase", confirmPhrase);
      const data = await authFetch("/api/uploads/paper-copy/save", { method: "POST", body: fd });
      setResultaat(data);
      setSummary(data.summary);
      toast({ title: "Import opgeslagen", description: data.message });
      laadJobs();
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
    setConfirmPhrase("");
    setMode("updaten");
  };

  const handleVerwijderAlles = async () => {
    if (deleteBevestig !== DELETE_PHRASE) return;
    setDeleteBezig(true);
    try {
      const fd = new FormData();
      fd.append("confirm_phrase", deleteBevestig);
      const data = await authFetch("/api/uploads/paper-copy/all", { method: "DELETE", body: fd });
      toast({ title: "Productdata verwijderd", description: `${data.rows_deleted} producten verwijderd.` });
      setDeleteBevestig("");
      laadSummary();
      laadJobs();
      reset();
    } catch (err: any) {
      toast({ title: "Verwijderen mislukt", description: err.message, variant: "destructive" });
    } finally {
      setDeleteBezig(false);
    }
  };

  const previewKolommen = rapport?.preview?.length ? Object.keys(rapport.preview[0]) : [];

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">DRS Product Import</h1>
          <p className="text-muted-foreground mt-1">
            Importeer de productmaster als XLSX ("Test Document AI Pricing Papier.xlsx") — één werkblad,
            rij 1 = kolomnamen. Los van de reguliere DRS Sales+Hierarchy importer.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { laadSummary(); laadJobs(); }}>
          <RefreshCw className="w-4 h-4 mr-2" />Vernieuwen
        </Button>
      </div>

      {/* Samenvattingsstatistieken */}
      {summaryLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i}><CardContent className="pt-6"><Skeleton className="h-12 w-full" /></CardContent></Card>
          ))}
        </div>
      ) : summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Totaal producten" value={summary.total_products} icon={Package} />
          <StatCard label="Actief" value={summary.active} icon={CheckCircle2} kleur="groen" />
          <StatCard label="Inactief" value={summary.inactive} icon={XCircle} kleur={summary.inactive > 0 ? "rood" : "default"} />
          <StatCard label="Unieke merken" value={summary.unique_brands} icon={Tag} />
          <StatCard label="OEM-artikelen" value={summary.oem_articles} icon={Database} />
          <StatCard label="Compatible/Huismerk" value={summary.compatible_huismerk_articles} icon={Package} />
          <StatCard label="Zonder EAN" value={summary.missing_ean} icon={AlertTriangle} kleur={summary.missing_ean > 0 ? "rood" : "groen"} />
          <StatCard label="Zonder OEM" value={summary.missing_oem} icon={AlertTriangle} kleur={summary.missing_oem > 0 ? "rood" : "groen"} />
          <StatCard label="Gem. verkoopprijs" value={summary.avg_sales_price !== null ? `€ ${summary.avg_sales_price.toFixed(2)}` : "—"} icon={Euro} />
          <StatCard label="Totale YTD-omzet" value={`€ ${summary.total_ytd_revenue.toLocaleString("nl-NL", { maximumFractionDigits: 0 })}`} icon={TrendingUp} />
          <StatCard label="Totale YTD-marge" value={`€ ${summary.total_ytd_margin.toLocaleString("nl-NL", { maximumFractionDigits: 0 })}`} icon={TrendingUp} />
          <StatCard label="Totale YTD-eenheden" value={summary.total_ytd_units.toLocaleString("nl-NL", { maximumFractionDigits: 0 })} icon={Package} />
        </div>
      )}

      {/* Upload & validatie kaart */}
      <Card className={rapport ? (rapport.kan_importeren ? "border-emerald-300" : "border-red-300") : ""}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5 text-primary" />
            Productmaster uploaden
            <Badge className="bg-primary/10 text-primary border-primary/20 text-xs">Paper_Copy pilot</Badge>
          </CardTitle>
          <CardDescription>
            Verplichte velden: productcode, Titel, Merk, Soort. Aanbevolen: EAN, OEM, marge/omzet, productHierarchy.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {validating && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />Bestand wordt gevalideerd…
            </div>
          )}

          {rapport && (
            <div className="rounded-md border p-4 space-y-3 bg-muted/30">
              <div className="text-sm font-medium">Validatierapport: {rapport.bestandsnaam}</div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div><div className="text-lg font-bold">{rapport.samenvatting.rijen_totaal}</div><div className="text-xs text-muted-foreground">Rijen totaal</div></div>
                <div><div className="text-lg font-bold text-emerald-600">{rapport.samenvatting.rijen_geldig}</div><div className="text-xs text-muted-foreground">Geldig</div></div>
                <div><div className="text-lg font-bold text-red-500">{rapport.samenvatting.rijen_ongeldig}</div><div className="text-xs text-muted-foreground">Ongeldig</div></div>
                <div><div className="text-lg font-bold">{rapport.samenvatting.unieke_merken}</div><div className="text-xs text-muted-foreground">Unieke merken</div></div>
                <div><div className="text-lg font-bold">{rapport.samenvatting.actief}</div><div className="text-xs text-muted-foreground">Actief</div></div>
                <div><div className="text-lg font-bold">{rapport.samenvatting.inactief}</div><div className="text-xs text-muted-foreground">Inactief</div></div>
                <div><div className="text-lg font-bold">{rapport.samenvatting.zonder_ean}</div><div className="text-xs text-muted-foreground">Zonder EAN</div></div>
                <div><div className="text-lg font-bold">{rapport.samenvatting.zonder_oem}</div><div className="text-xs text-muted-foreground">Zonder OEM</div></div>
              </div>

              {rapport.missing_columns.length > 0 && (
                <div className="text-xs text-red-600 flex items-start gap-1">
                  <XCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  Verplichte kolommen ontbreken: {rapport.missing_columns.join(", ")}
                </div>
              )}

              {rapport.duplicate_productcodes.length > 0 && (
                <div className="text-xs text-red-600 flex items-start gap-1">
                  <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                  {rapport.duplicate_productcodes.length} dubbele productcode(s): {rapport.duplicate_productcodes.slice(0, 5).join(", ")}
                </div>
              )}

              {Object.keys(rapport.errors_by_type).length > 0 && (
                <div className="space-y-1">
                  <div className="text-xs font-medium text-muted-foreground">Foutmeldingen per type:</div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(rapport.errors_by_type).map(([type, count]) => (
                      <Badge key={type} variant="outline" className="text-xs font-mono">{type}: {count}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {rapport.errors.length > 0 && (
                <div className="max-h-40 overflow-y-auto space-y-1 border-t pt-2">
                  {rapport.errors.slice(0, 20).map((e, i) => (
                    <div key={i} className="text-xs text-red-600">Rij {e.rij} — {e.veld}: {e.bericht}</div>
                  ))}
                  {rapport.errors.length > 20 && <div className="text-xs text-muted-foreground">+{rapport.errors.length - 20} meer</div>}
                </div>
              )}

              {rapport.warnings.length > 0 && (
                <div className="max-h-32 overflow-y-auto space-y-1 border-t pt-2">
                  {rapport.warnings.slice(0, 15).map((w, i) => (
                    <div key={i} className="text-xs text-amber-600 flex items-start gap-1">
                      <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}
                    </div>
                  ))}
                  {rapport.warnings.length > 15 && <div className="text-xs text-muted-foreground">+{rapport.warnings.length - 15} meer waarschuwingen</div>}
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
              <div className="border rounded-md overflow-x-auto max-h-72">
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

          {rapport?.kan_importeren && (
            <div className="space-y-3 border-t pt-4">
              <Label className="text-sm font-medium">Importmodus</Label>
              <RadioGroup value={mode} onValueChange={(v) => setMode(v as any)}>
                {(["aanvullen", "updaten", "vervangen"] as const).map(m => (
                  <div key={m} className="flex items-start gap-2">
                    <RadioGroupItem value={m} id={m} className="mt-0.5" />
                    <Label htmlFor={m} className="text-sm font-normal cursor-pointer">{MODE_LABELS[m]}</Label>
                  </div>
                ))}
              </RadioGroup>

              {mode === "vervangen" && (
                <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3 space-y-2">
                  <div className="text-xs text-amber-700 flex items-start gap-1 font-medium">
                    <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
                    Deze actie verwijdert alle bestaande Paper_Copy-producten die niet in dit bestand voorkomen.
                    Typ ter bevestiging exact: <code className="font-mono">{REPLACE_PHRASE}</code>
                  </div>
                  <Input
                    value={confirmPhrase}
                    onChange={e => setConfirmPhrase(e.target.value)}
                    placeholder={REPLACE_PHRASE}
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
              accept=".xlsx"
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              onChange={handleBestand}
              disabled={validating || importing}
            />
            <Button variant="outline" className="w-full text-sm" size="sm" disabled={validating || importing}>
              {validating
                ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Valideren…</>
                : <><Upload className="mr-2 h-4 w-4" />{bestand ? bestand.name : "XLSX kiezen (productmaster)"}</>
              }
            </Button>
          </div>

          {rapport?.kan_importeren && !resultaat && (
            <Button
              size="sm"
              onClick={handleImporteer}
              disabled={importing || (mode === "vervangen" && confirmPhrase !== REPLACE_PHRASE)}
              className="ml-auto"
            >
              {importing
                ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Opslaan…</>
                : <><CheckCircle2 className="mr-2 h-4 w-4" />Import opslaan</>
              }
            </Button>
          )}

          {resultaat && (
            <Button variant="outline" size="sm" onClick={reset} className="ml-auto">
              Nieuwe import
            </Button>
          )}
        </CardFooter>
      </Card>

      {/* Importlog */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-5 w-5" />Importlog
          </CardTitle>
          <CardDescription>Overzicht van eerdere Paper_Copy-imports, nieuwste eerst.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Bestand</TableHead>
                <TableHead>Modus</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Rijen verwerkt</TableHead>
                <TableHead className="text-right">Mislukt</TableHead>
                <TableHead>Door</TableHead>
                <TableHead className="text-right">Datum</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobsLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 7 }).map((_, j) => <TableCell key={j}><Skeleton className="h-5 w-full" /></TableCell>)}
                  </TableRow>
                ))
              ) : jobs.length === 0 ? (
                <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">Nog geen imports uitgevoerd.</TableCell></TableRow>
              ) : (
                jobs.map(j => {
                  const badge = STATUS_BADGE[j.status] || { label: j.status, className: "" };
                  return (
                    <TableRow key={j.id}>
                      <TableCell className="text-sm">{j.filename}</TableCell>
                      <TableCell className="text-xs font-mono">{j.import_mode || "—"}</TableCell>
                      <TableCell><Badge className={`text-xs ${badge.className}`}>{badge.label}</Badge></TableCell>
                      <TableCell className="text-right tabular-nums">{j.rows_processed}</TableCell>
                      <TableCell className="text-right tabular-nums">{j.rows_failed}</TableCell>
                      <TableCell className="text-xs">{j.uploaded_by}</TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        {j.created_at ? new Date(j.created_at).toLocaleString("nl-NL") : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Admin-only: alle productdata verwijderen */}
      {isAdmin && (
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2 text-red-600">
              <Trash2 className="h-5 w-5" />Alle productdata verwijderen
            </CardTitle>
            <CardDescription>
              Alleen voor beheerders. Verwijdert permanent alle Paper_Copy-producten uit dim_product.
              Dit is het enige codepad dat productdata mag verwijderen buiten een 'vervangen'-import.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm">
                  <Trash2 className="w-4 h-4 mr-2" />Alle productdata verwijderen
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Weet je het zeker?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Deze actie verwijdert permanent alle Paper_Copy-producten uit dim_product en kan niet ongedaan
                    worden gemaakt. Typ ter bevestiging exact: <code className="font-mono">{DELETE_PHRASE}</code>
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <Input
                  value={deleteBevestig}
                  onChange={e => setDeleteBevestig(e.target.value)}
                  placeholder={DELETE_PHRASE}
                  className="font-mono text-sm"
                />
                <AlertDialogFooter>
                  <AlertDialogCancel onClick={() => setDeleteBevestig("")}>Annuleren</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleVerwijderAlles}
                    disabled={deleteBevestig !== DELETE_PHRASE || deleteBezig}
                    className="bg-red-600 hover:bg-red-700"
                  >
                    {deleteBezig ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Verwijderen…</> : "Definitief verwijderen"}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
