import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { useShopId } from "@/hooks/use-shop-id";
import { useAuth } from "@/lib/auth";
import { useQuery } from "@tanstack/react-query";
import { CalendarRange, CheckCircle2, Loader2, Upload, XCircle, AlertTriangle, RotateCcw, Info } from "lucide-react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const TOKEN = () => localStorage.getItem("auth_token");
const LONG_TIMEOUT_MS = 180_000;
const STAGE_PREFIX = "drs_daily_stage_id";

interface ShopRow { id: number; name: string; is_default: boolean; active: boolean }

interface DailyError { row?: number | null; code?: string | null; message: string }
interface DailyPreview {
  stage_id: string | number;
  status: string;
  shop_id: number;
  period_start: string;
  period_end: string;
  product_count: number;
  fact_count: number;
  totals: { quantity: number; revenue_excl_vat: number; revenue_incl_vat: number };
  errors: DailyError[];
  error_count: number;
  warnings: string[];
  mapping_proposals: Array<{ code?: string | null; ean?: string | null; sku_id?: string | null }>;
  mapping_proposal_count: number;
  sample: Array<Record<string, unknown>>;
  expires_at?: string | null;
  result?: ConfirmResult | null;
  mapping_result?: MappingResult | null;
}
interface MappingResult { stage_id: string | number; mapped: number; sales_written: number; unresolved: number }
interface ConfirmResult { stage_id: string | number; status: string; inserted: number; updated: number; unchanged: number }

async function longFetch(path: string, init: RequestInit = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), LONG_TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: ctrl.signal,
      credentials: "include",
      headers: { ...(init.headers || {}), Authorization: `Bearer ${TOKEN()}` },
    });
    const text = await res.text();
    let body: any = null;
    try { body = text ? JSON.parse(text) : null; } catch { /* not json */ }
    if (!res.ok) {
      const d = body?.detail;
      const msg = typeof d === "string" ? d : d?.message || (d ? JSON.stringify(d) : text) || `HTTP ${res.status}`;
      const err = new Error(msg.length > 500 ? msg.slice(0, 500) + "…" : msg) as Error & { status?: number };
      err.status = res.status;
      throw err;
    }
    return body;
  } catch (e: any) {
    if (e?.name === "AbortError") throw new Error("De server reageerde niet binnen 3 minuten. Controleer het resultaat voordat u opnieuw bevestigt.");
    throw e;
  } finally {
    clearTimeout(t);
  }
}

const eur = (n: number) => new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(n ?? 0);
const num = (n: number) => new Intl.NumberFormat("nl-NL").format(n ?? 0);

export function DrsDailyImportCard() {
  const { toast } = useToast();
  const qc = useQueryClient();
  const explicitShopId = useShopId();
  const { user } = useAuth();
  // Zelfde query/cache als ShopSwitcher: zonder expliciete keuze geldt de default-shop.
  const shopsQuery = useQuery<{ shops: ShopRow[] }>({
    queryKey: ["/api/shops"],
    queryFn: async () => {
      const res = await fetch("/api/shops", { headers: { Authorization: `Bearer ${TOKEN()}` } });
      if (!res.ok) throw new Error("Winkels laden mislukt");
      return res.json();
    },
    staleTime: 5 * 60 * 1000,
  });
  const activeShops = (shopsQuery.data?.shops ?? []).filter(s => s.active);
  const effectiveShop = explicitShopId !== undefined
    ? activeShops.find(s => s.id === explicitShopId) ?? (shopsQuery.isSuccess ? undefined : { id: explicitShopId, name: `Winkel #${explicitShopId}`, is_default: false, active: true })
    : activeShops.find(s => s.is_default) ?? activeShops[0];
  const shopId = effectiveShop?.id;
  const userKey = user?.id ?? user?.username ?? "anon";
  const STAGE_KEY = shopId !== undefined ? `${STAGE_PREFIX}:${userKey}:${shopId}` : null;
  const [year, setYear] = useState("2026");
  const [start, setStart] = useState("2026-08-30");
  const [end, setEnd] = useState("2026-09-30");
  const [codeCol, setCodeCol] = useState("1");
  const [eanCol, setEanCol] = useState("3");
  const [firstDayCol, setFirstDayCol] = useState("5");
  const [sheet, setSheet] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<"preview" | "confirm" | "load" | "mapping" | null>(null);
  const [preview, setPreview] = useState<DailyPreview | null>(null);
  const [result, setResult] = useState<ConfirmResult | null>(null);
  const [confirmMapping, setConfirmMapping] = useState(false);
  const [resultMissing, setResultMissing] = useState(false);
  const confirmingRef = useRef(false);

  // Herstel een lopende/afgeronde stage na herladen
  useEffect(() => {
    // Winkel of gebruiker gewisseld: nooit een stage van een andere scope tonen.
    setPreview(null); setResult(null); setResultMissing(false); setConfirmMapping(false);
    if (!STAGE_KEY) return;
    const id = localStorage.getItem(STAGE_KEY);
    if (!id) return;
    let cancelled = false;
    setBusy("load");
    longFetch(`/api/uploads/drs-daily/${encodeURIComponent(id)}`)
      .then((p: DailyPreview) => {
        if (cancelled) return;
        if (p.shop_id !== shopId) { localStorage.removeItem(STAGE_KEY); return; }
        setPreview(p);
        if (p.status === "confirmed") {
          if (p.result) setResult(p.result);
          else setResultMissing(true);
        }
      })
      .catch(() => { if (!cancelled) localStorage.removeItem(STAGE_KEY); })
      .finally(() => { if (!cancelled) setBusy(null); });
    return () => { cancelled = true; setBusy(null); };
  }, [STAGE_KEY, shopId]);

  const runPreview = async () => {
    if (!file || !shopId) return;
    if (!start || !end || start > end) {
      toast({ title: "Periode ongeldig", description: "Kies een begin- en einddatum; begin moet voor einde liggen.", variant: "destructive" });
      return;
    }
    setBusy("preview"); setPreview(null); setResult(null); setResultMissing(false); setConfirmMapping(false);
    try {
      const fd = new FormData();
      fd.append("file", file, file.name);
      fd.append("shop_id", String(shopId));
      fd.append("year", year);
      fd.append("period_start", start);
      fd.append("period_end", end);
      fd.append("template", "drs-sales-wide-v1");
      const mapping: Record<string, unknown> = {
        code_column: Number(codeCol), ean_column: Number(eanCol), first_day_column: Number(firstDayCol),
      };
      if (sheet.trim()) mapping.sheet = sheet.trim();
      fd.append("mapping", JSON.stringify(mapping));
      const p: DailyPreview = await longFetch("/api/uploads/drs-daily/preview", { method: "POST", body: fd });
      setPreview(p);
      if (STAGE_KEY) localStorage.setItem(STAGE_KEY, String(p.stage_id));
    } catch (e: any) {
      toast({ title: "Preview mislukt", description: e.message, variant: "destructive" });
    } finally { setBusy(null); }
  };

  const confirm = async () => {
    if (!preview || confirmingRef.current) return;
    confirmingRef.current = true;
    setBusy("confirm");
    try {
      const r: ConfirmResult = await longFetch(`/api/uploads/drs-daily/${encodeURIComponent(String(preview.stage_id))}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Eerder expliciet goedgekeurde koppelingen (mapping_result) gelden als goedkeuring.
        body: JSON.stringify({ confirm_mapping: confirmMapping || !!preview.mapping_result }),
      });
      setResult(r);
      setPreview({ ...preview, status: "confirmed" });
      toast({ title: "Dagverkoop vastgelegd", description: `${r.inserted} nieuw, ${r.updated} gecorrigeerd, ${r.unchanged} ongewijzigd.` });
      qc.invalidateQueries();
    } catch (e: any) {
      const title = e.status === 409 ? "Import geblokkeerd" : e.status === 410 ? "Preview verlopen — upload opnieuw" : "Bevestigen mislukt";
      toast({ title, description: e.message, variant: "destructive" });
    } finally { setBusy(null); confirmingRef.current = false; }
  };

  const confirmMappingsOnly = async () => {
    if (!preview || confirmingRef.current || !confirmMapping) return;
    confirmingRef.current = true;
    setBusy("mapping");
    try {
      const r: MappingResult = await longFetch(`/api/uploads/drs-daily/${encodeURIComponent(String(preview.stage_id))}/confirm-mappings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm_mapping: true }),
      });
      setPreview(prev => prev ? { ...prev, mapping_result: r } : prev);
      toast({ title: "Koppelingen vastgelegd", description: `${r.mapped} gekoppeld, ${r.unresolved} onopgelost. Geen verkoop geschreven.` });
      qc.invalidateQueries();
    } catch (e: any) {
      const title = e.status === 409 ? "Koppelen geblokkeerd" : e.status === 410 ? "Preview verlopen — upload opnieuw" : "Koppelen mislukt";
      toast({ title, description: e.message, variant: "destructive" });
    } finally { setBusy(null); confirmingRef.current = false; }
  };

  const retryResult = async () => {
    if (!preview) return;
    setBusy("load");
    try {
      const p: DailyPreview = await longFetch(`/api/uploads/drs-daily/${encodeURIComponent(String(preview.stage_id))}`);
      setPreview(p);
      if (p.result) { setResult(p.result); setResultMissing(false); }
      else toast({ title: "Resultaat nog niet beschikbaar", description: "De server gaf geen importaantallen terug.", variant: "destructive" });
    } catch (e: any) {
      toast({ title: "Ophalen mislukt", description: e.message, variant: "destructive" });
    } finally { setBusy(null); }
  };

  const reset = () => {
    setResultMissing(false);
    if (STAGE_KEY) localStorage.removeItem(STAGE_KEY);
    setPreview(null); setResult(null); setFile(null); setConfirmMapping(false);
  };

  const blocked = preview?.status === "blocked";
  const needsMapping = (preview?.mapping_proposal_count ?? 0) > 0;
  const canConfirm = preview && preview.status === "ready" && !result && !resultMissing && (!needsMapping || confirmMapping || !!preview.mapping_result);
  const sampleCols = preview?.sample?.length ? Object.keys(preview.sample[0]) : [];

  return (
    <Card data-testid="card-drs-daily" className={`col-span-full ${result ? "border-emerald-300" : blocked ? "border-red-300" : preview ? "border-primary/40" : ""}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <CalendarRange className="h-5 w-5 text-primary" />
          DRS dagverkoop
          <Badge variant="outline" className="text-xs">Los van YTD/catalogus</Badge>
          {effectiveShop ? <Badge className="bg-primary/10 text-primary border-primary/20 text-xs" data-testid="badge-daily-shop">{effectiveShop.name}{effectiveShop.is_default ? " (standaard)" : ""}</Badge>
            : shopsQuery.isLoading ? <Badge variant="outline" className="text-xs" data-testid="badge-daily-shop-loading">Winkel laden…</Badge>
            : shopsQuery.isError ? <Badge variant="outline" className="text-xs text-red-600 cursor-pointer" data-testid="button-daily-shops-retry" onClick={() => shopsQuery.refetch()}>Winkels laden mislukt — opnieuw</Badge>
            : <Badge variant="outline" className="text-xs text-amber-600" data-testid="badge-daily-no-shop">Geen geautoriseerde winkel</Badge>}
        </CardTitle>
        <CardDescription className="text-sm">
          Brede XLSX met twee kopregels: rij 1 dagblokken (DD/MM), rij 2 Productcode, ProductName, EAN, OEM en per dag
          Quantity / Revenue Incl VAT / Revenue Excl. VAT. Productcodes blijven tekst, inclusief voorloopnullen.
          Onbekende of ambigue artikelen blokkeren de hele import.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {busy === "load" && <div className="h-24 rounded-md bg-muted/50 animate-pulse" />}

        {!preview && busy !== "load" && (
          <div className="grid gap-3 md:grid-cols-4">
            <div className="space-y-1"><Label htmlFor="dd-year">Jaar eerste dag</Label>
              <Input id="dd-year" data-testid="input-daily-year" inputMode="numeric" value={year} onChange={e => setYear(e.target.value.replace(/\D/g, "").slice(0, 4))} /></div>
            <div className="space-y-1"><Label htmlFor="dd-start">Periode vanaf</Label>
              <Input id="dd-start" data-testid="input-daily-start" type="date" value={start} onChange={e => setStart(e.target.value)} /></div>
            <div className="space-y-1"><Label htmlFor="dd-end">Periode t/m</Label>
              <Input id="dd-end" data-testid="input-daily-end" type="date" value={end} onChange={e => setEnd(e.target.value)} /></div>
            <div className="space-y-1"><Label htmlFor="dd-sheet">Tabblad (optioneel)</Label>
              <Input id="dd-sheet" data-testid="input-daily-sheet" placeholder="eerste tabblad" value={sheet} onChange={e => setSheet(e.target.value)} /></div>
            <div className="md:col-span-4 rounded-md border bg-muted/30 p-3 space-y-2">
              <div className="text-xs font-medium">Template <span className="font-mono">drs-sales-wide-v1</span> — kolomkoppeling (1 = kolom A)</div>
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1"><Label className="text-xs">Productcode (zakelijke SKU)</Label>
                  <Input data-testid="input-daily-codecol" inputMode="numeric" value={codeCol} onChange={e => setCodeCol(e.target.value.replace(/\D/g, ""))} /></div>
                <div className="space-y-1"><Label className="text-xs">EAN</Label>
                  <Input data-testid="input-daily-eancol" inputMode="numeric" value={eanCol} onChange={e => setEanCol(e.target.value.replace(/\D/g, ""))} /></div>
                <div className="space-y-1"><Label className="text-xs">Eerste dagkolom</Label>
                  <Input data-testid="input-daily-daycol" inputMode="numeric" value={firstDayCol} onChange={e => setFirstDayCol(e.target.value.replace(/\D/g, ""))} /></div>
              </div>
              <p className="text-xs text-muted-foreground">OEM wordt nooit als unieke sleutel gebruikt. ProductName wordt alleen als label getoond.</p>
            </div>
          </div>
        )}

        {preview && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge data-testid="status-daily" className={result ? "bg-emerald-50 text-emerald-700 border-emerald-200" : blocked ? "bg-red-50 text-red-600 border-red-200" : "bg-primary/10 text-primary border-primary/20"}>
                {result || resultMissing ? "Bevestigd" : blocked ? "Geblokkeerd" : "Klaar voor bevestiging"}
              </Badge>
              <span className="text-muted-foreground">Winkel #{preview.shop_id} · {preview.period_start} t/m {preview.period_end}</span>
              {preview.expires_at && !result && <span className="text-xs text-muted-foreground">Preview geldig tot {new Date(preview.expires_at).toLocaleString("nl-NL")}</span>}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[
                ["Artikelen", num(preview.product_count)],
                ["Dagregels", num(preview.fact_count)],
                ["Afzet (stuks)", num(preview.totals.quantity)],
                ["Omzet excl. btw", eur(preview.totals.revenue_excl_vat)],
                ["Omzet incl. btw", eur(preview.totals.revenue_incl_vat)],
              ].map(([l, v]) => (
                <div key={l} className="rounded-md border p-3">
                  <div className="text-lg font-semibold tabular-nums" data-testid={`text-daily-${l}`}>{v}</div>
                  <div className="text-xs text-muted-foreground">{l}</div>
                </div>
              ))}
            </div>
            <div className="text-xs text-muted-foreground flex items-start gap-1">
              <Info className="w-3 h-3 mt-0.5 shrink-0" />
              Aantallen en bedragen worden exact (met teken) overgenomen. Retourverwerking in DRS is niet geverifieerd;
              er vindt geen extra retourcorrectie plaats en dit is niet als geverifieerde netto-omzet te lezen.
            </div>

            {preview.error_count > 0 && (
              <div className="rounded-md border border-red-200 bg-red-50/50 p-3 space-y-1" data-testid="list-daily-errors">
                <div className="text-sm font-medium text-red-700 flex items-center gap-1"><XCircle className="w-4 h-4" />{preview.error_count} blokkerende melding(en)</div>
                {preview.errors.slice(0, 25).map((e, i) => (
                  <div key={i} className="text-xs text-red-700">
                    {e.row ? `Rij ${e.row}` : ""}{e.code ? <> · <span className="font-mono">{e.code}</span></> : null} — {e.message}
                  </div>
                ))}
                {preview.error_count > 25 && <div className="text-xs text-muted-foreground">+{preview.error_count - 25} meer</div>}
                <div className="text-xs text-muted-foreground pt-1">Leg de koppeling vast in de productidentiteit of corrigeer het bestand en upload opnieuw.</div>
              </div>
            )}

            {preview.warnings.map((w, i) => (
              <div key={i} className="text-xs text-amber-600 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}</div>
            ))}

            {needsMapping && !result && (
              <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3 space-y-2">
                <div className="text-sm font-medium">{preview.mapping_proposal_count} nieuwe koppeling(en) DRS-productcode naar technisch product</div>
                <Table>
                  <TableHeader><TableRow><TableHead>Zakelijke SKU (DRS)</TableHead><TableHead>EAN</TableHead><TableHead>Technisch product-ID</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {preview.mapping_proposals.slice(0, 20).map((m, i) => (
                      <TableRow key={i}><TableCell className="font-mono text-xs">{m.code ?? "—"}</TableCell><TableCell className="font-mono text-xs">{m.ean ?? "—"}</TableCell><TableCell className="font-mono text-xs text-muted-foreground">{m.sku_id ?? "—"}</TableCell></TableRow>
                    ))}
                  </TableBody>
                </Table>
                <label className="flex items-start gap-2 text-sm cursor-pointer">
                  <Checkbox data-testid="checkbox-confirm-mapping" checked={confirmMapping} onCheckedChange={v => setConfirmMapping(v === true)} className="mt-0.5" />
                  Ik keur deze eenduidige koppelingen goed. Er worden geen producten samengevoegd.
                </label>
                {!preview.mapping_result && (
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <Button size="sm" variant="outline" data-testid="button-confirm-mappings" onClick={confirmMappingsOnly} disabled={!confirmMapping || busy !== null}>
                      {busy === "mapping" ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Koppelen…</> : "Alleen koppelingen vastleggen"}
                    </Button>
                    <span className="text-xs text-muted-foreground">Schrijft geen verkoop. {blocked ? "Onbekende of ambigue rijen blijven geblokkeerd; maak daarna een nieuwe preview." : ""}</span>
                  </div>
                )}
              </div>
            )}

            {sampleCols.length > 0 && !result && (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader><TableRow>{sampleCols.map(c => <TableHead key={c} className="text-xs">{c}</TableHead>)}</TableRow></TableHeader>
                  <TableBody>
                    {preview.sample.slice(0, 8).map((r, i) => (
                      <TableRow key={i}>{sampleCols.map(c => <TableCell key={c} className="text-xs font-mono">{String(r[c] ?? "")}</TableCell>)}</TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {preview.mapping_result && (
              <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm flex flex-wrap items-center gap-2" data-testid="text-mapping-result">
                <CheckCircle2 className="w-4 h-4 text-primary" />
                Koppelingen vastgelegd: {num(preview.mapping_result.mapped)} gekoppeld, {num(preview.mapping_result.unresolved)} onopgelost,
                {" "}{num(preview.mapping_result.sales_written)} verkoopregels geschreven.
                {blocked && <span className="text-muted-foreground">Herstel de resterende rijen en maak een nieuwe preview om de verkoop te importeren.</span>}
              </div>
            )}
            {resultMissing && !result && (
              <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3 text-sm text-amber-800 flex flex-wrap items-center gap-2" data-testid="text-daily-result-unavailable">
                <AlertTriangle className="w-4 h-4" />
                Deze import is bevestigd, maar de aantallen zijn nu niet beschikbaar.
                <Button size="sm" variant="outline" data-testid="button-daily-result-retry" onClick={retryResult} disabled={busy !== null}>
                  {busy === "load" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-1 h-4 w-4" />}Opnieuw ophalen
                </Button>
              </div>
            )}
            {result && (
              <div className="rounded-md border border-emerald-200 bg-emerald-50/50 p-3 text-sm text-emerald-700 flex items-center gap-2" data-testid="text-daily-result">
                <CheckCircle2 className="w-5 h-5" />
                Vastgelegd: {num(result.inserted)} nieuw, {num(result.updated)} gecorrigeerd, {num(result.unchanged)} ongewijzigd. Heruploaden telt niet dubbel.
              </div>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="flex gap-2 flex-wrap">
        {!preview && (
          <>
            <div className="relative flex-1">
              <Input type="file" accept=".xlsx" data-testid="input-daily-file" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                disabled={busy !== null}
                onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ""; }} />
              <Button variant="outline" size="sm" className="w-full" disabled={busy !== null}>
                <Upload className="mr-2 h-4 w-4" />{file ? file.name : "XLSX dagrapport kiezen"}
              </Button>
            </div>
            <Button size="sm" data-testid="button-daily-preview" onClick={runPreview} disabled={!file || !shopId || year.length !== 4 || busy !== null}>
              {busy === "preview" ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Bestand analyseren…</> : "Preview maken"}
            </Button>
          </>
        )}
        {preview && !result && !resultMissing && (
          <>
            <Button variant="outline" size="sm" data-testid="button-daily-reset" onClick={reset} disabled={busy === "confirm"}><RotateCcw className="mr-1 h-4 w-4" />Opnieuw</Button>
            <Button size="sm" className="ml-auto" data-testid="button-daily-confirm" onClick={confirm} disabled={!canConfirm || busy !== null}>
              {busy === "confirm" ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Vastleggen…</> : <><CheckCircle2 className="mr-2 h-4 w-4" />Bevestig {num(preview.fact_count)} dagregels</>}
            </Button>
          </>
        )}
        {(result || resultMissing) && <Button variant="outline" size="sm" data-testid="button-daily-new" onClick={reset}>Nieuwe dagimport</Button>}
      </CardFooter>
    </Card>
  );
}
