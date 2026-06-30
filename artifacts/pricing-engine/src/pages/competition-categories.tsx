import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Search, Circle, ChevronRight } from "lucide-react";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const TRAFFIC_LIGHT: Record<string, { color: string; label: string }> = {
  green:  { color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "Belangrijk" },
  orange: { color: "text-amber-600 bg-amber-50 border-amber-200",       label: "Monitoren" },
  red:    { color: "text-red-600 bg-red-50 border-red-200",             label: "Laag" },
};

const SCORE_DEFS = [
  { key: "relevance_score",           label: "Relevantie",           color: "#3b82f6" },
  { key: "coverage_index",            label: "Coverage Index",       color: "#10b981" },
  { key: "authority_score",           label: "Gezag",                color: "#8b5cf6" },
  { key: "assortment_gap_score",      label: "Assortiment Gap",      color: "#f97316" },
  { key: "pricing_relevance_score",   label: "Prijsrelevantie",      color: "#f59e0b" },
  { key: "traffic_relevance_score",   label: "Trafficrelevantie",    color: "#ef4444" },
  { key: "opportunity_score",         label: "Opportunity",          color: "#06b6d4" },
];

export default function CompetitionCategories() {
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [labelFilter, setLabelFilter] = useState("all");
  const [zoekterm, setZoekterm] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["competition-categories", categoryFilter, labelFilter],
    queryFn: () => {
      const params = new URLSearchParams({ page_size: "200" });
      if (categoryFilter !== "all") params.set("category", categoryFilter);
      if (labelFilter !== "all") params.set("relevance_label", labelFilter);
      return apiFetch(`/api/competition/categories?${params}`);
    },
  });

  const items = (data?.items || []).filter((r: any) =>
    !zoekterm
      || r.competitor_name?.toLowerCase().includes(zoekterm.toLowerCase())
      || r.category?.toLowerCase().includes(zoekterm.toLowerCase())
  );

  // Unieke categorieën voor filter
  const allCategories = Array.from(new Set((data?.items || []).map((r: any) => r.category))) as string[];

  // Groepeer per categorie
  const grouped: Record<string, any[]> = {};
  for (const item of items) {
    grouped[item.category] = grouped[item.category] || [];
    grouped[item.category].push(item);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Categorie Analyse</h1>
        <p className="text-muted-foreground mt-1">7 categoryscores per concurrent per DRS-categorie — Coverage, Relevantie, Gezag, Assortiment Gap, Prijs, Traffic en Opportunity.</p>
      </div>

      <div className="flex gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Zoek concurrent of categorie..." className="pl-9" value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
        </div>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-52"><SelectValue placeholder="Alle categorieën" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle categorieën</SelectItem>
            {allCategories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={labelFilter} onValueChange={setLabelFilter}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Alle labels" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle labels</SelectItem>
            <SelectItem value="HIGH">Belangrijk</SelectItem>
            <SelectItem value="MONITOR">Monitoren</SelectItem>
            <SelectItem value="LOW">Laag</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-48" />)}</div>
      ) : Object.keys(grouped).length === 0 ? (
        <Card><CardContent className="p-12 text-center text-muted-foreground">Geen categoryscores beschikbaar. Draai de backfill of voer een analyse-run uit.</CardContent></Card>
      ) : (
        Object.entries(grouped).map(([cat, rows]) => (
          <Card key={cat}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">{cat}</CardTitle>
                  <CardDescription>{rows.length} concurrenten · gem. coverage {(rows.reduce((s, r) => s + (r.coverage_index || 0), 0) / rows.length).toFixed(0)}%</CardDescription>
                </div>
                <Link href={`/competition/categories/${encodeURIComponent(cat)}`}>
                  <span className="text-xs text-primary hover:underline cursor-pointer flex items-center gap-1">Categorie-detail <ChevronRight className="h-3 w-3" /></span>
                </Link>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="border-t">
                {/* Header */}
                <div className="grid px-4 py-2 bg-muted/40 border-b text-xs font-medium text-muted-foreground" style={{ gridTemplateColumns: "1fr 80px 80px 80px 80px 80px 80px 80px 80px" }}>
                  <div>Concurrent</div>
                  <div className="text-center">Status</div>
                  {SCORE_DEFS.slice(0, 5).map(s => (
                    <div key={s.key} className="text-center">{s.label.split(" ")[0]}</div>
                  ))}
                  <div className="text-center">Combinatie</div>
                </div>
                <div className="divide-y max-h-[400px] overflow-y-auto">
                  {rows.sort((a: any, b: any) => (b.combined_score || 0) - (a.combined_score || 0)).map((row: any) => {
                    const tl = TRAFFIC_LIGHT[row.traffic_light || "orange"] || TRAFFIC_LIGHT.orange;
                    return (
                      <Link key={row.competitor_name} href={`/competition/competitors/${encodeURIComponent(row.competitor_name)}`}>
                        <div className="grid items-center px-4 py-2.5 hover:bg-muted/30 cursor-pointer transition-colors" style={{ gridTemplateColumns: "1fr 80px 80px 80px 80px 80px 80px 80px 80px" }}>
                          <div className="font-medium text-sm truncate pr-2">{row.competitor_name}</div>
                          <div className="flex justify-center">
                            <Badge variant="outline" className={`text-xs ${tl.color}`}>
                              <Circle className="h-1.5 w-1.5 mr-0.5 fill-current" />{row.relevance_label}
                            </Badge>
                          </div>
                          {SCORE_DEFS.slice(0, 5).map(s => (
                            <div key={s.key} className="text-center">
                              <span className="font-mono text-sm font-medium"
                                style={{ color: (row[s.key] || 0) >= 70 ? "#10b981" : (row[s.key] || 0) >= 40 ? "#f59e0b" : "#ef4444" }}>
                                {(row[s.key] || 0).toFixed(0)}
                              </span>
                            </div>
                          ))}
                          <div className="text-center font-bold text-sm">{(row.combined_score || 0).toFixed(0)}</div>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
