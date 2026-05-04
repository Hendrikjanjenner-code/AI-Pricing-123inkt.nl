import { useListSubstitutions } from "@workspace/api-client-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRightLeft, TrendingUp, DollarSign } from "lucide-react";

export default function Substitutions() {
  const { data, isLoading } = useListSubstitutions();

  const formatCurrency = (val: number | null | undefined) => 
    val != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' }).format(val) : '-';
  
  const formatPct = (val: number | null | undefined) => 
    val != null ? `${(val * 100).toFixed(1)}%` : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Substitution Portfolio Monitor</h1>
          <p className="text-muted-foreground mt-1">Track A-Brand vs Private Label pricing gaps and margin opportunities.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <ArrowRightLeft className="w-4 h-4 mr-2" /> Active Pairs
          </div>
          <div className="text-3xl font-bold">{data?.length || 0}</div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <DollarSign className="w-4 h-4 mr-2" /> Avg Price Gap
          </div>
          <div className="text-3xl font-bold text-primary">
            {data?.length ? formatPct(data.reduce((acc, curr) => acc + (curr.price_gap_pct || 0), 0) / data.length) : '-'}
          </div>
        </div>
        <div className="border rounded-md p-4 bg-card">
          <div className="text-sm font-medium text-muted-foreground flex items-center mb-2">
            <TrendingUp className="w-4 h-4 mr-2 text-emerald-500" /> Avg Opportunity Score
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
              <TableHead colSpan={2} className="text-center border-r bg-muted/20">A-Brand</TableHead>
              <TableHead colSpan={2} className="text-center border-r bg-muted/20">Private Label</TableHead>
              <TableHead colSpan={4} className="text-center bg-muted/20">Metrics</TableHead>
            </TableRow>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead className="border-r">Price</TableHead>
              <TableHead>SKU</TableHead>
              <TableHead className="border-r">Price</TableHead>
              <TableHead className="text-right">Price Gap</TableHead>
              <TableHead className="text-right">Sales Shift</TableHead>
              <TableHead className="text-right">Margin Shift</TableHead>
              <TableHead className="text-center">Opp Score</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell className="border-r"><Skeleton className="h-4 w-12" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell className="border-r"><Skeleton className="h-4 w-12" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-6 w-8 mx-auto" /></TableCell>
                </TableRow>
              ))
            ) : data?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-32 text-center text-muted-foreground">
                  No substitution pairs found.
                </TableCell>
              </TableRow>
            ) : data?.map((pair) => (
              <TableRow key={pair.id}>
                <TableCell>
                  <div className="font-mono text-xs">{pair.a_brand_sku}</div>
                  <div className="text-xs text-muted-foreground truncate max-w-[150px]" title={pair.a_brand_name}>{pair.a_brand_name}</div>
                </TableCell>
                <TableCell className="border-r tabular-nums">{formatCurrency(pair.a_brand_price)}</TableCell>
                <TableCell>
                  <div className="font-mono text-xs text-primary">{pair.private_label_sku}</div>
                  <div className="text-xs text-muted-foreground truncate max-w-[150px]" title={pair.private_label_name}>{pair.private_label_name}</div>
                </TableCell>
                <TableCell className="border-r tabular-nums font-medium text-primary">{formatCurrency(pair.private_label_price)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatPct(pair.price_gap_pct)}</TableCell>
                <TableCell className={`text-right tabular-nums ${(pair.sales_shift_pct || 0) > 0 ? 'text-emerald-600' : ''}`}>
                  {(pair.sales_shift_pct || 0) > 0 ? '+' : ''}{formatPct(pair.sales_shift_pct)}
                </TableCell>
                <TableCell className={`text-right tabular-nums ${(pair.margin_shift_pct || 0) > 0 ? 'text-emerald-600' : ''}`}>
                  {(pair.margin_shift_pct || 0) > 0 ? '+' : ''}{formatPct(pair.margin_shift_pct)}
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
