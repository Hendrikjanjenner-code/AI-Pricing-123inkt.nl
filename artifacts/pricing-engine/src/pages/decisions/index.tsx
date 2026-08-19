import { useState } from "react";
import { Link } from "wouter";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Brain, RefreshCw, ChevronLeft, ChevronRight, AlertTriangle, Tag, Layers } from "lucide-react";
import { getAuthToken } from "@/lib/auth";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

async function apiFetch(path: string, options?: RequestInit) {
  const token = getAuthToken();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(options?.headers || {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  proposed: "bg-blue-100 text-blue-800",
  in_review: "bg-amber-100 text-amber-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  executed: "bg-emerald-600 text-white",
  cancelled: "bg-slate-200 text-slate-500",
};

const ENTITY_TYPE_STYLE: Record<string, string> = {
  sku: "bg-violet-100 text-violet-800",
  category: "bg-teal-100 text-teal-800",
};

const ENTITY_TYPE_LABEL: Record<string, string> = {
  sku: "SKU",
  category: "Categorie",
};

function EntityTypeBadge({ type }: { type: string }) {
  const Icon = type === "category" ? Layers : Tag;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${ENTITY_TYPE_STYLE[type] ?? "bg-slate-100 text-slate-700"}`}>
      <Icon className="h-3 w-3" />
      {ENTITY_TYPE_LABEL[type] ?? type}
    </span>
  );
}

export default function Beslissingen() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>("all");
  const [entityType, setEntityType] = useState<string>("all");
  const [search, setSearch] = useState("");
  const { toast } = useToast();
  const qc = useQueryClient();

  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (status !== "all") params.set("status", status);
  if (entityType !== "all") params.set("entity_type", entityType);
  if (search) params.set("search", search);
  const decisionsQs = [params.toString(), filterQs].filter(Boolean).join("&");

  const { data, isLoading } = useQuery({
    queryKey: ["decisions", page, status, entityType, search, filterQs],
    queryFn: () => apiFetch(`/api/decisions?${decisionsQs}`),
  });

  const runEngine = useMutation({
    mutationFn: () => apiFetch("/api/decisions/run", { method: "POST" }),
    onSuccess: (res: any) => {
      toast({
        title: "Decision Engine gedraaid",
        description: `${res.decisions_created} beslissingen aangemaakt (SKU's + categorieën), ${res.entities_skipped} overgeslagen.`,
      });
      qc.invalidateQueries({ queryKey: ["decisions"] });
    },
    onError: (e: any) => toast({ title: "Run mislukt", description: String(e?.message || e), variant: "destructive" }),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const etCounts: Record<string, number> = data?.entity_type_counts ?? {};

  return (
    <div className="p-6 space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Brain className="h-6 w-6 text-primary" /> Commerciële Beslissingen
            </h1>
            <p className="text-muted-foreground text-sm">
              Scenario's per SKU en categorie op basis van alle intelligence-signalen — goedkeuring blijft altijd menselijk.
            </p>
          </div>
          <Button onClick={() => runEngine.mutate()} disabled={runEngine.isPending}>
            <RefreshCw className={`h-4 w-4 mr-2 ${runEngine.isPending ? "animate-spin" : ""}`} />
            Genereer beslissingen
          </Button>
        </div>

        <GlobalFilterBar />

        <div className="flex gap-3 flex-wrap items-center">
          <Input
            placeholder="Zoek op SKU, categorie of naam…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="max-w-xs"
          />
          <Select value={entityType} onValueChange={(v) => { setEntityType(v); setPage(1); }}>
            <SelectTrigger className="w-48"><SelectValue placeholder="Entiteitstype" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                Alle typen ({(etCounts.sku ?? 0) + (etCounts.category ?? 0)})
              </SelectItem>
              <SelectItem value="sku">SKU ({etCounts.sku ?? 0})</SelectItem>
              <SelectItem value="category">Categorie ({etCounts.category ?? 0})</SelectItem>
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={(v) => { setStatus(v); setPage(1); }}>
            <SelectTrigger className="w-52"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle statussen</SelectItem>
              {(data?.statuses || []).map((s: any) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.label} ({data?.status_counts?.[s.id] ?? 0})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {isLoading ? (
          <div className="space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
        ) : !data?.items?.length ? (
          <Card><CardContent className="py-12 text-center text-muted-foreground">
            Geen beslissingen gevonden. Klik op "Genereer beslissingen" om de Decision Engine te draaien.
          </CardContent></Card>
        ) : (
          <div className="space-y-3">
            {data.items.map((d: any) => (
              <Link key={d.id} href={`/beslissingen/${d.id}`}>
                <Card className="cursor-pointer hover:border-primary/50 transition-colors">
                  <CardContent className="py-4 flex items-start justify-between gap-4 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <EntityTypeBadge type={d.entity_type} />
                        <span className="font-semibold">{d.entity_name || d.entity_id}</span>
                        <Badge variant="outline" className="font-mono text-xs">{d.entity_id}</Badge>
                        <Badge className={STATUS_STYLE[d.status] || ""}>{d.status_nl}</Badge>
                        {d.data_gaps?.length > 0 && (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-700">
                            <AlertTriangle className="h-3 w-3" /> {d.data_gaps.length} data-hiaten
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{d.summary}</p>
                    </div>
                    <div className="text-right text-sm shrink-0">
                      <div className="text-muted-foreground">{d.signal_count} signalen</div>
                      <div className="font-medium">
                        Confidence {d.confidence != null ? `${Math.round(d.confidence * 100)}%` : "—"}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}

        {data && data.total > data.page_size && (
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">{data.total} beslissingen — pagina {page} van {totalPages}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
    </div>
  );
}
