import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { Download, ChevronLeft, ChevronRight, Loader2, RotateCcw, Wrench, CheckCircle2, XCircle } from "lucide-react";
import { drsApi, num, type UnresolvedItem, type UnresolvedPage } from "@/lib/drs-daily-api";
import { RepairDialog } from "./repair-dialog";

const PAGE_SIZE = 50;

interface Props {
  stageId: string | number;
  shopId: number;
  scopeToken: string | null;
  isCurrent: (t: string | null) => boolean;
  totalErrors: number;
  repairedRows: number[];
  onRepaired: (row: number) => void;
  onFreshUploadRequired: () => void;
}

export function UnresolvedPanel({ stageId, shopId, scopeToken, isCurrent, totalErrors, repairedRows, onRepaired, onFreshUploadRequired }: Props) {
  const { toast } = useToast();
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<UnresolvedPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Server-side zoeken over de volledige dataset; debounce en terug naar pagina 1.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setQuery(filter.trim()); setOffset(0); }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [filter]);
  const [exporting, setExporting] = useState(false);
  const [active, setActive] = useState<UnresolvedItem | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => { setOffset(0); setPage(null); setActive(null); setFilter(""); setQuery(""); }, [stageId, scopeToken]);

  useEffect(() => {
    const token = scopeToken;
    let cancelled = false;
    setLoading(true); setError(null);
    drsApi.unresolved(stageId, shopId, offset, PAGE_SIZE, query)
      .then(p => {
        if (cancelled || !isCurrent(token)) return;
        setPage(p);
        if (p.requires_fresh_upload) onFreshUploadRequired();
      })
      .catch((e: any) => {
        if (cancelled || !isCurrent(token)) return;
        setError(e.message);
        if (e.status === 409 || e.status === 410) onFreshUploadRequired();
      })
      .finally(() => { if (!cancelled && isCurrent(token)) setLoading(false); });
    return () => { cancelled = true; };
    // onFreshUploadRequired/isCurrent zijn stabiel of via ouder begrensd
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stageId, shopId, offset, query, reload, scopeToken]);

  const repaired = useMemo(() => new Set(repairedRows), [repairedRows]);
  const items = page?.items ?? [];

  const doExport = async () => {
    const token = scopeToken;
    setExporting(true);
    try { await drsApi.exportUnresolved(stageId, shopId); }
    catch (e: any) {
      if (!isCurrent(token)) return;
      toast({ title: "Export mislukt", description: e.message, variant: "destructive" });
      if (e.status === 409) onFreshUploadRequired();
    } finally { if (isCurrent(token)) setExporting(false); }
  };

  const total = page?.total ?? (query ? 0 : totalErrors);
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="rounded-md border border-red-200 bg-red-50/30 p-3 space-y-3" data-testid="panel-unresolved">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-sm font-medium text-red-800 flex items-center gap-1"><XCircle className="w-4 h-4" />{query ? `${num(total)} van ${num(totalErrors)} blokkerende regels voor "${query}"` : `${num(totalErrors)} blokkerende regel(s)`}</div>
        {repairedRows.length > 0 && <Badge className="bg-primary/10 text-primary border-primary/20" data-testid="badge-repaired-count">{num(repairedRows.length)} beslissing(en) vastgelegd — nog niet gevalideerd</Badge>}
        <div className="ml-auto flex flex-wrap gap-2">
          <Input className="h-8 w-64" placeholder="Zoek code, naam, EAN, OEM, reden" value={filter} onChange={e => setFilter(e.target.value)} data-testid="input-unresolved-filter" />
          <Button size="sm" variant="outline" onClick={doExport} disabled={exporting} data-testid="button-unresolved-export">
            {exporting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Download className="mr-1 h-4 w-4" />}Volledige CSV (alle {num(totalErrors)}, zonder zoekfilter)
          </Button>
        </div>
      </div>

      {error ? (
        <div className="text-xs text-red-800 flex flex-wrap items-center gap-2" data-testid="text-unresolved-error">
          Lijst laden mislukt: {error}
          <Button size="sm" variant="outline" onClick={() => setReload(r => r + 1)} data-testid="button-unresolved-retry"><RotateCcw className="mr-1 h-4 w-4" />Opnieuw</Button>
        </div>
      ) : loading && !page ? (
        <div className="space-y-2">{[0, 1, 2, 3].map(i => <div key={i} className="h-8 rounded bg-muted/60 animate-pulse" />)}</div>
      ) : (
        <div className={`overflow-x-auto rounded-md border bg-background ${loading ? "opacity-60" : ""}`}>
          <Table>
            <TableHeader><TableRow>
              <TableHead className="text-xs">Rij</TableHead><TableHead className="text-xs">Productcode</TableHead>
              <TableHead className="text-xs">ProductName</TableHead><TableHead className="text-xs">EAN</TableHead>
              <TableHead className="text-xs">OEM</TableHead><TableHead className="text-xs">Reden</TableHead>
              <TableHead className="text-xs">Kandidaten</TableHead><TableHead />
            </TableRow></TableHeader>
            <TableBody>
              {items.length === 0 && (
                <TableRow><TableCell colSpan={8} className="text-center text-xs text-muted-foreground py-6">{query ? "Geen blokkerende regels gevonden voor deze zoekterm." : "Geen onopgeloste regels."}</TableCell></TableRow>
              )}
              {items.map((i, idx) => (
                <TableRow key={`${i.row ?? "x"}-${offset + idx}`} data-testid={`row-unresolved-${i.row ?? `x${offset + idx}`}`}>
                  <TableCell className="text-xs tabular-nums">{i.row ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{i.code || "—"}</TableCell>
                  <TableCell className="text-xs max-w-[220px] truncate" title={i.product_name ?? ""}>{i.product_name || "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{i.ean || "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{i.oem || "—"}</TableCell>
                  <TableCell className="text-xs text-red-800 max-w-[260px]">{i.message}</TableCell>
                  <TableCell className="text-xs">{(i.candidates?.length ?? 0) > 0 ? `${i.candidates!.length} kandidaat${i.candidates!.length > 1 ? "en" : ""}` : "geen"}</TableCell>
                  <TableCell className="text-right">
                    {i.kind === "parse" || i.row === null ? (
                      <span className="text-xs text-muted-foreground" data-testid={`status-parse-${offset + idx}`}>Bestand corrigeren</span>
                    ) : repaired.has(i.row) ? (
                      <span className="text-xs text-primary inline-flex items-center gap-1" data-testid={`status-repaired-${i.row}`}><CheckCircle2 className="h-3 w-3" />Vastgelegd, hervalideren</span>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => setActive(i)} data-testid={`button-repair-${i.row}`}><Wrench className="mr-1 h-3 w-3" />Herstel</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span data-testid="text-unresolved-range">{num(from)}–{num(to)} van {num(total)}</span>
        <div className="flex gap-1">
          <Button size="sm" variant="outline" disabled={offset === 0 || loading} onClick={() => setOffset(o => Math.max(0, o - PAGE_SIZE))} data-testid="button-unresolved-prev"><ChevronLeft className="h-4 w-4" /></Button>
          <Button size="sm" variant="outline" disabled={to >= total || loading} onClick={() => setOffset(o => o + PAGE_SIZE)} data-testid="button-unresolved-next"><ChevronRight className="h-4 w-4" /></Button>
        </div>
      </div>

      <RepairDialog item={active} stageId={stageId} shopId={shopId} scopeToken={scopeToken} isCurrent={isCurrent}
        onClose={() => setActive(null)} onRepaired={onRepaired} onFreshUploadRequired={onFreshUploadRequired} />
    </div>
  );
}
