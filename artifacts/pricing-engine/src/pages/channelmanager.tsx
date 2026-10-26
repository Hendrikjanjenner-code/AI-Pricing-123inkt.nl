import { useMemo, useState } from "react";
import { AlertTriangle, CalendarClock, ChevronRight, Play, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCostPriorityScope } from "@/hooks/use-cost-priority-scope";
import { setActiveShopId } from "@/hooks/use-shop-id";
import { useCmAction, useCmOverview } from "@/hooks/use-channelmanager";
import type { CmScope } from "@/hooks/use-channelmanager";
import { useChannelRegistry } from "@/hooks/use-channel-registry";
import { cmApi, fmtDate } from "@/lib/channelmanager/api";
import { COUNT_KEYS, QUEUE_KEYS, parseConfig, parseRun } from "@/lib/channelmanager/model";
import type { Overview } from "@/lib/channelmanager/model";
import { ErrorBox, STATUS_NL, StatusBadge } from "@/components/channelmanager/common";
import { ConfigPanel } from "@/components/channelmanager/ConfigPanel";
import { BasisPanel } from "@/components/channelmanager/BasisPanel";
import { CalcPanel } from "@/components/channelmanager/CalcPanel";
import { ExportPanel } from "@/components/channelmanager/ExportPanel";
import { ChannelList } from "@/components/channelmanager/ChannelList";
import { ChannelSetup, useTargetScope } from "@/components/channelmanager/ChannelSetup";
import { FeedProfilesPanel } from "@/components/feeds/FeedProfilesPanel";
import { PrinterPanel } from "@/components/feeds/PrinterPanel";

type Tab = "regels" | "basis" | "proef" | "export" | "feeds" | "printer";
const TABS: { id: Tab; label: string; sub: string }[] = [
  { id: "regels", label: "Shops & regels", sub: "Configuratie per winkel" },
  { id: "basis", label: "Basisprijzen", sub: "Import en goedkeuring" },
  { id: "proef", label: "Proefberekeningen", sub: "Rekenen en goedkeuren" },
  { id: "export", label: "Exports & DRS", sub: "Download en terugmelding" },
  { id: "feeds", label: "Feeds & koppelingen", sub: "Product, advies, kosten" },
  { id: "printer", label: "Printer-werkboek", sub: "Advies naar shopprijzen" },
];
const COUNT_NL: Record<(typeof COUNT_KEYS)[number], string> = {
  basis: "Basisversies", calculation: "Berekeningen", export: "Exports", readback: "Terugmeldingen", run: "Runs",
};
const REASON_NL: Record<string, string> = {
  disabled_by_environment_or_tests: "uitgeschakeld via omgeving of tests",
  application_scheduler_not_started: "planner is in deze applicatie niet gestart",
};

type View =
  | { kind: "list" }
  | { kind: "setup"; channelId: string }
  | { kind: "workspace"; shopId: number; tab: Tab; fromChannel: string | null };

export default function Channelmanager() {
  const { shops, shopId, userKey, scopeToken, isCurrent, shopsQuery } = useCostPriorityScope();
  const shopList = useMemo(() => shops.map(s => ({ id: s.id, name: s.name })), [shops]);
  const scope = useMemo<CmScope | null>(() => shopId === undefined || !scopeToken ? null : { shopId, userKey, scopeToken, isCurrent }, [shopId, userKey, scopeToken, isCurrent]);

  return (
    <div className="mx-auto w-full max-w-[1240px] min-w-0 space-y-6 px-3 py-5 sm:px-5 md:px-8 md:py-8">
      {!scope ? (
        <>
          <h1 className="text-3xl font-light tracking-tight">Kanalen</h1>
          {shopsQuery.isLoading ? <Skeleton className="h-48" data-testid="skeleton-shops" /> :
            shopsQuery.isError ? <ErrorBox error={shopsQuery.error} onRetry={() => shopsQuery.refetch()} /> :
              <p className="rounded-md border p-4 text-sm" data-testid="status-no-shop">Er is geen winkel waarvoor je gemachtigd bent.</p>}
        </>
      ) : (
        <SourceScope key={scope.scopeToken} scope={scope} shops={shopList} />
      )}
    </div>
  );
}

function SourceScope({ scope, shops }: { scope: CmScope; shops: { id: number; name: string }[] }) {
  const [view, setView] = useState<View>({ kind: "list" });
  const reg = useChannelRegistry(scope);
  const sourceName = shops.find(s => s.id === scope.shopId)?.name ?? `winkel #${scope.shopId}`;
  const channel = view.kind === "setup" ? reg.data?.channels.find(c => c.id === view.channelId) : undefined;
  const wsChannel = view.kind === "workspace" && view.fromChannel !== null ? reg.data?.channels.find(c => c.id === view.fromChannel) : undefined;

  const crumbs: { label: string; onClick?: () => void }[] = [{ label: "Kanalen", onClick: view.kind === "list" ? undefined : () => setView({ kind: "list" }) }];
  if (view.kind === "setup") crumbs.push({ label: channel?.name ?? "Kanaal" });
  if (view.kind === "workspace") {
    if (wsChannel) crumbs.push({ label: wsChannel.name, onClick: () => setView({ kind: "setup", channelId: wsChannel.id }) });
    crumbs.push({ label: `Werkruimte ${shops.find(s => s.id === view.shopId)?.name ?? `#${view.shopId}`}` });
  }

  return (
    <>
      <header className="space-y-3">
        <nav aria-label="Kruimelpad" className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground" data-testid="breadcrumb">
          <span className="font-mono">{sourceName}</span>
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1"><ChevronRight className="h-3 w-3" />
              {c.onClick ? <button className="text-primary hover:underline" onClick={c.onClick}>{c.label}</button> : <span className="text-foreground">{c.label}</span>}
            </span>
          ))}
        </nav>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h1 className="text-3xl md:text-4xl font-light tracking-tight" data-testid="text-page-title">
            {view.kind === "list" ? "Kanalen" : view.kind === "setup" ? channel?.name ?? "Kanaal" : "Werkruimte"}
          </h1>
          <div className="flex flex-wrap items-center gap-2">
            {view.kind === "list" && (
              <label className="flex items-center gap-2 text-sm text-muted-foreground">Bronwinkel
                <select className="h-9 rounded-md border bg-card px-3 text-foreground" value={scope.shopId} onChange={e => setActiveShopId(Number(e.target.value))} data-testid="select-cm-shop" aria-label="Bronwinkel">
                  {shops.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </label>
            )}
            {view.kind !== "workspace" && <Button variant="outline" size="sm" onClick={() => setView({ kind: "workspace", shopId: scope.shopId, tab: "regels", fromChannel: null })} data-testid="button-open-workspace">Werkruimte bronwinkel</Button>}
          </div>
        </div>
      </header>

      {view.kind === "workspace" ? (
        <WorkspaceScope key={`${view.shopId}`} source={scope} shopId={view.shopId} initialTab={view.tab} shops={shops} />
      ) : reg.isLoading ? (
        <div className="space-y-2" data-testid="skeleton-registry">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-14" />)}</div>
      ) : reg.isError || !reg.data ? (
        <ErrorBox error={reg.error} onRetry={() => reg.refetch()} />
      ) : view.kind === "list" ? (
        <ChannelList scope={scope} reg={reg.data} shops={shops} onSetup={id => setView({ kind: "setup", channelId: id })} />
      ) : !channel ? (
        <ErrorBox error={new Error("Dit kanaal bestaat niet meer in het register.")} onRetry={() => setView({ kind: "list" })} />
      ) : (
        <ChannelSetup key={channel.id} scope={scope} reg={reg.data} channel={channel} shops={shops}
          onOpenTarget={(shopId, tab) => setView({ kind: "workspace", shopId, tab, fromChannel: channel.id })} />
      )}
    </>
  );
}

/** Bestaande zes tabbladen; doel-scope lokaal, globale winkel blijft ongewijzigd. */
function WorkspaceScope({ source, shopId, initialTab, shops }: { source: CmScope; shopId: number; initialTab: Tab; shops: { id: number; name: string }[] }) {
  const target = useTargetScope(source, shopId);
  const scope = shopId === source.shopId ? source : target;
  const [tab, setTab] = useState<Tab>(initialTab);
  const [exportFocus, setExportFocus] = useState(0);
  return <ShopWorkspace scope={scope} shops={shops} tab={tab} setTab={setTab} exportFocus={exportFocus} onExported={() => { setExportFocus(x => x + 1); setTab("export"); }} />;
}

function ShopWorkspace({ scope, shops, tab, setTab, exportFocus, onExported }: {
  scope: CmScope; shops: { id: number; name: string }[]; tab: Tab; setTab: (t: Tab) => void; exportFocus: number; onExported: () => void;
}) {
  const q = useCmOverview(scope);
  if (q.isLoading) return <div className="space-y-3"><Skeleton className="h-28" /><Skeleton className="h-96" /></div>;
  if (q.isError || !q.data) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const ov = q.data;
  return (
    <div className="space-y-5 min-w-0">
      <Summary scope={scope} ov={ov} onRefresh={() => q.refetch()} refreshing={q.isFetching} />
      <nav className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-1 rounded-lg border bg-muted/40 p-1" role="tablist">
        {TABS.map((t, i) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} data-testid={`tab-${t.id}`}
            className={`rounded-md px-3 py-2 text-left transition-colors ${tab === t.id ? "bg-card shadow-sm" : "hover:bg-card/60"}`}>
            <span className="text-[10px] font-mono text-muted-foreground">0{i + 1}</span>
            <div className="text-sm font-medium">{t.label}</div>
            <div className="text-[11px] text-muted-foreground">{t.sub}</div>
          </button>
        ))}
      </nav>
      {tab === "regels" && <ConfigPanel scope={scope} overview={ov} canPropose={ov.can_propose} shops={shops} />}
      {tab === "basis" && <BasisPanel scope={scope} overview={ov} canPropose={ov.can_propose} canApprove={ov.can_approve} />}
      {tab === "proef" && <CalcPanel scope={scope} overview={ov} shops={shops} canPropose={ov.can_propose} canApprove={ov.can_approve} canExport={ov.can_export} onExported={onExported} />}
      {tab === "export" && <ExportPanel scope={scope} overview={ov} canPropose={ov.can_propose} canExport={ov.can_export} focusId={exportFocus} />}
      {tab === "feeds" && <FeedProfilesPanel scope={scope} purposes={["products", "advice", "cost", "cost_output"]} title="Feeds & koppelingen"
        intro="Productreferentie en PriceShape-adviezen als afzonderlijke inputs, plus de Hub-kostketen. Alles start uit; opslaan of uploaden activeert niets. De concurrentiefeed blijft ongewijzigd." />}
      {tab === "printer" && <PrinterPanel scope={scope} shops={shops} canPropose={ov.can_propose} canApprove={ov.can_approve} />}
    </div>
  );
}

function Summary({ scope, ov, onRefresh, refreshing }: { scope: CmScope; ov: Overview; onRefresh: () => void; refreshing: boolean }) {
  const { run, busy, lastError } = useCmAction(scope);
  const cfg = ov.config ? parseConfig(ov.config).data.config : null;
  const lastRun = ov.last_run ? parseRun(ov.last_run) : null;
  const sc = ov.scheduler;
  return (
    <div className="space-y-3">
      {ov.external_formats === "provisional_unconfirmed" && (
        <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm" data-testid="status-provisional">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <span><strong>Voorlopige configuratie.</strong> Externe CSV-formaten (bron, shopexport, DRS) zijn generiek en niet bevestigd voor echte koppelingen. Alle bronnen gelden als onbevestigd tot jij ze bevestigt.</span>
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-[1fr_1.2fr_1.3fr]">
        <div className="rounded-lg border bg-card p-3 text-sm space-y-1" data-testid="card-config-summary">
          <div className="text-xs text-muted-foreground">Configuratie</div>
          {ov.config && cfg ? <><div>Revisie <span className="font-mono">r{ov.config.revision}</span> <StatusBadge status={ov.config.status} /></div>
            <div className="text-xs text-muted-foreground">{cfg.rule.kind === "fixed" ? "Vast" : "Percentage"} {cfg.rule.value} · {cfg.currency} · {cfg.price_basis === "gross" ? "bruto" : "netto"} · btw {cfg.vat_rate}</div></>
            : <div className="text-amber-700">Nog niet ingesteld</div>}
          <div className="text-xs text-muted-foreground">Basis: {ov.basis ? `#${ov.basis.id} r${ov.basis.revision}` : "geen goedgekeurde"}</div>
          <div className="text-xs text-muted-foreground">Rechten: {[ov.can_propose && "voorstellen", ov.can_approve && "goedkeuren", ov.can_export && "exporteren"].filter(Boolean).join(", ") || "alleen bekijken"}</div>
        </div>
        <div className="rounded-lg border bg-card p-3 text-sm" data-testid="card-counts">
          <div className="flex justify-between text-xs text-muted-foreground">Werkvoorraad per status<button type="button" onClick={onRefresh} aria-label="Vernieuwen" data-testid="button-refresh"><RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} /></button></div>
          <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
            {QUEUE_KEYS.map(k => <div key={k} className="flex justify-between gap-2"><dt className={`truncate ${(k === "failed" || k === "partial") && ov.queues[k] > 0 ? "text-destructive" : "text-muted-foreground"}`}>{STATUS_NL[k]}</dt><dd className="font-mono" data-testid={`text-queue-${k}`}>{ov.queues[k]}</dd></div>)}
          </dl>
          <div className="mt-2 text-[11px] text-muted-foreground">{COUNT_KEYS.map(k => `${COUNT_NL[k]} ${ov.counts[k]}`).join(" · ")}</div>
        </div>
        <div className="rounded-lg border bg-card p-3 text-sm space-y-2" data-testid="card-scheduler">
          <div className="flex items-center gap-2 text-xs text-muted-foreground"><CalendarClock className="h-3.5 w-3.5" />Dagelijkse preview ({sc.timezone})</div>
          <div className="text-xs space-y-0.5">
            <div>Winkel-instelling: {cfg?.schedule_enabled ? `aan, vanaf ${String(cfg.schedule_hour_utc ?? 2).padStart(2, "0")}:00 ${ov.schedule_timezone}` : "uit"}</div>
            <div data-testid="text-scheduler-availability" className={sc.available ? "text-emerald-700" : "text-destructive"}>
              Planner-proces: {sc.available ? (sc.running ? "beschikbaar en actief" : "beschikbaar, niet actief") : `niet beschikbaar${sc.reason ? ` (${REASON_NL[sc.reason] ?? sc.reason})` : ""}`}{sc.disabled ? " · uitgeschakeld" : ""}
            </div>
            {cfg?.schedule_enabled && !sc.available && <div className="text-destructive">Ingeschakeld voor deze winkel, maar er draait geen planner: er komen geen automatische previews.</div>}
            <div className="text-muted-foreground">Laatste poll: {fmtDate(sc.last_poll_at)} · interval {sc.poll_interval_seconds}s</div>
            {sc.last_error && <div className="text-destructive">Plannerfout: {sc.last_error}</div>}
            <div>Laatste run: {lastRun ? <>{fmtDate(lastRun.snap.created_at)} <StatusBadge status={lastRun.snap.status} />{lastRun.data.calculation_id !== undefined && <span className="text-muted-foreground"> → berekening #{lastRun.data.calculation_id}</span>}</> : "nog geen"}</div>
            {lastRun?.data.error && <div className="text-destructive" data-testid="text-run-error">{lastRun.data.error}</div>}
          </div>
          <Button size="sm" variant="outline" disabled={!ov.can_propose || !!busy} onClick={() => void run("run", async () => parseRun(await cmApi.run(scope.shopId)), "Preview-run afgehandeld")} data-testid="button-run-now">
            <Play className="h-3.5 w-3.5 mr-1" />{busy ? "Bezig…" : "Nu draaien (alleen preview)"}
          </Button>
          <p className="text-[11px] text-muted-foreground">Eén run per winkel per UTC-dag; een herhaling geeft de bestaande run terug. Nooit automatische goedkeuring of export.</p>
          {lastError && <ErrorBox error={lastError.error} />}
        </div>
      </div>
    </div>
  );
}
