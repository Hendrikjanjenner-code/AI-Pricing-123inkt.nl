import { useState } from "react";
import { Link } from "wouter";
import { useListRecommendations, useApproveRecommendation, useRejectRecommendation, useBulkApproveRecommendations } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { format } from "date-fns";
import { Search, CheckCircle, XCircle, AlertCircle, FileSearch, ArrowRight } from "lucide-react";

export default function Recommendations() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string>("pending");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const { data, isLoading } = useListRecommendations({
    params: {
      page,
      page_size: 50,
      search: search || null,
      approval_status: status !== "all" ? status : null,
    }
  });

  const queryClient = useQueryClient();
  const { toast } = useToast();

  const approveMut = useApproveRecommendation();
  const rejectMut = useRejectRecommendation();
  const bulkApproveMut = useBulkApproveRecommendations();

  const handleApprove = async (id: number) => {
    try {
      await approveMut.mutateAsync({ id });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      toast({ title: "Approved recommendation" });
    } catch (err) {
      toast({ title: "Error", variant: "destructive" });
    }
  };

  const handleReject = async (id: number) => {
    try {
      await rejectMut.mutateAsync({ id, data: { reason: "Manual rejection" } });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      toast({ title: "Rejected recommendation" });
    } catch (err) {
      toast({ title: "Error", variant: "destructive" });
    }
  };

  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return;
    try {
      await bulkApproveMut.mutateAsync({ data: { ids: Array.from(selectedIds) } });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      setSelectedIds(new Set());
      toast({ title: `Approved ${selectedIds.size} recommendations` });
    } catch (err) {
      toast({ title: "Error", variant: "destructive" });
    }
  };

  const toggleSelectAll = () => {
    if (!data?.items) return;
    if (selectedIds.size === data.items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(data.items.map(i => i.id)));
    }
  };

  const toggleSelect = (id: number) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const formatCurrency = (val: number | null | undefined) => 
    val != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' }).format(val) : '-';
  
  const formatPct = (val: number | null | undefined) => 
    val != null ? `${(val * 100).toFixed(1)}%` : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Pricing Recommendations</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleBulkApprove} disabled={selectedIds.size === 0 || bulkApproveMut.isPending}>
            <CheckCircle className="mr-2 h-4 w-4" /> Bulk Approve ({selectedIds.size})
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-4 bg-card p-4 border rounded-md">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input 
            placeholder="Search SKU or product..." 
            className="pl-9 bg-background" 
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="w-48">
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="bg-background">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">
                <Checkbox 
                  checked={data?.items?.length ? selectedIds.size === data.items.length : false}
                  onCheckedChange={toggleSelectAll}
                />
              </TableHead>
              <TableHead>SKU</TableHead>
              <TableHead>Product</TableHead>
              <TableHead>Strategy</TableHead>
              <TableHead className="text-right">Current</TableHead>
              <TableHead className="text-right">Recommended</TableHead>
              <TableHead className="text-right">Change</TableHead>
              <TableHead className="text-right">Margin Uplift</TableHead>
              <TableHead className="text-center">Conf.</TableHead>
              <TableHead className="text-center">Safety</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton className="h-4 w-4" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-8 mx-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16 mx-auto" /></TableCell>
                  <TableCell><Skeleton className="h-8 w-24 ml-auto" /></TableCell>
                </TableRow>
              ))
            ) : data?.items?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={11} className="h-32 text-center text-muted-foreground">
                  No recommendations found.
                </TableCell>
              </TableRow>
            ) : data?.items?.map((rec) => (
              <TableRow key={rec.id} className="group cursor-pointer hover:bg-muted/50">
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox 
                    checked={selectedIds.has(rec.id)}
                    onCheckedChange={() => toggleSelect(rec.id)}
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">{rec.sku_id}</TableCell>
                <TableCell className="font-medium max-w-[200px] truncate" title={rec.product_name}>
                  {rec.product_name}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-[10px] font-normal">
                    {rec.strategy_type?.replace(/_/g, ' ')}
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">{formatCurrency(rec.current_price)}</TableCell>
                <TableCell className="text-right tabular-nums font-medium text-primary">{formatCurrency(rec.recommended_price)}</TableCell>
                <TableCell className={`text-right tabular-nums ${(rec.recommended_change_pct || 0) > 0 ? 'text-emerald-600' : 'text-destructive'}`}>
                  {formatPct(rec.recommended_change_pct)}
                </TableCell>
                <TableCell className="text-right tabular-nums text-emerald-600">{formatCurrency(rec.expected_margin_uplift)}</TableCell>
                <TableCell className="text-center">
                  <Badge variant={rec.confidence_score && rec.confidence_score > 0.8 ? "secondary" : "outline"}>
                    {formatPct(rec.confidence_score)}
                  </Badge>
                </TableCell>
                <TableCell className="text-center">
                  {rec.safety_status === 'ok' && <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200">OK</Badge>}
                  {rec.safety_status === 'warning' && <Badge variant="outline" className="text-amber-600 border-amber-200 bg-amber-50">WARN</Badge>}
                  {rec.safety_status === 'blocked' && <Badge variant="destructive">BLOCKED</Badge>}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                    <Link href={`/recommendations/${rec.id}`}>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
                        <FileSearch className="h-4 w-4" />
                      </Button>
                    </Link>
                    {rec.approval_status === 'pending' && (
                      <>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50" onClick={() => handleApprove(rec.id)}>
                          <CheckCircle className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => handleReject(rec.id)}>
                          <XCircle className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                    {rec.approval_status !== 'pending' && (
                      <Badge variant="outline" className="uppercase text-[10px] ml-2">{rec.approval_status}</Badge>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      
      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div>Showing {(data.page - 1) * data.page_size + 1} to Math.min(data.page * data.page_size, data.total) of {data.total} entries</div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</Button>
            <Button variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}
    </div>
  );
}
