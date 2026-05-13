import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from "recharts";
import { Search, TrendingUp, Eye } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const GAP_KLEUR: Record<string, string> = {
  hoog:      "#ef4444",
  gemiddeld: "#f59e0b",
  laag:      "#22c55e",
};

export default function SearchDemand() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoek, setZoek] = useState("");
  const { toast } = useToast();

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/search-demand`, { headers: { Authorization: `Bearer ${getAuthToken()}` } });
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

  const items: any[] = data?.items || [];
  const gefilterd = zoek
    ? items.filter(i => i.naam.toLowerCase().includes(zoek.toLowerCase()) || i.sku_id.toLowerCase().includes(zoek.toLowerCase()))
    : items;

  const sgsData = items.slice(0, 12).map((i: any) => ({
    naam: i.sku_id,
    sgs: Math.round(i.sgs * 100),
    kleur: GAP_KLEUR[i.gap_label] || "#94a3b8",
  }));

  const typeData = Object.entries(data?.keyword_types || {}).map(([naam, waarde]) => ({
    naam, waarde: waarde as number,
  }));

  const TYPE_KLEUREN = ["#6366f1","#22c55e","#f59e0b","#3b82f6","#8b5cf6"];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Search Demand Analyse</h1>
        <p className="text-muted-foreground text-sm mt-1">Extern zoekvolume, eigen zichtbaarheid en search gap per SKU</p>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-2xl font-bold">{(data?.totaal_volume || 0).toLocaleString("nl-NL")}</p>
            <p className="text-sm text-muted-foreground">Totaal zoekvolume / mnd</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-2xl font-bold">{data?.totaal_keywords || 0}</p>
            <p className="text-sm text-muted-foreground">Keywords getrackt</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-2xl font-bold text-red-600">{data?.hoge_gap_count || 0}</p>
            <p className="text-sm text-muted-foreground">Hoge search gap SKU's</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-2xl font-bold">{Math.round((data?.gemiddelde_sgs || 0) * 100)}%</p>
            <p className="text-sm text-muted-foreground">Gem. search gap</p>
          </CardContent>
        </Card>
      </div>

      {/* Grafieken */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Search Gap per SKU</CardTitle>
            <CardDescription>Rood = groot verschil marktvraag vs eigen zichtbaarheid</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={sgsData} layout="vertical">
                <XAxis type="number" domain={[0, 100]} fontSize={10} tickFormatter={v => `${v}%`} />
                <YAxis type="category" dataKey="naam" width={55} fontSize={10} />
                <Tooltip formatter={(v: number) => [`${v}%`, "Search Gap"]} />
                <Bar dataKey="sgs" radius={[0, 4, 4, 0]}>
                  {sgsData.map((e, i) => <Cell key={i} fill={e.kleur} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Keyword Type Verdeling</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-center">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={typeData} dataKey="waarde" nameKey="naam" cx="50%" cy="50%" outerRadius={80}
                  label={({ naam, waarde }: any) => `${naam}: ${waarde}`} fontSize={10}>
                  {typeData.map((_, i) => (
                    <Cell key={i} fill={TYPE_KLEUREN[i % TYPE_KLEUREN.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Tabel */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">SKU Search Demand Overzicht ({items.length} SKU's)</CardTitle>
            <Input placeholder="Zoek SKU..." value={zoek} onChange={e => setZoek(e.target.value)} className="w-48 h-8 text-sm" />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {["SKU","Naam","Categorie","Keywords","Zoekvolume","Trend","Impressies","Klikken","SGS","Gap","Actie",""].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gefilterd.map((item: any) => (
                  <tr key={item.sku_id} className="border-b hover:bg-muted/30">
                    <td className="py-2 px-3 font-mono text-xs">{item.sku_id}</td>
                    <td className="py-2 px-3 max-w-[160px] truncate">{item.naam}</td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">{item.categorie}</td>
                    <td className="py-2 px-3 text-xs">{item.keyword_count}</td>
                    <td className="py-2 px-3 font-mono text-xs">{(item.total_volume || 0).toLocaleString("nl-NL")}</td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-1">
                        <div className="w-10 bg-muted rounded-full h-1.5">
                          <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${Math.round(item.avg_trend * 100)}%` }} />
                        </div>
                        <span className="text-xs font-mono">{Math.round(item.avg_trend * 100)}%</span>
                      </div>
                    </td>
                    <td className="py-2 px-3 font-mono text-xs">{(item.eigen_impressies || 0).toLocaleString("nl-NL")}</td>
                    <td className="py-2 px-3 font-mono text-xs">{(item.eigen_klikken || 0).toLocaleString("nl-NL")}</td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-1">
                        <div className="w-10 bg-muted rounded-full h-1.5">
                          <div className="h-1.5 rounded-full" style={{ width: `${Math.round(item.sgs * 100)}%`, background: GAP_KLEUR[item.gap_label] || "#94a3b8" }} />
                        </div>
                        <span className="text-xs font-mono">{Math.round(item.sgs * 100)}%</span>
                      </div>
                    </td>
                    <td className="py-2 px-3">
                      <span className="px-1.5 py-0.5 rounded-full text-xs text-white"
                        style={{ background: GAP_KLEUR[item.gap_label] || "#94a3b8" }}>
                        {item.gap_label}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs text-muted-foreground max-w-[160px] truncate">{item.actie}</td>
                    <td className="py-2 px-3">
                      <Link href={`/traffic/sku/${item.sku_id}`}>
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
