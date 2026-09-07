import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Search, ArrowUpDown, TrendingUp, TrendingDown, Minus, Store, Info, ArrowUpRight } from "lucide-react";
import { useShopId } from "@/hooks/use-shop-id";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

async function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  const r = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`HTTP ${r.status} voor ${path}`);
  return r.json();
}

const eur = (v: number | null | undefined) =>
  v == null ? "—" : new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(v);

function TrendIcon({ trend }: { trend: string | null }) {
  if (trend === "up") return <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />;
  if (trend === "down") return <TrendingDown className="h-3.5 w-3.5 text-red-600" />;
  return <Minus className="h-3.5 w-3.5 text-muted-foreground" />;
}

function ScoreCell({ v }: { v: number | null | undefined }) {
  return <span className="tabular-nums">{v == null ? "Niet beschikbaar" : Math.round(v * 100)}</span>;
}

export default function CompetitionCompetitors() {
  const shopId = useShopId();
  const [topN, setTopN] = useState("10");
  const [zoekterm, setZoekterm] = useState("");
  const [posSort, setPosSort] = useState<"position_asc" | "position_desc">("position_asc");
  const [minItems, setMinItems] = useState("10");

  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  const baseParams = () => {
    const p = new URLSearchParams();
    if (shopId !== undefined) p.set("shop_id", String(shopId));
    new URLSearchParams(filterQs).forEach((v, k) => p.set(k, v));
    return p;
  };

  const { data: rankData, isLoading: rankLoading, isError: rankError } = useQuery({
    queryKey: ["competition-rankings-top", shopId, filterQs, topN],
    queryFn: () => {
      const p = baseParams();
      if (topN !== "all") p.set("limit", topN);
      return apiFetch(`/api/competition/rankings?${p}`);
    },
  });

  const { data: posData, isLoading: posLoading, isError: posError } = useQuery({
    queryKey: ["competition-price-position", shopId, filterQs, topN, posSort, minItems],
    queryFn: () => {
      const p = baseParams();
      p.set("sort", posSort);
      p.set("min_items", minItems);
      if (topN !== "all") p.set("limit", topN);
      return apiFetch(`/api/competition/price-position?${p}`);
    },
  });

  const { data: roomData, isLoading: roomLoading, isError: roomError } = useQuery({
    queryKey: ["competition-increase-room", shopId, filterQs],
    queryFn: () => apiFetch(`/api/competition/price-increase-room?${baseParams()}`),
  });

  const rankings = (rankData?.rankings || []).filter((r: any) =>
    !zoekterm || r.competitor_name?.toLowerCase().includes(zoekterm.toLowerCase()));

  const scopeLabel = posData?.as_of_max
    ? `Peildatum t/m ${posData.as_of_max}${posData.as_of_min && posData.as_of_min !== posData.as_of_max ? ` (oudste item: ${posData.as_of_min})` : ""}`
    : null;
  const excludedTotal = Object.values(posData?.excluded_by_reason || {}).reduce(
    (a: number, b: any) => a + Number(b), 0) as number;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Concurrenten</h1>
        <p className="text-muted-foreground mt-1">
          Topconcurrenten en prijspositie binnen de actieve productscope — de eigen shop staat in dezelfde ranglijst.
        </p>
      </div>

      <GlobalFilterBar />

      <div className="flex gap-3 flex-wrap items-center">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Zoek concurrent..." className="pl-9" value={zoekterm} onChange={e => setZoekterm(e.target.value)} data-testid="input-zoek-concurrent" />
        </div>
        <Select value={topN} onValueChange={setTopN}>
          <SelectTrigger className="w-32" data-testid="select-top-n"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="10">Top 10</SelectItem>
            <SelectItem value="20">Top 20</SelectItem>
            <SelectItem value="all">Alle</SelectItem>
          </SelectContent>
        </Select>
        {scopeLabel && <span className="text-xs text-muted-foreground">{scopeLabel}</span>}
      </div>

      {/* ── Topconcurrenten ─────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Belangrijkste concurrenten</CardTitle>
          <CardDescription>
            {rankData?.total != null && (
              <>Toont {rankings.length} van {rankData.total} concurrenten binnen de scope
              {rankData?.score_basis === "hierarchy_nodes" && " — scores berekend voor de geselecteerde hiërarchie"}.</>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rankLoading ? <Skeleton className="h-48" /> : rankError ? (
            <p className="text-sm text-destructive py-6 text-center" data-testid="error-rankings">
              Rankings konden niet worden geladen — probeer het opnieuw.
            </p>
          ) : rankings.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              Geen rankings binnen deze scope. Voer een rankings-run uit of verruim de filters.
            </p>
          ) : (
            <Table data-testid="table-topconcurrenten">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Concurrent</TableHead>
                  <TableHead className="text-right">Belang</TableHead>
                  <TableHead className="text-right">Comp. rel.</TableHead>
                  <TableHead className="text-right">Prijs rel.</TableHead>
                  <TableHead className="text-right">Influence</TableHead>
                  <TableHead className="text-right">Confidence</TableHead>
                  <TableHead>Waarom relevant</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rankings.map((r: any) => (
                  <TableRow key={r.competitor_name} data-testid={`row-rank-${r.competitor_name}`}>
                    <TableCell className="font-medium tabular-nums">
                      <span className="flex items-center gap-1">{r.rank}<TrendIcon trend={r.trend} /></span>
                    </TableCell>
                    <TableCell>
                      <Link href={`/competition/competitors/${encodeURIComponent(r.competitor_name)}`} className="font-medium hover:underline inline-flex items-center gap-1">
                        {r.competitor_name}<ArrowUpRight className="h-3 w-3 text-muted-foreground" />
                      </Link>
                    </TableCell>
                    <TableCell className="text-right font-semibold"><ScoreCell v={r.combined_score} /></TableCell>
                    <TableCell className="text-right"><ScoreCell v={r.competition_relevance_score} /></TableCell>
                    <TableCell className="text-right"><ScoreCell v={r.price_relevance_score} /></TableCell>
                    <TableCell className="text-right"><ScoreCell v={r.influence_score} /></TableCell>
                    <TableCell className="text-right tabular-nums">{r.confidence != null ? `${Math.round(r.confidence * 100)}%` : "—"}</TableCell>
                    <TableCell className="max-w-md text-xs text-muted-foreground">{r.explanation || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Prijspositie per aanbieder ─────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <CardTitle className="text-base">Prijspositie per aanbieder</CardTitle>
              <CardDescription>
                Positie 1 = laagste geldige prijs; gelijke prijzen delen een positie. Vergeleken over{" "}
                {posData?.items_compared ?? 0} van {posData?.items_total ?? 0} producten in de scope
                {posData?.items_without_valid_competitor > 0 && ` (${posData.items_without_valid_competitor} zonder geldige concurrentprijs)`}
                {excludedTotal > 0 && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="inline-flex items-center gap-0.5 ml-1 underline decoration-dotted cursor-help">
                        <Info className="h-3 w-3" />{excludedTotal} waarnemingen uitgesloten
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      {Object.entries(posData?.excluded_by_reason || {}).map(([k, v]: any) => (
                        <div key={k} className="text-xs">{k}: {v}</div>
                      ))}
                    </TooltipContent>
                  </Tooltip>
                )}.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
            <Select value={minItems} onValueChange={setMinItems}>
              <SelectTrigger className="w-44 h-8 text-xs" data-testid="select-min-items"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Alle aanbieders</SelectItem>
                <SelectItem value="10">Min. 10 vergeleken items</SelectItem>
                <SelectItem value="50">Min. 50 vergeleken items</SelectItem>
                <SelectItem value="250">Min. 250 vergeleken items</SelectItem>
              </SelectContent>
            </Select>
            <button
              className="text-xs inline-flex items-center gap-1 border rounded-md px-2.5 py-1.5 hover:bg-muted"
              onClick={() => setPosSort(s => s === "position_asc" ? "position_desc" : "position_asc")}
              data-testid="button-toggle-pos-sort"
            >
              <ArrowUpDown className="h-3.5 w-3.5" />
              {posSort === "position_asc" ? "Beste positie eerst (1→20)" : "Slechtste positie eerst (20→1)"}
            </button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {posLoading ? <Skeleton className="h-48" /> : posError ? (
            <p className="text-sm text-destructive py-6 text-center" data-testid="error-price-position">
              Prijsposities konden niet worden geladen — probeer het opnieuw.
            </p>
          ) : !posData?.providers?.length ? (
            <p className="text-sm text-muted-foreground py-6 text-center">Geen prijsposities beschikbaar binnen deze scope.</p>
          ) : (
            <Table data-testid="table-prijspositie">
              <TableHeader>
                <TableRow>
                  <TableHead>Aanbieder</TableHead>
                  <TableHead className="text-right">Vergeleken items</TableHead>
                  <TableHead className="text-right">Op positie 1</TableHead>
                  <TableHead className="text-right">Mediane positie</TableHead>
                  <TableHead className="text-right">Gem. positie</TableHead>
                  <TableHead className="text-right">Prijsindex (wij/zij)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {posData.providers.map((p: any) => (
                  <TableRow key={p.name} className={p.is_own ? "bg-blue-50/60 dark:bg-blue-950/30" : undefined} data-testid={`row-pos-${p.name}`}>
                    <TableCell className="font-medium">
                      {p.is_own ? (
                        <span className="inline-flex items-center gap-1.5">
                          <Store className="h-3.5 w-3.5 text-blue-600" />{p.name}
                          <Badge variant="outline" className="text-[10px] border-blue-300 text-blue-700 bg-blue-50">Eigen shop</Badge>
                        </span>
                      ) : (
                        <Link href={`/competition/competitors/${encodeURIComponent(p.name)}`} className="hover:underline">{p.name}</Link>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{p.items_compared}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.pos1_count} ({Math.round((p.pos1_share || 0) * 100)}%)
                      {p.pos1_shared_count > 0 && <span className="text-xs text-muted-foreground"> · {p.pos1_shared_count} gedeeld</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{p.median_position ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.avg_position ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.is_own ? "1.00" : (p.avg_price_index?.toFixed(2) ?? "—")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {posData?.item_detail && (
            <div className="rounded-md border p-3" data-testid="item-detail">
              <div className="text-sm font-medium mb-2">
                Prijsranglijst voor {posData.item_detail.product_name}
                <span className="text-xs text-muted-foreground font-normal ml-2">peildatum {posData.item_detail.as_of}</span>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">Positie</TableHead>
                    <TableHead>Aanbieder</TableHead>
                    <TableHead className="text-right">Prijs</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {posData.item_detail.providers.map((pr: any, i: number) => (
                    <TableRow key={`${pr.name}-${i}`} className={pr.is_own ? "bg-blue-50/60 dark:bg-blue-950/30" : undefined}>
                      <TableCell className="tabular-nums font-medium">{pr.position}</TableCell>
                      <TableCell>{pr.is_own ? <span className="inline-flex items-center gap-1.5"><Store className="h-3.5 w-3.5 text-blue-600" />{pr.name}</span> : pr.name}</TableCell>
                      <TableCell className="text-right tabular-nums">{eur(pr.price)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Veilige verhogingsruimte ───────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Veilige verhogingsruimte op positie 1</CardTitle>
          <CardDescription>
            Waar we strikt de goedkoopste zijn: hoeveel kan de prijs omhoog zonder positie 1 te verliezen aan nummer 2
            (voorstel = prijs nr. 2 − {roomData?.safety_margin_pct ?? 1}% veiligheidsmarge, afgerond op centen). Alleen inzicht — er wordt niets automatisch gewijzigd.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {roomLoading ? <Skeleton className="h-32" /> : roomError || !roomData ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Verhogingsruimte kon niet worden geladen — probeer het opnieuw.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                <div className="rounded-md border p-3">
                  <div className="text-xl font-bold tabular-nums" data-testid="stat-pos1">{roomData.items_at_pos1_strict}</div>
                  <div className="text-xs text-muted-foreground">items strikt op positie 1</div>
                </div>
                <div className="rounded-md border p-3">
                  <div className="text-xl font-bold tabular-nums">{roomData.items_pos1_shared}</div>
                  <div className="text-xs text-muted-foreground">gedeelde positie 1 (geen ruimte)</div>
                </div>
                <div className="rounded-md border p-3">
                  <div className="text-xl font-bold tabular-nums" data-testid="stat-room">{roomData.items_with_room}</div>
                  <div className="text-xs text-muted-foreground">items met verhogingsruimte</div>
                </div>
                <div className="rounded-md border p-3">
                  <div className="text-xl font-bold tabular-nums">
                    {roomData.volume_known ? eur(roomData.total_uplift_estimate_30d) : "—"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {roomData.volume_known ? "geschat effect (afzet 30 dgn)" : "totaal onbekend — geen afzetdata"}
                  </div>
                </div>
              </div>
              {roomData.boundary_competitors?.length > 0 && (
                <div className="flex flex-wrap gap-1.5 items-center text-xs text-muted-foreground">
                  Grensconcurrent (nr. 2):
                  {roomData.boundary_competitors.slice(0, 6).map((b: any) => (
                    <Badge key={b.name} variant="secondary" className="text-xs">{b.name} ×{b.count}</Badge>
                  ))}
                </div>
              )}
              {roomData.items?.length > 0 ? (
                <Table data-testid="table-verhogingsruimte">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Eigen prijs</TableHead>
                      <TableHead className="text-right">Prijs nr. 2</TableHead>
                      <TableHead>Nr. 2 concurrent</TableHead>
                      <TableHead className="text-right">Veilig voorstel</TableHead>
                      <TableHead className="text-right">Extra marge/stuk</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {roomData.items.map((i: any) => (
                      <TableRow key={i.sku_id} data-testid={`row-room-${i.sku_id}`}>
                        <TableCell className="max-w-sm truncate font-medium">{i.product_name}</TableCell>
                        <TableCell className="text-right tabular-nums">{eur(i.own_price)}</TableCell>
                        <TableCell className="text-right tabular-nums">{eur(i.pos2_price)}</TableCell>
                        <TableCell className="text-xs">{i.pos2_competitor}</TableCell>
                        <TableCell className="text-right tabular-nums font-medium">
                          {eur(i.proposed_price)}
                          {i.capped_by_max_price && <span className="text-[10px] text-amber-600 ml-1">max</span>}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-emerald-700 font-semibold">+{eur(i.extra_margin_per_unit)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Geen items met veilige verhogingsruimte binnen deze scope.
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
