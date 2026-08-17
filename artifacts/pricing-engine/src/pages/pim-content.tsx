import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CheckCircle2, ChevronDown, ChevronUp, Loader2, RefreshCw, XCircle } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface Overview {
  total_skus: number;
  skus_scored: number;
  avg_completeness_pct: number;
  avg_quality_score: number;
  low_completeness_count: number;
  pending_suggestions: number;
  last_run_date: string | null;
  channels: {
    code: string; name: string; min_completeness_pct: number;
    skus_scored: number; skus_ready: number; avg_completeness_pct: number;
  }[];
}

interface CompletenessRow {
  sku_id: string;
  product_name: string;
  brand?: string;
  category?: string;
  channel_code: string | null;
  completeness_pct: number;
  quality_score: number;
  channel_ready: boolean;
  missing_attributes: string[];
  quality_issues: { code: string; bericht: string }[];
}

interface ContentAttribute {
  code: string;
  name: string;
  source_owner: string;
  is_required: boolean;
  value: string | null;
  value_source: string | null;
}

function pctBadge(pct: number) {
  const cls = pct >= 80
    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : pct >= 60
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-red-50 text-red-600 border-red-200";
  return <Badge className={`${cls} text-xs`}>{pct.toFixed(0)}%</Badge>;
}

function sourceBadge(source?: string | null) {
  if (!source) return <span className="text-muted-foreground text-xs">—</span>;
  const kleur: Record<string, string> = {
    DRS: "bg-blue-50 text-blue-700 border-blue-200",
    Leverancier: "bg-purple-50 text-purple-700 border-purple-200",
    Handmatig: "bg-slate-50 text-slate-700 border-slate-200",
    AI: "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
  return <Badge className={`${kleur[source] ?? ""} text-xs`}>{source}</Badge>;
}

function DetailRij({ row }: { row: CompletenessRow }) {
  const [attrs, setAttrs] = useState<ContentAttribute[] | null>(null);
  const [laden, setLaden] = useState(false);

  useEffect(() => {
    let actief = true;
    setLaden(true);
    fetch(`${BASE}/api/pim/products/${encodeURIComponent(row.sku_id)}/content`, {
      headers: getAuthHeaders(), signal: AbortSignal.timeout(30_000),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (actief) setAttrs(d.attributes ?? []); })
      .catch(() => { if (actief) setAttrs([]); })
      .finally(() => { if (actief) setLaden(false); });
    return () => { actief = false; };
  }, [row.sku_id]);

  return (
    <TableRow>
      <TableCell colSpan={7} className="bg-muted/30">
        {laden ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Attributen laden…
          </div>
        ) : (
          <div className="space-y-3 py-2">
            {row.missing_attributes.length > 0 && (
              <div className="text-sm">
                <span className="font-medium">Ontbrekend: </span>
                {row.missing_attributes.map((m) => (
                  <Badge key={m} variant="outline" className="mr-1 text-xs text-red-600 border-red-200">{m}</Badge>
                ))}
              </div>
            )}
            {row.quality_issues.length > 0 && (
              <div className="text-sm">
                <span className="font-medium">Kwaliteitsissues: </span>
                {row.quality_issues.map((q, i) => (
                  <span key={i} className="mr-2 text-amber-700">{q.bericht}</span>
                ))}
              </div>
            )}
            <div className="grid grid-cols-1 gap-1 md:grid-cols-2 lg:grid-cols-3">
              {(attrs ?? []).map((a) => (
                <div key={a.code} className="flex items-center justify-between rounded border bg-background px-2 py-1 text-sm">
                  <span className="truncate">
                    {a.name}
                    {a.is_required && <span className="text-red-500"> *</span>}
                  </span>
                  <span className="ml-2 flex items-center gap-2">
                    <span className="max-w-[160px] truncate text-muted-foreground">{a.value ?? "—"}</span>
                    {sourceBadge(a.value_source ?? (a.value ? a.source_owner : null))}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}

export default function PimContent() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [rows, setRows] = useState<CompletenessRow[]>([]);
  const [totaal, setTotaal] = useState(0);
  const [laden, setLaden] = useState(true);
  const [herberekenen, setHerberekenen] = useState(false);
  const [fout, setFout] = useState<string | null>(null);
  const [kanaal, setKanaal] = useState<string>("overall");
  const [zoek, setZoek] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const laad = useCallback(async () => {
    setLaden(true);
    setFout(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (kanaal !== "overall") params.set("channel", kanaal);
      if (zoek.trim()) params.set("search", zoek.trim());
      const [ovRes, listRes] = await Promise.all([
        fetch(`${BASE}/api/pim/overview`, { headers: getAuthHeaders(), signal: AbortSignal.timeout(60_000) }),
        fetch(`${BASE}/api/pim/completeness?${params}`, { headers: getAuthHeaders(), signal: AbortSignal.timeout(60_000) }),
      ]);
      if (!ovRes.ok || !listRes.ok) throw new Error("Laden mislukt");
      const ov = await ovRes.json();
      const list = await listRes.json();
      setOverview(ov);
      setRows(list.items ?? []);
      setTotaal(list.total ?? 0);
    } catch (e: any) {
      setFout(e?.message ?? "Onbekende fout");
    } finally {
      setLaden(false);
    }
  }, [kanaal, zoek]);

  useEffect(() => { laad(); }, [laad]);

  const herbereken = async () => {
    setHerberekenen(true);
    try {
      const res = await fetch(`${BASE}/api/pim/recompute`, {
        method: "POST", headers: getAuthHeaders(), signal: AbortSignal.timeout(120_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await laad();
    } catch (e: any) {
      setFout(e?.message ?? "Herberekenen mislukt");
    } finally {
      setHerberekenen(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Content Completeness (PIM)</h1>
          <p className="text-sm text-muted-foreground">
            Productcontent-volledigheid en -kwaliteit per SKU en per channel, met bron-eigenaarschap per veld.
          </p>
        </div>
        <Button onClick={herbereken} disabled={herberekenen} variant="outline">
          {herberekenen ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          Herbereken scores
        </Button>
      </div>

      {overview && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Card><CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">Gem. completeness</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-semibold">{overview.avg_completeness_pct.toFixed(1)}%</div></CardContent></Card>
          <Card><CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">Gem. kwaliteit</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-semibold">{overview.avg_quality_score.toFixed(1)}</div></CardContent></Card>
          <Card><CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">Onder 60%</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-semibold">{overview.low_completeness_count}</div></CardContent></Card>
          <Card><CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">Open AI-suggesties</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-semibold">{overview.pending_suggestions}</div></CardContent></Card>
        </div>
      )}

      {overview && overview.channels.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {overview.channels.map((ch) => (
            <Card key={ch.code}>
              <CardHeader className="pb-1">
                <CardTitle className="text-sm font-medium">Channel readiness — {ch.name}</CardTitle>
              </CardHeader>
              <CardContent className="flex items-center justify-between text-sm">
                <span>{ch.skus_ready} van {ch.skus_scored} SKU's ready (drempel {ch.min_completeness_pct}%)</span>
                {pctBadge(ch.avg_completeness_pct)}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center gap-3">
            <Select value={kanaal} onValueChange={setKanaal}>
              <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="overall">Totaal (alle attributen)</SelectItem>
                {(overview?.channels ?? []).map((c) => (
                  <SelectItem key={c.code} value={c.code}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              placeholder="Zoek op SKU of naam…"
              value={zoek}
              onChange={(e) => setZoek(e.target.value)}
              className="w-64"
            />
            <span className="text-sm text-muted-foreground">{totaal} SKU's</span>
          </div>
        </CardHeader>
        <CardContent>
          {fout && <div className="mb-3 text-sm text-red-600">{fout}</div>}
          {laden ? (
            <div className="space-y-2">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
          ) : rows.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              Geen scores gevonden. Klik op “Herbereken scores” om de contentlaag te vullen vanuit de productmaster.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead>Merk</TableHead>
                  <TableHead>Completeness</TableHead>
                  <TableHead>Kwaliteit</TableHead>
                  <TableHead>{kanaal !== "overall" ? "Ready" : "Ontbrekend"}</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <>
                    <TableRow
                      key={r.sku_id}
                      className="cursor-pointer"
                      onClick={() => setOpen(open === r.sku_id ? null : r.sku_id)}
                    >
                      <TableCell className="font-mono text-xs">{r.sku_id}</TableCell>
                      <TableCell className="max-w-[280px] truncate">{r.product_name}</TableCell>
                      <TableCell>{r.brand ?? "—"}</TableCell>
                      <TableCell>{pctBadge(r.completeness_pct)}</TableCell>
                      <TableCell>{r.quality_score.toFixed(0)}</TableCell>
                      <TableCell>
                        {kanaal !== "overall" ? (
                          r.channel_ready
                            ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                            : <XCircle className="h-4 w-4 text-red-500" />
                        ) : (
                          <span className="text-xs text-muted-foreground">{r.missing_attributes.length} veld(en)</span>
                        )}
                      </TableCell>
                      <TableCell>{open === r.sku_id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</TableCell>
                    </TableRow>
                    {open === r.sku_id && <DetailRij key={`${r.sku_id}-detail`} row={r} />}
                  </>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
