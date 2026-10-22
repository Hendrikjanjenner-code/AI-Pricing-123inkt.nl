import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Info, Lock, Play, Upload } from "lucide-react";
import {
  useGetCostPriority, getGetCostPriorityQueryKey, useGetCostPriorityHistory, getGetCostPriorityHistoryQueryKey,
  useActivateCostPriority, previewCostPriority,
} from "@workspace/api-client-react";
import type { CostPriorityConfiguration, CostPriorityPreview, CostPriorityRules } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useToast } from "@/hooks/use-toast";
import { useCostPriorityScope } from "@/hooks/use-cost-priority-scope";
import { setActiveShopId } from "@/hooks/use-shop-id";
import { RuleEditor } from "@/components/pricing-hub/RuleEditor";
import { PreviewInput } from "@/components/pricing-hub/PreviewInput";
import type { InputMode } from "@/components/pricing-hub/PreviewInput";
import { PreviewResults } from "@/components/pricing-hub/PreviewResults";
import { HistoryPanel } from "@/components/pricing-hub/HistoryPanel";
import { Explainer } from "@/components/pricing-hub/Explainer";
import {
  describeApiError, emptyManualRow, manualRowsError, previewFingerprint, rulesEqual, sourcesOf, toScenarioRows,
} from "@/lib/cost-priority/model";
import type { ManualRow } from "@/lib/cost-priority/model";
import { previewWorkbook, workbookFileError } from "@/lib/cost-priority/workbook";

interface StoredDraft { revision: number; rules: CostPriorityRules }

export default function PricingHub() {
  const { shops, shop, shopId, userKey, scopeToken, isCurrent, shopsQuery } = useCostPriorityScope();
  const shopPicker = shops.length > 0 ? (
    <label className="mb-4 flex items-center gap-3 text-sm">
      Winkel
      <select
        className="rounded-md border bg-background px-3 py-2"
        aria-label="Pricing Hub winkel"
        data-testid="select-pricing-hub-shop"
        value={shopId ?? ""}
        onChange={event => setActiveShopId(Number(event.target.value))}
      >
        {shopId === undefined && <option value="" disabled>Kies een toegestane winkel</option>}
        {shops.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
    </label>
  ) : null;

  if (shopId === undefined) {
    return (
      <Shell>
        {shopPicker}
        {shopsQuery.isLoading ? <Skeleton className="h-64 w-full" data-testid="skeleton-shops" /> : (
          <Alert variant="destructive" data-testid="status-no-shop">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Geen winkel beschikbaar</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center gap-3">
              {shopsQuery.isError ? "De winkellijst kon niet worden geladen." : "Er is geen winkel waarvoor je gemachtigd bent. Kies een winkel via de winkelwissel."}
              <Button variant="outline" size="sm" onClick={() => shopsQuery.refetch()} data-testid="button-retry-shops">Opnieuw</Button>
            </AlertDescription>
          </Alert>
        )}
      </Shell>
    );
  }
  // key = scope: elke gebruiker/winkel-wissel geeft een volledig verse staat.
  return (
    <Shell shopName={shop?.name}>
      {shopPicker}
      <CostPriorityWorkspace key={scopeToken ?? "x"} shopId={shopId} userKey={userKey} scopeToken={scopeToken} isCurrent={isCurrent} />
    </Shell>
  );
}

function CostPriorityWorkspace({ shopId, userKey, scopeToken, isCurrent }: {
  shopId: number; userKey: string; scopeToken: string | null; isCurrent: (t: string | null) => boolean;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const configKey = [...getGetCostPriorityQueryKey(shopId), userKey];
  const configQ = useGetCostPriority(shopId, { query: { queryKey: configKey, retry: 1 } });
  const config = configQ.data && configQ.data.shop_id === shopId ? configQ.data : undefined;
  const historyKey = [...getGetCostPriorityHistoryQueryKey(shopId), userKey];
  const historyQ = useGetCostPriorityHistory(shopId, { query: { queryKey: historyKey, enabled: !!config?.can_edit, retry: 1 } });

  // --- Concept (scoped sessionStorage: gebruiker + winkel) ---
  const storageKey = `pricing-hub:cost-draft:${scopeToken}`;
  const [draft, setDraft] = useState<CostPriorityRules | null>(null);
  const [draftNotice, setDraftNotice] = useState<string | null>(null);
  const initRevision = useRef<number | null>(null);
  const activatedRef = useRef(false);
  useEffect(() => {
    if (!config || initRevision.current === config.revision) return;
    const first = initRevision.current === null;
    initRevision.current = config.revision;
    if (!first && activatedRef.current) { activatedRef.current = false; setDraft(config.rules); setDraftNotice(null); return; }
    if (!first) {
      // Nieuwe serverrevisie (bijv. na conflict): concept behouden, preview moet opnieuw.
      setDraftNotice(`De actieve regels zijn bijgewerkt naar revisie ${config.revision}. Je concept is behouden; bereken een nieuwe preview.`);
      return;
    }
    let stored: StoredDraft | null = null;
    try { stored = JSON.parse(sessionStorage.getItem(storageKey) || "null"); } catch { stored = null; }
    if (stored && stored.revision === config.revision) setDraft(stored.rules);
    else {
      if (stored) setDraftNotice("Je eerdere concept was gebaseerd op een oudere revisie en is vervangen door de actieve regels.");
      setDraft(config.rules);
    }
  }, [config, storageKey]);
  useEffect(() => {
    if (!config || !draft) return;
    try {
      if (rulesEqual(draft, config.rules)) sessionStorage.removeItem(storageKey);
      else sessionStorage.setItem(storageKey, JSON.stringify({ revision: config.revision, rules: draft } satisfies StoredDraft));
    } catch { /* opslag niet beschikbaar */ }
  }, [draft, config, storageKey]);

  const [targetKey, setTargetKey] = useState("print");
  const dirty = !!config && !!draft && !rulesEqual(draft, config.rules);
  const sources = useMemo(() => (draft ? sourcesOf(draft) : []), [draft]);

  // --- Preview-invoer ---
  const [mode, setMode] = useState<InputMode>("manual");
  const [file, setFile] = useState<File | null>(null);
  const [manualRows, setManualRows] = useState<ManualRow[]>([emptyManualRow(1, "Print"), emptyManualRow(2, "Kantoor")]);
  const fileErr = workbookFileError(file);
  const manualErr = manualRowsError(manualRows);
  const inputSig = mode === "workbook"
    ? `wb:${file ? `${file.name}:${file.size}:${file.lastModified}` : ""}`
    : `m:${JSON.stringify(manualRows)}`;
  const fp = draft ? previewFingerprint({ userKey, shopId, revision: config?.revision, rules: draft, inputSig }) : "";

  const [preview, setPreview] = useState<CostPriorityPreview | null>(null);
  const [previewFp, setPreviewFp] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [conflict, setConflict] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Elke wijziging in concept/invoer/revisie: token wissen, lopende preview afbreken.
  useEffect(() => {
    if (previewFp !== null && previewFp !== fp) setToken(null);
    abortRef.current?.abort();
    setPreviewErr(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fp]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const stale = !!preview && previewFp !== fp;
  const expired = !!preview && new Date(preview.expires_at).getTime() < Date.now();
  const canEdit = !!config?.can_edit;
  const inputError = mode === "workbook" ? fileErr : manualErr;
  const canPreview = canEdit && !!draft && !!config && !inputError && !previewing;

  async function runPreview() {
    if (!config || !draft) return;
    abortRef.current?.abort();
    const ctrl = new AbortController(); abortRef.current = ctrl;
    const myScope = scopeToken; const myFp = fp;
    setPreviewing(true); setPreviewErr(null); setConflict(null); setToken(null);
    try {
      const res = mode === "workbook" && file
        ? await previewWorkbook({ shopId, file, baseRevision: config.revision, rules: draft, signal: ctrl.signal })
        : await previewCostPriority(shopId, { base_revision: config.revision, rules: draft, rows: toScenarioRows(manualRows, sources) }, { signal: ctrl.signal });
      if (ctrl.signal.aborted || !isCurrent(myScope) || res.shop_id !== shopId) return;
      setPreview(res); setPreviewFp(myFp); setToken(res.can_activate ? res.preview_token : null);
    } catch (e) {
      if (ctrl.signal.aborted || !isCurrent(myScope)) return;
      const err = describeApiError(e);
      if (err.kind === "conflict") { setConflict(err.message); configQ.refetch(); }
      else setPreviewErr(err.message);
    } finally {
      if (abortRef.current === ctrl) setPreviewing(false);
    }
  }

  const activateM = useActivateCostPriority();
  function activate() {
    if (!config || !token || stale) return;
    const myScope = scopeToken;
    activateM.mutate({ shopId, data: { preview_token: token, base_revision: config.revision } }, {
      onSuccess: (next: CostPriorityConfiguration) => {
        if (!isCurrent(myScope)) return;
        setToken(null); setPreview(null); setPreviewFp(null);
        activatedRef.current = true;
        try { sessionStorage.removeItem(storageKey); } catch { /* */ }
        qc.setQueryData(configKey, next);
        qc.invalidateQueries({ queryKey: historyKey });
        toast({ title: "Kostprioriteit geactiveerd", description: `Revisie ${next.revision} opgeslagen. Live prijzen zijn niet gewijzigd.` });
      },
      onError: (e) => {
        if (!isCurrent(myScope)) return;
        const err = describeApiError(e);
        setToken(null);
        if (err.kind === "conflict") { setConflict(err.message); configQ.refetch(); }
        else toast({ title: "Activeren mislukt", description: err.message, variant: "destructive" });
      },
    });
  }

  if (configQ.isLoading || (config && !draft)) {
    return <div className="space-y-3" data-testid="skeleton-rules"><Skeleton className="h-10 w-72" /><Skeleton className="h-80 w-full" /></div>;
  }
  if (configQ.isError || !config || !draft) {
    const err = describeApiError(configQ.error);
    return (
      <Alert variant="destructive" data-testid="status-rules-error">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Kostprioriteiten konden niet worden geladen</AlertTitle>
        <AlertDescription className="flex flex-wrap items-center gap-3">
          {err.message}
          <Button variant="outline" size="sm" onClick={() => configQ.refetch()} data-testid="button-retry-rules">Opnieuw</Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
      <section className="space-y-4">
        <div className="text-xs text-muted-foreground" data-testid="text-active-revision">
          Actief: {config.revision === 0 ? "Excel-default (nog geen versie opgeslagen)" : `revisie ${config.revision}`}
          {config.version_id !== undefined && ` · versie-ID ${config.version_id}`} · alleen configuratie, geen live prijzen
        </div>
        {!canEdit && (
          <Alert data-testid="status-read-only"><Lock className="h-4 w-4" /><AlertTitle>Alleen lezen</AlertTitle>
            <AlertDescription>Je mag de kostprioriteit bekijken, maar niet wijzigen. Preview en activeren vereisen de rol pricing manager.</AlertDescription></Alert>
        )}
        {draftNotice && <Alert data-testid="status-draft-notice"><Info className="h-4 w-4" /><AlertDescription>{draftNotice}</AlertDescription></Alert>}
        <RuleEditor
          rules={draft} onChange={setDraft} dirty={dirty} onDiscard={() => setDraft(config.rules)}
          canEdit={canEdit} activeKey={targetKey} onActiveKey={setTargetKey}
        />
        <Explainer sources={sources} />
      </section>

      <section className="space-y-4">
        <div className="rounded-lg border bg-card">
          <div className="border-b px-4 py-3">
            <h2 className="font-semibold">Preview-invoer</h2>
            <p className="text-xs text-muted-foreground">De preview vergelijkt het volledige concept met de actieve regels op dezelfde referentie-invoer.</p>
          </div>
          <PreviewInput
            mode={mode} onMode={setMode} file={file} onFile={setFile} fileError={fileErr}
            rows={manualRows} onRows={setManualRows} sources={sources} customSource={draft.custom_source}
          />
          <div className="flex flex-wrap items-center gap-2 border-t px-4 py-3">
            <Button onClick={runPreview} disabled={!canPreview} data-testid="button-preview">
              {mode === "workbook" ? <Upload className="mr-1 h-4 w-4" /> : <Play className="mr-1 h-4 w-4" />}
              {previewing ? "Preview berekenen…" : "Preview berekenen"}
            </Button>
            <Button className="bg-emerald-700 text-white hover:bg-emerald-800" onClick={activate} disabled={!canEdit || !token || stale || expired || activateM.isPending} data-testid="button-activate">
              <CheckCircle2 className="mr-1 h-4 w-4" />{activateM.isPending ? "Activeren…" : "Gepreviewde regels activeren"}
            </Button>
            {inputError && canEdit && <span className="text-xs text-muted-foreground" data-testid="text-input-hint">{inputError}</span>}
          </div>
        </div>

        {conflict && (
          <Alert variant="destructive" data-testid="status-conflict">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Preview niet meer geldig</AlertTitle>
            <AlertDescription>De regels zijn intussen gewijzigd, of het token is verlopen of al gebruikt. De actieve regels zijn herladen; bereken een nieuwe preview. ({conflict})</AlertDescription>
          </Alert>
        )}
        {previewErr && <Alert variant="destructive" data-testid="status-preview-error"><AlertTriangle className="h-4 w-4" /><AlertTitle>Preview mislukt</AlertTitle><AlertDescription>{previewErr}</AlertDescription></Alert>}
        {stale && <Alert data-testid="status-preview-stale"><Info className="h-4 w-4" /><AlertTitle>Preview verouderd</AlertTitle><AlertDescription>Concept, invoer of revisie is gewijzigd. Het activatietoken is gewist; bereken een nieuwe preview.</AlertDescription></Alert>}
        {expired && !stale && <Alert data-testid="status-preview-expired"><Info className="h-4 w-4" /><AlertTitle>Preview verlopen</AlertTitle><AlertDescription>Previews zijn 30 minuten geldig. Bereken een nieuwe preview.</AlertDescription></Alert>}
        {previewing && <Skeleton className="h-48 w-full" data-testid="skeleton-preview" />}
        {!preview && !previewing && <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground" data-testid="status-preview-empty">Nog geen preview. Vul scenario's in of upload een werkboek.</div>}
        {preview && !previewing && <PreviewResults preview={preview} stale={stale} />}

        {canEdit && (
          <HistoryPanel versions={historyQ.data?.versions} isLoading={historyQ.isLoading} isError={historyQ.isError} onRetry={() => historyQ.refetch()} />
        )}
      </section>
    </div>
  );
}

function Shell({ children, shopName }: { children: React.ReactNode; shopName?: string }) {
  return (
    <div className="space-y-6 p-6" data-testid="page-pricing-hub">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Pricing Hub — Kostprioriteit</h1>
        <p className="text-sm text-muted-foreground">
          Bepaal welke kostbron als eerste geldt, per Print, overige categorieën of een specifieke categorie.
          {shopName && <span className="ml-1" data-testid="text-shop-name">Winkel: {shopName}</span>}
        </p>
      </header>
      {children}
    </div>
  );
}
