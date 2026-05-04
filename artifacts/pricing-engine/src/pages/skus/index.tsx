import { useState } from "react";
import { Link } from "wouter";
import { useListProducts } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, ChevronRight } from "lucide-react";

export default function Skus() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("all");

  const { data, isLoading } = useListProducts({
    params: {
      page,
      page_size: 50,
      search: search || null,
      category: category !== "all" ? category : null,
    }
  });

  const formatCurrency = (val: number | null | undefined) => 
    val != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' }).format(val) : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">SKU Management</h1>
      </div>

      <div className="flex items-center gap-4 bg-card p-4 border rounded-md">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input 
            placeholder="Search SKU ID, Name, or Brand..." 
            className="pl-9 bg-background" 
            value={search}
            onChange={e => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="w-64">
          <Select value={category} onValueChange={(v) => { setCategory(v); setPage(1); }}>
            <SelectTrigger className="bg-background">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              <SelectItem value="Ink & Toner">Ink & Toner</SelectItem>
              <SelectItem value="Office Supplies">Office Supplies</SelectItem>
              <SelectItem value="Electronics">Electronics</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU ID</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Brand</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Strategy</TableHead>
              <TableHead>Lifecycle</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead className="text-right">Current Price</TableHead>
              <TableHead className="text-center">Data Quality</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-8 mx-auto" /></TableCell>
                  <TableCell></TableCell>
                </TableRow>
              ))
            ) : data?.items?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} className="h-32 text-center text-muted-foreground">
                  No SKUs found.
                </TableCell>
              </TableRow>
            ) : data?.items?.map((sku) => (
              <TableRow key={sku.sku_id} className="group cursor-pointer hover:bg-muted/50">
                <TableCell className="font-mono text-xs">{sku.sku_id}</TableCell>
                <TableCell className="font-medium max-w-[200px] truncate" title={sku.product_name}>
                  {sku.product_name}
                </TableCell>
                <TableCell className="text-muted-foreground">{sku.brand}</TableCell>
                <TableCell>{sku.category}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-[10px] font-normal">
                    {sku.strategy_type?.replace(/_/g, ' ')}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary" className="text-[10px] font-normal uppercase">
                    {sku.lifecycle_status?.replace(/_/g, ' ')}
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">{formatCurrency(sku.cost_price)}</TableCell>
                <TableCell className="text-right tabular-nums font-medium">{formatCurrency(sku.current_price)}</TableCell>
                <TableCell className="text-center">
                  <div className={`text-sm font-semibold ${(sku.data_quality_score || 0) >= 80 ? 'text-emerald-600' : 'text-amber-600'}`}>
                    {sku.data_quality_score}%
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <Link href={`/skus/${sku.sku_id}`}>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground group-hover:text-foreground">
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div>Showing {(data.page - 1) * data.page_size + 1} to {Math.min(data.page * data.page_size, data.total)} of {data.total} entries</div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</Button>
            <Button variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}
    </div>
  );
}
