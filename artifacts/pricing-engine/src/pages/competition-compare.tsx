import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useSearch } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowLeft, X, GitCompareArrows } from "lucide-react";
import { useShopId } from "@/hooks/use-shop-id";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => {
    if (!r.ok) throw new Error(`API-fout (${r.status})`);
    return r.json();
  });
}

function fmtRange(min: any, max: any) {
  if (min == null && max == null) return null;
  const f = (v: any) => Number(v).toLocaleString("nl-NL");
  if (min != null && max != null) return `${f(min)} – ${f(max)}`;
  return min != null ? `${f(min)}+` : `t/m ${f(max)}`;
}

function Cell({ children }: { children: any }) {
  const empty = children == null || children === "";
  return (
    <td className="py-2 px-3 border-b align-top text-sm">
      {empty ? <span className="italic text-muted-foreground">Onbekend</span> : children}
    </td>
  );
}

export default function CompetitionCompare() {
  const shopId = useShopId();
  const search = useSearch();
  const initial = useMemo(() => {
    const p = new URLSearchParams(search);
    return (p.get("names") || "").split(",").map(s => s.trim()).filter(Boolean);
  }, [search]);
  const [selected, setSelected] = useState<string[]>(initial);

  const { data: allComps } = useQuery({
    queryKey: ["competition-competitors-all", shopId],
    queryFn: () => {
      const p = new URLSearchParams({ page_size: "200" });
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      return apiFetch(`/api/competition/competitors?${p}`);
    },
  });
  const names = (allComps?.items || []).map((c: any) => c.competitor_name);

  const canCompare = selected.length >= 2 && selected.length <= 5;
  const { data, isLoading, error } = useQuery({
    queryKey: ["competition-compare", selected.join(","), shopId],
    queryFn: () => {
      const p = new URLSearchParams({ names: selected.join(",") });
      if (shopId !== undefined) p.set("shop_id", String(shopId));
      return apiFetch(`/api/competition/competitor-profile/compare?${p}`);
    },
    enabled: canCompare,
  });

  const items: any[] = data?.items || [];
  const rows: { label: string; render: (it: any) => any }[] = [
    { label: "Bedrijfsomvang", render: it => it.scores?.company_size_class || it.business?.size_class },
    { label: "Medewerkers", render: it => fmtRange(it.business?.employee_range_min, it.business?.employee_range_max) },
    { label: "Omzet", render: it => { const r = fmtRange(it.business?.revenue_range_min, it.business?.revenue_range_max); return r ? `${r} ${it.business?.revenue_currency || "EUR"}` : null; } },
    { label: "Landen", render: it => it.countries?.length ? it.countries.join(", ") : null },
    { label: "Market role / DNA", render: it => it.market_roles?.length ? it.market_roles.map((r: any) => r.role).join(", ") : null },
    { label: "Klantfocus", render: it => it.business?.customer_model },
    { label: "Fulfilment", render: it => it.scores?.fulfilment_model_class || it.fulfilment?.inventory_model },
    { label: "Financial health", render: it => it.scores?.financial_health_score != null ? `${Math.round(it.scores.financial_health_score)} (${it.scores.financial_health_status || "?"})` : null },
    { label: "Procurement power", render: it => it.scores?.procurement_power_score != null ? Math.round(it.scores.procurement_power_score) : null },
    { label: "Business strength", render: it => it.scores?.business_strength_score != null ? Math.round(it.scores.business_strength_score) : null },
    { label: "Operational strength", render: it => it.scores?.operational_strength_score != null ? Math.round(it.scores.operational_strength_score) : null },
    { label: "Future threat", render: it => it.scores?.future_threat_score != null ? Math.round(it.scores.future_threat_score) : null },
    { label: "Service & loyalty (levering)", render: it => it.fulfilment?.next_day_delivery == null && it.fulfilment?.same_day_delivery == null ? null : `volgende dag: ${it.fulfilment?.next_day_delivery ? "ja" : it.fulfilment?.next_day_delivery === false ? "nee" : "?"} · zelfde dag: ${it.fulfilment?.same_day_delivery ? "ja" : it.fulfilment?.same_day_delivery === false ? "nee" : "?"}` },
    { label: "Assortiment (SKU's)", render: it => it.assortment_size },
    { label: "Pricing (segment)", render: it => it.price_segment },
    { label: "Competition Relevance", render: it => it.ranking ? Math.round((it.ranking.competition_relevance_score || 0) * 100) : null },
    { label: "Price Relevance", render: it => it.ranking ? Math.round((it.ranking.price_relevance_score || 0) * 100) : null },
    { label: "Influence", render: it => it.ranking ? Math.round((it.ranking.influence_score || 0) * 100) : null },
    { label: "Data completeness", render: it => it.scores?.data_completeness_pct != null ? `${Math.round(it.scores.data_completeness_pct)}%` : null },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <Link href="/competition/competitors">
          <Button variant="ghost" size="sm" className="mt-1"><ArrowLeft className="h-4 w-4 mr-1" /> Terug</Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2"><GitCompareArrows className="h-6 w-6" />Concurrentvergelijking</h1>
          <p className="text-muted-foreground mt-1 text-sm">Vergelijk 2–5 concurrenten over profiel, fulfilment, financieel en de relevantiescores.</p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Selectie ({selected.length}/5)</CardTitle></CardHeader>
        <CardContent className="flex items-center gap-3 flex-wrap">
          {selected.map(n => (
            <Badge key={n} variant="secondary" className="text-xs pr-1" data-testid={`selected-${n}`}>
              {n}
              <button type="button" className="ml-1 hover:text-red-600" onClick={() => setSelected(s => s.filter(x => x !== n))} data-testid={`remove-${n}`}>
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {selected.length < 5 && (
            <Select value="" onValueChange={v => v && setSelected(s => s.includes(v) ? s : [...s, v])}>
              <SelectTrigger className="w-64" data-testid="select-add-competitor"><SelectValue placeholder="Concurrent toevoegen..." /></SelectTrigger>
              <SelectContent>
                {names.filter((n: string) => !selected.includes(n)).map((n: string) => (
                  <SelectItem key={n} value={n}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {!canCompare && <span className="text-xs text-muted-foreground">Kies minimaal 2 (max. 5) concurrenten.</span>}
        </CardContent>
      </Card>

      {canCompare && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Vergelijking</CardTitle>
            <CardDescription>Onbekende waarden blijven expliciet "Onbekend" — nooit 0.</CardDescription>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            {isLoading ? <div className="p-6"><Skeleton className="h-64 w-full" /></div>
              : error ? <p className="p-6 text-sm text-red-600">Vergelijking laden mislukt: {(error as Error).message}</p>
              : (
              <table className="w-full min-w-[720px]" data-testid="compare-table">
                <thead>
                  <tr className="bg-muted/40">
                    <th className="py-2 px-3 text-left text-xs font-medium text-muted-foreground border-b w-48">Kenmerk</th>
                    {items.map(it => (
                      <th key={it.competitor_name} className="py-2 px-3 text-left text-sm font-semibold border-b">
                        <Link href={`/competition/competitors/${encodeURIComponent(it.competitor_name)}`}>
                          <span className="hover:underline cursor-pointer">{it.competitor_name}</span>
                        </Link>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(row => (
                    <tr key={row.label}>
                      <td className="py-2 px-3 border-b text-xs text-muted-foreground">{row.label}</td>
                      {items.map(it => <Cell key={it.competitor_name}>{row.render(it)}</Cell>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
