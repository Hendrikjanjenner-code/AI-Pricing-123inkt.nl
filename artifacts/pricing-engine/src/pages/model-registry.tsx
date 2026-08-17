import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { History, RotateCcw } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface Versie {
  id: number;
  versie: string;
  status: string;
  metrics: Record<string, unknown>;
  omschrijving: string | null;
  geactiveerd_op: string | null;
  aangemaakt_op: string | null;
}

interface Model {
  model_name: string;
  actieve_versie: string | null;
  versies: Versie[];
}

const STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-800",
  superseded: "bg-slate-100 text-slate-800",
  rolled_back: "bg-amber-100 text-amber-800",
  archived: "bg-slate-100 text-slate-500",
};

const MODEL_LABELS: Record<string, string> = {
  basket: "Basket Intelligence",
  promotion: "Promotion Intelligence",
  forecast_risk: "Forecast & Risk",
  opportunity: "Opportunity Engine",
  pricing: "Pricing Engine",
};

export default function ModelRegistry() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<{ modellen: Model[] }>({
    queryKey: ["model-registry"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/api/model-registry`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Kon modelregister niet laden");
      return res.json();
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: async ({ modelName, entryId }: { modelName: string; entryId: number }) => {
      const res = await fetch(`${BASE}/api/model-registry/${modelName}/rollback/${entryId}`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("Rollback mislukt");
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["model-registry"] }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Modelregister</h1>
        <p className="text-muted-foreground mt-1">
          Modelgovernance: naam, versie, metrics en status per model, met rollback naar een eerdere versie.
        </p>
      </div>

      {rollbackMutation.isError && (
        <p className="text-sm text-destructive">Rollback mislukt. Probeer het opnieuw.</p>
      )}

      {isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}
        </div>
      ) : !data?.modellen?.length ? (
        <div className="border rounded-md bg-card p-8 text-center text-muted-foreground">
          Nog geen modellen geregistreerd. Draai een engine om de eerste versie te registreren.
        </div>
      ) : (
        data.modellen.map((m) => (
          <div key={m.model_name} className="border rounded-md bg-card">
            <div className="p-4 border-b flex items-center justify-between">
              <div className="font-semibold flex items-center">
                <History className="w-4 h-4 mr-2" />
                {MODEL_LABELS[m.model_name] || m.model_name}
              </div>
              <Badge variant="secondary" className="bg-emerald-100 text-emerald-800">
                Actief: {m.actieve_versie || "—"}
              </Badge>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Versie</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Metrics (laatste run)</TableHead>
                  <TableHead>Geactiveerd</TableHead>
                  <TableHead className="text-right">Acties</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {m.versies.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell className="font-medium">{v.versie}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={STATUS_COLORS[v.status] || ""}>{v.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-md">
                      {Object.entries(v.metrics || {})
                        .filter(([k]) => k !== "last_run_at")
                        .map(([k, val]) => `${k}: ${val}`)
                        .join(" · ") || "—"}
                    </TableCell>
                    <TableCell className="text-sm">
                      {v.geactiveerd_op ? new Date(v.geactiveerd_op).toLocaleString("nl-NL") : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {v.status !== "active" && (
                        <Button
                          size="sm" variant="outline"
                          disabled={rollbackMutation.isPending}
                          onClick={() => rollbackMutation.mutate({ modelName: m.model_name, entryId: v.id })}
                        >
                          <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Rollback
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))
      )}
    </div>
  );
}
