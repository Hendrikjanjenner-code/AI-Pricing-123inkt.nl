import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from "recharts";
import { TrendingUp, TrendingDown, AlertTriangle, Search, Eye, ShoppingCart, RefreshCw, Zap } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const SIGNAAL_KLEUR: Record<string, string> = {
  CONVERSION_DROP_DETECTED:       "#ef4444",
  TRAFFIC_DROP_DETECTED:          "#f97316",
  SEARCH_DEMAND_HIGH_LOW_TRAFFIC: "#3b82f6",
  HIGH_TRAFFIC_LOW_CONVERSION:    "#f59e0b",
  PRICING_POWER_FROM_DEMAND:      "#10b981",
  NEW_SKU_HIGH_SEARCH_DEMAND:     "#06b6d4",
  TRAFFIC_OPPORTUNITY_HIGH:       "#22c55e",
  PROMOTION_NEEDED_FOR_TRAFFIC:   "#8b5cf6",
  NO_SIGNAL:                      "#cbd5e1",
};

function ScoreBar({ score, label, kleur = "#6366f1" }: { score: number; label: string; kleur?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 text-muted-foreground shrink-0">{label}</span>
      <div className="flex-1 bg-muted rounded-full h-2">
        <div className="h-2 rounded-full" style={{ width: `${Math.round(score * 100)}%`, background: kleur }} />
      </div>
      <span className="font-mono w-8 text-right">{Math.round(score * 100)}%</span>
    </div>
  );
}

export default function TrafficDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const { toast } = useToast();

  useEffect(() => { laden(); }, []);

  async function laden() {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/traffic`, { headers: { Authorization: `Bearer ${getAuthToken()}` } });
      if (!r.ok) throw new Error();
      setData(await r.json());
    } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
    setLoading(false);
  }

  async function berekenen() {
    setRunning(true);
    try {
      const r = await fetch(`${API}/api/traffic/berekenen`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      if (!r.ok) throw new Error();
      toast({ title: "Traffic engine uitgevoerd" });
      await laden();
    } catch { toast({ title: "Mislukt", variant: "destructive" }); }
    setRunning(false);
  }

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-56" />
      <div className="grid grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
      <div className="grid grid-cols-2 gap-6">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-64" />)}</div>
    </div>
  );

  const kpis = [
    { label: "Totale Sessies (30d)", val: (data?.totale_sessies || 0).toLocaleString("nl-NL"), icon: Eye, kleur: "bg-blue-50 text-blue-600" },
    { label: "Conversieratio", val: `${((data?.conversieratio || 0) * 100).toFixed(2)}%`, icon: ShoppingCart, kleur: "bg-green-50 text-green-600" },
    { label: "Omzet / Bezoeker", val: `€${(data?.omzet_per_bezoeker || 0).toFixed(2)}`, icon: TrendingUp, kleur: "bg-amber-50 text-amber-600" },
    { label: "Marge / Bezoeker", val: `€${(data?.marge_per_bezoeker || 0).toFixed(2)}`, icon: TrendingUp, kleur: "bg-purple-50 text-purple-600" },
  ];

  const alertKpis = [
    { label: "SKU's Conversiedaling", val: data?.sku_met_conversiedaling || 0, kleur: "text-red-600" },
    { label: "Hoge Search Gap", val: data?.sku_met_hoge_search_gap || 0, kleur: "text-indigo-600" },
    { label: "Traffic Opportunities", val: data?.traffic_opportunities || 0, kleur: "text-green-600" },
    { label: "Totaal SKU's", val: data?.totaal_skus || 0, kleur: "text-slate-600" },
  ];

  const gapData = (data?.search_gap_top || []).map((s: any) => ({
    naam: s.sku_id,
    sgs: Math.round(s.sgs * 100),
    kleur: s.sgs >= 0.60 ? "#ef4444" : s.sgs >= 0.40 ? "#f59e0b" : "#94a3b8",
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Traffic & Demand Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">Interne traffic, conversie en externe marktvraag op één plek</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={laden}><RefreshCw className="w-4 h-4 mr-2" />Vernieuwen</Button>
          <Button size="sm" onClick={berekenen} disabled={running}>
            <Zap className="w-4 h-4 mr-2" />{running ? "Bezig..." : "Engine Uitvoeren"}
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpis.map(({ label, val, icon: Icon, kleur }) => (
          <Card key={label}>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${kleur}`}><Icon className="w-5 h-5" /></div>
                <div>
                  <p className="text-xl font-bold">{val}</p>
                  <p className="text-xs text-muted-foreground">{label}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Alert KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {alertKpis.map(({ label, val, kleur }) => (
          <Card key={label} className="bg-muted/20">
            <CardContent className="pt-4 pb-4 text-center">
              <p className={`text-3xl font-bold ${kleur}`}>{val}</p>
              <p className="text-xs text-muted-foreground mt-1">{label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Grafieken */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top 10 Search Gap SKU's</CardTitle>
            <CardDescription>Hoge externe vraag, lage eigen zichtbaarheid</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={gapData} layout="vertical">
                <XAxis type="number" domain={[0, 100]} fontSize={10} tickFormatter={v => `${v}%`} />
                <YAxis type="category" dataKey="naam" width={55} fontSize={10} />
                <Tooltip formatter={(v: number) => [`${v}%`, "Search Gap"]} />
                <Bar dataKey="sgs" radius={[0, 4, 4, 0]}>
                  {gapData.map((e: any, i: number) => <Cell key={i} fill={e.kleur} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Actieve Signalen</CardTitle>
            <CardDescription>Gerangschikt op prioriteit en CRS-score</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(data?.signalen || []).slice(0, 7).map((s: any, i: number) => (
                <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-muted/30">
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: s.kleur }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{s.signaal_nl}</p>
                    <p className="text-xs text-muted-foreground truncate">{s.entity_naam}</p>
                  </div>
                  <Link href={`/traffic/sku/${s.entity_id}`}>
                    <Button variant="ghost" size="sm" className="h-6 text-xs px-2 shrink-0">→</Button>
                  </Link>
                </div>
              ))}
              {!(data?.signalen?.length) && <p className="text-sm text-muted-foreground">Geen actieve signalen.</p>}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* SKU Overzicht tabel */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">SKU Traffic Overzicht</CardTitle>
            <div className="flex gap-2">
              <Link href="/traffic/opportunity"><Button variant="outline" size="sm">Opportunities</Button></Link>
              <Link href="/traffic/conversie"><Button variant="outline" size="sm">Conversie</Button></Link>
              <Link href="/traffic/search-gap"><Button variant="outline" size="sm">Search Gap</Button></Link>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {["SKU", "Naam", "Categorie", "DSS", "CHS", "TOS", "CRS", "SGS", "Signaal", ""].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data?.sku_overzicht || []).slice(0, 15).map((s: any) => (
                  <tr key={s.sku_id} className="border-b hover:bg-muted/30">
                    <td className="py-2 px-3 font-mono text-xs">{s.sku_id}</td>
                    <td className="py-2 px-3 max-w-[160px] truncate">{s.naam}</td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">{s.categorie}</td>
                    {["dss","chs","tos","crs","sgs"].map(k => (
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
                      <span className="px-1.5 py-0.5 rounded-full text-xs text-white whitespace-nowrap"
                        style={{ background: SIGNAAL_KLEUR[s.signaal] || "#94a3b8" }}>
                        {s.signaal_nl || "—"}
                      </span>
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

      {/* Snelkoppelingen */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {[
          { href: "/traffic/conversie", label: "Conversie Monitoring", desc: "Dalende conversies detecteren", icon: TrendingDown },
          { href: "/traffic/search-demand", label: "Search Demand", desc: "Extern zoekvolume analyseren", icon: Search },
          { href: "/traffic/opportunity", label: "Traffic Opportunity", desc: "Kansen identificeren", icon: TrendingUp },
          { href: "/traffic/search-gap", label: "Search Gap Analyse", desc: "Eigen vs externe zichtbaarheid", icon: AlertTriangle },
        ].map(({ href, label, desc, icon: Icon }) => (
          <Link key={href} href={href}>
            <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-primary/10"><Icon className="w-4 h-4 text-primary" /></div>
                  <div>
                    <p className="font-medium text-sm">{label}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
