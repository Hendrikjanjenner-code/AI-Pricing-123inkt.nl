import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ShoppingCart, Link2, Euro, RefreshCw } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";
import { useEngineRun } from "@/lib/use-engine-run";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface Associatie {
  id: number;
  antecedent_sku: string;
  antecedent_naam: string | null;
  consequent_sku: string;
  consequent_naam: string | null;
  support: number;
  confidence: number;
  lift: number;
  samen_gekocht: number;
  relatie_type: string;
  bundel_marge_eur: number;
  gem_mandwaarde: number;
  toelichting: string | null;
}

interface Dashboard {
  run_date: string | null;
  totaal_associaties: number;
  per_type: Record<string, number>;
  gemiddelde_mandmarge: number;
  associaties: Associatie[];
}

const TYPE_LABELS: Record<string, string> = {
  cross_sell: "Cross-sell",
  upsell: "Upsell",
  bundle: "Bundel",
  basket_filler: "Basket filler",
};

const TYPE_COLORS: Record<string, string> = {
  cross_sell: "bg-blue-100 text-blue-800",
  upsell: "bg-purple-100 text-purple-800",
  bundle: "bg-emerald-100 text-emerald-800",
  basket_filler: "bg-amber-100 text-amber-800",
};

const eur = (v: number) => new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(v);

export default function BasketIntelligenceDashboard() {
  const qc = useQueryClient();
  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);
  const { data, isLoading } = useQuery<Dashboard>({
    queryKey: ["basket-associations", filterQs],
    queryFn: async () => {
      const res = await fetch(`${BASE}/api/basket/associations${filterQs ? `?${filterQs}` : ""}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Kon basket-associaties niet laden");
      return res.json();
    },
  });

  const run = useEngineRun({
    runUrl: `${BASE}/api/basket/run`,
    onCompleted: () => qc.invalidateQueries({ queryKey: ["basket-associations"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Basket Intelligence</h1>
          <p className="text-muted-foreground mt-1">
            Product-associaties, frequently-bought-together, cross-sell/upsell en basket fillers.
            {data?.run_date && <> Laatste analyse: {data.run_date}.</>}
          </p>
        </div>
        <Button onClick={() => run.start()} disabled={run.isRunning}>
          <RefreshCw className={`w-4 h-4 mr-2 ${run.isRunning ? "animate-spin" : ""}`} />
          {run.isRunning ? "Bezig met herberekenen…" : "Herbereken"}
        </Button>
      </div>

      <GlobalFilterBar />

      {run.isRunning && (
        <p className="text-sm text-muted-foreground">
          De herberekening draait op de achtergrond. Dit kan enkele minuten duren; de resultaten verschijnen automatisch.
        </p>
      )}
      {run.error && (
        <p className="text-sm text-destructive">{run.error}</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Link2 className="w-4 h-4 mr-2" /> Associaties
          </div>
          <div className="text-3xl font-bold">{isLoading ? <Skeleton className="h-8 w-16" /> : data?.totaal_associaties ?? 0}</div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Euro className="w-4 h-4 mr-2" /> Gem. marge per mandje
          </div>
          <div className="text-3xl font-bold text-emerald-600">
            {isLoading ? <Skeleton className="h-8 w-20" /> : eur(data?.gemiddelde_mandmarge ?? 0)}
          </div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <ShoppingCart className="w-4 h-4 mr-2" /> Per type
          </div>
          <div className="flex flex-wrap gap-2 mt-1">
            {Object.entries(data?.per_type ?? {}).map(([t, n]) => (
              <Badge key={t} variant="secondary" className={TYPE_COLORS[t] || ""}>
                {TYPE_LABELS[t] || t}: {n}
              </Badge>
            ))}
            {!isLoading && Object.keys(data?.per_type ?? {}).length === 0 && (
              <span className="text-sm text-muted-foreground">—</span>
            )}
          </div>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead>Samen gekocht met</TableHead>
              <TableHead>Type</TableHead>
              <TableHead className="text-right">Samen gekocht</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
              <TableHead className="text-right">Lift</TableHead>
              <TableHead className="text-right">Bundelmarge</TableHead>
              <TableHead className="text-right">Gem. mandwaarde</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {[1, 2, 3, 4, 5, 6, 7, 8].map((j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : !data?.associaties?.length ? (
              <TableRow>
                <TableCell colSpan={8} className="h-32 text-center text-muted-foreground">
                  Geen associaties gevonden. Upload basket-affiniteitsdata en klik op Herbereken.
                </TableCell>
              </TableRow>
            ) : (
              data.associaties.map((a) => (
                <TableRow key={a.id}>
                  <TableCell>
                    <div className="font-medium">{a.antecedent_naam || a.antecedent_sku}</div>
                    <div className="text-xs text-muted-foreground">{a.antecedent_sku}</div>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{a.consequent_naam || a.consequent_sku}</div>
                    <div className="text-xs text-muted-foreground">{a.consequent_sku}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={TYPE_COLORS[a.relatie_type] || ""}>
                      {TYPE_LABELS[a.relatie_type] || a.relatie_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">{a.samen_gekocht}×</TableCell>
                  <TableCell className="text-right">{(a.confidence * 100).toFixed(0)}%</TableCell>
                  <TableCell className="text-right">{a.lift.toFixed(2)}</TableCell>
                  <TableCell className="text-right text-emerald-600">{eur(a.bundel_marge_eur)}</TableCell>
                  <TableCell className="text-right">{eur(a.gem_mandwaarde)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
