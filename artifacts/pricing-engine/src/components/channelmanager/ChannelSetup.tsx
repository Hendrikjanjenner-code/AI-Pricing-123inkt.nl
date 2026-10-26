import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, Circle, FileUp, Pause, Plus, ShieldCheck, Trash2, Unplug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import type { CmScope } from "@/hooks/use-channelmanager";
import { useCmOverview } from "@/hooks/use-channelmanager";
import { useRegistryAction } from "@/hooks/use-channel-registry";
import { cmKeys, errText, fmtDate } from "@/lib/channelmanager/api";
import { feedApi, feedKeys } from "@/lib/feeds/api";
import { mappingErrors, parseMappingCsv, regApi } from "@/lib/channelmanager/registry";
import type { Channel, Mapping, Registry } from "@/lib/channelmanager/registry";
import { FeedProfilesPanel } from "@/components/feeds/FeedProfilesPanel";
import { ConfigPanel } from "./ConfigPanel";
import { ErrorBox, Field, inputCls } from "./common";
import { ChannelStatusPill } from "./ChannelList";

type Shop = { id: number; name: string };

/** Lokale doelscope: verandert nooit de globale winkel. Actueel zolang gemount en de bronscope (gebruiker/winkel) gelijk blijft. */
export function useTargetScope(parent: CmScope, shopId: number): CmScope {
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const { userKey, scopeToken: parentToken, isCurrent: parentIsCurrent } = parent;
  return useMemo(() => {
    const token = `${parentToken}|doel:${shopId}`;
    return { shopId, userKey, scopeToken: token, isCurrent: (t: string | null) => t === token && mounted.current && parentIsCurrent(parentToken) };
  }, [userKey, parentToken, parentIsCurrent, shopId]);
}

function Step({ n, title, done, children, aside }: { n: number; title: string; done: boolean; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="relative rounded-lg border bg-card p-4 md:p-5" data-testid={`step-${n}`}>
      <header className="mb-3 flex flex-wrap items-center gap-3">
        <span className={`flex h-7 w-7 items-center justify-center rounded-full border font-mono text-xs ${done ? "border-emerald-600 bg-emerald-600 text-white" : "border-primary/40 text-primary"}`}>{done ? <CheckCircle2 className="h-4 w-4" /> : n}</span>
        <h3 className="font-semibold">{title}</h3>
        <div className="ml-auto">{aside}</div>
      </header>
      {children}
    </section>
  );
}

export function ChannelSetup({ scope, reg, channel, shops, onOpenTarget }: {
  scope: CmScope; reg: Registry; channel: Channel; shops: Shop[]; onOpenTarget: (shopId: number, tab: "basis" | "regels") => void;
}) {
  const { run, busy } = useRegistryAction(scope);
  const { toast } = useToast();
  const qc = useQueryClient();
  const editable = channel.can_edit;
  const [target, setTarget] = useState<number | null>(channel.target_shop_id);
  const [profile, setProfile] = useState<number | null>(channel.product_profile_id);
  const [rows, setRows] = useState<Mapping[]>(channel.mappings);
  const [confirmed, setConfirmed] = useState(channel.mapping_confirmed);
  const [paste, setPaste] = useState("");
  const [csvErrors, setCsvErrors] = useState<string[]>([]);
  const [showFeeds, setShowFeeds] = useState(false);
  const [limit, setLimit] = useState(200);
  const [preparing, setPreparing] = useState(false);
  const prepRef = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const fileRef = useRef<HTMLInputElement>(null);

  const profilesQ = useQuery({ queryKey: feedKeys.profiles(scope.userKey, scope.shopId), queryFn: ({ signal }) => feedApi.profiles(scope.shopId, signal), retry: 1 });
  const productProfiles = (profilesQ.data ?? []).filter(p => p.purpose === "products");
  const rowErrs = useMemo(() => mappingErrors(rows), [rows]);
  const dirty = target !== channel.target_shop_id || profile !== channel.product_profile_id || confirmed !== channel.mapping_confirmed
    || JSON.stringify(rows) !== JSON.stringify(channel.mappings);
  const savedTarget = channel.target_shop_id;

  const importCsv = (text: string, replace: boolean) => {
    const r = parseMappingCsv(text);
    if (r.errors.length) { setCsvErrors([`Import geweigerd, bestaande koppelingen ongewijzigd. Herstel ${r.errors.length} fout(en):`, ...r.errors]); return false; }
    if (!r.rows.length) { setCsvErrors(["Geen koppelingen gevonden in de invoer."]); return false; }
    setCsvErrors([]);
    setRows(old => replace ? r.rows : [...old, ...r.rows]); setConfirmed(false);
    return true;
  };
  const editRow = (i: number, k: keyof Mapping, v: string) => { setRows(rs => rs.map((r, j) => j === i ? { ...r, [k]: v } : r)); setConfirmed(false); };

  const save = () => run("save", () => regApi.save(scope.shopId, reg.revision, channel.id, { target_shop_id: target, product_profile_id: profile, mappings: rows, mapping_confirmed: confirmed }), "Concept opgeslagen (niet geactiveerd)");
  const prepare = async () => {
    if (prepRef.current || savedTarget === null) return;
    const token = scope.scopeToken;
    const live = () => mounted.current && scope.isCurrent(token);
    prepRef.current = true; setPreparing(true);
    try {
      const snap = await regApi.prepareBasis(scope.shopId, reg.revision, channel.id);
      if (!live()) return;
      void qc.invalidateQueries({ queryKey: cmKeys.shop(scope.userKey, savedTarget) });
      toast({ title: `Kanaalbasis #${snap.id} klaargezet`, description: "Nog niet goedgekeurd. Keur goed in Basisprijzen van de doelwinkel." });
      onOpenTarget(savedTarget, "basis");
    } catch (e) {
      if (live()) toast({ title: "Kanaalbasis maken mislukt", description: errText(e), variant: "destructive" });
    } finally {
      prepRef.current = false;
      if (mounted.current) setPreparing(false);
    }
  };

  const shopName = (id: number | null) => shops.find(s => s.id === id)?.name ?? (id === null ? "geen" : `winkel #${id}`);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="space-y-4 min-w-0">
        <Step n={1} title="Doelwinkel" done={savedTarget !== null}>
          <p className="mb-2 text-sm text-muted-foreground">Naar welke bestaande winkel gaan de prijzen van {channel.name}? Alleen winkels waarvoor je gemachtigd bent.</p>
          {shops.filter(s => s.id !== scope.shopId).length === 0 && <p className="mb-2 rounded-md border border-amber-300 bg-amber-50 p-2.5 text-sm text-amber-900" data-testid="status-no-target">Er is geen andere winkel waarvoor je gemachtigd bent. Standaardkanalen maken geen winkel of rechten aan: laat eerst een winkel voor {channel.name} aanmaken en je toegang geven.</p>}
          <select className={`${inputCls} w-full sm:w-80 font-sans`} disabled={!editable} value={target ?? ""} onChange={e => setTarget(e.target.value ? Number(e.target.value) : null)} data-testid="select-target-shop">
            <option value="">Nog niet gekozen</option>
            {shops.filter(s => s.id !== scope.shopId).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Step>

        <Step n={2} title="Productreferentie (bron)" done={channel.product_profile_id !== null}
          aside={<Button size="sm" variant="ghost" className="text-primary" onClick={() => setShowFeeds(v => !v)} data-testid="button-toggle-feeds">{showFeeds ? "Feeds sluiten" : "Feeds beheren"}</Button>}>
          <p className="mb-2 text-sm text-muted-foreground">Productfeed van de bronwinkel om broncodes te controleren. Dit is een referentie, geen prijsadvies. Er moet een actieve versie zijn.</p>
          {profilesQ.isLoading ? <Skeleton className="h-9 w-80" /> : profilesQ.isError ? <ErrorBox error={profilesQ.error} onRetry={() => profilesQ.refetch()} /> : (
            productProfiles.length === 0
              ? <p className="text-sm text-amber-800">Geen productfeed in deze bronwinkel. Maak er een via Feeds beheren.</p>
              : <select className={`${inputCls} w-full sm:w-80 font-sans`} disabled={!editable} value={profile ?? ""} onChange={e => setProfile(e.target.value ? Number(e.target.value) : null)} data-testid="select-product-profile">
                <option value="">Nog niet gekozen</option>
                {productProfiles.map(p => <option key={p.id} value={p.id}>{p.name}{p.active ? " · actief" : " · niet actief"}</option>)}
              </select>
          )}
          {showFeeds && <div className="mt-4 border-t pt-4"><FeedProfilesPanel scope={scope} purposes={["products"]} title="Productfeeds bronwinkel" intro="Opslaan of uploaden activeert niets; activeer een gevalideerde versie expliciet." /></div>}
        </Step>

        <Step n={3} title="Productkoppeling" done={channel.mapping_confirmed && channel.mappings.length > 0}>
          <p className="mb-3 text-sm text-muted-foreground">Expliciete paren <span className="font-mono">source_productcode;target_productcode</span>. Codes blijven tekst, voorloopnullen blijven behouden.</p>
          {editable && (
            <div className="mb-3 grid gap-2 md:grid-cols-[1fr_auto]">
              <textarea className={`${inputCls} h-24 py-2`} placeholder={"source_productcode;target_productcode\n000123;KB-123"} value={paste} onChange={e => setPaste(e.target.value)} data-testid="textarea-mapping-csv" />
              <div className="flex flex-row gap-2 md:flex-col">
                <Button size="sm" variant="outline" disabled={!paste.trim()} onClick={() => { if (importCsv(paste, false)) setPaste(""); }} data-testid="button-paste-append">Toevoegen</Button>
                <Button size="sm" variant="outline" disabled={!paste.trim()} onClick={() => { if (importCsv(paste, true)) setPaste(""); }}>Vervangen</Button>
                <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} data-testid="button-mapping-file"><FileUp className="mr-1 h-4 w-4" />CSV</Button>
                <input ref={fileRef} type="file" accept=".csv,text/csv,text/plain" className="hidden" onChange={async e => { const f = e.target.files?.[0]; if (f) importCsv(await f.text(), true); e.target.value = ""; }} />
              </div>
            </div>
          )}
          {csvErrors.length > 0 && <ul className="mb-2 space-y-0.5 text-xs text-destructive" data-testid="list-csv-errors">{csvErrors.slice(0, 12).map((e, i) => <li key={i}>{e}</li>)}{csvErrors.length > 12 && <li>en {csvErrors.length - 12} meer</li>}</ul>}
          <div className="max-h-80 overflow-auto rounded-md border">
            <table className="w-full min-w-[420px] text-sm">
              <thead className="sticky top-0 bg-muted/80 text-xs text-muted-foreground"><tr><th className="px-2 py-1.5 text-left font-medium w-10">#</th><th className="px-2 py-1.5 text-left font-medium">Broncode</th><th className="px-2 py-1.5 text-left font-medium">Doelcode</th><th className="w-10" /></tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">Nog geen koppelingen.</td></tr>}
                {rows.slice(0, limit).map((r, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-2 font-mono text-xs text-muted-foreground">{i + 1}</td>
                    <td className="px-1 py-1"><input className={`${inputCls} h-8 w-full`} disabled={!editable} value={r.source_productcode} onChange={e => editRow(i, "source_productcode", e.target.value)} aria-label={`Broncode rij ${i + 1}`} /></td>
                    <td className="px-1 py-1"><input className={`${inputCls} h-8 w-full`} disabled={!editable} value={r.target_productcode} onChange={e => editRow(i, "target_productcode", e.target.value)} aria-label={`Doelcode rij ${i + 1}`} /></td>
                    <td><Button size="icon" variant="ghost" className="h-8 w-8" disabled={!editable} aria-label={`Verwijder rij ${i + 1}`} onClick={() => { setRows(rs => rs.filter((_, j) => j !== i)); setConfirmed(false); }}><Trash2 className="h-3.5 w-3.5" /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > limit && <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground"><span>{limit} van {rows.length} rijen getoond</span><Button size="sm" variant="outline" onClick={() => setLimit(l => l + 500)} data-testid="button-more-rows">500 meer tonen</Button><Button size="sm" variant="ghost" onClick={() => setLimit(rows.length)}>Alles tonen</Button></div>}
          <div className="mt-2 flex flex-wrap items-center gap-3">
            {editable && <Button size="sm" variant="ghost" onClick={() => { setRows(rs => [...rs, { source_productcode: "", target_productcode: "" }]); setConfirmed(false); }} data-testid="button-add-row"><Plus className="mr-1 h-4 w-4" />Rij</Button>}
            <span className="text-xs text-muted-foreground font-mono">{rows.length} rijen</span>
          </div>
          {rowErrs.length > 0 && <ul className="mt-2 space-y-0.5 text-xs text-destructive">{rowErrs.slice(0, 6).map(e => <li key={e}>{e}</li>)}</ul>}
          <label className="mt-3 flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" disabled={!editable || rows.length === 0 || rowErrs.length > 0} checked={confirmed} onChange={e => setConfirmed(e.target.checked)} data-testid="checkbox-mapping-confirmed" />
            <span>Ik heb deze {rows.length} koppelingen gecontroleerd en bevestig ze expliciet.</span>
          </label>
          {editable && (
            <div className="mt-4 flex flex-wrap items-center gap-3 border-t pt-3">
              <Button disabled={!dirty || !!busy || rowErrs.length > 0} onClick={() => void save()} data-testid="button-save-channel">{busy === "save" ? "Opslaan…" : "Concept opslaan"}</Button>
              {dirty && <span className="text-xs text-amber-800">Niet-opgeslagen wijzigingen</span>}
              <span className="text-xs text-muted-foreground">Opslaan zet het kanaal niet actief.</span>
            </div>
          )}
        </Step>

        <Step n={4} title="Prijsregels doelwinkel" done={false}>
          {savedTarget === null
            ? <p className="text-sm text-muted-foreground">Kies en bewaar eerst een doelwinkel.</p>
            : <TargetRules key={savedTarget} parent={scope} shopId={savedTarget} shops={shops} />}
        </Step>
      </div>

      <aside className="space-y-4 lg:sticky lg:top-4 self-start">
        <div className="rounded-lg border bg-card p-4 space-y-3" data-testid="panel-channel-state">
          <div className="flex items-center justify-between gap-2"><span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Status</span><ChannelStatusPill status={channel.status} /></div>
          <dl className="space-y-1 text-sm">
            <Row k="Doelwinkel" v={shopName(savedTarget)} />
            <Row k="Gekoppeld" v={channel.mapped_products !== null ? `${channel.mapped_products} producten` : "Nog niet gekoppeld"} />
            <Row k="Gevalideerd" v={channel.validated_at ? fmtDate(channel.validated_at) : "nog niet"} />
            <Row k="Laatste succes" v={channel.last_success_at ? fmtDate(channel.last_success_at) : "nog geen"} />
          </dl>
          <div className="flex items-start gap-2 rounded-md bg-muted/60 p-2.5 text-xs"><Unplug className="h-4 w-4 shrink-0 text-muted-foreground" /><span>Externe verbinding: <strong>{channel.external_connected ? "gemeld door server" : "niet verbonden"}</strong>. Activeren geldt alleen intern; er gaat niets live naar {channel.domain}.</span></div>
          {channel.validation_errors.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs" data-testid="list-validation-errors">
              <div className="mb-1 flex items-center gap-1 font-medium text-destructive"><AlertTriangle className="h-3.5 w-3.5" />Nog op te lossen</div>
              <ul className="space-y-0.5">{channel.validation_errors.map(e => <li key={e}>{e}</li>)}</ul>
            </div>
          )}
          <Checklist channel={channel} />
          <div className="grid gap-2">
            <Button variant="outline" disabled={!editable || dirty || !!busy} onClick={() => void run("validate", () => regApi.validate(scope.shopId, reg.revision, channel.id), "Validatie uitgevoerd")} data-testid="button-validate">{busy === "validate" ? "Valideren…" : "Valideren"}</Button>
            {channel.status === "active"
              ? <Button variant="outline" disabled={!editable || !!busy} onClick={() => void run("pause", () => regApi.pause(scope.shopId, reg.revision, channel.id), "Kanaal gepauzeerd")} data-testid="button-pause"><Pause className="mr-1 h-4 w-4" />Pauzeren</Button>
              : <Button disabled={!channel.can_activate || channel.status !== "ready" || dirty || !!busy} onClick={() => void run("activate", () => regApi.activate(scope.shopId, reg.revision, channel.id), "Intern geactiveerd")} data-testid="button-activate"><ShieldCheck className="mr-1 h-4 w-4" />Intern activeren</Button>}
            {!channel.can_activate && channel.status !== "active" && <p className="text-[11px] text-muted-foreground">Activeren vereist goedkeurrecht.</p>}
            {dirty && <p className="text-[11px] text-amber-800">Sla eerst op voordat je valideert of activeert.</p>}
          </div>
        </div>
        {channel.status === "active" && savedTarget !== null && (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-2 text-sm" data-testid="panel-prepare-basis">
            <div className="font-medium">Prijsflow</div>
            <p className="text-xs text-muted-foreground">Vereist een goedgekeurde basis in de bronwinkel (beheer via Werkruimte bronwinkel). Zet uit de laatst goedgekeurde bronbasis een kanaalbasis klaar voor {shopName(savedTarget)}, alleen via de bevestigde koppelingen. Wordt nooit automatisch goedgekeurd.</p>
            <Button className="w-full" disabled={!channel.can_edit || preparing} onClick={() => void prepare()} data-testid="button-prepare-basis">{preparing ? "Bezig…" : "Maak kanaalbasis"}</Button>
            <Button className="w-full" variant="ghost" onClick={() => onOpenTarget(savedTarget, "basis")}>Doelwerkruimte openen <ArrowRight className="ml-1 h-4 w-4" /></Button>
          </div>
        )}
      </aside>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between gap-3"><dt className="text-muted-foreground">{k}</dt><dd className="text-right font-medium truncate">{v}</dd></div>;
}

function Checklist({ channel }: { channel: Channel }) {
  const items: [string, boolean][] = [
    ["Doelwinkel gekozen", channel.target_shop_id !== null],
    ["Productfeed gekozen", channel.product_profile_id !== null],
    ["Koppelingen bevestigd", channel.mapping_confirmed && channel.mappings.length > 0],
    ["Validatie geslaagd", channel.status === "ready" || channel.status === "active"],
    ["Intern actief", channel.status === "active"],
  ];
  return <ul className="space-y-1 text-xs">{items.map(([l, ok]) => <li key={l} className={`flex items-center gap-2 ${ok ? "text-emerald-800" : "text-muted-foreground"}`}>{ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Circle className="h-3.5 w-3.5" />}{l}</li>)}</ul>;
}

function TargetRules({ parent, shopId, shops }: { parent: CmScope; shopId: number; shops: Shop[] }) {
  const scope = useTargetScope(parent, shopId);
  const q = useCmOverview(scope);
  if (q.isLoading) return <Skeleton className="h-40" />;
  if (q.isError || !q.data) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">Bestaande prijsregels van de doelwinkel. Wijzigingen gelden voor die winkel; er wordt niets automatisch ingevuld.</p>
      <ConfigPanel scope={scope} overview={q.data} canPropose={q.data.can_propose} shops={shops} />
    </div>
  );
}
