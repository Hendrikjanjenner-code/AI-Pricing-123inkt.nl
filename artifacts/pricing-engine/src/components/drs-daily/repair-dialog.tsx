import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Loader2, Search, Link2, PackagePlus, ShieldCheck, AlertTriangle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import {
  drsApi, num, dt, ApiError,
  type Candidate, type UnresolvedItem, type ResolutionAction, type ResolutionPreview,
} from "@/lib/drs-daily-api";

interface Props {
  item: UnresolvedItem | null;
  stageId: string | number;
  shopId: number;
  scopeToken: string | null;
  isCurrent: (t: string | null) => boolean;
  onClose: () => void;
  onRepaired: (row: number, resolutionId: string) => void;
  onFreshUploadRequired: () => void;
}

type Choice = { kind: "link"; sku_id: string } | { kind: "create" } | null;

const Code = ({ v }: { v?: string | null }) => <span className="font-mono">{v && v.length ? v : "—"}</span>;

function CandidateRow({ c, selected, onSelect, testId }: { c: Candidate; selected: boolean; onSelect: () => void; testId: string }) {
  return (
    <button type="button" onClick={onSelect} data-testid={testId}
      className={`w-full text-left rounded-md border p-2 text-xs transition-colors ${selected ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-sm">{c.product_name || "Naam onbekend"}</span>
        {c.import_source && <Badge variant="outline" className="text-[10px]">{c.import_source}</Badge>}
      </div>
      <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-x-3 text-muted-foreground">
        <span>SKU <Code v={c.business_sku} /></span><span>EAN <Code v={c.ean} /></span>
        <span>OEM <Code v={c.oem} /></span><span>ID <Code v={c.sku_id} /></span>
      </div>
      {c.evidence && c.evidence.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-muted-foreground">{c.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
      )}
    </button>
  );
}

export function RepairDialog({ item, stageId, shopId, scopeToken, isCurrent, onClose, onRepaired, onFreshUploadRequired }: Props) {
  const { toast } = useToast();
  const [choice, setChoice] = useState<Choice>(null);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Candidate[] | null>(null);
  const [searchErr, setSearchErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<"search" | "preview" | "confirm" | null>(null);
  const [impact, setImpact] = useState<ResolutionPreview | null>(null);
  const [consent, setConsent] = useState(false);
  const [conflict, setConflict] = useState<string | null>(null);
  const confirmingRef = useRef(false);

  useEffect(() => {
    setChoice(null); setQ(item?.code ?? ""); setResults(null); setSearchErr(null);
    setImpact(null); setConsent(false); setConflict(null);
  }, [item]);

  if (!item) return null;

  const resetImpact = () => { setImpact(null); setConsent(false); setConflict(null); };

  const search = async () => {
    const token = scopeToken;
    setBusy("search"); setSearchErr(null);
    try {
      const r = await drsApi.products(stageId, shopId, q.trim());
      if (!isCurrent(token)) return;
      setResults(r.items);
    } catch (e: any) {
      if (isCurrent(token)) { setResults(null); setSearchErr(e.message); }
    } finally { if (isCurrent(token)) setBusy(null); }
  };

  const requestImpact = async () => {
    if (!choice) return;
    const token = scopeToken;
    if (item.row === null) return;
    const action: ResolutionAction = choice.kind === "link" ? { row: item.row, action: "link", sku_id: choice.sku_id } : { row: item.row, action: "create" };
    setBusy("preview"); resetImpact();
    try {
      const r = await drsApi.resolutionPreview(stageId, shopId, [action]);
      if (!isCurrent(token)) return;
      setImpact(r);
    } catch (e: any) {
      if (!isCurrent(token)) return;
      if (e instanceof ApiError && (e.status === 409 || e.status === 410)) {
        setConflict(e.message);
        if (e.status === 410 || /fresh upload|opnieuw uploaden|verlopen|expired/i.test(e.message)) onFreshUploadRequired();
      } else toast({ title: "Impactpreview mislukt", description: e.message, variant: "destructive" });
    } finally { if (isCurrent(token)) setBusy(null); }
  };

  const confirm = async () => {
    if (!impact || !consent || confirmingRef.current) return;
    confirmingRef.current = true;
    const token = scopeToken;
    setBusy("confirm");
    try {
      const r = await drsApi.resolutionConfirm(stageId, shopId, impact.resolution_id);
      if (!isCurrent(token)) return;
      // Alleen een door de server bevestigd resultaat telt als vastgelegde beslissing.
      if (r?.status !== "confirmed" || r.resolution_id !== impact.resolution_id) {
        setConflict("De server bevestigde deze beslissing niet. Vraag een nieuwe impactpreview.");
        setImpact(null); setConsent(false); return;
      }
      toast({ title: "Beslissing vastgelegd", description: `${num(r.products_created)} product(en) aangemaakt, ${num(r.aliases_added)} koppeling(en). Geen verkoop geschreven; nog niet opgelost tot hervalidatie.` });
      if (item.row !== null) onRepaired(item.row, r.resolution_id);
      onClose();
    } catch (e: any) {
      if (!isCurrent(token)) return;
      if (e instanceof ApiError && (e.status === 409 || e.status === 410 || e.status === 403)) {
        // 409 catalogus gewijzigd/gelijktijdig, 410 voorstel verlopen, 403 voorstel van andere gebruiker: nieuw voorstel nodig.
        setConflict(`${e.message} Er is niets vastgelegd.`); setImpact(null); setConsent(false);
      } else toast({ title: "Vastleggen mislukt", description: e.message, variant: "destructive" });
    } finally { confirmingRef.current = false; if (isCurrent(token)) setBusy(null); }
  };

  const linkId = choice?.kind === "link" ? choice.sku_id : null;
  const candidates = item.candidates ?? [];

  return (
    <Dialog open={!!item} onOpenChange={o => { if (!o && busy !== "confirm") onClose(); }}>
      <DialogContent className="max-w-3xl max-h-[90dvh] overflow-y-auto" data-testid="dialog-repair">
        <DialogHeader>
          <DialogTitle>Rij {item.row} herstellen</DialogTitle>
          <DialogDescription>Kies expliciet een bestaand product of maak het ontbrekende DRS-product aan. Er wordt niets samengevoegd en er wordt geen verkoop geschreven.</DialogDescription>
        </DialogHeader>

        <div className="rounded-md border bg-muted/30 p-3 text-xs space-y-1" data-testid="text-repair-source">
          <div className="text-sm font-medium">{item.product_name || "ProductName ontbreekt"}</div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-3">
            <span>Productcode <Code v={item.code} /></span><span>EAN <Code v={item.ean} /></span><span>OEM <Code v={item.oem} /></span>
          </div>
          <div className="text-red-700">{item.message}</div>
        </div>

        {candidates.length > 0 && (
          <div className="space-y-2">
            <div className="text-sm font-medium">Kandidaten met bronbewijs ({candidates.length})</div>
            {candidates.map((c, i) => (
              <CandidateRow key={c.sku_id} c={c} testId={`option-candidate-${i}`} selected={linkId === c.sku_id}
                onSelect={() => { setChoice({ kind: "link", sku_id: c.sku_id }); resetImpact(); }} />
            ))}
          </div>
        )}

        <div className="space-y-2">
          <div className="text-sm font-medium">Ander bestaand product zoeken</div>
          <div className="flex gap-2">
            <Input data-testid="input-repair-search" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === "Enter") search(); }} placeholder="SKU, EAN, naam" />
            <Button variant="outline" size="sm" onClick={search} disabled={busy !== null} data-testid="button-repair-search">
              {busy === "search" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            </Button>
          </div>
          {searchErr && <div className="text-xs text-red-700">Zoeken mislukt: {searchErr}</div>}
          {results && results.length === 0 && <div className="text-xs text-muted-foreground">Geen producten gevonden in deze winkel.</div>}
          {results?.map((c, i) => (
            <CandidateRow key={c.sku_id} c={c} testId={`option-search-${i}`} selected={linkId === c.sku_id}
              onSelect={() => { setChoice({ kind: "link", sku_id: c.sku_id }); resetImpact(); }} />
          ))}
        </div>

        <button type="button" data-testid="option-create-product" onClick={() => { setChoice({ kind: "create" }); resetImpact(); }}
          className={`w-full text-left rounded-md border p-3 text-xs ${choice?.kind === "create" ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}>
          <div className="flex items-center gap-2 text-sm font-medium"><PackagePlus className="h-4 w-4" />Ontbrekend DRS-product aanmaken</div>
          <div className="text-muted-foreground mt-1">Uitsluitend uit het rapport: productcode <Code v={item.code} /> wordt zakelijke SKU, ProductName wordt naam; EAN <Code v={item.ean} /> en OEM <Code v={item.oem} /> blijven apart. De server controleert duplicaten.</div>
        </button>

        {conflict && (
          <div className="rounded-md border border-red-200 bg-red-50/60 p-3 text-xs text-red-800 flex gap-2" data-testid="text-repair-conflict">
            <AlertTriangle className="h-4 w-4 shrink-0" /><div><div className="font-medium">Geblokkeerd door conflict</div>{conflict}<div className="mt-1 text-muted-foreground">Kies een ander product of los het conflict op in productbeheer.</div></div>
          </div>
        )}

        {impact && (
          <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm space-y-2" data-testid="panel-repair-impact">
            <div className="font-medium flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" />Impact volgens server</div>
            <ul className="text-xs space-y-0.5">
              <li>Producten aangemaakt: <b data-testid="text-impact-created">{num(impact.products_created)}</b></li>
              <li>Koppelingen toegevoegd: <b data-testid="text-impact-aliases">{num(impact.aliases_added)}</b></li>
              <li>Verkoopregels geschreven: <b>{num(impact.sales_written)}</b></li>
              {impact.requires_revalidation && <li>Daarna is een nieuwe validatiepreview nodig.</li>}
              {impact.expires_at && <li className="text-muted-foreground">Voorstel geldig tot {dt(impact.expires_at)}</li>}
            </ul>
            {impact.actions.map(a => (
              <div key={a.row} className="rounded border bg-background p-2 text-xs" data-testid={`text-impact-action-${a.row}`}>
                <div className="font-medium">Rij {a.row}: {a.action === "create" ? "nieuw DRS-product" : "koppelen aan bestaand product"}</div>
                <div className="text-muted-foreground">Bron: SKU <Code v={a.code} /> · EAN <Code v={a.ean} /> · OEM <Code v={a.oem} /> · {a.product_name || "naam ontbreekt"}</div>
                {a.target && <div className="text-muted-foreground">Doel: {a.target.product_name || "naam onbekend"} · SKU <Code v={a.target.business_sku} /> · EAN <Code v={a.target.ean} /> · ID <Code v={a.target.sku_id} /></div>}
                {a.action === "create" && <div className="text-muted-foreground">Nieuwe technische ID <Code v={a.sku_id} /> (door server bepaald)</div>}
              </div>
            ))}
            <label className="flex items-start gap-2 text-xs cursor-pointer">
              <Checkbox data-testid="checkbox-repair-consent" checked={consent} onCheckedChange={v => setConsent(v === true)} className="mt-0.5" />
              Ik bevestig deze beslissing voor deze winkel en bron. Ze wordt gelogd en bij heruploads en PriceShape-sync behouden.
            </label>
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={busy === "confirm"} data-testid="button-repair-cancel">Annuleren</Button>
          {!impact ? (
            <Button onClick={requestImpact} disabled={!choice || busy !== null} data-testid="button-repair-preview">
              {busy === "preview" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Link2 className="mr-2 h-4 w-4" />}Impact bekijken
            </Button>
          ) : (
            <Button onClick={confirm} disabled={!consent || busy !== null} data-testid="button-repair-confirm">
              {busy === "confirm" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}Beslissing vastleggen
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
