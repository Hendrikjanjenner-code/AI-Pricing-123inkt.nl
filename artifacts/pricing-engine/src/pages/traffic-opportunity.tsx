import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ScatterChart, Scatter, ZAxis } from "recharts";
import { TrendingUp, Target, Zap } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const SIGNAAL_KLEUR: Record<string, string> = {
  SEARCH_DEMAND_HIGH_LOW_TRAFFIC: "#3b82f6",
  TRAFFIC_OPPORTUNITY_HIGH:       "#22c55e",
  NEW_SKU_HIGH_SEARCH_DEMAND:     "#06b6d4",
  PROMOTION_NEEDED_FOR_TRAFFIC:   "#8b5cf6",
  PRICING_POWER_FROM_DEMAND:      "#10b981",
};

export default function TrafficOpportunity() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/traffic`, { headers: { Authorization: `Bearer ${getAuthToken()}` } });
        if (!r.ok) throw new Error();
        setData(await r.json());
      } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
      setLoading(false);
    })();
  }, []);

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-56" />
      <div className="grid grid-cols-3 gap-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
      <Skeleton className="h-64 w-full" />
    </div>
  );

  const allSkus: any[] = data?.sku_overzicht || [];

  // Opportunity SKU's = hoge TOS
  const opportunities = allSkus
    .filter(s => s.tos >= 0.45)
    .sort((a, b) => b.tos - a.tos);

  // DSS vs TOS scatter
  const scatterData = allSkus.map(s => ({
    x: Math.round(s.dss * 100),
    y: Math.round(s.tos * 100),
    z: Math.round(s.sgs * 100),
    naam: s.naam,
    sku: s.sku_id,
  }));

  // TOS top 15 bar chart
  const tosBar = opportunities.slice(0, 15).map(s => ({
    naam: s.sku_id,
    tos: Math.round(s.tos * 100),
    kleur: s.tos >= 0.65 ? "#22c55e" : s.tos >= 0.50 ? "#f59e0b" : "#94a3b8",
  }));

  // Signalen gerelateerd aan opportunity
  const opportunitySignalen = [
    "SEARCH_DEMAND_HIGH_LOW_TRAFFIC",
    "TRAFFIC_OPPORTUNITY_HIGH",
    "NEW_SKU_HIGH_SEARCH_DEMAND",
    "PROMOTION_NEEDED_FOR_TRAFFIC",
    "PRICING_POWER_FROM_DEMAND",
  ];

  const signaalCounts = opportunitySignalen.reduce((acc, sig) => {
    acc[sig] = allSkus.filter(s => s.signaal === sig).length;
    return acc;
  }, {} as Record<string, number>);

  const SIGNAAL_NL: Record<string, string> = {
    SEARCH_DEMAND_HIGH_LOW_TRAFFIC: "Hoge Zoekvraag / Lage Traffic",
    TRAFFIC_OPPORTUNITY_HIGH: "Hoge Traffic Opportunity",
    NEW_SKU_HIGH_SEARCH_DEMAND: "Nieuw SKU — Hoge Zoekvraag",
    PROMOTION_NEEDED_FOR_TRAFFIC: "Promotie Nodig",
    PRICING_POWER_FROM_DEMAND: "Pricing Power via Vraag",
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Traffic Opportunity Dashboard</h1>
        <p className="text-muted-foreground text-sm mt-1">
          SKU's met hoge externe vraag én groeipotentieel — commerciële kansen
        </p>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="border-green-200">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-green-50"><Target className="w-5 h-5 text-green-600" /></div>
              <div>
                <p className="text-2xl font-bold text-green-600">{opportunities.length}</p>
                <p className="text-sm text-muted-foreground">SKU's met opportunity</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-blue-200">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-50"><TrendingUp className="w-5 h-5 text-blue-600" /></div>
              <div>
                <p className="text-2xl font-bold text-blue-600">{data?.traffic_opportunities || 0}</p>
                <p className="text-sm text-muted-foreground">Hoge TOS (&gt;55%)</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-purple-200">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-purple-50"><Zap className="w-5 h-5 text-purple-600" /></div>
              <div>
                <p className="text-2xl font-bold text-purple-600">{allSkus.filter(s => s.signaal === "SEARCH_DEMAND_HIGH_LOW_TRAFFIC").length}</p>
                <p className="text-sm text-muted-foreground">SEO/SEA kansen</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Signaal verdeling */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {opportunitySignalen.map(sig => (
          <Card key={sig} className="text-center">
            <CardContent className="pt-4 pb-3">
              <p className="text-2xl font-bold" style={{ color: SIGNAAL_KLEUR[sig] }}>{signaalCounts[sig]}</p>
              <p className="text-xs text-muted-foreground mt-1">{SIGNAAL_NL[sig]}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* TOS Grafiek */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top 15 Traffic Opportunity Score</CardTitle>
          <CardDescription>Groen ≥ 65% — directe actie aanbevolen</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={tosBar} layout="vertical">
              <XAxis type="number" domain={[0, 100]} fontSize={10} tickFormatter={v => `${v}%`} />
              <YAxis type="category" dataKey="naam" width={60} fontSize={10} />
              <Tooltip formatter={(v: number) => [`${v}%`, "TOS"]} />
              <Bar dataKey="tos" radius={[0, 4, 4, 0]}>
                {tosBar.map((e, i) => <Cell key={i} fill={e.kleur} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Opportunity tabel */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Opportunity SKU's ({opportunities.length})</CardTitle>
          <CardDescription>Gesorteerd op Traffic Opportunity Score</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {["SKU","Naam","Categorie","DSS","CHS","TOS","SGS","Signaal","Actie",""].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {opportunities.map((s: any) => (
                  <tr key={s.sku_id} className="border-b hover:bg-muted/30">
                    <td className="py-2 px-3 font-mono text-xs">{s.sku_id}</td>
                    <td className="py-2 px-3 max-w-[180px] truncate">{s.naam}</td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">{s.categorie}</td>
                    {["dss","chs","tos","sgs"].map(k => (
                      <td key={k} className="py-2 px-3">
                        <div className="flex items-center gap-1">
                          <div className="w-10 bg-muted rounded-full h-1.5">
                            <div className="h-1.5 rounded-full bg-primary" style={{ width: `${Math.round(s[k] * 100)}%` }} />
                          </div>
                          <span className="text-xs font-mono">{Math.round(s[k] * 100)}%</span>
                        </div>
                      </td>
                    ))}
                    <td className="py-2 px-3">
                      <span className="text-xs px-1.5 py-0.5 rounded-full text-white whitespace-nowrap"
                        style={{ background: SIGNAAL_KLEUR[s.signaal] || "#94a3b8" }}>
                        {s.signaal_nl || "—"}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">
                      {s.signaal === "SEARCH_DEMAND_HIGH_LOW_TRAFFIC" && "SEO/SEA push"}
                      {s.signaal === "PRICING_POWER_FROM_DEMAND" && "Prijs verhogen"}
                      {s.signaal === "NEW_SKU_HIGH_SEARCH_DEMAND" && "Launch promotie"}
                      {s.signaal === "PROMOTION_NEEDED_FOR_TRAFFIC" && "Promotie activeren"}
                      {s.signaal === "TRAFFIC_OPPORTUNITY_HIGH" && "Marketing inzet"}
                    </td>
                    <td className="py-2 px-3">
                      <Link href={`/traffic/sku/${s.sku_id}`}>
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
