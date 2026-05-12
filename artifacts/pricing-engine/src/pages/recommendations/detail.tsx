import { useRoute, Link } from "wouter";
import { useGetRecommendation, useApproveRecommendation, useRejectRecommendation, useOverrideRecommendation } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { ArrowLeft, CheckCircle, XCircle, AlertTriangle, TrendingUp, TrendingDown, Clock } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const REDEN_LABELS: Record<string, string> = {
  PRIMARY_COMPETITOR_PRESSURE: "Primaire concurrentiedruk",
  IGNORED_LOW_CSS: "Genegeerd (lage CSS-score)",
  IGNORED_LOW_CSRS: "Genegeerd (lage CSRS-score)",
  PRIVATE_LABEL_MARGIN_OPPORTUNITY: "Huismerkmarge-kans",
  INTERNAL_SUBSTITUTION_HIGH: "Hoge interne substitutie",
  PORTFOLIO_MARGIN_PROTECTION: "Portfoliobescherming marge",
  ELASTICITY_LOW_CONFIDENCE: "Elasticiteit laag betrouwbaar",
  COMPETITION_SIGNAL_WEAK: "Zwak concurrentiesignaal",
  WATCH_ONLY_LOW_STOCK_RELIABILITY: "Alleen bewaken (lage voorraadbetrouwbaarheid)",
  MIN_PRICE_GUARDRAIL_APPLIED: "Minimumprijs toegepast",
  MAX_PRICE_GUARDRAIL_APPLIED: "Maximumprijs toegepast",
  PRICE_BLOCKED_BY_SAFETY_RULES: "Prijs geblokkeerd door veiligheidsregels",
  LOW_CONFIDENCE_FLAG: "Lage betrouwbaarheidsvlag",
};

const STRATEGIE_LABELS: Record<string, string> = {
  SUBSTITUTION_PORTFOLIO: "Substitutieportfolio",
  COMPETITOR_INDEX: "Concurrentie-index",
  MARGIN_OPTIMIZATION: "Margeoptimalisatie",
  STOCK_CLEARANCE: "Voorraadopruiming",
  BASKET_BUILDER: "Winkelmandbouwer",
  VOLUME_DISCOUNT: "Volumekorting",
  REPEAT_PURCHASE: "Herhalingsaankoop",
  LOW_VELOCITY: "Laag volume",
  PRIVATE_LABEL_PUSH: "Huismerk push",
  PORTFOLIO_MARGIN_OPTIMIZATION: "Portfolio margeopt.",
  TRAFFIC_TO_MARGIN_SWITCH: "Traffic → marge",
};

export default function PrijsadviesDetail() {
  const [, params] = useRoute("/prijsadviezen/:id");
  const id = Number(params?.id);
  const { data, isLoading } = useGetRecommendation(id, { query: { enabled: !!id } });
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const goedkeurenMut = useApproveRecommendation();
  const afwijzenMut = useRejectRecommendation();
  const overschrijvenMut = useOverrideRecommendation();
  const [overschrijfPrijs, setOverschrijfPrijs] = useState("");
  const [overschrijfOpen, setOverschrijfOpen] = useState(false);

  if (isLoading) return <div className="p-8"><Skeleton className="h-96 w-full" /></div>;
  if (!data) return <div>Advies niet gevonden</div>;

  const { recommendation: rec, product, competitor_prices, audit_trail, safety_rules_applied } = data;

  const handleGoedkeuren = async () => {
    try {
      await goedkeurenMut.mutateAsync({ id });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      toast({ title: "Advies goedgekeurd" });
    } catch { toast({ title: "Fout", variant: "destructive" }); }
  };

  const handleAfwijzen = async () => {
    try {
      await afwijzenMut.mutateAsync({ id, data: { reason: "Handmatig afgewezen" } });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      toast({ title: "Advies afgewezen" });
    } catch { toast({ title: "Fout", variant: "destructive" }); }
  };

  const handleOverschrijven = async () => {
    try {
      await overschrijvenMut.mutateAsync({ id, data: { override_price: Number(overschrijfPrijs), reason: "Handmatige overschrijving" } });
      queryClient.invalidateQueries({ queryKey: ["/api/recommendations"] });
      setOverschrijfOpen(false);
      toast({ title: "Prijs overschreven" });
    } catch { toast({ title: "Fout", variant: "destructive" }); }
  };

  const fmtBedrag = (v: number | null | undefined) =>
    v != null ? new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(v) : '-';
  const fmtPct = (v: number | null | undefined) =>
    v != null ? `${(v * 100).toFixed(1)}%` : '-';

  const statusLabel = (s: string) =>
    s === 'approved' ? 'Goedgekeurd' : s === 'rejected' ? 'Afgewezen' : s === 'overridden' ? 'Overschreven' : s;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/prijsadviezen">
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
              <Button variant="outline" className="text-destructive border-destructive/20 hover:bg-destructive/10"
                onClick={handleAfwijzen} disabled={afwijzenMut.isPending}>
                <XCircle className="mr-2 h-4 w-4" /> Afwijzen
              </Button>
              <Dialog open={overschrijfOpen} onOpenChange={setOverschrijfOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline">Prijs overschrijven</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader><DialogTitle>Prijs overschrijven</DialogTitle></DialogHeader>
                  <div className="py-4 space-y-4">
                    <div className="space-y-2">
                      <Label>Nieuwe prijs (€)</Label>
                      <Input type="number" step="0.01" value={overschrijfPrijs} onChange={e => setOverschrijfPrijs(e.target.value)} />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setOverschrijfOpen(false)}>Annuleren</Button>
                    <Button onClick={handleOverschrijven} disabled={overschrijvenMut.isPending || !overschrijfPrijs}>Opslaan</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
              <Button className="bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={handleGoedkeuren} disabled={goedkeurenMut.isPending}>
                <CheckCircle className="mr-2 h-4 w-4" /> Goedkeuren
              </Button>
            </>
          ) : (
            <Badge className="text-lg px-4 py-1 uppercase tracking-wider" variant="outline">
              {statusLabel(rec.approval_status || "")}
            </Badge>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="col-span-1 md:col-span-3">
          <CardHeader><CardTitle>Prijsadvies</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-8">
              <div>
                <div className="text-sm font-medium text-muted-foreground mb-1">Huidige prijs</div>
                <div className="text-3xl font-bold">{fmtBedrag(rec.current_price)}</div>
              </div>
              <div>
                <div className="text-sm font-medium text-muted-foreground mb-1">Geadviseerde prijs</div>
                <div className="text-3xl font-bold text-primary">{fmtBedrag(rec.recommended_price)}</div>
              </div>
              <div>
                <div className="text-sm font-medium text-muted-foreground mb-1">Verwacht effect</div>
                <div className="flex items-center gap-2">
                  <div className={`text-3xl font-bold ${(rec.recommended_change_pct || 0) > 0 ? 'text-emerald-600' : 'text-destructive'}`}>
                    {fmtPct(rec.recommended_change_pct)}
                  </div>
                  {(rec.recommended_change_pct || 0) > 0
                    ? <TrendingUp className="h-6 w-6 text-emerald-600" />
                    : <TrendingDown className="h-6 w-6 text-destructive" />}
                </div>
              </div>
            </div>
            <div className="mt-8 grid grid-cols-4 gap-4 pt-6 border-t">
              <div>
                <div className="text-xs text-muted-foreground">Verwachte margeverbetering</div>
                <div className="font-semibold text-emerald-600">+{fmtBedrag(rec.expected_margin_uplift)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Verwachte omzet</div>
                <div className="font-semibold">{fmtBedrag(rec.expected_revenue)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Verwachte eenheden</div>
                <div className="font-semibold">{rec.expected_units}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Modelbetrouwbaarheid</div>
                <div className="font-semibold">{fmtPct(rec.confidence_score)}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Strategie & regels</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Toegepaste strategie</div>
              <Badge variant="secondary">
                {STRATEGIE_LABELS[rec.strategy_type || ""] || rec.strategy_type?.replace(/_/g, ' ')}
              </Badge>
            </div>
            {rec.reason_code && (
              <div>
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Redencode</div>
                <div className="text-sm text-muted-foreground bg-muted/50 p-2 rounded-md">
                  {REDEN_LABELS[rec.reason_code] || rec.reason_code}
                </div>
              </div>
            )}
            {safety_rules_applied && safety_rules_applied.length > 0 && (
              <div>
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Veiligheidschecks</div>
                <div className="space-y-2">
                  {safety_rules_applied.map((rule, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm bg-muted/50 p-2 rounded-md">
                      <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                      <span>{REDEN_LABELS[rule] || rule}</span>
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
            <CardTitle>Concurrentielandschap</CardTitle>
            <CardDescription>Actuele prijzen bij gevolgde concurrenten</CardDescription>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={competitor_prices || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="competitor_name" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis fontSize={12} tickLine={false} axisLine={false} domain={['auto', 'auto']} tickFormatter={(v) => `€${v}`} />
                <Tooltip formatter={(value: number) => [`€${value}`, 'Prijs']} cursor={{fill: 'var(--muted)'}} />
                <Bar dataKey="price" fill="var(--chart-2)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Auditlog</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-4">
              {audit_trail?.length === 0 && (
                <p className="text-sm text-muted-foreground">Geen acties geregistreerd.</p>
              )}
              {audit_trail?.map((entry) => (
                <div key={entry.id} className="flex items-start gap-4">
                  <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center shrink-0">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">
                      {entry.action.replace(/_/g, ' ')}
                      {entry.performed_by && <span className="text-muted-foreground font-normal"> door {entry.performed_by}</span>}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {new Date(entry.timestamp).toLocaleString('nl-NL')}
                    </div>
                    {entry.details && (
                      <div className="text-sm mt-1 text-muted-foreground bg-muted/50 p-2 rounded-md">{entry.details}</div>
                    )}
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
