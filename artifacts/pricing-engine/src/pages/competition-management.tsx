import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Target, TrendingUp, AlertTriangle, Lightbulb, Eye, ChevronRight } from "lucide-react";
import { Link } from "wouter";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const PRIORITY_COLORS: Record<string, string> = {
  hoog:      "text-red-600 bg-red-50 border-red-200",
  gemiddeld: "text-amber-600 bg-amber-50 border-amber-200",
  laag:      "text-blue-600 bg-blue-50 border-blue-200",
};

export default function CompetitionManagement() {
  const [categoryFilter, setCategoryFilter] = useState("all");

  const { data, isLoading } = useQuery({
    queryKey: ["competition-management", categoryFilter],
    queryFn: () => {
      const p = new URLSearchParams();
      if (categoryFilter !== "all") p.set("category", categoryFilter);
      return apiFetch(`/api/competition/management?${p}`);
    },
  });

  const insights: any[] = data?.insights || [];
  const allCategories = Array.from(new Set(insights.map((i: any) => i.category))) as string[];

  const filtered = categoryFilter === "all" ? insights : insights.filter((i: any) => i.category === categoryFilter);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Management Intelligence</h1>
        <p className="text-muted-foreground mt-1">Per categorie: waarom is X relevant, wat ontbreekt, groeipotentieel en actiepunten voor management.</p>
      </div>

      {/* Samenvatting */}
      {insights.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-1"><Target className="h-4 w-4" /> Categorieën</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-bold">{insights.length}</div></CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-1"><TrendingUp className="h-4 w-4 text-emerald-500" /> Hoogste groeipotentieel</CardTitle></CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{insights[0]?.growth_potential?.toFixed(0) ?? "—"}</div>
              <p className="text-xs text-muted-foreground">{insights[0]?.category}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-1"><AlertTriangle className="h-4 w-4 text-red-500" /> Hoge actiepunten</CardTitle></CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">
                {insights.reduce((s: number, i: any) => s + (i.actiepunten || []).filter((a: any) => a.prioriteit === "hoog").length, 0)}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-1"><Eye className="h-4 w-4 text-amber-500" /> Te monitoren</CardTitle></CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-amber-600">
                {insights.reduce((s: number, i: any) => s + (i.te_monitoren || []).length, 0)}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-3">
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-52"><SelectValue placeholder="Alle categorieën" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle categorieën</SelectItem>
            {allCategories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-64" />)}</div>
      ) : filtered.length === 0 ? (
        <Card><CardContent className="p-12 text-center text-muted-foreground">
          Geen management-inzichten beschikbaar. Voer categoryscores in via de Categorie Analyse pagina.
        </CardContent></Card>
      ) : (
        filtered.map((insight: any, idx: number) => (
          <Card key={insight.category} className={idx === 0 && insight.growth_potential >= 60 ? "border-emerald-200" : ""}>
            <CardHeader className="pb-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    {idx === 0 && <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-medium">Hoogste groeipotentieel</span>}
                    <CardTitle className="text-lg">{insight.category}</CardTitle>
                  </div>
                  <CardDescription className="mt-1">
                    {insight.total_competitors_analyzed} concurrenten · {insight.high_relevance_count} belangrijk · {insight.monitor_count} monitoren
                  </CardDescription>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold">{insight.growth_potential?.toFixed(0)}</div>
                  <div className="text-xs text-muted-foreground">Groeipotentieel</div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Waarom relevant */}
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold flex items-center gap-2">
                    <Lightbulb className="h-4 w-4 text-amber-500" /> Waarom relevant?
                  </h4>
                  <p className="text-sm text-muted-foreground">{insight.waarom_relevant}</p>
                  <div className="flex justify-between text-xs mt-2">
                    <span className="text-muted-foreground">Coverage</span>
                    <span>{insight.coverage_index?.toFixed(0)}%</span>
                  </div>
                  <Progress value={insight.coverage_index || 0} className="h-1.5" />
                </div>

                {/* Wat ontbreekt */}
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold">Wat ontbreekt er?</h4>
                  <p className="text-sm text-muted-foreground">{insight.wat_ontbreekt}</p>
                  {(insight.missing_brands || []).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {insight.missing_brands.slice(0, 4).map((b: string) => (
                        <span key={b} className="text-xs bg-muted px-2 py-0.5 rounded">{b}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Actiepunten */}
              {(insight.actiepunten || []).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-500" /> Actiepunten
                  </h4>
                  <div className="space-y-2">
                    {insight.actiepunten.map((ap: any, i: number) => (
                      <div key={i} className="flex items-start gap-2 text-sm">
                        <Badge variant="outline" className={`text-xs shrink-0 ${PRIORITY_COLORS[ap.prioriteit] || ""}`}>
                          {ap.prioriteit}
                        </Badge>
                        <span className="text-muted-foreground">{ap.actie}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Te monitoren + Links */}
              <div className="flex items-center justify-between flex-wrap gap-3">
                {(insight.te_monitoren || []).length > 0 && (
                  <div className="flex items-center gap-2">
                    <Eye className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">Monitoren:</span>
                    {insight.te_monitoren.map((comp: string) => (
                      <Link key={comp} href={`/competition/competitors/${encodeURIComponent(comp)}`}>
                        <span className="text-sm text-primary hover:underline cursor-pointer">{comp}</span>
                      </Link>
                    ))}
                  </div>
                )}
                <Link href={`/competition/categories/${encodeURIComponent(insight.category)}`}>
                  <span className="text-xs text-primary hover:underline cursor-pointer flex items-center gap-1">
                    Volledige categorie-analyse <ChevronRight className="h-3 w-3" />
                  </span>
                </Link>
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
