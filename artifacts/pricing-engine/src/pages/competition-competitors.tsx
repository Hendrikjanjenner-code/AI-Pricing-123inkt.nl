import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Search, Circle, Building2, TrendingDown } from "lucide-react";
import { useShopId } from "@/hooks/use-shop-id";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const TRAFFIC_LIGHT: Record<string, { color: string; label: string }> = {
  green:  { color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "Belangrijk" },
  orange: { color: "text-amber-600 bg-amber-50 border-amber-200",       label: "Monitoren" },
  red:    { color: "text-red-600 bg-red-50 border-red-200",             label: "Laag" },
};

const SEGMENT_COLORS: Record<string, string> = {
  BUDGET:  "bg-blue-100 text-blue-700",
  MIDDEN:  "bg-slate-100 text-slate-700",
  PREMIUM: "bg-purple-100 text-purple-700",
};

export default function CompetitionCompetitors() {
  const shopId = useShopId();
  const [labelFilter, setLabelFilter] = useState("all");
  const [zoekterm, setZoekterm] = useState("");

  // Global Filter Context (taak #263): hiërarchie/merk gaan als queryparams mee.
  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  const { data, isLoading } = useQuery({
    queryKey: ["competition-competitors", labelFilter, shopId, filterQs],
    queryFn: () => {
      const p = new URLSearchParams({ page_size: "100" });
      if (labelFilter !== "all") p.set("relevance_label", labelFilter);
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      new URLSearchParams(filterQs).forEach((v, k) => p.set(k, v));
      return apiFetch(`/api/competition/competitors?${p}`);
    },
  });

  const items = (data?.items || []).filter((c: any) =>
    !zoekterm
      || c.competitor_name?.toLowerCase().includes(zoekterm.toLowerCase())
      || c.domain?.toLowerCase().includes(zoekterm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Concurrenten</h1>
        <p className="text-muted-foreground mt-1">Alle goedgekeurde concurrenten met automatisch opgebouwd profiel en verkeerslicht.</p>
      </div>

      <GlobalFilterBar />

      <div className="flex gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Zoek concurrent of domein..." className="pl-9" value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
        </div>
        <Select value={labelFilter} onValueChange={setLabelFilter}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Alle labels" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle labels</SelectItem>
            <SelectItem value="HIGH">Belangrijk (groen)</SelectItem>
            <SelectItem value="MONITOR">Monitoren (oranje)</SelectItem>
            <SelectItem value="LOW">Laag (rood)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-48" />)}
        </div>
      ) : items.length === 0 ? (
        <Card><CardContent className="p-12 text-center text-muted-foreground">Geen concurrenten gevonden. Voer eerst een discovery-run uit en keur concurrenten goed.</CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map((comp: any) => {
            const tl = TRAFFIC_LIGHT[comp.traffic_light || "orange"] || TRAFFIC_LIGHT.orange;
            return (
              <Link key={comp.competitor_name} href={`/competition/competitors/${encodeURIComponent(comp.competitor_name)}`}>
                <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <CardTitle className="text-base flex items-center gap-2">
                          <Building2 className="h-4 w-4 text-muted-foreground" />
                          {comp.competitor_name}
                        </CardTitle>
                        <CardDescription className="mt-0.5">{comp.domain}</CardDescription>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <Badge variant="outline" className={`text-xs ${tl.color} shrink-0`}>
                          <Circle className="h-2 w-2 mr-1 fill-current" />{tl.label}
                        </Badge>
                        {comp.price_segment && (
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${SEGMENT_COLORS[comp.price_segment] || ""}`}>
                            {comp.price_segment}
                          </span>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="grid grid-cols-3 gap-3 text-center text-sm">
                      <div>
                        <div className="font-bold text-lg">{comp.assortment_size || 0}</div>
                        <div className="text-xs text-muted-foreground">SKU's</div>
                      </div>
                      <div>
                        <div className="font-bold text-lg">{comp.category_breadth || 0}</div>
                        <div className="text-xs text-muted-foreground">Categorieën</div>
                      </div>
                      <div>
                        <div className="font-bold text-lg">{comp.price_change_frequency?.toFixed(1) || "—"}</div>
                        <div className="text-xs text-muted-foreground">Wijz./week</div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-muted-foreground">Functionele overlap</span>
                        <span className="font-medium">{Math.round((comp.functional_overlap_score || 0) * 100)}%</span>
                      </div>
                      <Progress value={(comp.functional_overlap_score || 0) * 100} className="h-1.5" />
                    </div>
                    {comp.top_brands && comp.top_brands.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {comp.top_brands.slice(0, 4).map((b: string) => (
                          <span key={b} className="text-xs bg-muted px-1.5 py-0.5 rounded">{b}</span>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <TrendingDown className="h-3 w-3" />
                      Laatste prijswijziging: {comp.last_price_change_date || "onbekend"}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
