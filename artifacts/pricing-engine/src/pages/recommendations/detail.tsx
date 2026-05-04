import { useRoute, Link } from "wouter";
import { useGetRecommendation, useApproveRecommendation, useRejectRecommendation, useOverrideRecommendation } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { ArrowLeft, CheckCircle, XCircle, AlertTriangle, TrendingUp, TrendingDown, Clock } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, LineChart, Line } from "recharts";
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function RecommendationDetail() {
  const [, params] = useRoute("/recommendations/:id");
  const id = Number(params?.id);
  const { data, isLoading } = useGetRecommendation(id, { query: { enabled: !!id } });
  const queryClient = useQueryClient();
  const { toast } = useToast();
  
  const approveMut = useApproveRecommendation();
  const rejectMut = useRejectRecommendation();
  const overrideMut = useOverrideRecommendation();

  const [overridePrice, setOverridePrice] = useState("");
  const [overrideOpen, setOverrideOpen] = useState(false);

  if (isLoading) return <div className="p-8"><Skeleton className="h-96 w-full" /></div>;
  if (!data) return <div>Recommendation not found</div>;

  const { recommendation: rec, product, competitor_prices, audit_trail, safety_rules_applied } = data;

  const handleApprove = async () => {
    try {
      await approveMut.mutateAsync({ id });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      toast({ title: "Approved" });
    } catch (err) {
      toast({ title: "Error", variant: "destructive" });
    }
  };

  const handleReject = async () => {
    try {
      await rejectMut.mutateAsync({ id, data: { reason: "Manual rejection" } });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      toast({ title: "Rejected" });
    } catch (err) {
      toast({ title: "Error", variant: "destructive" });
    }
  };

  const handleOverride = async () => {
    try {
      await overrideMut.mutateAsync({ id, data: { override_price: Number(overridePrice), reason: "Manual override" } });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      setOverrideOpen(false);
      toast({ title: "Overridden" });
    } catch (err) {
      toast({ title: "Error", variant: "destructive" });
    }
  };

  const formatCurrency = (val: number | null | undefined) => 
    val != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' }).format(val) : '-';
  
  const formatPct = (val: number | null | undefined) => 
    val != null ? `${(val * 100).toFixed(1)}%` : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/recommendations">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{rec.product_name}</h1>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
            <span className="font-mono">{rec.sku_id}</span>
            <span>•</span>
            <span>{product.brand}</span>
            <span>•</span>
            <span>{product.category}</span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {rec.approval_status === 'pending' ? (
            <>
              <Button variant="outline" className="text-destructive border-destructive/20 hover:bg-destructive/10" onClick={handleReject} disabled={rejectMut.isPending}>
                <XCircle className="mr-2 h-4 w-4" /> Reject
              </Button>
              <Dialog open={overrideOpen} onOpenChange={setOverrideOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline">Override</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Override Price</DialogTitle>
                  </DialogHeader>
                  <div className="py-4 space-y-4">
                    <div className="space-y-2">
                      <Label>New Price (€)</Label>
                      <Input type="number" step="0.01" value={overridePrice} onChange={e => setOverridePrice(e.target.value)} />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setOverrideOpen(false)}>Cancel</Button>
                    <Button onClick={handleOverride} disabled={overrideMut.isPending || !overridePrice}>Submit</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
              <Button className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={handleApprove} disabled={approveMut.isPending}>
                <CheckCircle className="mr-2 h-4 w-4" /> Approve
              </Button>
            </>
          ) : (
            <Badge className="text-lg px-4 py-1 uppercase tracking-wider" variant="outline">
              {rec.approval_status}
            </Badge>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="col-span-1 md:col-span-3">
          <CardHeader>
            <CardTitle>Pricing Recommendation</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-8">
              <div>
                <div className="text-sm font-medium text-muted-foreground mb-1">Current Price</div>
                <div className="text-3xl font-bold">{formatCurrency(rec.current_price)}</div>
              </div>
              <div>
                <div className="text-sm font-medium text-muted-foreground mb-1">Recommended</div>
                <div className="text-3xl font-bold text-primary">{formatCurrency(rec.recommended_price)}</div>
              </div>
              <div>
                <div className="text-sm font-medium text-muted-foreground mb-1">Impact</div>
                <div className="flex items-center gap-2">
                  <div className={`text-3xl font-bold ${(rec.recommended_change_pct || 0) > 0 ? 'text-emerald-600' : 'text-destructive'}`}>
                    {formatPct(rec.recommended_change_pct)}
                  </div>
                  {(rec.recommended_change_pct || 0) > 0 ? <TrendingUp className="h-6 w-6 text-emerald-600" /> : <TrendingDown className="h-6 w-6 text-destructive" />}
                </div>
              </div>
            </div>
            
            <div className="mt-8 grid grid-cols-4 gap-4 pt-6 border-t">
              <div>
                <div className="text-xs text-muted-foreground">Expected Margin</div>
                <div className="font-semibold text-emerald-600">+{formatCurrency(rec.expected_margin_uplift)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Expected Revenue</div>
                <div className="font-semibold">{formatCurrency(rec.expected_revenue)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Expected Units</div>
                <div className="font-semibold">{rec.expected_units}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Model Confidence</div>
                <div className="font-semibold">{formatPct(rec.confidence_score)}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Strategy & Rules</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Strategy Applied</div>
              <Badge variant="secondary">{rec.strategy_type?.replace(/_/g, ' ')}</Badge>
            </div>
            {safety_rules_applied && safety_rules_applied.length > 0 && (
              <div>
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Safety Checks</div>
                <div className="space-y-2">
                  {safety_rules_applied.map((rule, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm bg-muted/50 p-2 rounded-md">
                      <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                      <span>{rule}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Competitor Landscape</CardTitle>
            <CardDescription>Current prices across tracked competitors</CardDescription>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={competitor_prices || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="competitor_name" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis fontSize={12} tickLine={false} axisLine={false} domain={['auto', 'auto']} tickFormatter={(v) => `€${v}`} />
                <Tooltip formatter={(value: number) => [`€${value}`, 'Price']} cursor={{fill: 'var(--muted)'}} />
                <Bar dataKey="price" fill="var(--chart-2)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Audit Trail</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {audit_trail?.map((entry) => (
                <div key={entry.id} className="flex items-start gap-4">
                  <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center shrink-0">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">
                      {entry.action.replace(/_/g, ' ')}
                      {entry.performed_by && <span className="text-muted-foreground font-normal"> by {entry.performed_by}</span>}
                    </div>
                    <div className="text-xs text-muted-foreground">{new Date(entry.timestamp).toLocaleString()}</div>
                    {entry.details && <div className="text-sm mt-1 text-muted-foreground bg-muted/50 p-2 rounded-md">{entry.details}</div>}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
