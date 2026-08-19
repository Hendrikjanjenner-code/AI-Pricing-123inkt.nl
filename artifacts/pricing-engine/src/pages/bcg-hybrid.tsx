import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import { getAuthToken } from "@/lib/auth";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const HYBRID_KLEUR: Record<string, string> = {
  PRICING_POWER_STAR:          "#22c55e",
  DEFENSIVE_CASH_COW:          "#f59e0b",
  PRIVATE_LABEL_STAR:          "#8b5cf6",
  EXPERIMENTAL_QUESTION_MARK:  "#3b82f6",
  LOW_PRIORITY_DOG:            "#94a3b8",
};

const KWADRANT_INFO = [
  {
    klasse: "PRICING_POWER_STAR",
    label: "Pricing Power Ster",
    uitleg: "Hoge pricing power, lage concurrentiedruk → prijsverhoging mogelijk",
    kleur: "#22c55e",
    positie: "Rechtsonder",
  },
  {
    klasse: "DEFENSIVE_CASH_COW",
    label: "Defensieve Cash Cow",
    uitleg: "Hoge pricing power maar ook hoge druk → marge beschermen",
    kleur: "#f59e0b",
    positie: "Rechtsboven",
  },
  {
    klasse: "EXPERIMENTAL_QUESTION_MARK",
    label: "Experimenteel Vraagteken",
    uitleg: "Lage pricing power maar lage druk → experimenten mogelijk",
    kleur: "#3b82f6",
    positie: "Linksonder",
  },
  {
    klasse: "LOW_PRIORITY_DOG",
    label: "Lage Prioriteit Dog",
    uitleg: "Lage pricing power en hoge druk → minimale aandacht",
    kleur: "#94a3b8",
    positie: "Linksboven",
  },
];

const HybridTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-popover border rounded-lg p-3 shadow-lg text-xs max-w-[240px]">
      <p className="font-semibold mb-1 truncate">{d.naam}</p>
      <div
        className="inline-block px-2 py-0.5 rounded text-white text-xs mb-2"
        style={{ background: d.kleur }}
      >
        {d.klasse_nl}
      </div>
      <div className="space-y-0.5 text-muted-foreground">
        <p>Pricing Power: <strong className="text-foreground">{Math.round(d.x * 100)}%</strong></p>
        <p>Concurrentiedruk: <strong className="text-foreground">{Math.round(d.y * 100)}%</strong></p>
        <p>IBSS: <strong className="text-foreground">{Math.round(d.ibss * 100)}%</strong></p>
        <p>GPS: <strong className="text-foreground">{Math.round(d.gps * 100)}%</strong></p>
      </div>
      <p className="mt-2 font-medium text-foreground">{d.strategie}</p>
    </div>
  );
};

export default function BcgHybrid() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const { toast } = useToast();
  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const r = await fetch(`${API}/api/bcg/hybrid-matrix${filterQs ? `?${filterQs}` : ""}`, {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
        });
        if (!r.ok) throw new Error();
        setData(await r.json());
      } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
      setLoading(false);
    })();
  }, [filterQs]);

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-[480px] w-full" />
    </div>
  );

  const items: any[] = data?.items || [];
  const kwadranten = data?.kwadranten || {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Hybride Pricing Matrix</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Pricing Power (X-as) vs Concurrentiedruk (Y-as) — pricingstrategie op één oogopslag
        </p>
      </div>

      <GlobalFilterBar />

      {/* Kwadrant samenvatting */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {KWADRANT_INFO.map(q => (
          <Card key={q.klasse} className="border-l-4" style={{ borderLeftColor: q.kleur }}>
            <CardContent className="pt-4 pb-4">
              <div className="flex items-center justify-between mb-1">
                <p className="font-semibold text-sm">{q.label}</p>
                <span className="text-2xl font-bold">{kwadranten[q.klasse] || 0}</span>
              </div>
              <p className="text-xs text-muted-foreground">{q.uitleg}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Scatter matrix */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Hybride BCG Scatter Plot</CardTitle>
          <CardDescription>
            X-as: Pricing Power (hoog = meer ruimte voor prijsverhoging) ·
            Y-as: Concurrentiedruk (hoog = veel externe druk) ·
            Bubbelgrootte: huidige prijs
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Kwadrant labels overlay */}
          <div className="relative">
            <div className="absolute inset-0 grid grid-cols-2 grid-rows-2 pointer-events-none z-10 px-14 py-6">
              <div className="flex items-start justify-start pl-2 pt-2">
                <span className="text-xs text-slate-400 font-medium">Experimenteel</span>
              </div>
              <div className="flex items-start justify-end pr-2 pt-2">
                <span className="text-xs text-amber-400 font-medium">Defensieve Cash Cow</span>
              </div>
              <div className="flex items-end justify-start pl-2 pb-8">
                <span className="text-xs text-green-500 font-medium">Pricing Power Ster ⭐</span>
              </div>
              <div className="flex items-end justify-end pr-2 pb-8">
                <span className="text-xs text-slate-400 font-medium">Lage Prioriteit</span>
              </div>
            </div>

            <ResponsiveContainer width="100%" height={440}>
              <ScatterChart margin={{ top: 30, right: 30, bottom: 40, left: 30 }}>
                <XAxis
                  type="number" dataKey="x" domain={[0, 1]} name="Pricing Power"
                  label={{ value: "Pricing Power →", position: "insideBottom", offset: -15, fontSize: 11 }}
                  fontSize={10} tickFormatter={v => `${Math.round(v * 100)}%`}
                />
                <YAxis
                  type="number" dataKey="y" domain={[0, 1]} name="Concurrentiedruk"
                  label={{ value: "Concurrentiedruk →", angle: -90, position: "insideLeft", fontSize: 11 }}
                  fontSize={10} tickFormatter={v => `${Math.round(v * 100)}%`}
                />
                <ZAxis type="number" dataKey="bubble" range={[40, 500]} />
                <Tooltip content={<HybridTooltip />} />
                <ReferenceLine x={0.60} stroke="#cbd5e1" strokeDasharray="5 5" />
                <ReferenceLine y={0.60} stroke="#cbd5e1" strokeDasharray="5 5" />
                <Scatter
                  data={items}
                  onClick={(d: any) => setSelected(d.sku_id === selected ? null : d.sku_id)}
                >
                  {items.map((e: any, i: number) => (
                    <Cell
                      key={i}
                      fill={e.kleur}
                      opacity={selected && selected !== e.sku_id ? 0.3 : 0.85}
                      stroke={selected === e.sku_id ? "#1e40af" : "transparent"}
                      strokeWidth={2}
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* SKU tabel gefilterd op hybride klasse */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {KWADRANT_INFO.map(q => {
          const groep = items.filter(i => i.klasse === q.klasse);
          if (!groep.length) return null;
          return (
            <Card key={q.klasse}>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: q.kleur }} />
                  {q.label}
                  <Badge variant="secondary" className="ml-auto">{groep.length}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-xs">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="text-left py-2 px-3 font-medium text-muted-foreground">SKU</th>
                      <th className="text-left py-2 px-3 font-medium text-muted-foreground">Naam</th>
                      <th className="text-right py-2 px-3 font-medium text-muted-foreground">Power</th>
                      <th className="text-right py-2 px-3 font-medium text-muted-foreground">Druk</th>
                      <th className="py-2 px-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {groep.slice(0, 6).map((sku: any) => (
                      <tr key={sku.sku_id} className="border-b hover:bg-muted/30">
                        <td className="py-1.5 px-3 font-mono">{sku.sku_id}</td>
                        <td className="py-1.5 px-3 max-w-[140px] truncate">{sku.naam}</td>
                        <td className="py-1.5 px-3 text-right">{Math.round(sku.x * 100)}%</td>
                        <td className="py-1.5 px-3 text-right">{Math.round(sku.y * 100)}%</td>
                        <td className="py-1.5 px-3">
                          <Link href={`/bcg/sku/${sku.sku_id}`}>
                            <Button variant="ghost" size="sm" className="h-5 text-xs px-1.5">→</Button>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
