import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Search, TrendingUp, Package, Tag, Layers, Euro } from "lucide-react";
import { useShopId } from "@/hooks/use-shop-id";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const GAP_TYPE_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  MERK:        { label: "Ontbrekend Merk",        color: "bg-blue-100 text-blue-700",    icon: Tag },
  PRODUCTTYPE: { label: "Ontbrekend Producttype",  color: "bg-purple-100 text-purple-700", icon: Package },
  PRIJSSEGMENT:{ label: "Ontbrekend Prijssegment", color: "bg-amber-100 text-amber-700",  icon: Layers },
  OEM_KANS:    { label: "OEM/Huismerk Kans",       color: "bg-emerald-100 text-emerald-700", icon: TrendingUp },
};

export default function CompetitionAssortmentGap() {
  const shopId = useShopId();
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [gapTypeFilter, setGapTypeFilter] = useState("all");
  const [zoekterm, setZoekterm] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["competition-assortment-gap", categoryFilter, gapTypeFilter, shopId, fp],
    queryFn: () => {
      const p = new URLSearchParams({ page_size: "200" });
      if (categoryFilter !== "all") p.set("category", categoryFilter);
      if (gapTypeFilter !== "all") p.set("gap_type", gapTypeFilter);
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      let url = `/api/competition/assortment-gap?${p}`;
      if (fp !== "") url += url.includes("?") ? `&${fp}` : `?${fp}`;
      return apiFetch(url);
    },
  });

  const items = (data?.items || []).filter((g: any) =>
    !zoekterm
      || g.gap_value?.toLowerCase().includes(zoekterm.toLowerCase())
      || g.competitor_name?.toLowerCase().includes(zoekterm.toLowerCase())
      || g.category?.toLowerCase().includes(zoekterm.toLowerCase())
  );

  const allCategories = Array.from(new Set((data?.items || []).map((g: any) => g.category))) as string[];

  // Groepeer per categorie en gap-type
  const grouped: Record<string, Record<string, any[]>> = {};
  for (const item of items) {
    grouped[item.category] = grouped[item.category] || {};
    grouped[item.category][item.gap_type] = grouped[item.category][item.gap_type] || [];
    grouped[item.category][item.gap_type].push(item);
  }

  // Totaal potentieel revenue
  const totalRevenue = items.reduce((sum: number, g: any) => sum + (g.potential_revenue_eur || 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Assortiment Gap Analyse</h1>
        <p className="text-muted-foreground mt-1">Ontbrekende merken, producttypen, prijssegmenten en OEM/huismerk-kansen per categorie.</p>
      </div>

      <GlobalFilterBar />

      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Totale gaten</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{data?.total ?? 0}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Revenue potentieel</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">€{(totalRevenue / 1000).toFixed(0)}k</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Categorieën</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{allCategories.length}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Hoge kans (≥70)</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-amber-600">{items.filter((g: any) => (g.opportunity_score || 0) >= 70).length}</div></CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Zoek merk, type of categorie..." className="pl-9" value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
        </div>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-52"><SelectValue placeholder="Alle categorieën" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle categorieën</SelectItem>
            {allCategories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={gapTypeFilter} onValueChange={setGapTypeFilter}>
          <SelectTrigger className="w-52"><SelectValue placeholder="Alle gaptype" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle typen</SelectItem>
            {Object.entries(GAP_TYPE_CONFIG).map(([k, v]) => (
              <SelectItem key={k} value={k}>{v.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-48" />)}</div>
      ) : Object.keys(grouped).length === 0 ? (
        <Card><CardContent className="p-12 text-center text-muted-foreground">Geen assortimentsgaten beschikbaar. Draai de backfill of analyseer met de engine.</CardContent></Card>
      ) : (
        Object.entries(grouped).map(([cat, gapTypes]) => (
          <Card key={cat}>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{cat}</CardTitle>
              <CardDescription>
                {Object.values(gapTypes).flat().length} gaten · 
                €{(Object.values(gapTypes).flat().reduce((s: number, g: any) => s + (g.potential_revenue_eur || 0), 0) / 1000).toFixed(0)}k potentieel
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {Object.entries(gapTypes).map(([gtype, gaps]) => {
                const config = GAP_TYPE_CONFIG[gtype] || { label: gtype, color: "bg-slate-100 text-slate-700", icon: Package };
                const Icon = config.icon;
                return (
                  <div key={gtype}>
                    <div className="flex items-center gap-2 mb-2">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${config.color}`}>{config.label}</span>
                      <span className="text-xs text-muted-foreground">({gaps.length})</span>
                    </div>
                    <div className="space-y-2 pl-6">
                      {(gaps as any[]).sort((a, b) => (b.opportunity_score || 0) - (a.opportunity_score || 0)).map((gap: any) => (
                        <div key={gap.id} className="flex items-center gap-4 text-sm">
                          <span className="font-medium w-40 shrink-0 truncate">{gap.gap_value}</span>
                          <div className="flex items-center gap-2 flex-1">
                            <Progress value={gap.opportunity_score || 0} className="h-1.5 flex-1 max-w-32" />
                            <span className="text-xs tabular-nums font-medium w-6">{(gap.opportunity_score || 0).toFixed(0)}</span>
                          </div>
                          <span className="text-xs text-muted-foreground w-24 shrink-0">via {gap.competitor_name}</span>
                          {gap.potential_revenue_eur && (
                            <span className="text-xs text-emerald-600 font-medium flex items-center gap-0.5 w-16 shrink-0">
                              <Euro className="h-3 w-3" />{(gap.potential_revenue_eur / 1000).toFixed(1)}k
                            </span>
                          )}
                          <p className="text-xs text-muted-foreground line-clamp-1 flex-1 hidden xl:block">{gap.explanation_nl}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
