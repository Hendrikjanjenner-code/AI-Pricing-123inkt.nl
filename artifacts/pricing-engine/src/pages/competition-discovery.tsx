import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle2, XCircle, Play, Search, Globe, Tag } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

function apiFetch(path: string, opts?: RequestInit) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    ...opts,
  }).then(r => r.json());
}

const METHOD_COLORS: Record<string, string> = {
  PATTERN:  "bg-blue-100 text-blue-700",
  KEYWORD:  "bg-purple-100 text-purple-700",
  OEM:      "bg-amber-100 text-amber-700",
  CATEGORY: "bg-emerald-100 text-emerald-700",
  EAN:      "bg-rose-100 text-rose-700",
};

const STATUS_COLORS: Record<string, string> = {
  PROPOSED: "bg-blue-50 text-blue-700 border-blue-200",
  APPROVED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  REJECTED: "bg-red-50 text-red-600 border-red-200",
};

const STATUS_LABELS: Record<string, string> = {
  PROPOSED: "Voorgesteld",
  APPROVED: "Goedgekeurd",
  REJECTED: "Afgewezen",
};

export default function CompetitionDiscovery() {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("all");
  const [zoekterm, setZoekterm] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["competition-discovery", statusFilter],
    queryFn: () => apiFetch(`/api/competition/discovery?page_size=100${statusFilter !== "all" ? `&status=${statusFilter}` : ""}`),
  });

  const approveMutation = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/competition/discovery/${id}/approve`, { method: "POST" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["competition-discovery"] }); toast({ title: "Goedgekeurd" }); },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/competition/discovery/${id}/reject`, { method: "POST" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["competition-discovery"] }); toast({ title: "Afgewezen" }); },
  });

  const runMutation = useMutation({
    mutationFn: () => apiFetch("/api/competition/discovery/run", { method: "POST" }),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["competition-discovery"] });
      toast({ title: "Discovery-run gestart", description: `${d.candidates_found} concurrenten gevonden, ${d.candidates_new} nieuw.` });
    },
  });

  const items = (data?.items || []).filter((i: any) =>
    !zoekterm
      || i.competitor_name?.toLowerCase().includes(zoekterm.toLowerCase())
      || i.domain?.toLowerCase().includes(zoekterm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Concurrent Discovery</h1>
          <p className="text-muted-foreground mt-1">Automatisch ontdekte concurrenten — beoordeel en keur goed of wijs af.</p>
        </div>
        <Button onClick={() => runMutation.mutate()} disabled={runMutation.isPending} className="shrink-0">
          <Play className="h-4 w-4 mr-2" />
          {runMutation.isPending ? "Bezig..." : "Discovery Starten"}
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Zoek concurrent of domein..." className="pl-9" value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Alle statussen" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle statussen</SelectItem>
            <SelectItem value="PROPOSED">Voorgesteld</SelectItem>
            <SelectItem value="APPROVED">Goedgekeurd</SelectItem>
            <SelectItem value="REJECTED">Afgewezen</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Discovery Queue</CardTitle>
          <CardDescription>{data?.total ?? 0} concurrenten — {items.length} weergegeven</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="border-t">
            <div className="grid grid-cols-12 bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground border-b">
              <div className="col-span-3">Concurrent / Domein</div>
              <div className="col-span-1 text-center">Status</div>
              <div className="col-span-1 text-center">Methode</div>
              <div className="col-span-1 text-center">Confidence</div>
              <div className="col-span-3">Categorieën</div>
              <div className="col-span-3">Acties</div>
            </div>
            {isLoading ? (
              <div className="p-8 space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-12" />)}</div>
            ) : items.length === 0 ? (
              <div className="p-12 text-center text-muted-foreground">Geen concurrenten gevonden. Klik op "Discovery Starten" om te beginnen.</div>
            ) : (
              <div className="divide-y max-h-[600px] overflow-y-auto">
                {items.map((item: any) => (
                  <div key={item.id} className="grid grid-cols-12 items-start px-4 py-3 text-sm hover:bg-muted/30 transition-colors gap-y-1">
                    <div className="col-span-3">
                      <div className="font-medium">{item.competitor_name}</div>
                      <div className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                        <Globe className="h-3 w-3" />{item.domain}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1 line-clamp-2 pr-2">{item.discovery_reason}</div>
                    </div>
                    <div className="col-span-1 flex justify-center pt-0.5">
                      <Badge variant="outline" className={`text-xs ${STATUS_COLORS[item.status] || ""}`}>
                        {STATUS_LABELS[item.status] || item.status}
                      </Badge>
                    </div>
                    <div className="col-span-1 flex justify-center pt-0.5">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${METHOD_COLORS[item.discovery_method] || "bg-slate-100 text-slate-700"}`}>
                        {item.discovery_method}
                      </span>
                    </div>
                    <div className="col-span-1 text-center pt-1">
                      <span className="font-mono text-sm font-semibold">
                        {Math.round((item.confidence || 0) * 100)}%
                      </span>
                    </div>
                    <div className="col-span-3 flex flex-wrap gap-1 pt-0.5">
                      {(item.categories || []).slice(0, 3).map((cat: string) => (
                        <span key={cat} className="text-xs bg-muted px-1.5 py-0.5 rounded flex items-center gap-0.5">
                          <Tag className="h-2.5 w-2.5" />{cat}
                        </span>
                      ))}
                      {(item.categories?.length || 0) > 3 && (
                        <span className="text-xs text-muted-foreground">+{item.categories.length - 3}</span>
                      )}
                    </div>
                    <div className="col-span-3 flex items-center gap-2 pt-0.5">
                      {item.status === "PROPOSED" && (
                        <>
                          <Button size="sm" variant="outline"
                            className="h-7 text-xs border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                            onClick={() => approveMutation.mutate(item.id)}
                            disabled={approveMutation.isPending}>
                            <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Goedkeuren
                          </Button>
                          <Button size="sm" variant="outline"
                            className="h-7 text-xs border-red-200 text-red-600 hover:bg-red-50"
                            onClick={() => rejectMutation.mutate(item.id)}
                            disabled={rejectMutation.isPending}>
                            <XCircle className="h-3.5 w-3.5 mr-1" /> Afwijzen
                          </Button>
                        </>
                      )}
                      {item.status === "APPROVED" && (
                        <span className="text-xs text-emerald-600 flex items-center gap-1">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Goedgekeurd door {item.approved_by}
                        </span>
                      )}
                      {item.status === "REJECTED" && (
                        <span className="text-xs text-red-500 flex items-center gap-1">
                          <XCircle className="h-3.5 w-3.5" />
                          Afgewezen door {item.approved_by}
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
