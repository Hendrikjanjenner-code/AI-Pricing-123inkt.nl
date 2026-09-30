import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { useDrsScope } from "@/hooks/use-drs-scope";
import { useMarginInsight } from "@/hooks/use-margin-insight";
import { CalendarRange, CheckCircle2, Loader2, Upload, AlertTriangle, RotateCcw, RefreshCcw, FileWarning } from "lucide-react";
import { drsApi, importPhase, num, type DailyPreview } from "@/lib/drs-daily-api";
import { ImportForm, type ImportFormValues } from "./drs-daily/import-form";
import { PreviewSummary } from "./drs-daily/preview-summary";
import { UnresolvedPanel } from "./drs-daily/unresolved-panel";
import { RecalcControl } from "./margin/recalc-control";

const STAGE_PREFIX = "drs_daily_stage_id";
const REPAIRED_PREFIX = "drs_daily_repaired";

type Busy = "preview" | "confirm" | "load" | "mapping" | "revalidate" | null;

export function DrsDailyImportCard() {
  const { toast } = useToast();
  const qc = useQueryClient();
  const { shop, shopId, userKey, scopeToken, isCurrent, shopsQuery } = useDrsScope();
  const margin = useMarginInsight("", true);
  const STAGE_KEY = scopeToken ? `${STAGE_PREFIX}:${scopeToken}` : null;

  const [form, setForm] = useState<ImportFormValues>({ year: "2026", start: "2026-08-30", end: "2026-09-30", sheet: "", codeCol: "1", eanCol: "3", firstDayCol: "5" });
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [preview, setPreview] = useState<DailyPreview | null>(null);
  const [confirmMapping, setConfirmMapping] = useState(false);
  const [resultMissing, setResultMissing] = useState(false);
  const [freshUpload, setFreshUpload] = useState(false);
  const [repairedRows, setRepairedRows] = useState<number[]>([]);
  const confirmingRef = useRef(false);

  const repairedKey = preview && scopeToken ? `${REPAIRED_PREFIX}:${scopeToken}:${preview.stage_id}` : null;
  useEffect(() => {
    if (!repairedKey) { setRepairedRows([]); return; }
    try { setRepairedRows(JSON.parse(localStorage.getItem(repairedKey) || "[]")); } catch { setRepairedRows([]); }
  }, [repairedKey]);

  const adoptPreview = useCallback((p: DailyPreview) => {
    setPreview(p); setConfirmMapping(false); setFreshUpload(false);
    setResultMissing(p.status === "confirmed" && !p.result);
    if (STAGE_KEY) localStorage.setItem(STAGE_KEY, String(p.stage_id));
  }, [STAGE_KEY]);

  // Herstel stage na reload; scopewissel wist alles.
  useEffect(() => {
    setPreview(null); setResultMissing(false); setConfirmMapping(false); setFreshUpload(false); setBusy(null);
    if (!STAGE_KEY || shopId === undefined) return;
    const id = localStorage.getItem(STAGE_KEY);
    if (!id) return;
    const token = scopeToken;
    setBusy("load");
    drsApi.getStage(id, shopId)
      .then(p => {
        if (!isCurrent(token)) return;
        if (p.shop_id !== shopId) { localStorage.removeItem(STAGE_KEY); return; }
        adoptPreview(p);
      })
      .catch((e: any) => {
        if (!isCurrent(token)) return;
        if (e.status === 404 || e.status === 403 || e.status === 410) localStorage.removeItem(STAGE_KEY);
        if (e.status === 410) setFreshUpload(true);
        else if (e.status !== 404 && e.status !== 403) toast({ title: "Import laden mislukt", description: e.message, variant: "destructive" });
      })
      .finally(() => { if (isCurrent(token)) setBusy(null); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [STAGE_KEY, shopId]);

  const guarded = async <T,>(kind: Busy, fn: () => Promise<T>, onOk: (r: T) => void, onErr: (e: any) => void) => {
    if (confirmingRef.current || shopId === undefined) return;
    confirmingRef.current = true;
    const token = scopeToken;
    setBusy(kind);
    try { const r = await fn(); if (isCurrent(token)) onOk(r); }
    catch (e: any) { if (isCurrent(token)) onErr(e); }
    finally { confirmingRef.current = false; if (isCurrent(token)) setBusy(null); }
  };

  const errTitle = (e: any, base: string) => e.status === 409 ? `${base} geblokkeerd` : e.status === 410 ? "Preview verlopen — upload opnieuw" : `${base} mislukt`;
  const handleErr = (base: string) => (e: any) => {
    if (e.status === 410) setFreshUpload(true);
    toast({ title: errTitle(e, base), description: e.message, variant: "destructive" });
  };

  const runPreview = () => {
    if (!file || shopId === undefined) return;
    if (!form.start || !form.end || form.start > form.end) {
      toast({ title: "Periode ongeldig", description: "Begin moet voor of op de einddatum liggen.", variant: "destructive" }); return;
    }
    const fd = new FormData();
    fd.append("file", file, file.name); fd.append("shop_id", String(shopId)); fd.append("year", form.year);
    fd.append("period_start", form.start); fd.append("period_end", form.end); fd.append("template", "drs-sales-wide-v1");
    const mapping: Record<string, unknown> = { code_column: Number(form.codeCol), ean_column: Number(form.eanCol), first_day_column: Number(form.firstDayCol) };
    if (form.sheet.trim()) mapping.sheet = form.sheet.trim();
    fd.append("mapping", JSON.stringify(mapping));
    setPreview(null);
    guarded("preview", () => drsApi.preview(fd), p => { if (p.shop_id === shopId) adoptPreview(p); }, handleErr("Preview"));
  };

  const confirm = () => preview && guarded("confirm",
    () => drsApi.confirm(preview.stage_id, shopId as number, confirmMapping || !!preview.mapping_result),
    r => {
      setPreview(p => p ? { ...p, status: "confirmed", result: r } : p); setResultMissing(false);
      toast({ title: "Dagverkoop vastgelegd", description: `${num(r.inserted)} nieuw, ${num(r.updated)} gecorrigeerd, ${num(r.unchanged)} ongewijzigd.` });
      qc.invalidateQueries({ queryKey: ["drs-margin-insight", userKey, shopId] });
    }, handleErr("Bevestigen"));

  const confirmMappingsOnly = () => preview && confirmMapping && guarded("mapping",
    () => drsApi.confirmMappings(preview.stage_id, shopId as number),
    r => {
      setPreview(p => p ? { ...p, mapping_result: r } : p);
      toast({ title: "Koppelingen vastgelegd", description: `${num(r.mapped)} gekoppeld, ${num(r.unresolved)} onopgelost. Geen verkoop geschreven.` });
      qc.invalidateQueries({ queryKey: ["drs-margin-insight", userKey, shopId] });
    }, handleErr("Koppelen"));

  const revalidate = () => preview && guarded("revalidate",
    () => drsApi.revalidate(preview.stage_id, shopId as number),
    p => {
      if (p.shop_id !== shopId) return;
      adoptPreview(p);
      toast({ title: "Nieuwe validatiepreview", description: `${num(p.resolved_error_count ?? 0)} blokkade(s) opgelost, ${num(p.error_count)} resterend.` });
      qc.invalidateQueries({ queryKey: ["drs-margin-insight", userKey, shopId] });
    }, e => { if (e.status === 409 || e.status === 410) setFreshUpload(true); handleErr("Hervalideren")(e); });

  const retryResult = () => preview && guarded("load", () => drsApi.getStage(preview.stage_id, shopId as number), p => {
    adoptPreview(p);
    if (!p.result) toast({ title: "Resultaat nog niet beschikbaar", description: "De server gaf geen importaantallen terug.", variant: "destructive" });
  }, e => toast({ title: "Ophalen mislukt", description: e.message, variant: "destructive" }));

  const markRepaired = (row: number) => setRepairedRows(prev => {
    const next = Array.from(new Set([...prev, row]));
    if (repairedKey) localStorage.setItem(repairedKey, JSON.stringify(next));
    return next;
  });
  const requireFresh = useCallback(() => setFreshUpload(true), []);

  const reset = () => {
    if (STAGE_KEY) localStorage.removeItem(STAGE_KEY);
    if (repairedKey) localStorage.removeItem(repairedKey);
    setPreview(null); setFile(null); setConfirmMapping(false); setResultMissing(false); setFreshUpload(false);
  };

  const phase = preview ? importPhase(preview, resultMissing) : null;
  const confirmed = phase === "confirmed" || phase === "confirmed_missing";
  const blocked = preview?.status === "blocked";
  const needsMapping = (preview?.mapping_proposal_count ?? 0) > 0;
  const canConfirm = !!preview && preview.status === "ready" && !confirmed && !freshUpload && (!needsMapping || confirmMapping || !!preview.mapping_result);
  const sampleCols = preview?.sample?.length ? Object.keys(preview.sample[0]) : [];
  const revalidated = preview?.previous_stage_id !== undefined && preview?.previous_stage_id !== null;

  return (
    <Card data-testid="card-drs-daily" className={`col-span-full ${confirmed ? "border-emerald-300" : blocked ? "border-red-300" : preview ? "border-primary/40" : ""}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex flex-wrap items-center gap-2">
          <CalendarRange className="h-5 w-5 text-primary" />DRS dagverkoop
          <Badge variant="outline" className="text-xs">Los van YTD/catalogus</Badge>
          {shop ? <Badge className="bg-primary/10 text-primary border-primary/20 text-xs" data-testid="badge-daily-shop">{shop.name}{shop.is_default ? " (standaard)" : ""}</Badge>
            : shopsQuery.isLoading ? <Badge variant="outline" className="text-xs">Winkel laden...</Badge>
            : shopsQuery.isError ? <Badge variant="outline" className="text-xs text-red-600 cursor-pointer" data-testid="button-daily-shops-retry" onClick={() => shopsQuery.refetch()}>Winkels laden mislukt — opnieuw</Badge>
            : <Badge variant="outline" className="text-xs text-amber-600" data-testid="badge-daily-no-shop">Geen geautoriseerde winkel</Badge>}
        </CardTitle>
        <CardDescription className="text-sm">
          Brede XLSX met twee kopregels. Productcodes blijven tekst, inclusief voorloopnullen. Onbekende of ambigue artikelen
          blokkeren de hele import totdat u ze expliciet herstelt en het volledige rapport opnieuw valideert.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {busy === "load" && !preview && <div className="h-24 rounded-md bg-muted/50 animate-pulse" />}

        {freshUpload && (
          <div className="rounded-md border border-amber-300 bg-amber-50/60 p-3 text-sm text-amber-900 flex flex-wrap items-center gap-2" data-testid="text-fresh-upload-required">
            <FileWarning className="h-4 w-4" />
            Deze preview is verlopen of mist de volledige bronmetadata. Herstel en hervalidatie vereisen een nieuwe upload van hetzelfde rapport; eerder vastgelegde beslissingen blijven behouden.
            <Button size="sm" variant="outline" onClick={reset} data-testid="button-fresh-upload"><Upload className="mr-1 h-4 w-4" />Nieuw bestand uploaden</Button>
          </div>
        )}

        {!preview && busy !== "load" && <ImportForm values={form} onChange={setForm} />}

        {preview && phase && (
          <div className="space-y-3">
            {revalidated && (
              <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm" data-testid="text-revalidation-result">
                Nieuwe preview na herstel (vorige stage <span className="font-mono">{String(preview.previous_stage_id)}</span>):{" "}
                <b>{num(preview.resolved_error_count ?? 0)}</b> van {num(preview.previous_error_count ?? 0)} blokkades opgelost, <b>{num(preview.error_count)}</b> resterend.
                {preview.error_count > 0 && " Herstel de resterende regels hieronder en valideer opnieuw."}
              </div>
            )}

            <PreviewSummary preview={preview} phase={phase} shopName={shop?.name ?? `Winkel #${preview.shop_id}`} />

            {preview.error_count > 0 && !confirmed && shopId !== undefined && (
              <UnresolvedPanel stageId={preview.stage_id} shopId={shopId} scopeToken={scopeToken} isCurrent={isCurrent}
                totalErrors={preview.error_count} repairedRows={repairedRows} onRepaired={markRepaired} onFreshUploadRequired={requireFresh} />
            )}

            {blocked && !confirmed && (
              <div className="flex flex-wrap items-center gap-2 rounded-md border p-3 text-xs">
                <Button size="sm" onClick={revalidate} disabled={busy !== null || freshUpload} data-testid="button-daily-revalidate">
                  {busy === "revalidate" ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Volledig rapport valideren...</> : <><RefreshCcw className="mr-2 h-4 w-4" />Hervalideer volledig rapport</>}
                </Button>
                <span className="text-muted-foreground">Maakt een nieuwe preview van alle regels. Deze preview blijft ongewijzigd; alleen echt opgeloste regels tellen als opgelost.</span>
              </div>
            )}

            {needsMapping && !confirmed && (
              <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3 space-y-2">
                <div className="text-sm font-medium">{num(preview.mapping_proposal_count)} nieuwe koppeling(en) DRS-productcode naar technisch product</div>
                <div className="overflow-x-auto"><Table>
                  <TableHeader><TableRow><TableHead>Zakelijke SKU (DRS)</TableHead><TableHead>EAN</TableHead><TableHead>Technisch product-ID</TableHead></TableRow></TableHeader>
                  <TableBody>{preview.mapping_proposals.slice(0, 20).map((m, i) => (
                    <TableRow key={i}><TableCell className="font-mono text-xs">{m.code ?? "—"}</TableCell><TableCell className="font-mono text-xs">{m.ean ?? "—"}</TableCell><TableCell className="font-mono text-xs text-muted-foreground">{m.sku_id ?? "—"}</TableCell></TableRow>
                  ))}</TableBody>
                </Table></div>
                {preview.mapping_proposal_count > 20 && <div className="text-xs text-muted-foreground">+{num(preview.mapping_proposal_count - 20)} meer</div>}
                <label className="flex items-start gap-2 text-sm cursor-pointer">
                  <Checkbox data-testid="checkbox-confirm-mapping" checked={confirmMapping} onCheckedChange={v => setConfirmMapping(v === true)} className="mt-0.5" />
                  Ik keur deze eenduidige koppelingen goed. Er worden geen producten samengevoegd.
                </label>
                {!preview.mapping_result && (
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <Button size="sm" variant="outline" data-testid="button-confirm-mappings" onClick={confirmMappingsOnly} disabled={!confirmMapping || busy !== null}>
                      {busy === "mapping" ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Koppelen...</> : "Alleen koppelingen vastleggen"}
                    </Button>
                    <span className="text-xs text-muted-foreground">Schrijft geen verkoop.</span>
                  </div>
                )}
              </div>
            )}

            {preview.mapping_result && !confirmed && (
              <div className="rounded-md border border-amber-200 bg-amber-50/40 p-3 text-sm" data-testid="text-mapping-result">
                Alleen koppelingen vastgelegd: {num(preview.mapping_result.mapped)} gekoppeld, {num(preview.mapping_result.unresolved)} onopgelost,
                {" "}{num(preview.mapping_result.sales_written)} verkoopregels geschreven.
              </div>
            )}

            {sampleCols.length > 0 && !confirmed && (
              <details className="rounded-md border">
                <summary className="cursor-pointer px-3 py-2 text-xs text-muted-foreground" data-testid="toggle-daily-sample">Voorbeeldregels uit preview</summary>
                <div className="overflow-x-auto"><Table>
                  <TableHeader><TableRow>{sampleCols.map(c => <TableHead key={c} className="text-xs">{c}</TableHead>)}</TableRow></TableHeader>
                  <TableBody>{preview.sample.slice(0, 8).map((r, i) => (
                    <TableRow key={i}>{sampleCols.map(c => <TableCell key={c} className="text-xs font-mono">{String(r[c] ?? "")}</TableCell>)}</TableRow>
                  ))}</TableBody>
                </Table></div>
              </details>
            )}

            {phase === "confirmed_missing" && (
              <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3 text-sm text-amber-800 flex flex-wrap items-center gap-2" data-testid="text-daily-result-unavailable">
                <AlertTriangle className="w-4 h-4" />Deze import is bevestigd, maar de aantallen zijn nu niet beschikbaar.
                <Button size="sm" variant="outline" data-testid="button-daily-result-retry" onClick={retryResult} disabled={busy !== null}>
                  {busy === "load" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-1 h-4 w-4" />}Opnieuw ophalen
                </Button>
              </div>
            )}
            {preview.result && (
              <div className="rounded-md border border-emerald-200 bg-emerald-50/50 p-3 text-sm text-emerald-700 flex items-center gap-2" data-testid="text-daily-result">
                <CheckCircle2 className="w-5 h-5" />Vastgelegd: {num(preview.result.inserted)} nieuw, {num(preview.result.updated)} gecorrigeerd, {num(preview.result.unchanged)} ongewijzigd. Heruploaden telt niet dubbel.
              </div>
            )}
            {confirmed && (
              <div className="rounded-md border p-3 space-y-2" data-testid="panel-daily-recalc">
                <div className="text-sm font-medium">Volgende stap: prijsadviezen herberekenen met deze verkoop</div>
                {margin.query.isError
                  ? <div className="text-xs text-red-700 flex items-center gap-2">Status herberekening onbekend: {(margin.query.error as Error).message}
                      <Button size="sm" variant="outline" onClick={() => margin.query.refetch()} data-testid="button-recalc-status-retry">Opnieuw</Button></div>
                  : margin.query.isLoading ? <div className="h-8 rounded bg-muted/60 animate-pulse" />
                  : <RecalcControl insight={margin.query.data} starting={margin.starting} onRecalculate={margin.recalculate} shopName={shop?.name} />}
              </div>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="flex gap-2 flex-wrap">
        {!preview && (
          <>
            <div className="relative flex-1 min-w-[200px]">
              <Input type="file" accept=".xlsx" data-testid="input-daily-file" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" disabled={busy !== null}
                onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ""; }} />
              <Button variant="outline" size="sm" className="w-full" disabled={busy !== null}><Upload className="mr-2 h-4 w-4" />{file ? file.name : "XLSX dagrapport kiezen"}</Button>
            </div>
            <Button size="sm" data-testid="button-daily-preview" onClick={runPreview} disabled={!file || shopId === undefined || form.year.length !== 4 || busy !== null}>
              {busy === "preview" ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Bestand analyseren...</> : "Preview maken"}
            </Button>
          </>
        )}
        {preview && !confirmed && (
          <>
            <Button variant="outline" size="sm" data-testid="button-daily-reset" onClick={reset} disabled={busy !== null}><RotateCcw className="mr-1 h-4 w-4" />Opnieuw uploaden</Button>
            <Button size="sm" className="ml-auto" data-testid="button-daily-confirm" onClick={confirm} disabled={!canConfirm || busy !== null}
              title={blocked ? "Alleen een nieuwe geldige preview kan verkoop bevestigen" : undefined}>
              {busy === "confirm" ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Vastleggen...</> : <><CheckCircle2 className="mr-2 h-4 w-4" />Bevestig {num(preview.fact_count)} dagregels</>}
            </Button>
          </>
        )}
        {confirmed && <Button variant="outline" size="sm" data-testid="button-daily-new" onClick={reset}>Nieuwe dagimport</Button>}
      </CardFooter>
    </Card>
  );
}
