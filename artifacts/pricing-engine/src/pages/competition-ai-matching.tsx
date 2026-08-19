import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { CheckCircle2, XCircle, Search, Link as LinkIcon, Check, X } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useShopId, withShop } from "@/hooks/use-shop-id";

function apiFetch(path: string, opts?: RequestInit) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, ...opts }).then(r => r.json());
}

const MATCH_TYPE_COLORS: Record<string, string> = {
  Exact:                "bg-emerald-100 text-emerald-700 border-emerald-200",
  Sterk:                "bg-blue-100 text-blue-700 border-blue-200",
  Functioneel:          "bg-amber-100 text-amber-700 border-amber-200",
  Categorie_Alternatief:"bg-orange-100 text-orange-700 border-orange-200",
  Geen_Match:           "bg-red-100 text-red-600 border-red-200",
};

const MATCH_TYPE_LABELS: Record<string, string> = {
  Exact:                "Exact",
  Sterk:                "Sterk",
  Functioneel:          "Functioneel",
  Categorie_Alternatief:"Categorie Alt.",
  Geen_Match:           "Geen Match",
};

const STATUS_COLORS: Record<string, string> = {
  PENDING:  "bg-slate-100 text-slate-600",
  APPROVED: "bg-emerald-50 text-emerald-700",
  REJECTED: "bg-red-50 text-red-600",
};

export default function CompetitionAiMatching() {
  const { toast } = useToast();
  const qc = useQueryClient();
  const shopId = useShopId();
  const [matchTypeFilter, setMatchTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [minConfidence, setMinConfidence] = useState(0);
  const [zoekterm, setZoekterm] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["competition-ai-matching", matchTypeFilter, statusFilter, minConfidence, shopId],
    queryFn: () => {
      const p = new URLSearchParams({ page_size: "100", min_confidence: (minConfidence / 100).toString() });
      if (matchTypeFilter !== "all") p.set("match_type", matchTypeFilter);
      if (statusFilter !== "all") p.set("status", statusFilter);
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      return apiFetch(`/api/competition/ai-matching?${p}`);
    },
  });

  const approveMutation = useMutation({
    mutationFn: (id: number) => apiFetch(
      `/api/competition/ai-matching/${id}/approve${shopId !== undefined ? `?shop_id=${shopId}` : ""}`,
      { method: "POST" },
    ),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["competition-ai-matching"] }); toast({ title: "Match goedgekeurd" }); },
  });
  const rejectMutation = useMutation({
    mutationFn: (id: number) => apiFetch(
      `/api/competition/ai-matching/${id}/reject${shopId !== undefined ? `?shop_id=${shopId}` : ""}`,
      { method: "POST" },
    ),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["competition-ai-matching"] }); toast({ title: "Match afgewezen" }); },
  });

  const items = (data?.items || []).filter((m: any) =>
    !zoekterm
      || m.product_name?.toLowerCase().includes(zoekterm.toLowerCase())
      || m.competitor_name?.toLowerCase().includes(zoekterm.toLowerCase())
      || m.own_sku_id?.toLowerCase().includes(zoekterm.toLowerCase())
  );

  const { data: quality } = useQuery({
    queryKey: ["competition-match-quality", shopId],
    queryFn: () => apiFetch(`/api/competition/match-quality${shopId !== undefined ? `?shop_id=${shopId}` : ""}`),
  });

  // Statistieken
  const allItems = data?.items || [];
  const stats = ["Exact", "Sterk", "Functioneel", "Categorie_Alternatief", "Geen_Match"].map(mt => ({
    type: mt,
    count: allItems.filter((i: any) => i.match_type === mt).length,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">AI Matching</h1>
        <p className="text-muted-foreground mt-1">Automatisch herkende productkoppelingen tussen eigen SKU's en concurrent-aanbod — beoordeel en keur goed.</p>
      </div>

      {/* Kwaliteits-KPI's */}
      {quality?.totals && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground">Totaal matches</p>
              <p className="text-xl font-bold tabular-nums">{quality.totals.total}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground">Beoordeeld</p>
              <p className="text-xl font-bold tabular-nums">{quality.totals.review_rate_pct}%</p>
              <p className="text-xs text-muted-foreground">{quality.totals.approved} goedgekeurd · {quality.totals.rejected} afgewezen</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground">Goedkeuringsratio</p>
              <p className="text-xl font-bold tabular-nums">
                {quality.totals.approval_rate_pct != null ? `${quality.totals.approval_rate_pct}%` : "—"}
              </p>
            </CardContent>
          </Card>
          <Card className={quality.suspect_matches?.length ? "border-amber-300" : ""}>
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground">Verdachte matches</p>
              <p className="text-xl font-bold tabular-nums">{quality.suspect_matches?.length ?? 0}</p>
              <p className="text-xs text-muted-foreground">|prijsverschil| &gt; 40%, nog PENDING</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Match-basis: EAN vs feed-koppeling */}
      {quality?.match_basis && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground">EAN-match (geverifieerd)</p>
              <p className="text-xl font-bold tabular-nums">{quality.match_basis.ean_matched}</p>
              <p className="text-xs text-muted-foreground">Exacte matches bevestigd via EAN/GTIN</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground" title={quality.match_basis.note}>
                Feed-koppeling (itemGroupId)
              </p>
              <p className="text-xl font-bold tabular-nums">{quality.match_basis.feed_linked}</p>
              <p className="text-xs text-muted-foreground">
                Standaard voor PriceShape-exports zonder EAN — 0 EAN-matches is dan verwacht, geen kwaliteitsprobleem.
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Match-type statistieken */}
      <div className="flex flex-wrap gap-3">
        {stats.map(s => (
          <Card key={s.type} className="flex-shrink-0 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setMatchTypeFilter(matchTypeFilter === s.type ? "all" : s.type)}>
            <CardContent className="py-3 px-4">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={`text-xs ${MATCH_TYPE_COLORS[s.type] || ""}`}>
                  {MATCH_TYPE_LABELS[s.type]}
                </Badge>
                <span className="font-bold text-lg">{s.count}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap items-end">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Zoek SKU, product of concurrent..." className="pl-9" value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
        </div>
        <Select value={matchTypeFilter} onValueChange={setMatchTypeFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Match-type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle typen</SelectItem>
            <SelectItem value="Exact">Exact</SelectItem>
            <SelectItem value="Sterk">Sterk</SelectItem>
            <SelectItem value="Functioneel">Functioneel</SelectItem>
            <SelectItem value="Categorie_Alternatief">Categorie Alternatief</SelectItem>
            <SelectItem value="Geen_Match">Geen Match</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle statussen</SelectItem>
            <SelectItem value="PENDING">In behandeling</SelectItem>
            <SelectItem value="APPROVED">Goedgekeurd</SelectItem>
            <SelectItem value="REJECTED">Afgewezen</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground whitespace-nowrap">Min. confidence: {minConfidence}%</span>
          <div className="w-32">
            <Slider value={[minConfidence]} onValueChange={v => setMinConfidence(v[0])} min={0} max={90} step={5} />
          </div>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Matchresultaten</CardTitle>
          <CardDescription>{data?.total ?? 0} matches · {items.length} weergegeven</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="border-t">
            <div className="grid grid-cols-12 bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground border-b">
              <div className="col-span-3">SKU / Product</div>
              <div className="col-span-2">Concurrent</div>
              <div className="col-span-2 text-center">Match-type</div>
              <div className="col-span-1 text-center">Confidence</div>
              <div className="col-span-2">Uitleg</div>
              <div className="col-span-1 text-right">Prijs Δ</div>
              <div className="col-span-1 text-center">Status</div>
            </div>
            {isLoading ? (
              <div className="p-8 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12" />)}</div>
            ) : items.length === 0 ? (
              <div className="p-12 text-center text-muted-foreground">Geen matches gevonden. Voer een matching-run uit via de API of draai de backfill.</div>
            ) : (
              <div className="divide-y max-h-[600px] overflow-y-auto">
                {items.map((m: any) => (
                  <div key={m.id} className="grid grid-cols-12 items-start px-4 py-3 text-sm hover:bg-muted/30 transition-colors">
                    <div className="col-span-3">
                      <div className="font-medium truncate pr-2">{m.product_name}</div>
                      <div className="text-xs text-muted-foreground">
                        {m.own_sku_id}
                        {m.ean ? ` · EAN ${m.ean}` : ""}
                        {m.oem_code ? ` · OEM ${m.oem_code}` : ""}
                      </div>
                    </div>
                    <div className="col-span-2">
                      <div className="text-sm truncate">{m.competitor_name}</div>
                      {m.competitor_url && (
                        <a href={m.competitor_url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-primary flex items-center gap-0.5 hover:underline" onClick={e => e.stopPropagation()}>
                          <LinkIcon className="h-2.5 w-2.5" /> Link
                        </a>
                      )}
                    </div>
                    <div className="col-span-2 flex justify-center pt-0.5">
                      <Badge variant="outline" className={`text-xs ${MATCH_TYPE_COLORS[m.match_type] || ""}`}>
                        {MATCH_TYPE_LABELS[m.match_type] || m.match_type}
                      </Badge>
                    </div>
                    <div className="col-span-1 text-center font-mono text-sm font-semibold">
                      {Math.round((m.confidence || 0) * 100)}%
                    </div>
                    <div className="col-span-2 text-xs text-muted-foreground line-clamp-2 pr-2">
                      {m.explanation_nl}
                    </div>
                    <div className={`col-span-1 text-right text-xs font-medium tabular-nums ${
                      m.price_diff_pct > 0 ? "text-emerald-600" : m.price_diff_pct < 0 ? "text-red-600" : "text-muted-foreground"
                    }`}>
                      {m.price_diff_pct != null ? `${m.price_diff_pct > 0 ? "+" : ""}${m.price_diff_pct.toFixed(1)}%` : "—"}
                    </div>
                    <div className="col-span-1 flex items-center justify-center gap-1">
                      {m.status === "PENDING" ? (
                        <>
                          <button onClick={() => approveMutation.mutate(m.id)} className="text-emerald-600 hover:text-emerald-700" title="Goedkeuren">
                            <Check className="h-4 w-4" />
                          </button>
                          <button onClick={() => rejectMutation.mutate(m.id)} className="text-red-500 hover:text-red-600" title="Afwijzen">
                            <X className="h-4 w-4" />
                          </button>
                        </>
                      ) : (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLORS[m.status] || ""}`}>
                          {m.status === "APPROVED" ? "OK" : "Nee"}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
