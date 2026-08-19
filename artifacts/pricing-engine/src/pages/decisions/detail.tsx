import { useState } from "react";
import { useRoute, Link } from "wouter";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import {
  ArrowLeft, Check, X, Star, AlertTriangle, History, Eye, PlayCircle, Ban, ExternalLink,
} from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

async function apiFetch(path: string, options?: RequestInit) {
  const token = getAuthToken();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(options?.headers || {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  proposed: "bg-blue-100 text-blue-800",
  in_review: "bg-amber-100 text-amber-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  executed: "bg-emerald-600 text-white",
  cancelled: "bg-slate-200 text-slate-500",
};

const RISK_STYLE: Record<string, string> = {
  low: "bg-green-100 text-green-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-red-100 text-red-800",
};
const RISK_NL: Record<string, string> = { low: "Laag", medium: "Gemiddeld", high: "Hoog" };

function eur(v: number | null | undefined) {
  if (v == null) return <span className="text-muted-foreground italic">data unavailable</span>;
  return `€${Math.round(v).toLocaleString("nl-NL")}`;
}
function num(v: number | null | undefined) {
  if (v == null) return <span className="text-muted-foreground italic">data unavailable</span>;
  return Math.round(v).toLocaleString("nl-NL");
}

export default function BeslissingDetail() {
  const [, params] = useRoute("/beslissingen/:id");
  const id = params?.id;
  const { toast } = useToast();
  const qc = useQueryClient();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [approveScenarioId, setApproveScenarioId] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [expandedWhy, setExpandedWhy] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["decision", id],
    queryFn: () => apiFetch(`/api/decisions/${id}`),
    enabled: !!id,
  });

  const { data: history } = useQuery({
    queryKey: ["decision-history", id],
    queryFn: () => apiFetch(`/api/decisions/${id}/history`),
    enabled: !!id && showHistory,
  });

  const transition = useMutation({
    mutationFn: (payload: { to_status: string; note?: string; scenario_id?: number }) =>
      apiFetch(`/api/decisions/${id}/transition`, { method: "POST", body: JSON.stringify(payload) }),
    onSuccess: () => {
      toast({ title: "Status bijgewerkt" });
      qc.invalidateQueries({ queryKey: ["decision", id] });
      qc.invalidateQueries({ queryKey: ["decision-history", id] });
      qc.invalidateQueries({ queryKey: ["decisions"] });
      setRejectOpen(false);
      setRejectReason("");
    },
    onError: (e: any) => toast({ title: "Actie mislukt", description: String(e?.message || e), variant: "destructive" }),
  });

  if (isLoading || !data) {
    return (
      <div className="p-6 space-y-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}</div>
    );
  }

  const canReview = ["proposed", "in_review"].includes(data.status);
  const isCategory = data.entity_type === "category";
  const catCtx = data.category_context;
  const scenarios = [...(data.scenarios || [])].sort((a: any, b: any) => (b.is_recommended ? 1 : 0) - (a.is_recommended ? 1 : 0) || b.score - a.score);
  const recommended = scenarios.find((s: any) => s.is_recommended);

  return (
    <>
    <div className="p-6 space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <Link href="/beslissingen">
              <Button variant="ghost" size="sm" className="mb-2"><ArrowLeft className="h-4 w-4 mr-1" /> Terug</Button>
            </Link>
            <h1 className="text-2xl font-bold">{data.title}</h1>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <Badge variant="outline">{isCategory ? "Categorie" : "SKU"} · {data.entity_id}</Badge>
              <Badge className={STATUS_STYLE[data.status] || ""}>{data.status_nl}</Badge>
              <span className="text-sm text-muted-foreground">
                Voorgesteld door {data.proposed_by} ({data.ai_model_version}) op {data.run_date}
              </span>
              {data.reviewer && (
                <span className="text-sm text-muted-foreground">· Beoordeeld door {data.reviewer}</span>
              )}
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" size="sm" onClick={() => setShowHistory(!showHistory)}>
              <History className="h-4 w-4 mr-1" /> Historie
            </Button>
            {canReview && data.status === "proposed" && (
              <Button variant="outline" size="sm" onClick={() => transition.mutate({ to_status: "in_review" })}>
                <Eye className="h-4 w-4 mr-1" /> In review nemen
              </Button>
            )}
            {canReview && (
              <>
                <Button size="sm" className="bg-green-600 hover:bg-green-700"
                  onClick={() => transition.mutate({ to_status: "approved", scenario_id: approveScenarioId ?? undefined })}>
                  <Check className="h-4 w-4 mr-1" />
                  Goedkeuren{approveScenarioId && approveScenarioId !== recommended?.id ? " (gekozen alternatief)" : ""}
                </Button>
                <Button size="sm" variant="destructive" onClick={() => setRejectOpen(true)}>
                  <X className="h-4 w-4 mr-1" /> Afwijzen
                </Button>
                <Button size="sm" variant="outline" onClick={() => transition.mutate({ to_status: "cancelled", note: "Geannuleerd door reviewer" })}>
                  <Ban className="h-4 w-4 mr-1" /> Annuleren
                </Button>
              </>
            )}
            {data.status === "approved" && (
              <Button size="sm" onClick={() => transition.mutate({ to_status: "executed", note: "Gemarkeerd als uitgevoerd" })}>
                <PlayCircle className="h-4 w-4 mr-1" /> Markeer als uitgevoerd
              </Button>
            )}
          </div>
        </div>

        {data.summary && (
          <Card className="border-primary/40">
            <CardContent className="py-4 text-sm">{data.summary}</CardContent>
          </Card>
        )}

        {/* Categoriecontext — alleen voor categoriebeslissingen */}
        {isCategory && catCtx && (
          <Card data-testid="card-category-context">
            <CardHeader><CardTitle className="text-base">Categoriecontext — {catCtx.category}</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                <div>
                  <div className="text-xs text-muted-foreground">SKU's in categorie</div>
                  <div className="font-medium" data-testid="text-cat-sku-count">{num(catCtx.sku_count)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Omzet ({catCtx.horizon_days}d)</div>
                  <div className="font-medium" data-testid="text-cat-revenue">{eur(catCtx.total_revenue_30d)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Marge ({catCtx.horizon_days}d)</div>
                  <div className="font-medium" data-testid="text-cat-margin">{eur(catCtx.total_margin_30d)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Huismerkaandeel (SKU's)</div>
                  <div className="font-medium" data-testid="text-cat-pl-share">
                    {catCtx.private_label_share_skus != null
                      ? `${Math.round(catCtx.private_label_share_skus * 100)}% (${catCtx.private_label_sku_count} SKU's)`
                      : <span className="text-muted-foreground italic">data unavailable</span>}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Huismerkaandeel (omzet)</div>
                  <div className="font-medium">
                    {catCtx.private_label_share_revenue != null
                      ? `${Math.round(catCtx.private_label_share_revenue * 100)}%`
                      : <span className="text-muted-foreground italic">data unavailable</span>}
                  </div>
                </div>
              </div>
              {catCtx.subcategories?.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Subcategorieën</div>
                  <div className="flex flex-wrap gap-2">
                    {catCtx.subcategories.map((sc: any) => (
                      <Link
                        key={sc.name}
                        href={`/producten?category=${encodeURIComponent(catCtx.category)}&subcategory=${encodeURIComponent(sc.name)}`}
                      >
                        <Badge
                          variant="secondary"
                          className="cursor-pointer hover:bg-primary/15 hover:text-primary transition-colors"
                          data-testid={`link-subcategory-${sc.name}`}
                          title={`Bekijk SKU's in ${sc.name}`}
                        >
                          {sc.name} ({sc.sku_count}) <ExternalLink className="h-3 w-3 ml-1 inline" />
                        </Badge>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
              {catCtx.top_skus?.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Top-SKU's op omzet ({catCtx.horizon_days}d)</div>
                  <div className="border rounded-md overflow-hidden">
                    <table className="w-full text-xs" data-testid="table-top-skus">
                      <thead className="bg-muted/50 text-muted-foreground">
                        <tr>
                          <th className="text-left px-2 py-1.5 font-medium">SKU</th>
                          <th className="text-left px-2 py-1.5 font-medium">Naam</th>
                          <th className="text-right px-2 py-1.5 font-medium">Omzet</th>
                          <th className="text-right px-2 py-1.5 font-medium">Marge</th>
                          <th className="text-right px-2 py-1.5 font-medium">Units</th>
                        </tr>
                      </thead>
                      <tbody>
                        {catCtx.top_skus.map((t: any) => (
                          <tr key={t.sku_id} className="border-t hover:bg-muted/30">
                            <td className="px-2 py-1.5">
                              <Link href={`/producten/${encodeURIComponent(t.sku_id)}`} className="font-mono text-primary hover:underline" data-testid={`link-top-sku-${t.sku_id}`}>
                                {t.sku_id}
                              </Link>
                              {t.is_private_label && <Badge variant="secondary" className="ml-1 text-[9px] px-1 py-0">HM</Badge>}
                            </td>
                            <td className="px-2 py-1.5 max-w-[240px] truncate" title={t.product_name || undefined}>{t.product_name || "—"}</td>
                            <td className="px-2 py-1.5 text-right tabular-nums">{eur(t.revenue_30d)}</td>
                            <td className="px-2 py-1.5 text-right tabular-nums">{eur(t.margin_30d)}</td>
                            <td className="px-2 py-1.5 text-right tabular-nums">{num(t.units_30d)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              <div>
                <Link href={`/producten?category=${encodeURIComponent(catCtx.category)}&merktype=huismerk`}>
                  <Button variant="outline" size="sm" data-testid="link-pl-skus">
                    Bekijk huismerk-SKU's in {catCtx.category} <ExternalLink className="h-3.5 w-3.5 ml-1" />
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        )}

        {data.data_gaps?.length > 0 && (
          <Card className="border-amber-300 bg-amber-50/50">
            <CardContent className="py-4">
              <div className="flex items-center gap-2 font-medium text-amber-800 mb-1">
                <AlertTriangle className="h-4 w-4" /> Databeperkingen (§56)
              </div>
              <ul className="text-sm text-amber-800 list-disc pl-5">
                {data.data_gaps.map((g: string, i: number) => <li key={i}>{g}</li>)}
              </ul>
            </CardContent>
          </Card>
        )}

        {showHistory && history && (
          <Card>
            <CardHeader><CardTitle className="text-base">Statushistorie & reconstructie (§53)</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {history.events.map((e: any) => (
                <div key={e.id} className="text-sm border-l-2 border-primary/30 pl-3 py-1">
                  <span className="font-medium">{e.from_status ? `${e.from_status} → ` : ""}{e.to_status}</span>
                  {" — "}{e.actor} ({e.actor_type === "ai" ? "AI" : "mens"})
                  <span className="text-muted-foreground"> · {e.created_at?.replace("T", " ").slice(0, 16)}</span>
                  {e.note && <div className="text-muted-foreground">{e.note}</div>}
                </div>
              ))}
              <div className="text-xs text-muted-foreground pt-2">
                Op basis van {history.signal_snapshot?.length ?? 0} bevroren signalen — beslissing volledig reconstrueerbaar.
              </div>
            </CardContent>
          </Card>
        )}

        {/* Scenario-vergelijking */}
        <div>
          <h2 className="text-lg font-semibold mb-3">Scenario-vergelijking ({scenarios.length})</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {scenarios.map((s: any) => (
              <Card key={s.id} className={s.is_recommended ? "border-primary ring-1 ring-primary" : approveScenarioId === s.id ? "border-green-500 ring-1 ring-green-500" : ""}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2">
                      {s.is_recommended && <Star className="h-4 w-4 text-primary fill-primary" />}
                      {s.label}
                    </span>
                    <Badge className={RISK_STYLE[s.risk_level] || ""}>Risico: {RISK_NL[s.risk_level] || s.risk_level}</Badge>
                  </CardTitle>
                  {s.is_recommended && <div className="text-xs text-primary font-medium">AANBEVOLEN SCENARIO</div>}
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="text-muted-foreground">{s.description}</p>
                  <div className="grid grid-cols-3 gap-2">
                    <div><div className="text-xs text-muted-foreground">Units (30d)</div><div className="font-medium">{num(s.expected_units)}</div></div>
                    <div><div className="text-xs text-muted-foreground">Omzet</div><div className="font-medium">{eur(s.expected_revenue)}</div></div>
                    <div><div className="text-xs text-muted-foreground">Marge</div><div className="font-medium">{eur(s.expected_margin)}</div></div>
                  </div>
                  {isCategory && s.parameters && Object.keys(s.parameters).length > 0 && (
                    <div className="rounded-md bg-muted/50 p-2 text-xs space-y-1" data-testid={`params-scenario-${s.id}`}>
                      <div className="font-semibold">Scenario-parameters</div>
                      {s.parameters.discount_pct != null && (
                        <div><span className="font-medium">Korting:</span> {Math.round(s.parameters.discount_pct * 100)}%</div>
                      )}
                      {s.parameters.duration_days != null && (
                        <div><span className="font-medium">Duur:</span> {s.parameters.duration_days} dagen</div>
                      )}
                      {s.parameters.n_skus != null && (
                        <div><span className="font-medium">Aantal SKU's:</span> {num(s.parameters.n_skus)}</div>
                      )}
                      {s.parameters.pl_ratio_current != null && (
                        <div><span className="font-medium">Huidig huismerkaandeel:</span> {Math.round(s.parameters.pl_ratio_current * 100)}%</div>
                      )}
                      {Array.isArray(s.parameters.private_label_skus) && s.parameters.private_label_skus.length > 0 && (
                        <div>
                          <span className="font-medium">Huismerk-SKU's:</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {s.parameters.private_label_skus.map((sku: string) => (
                              <Link key={sku} href={`/producten/${encodeURIComponent(sku)}`}>
                                <Badge
                                  variant="outline"
                                  className="text-[10px] cursor-pointer hover:bg-primary/15 hover:text-primary transition-colors"
                                  data-testid={`link-pl-sku-${sku}`}
                                  title={`Bekijk productdetail van ${sku}`}
                                >
                                  {sku}
                                </Badge>
                              </Link>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  <div className="space-y-1 text-xs">
                    <div><span className="font-medium">Klant:</span> {s.customer_impact}</div>
                    <div><span className="font-medium">Basket:</span> {s.basket_impact}</div>
                    <div><span className="font-medium">Voorraad:</span> {s.stock_impact}</div>
                    <div><span className="font-medium">Strategisch:</span> {s.strategic_impact}</div>
                    {s.risk_notes && <div className="text-amber-700"><span className="font-medium">Risico:</span> {s.risk_notes}</div>}
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Confidence {Math.round((s.confidence || 0) * 100)}%</span>
                    <div className="flex gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setExpandedWhy(expandedWhy === s.id ? null : s.id)}>
                        WHY {expandedWhy === s.id ? "▲" : "▼"}
                      </Button>
                      {canReview && !s.is_recommended && (
                        <Button variant={approveScenarioId === s.id ? "default" : "outline"} size="sm"
                          onClick={() => setApproveScenarioId(approveScenarioId === s.id ? null : s.id)}>
                          {approveScenarioId === s.id ? "Gekozen" : "Kies dit"}
                        </Button>
                      )}
                    </div>
                  </div>

                  {expandedWhy === s.id && (
                    <div className="border-t pt-3 space-y-3 text-xs">
                      <div>
                        <div className="font-semibold mb-1">Factoren</div>
                        {s.why.factoren.length ? s.why.factoren.map((f: any, i: number) => (
                          <div key={i} className="flex justify-between gap-2">
                            <span className="truncate">{f.factor}</span>
                            <span className="text-muted-foreground shrink-0">{f.waarde != null ? Number(f.waarde).toFixed(2) : "—"} ({f.richting})</span>
                          </div>
                        )) : <span className="text-muted-foreground italic">data unavailable</span>}
                      </div>
                      <div>
                        <div className="font-semibold mb-1">Bronnen</div>
                        {s.why.bronnen.map((b: any, i: number) => (
                          <div key={i} className="text-muted-foreground">
                            {b.engine ? `${b.engine} · ${b.signal_type} (signaal #${b.signal_id})` : b.note}
                          </div>
                        ))}
                      </div>
                      <div>
                        <div className="font-semibold mb-1">Aannames</div>
                        {s.why.aannames.length ? (
                          <ul className="list-disc pl-4 text-muted-foreground">
                            {s.why.aannames.map((a: string, i: number) => <li key={i}>{a}</li>)}
                          </ul>
                        ) : <span className="text-muted-foreground italic">geen</span>}
                      </div>
                      <div>
                        <div className="font-semibold mb-1">Berekeningen</div>
                        {s.why.berekeningen.length ? s.why.berekeningen.map((c: any, i: number) => (
                          <div key={i} className="mb-1">
                            <div className="font-medium">{c.stap}</div>
                            <div className="text-muted-foreground">{c.formule} = {c.resultaat}</div>
                          </div>
                        )) : <span className="text-muted-foreground italic">data unavailable</span>}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* Onderliggende signalen */}
        <Card>
          <CardHeader><CardTitle className="text-base">Onderliggende signalen ({data.signal_snapshot?.length ?? 0})</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {(data.signal_snapshot || []).map((s: any, i: number) => (
              <div key={i} className="text-sm border rounded-md p-2 flex items-start justify-between gap-3">
                <div>
                  <span className="font-medium">{s.engine} · {s.signal_type}</span>
                  <p className="text-muted-foreground text-xs mt-0.5">{s.explanation}</p>
                </div>
                <Badge variant="outline" className="shrink-0">{s.severity}</Badge>
              </div>
            ))}
            {!data.signal_snapshot?.length && <span className="text-muted-foreground text-sm italic">data unavailable</span>}
          </CardContent>
        </Card>
      </div>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Beslissing afwijzen</DialogTitle></DialogHeader>
          <Textarea placeholder="Reden voor afwijzing (verplicht)…" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)}>Annuleren</Button>
            <Button variant="destructive" disabled={!rejectReason.trim() || transition.isPending}
              onClick={() => transition.mutate({ to_status: "rejected", note: rejectReason })}>
              Afwijzen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
