import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Lightbulb, Euro, RefreshCw, Check, X } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface Opportunity {
  id: number;
  bron_engine: string;
  ondersteunende_engines: string[];
  type: string;
  sku_id: string;
  naam: string | null;
  titel: string | null;
  toelichting: string | null;
  verwachte_waarde: number;
  verwachte_omzet: number;
  verwachte_marge: number;
  confidence: number;
  urgentie: string;
  effort: string;
  risico: string;
  prioriteit: number;
  status: string;
}

interface Dashboard {
  run_date: string | null;
  totaal: number;
  per_engine: Record<string, number>;
  totale_verwachte_waarde: number;
  opportunities: Opportunity[];
}

const ENGINE_LABELS: Record<string, string> = {
  pricing: "Pricing",
  basket: "Basket",
  promotion: "Promotion",
  forecast_risk: "Forecast & Risk",
};

const URGENCY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-800",
};

const eur = (v: number) => new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(v);

export default function Opportunities() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<Dashboard>({
    queryKey: ["opportunities"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/api/opportunities?status=open`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Kon opportunities niet laden");
      return res.json();
    },
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${BASE}/api/opportunities/run`, { method: "POST", headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Run mislukt");
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["opportunities"] }),
  });

  const statusMutation = useMutation({
    mutationFn: async ({ id, status }: { id: number; status: string }) => {
      const res = await fetch(`${BASE}/api/opportunities/${id}/status?status=${status}`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("Statuswijziging mislukt");
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["opportunities"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Opportunity Engine</h1>
          <p className="text-muted-foreground mt-1">
            Eén centraal overzicht van kansen uit alle engines, geprioriteerd op verwachte waarde,
            urgentie, effort en risico.
            {data?.run_date && <> Laatste run: {data.run_date}.</>}
          </p>
        </div>
        <Button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
          <RefreshCw className={`w-4 h-4 mr-2 ${runMutation.isPending ? "animate-spin" : ""}`} />
          Vernieuw kansen
        </Button>
      </div>

      {(runMutation.isError || statusMutation.isError) && (
        <p className="text-sm text-destructive">Actie mislukt. Probeer het opnieuw.</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Lightbulb className="w-4 h-4 mr-2" /> Open kansen
          </div>
          <div className="text-3xl font-bold">{isLoading ? <Skeleton className="h-8 w-12" /> : data?.totaal ?? 0}</div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Euro className="w-4 h-4 mr-2" /> Totale verwachte waarde
          </div>
          <div className="text-3xl font-bold text-emerald-600">
            {isLoading ? <Skeleton className="h-8 w-24" /> : eur(data?.totale_verwachte_waarde ?? 0)}
          </div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground mb-2">Per engine</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data?.per_engine ?? {}).map(([e, n]) => (
              <Badge key={e} variant="secondary">{ENGINE_LABELS[e] || e}: {n}</Badge>
            ))}
            {!isLoading && Object.keys(data?.per_engine ?? {}).length === 0 && (
              <span className="text-sm text-muted-foreground">—</span>
            )}
          </div>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-right">Prio</TableHead>
              <TableHead>Kans</TableHead>
              <TableHead>Bron</TableHead>
              <TableHead className="text-right">Verwachte waarde</TableHead>
              <TableHead className="text-right">Marge</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
              <TableHead>Urgentie</TableHead>
              <TableHead>Effort</TableHead>
              <TableHead>Risico</TableHead>
              <TableHead className="text-right">Acties</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 10 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : !data?.opportunities?.length ? (
              <TableRow>
                <TableCell colSpan={10} className="h-32 text-center text-muted-foreground">
                  Geen open kansen. Draai de engines en klik op "Vernieuw kansen".
                </TableCell>
              </TableRow>
            ) : (
              data.opportunities.map((o) => (
                <TableRow key={o.id}>
                  <TableCell className="text-right font-bold">{o.prioriteit.toFixed(0)}</TableCell>
                  <TableCell className="max-w-md">
                    <div className="font-medium">{o.titel}</div>
                    <div className="text-xs text-muted-foreground">{o.naam || o.sku_id} · {o.toelichting}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{ENGINE_LABELS[o.bron_engine] || o.bron_engine}</Badge>
                    {o.ondersteunende_engines.length > 0 && (
                      <div className="text-xs text-muted-foreground mt-1">
                        + {o.ondersteunende_engines.map((e) => ENGINE_LABELS[e] || e).join(", ")}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-right text-emerald-600 font-medium">{eur(o.verwachte_waarde)}</TableCell>
                  <TableCell className="text-right">{eur(o.verwachte_marge)}</TableCell>
                  <TableCell className="text-right">{(o.confidence * 100).toFixed(0)}%</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={URGENCY_COLORS[o.urgentie] || ""}>{o.urgentie}</Badge>
                  </TableCell>
                  <TableCell className="text-sm">{o.effort}</TableCell>
                  <TableCell className="text-sm">{o.risico}</TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      size="sm" variant="ghost" title="Markeer als afgehandeld"
                      onClick={() => statusMutation.mutate({ id: o.id, status: "done" })}
                    >
                      <Check className="w-4 h-4 text-emerald-600" />
                    </Button>
                    <Button
                      size="sm" variant="ghost" title="Verwerp"
                      onClick={() => statusMutation.mutate({ id: o.id, status: "dismissed" })}
                    >
                      <X className="w-4 h-4 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
