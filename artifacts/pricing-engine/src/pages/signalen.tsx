import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  RefreshCw, TrendingUp, TrendingDown, Minus, Radio, ChevronLeft, ChevronRight, X,
} from "lucide-react";
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

const SEVERITY_NL: Record<string, string> = {
  critical: "Kritiek",
  high: "Hoog",
  medium: "Gemiddeld",
  low: "Laag",
  info: "Info",
};

const SEVERITY_STYLE: Record<string, string> = {
  critical: "bg-red-600 text-white",
  high: "bg-red-100 text-red-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-700",
  info: "bg-blue-100 text-blue-800",
};

const ENGINE_NL: Record<string, string> = {
  competition: "Concurrentie",
  pricing: "Pricing",
  bcg: "BCG",
  traffic: "Traffic",
  procurement: "Inkoop",
  switching: "Huismerk/Switching",
  cost: "Kosten",
  economic: "Economie",
};

const ENTITY_NL: Record<string, string> = {
  sku: "SKU",
  category: "Categorie",
  brand: "Merk",
  competitor: "Concurrent",
  shop: "Shop",
  supplier: "Leverancier",
};

interface Signal {
  id: number;
  engine: string;
  signal_type: string;
  severity: string;
  direction: string | null;
  entity_type: string;
  entity_id: string;
  entity_name: string | null;
  metric: string | null;
  current_value: number | null;
  previous_value: number | null;
  change_pct: number | null;
  confidence: number;
  explanation: string;
  evidence: Record<string, unknown> | null;
  suggested_action: string | null;
  observed_at: string | null;
  valid_until: string | null;
  model_version: string | null;
  status: string;
}

export default function Signalen() {
  const { toast } = useToast();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [laden, setLaden] = useState(true);
  const [vernieuwen, setVernieuwen] = useState(false);
  const [engine, setEngine] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [entityType, setEntityType] = useState("all");
  const [engines, setEngines] = useState<string[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const pageSize = 50;

  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  const laad = useCallback(async () => {
    setLaden(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), status: "active" });
      if (engine !== "all") params.set("engine", engine);
      if (severity !== "all") params.set("severity", severity);
      if (entityType !== "all") params.set("entity_type", entityType);
      const qs = [params.toString(), filterQs].filter(Boolean).join("&");
      const data = await apiFetch(`/api/signals?${qs}`);
      setSignals(data.signals || []);
      setTotal(data.total || 0);
      setEngines(data.filter_options?.engines || []);
    } catch (e: any) {
      toast({ title: "Laden mislukt", description: String(e?.message || e), variant: "destructive" });
    } finally {
      setLaden(false);
    }
  }, [page, engine, severity, entityType, filterQs, toast]);

  useEffect(() => { laad(); }, [laad]);

  async function vernieuwSignalen() {
    setVernieuwen(true);
    try {
      const res = await apiFetch(`/api/signals/refresh`, { method: "POST" });
      const totaal = Object.values(res.published_per_engine || {})
        .filter((v: any) => typeof v === "number" && v > 0)
        .reduce((a: number, b: any) => a + b, 0);
      const gefaald: string[] = res.failed_engines || [];
      if (gefaald.length > 0) {
        toast({
          title: "Vernieuwen gedeeltelijk mislukt",
          description: `Gefaalde engines: ${gefaald.join(", ")}. ${totaal} signalen gepubliceerd door de overige engines.`,
          variant: "destructive",
        });
      } else {
        toast({ title: "Signalen vernieuwd", description: `${totaal} signalen gepubliceerd.` });
      }
      setPage(1);
      await laad();
    } catch (e: any) {
      toast({ title: "Vernieuwen mislukt", description: String(e?.message || e), variant: "destructive" });
    } finally {
      setVernieuwen(false);
    }
  }

  async function dismiss(id: number) {
    try {
      await apiFetch(`/api/signals/${id}/dismiss`, { method: "POST" });
      setSignals((s) => s.filter((x) => x.id !== id));
      toast({ title: "Signaal verborgen" });
    } catch (e: any) {
      toast({ title: "Verbergen mislukt", description: String(e?.message || e), variant: "destructive" });
    }
  }

  const totaalPaginas = Math.max(1, Math.ceil(total / pageSize));

  const perSeverity: Record<string, number> = {};
  for (const s of signals) perSeverity[s.severity] = (perSeverity[s.severity] || 0) + 1;

  return (
    <div className="p-6 space-y-6" data-testid="page-signalen">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Radio className="w-6 h-6 text-blue-600" /> Intelligence Signals
          </h1>
          <p className="text-sm text-muted-foreground">
            Gestandaardiseerde signalen van alle engines — met uitleg, bewijs en betrouwbaarheid.
          </p>
        </div>
        <Button onClick={vernieuwSignalen} disabled={vernieuwen} data-testid="button-refresh-signals">
          <RefreshCw className={`w-4 h-4 mr-2 ${vernieuwen ? "animate-spin" : ""}`} />
          {vernieuwen ? "Bezig..." : "Signalen vernieuwen"}
        </Button>
      </div>

      <GlobalFilterBar />

      {/* Filters */}
      <Card>
        <CardContent className="pt-6 flex flex-wrap gap-3 items-center">
          <Select value={engine} onValueChange={(v) => { setEngine(v); setPage(1); }}>
            <SelectTrigger className="w-52" data-testid="select-engine"><SelectValue placeholder="Engine" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle engines</SelectItem>
              {engines.map((e) => (
                <SelectItem key={e} value={e}>{ENGINE_NL[e] || e}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={severity} onValueChange={(v) => { setSeverity(v); setPage(1); }}>
            <SelectTrigger className="w-44" data-testid="select-severity"><SelectValue placeholder="Ernst" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle ernstniveaus</SelectItem>
              {Object.entries(SEVERITY_NL).map(([k, v]) => (
                <SelectItem key={k} value={k}>{v}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={entityType} onValueChange={(v) => { setEntityType(v); setPage(1); }}>
            <SelectTrigger className="w-44" data-testid="select-entity-type"><SelectValue placeholder="Type" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle entiteiten</SelectItem>
              {Object.entries(ENTITY_NL).map(([k, v]) => (
                <SelectItem key={k} value={k}>{v}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="ml-auto text-sm text-muted-foreground" data-testid="text-total">
            {total} actieve signalen
          </div>
        </CardContent>
      </Card>

      {/* Lijst */}
      {laden ? (
        <div className="space-y-2">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}</div>
      ) : signals.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-muted-foreground">
          Geen actieve signalen voor deze filters. Klik op "Signalen vernieuwen" om de engines opnieuw te laten publiceren.
        </CardContent></Card>
      ) : (
        <div className="space-y-2">
          {signals.map((s) => (
            <Card key={s.id} className="hover:shadow-sm transition-shadow" data-testid={`card-signal-${s.id}`}>
              <CardContent className="py-4">
                <div className="flex items-start gap-3 flex-wrap">
                  <div className="mt-0.5">
                    {s.direction === "positive" ? <TrendingUp className="w-5 h-5 text-green-600" />
                      : s.direction === "negative" ? <TrendingDown className="w-5 h-5 text-red-500" />
                      : <Minus className="w-5 h-5 text-slate-400" />}
                  </div>
                  <div className="flex-1 min-w-[280px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge className={SEVERITY_STYLE[s.severity] || SEVERITY_STYLE.info}>
                        {SEVERITY_NL[s.severity] || s.severity}
                      </Badge>
                      <Badge variant="outline">{ENGINE_NL[s.engine] || s.engine}</Badge>
                      <Badge variant="outline">{ENTITY_NL[s.entity_type] || s.entity_type}: {s.entity_name || s.entity_id}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {s.signal_type.replace(/_/g, " ")}
                        {s.change_pct != null && ` · ${s.change_pct > 0 ? "+" : ""}${s.change_pct.toFixed(1)}%`}
                        {` · betrouwbaarheid ${(s.confidence * 100).toFixed(0)}%`}
                      </span>
                    </div>
                    <p className="text-sm mt-1">{s.explanation}</p>
                    {s.suggested_action && (
                      <p className="text-xs text-blue-700 mt-1">Actie: {s.suggested_action}</p>
                    )}
                    {open === s.id && s.evidence && (
                      <pre className="text-xs bg-slate-50 border rounded p-2 mt-2 overflow-x-auto" data-testid={`evidence-${s.id}`}>
                        {JSON.stringify({ evidence: s.evidence, model_version: s.model_version, observed_at: s.observed_at, valid_until: s.valid_until }, null, 2)}
                      </pre>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="sm" onClick={() => setOpen(open === s.id ? null : s.id)} data-testid={`button-evidence-${s.id}`}>
                      {open === s.id ? "Verberg bewijs" : "Bewijs"}
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => dismiss(s.id)} title="Signaal verbergen" data-testid={`button-dismiss-${s.id}`}>
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Paginering */}
      {totaalPaginas > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="button-prev-page">
            <ChevronLeft className="w-4 h-4" /> Vorige
          </Button>
          <span className="text-sm text-muted-foreground">Pagina {page} van {totaalPaginas}</span>
          <Button variant="outline" size="sm" disabled={page >= totaalPaginas} onClick={() => setPage(page + 1)} data-testid="button-next-page">
            Volgende <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
