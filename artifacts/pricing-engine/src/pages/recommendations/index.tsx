import { useState, useCallback } from "react";
import { Link } from "wouter";
import { useApproveRecommendation, useRejectRecommendation, useBulkApproveRecommendations } from "@workspace/api-client-react";
import type { RecommendationListResponse } from "@workspace/api-client-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Search, CheckCircle, XCircle, FileSearch } from "lucide-react";
import SmartFilters, { SmartFilterValues, EMPTY_FILTERS } from "@/components/filters/SmartFilters";
import { getAuthHeaders } from "@/lib/auth";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

const STRATEGIE_LABELS: Record<string, string> = {
  SUBSTITUTION_PORTFOLIO: "Substitutieportfolio",
  COMPETITOR_INDEX: "Concurrentie-index",
  MARGIN_OPTIMIZATION: "Margeoptimalisatie",
  STOCK_CLEARANCE: "Voorraadopruiming",
  BASKET_BUILDER: "Winkelmandbouwer",
  VOLUME_DISCOUNT: "Volumekorting",
  REPEAT_PURCHASE: "Herhalingsaankoop",
  LOW_VELOCITY: "Laag volume",
  PRIVATE_LABEL_PUSH: "Huismerk push",
  PORTFOLIO_MARGIN_OPTIMIZATION: "Portfolio margeopt.",
  TRAFFIC_TO_MARGIN_SWITCH: "Traffic → marge",
};

export default function Prijsadviezen() {
  const [page, setPage] = useState(1);
  const [zoekterm, setZoekterm] = useState("");
  const [status, setStatus] = useState<string>("pending");
  const [geselecteerd, setGeselecteerd] = useState<Set<number>>(new Set());
  const [smartFilters, setSmartFilters] = useState<SmartFilterValues>(EMPTY_FILTERS);

  const handleSmartFilters = useCallback((f: SmartFilterValues) => {
    setSmartFilters(f);
    setPage(1);
    setGeselecteerd(new Set());
  }, []);

  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  const { data, isLoading } = useQuery<RecommendationListResponse>({
    queryKey: ["/api/recommendations", page, zoekterm, status, filterQs],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: "50" });
      if (zoekterm) params.set("search", zoekterm);
      if (status !== "all") params.set("approval_status", status);
      const qs = [params.toString(), filterQs].filter(Boolean).join("&");
      const res = await fetch(`${BASE}/api/recommendations?${qs}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Kon prijsadviezen niet laden");
      return res.json();
    },
  });

  const queryClient = useQueryClient();
  const { toast } = useToast();

  const goedkeurenMut = useApproveRecommendation();
  const afwijzenMut = useRejectRecommendation();
  const bulkGoedkeurenMut = useBulkApproveRecommendations();

  const handleGoedkeuren = async (id: number) => {
    try {
      await goedkeurenMut.mutateAsync({ id });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      toast({ title: "Advies goedgekeurd" });
    } catch {
      toast({ title: "Fout bij goedkeuren", variant: "destructive" });
    }
  };

  const handleAfwijzen = async (id: number) => {
    try {
      await afwijzenMut.mutateAsync({ id, data: { reason: "Handmatig afgewezen" } });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      toast({ title: "Advies afgewezen" });
    } catch {
      toast({ title: "Fout bij afwijzen", variant: "destructive" });
    }
  };

  const handleBulkGoedkeuren = async () => {
    if (geselecteerd.size === 0) return;
    try {
      await bulkGoedkeurenMut.mutateAsync({ data: { ids: Array.from(geselecteerd) } });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      setGeselecteerd(new Set());
      toast({ title: `${geselecteerd.size} adviezen goedgekeurd` });
    } catch {
      toast({ title: "Fout bij bulk goedkeuren", variant: "destructive" });
    }
  };

  const toggleAlles = () => {
    if (!data?.items) return;
    if (geselecteerd.size === data.items.length) {
      setGeselecteerd(new Set());
    } else {
      setGeselecteerd(new Set(data.items.map(i => i.id)));
    }
  };

  const toggleSelectie = (id: number) => {
    const next = new Set(geselecteerd);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setGeselecteerd(next);
  };

  const formatBedrag = (val: number | null | undefined) =>
    val != null ? new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(val) : '-';

  const formatPct = (val: number | null | undefined) =>
    val != null ? `${(val * 100).toFixed(1)}%` : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Prijsadviezen</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleBulkGoedkeuren}
            disabled={geselecteerd.size === 0 || bulkGoedkeurenMut.isPending}>
            <CheckCircle className="mr-2 h-4 w-4" /> Alles goedkeuren ({geselecteerd.size})
          </Button>
        </div>
      </div>

      <GlobalFilterBar />

      <div className="flex items-center gap-4 bg-card p-3 border rounded-md">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Zoek op SKU of productnaam..."
            className="pl-9 bg-background"
            value={zoekterm}
            onChange={e => setZoekterm(e.target.value)}
          />
        </div>
        <div className="w-48">
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="bg-background">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle statussen</SelectItem>
              <SelectItem value="pending">In behandeling</SelectItem>
              <SelectItem value="approved">Goedgekeurd</SelectItem>
              <SelectItem value="rejected">Afgewezen</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <SmartFilters onChange={handleSmartFilters} />

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">
                <Checkbox
                  checked={data?.items?.length ? geselecteerd.size === data.items.length : false}
                  onCheckedChange={toggleAlles}
                />
              </TableHead>
              <TableHead>SKU</TableHead>
              <TableHead>EAN</TableHead>
              <TableHead>OEM</TableHead>
              <TableHead>Product</TableHead>
              <TableHead>Strategie</TableHead>
              <TableHead className="text-right">Huidige prijs</TableHead>
              <TableHead className="text-right">Geadviseerde prijs</TableHead>
              <TableHead className="text-right">Wijziging</TableHead>
              <TableHead className="text-right">Margeverbetering</TableHead>
              <TableHead className="text-center">Betr.</TableHead>
              <TableHead className="text-center">Veiligheid</TableHead>
              <TableHead className="text-right">Acties</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 13 }).map((__, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : data?.items?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={13} className="h-32 text-center text-muted-foreground">
                  Geen adviezen gevonden.
                </TableCell>
              </TableRow>
            ) : data?.items?.map((rec) => (
              <TableRow key={rec.id} className="group cursor-pointer hover:bg-muted/50">
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={geselecteerd.has(rec.id)}
                    onCheckedChange={() => toggleSelectie(rec.id)}
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">{rec.sku_id}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{rec.ean || "—"}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{rec.oem_code || "—"}</TableCell>
                <TableCell className="font-medium max-w-[180px] truncate" title={rec.product_name}>
                  {rec.product_name}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-[10px] font-normal">
                    {STRATEGIE_LABELS[rec.strategy_type || ""] || rec.strategy_type?.replace(/_/g, ' ')}
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">{formatBedrag(rec.current_price)}</TableCell>
                <TableCell className="text-right tabular-nums font-medium text-primary">{formatBedrag(rec.recommended_price)}</TableCell>
                <TableCell className={`text-right tabular-nums ${(rec.recommended_change_pct || 0) > 0 ? 'text-emerald-600' : 'text-destructive'}`}>
                  {formatPct(rec.recommended_change_pct)}
                </TableCell>
                <TableCell className="text-right tabular-nums text-emerald-600">{formatBedrag(rec.expected_margin_uplift)}</TableCell>
                <TableCell className="text-center">
                  <Badge variant={rec.confidence_score && rec.confidence_score > 0.8 ? "secondary" : "outline"}>
                    {formatPct(rec.confidence_score)}
                  </Badge>
                </TableCell>
                <TableCell className="text-center">
                  {rec.safety_status === 'ok' && <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200">OK</Badge>}
                  {rec.safety_status === 'warning' && <Badge variant="outline" className="text-amber-600 border-amber-200 bg-amber-50">WAARSCH.</Badge>}
                  {rec.safety_status === 'blocked' && <Badge variant="destructive">GEBLOKKEERD</Badge>}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                    <Link href={`/prijsadviezen/${rec.id}`}>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
                        <FileSearch className="h-4 w-4" />
                      </Button>
                    </Link>
                    {rec.approval_status === 'pending' && (
                      <>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                          onClick={() => handleGoedkeuren(rec.id)}>
                          <CheckCircle className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={() => handleAfwijzen(rec.id)}>
                          <XCircle className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                    {rec.approval_status !== 'pending' && (
                      <Badge variant="outline" className="uppercase text-[10px] ml-2">
                        {rec.approval_status === 'approved' ? 'Goedgekeurd' : rec.approval_status === 'rejected' ? 'Afgewezen' : rec.approval_status}
                      </Badge>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div>
            {(data.page - 1) * data.page_size + 1}–{Math.min(data.page * data.page_size, data.total)} van {data.total} adviezen
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Vorige</Button>
            <Button variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)}>Volgende</Button>
          </div>
        </div>
      )}
    </div>
  );
}
