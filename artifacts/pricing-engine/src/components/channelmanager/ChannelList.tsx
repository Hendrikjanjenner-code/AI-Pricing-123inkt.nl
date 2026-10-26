import { useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import { ArrowDown, ArrowUp, Check, Eye, EyeOff, GripVertical, Link2, ListOrdered, MoreHorizontal, Pause, Plus, RotateCcw, Search, Settings2, SlidersHorizontal, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { fmtDate } from "@/lib/channelmanager/api";
import { CH_STATUS, regApi } from "@/lib/channelmanager/registry";
import type { Channel, ChannelStatus, Registry } from "@/lib/channelmanager/registry";
import type { CmScope } from "@/hooks/use-channelmanager";
import { useRegistryAction } from "@/hooks/use-channel-registry";
import { Field, inputCls } from "./common";

export function ChannelStatusPill({ status }: { status: ChannelStatus }) {
  const s = CH_STATUS[status];
  return <span className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium ${s.cls}`} data-testid={`status-channel-${status}`}>{s.label}</span>;
}

export function ChannelList({ scope, reg, shops, onSetup }: { scope: CmScope; reg: Registry; shops: { id: number; name: string }[]; onSetup: (id: string) => void }) {
  const { run, busy } = useRegistryAction(scope);
  const [tab, setTab] = useState<"mine" | "all">("mine");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<ChannelStatus | "">("");
  const [showFilter, setShowFilter] = useState(false);
  const [order, setOrder] = useState<string[] | null>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const mine = reg.channels.filter(c => !c.hidden);
  const base = tab === "mine" ? mine : reg.channels;
  const reordering = order !== null;
  const byId = useMemo(() => new Map(reg.channels.map(c => [c.id, c])), [reg.channels]);
  const shopName = (id: number | null) => id === null ? null : shops.find(s => s.id === id)?.name ?? `winkel #${id}`;

  const visible = reordering
    ? order.map(id => byId.get(id)).filter((c): c is Channel => !!c)
    : base.filter(c => (!q.trim() || `${c.name} ${c.domain}`.toLowerCase().includes(q.trim().toLowerCase())) && (!status || c.status === status));
  const filtered = !!q.trim() || !!status;

  const reorderable = reg.channels.filter(c => c.status !== "restricted");
  const move = (id: string, delta: number) => setOrder(o => {
    if (!o) return o; const i = o.indexOf(id); const j = i + delta;
    if (i < 0 || j < 0 || j >= o.length) return o;
    const n = [...o]; [n[i], n[j]] = [n[j], n[i]]; return n;
  });
  const onKey = (e: KeyboardEvent, id: string) => {
    if (e.key === "ArrowUp") { e.preventDefault(); move(id, -1); requestAnimationFrame(() => document.getElementById(`ch-row-${id}`)?.focus()); }
    if (e.key === "ArrowDown") { e.preventDefault(); move(id, 1); requestAnimationFrame(() => document.getElementById(`ch-row-${id}`)?.focus()); }
  };
  const saveOrder = async () => {
    if (!order) return;
    if (await run("reorder", () => regApi.reorder(scope.shopId, reg.revision, order), "Volgorde opgeslagen")) setOrder(null);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3 border-b border-border/70">
        <div className="flex gap-1" role="tablist">
          {([["mine", "Mijn kanalen", mine.length], ["all", "Alle kanalen", reg.channels.length]] as const).map(([id, label, n]) => (
            <button key={id} role="tab" aria-selected={tab === id} disabled={reordering} onClick={() => setTab(id)} data-testid={`tab-channels-${id}`}
              className={`-mb-px border-b-2 px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition-colors disabled:opacity-50 ${tab === id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
              {label} <span className="font-mono font-normal">({n})</span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {!reordering ? <>
          <div className="relative w-full sm:w-72">
            <input className="h-10 w-full rounded-md border bg-card pl-3 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-ring" placeholder="Zoek op kanaalnaam of domein" value={q} onChange={e => setQ(e.target.value)} aria-label="Zoek kanaal" data-testid="input-channel-search" />
            <Search className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-muted-foreground" />
          </div>
          <Button variant="outline" size="icon" className={`h-10 w-10 ${showFilter || status ? "border-primary text-primary" : ""}`} onClick={() => setShowFilter(v => !v)} aria-label="Filter op status" aria-expanded={showFilter} data-testid="button-channel-filter"><SlidersHorizontal className="h-4 w-4" /></Button>
          {filtered && <button className="text-sm font-medium text-primary hover:underline" onClick={() => { setQ(""); setStatus(""); }} data-testid="button-clear-filters">Alles wissen</button>}
          <div className="ml-auto flex gap-1">
            {reg.can_edit && <Button variant="ghost" size="sm" className="text-primary" onClick={() => setAdding(true)} data-testid="button-add-channel"><Plus className="mr-1 h-4 w-4" />Kanaal</Button>}
            {reg.can_edit && reorderable.length > 1 && <Button variant="ghost" size="sm" className="text-primary" onClick={() => { setQ(""); setStatus(""); setOrder(reorderable.map(c => c.id)); }} data-testid="button-reorder"><ListOrdered className="mr-1 h-4 w-4" />Volgorde</Button>}
          </div>
        </> : (
          <div className="flex w-full flex-wrap items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
            <span className="flex-1 min-w-[200px]">Sleep rijen, of focus een rij en gebruik pijl omhoog/omlaag. Verborgen kanalen schuiven mee.</span>
            <Button size="sm" variant="ghost" onClick={() => setOrder(null)} data-testid="button-reorder-cancel"><X className="mr-1 h-4 w-4" />Annuleren</Button>
            <Button size="sm" disabled={!!busy} onClick={() => void saveOrder()} data-testid="button-reorder-save"><Check className="mr-1 h-4 w-4" />{busy ? "Opslaan…" : "Volgorde opslaan"}</Button>
          </div>
        )}
      </div>

      {showFilter && !reordering && (
        <div className="flex flex-wrap gap-1.5" data-testid="panel-status-filter">
          {(Object.keys(CH_STATUS) as ChannelStatus[]).map(s => (
            <button key={s} onClick={() => setStatus(status === s ? "" : s)} aria-pressed={status === s}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${status === s ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted"}`} data-testid={`filter-${s}`}>{CH_STATUS[s].label}</button>
          ))}
        </div>
      )}

      {visible.length === 0 ? (
        <div className="rounded-lg border border-dashed bg-card/50 px-6 py-10 text-center" data-testid="empty-channels">
          <p className="font-medium">{filtered ? "Geen kanaal past bij deze zoekopdracht" : tab === "mine" ? "Alle kanalen zijn verborgen" : "Nog geen kanalen"}</p>
          <p className="mt-1 text-sm text-muted-foreground">{filtered ? "Pas de zoekterm of het statusfilter aan." : "Bekijk Alle kanalen om verborgen kanalen te herstellen."}</p>
        </div>
      ) : (
        <ul className="space-y-2" data-testid="list-channels">
          {visible.map((c, idx) => {
            const restricted = c.status === "restricted";
            return (
              <li key={c.id} id={`ch-row-${c.id}`} tabIndex={reordering ? 0 : -1}
                draggable={reordering} onDragStart={() => setDrag(c.id)} onDragEnd={() => setDrag(null)}
                onDragOver={e => { if (!reordering || drag === null || drag === c.id) return; e.preventDefault(); setOrder(o => { if (!o) return o; const n = o.filter(x => x !== drag); n.splice(n.indexOf(c.id) + (o.indexOf(drag) < o.indexOf(c.id) ? 1 : 0), 0, drag); return n; }); }}
                onKeyDown={e => reordering && onKey(e, c.id)} aria-label={reordering ? `${c.name}, positie ${idx + 1}` : undefined}
                className={`group grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 rounded-md border bg-card px-4 py-2.5 shadow-[0_1px_0_hsl(var(--border))] transition-[transform,opacity] md:grid-cols-[minmax(0,1.6fr)_10rem_11rem_10rem_auto] focus:outline-none focus:ring-2 focus:ring-ring ${c.hidden ? "opacity-60" : ""} ${drag === c.id ? "opacity-40" : ""} ${reordering ? "cursor-grab" : ""}`}
                data-testid={`row-channel-${c.id}`}>
                <div className="flex min-w-0 items-center gap-2">
                  {reordering && <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground" />}
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{c.name}</div>
                    <div className="truncate text-[11px] text-muted-foreground font-mono">{c.domain}{c.target_shop_id !== null && <> → {shopName(c.target_shop_id)}</>}{c.hidden && " · verborgen"}</div>
                  </div>
                </div>
                <div className="col-start-2 row-start-1 md:col-auto md:row-auto"><ChannelStatusPill status={c.status} /></div>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground" title="Laatste succesvolle import of export">
                  <RotateCcw className="h-3.5 w-3.5 shrink-0" />{c.last_success_at ? fmtDate(c.last_success_at) : "Nog geen import/export"}
                </div>
                <div className="flex items-center gap-1.5 text-xs">
                  <Link2 className="h-3.5 w-3.5 shrink-0 text-primary" />
                  {c.mapped_products !== null ? <span className="text-primary">{c.mapped_products} gekoppeld</span> : <span className="text-muted-foreground">Nog niet gekoppeld</span>}
                </div>
                <div className="col-start-2 row-start-2 justify-self-end md:col-auto md:row-auto">
                  {reordering ? (
                    <div className="flex gap-0.5">
                      <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={`${c.name} omhoog`} disabled={idx === 0} onClick={() => move(c.id, -1)}><ArrowUp className="h-4 w-4" /></Button>
                      <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={`${c.name} omlaag`} disabled={idx === visible.length - 1} onClick={() => move(c.id, 1)}><ArrowDown className="h-4 w-4" /></Button>
                    </div>
                  ) : (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="icon" variant="ghost" className="h-8 w-8 text-primary" aria-label={`Acties voor ${c.name}`} disabled={restricted} data-testid={`menu-channel-${c.id}`}><MoreHorizontal className="h-4 w-4" /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => onSetup(c.id)} data-testid={`action-setup-${c.id}`}><Settings2 className="mr-2 h-4 w-4" />{c.status === "setup" ? "Instellen" : "Instellingen"}</DropdownMenuItem>
                        {c.status === "active" && <DropdownMenuItem disabled={!c.can_edit || !!busy} onSelect={() => void run("pause", () => regApi.pause(scope.shopId, reg.revision, c.id), `${c.name} gepauzeerd`)}><Pause className="mr-2 h-4 w-4" />Pauzeren</DropdownMenuItem>}
                        <DropdownMenuSeparator />
                        {c.hidden
                          ? <DropdownMenuItem disabled={!c.can_edit || !!busy} onSelect={() => void run("vis", () => regApi.visibility(scope.shopId, reg.revision, c.id, false), `${c.name} hersteld`)} data-testid={`action-restore-${c.id}`}><Eye className="mr-2 h-4 w-4" />Herstellen</DropdownMenuItem>
                          : <DropdownMenuItem disabled={!c.can_edit || !!busy} onSelect={() => void run("vis", () => regApi.visibility(scope.shopId, reg.revision, c.id, true), `${c.name} verborgen en gepauzeerd`)} data-testid={`action-hide-${c.id}`}><EyeOff className="mr-2 h-4 w-4" />Verbergen</DropdownMenuItem>}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">Intern actief betekent: setup gevalideerd en goedgekeurd binnen deze app. Er is geen live verbinding met een webshop; prijzen gaan alleen via de bestaande export.</p>
      {adding && <AddChannelDialog onClose={() => setAdding(false)} busy={!!busy} onAdd={async (n, d) => { if (await run("add", () => regApi.add(scope.shopId, reg.revision, n, d), "Kanaal toegevoegd")) setAdding(false); }} />}
    </div>
  );
}

function AddChannelDialog({ onClose, onAdd, busy }: { onClose: () => void; onAdd: (n: string, d: string) => void; busy: boolean }) {
  const [name, setName] = useState(""); const [domain, setDomain] = useState("");
  const domErr = domain && !/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(domain.trim()) ? "Gebruik een domein zoals voorbeeld.nl" : null;
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Kanaal toevoegen</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Field label="Naam"><input className={inputCls} value={name} onChange={e => setName(e.target.value)} data-testid="input-channel-name" /></Field>
          <Field label="Domein" error={domErr} hint="Uniek per register; dubbele domeinen worden geweigerd."><input className={inputCls} value={domain} onChange={e => setDomain(e.target.value)} data-testid="input-channel-domain" /></Field>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Annuleren</Button>
          <Button disabled={busy || !name.trim() || !domain.trim() || !!domErr} onClick={() => onAdd(name.trim(), domain.trim().toLowerCase())} data-testid="button-add-channel-submit">Toevoegen</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
