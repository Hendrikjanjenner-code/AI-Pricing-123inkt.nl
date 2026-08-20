import { useListSubstitutions } from "@workspace/api-client-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRightLeft, TrendingUp, DollarSign } from "lucide-react";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";

export default function Substitutiemonitor() {
  // Globale filtercontext (hiërarchie + merk) — server-side subtree-expansie.
  const filters = useGlobalFilters();
  const { data, isLoading } = useListSubstitutions({
    hierarchy_node_ids:
      filters.hierarchy.length > 0
        ? filters.hierarchy.map((n) => n.id).join(",")
        : undefined,
    brands: filters.brands.length > 0 ? filters.brands.join(",") : undefined,
  });

  const fmtBedrag = (val: number | null | undefined) =>
    val != null ? new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(val) : '-';

  const fmtPct = (val: number | null | undefined) =>
    val != null ? `${(val * 100).toFixed(1)}%` : '-';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Substitutieportfolio monitor</h1>
        <p className="text-muted-foreground mt-1">Beheer A-merk vs. huismerk prijskloven en margemogelijkheden.</p>
      </div>
      <GlobalFilterBar />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <ArrowRightLeft className="w-4 h-4 mr-2" /> Actieve paren
          </div>
          <div className="text-3xl font-bold">{data?.length || 0}</div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <DollarSign className="w-4 h-4 mr-2" /> Gem. prijskloof
          </div>
          <div className="text-3xl font-bold text-primary">
            {data?.length ? fmtPct(data.reduce((acc, curr) => acc + (curr.price_gap_pct || 0), 0) / data.length) : '-'}
          </div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <TrendingUp className="w-4 h-4 mr-2 text-emerald-500" /> Gem. kansscore
          </div>
          <div className="text-3xl font-bold text-emerald-600">
            {data?.length ? (data.reduce((acc, curr) => acc + (curr.opportunity_score || 0), 0) / data.length).toFixed(1) : '-'} / 10
          </div>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead colSpan={2} className="text-center border-r bg-muted/20">A-merk</TableHead>
              <TableHead colSpan={2} className="text-center border-r bg-muted/20">Huismerk</TableHead>
              <TableHead colSpan={4} className="text-center bg-muted/20">Statistieken</TableHead>
            </TableRow>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead className="border-r">Prijs</TableHead>
              <TableHead>SKU</TableHead>
              <TableHead className="border-r">Prijs</TableHead>
              <TableHead className="text-right">Prijskloof</TableHead>
              <TableHead className="text-right">Verkoopverschuiving</TableHead>
              <TableHead className="text-right">Margeverschuiving</TableHead>
              <TableHead className="text-center">Kansscore</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {[1,2,3,4,5,6,7,8].map(j => <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>)}
                </TableRow>
              ))
            ) : data?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-32 text-center text-muted-foreground">
                  Geen substitutieparen gevonden.
                </TableCell>
              </TableRow>
            ) : data?.map((pair) => (
              <TableRow key={pair.id}>
                <TableCell>
                  <div className="font-mono text-xs">{pair.a_brand_sku}</div>
                  <div className="text-xs text-muted-foreground truncate max-w-[150px]" title={pair.a_brand_name}>{pair.a_brand_name}</div>
                </TableCell>
                <TableCell className="border-r tabular-nums">{fmtBedrag(pair.a_brand_price)}</TableCell>
                <TableCell>
                  <div className="font-mono text-xs text-primary">{pair.private_label_sku}</div>
                  <div className="text-xs text-muted-foreground truncate max-w-[150px]" title={pair.private_label_name}>{pair.private_label_name}</div>
                </TableCell>
                <TableCell className="border-r tabular-nums font-medium text-primary">{fmtBedrag(pair.private_label_price)}</TableCell>
                <TableCell className="text-right tabular-nums">{fmtPct(pair.price_gap_pct)}</TableCell>
                <TableCell className={`text-right tabular-nums ${(pair.sales_shift_pct || 0) > 0 ? 'text-emerald-600' : ''}`}>
                  {(pair.sales_shift_pct || 0) > 0 ? '+' : ''}{fmtPct(pair.sales_shift_pct)}
                </TableCell>
                <TableCell className={`text-right tabular-nums ${(pair.margin_shift_pct || 0) > 0 ? 'text-emerald-600' : ''}`}>
                  {(pair.margin_shift_pct || 0) > 0 ? '+' : ''}{fmtPct(pair.margin_shift_pct)}
                </TableCell>
                <TableCell className="text-center">
                  <Badge variant={(pair.opportunity_score || 0) >= 8 ? "default" : "secondary"}>
                    {pair.opportunity_score?.toFixed(1)}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
