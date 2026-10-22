import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Copy, Download, Eye, KeyRound, FlaskConical, Pause, Play, Plus, Power, Rocket, Save, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCmAction } from "@/hooks/use-channelmanager";
import type { CmScope } from "@/hooks/use-channelmanager";
import { ErrorBox, Field, inputCls } from "@/components/channelmanager/common";
import { fmtDate } from "@/lib/channelmanager/api";
import { PURPOSE_NL, feedApi, feedKeys } from "@/lib/feeds/api";
import type { FeedConfig, FeedProfile, FeedPurpose, FeedVersion } from "@/lib/feeds/api";

const MAPPING_KEYS: Record<FeedPurpose, { key: string; label: string; hint?: string }[]> = {
  cost: [
    { key: "productcode", label: "Productcode" }, { key: "type", label: "Type" }, { key: "gtin", label: "GTIN / EAN" },
    { key: "Stockprice", label: "Stockprice" }, { key: "ABCLev", label: "ABCLev" }, { key: "AB", label: "AB" },
    { key: "123inkt.nl Marktprijs", label: "123inkt.nl Marktprijs" },
  ],
  products: [
    { key: "productcode", label: "Productcode" }, { key: "type", label: "Type" }, { key: "gtin", label: "EAN / GTIN" },
    { key: "price", label: "Prijs (bronwaarde)", hint: "Nooit gebruikt als advies" },
  ],
  advice: [{ key: "productcode", label: "Productcode / extern ID" }, { key: "advice", label: "Nieuw advies" }, { key: "price", label: "Oude prijs (optioneel)" }],
  cost_output: [],
};
const CATEGORY_HINTS = ["Print", "Other"];

function Pill({ tone, children, testid }: { tone: "ok" | "warn" | "bad" | "mute"; children: React.ReactNode; testid?: string }) {
  const c = tone === "ok" ? "bg-emerald-500/10 text-emerald-700 border-emerald-600/30" : tone === "warn" ? "bg-amber-500/10 text-amber-700 border-amber-600/30"
    : tone === "bad" ? "bg-destructive/10 text-destructive border-destructive/30" : "bg-muted text-muted-foreground border-border";
  return <span data-testid={testid} className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium ${c}`}>{children}</span>;
}

export function FeedProfilesPanel({ scope, purposes, title, intro }: { scope: CmScope; purposes: FeedPurpose[]; title: string; intro: string }) {
  const q = useQuery({ queryKey: feedKeys.profiles(scope.userKey, scope.shopId), queryFn: ({ signal }) => feedApi.profiles(scope.shopId, signal), retry: 1 });
  const [creating, setCreating] = useState<FeedPurpose | null>(null);
  const all = q.data ?? [];
  const mine = all.filter(p => purposes.includes(p.purpose));
  return (
    <div className="space-y-4" data-testid="panel-feeds">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h2 className="text-lg font-semibold">{title}</h2><p className="max-w-3xl text-sm text-muted-foreground">{intro}</p></div>
        <div className="flex flex-wrap gap-2">
          {purposes.map(p => <Button key={p} size="sm" variant="outline" onClick={() => setCreating(p)} data-testid={`button-new-feed-${p}`}><Plus className="mr-1 h-3.5 w-3.5" />{PURPOSE_NL[p]}</Button>)}
        </div>
      </div>
      {purposes.includes("cost") && purposes.includes("products") && q.data && <Compare scope={scope} all={q.data} />}
      {creating && <ProfileForm scope={scope} purpose={creating} onDone={() => setCreating(null)} />}
      {q.isLoading ? <div className="grid gap-3 lg:grid-cols-2"><Skeleton className="h-56" /><Skeleton className="h-56" /></div>
        : q.isError ? <ErrorBox error={q.error} onRetry={() => q.refetch()} />
        : (
          <div className="grid gap-4 xl:grid-cols-2">
            {purposes.map(p => {
              const ps = mine.filter(x => x.purpose === p);
              return ps.length ? ps.map(prof => <ProfileCard key={prof.id} scope={scope} profile={prof} all={all} />) : (
                <div key={p} className="rounded-lg border border-dashed p-5 text-sm" data-testid={`status-feed-empty-${p}`}>
                  <div className="font-medium">{PURPOSE_NL[p]}</div>
                  <div className="text-muted-foreground">Niet geconfigureerd. Niets wordt opgehaald of gepubliceerd tot je een koppeling aanmaakt, test en expliciet activeert.</div>
                </div>
              );
            })}
          </div>
        )}
    </div>
  );
}

function ProfileCard({ scope, profile: p, all }: { scope: CmScope; profile: FeedProfile; all: FeedProfile[] }) {
  const { run, busy, lastError } = useCmAction(scope);
  const [editing, setEditing] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [openVersion, setOpenVersion] = useState<number | null>(null);
  const vq = useQuery({ queryKey: feedKeys.versions(scope.userKey, scope.shopId, p.id), queryFn: ({ signal }) => feedApi.versions(scope.shopId, p.id, signal), retry: 1 });
  const versions = vq.data ?? [];
  const isOutput = p.purpose === "cost_output";
  const activeCost = all.filter(x => x.purpose === "cost" && x.active && x.current_version_id !== null);
  const [srcId, setSrcId] = useState<number | "">("");
  const [revealed, setRevealed] = useState<{ token: string; feed_path: string; authentication: string } | null>(null);
  const [confirmRotate, setConfirmRotate] = useState(false);
  const src = activeCost.find(x => x.id === srcId);
  const s = scope.shopId;
  const cfg = p.config;
  const mappingKeys = MAPPING_KEYS[p.purpose];

  return (
    <article className="rounded-lg border bg-card" data-testid={`card-feed-${p.id}`}>
      <header className="flex flex-wrap items-start justify-between gap-2 border-b px-4 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{PURPOSE_NL[p.purpose]} · r{p.revision}</div>
          <div className="font-semibold" data-testid={`text-feed-name-${p.id}`}>{p.name}</div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {p.active ? <Pill tone="ok" testid={`status-feed-active-${p.id}`}>Actief</Pill> : <Pill tone="mute" testid={`status-feed-active-${p.id}`}>Uit</Pill>}
          {p.validated_version_id ? <Pill tone="ok">Gevalideerd v{p.validated_version_id}</Pill> : <Pill tone="warn">Niet gevalideerd</Pill>}
          {isOutput && (p.released_version_id ? <Pill tone="ok">Vrijgegeven v{p.released_version_id}</Pill> : <Pill tone="warn">Niets vrijgegeven</Pill>)}
        </div>
      </header>
      <div className="space-y-3 p-4 text-sm">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <dt className="text-muted-foreground">Bron-URL</dt><dd>{cfg.has_url ? "ingesteld (verborgen)" : "geen, alleen upload"}{cfg.has_bearer_token ? " · token ingesteld" : ""}</dd>
          <dt className="text-muted-foreground">Huidige versie</dt><dd className="font-mono">{p.current_version_id ?? "—"}</dd>
          {p.purpose === "cost" && <><dt className="text-muted-foreground">Modus</dt><dd>{cfg.mode === "reference" ? "Referentie (5-koloms, geen rekenbron)" : "Kostbronnen"}</dd></>}
          {cfg.vat_rate !== undefined && <><dt className="text-muted-foreground">Btw-basis</dt><dd>{cfg.vat_rate}% · {cfg.vat_basis === "exc" ? "excl." : "incl."}</dd></>}
          <dt className="text-muted-foreground">Laatste poging</dt><dd>{fmtDate(p.last_attempt)}</dd>
          <dt className="text-muted-foreground">Laatste succes</dt><dd>{fmtDate(p.last_success)}</dd>
          {mappingKeys.length > 0 && <><dt className="text-muted-foreground">Mapping</dt>
            <dd className="font-mono text-[11px]">{mappingKeys.map(m => cfg.mapping?.[m.key] ? `${m.label}←${cfg.mapping[m.key]}` : null).filter(Boolean).join(" · ") || "geen"}</dd></>}
          {cfg.type_mapping && <><dt className="text-muted-foreground">Type-mapping</dt><dd>{Object.keys(cfg.type_mapping).length} types</dd></>}
        </dl>
        {p.last_error && <div className="rounded border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive" data-testid={`text-feed-error-${p.id}`}>Laatste fout: {p.last_error}</div>}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setEditing(e => !e)} data-testid={`button-edit-feed-${p.id}`}>{editing ? "Sluiten" : "Instellingen"}</Button>
          {!isOutput && <Button size="sm" variant="outline" disabled={!cfg.has_url || !!busy} onClick={() => void run("test", () => feedApi.test(s, p.id), "Bron getest (staging, niet geactiveerd)")} data-testid={`button-test-feed-${p.id}`}>
            <FlaskConical className="mr-1 h-3.5 w-3.5" />URL testen</Button>}
          {p.active && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void run("pause", () => feedApi.pause(s, p.id), "Koppeling gepauzeerd")} data-testid={`button-pause-feed-${p.id}`}>
            <Pause className="mr-1 h-3.5 w-3.5" />Pauzeren</Button>}
        </div>
        {editing && <ProfileForm scope={scope} purpose={p.purpose} profile={p} onDone={() => setEditing(false)} />}

        {!isOutput && (
          <div className="flex flex-wrap items-center gap-2 rounded-md bg-muted/40 p-2">
            <input type="file" accept=".csv,text/csv" className="text-xs" onChange={e => setFile(e.target.files?.[0] ?? null)} data-testid={`input-upload-feed-${p.id}`} />
            <Button size="sm" disabled={!file || !!busy} onClick={() => file && void run("upload", () => feedApi.upload(s, p.id, file), "Bestand gevalideerd in staging").then(() => setFile(null))} data-testid={`button-upload-feed-${p.id}`}>
              <Upload className="mr-1 h-3.5 w-3.5" />{busy === "upload" ? "Valideren…" : "Uploaden en valideren"}</Button>
            <span className="text-[11px] text-muted-foreground">Alleen staging. Activeren is een aparte stap.</span>
          </div>
        )}
        {isOutput && (
          <div className="space-y-2 rounded-md bg-muted/40 p-2">
            <div className="flex flex-wrap items-center gap-2">
              <select className={inputCls} value={srcId} onChange={e => setSrcId(e.target.value ? Number(e.target.value) : "")} data-testid={`select-build-source-${p.id}`}>
                <option value="">Kies actieve kostbron</option>
                {activeCost.map(c => <option key={c.id} value={c.id}>{c.name} (v{c.current_version_id})</option>)}
              </select>
              <Button size="sm" disabled={!src || !!busy} onClick={() => src && void run("build", () => feedApi.build(s, p.id, { source_profile_id: src.id, source_version_id: src.current_version_id as number }), "Costfeed-preview gebouwd")} data-testid={`button-build-feed-${p.id}`}>
                <Play className="mr-1 h-3.5 w-3.5" />Preview bouwen</Button>
              <Button size="sm" variant="outline" disabled={!p.active || !p.released_version_id || !!busy} onClick={() => void run("feed", () => feedApi.downloadFeed(s, p.id))} data-testid={`button-download-feed-${p.id}`}>
                <Download className="mr-1 h-3.5 w-3.5" />Vrijgegeven feed downloaden</Button>
            </div>
            {!activeCost.length && <p className="text-[11px] text-muted-foreground">Er is geen actieve kostbron met huidige versie; bouwen is pas mogelijk na activering.</p>}
            <p className="text-[11px] text-muted-foreground">Feedadres: <span className="font-mono">{feedApi.feedPath(s, p.id)}</span>. Toegang met sessie of machinetoken via Authorization-header; nooit anoniem. Of PriceShape dit kan gebruiken is onbevestigd; downloaden is de handmatige route.</p>
            <div className="flex flex-wrap items-center gap-2 border-t pt-2">
              <label className="flex items-center gap-2 text-[11px]"><input type="checkbox" checked={confirmRotate} onChange={e => setConfirmRotate(e.target.checked)} data-testid={`check-rotate-token-${p.id}`} />Een nieuw token maakt het vorige direct ongeldig</label>
              <Button size="sm" variant="outline" disabled={!confirmRotate || !!busy} data-testid={`button-rotate-token-${p.id}`}
                onClick={() => void run("token", () => feedApi.token(s, p.id), "Nieuw machinetoken aangemaakt").then(r => { if (r) { setRevealed(r); setConfirmRotate(false); } })}>
                <KeyRound className="mr-1 h-3.5 w-3.5" />Machinetoken genereren</Button>
            </div>
            {revealed && (
              <div className="space-y-1 rounded border border-amber-500/40 bg-amber-500/5 p-2 text-[11px]" data-testid={`panel-token-${p.id}`}>
                <div className="font-medium text-amber-800">Eenmalig getoond. Kopieer nu; het wordt niet opnieuw weergegeven.</div>
                <div className="flex items-center gap-2"><code className="break-all rounded bg-background px-1.5 py-0.5" data-testid={`text-token-${p.id}`}>{revealed.token}</code>
                  <Button size="icon" variant="ghost" className="h-6 w-6" aria-label="Kopieren" onClick={() => void navigator.clipboard?.writeText(revealed.token)} data-testid={`button-copy-token-${p.id}`}><Copy className="h-3 w-3" /></Button></div>
                <div>Pad: <span className="font-mono">{revealed.feed_path}</span> · Header: <span className="font-mono">{revealed.authentication}</span></div>
                <Button size="sm" variant="ghost" className="h-6" onClick={() => setRevealed(null)} data-testid={`button-hide-token-${p.id}`}>Verbergen</Button>
              </div>
            )}
          </div>
        )}

        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Versies</div>
          {vq.isLoading ? <Skeleton className="h-16" /> : vq.isError ? <ErrorBox error={vq.error} onRetry={() => vq.refetch()} /> : !versions.length ?
            <p className="text-xs text-muted-foreground" data-testid={`status-versions-empty-${p.id}`}>Nog geen versies. Upload of test een bron.</p> : (
            <div className="max-h-72 overflow-auto rounded border">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-muted"><tr><th className="px-2 py-1 text-left">Versie</th><th className="px-2 py-1 text-left">Status</th><th className="px-2 py-1 text-right">Rijen</th><th className="px-2 py-1 text-left">Rapport</th><th /></tr></thead>
                <tbody>{versions.map(v => <VersionRow key={v.id} v={v} p={p} busy={!!busy}
                  onOpen={() => setOpenVersion(o => o === v.id ? null : v.id)}
                  onActivate={() => void run("activate", () => feedApi.activate(s, p.id, v.id), `Versie ${v.id} geactiveerd`)}
                  onRelease={() => void run("release", () => feedApi.release(s, p.id, v.id), `Versie ${v.id} vrijgegeven`)}
                  onDownload={() => void run("dl", () => feedApi.downloadVersion(s, p.id, v.id))} />)}</tbody>
              </table>
            </div>
          )}
        </div>
        {openVersion !== null && <VersionDetail scope={scope} profileId={p.id} versionId={openVersion} onClose={() => setOpenVersion(null)} />}
        {lastError && <ErrorBox error={lastError.error} />}
      </div>
    </article>
  );
}

function VersionRow({ v, p, busy, onOpen, onActivate, onRelease, onDownload }: {
  v: FeedVersion; p: FeedProfile; busy: boolean; onOpen: () => void; onActivate: () => void; onRelease: () => void; onDownload: () => void;
}) {
  const errs = v.report?.errors?.length ?? 0; const warns = v.report?.warnings?.length ?? 0;
  const isOutput = p.purpose === "cost_output";
  const stale = v.config_revision !== p.revision;
  return (
    <tr className="border-t" data-testid={`row-version-${v.id}`}>
      <td className="px-2 py-1 font-mono">v{v.id}<div className="text-[10px] text-muted-foreground">{fmtDate(v.created_at)} · r{v.config_revision}{stale && " (oude config)"}</div></td>
      <td className="px-2 py-1">{v.status === "valid" ? <Pill tone="ok">Geldig</Pill> : <Pill tone="bad">Ongeldig</Pill>}
        {p.current_version_id === v.id && <span className="ml-1"><Pill tone="ok">Huidig</Pill></span>}</td>
      <td className="px-2 py-1 text-right font-mono">{v.row_count.toLocaleString("nl-NL")}</td>
      <td className="px-2 py-1">{errs} fouten · {warns} waarsch.{v.report?.duplicate_rows ? ` · ${v.report.duplicate_rows} dubbel` : ""}{v.report?.distinct_products !== undefined ? ` · ${v.report.distinct_products} producten` : ""}</td>
      <td className="px-2 py-1"><div className="flex justify-end gap-1">
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onOpen} aria-label="Bekijken" data-testid={`button-view-version-${v.id}`}><Eye className="h-3.5 w-3.5" /></Button>
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onDownload} disabled={busy} aria-label="Downloaden" data-testid={`button-download-version-${v.id}`}><Download className="h-3.5 w-3.5" /></Button>
        <Button size="sm" variant="outline" className="h-7" disabled={busy || v.status !== "valid" || stale || (p.active && p.current_version_id === v.id)} onClick={onActivate} data-testid={`button-activate-version-${v.id}`}><Power className="mr-1 h-3 w-3" />Activeren</Button>
        {isOutput && <Button size="sm" variant="outline" className="h-7" disabled={busy || v.status !== "valid" || stale || !p.active || p.released_version_id === v.id} onClick={onRelease} data-testid={`button-release-version-${v.id}`}><Rocket className="mr-1 h-3 w-3" />Vrijgeven</Button>}
      </div></td>
    </tr>
  );
}

function VersionDetail({ scope, profileId, versionId, onClose }: { scope: CmScope; profileId: number; versionId: number; onClose: () => void }) {
  const q = useQuery({ queryKey: feedKeys.version(scope.userKey, scope.shopId, profileId, versionId), queryFn: ({ signal }) => feedApi.version(scope.shopId, profileId, versionId, signal), retry: 1 });
  if (q.isLoading) return <Skeleton className="h-32" />;
  if (q.isError || !q.data) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const v = q.data; const recs = v.records ?? [];
  const cols = recs.length ? Object.keys(recs[0]) : [];
  const str = (x: unknown) => typeof x === "string" ? x : JSON.stringify(x);
  return (
    <div className="space-y-2 rounded-md border p-3" data-testid={`panel-version-${versionId}`}>
      <div className="flex items-center justify-between text-xs"><span>Versie v{v.id} · sha256 <span className="font-mono">{v.sha256.slice(0, 16)}…</span></span>
        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={onClose} aria-label="Sluiten" data-testid="button-close-version"><X className="h-3.5 w-3.5" /></Button></div>
      {!!v.report?.errors?.length && <ul className="list-disc pl-4 text-xs text-destructive">{v.report.errors.slice(0, 30).map((e, i) => <li key={i}>{str(e)}</li>)}</ul>}
      {!!v.report?.warnings?.length && <ul className="list-disc pl-4 text-xs text-amber-700">{v.report.warnings.slice(0, 30).map((e, i) => <li key={i}>{str(e)}</li>)}</ul>}
      {cols.length > 0 && (
        <div className="max-h-64 overflow-auto rounded border"><table className="w-full text-[11px]">
          <thead className="sticky top-0 bg-muted"><tr>{cols.map(c => <th key={c} className="px-2 py-1 text-left whitespace-nowrap">{c}</th>)}</tr></thead>
          <tbody>{recs.map((r, i) => <tr key={i} className="border-t">{cols.map(c => <td key={c} className="px-2 py-0.5 font-mono whitespace-nowrap">{r[c] === null || r[c] === undefined ? <span className="text-destructive">ontbreekt</span> : str(r[c])}</td>)}</tr>)}</tbody>
        </table></div>
      )}
      <p className="text-[11px] text-muted-foreground">Eerste {recs.length} genormaliseerde regels.</p>
    </div>
  );
}

function ProfileForm({ scope, purpose, profile, onDone }: { scope: CmScope; purpose: FeedPurpose; profile?: FeedProfile; onDone: () => void }) {
  const { run, busy, lastError } = useCmAction(scope);
  const c = profile?.config ?? {};
  const [name, setName] = useState(profile?.name ?? PURPOSE_NL[purpose]);
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [mode, setMode] = useState<"sources" | "reference">(c.mode ?? "sources");
  const [mapping, setMapping] = useState<Record<string, string>>({ ...(c.mapping ?? {}) });
  const [types, setTypes] = useState<[string, string][]>(Object.entries(c.type_mapping ?? {}));
  const [bulk, setBulk] = useState("");
  const [vatRate, setVatRate] = useState(c.vat_rate ?? "");
  const [vatBasis, setVatBasis] = useState<"inc" | "exc">(c.vat_basis ?? "inc");
  const [unit, setUnit] = useState(!!c.unit_confirmed);
  const [complete, setComplete] = useState(!!c.complete_snapshot_confirmed);
  const [minRows, setMinRows] = useState(String(c.minimum_rows ?? 1));
  const [interval, setInterval] = useState(String(c.interval_minutes ?? 60));
  const [custom, setCustom] = useState(c.custom_source ?? "");
  const [showJson, setShowJson] = useState(false);

  const intervalErr = Number(interval) < 5 || Number(interval) > 10080 ? "5 tot 10080 minuten" : null;
  const minErr = Number(minRows) < 1 || Number(minRows) > 200000 ? "1 tot 200000" : null;
  const vatErr = vatRate && !/^\d+(\.\d+)?$/.test(vatRate) ? "Decimaal met punt, bv. 21" : null;
  const keys = MAPPING_KEYS[purpose];
  const needsVat = purpose === "cost" || purpose === "cost_output";

  function build(): FeedConfig {
    const cfg: FeedConfig = {
      minimum_rows: Number(minRows) || 1, interval_minutes: Number(interval) || 60,
      unit_confirmed: unit, complete_snapshot_confirmed: complete,
    };
    const m = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v.trim()).map(([k, v]) => [k, v.trim()]));
    if (keys.length) cfg.mapping = m;
    const tm = Object.fromEntries(types.filter(([k, v]) => k.trim() && v.trim()).map(([k, v]) => [k.trim(), v.trim()]));
    if (Object.keys(tm).length) cfg.type_mapping = tm;
    if (needsVat) { if (vatRate) cfg.vat_rate = vatRate; cfg.vat_basis = vatBasis; }
    if (purpose === "cost") { cfg.mode = mode; if (custom.trim()) cfg.custom_source = custom.trim(); }
    if (url.trim()) cfg.url = url.trim();
    if (token.trim()) cfg.bearer_token = token.trim();
    return cfg;
  }
  function addBulk() {
    const extra = bulk.split(/\r?\n/).map(l => l.split(/[;=\t]/)).filter(x => x[0]?.trim()).map(x => [x[0].trim(), (x[1] ?? "").trim()] as [string, string]);
    setTypes(t => [...t.filter(([k]) => !extra.some(([e]) => e === k)), ...extra]); setBulk("");
  }
  async function save() {
    const config = build();
    const out = await run("save", () => profile
      ? feedApi.update(scope.shopId, profile.id, { name, purpose, config, base_revision: profile.revision })
      : feedApi.create(scope.shopId, { name, purpose, config }), profile ? "Instellingen opgeslagen; koppeling is gedeactiveerd en moet opnieuw gevalideerd" : "Koppeling aangemaakt (uit)");
    if (out) onDone();
  }

  return (
    <div className="space-y-3 rounded-md border bg-background p-3" data-testid={`form-feed-${profile?.id ?? "new"}`}>
      <div className="text-sm font-medium">{profile ? "Instellingen wijzigen" : `Nieuwe ${PURPOSE_NL[purpose].toLowerCase()}`}</div>
      {profile && <p className="text-[11px] text-amber-700">Opslaan deactiveert deze koppeling en vereist hervalidatie en heractivering.</p>}
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Naam"><input className={inputCls} value={name} onChange={e => setName(e.target.value)} data-testid="input-feed-name" /></Field>
        {purpose !== "cost_output" && <Field label="Bron-URL (optioneel)" hint={c.has_url ? "Leeg laten houdt de bestaande URL" : "https; wordt versleuteld bewaard"}>
          <input className={inputCls} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://" data-testid="input-feed-url" /></Field>}
        {purpose !== "cost_output" && <Field label="Bearer-token bron (optioneel)" hint={c.has_bearer_token ? "Ingesteld; leeg laten houdt het bestaande" : "Alleen schrijven; wordt nooit getoond"}>
          <input type="password" className={inputCls} value={token} onChange={e => setToken(e.target.value)} autoComplete="off" data-testid="input-feed-token" /></Field>}
        {purpose === "cost" && <Field label="Modus">
          <select className={inputCls} value={mode} onChange={e => setMode(e.target.value as "sources" | "reference")} data-testid="select-feed-mode">
            <option value="sources">Kostbronnen (Stockprice, ABCLev, AB, marktprijs)</option>
            <option value="reference">Referentie: bestaande 5-koloms costfeed</option>
          </select></Field>}
        {needsVat && <Field label="Btw-tarief (%)" error={vatErr} hint="Expliciet; wordt niet afgeleid"><input className={inputCls} value={vatRate} onChange={e => setVatRate(e.target.value)} placeholder="21" data-testid="input-feed-vat" /></Field>}
        {needsVat && <Field label="Prijzen in bron zijn">
          <select className={inputCls} value={vatBasis} onChange={e => setVatBasis(e.target.value as "inc" | "exc")} data-testid="select-feed-vat-basis"><option value="inc">Inclusief btw</option><option value="exc">Exclusief btw</option></select></Field>}
        <Field label="Minimum rijen" error={minErr}><input className={inputCls} value={minRows} onChange={e => setMinRows(e.target.value.replace(/\D/g, ""))} data-testid="input-feed-min-rows" /></Field>
        {purpose !== "cost_output" && <Field label="Interval (minuten)" error={intervalErr} hint="Alleen na activering"><input className={inputCls} value={interval} onChange={e => setInterval(e.target.value.replace(/\D/g, ""))} data-testid="input-feed-interval" /></Field>}
        {purpose === "cost" && mode === "sources" && <Field label="Eigen vijfde bron (optioneel)" hint="Naam gelijk aan custom source in kostprioriteit">
          <input className={inputCls} value={custom} onChange={e => setCustom(e.target.value)} data-testid="input-feed-custom-source" /></Field>}
      </div>

      {keys.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Kolommapping: veld → kolomnaam in bron-CSV</div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {keys.filter(k => !(purpose === "cost" && mode === "reference" && ["Stockprice", "ABCLev", "AB", "123inkt.nl Marktprijs"].includes(k.key))).map(k => (
              <Field key={k.key} label={k.label} hint={k.hint}>
                <input className={inputCls} value={mapping[k.key] ?? ""} placeholder="kolomnaam" onChange={e => setMapping(m => ({ ...m, [k.key]: e.target.value }))} data-testid={`input-map-${k.key}`} />
              </Field>
            ))}
            {purpose === "cost" && mode === "sources" && custom.trim() && (
              <Field label={`Bron: ${custom.trim()}`}><input className={inputCls} value={mapping[custom.trim()] ?? ""} onChange={e => setMapping(m => ({ ...m, [custom.trim()]: e.target.value }))} data-testid="input-map-custom" /></Field>
            )}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">Lege bronkolommen blijven ontbrekend, nooit nul.</p>
        </div>
      )}

      {(purpose === "cost" || purpose === "products") && (
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Type → categorie ({types.length})</div>
          <datalist id="feed-cats">{CATEGORY_HINTS.map(x => <option key={x} value={x} />)}</datalist>
          <div className="max-h-56 space-y-1 overflow-auto">
            {types.map(([k, v], i) => (
              <div key={i} className="flex gap-2">
                <input className={`${inputCls} flex-1`} value={k} onChange={e => setTypes(t => t.map((r, j) => j === i ? [e.target.value, r[1]] : r))} placeholder="Type" data-testid={`input-type-${i}`} />
                <input className={`${inputCls} flex-1`} list="feed-cats" value={v} onChange={e => setTypes(t => t.map((r, j) => j === i ? [r[0], e.target.value] : r))} placeholder="Print / Other / categorie" data-testid={`input-type-cat-${i}`} />
                <Button size="icon" variant="ghost" className="h-9 w-9" onClick={() => setTypes(t => t.filter((_, j) => j !== i))} aria-label="Verwijderen" data-testid={`button-remove-type-${i}`}><X className="h-3.5 w-3.5" /></Button>
              </div>
            ))}
          </div>
          <div className="mt-2 flex gap-2">
            <textarea className="min-h-[60px] flex-1 rounded-md border bg-background p-2 font-mono text-xs" value={bulk} onChange={e => setBulk(e.target.value)} placeholder={"Plak regels: Type;Categorie\nToner;Print"} data-testid="input-type-bulk" />
            <div className="flex flex-col gap-1">
              <Button size="sm" variant="outline" onClick={addBulk} disabled={!bulk.trim()} data-testid="button-type-bulk">Toevoegen</Button>
              <Button size="sm" variant="ghost" onClick={() => setTypes(t => [...t, ["", ""]])} data-testid="button-type-add">Rij</Button>
            </div>
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">Elk aangetroffen Type moet expliciet gemapt zijn; de validatie meldt ontbrekende types.</p>
        </div>
      )}

      <div className="flex flex-wrap gap-4 text-xs">
        <label className="flex items-center gap-2"><input type="checkbox" checked={unit} onChange={e => setUnit(e.target.checked)} data-testid="check-unit-confirmed" />Eenheden/valuta bevestigd</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={complete} onChange={e => setComplete(e.target.checked)} data-testid="check-complete-confirmed" />Bron levert volledige snapshot</label>
      </div>
      <button type="button" className="text-[11px] text-muted-foreground underline" onClick={() => setShowJson(x => !x)} data-testid="button-toggle-json">{showJson ? "Verberg" : "Toon"} geavanceerd (config-voorbeeld)</button>
      {showJson && <pre className="max-h-48 overflow-auto rounded bg-muted p-2 text-[10px]">{JSON.stringify({ ...build(), bearer_token: token ? "***" : undefined, url: url ? "***" : undefined }, null, 2)}</pre>}
      {lastError && <ErrorBox error={lastError.error} />}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => void save()} disabled={!name.trim() || !!vatErr || !!minErr || (purpose !== "cost_output" && !!intervalErr) || !!busy} data-testid="button-save-feed"><Save className="mr-1 h-3.5 w-3.5" />{busy ? "Opslaan…" : "Opslaan (blijft uit)"}</Button>
        <Button size="sm" variant="ghost" onClick={onDone} data-testid="button-cancel-feed">Annuleren</Button>
      </div>
    </div>
  );
}

function Compare({ scope, all }: { scope: CmScope; all: FeedProfile[] }) {
  const costs = all.filter(p => p.purpose === "cost" && p.active);
  const prods = all.filter(p => p.purpose === "products" && p.active);
  const [c, setC] = useState<number | "">(""); const [pr, setPr] = useState<number | "">("");
  const enabled = c !== "" && pr !== "";
  const q = useQuery({
    queryKey: [...feedKeys.profiles(scope.userKey, scope.shopId), "compare", c, pr],
    queryFn: ({ signal }) => feedApi.compare(scope.shopId, c as number, pr as number, signal), enabled, retry: 1,
  });
  if (!costs.length || !prods.length) return null;
  const d = q.data;
  return (
    <div className="space-y-2 rounded-lg border bg-card p-3 text-sm" data-testid="panel-feed-compare">
      <div className="flex flex-wrap items-end gap-3">
        <div className="font-medium">Kost- versus productreferentie</div>
        <select className={inputCls} value={c} onChange={e => setC(e.target.value ? Number(e.target.value) : "")} data-testid="select-compare-cost"><option value="">Actieve kostbron</option>{costs.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
        <select className={inputCls} value={pr} onChange={e => setPr(e.target.value ? Number(e.target.value) : "")} data-testid="select-compare-products"><option value="">Actieve productreferentie</option>{prods.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
      </div>
      {enabled && (q.isLoading ? <Skeleton className="h-12" /> : q.isError ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : d && (
        <div className="grid gap-2 text-xs sm:grid-cols-2" data-testid="text-compare-result">
          <div>Kostversie v{d.cost_version_id}: {d.cost_rows.toLocaleString("nl-NL")} regels · productversie v{d.products_version_id}: {d.products_rows.toLocaleString("nl-NL")} regels · {d.matched_products.toLocaleString("nl-NL")} producten in beide</div>
          <div><span className={d.cost_only.length ? "text-amber-700" : ""}>{d.cost_only.length} alleen in kostbron</span> · <span className={d.products_only.length ? "text-amber-700" : ""}>{d.products_only.length} alleen in productreferentie</span>
            {(d.cost_only.length > 0 || d.products_only.length > 0) && <details className="mt-1"><summary className="cursor-pointer">Toon productcodes</summary>
              <div className="max-h-32 overflow-auto font-mono">{d.cost_only.slice(0, 500).map(x => <div key={`c${x}`}>kost: {x}</div>)}{d.products_only.slice(0, 500).map(x => <div key={`p${x}`}>product: {x}</div>)}</div></details>}
          </div>
        </div>
      ))}
    </div>
  );
}
