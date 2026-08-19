import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from "recharts";
import { Zap, TrendingUp } from "lucide-react";
import { getAuthToken } from "@/lib/auth";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const PPS_KLEUR = (score: number): string => {
  if (score >= 0.75) return "#22c55e";
  if (score >= 0.60) return "#84cc16";
  if (score >= 0.45) return "#f59e0b";
  if (score >= 0.30) return "#f97316";
  return "#ef4444";
};

const HYBRID_KLEUR: Record<string, string> = {
  PRICING_POWER_STAR:          "#22c55e",
  DEFENSIVE_CASH_COW:          "#f59e0b",
  PRIVATE_LABEL_STAR:          "#8b5cf6",
  EXPERIMENTAL_QUESTION_MARK:  "#3b82f6",
  LOW_PRIORITY_DOG:            "#94a3b8",
};

const LABEL_KLEUR: Record<string, string> = {
  "Zeer hoog":  "#22c55e",
  "Hoog":       "#84cc16",
  "Gemiddeld":  "#f59e0b",
  "Laag":       "#f97316",
  "Zeer laag":  "#ef4444",
};

export default function BcgPricingPower() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoek, setZoek] = useState("");
  const { toast } = useToast();
  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const r = await fetch(`${API}/api/bcg/pricing-power${filterQs ? `?${filterQs}` : ""}`, {
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
      <Skeleton className="h-60 w-full" />
      <Skeleton className="h-80 w-full" />
    </div>
  );

  const items: any[] = data?.items || [];
  const distributie: any[] = data?.distributie || [];
  const gemiddeld: number = data?.gemiddeld || 0;

  const gefilterd = zoek
    ? items.filter(i => i.naam.toLowerCase().includes(zoek.toLowerCase()) || i.sku_id.toLowerCase().includes(zoek.toLowerCase()))
    : items;

  // Top 12 voor grafiek
  const topData = items.slice(0, 12).map(i => ({
    naam: i.sku_id,
    pps: Math.round(i.pricing_power_score * 100),
    kleur: PPS_KLEUR(i.pricing_power_score),
  }));

  // Pie chart distributie op label
  const labelTelling: Record<string, number> = {};
  items.forEach(i => {
    labelTelling[i.label] = (labelTelling[i.label] || 0) + 1;
  });
  const pieData = Object.entries(labelTelling).map(([naam, waarde]) => ({
    naam, waarde, kleur: LABEL_KLEUR[naam] || "#94a3b8",
  }));

  // KPI's
  const hoog = items.filter(i => i.pricing_power_score >= 0.60).length;
  const laag = items.filter(i => i.pricing_power_score < 0.40).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Pricing Power Dashboard</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Welke SKU's hebben de meeste ruimte voor prijsverhoging zonder omzetverlies?
        </p>
      </div>

      <GlobalFilterBar />

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-green-50"><Zap className="w-5 h-5 text-green-600" /></div>
              <div>
                <p className="text-2xl font-bold">{hoog}</p>
                <p className="text-sm text-muted-foreground">Hoge pricing power</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-red-50"><TrendingUp className="w-5 h-5 text-red-500" /></div>
              <div>
                <p className="text-2xl font-bold">{laag}</p>
                <p className="text-sm text-muted-foreground">Lage pricing power</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div>
              <p className="text-2xl font-bold">{Math.round(gemiddeld * 100)}%</p>
              <p className="text-sm text-muted-foreground">Gemiddelde pricing power</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div>
              <p className="text-2xl font-bold">{items.length}</p>
              <p className="text-sm text-muted-foreground">Totaal SKU's geanalyseerd</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Grafieken */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top Pricing Power SKU's</CardTitle>
            <CardDescription>Top 12 SKU's op pricing power score</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={topData} layout="vertical">
                <XAxis type="number" domain={[0, 100]} fontSize={10} tickFormatter={v => `${v}%`} />
                <YAxis type="category" dataKey="naam" width={65} fontSize={10} />
                <Tooltip formatter={(v: number) => [`${v}%`, "Pricing Power"]} />
                <Bar dataKey="pps" radius={[0, 4, 4, 0]}>
                  {topData.map((e, i) => <Cell key={i} fill={e.kleur} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Pricing Power Verdeling</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-center">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="waarde"
                  nameKey="naam"
                  cx="50%" cy="50%"
                  outerRadius={90}
                  label={({ naam, waarde }: any) => `${naam}: ${waarde}`}
                  labelLine={false}
                  fontSize={10}
                >
                  {pieData.map((e, i) => <Cell key={i} fill={e.kleur} />)}
                </Pie>
                <Tooltip />
                <Legend fontSize={11} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Tabel */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Alle SKU's — Pricing Power Ranglijst</CardTitle>
            <Input
              placeholder="Zoek SKU of naam..."
              value={zoek}
              onChange={e => setZoek(e.target.value)}
              className="w-52 h-8 text-sm"
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {["#", "SKU", "Naam", "Categorie", "Pricing Power", "Label", "BCG", "Strategie", "Prioriteit", ""].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gefilterd.map((item: any, idx: number) => (
                  <tr key={item.sku_id} className="border-b hover:bg-muted/30">
                    <td className="py-2 px-3 text-muted-foreground text-xs">{idx + 1}</td>
                    <td className="py-2 px-3 font-mono text-xs">{item.sku_id}</td>
                    <td className="py-2 px-3 max-w-[180px] truncate">{item.naam}</td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">{item.categorie}</td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-2">
                        <div className="w-20 bg-muted rounded-full h-2">
                          <div
                            className="h-2 rounded-full"
                            style={{
                              width: `${Math.round(item.pricing_power_score * 100)}%`,
                              background: PPS_KLEUR(item.pricing_power_score),
                            }}
                          />
                        </div>
                        <span className="font-mono text-xs w-10">{Math.round(item.pricing_power_score * 100)}%</span>
                      </div>
                    </td>
                    <td className="py-2 px-3">
                      <span
                        className="px-2 py-0.5 rounded-full text-xs font-medium text-white"
                        style={{ background: PPS_KLEUR(item.pricing_power_score) }}
                      >
                        {item.label}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <span
                        className="px-2 py-0.5 rounded-full text-xs font-medium text-white"
                        style={{ background: HYBRID_KLEUR[item.hybrid_bcg] || "#94a3b8" }}
                      >
                        {item.hybrid_bcg_nl}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs text-muted-foreground max-w-[160px] truncate">{item.strategie}</td>
                    <td className="py-2 px-3">
                      <Badge variant={item.prioriteit === "hoog" ? "destructive" : item.prioriteit === "gemiddeld" ? "secondary" : "outline"} className="text-xs">
                        {item.prioriteit}
                      </Badge>
                    </td>
                    <td className="py-2 px-3">
                      <Link href={`/bcg/sku/${item.sku_id}`}>
                        <Button variant="ghost" size="sm" className="h-6 text-xs px-2">Detail</Button>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
