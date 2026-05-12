import { useState } from "react";
import { useListCategoryStrategies, useUpdateCategoryStrategy } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Save } from "lucide-react";

const STRATEGIE_OPTIES = [
  { waarde: "SUBSTITUTION_PORTFOLIO", label: "Substitutieportfolio" },
  { waarde: "COMPETITOR_INDEX", label: "Concurrentie-index" },
  { waarde: "MARGIN_OPTIMIZATION", label: "Margeoptimalisatie" },
  { waarde: "STOCK_CLEARANCE", label: "Voorraadopruiming" },
  { waarde: "BASKET_BUILDER", label: "Winkelmandbouwer" },
  { waarde: "VOLUME_DISCOUNT", label: "Volumekorting" },
  { waarde: "REPEAT_PURCHASE", label: "Herhalingsaankoop" },
  { waarde: "LOW_VELOCITY", label: "Laag volume" },
  { waarde: "PRIVATE_LABEL_PUSH", label: "Huismerk push" },
  { waarde: "PORTFOLIO_MARGIN_OPTIMIZATION", label: "Portfolio margeoptimalisatie" },
  { waarde: "TRAFFIC_TO_MARGIN_SWITCH", label: "Traffic naar marge" },
];

export default function CategorieStrategie() {
  const { data: strategieen, isLoading } = useListCategoryStrategies();
  const updateMut = useUpdateCategoryStrategy();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [bewerkingen, setBewerkingen] = useState<Record<number, { strategy_type: string; notes: string }>>({});

  const handleBewerking = (id: number, veld: string, waarde: string) => {
    setBewerkingen(prev => ({
      ...prev,
      [id]: {
        ...prev[id],
        strategy_type: prev[id]?.strategy_type ?? strategieen?.find(s => s.id === id)?.strategy_type ?? "",
        notes: prev[id]?.notes ?? strategieen?.find(s => s.id === id)?.notes ?? "",
        [veld]: waarde
      }
    }));
  };

  const handleOpslaan = async (id: number) => {
    const bewerking = bewerkingen[id];
    if (!bewerking) return;
    try {
      await updateMut.mutateAsync({
        id,
        data: { strategy_type: bewerking.strategy_type, notes: bewerking.notes || null }
      });
      queryClient.invalidateQueries({ queryKey: ["/api/category-strategies"] });
      const nieuw = { ...bewerkingen };
      delete nieuw[id];
      setBewerkingen(nieuw);
      toast({ title: "Strategie bijgewerkt" });
    } catch {
      toast({ title: "Fout bij opslaan", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Categoriestrategieën</h1>
          <p className="text-muted-foreground mt-1">Stel standaard prijsstrategieën in per categorie en subcategorie.</p>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Categorie</TableHead>
              <TableHead>Subcategorie</TableHead>
              <TableHead>Strategie</TableHead>
              <TableHead>Opmerkingen</TableHead>
              <TableHead className="text-right">Acties</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {[1,2,3,4,5].map(j => <TableCell key={j}><Skeleton className="h-8 w-full" /></TableCell>)}
                </TableRow>
              ))
            ) : strategieen?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-32 text-center text-muted-foreground">
                  Geen categoriestrategieën gedefinieerd.
                </TableCell>
              </TableRow>
            ) : strategieen?.map((strat) => {
              const bewerkt = bewerkingen[strat.id] !== undefined;
              const huidigStrat = bewerkt ? bewerkingen[strat.id].strategy_type : strat.strategy_type;
              const huidigNotes = bewerkt ? bewerkingen[strat.id].notes : (strat.notes || "");

              return (
                <TableRow key={strat.id} className="group">
                  <TableCell className="font-medium">{strat.category}</TableCell>
                  <TableCell>{strat.subcategory || <span className="text-muted-foreground italic">Alle</span>}</TableCell>
                  <TableCell>
                    <Select value={huidigStrat} onValueChange={(v) => handleBewerking(strat.id, "strategy_type", v)}>
                      <SelectTrigger className="w-[260px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {STRATEGIE_OPTIES.map(opt => (
                          <SelectItem key={opt.waarde} value={opt.waarde}>{opt.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Input
                      value={huidigNotes}
                      onChange={(e) => handleBewerking(strat.id, "notes", e.target.value)}
                      placeholder="Toelichting toevoegen..."
                      className="max-w-[400px]"
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    {bewerkt ? (
                      <Button size="sm" onClick={() => handleOpslaan(strat.id)} disabled={updateMut.isPending}>
                        <Save className="h-4 w-4 mr-2" /> Opslaan
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {strat.updated_at ? `Bijgewerkt ${new Date(strat.updated_at).toLocaleDateString('nl-NL')}` : ''}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
