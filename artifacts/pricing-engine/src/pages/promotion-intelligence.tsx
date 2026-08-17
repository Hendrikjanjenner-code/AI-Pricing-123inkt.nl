import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Megaphone, Euro, FlaskConical, RefreshCw } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface Effect {
  id: number;
  promotion_id: number;
  sku_id: string;
  naam: string;
  periode: string;
  uplift_pct: number;
  net_uplift_pct: number;
  incrementele_omzet: number;
  incrementele_marge: number;
  break_even_stuks: number;
  break_even_gehaald: boolean;
  cannibalisatie_pct: number | null;
  halo_pct: number | null;
  controlegroep: boolean;
  controlegroep_grootte: number;
  oordeel: string;
  confidence: number;
  toelichting: string | null;
}

interface Dashboard {
  run_date: string | null;
  totaal: number;
  verdicts: Record<string, number>;
  totale_incrementele_marge: number;
  totale_incrementele_omzet: number;
  met_controlegroep: number;
  effecten: Effect[];
}

const VERDICT_COLORS: Record<string, string> = {
  EFFECTIEF: "bg-emerald-100 text-emerald-800",
  MARGINAAL: "bg-amber-100 text-amber-800",
  VERLIESGEVEND: "bg-red-100 text-red-800",
};

const eur = (v: number) => new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(v);
const pct = (v: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);

export default function PromotionIntelligence() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<Dashboard>({
    queryKey: ["promotion-dashboard"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/api/promotion-intelligence/dashboard`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Kon promotie-analyse niet laden");
      return res.json();
    },
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${BASE}/api/promotion-intelligence/run`, { method: "POST", headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Run mislukt");
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["promotion-dashboard"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Promotion Intelligence</h1>
          <p className="text-muted-foreground mt-1">
            Historische promo-analyse: uplift, incrementele omzet/marge, break-even, cannibalisatie en halo.
            {data?.run_date && <> Laatste analyse: {data.run_date}.</>}
          </p>
        </div>
        <Button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
          <RefreshCw className={`w-4 h-4 mr-2 ${runMutation.isPending ? "animate-spin" : ""}`} />
          Analyseer promoties
        </Button>
      </div>

      {runMutation.isError && (
        <p className="text-sm text-destructive">Analyse mislukt. Probeer het opnieuw.</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Megaphone className="w-4 h-4 mr-2" /> Geanalyseerd
          </div>
          <div className="text-3xl font-bold">{isLoading ? <Skeleton className="h-8 w-12" /> : data?.totaal ?? 0}</div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Euro className="w-4 h-4 mr-2" /> Incrementele marge
          </div>
          <div className={`text-3xl font-bold ${(data?.totale_incrementele_marge ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
            {isLoading ? <Skeleton className="h-8 w-24" /> : eur(data?.totale_incrementele_marge ?? 0)}
          </div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <Euro className="w-4 h-4 mr-2" /> Incrementele omzet
          </div>
          <div className="text-3xl font-bold">
            {isLoading ? <Skeleton className="h-8 w-24" /> : eur(data?.totale_incrementele_omzet ?? 0)}
          </div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <FlaskConical className="w-4 h-4 mr-2" /> Met controlegroep
          </div>
          <div className="text-3xl font-bold">{isLoading ? <Skeleton className="h-8 w-12" /> : `${data?.met_controlegroep ?? 0}/${data?.totaal ?? 0}`}</div>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead>Periode</TableHead>
              <TableHead className="text-right">Uplift</TableHead>
              <TableHead className="text-right">Netto uplift</TableHead>
              <TableHead className="text-right">Incr. marge</TableHead>
              <TableHead className="text-center">Break-even</TableHead>
              <TableHead className="text-right">Cannibalisatie</TableHead>
              <TableHead className="text-right">Halo</TableHead>
              <TableHead>Oordeel</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 9 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : !data?.effecten?.length ? (
              <TableRow>
                <TableCell colSpan={9} className="h-32 text-center text-muted-foreground">
                  Geen promotie-effecten. Upload promoties en klik op "Analyseer promoties".
                </TableCell>
              </TableRow>
            ) : (
              data.effecten.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>
                    <div className="font-medium">{e.naam}</div>
                    <div className="text-xs text-muted-foreground">{e.sku_id}</div>
                  </TableCell>
                  <TableCell className="text-sm">{e.periode}</TableCell>
                  <TableCell className="text-right">{pct(e.uplift_pct)}</TableCell>
                  <TableCell className="text-right font-medium">
                    {pct(e.net_uplift_pct)}
                    {e.controlegroep && (
                      <div className="text-xs text-muted-foreground">ctrl n={e.controlegroep_grootte}</div>
                    )}
                  </TableCell>
                  <TableCell className={`text-right ${e.incrementele_marge >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                    {eur(e.incrementele_marge)}
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant="secondary" className={e.break_even_gehaald ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}>
                      {e.break_even_gehaald ? "Gehaald" : "Niet gehaald"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">{e.cannibalisatie_pct != null ? `${e.cannibalisatie_pct.toFixed(1)}%` : "—"}</TableCell>
                  <TableCell className="text-right">{pct(e.halo_pct)}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={VERDICT_COLORS[e.oordeel] || ""}>{e.oordeel}</Badge>
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
