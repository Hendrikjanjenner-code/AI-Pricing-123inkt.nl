import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { Search, AlertTriangle, TrendingUp } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const GAP_STIJL = (sgs: number) => ({
  bg: sgs >= 0.60 ? "bg-red-50 border-red-200" : sgs >= 0.35 ? "bg-amber-50 border-amber-200" : "bg-green-50 border-green-200",
  kleur: sgs >= 0.60 ? "#ef4444" : sgs >= 0.35 ? "#f59e0b" : "#22c55e",
  label: sgs >= 0.60 ? "Groot" : sgs >= 0.35 ? "Gemiddeld" : "Klein",
  badge: sgs >= 0.60 ? "bg-red-100 text-red-800" : sgs >= 0.35 ? "bg-amber-100 text-amber-800" : "bg-green-100 text-green-800",
});

export default function SearchGap() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoek, setZoek] = useState("");
  const [selected, setSelected] = useState<any>(null);
  const [sdData, setSdData] = useState<any>(null);
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

  async function laadDetail(sku_id: string) {
    try {
      const r = await fetch(`${API}/api/search-demand/sku/${sku_id}`, { headers: { Authorization: `Bearer ${getAuthToken()}` } });
      if (!r.ok) return;
      const d = await r.json();
      setSelected(sku_id);
      setSdData(d);
    } catch { }
  }

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

  const gapData = items.slice(0, 14).map((i: any) => {
    const s = GAP_STIJL(i.sgs);
    return { naam: i.sku_id, sgs: Math.round(i.sgs * 100), ovs: Math.round(i.ovs * 100), kleur: s.kleur };
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Search Gap Analyse</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Verschil tussen externe marktvraag en eigen zichtbaarheid — gemiste kansen in kaart
        </p>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-red-200">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-red-50"><AlertTriangle className="w-5 h-5 text-red-600" /></div>
              <div>
                <p className="text-2xl font-bold text-red-600">{data?.hoge_gap_count || 0}</p>
                <p className="text-sm text-muted-foreground">Grote search gap</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-2xl font-bold">{(data?.totaal_volume || 0).toLocaleString("nl-NL")}</p>
            <p className="text-sm text-muted-foreground">Totaal zoekvolume / mnd</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-2xl font-bold">{Math.round((data?.gemiddelde_sgs || 0) * 100)}%</p>
            <p className="text-sm text-muted-foreground">Gem. search gap</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-2xl font-bold">{data?.totaal_keywords || 0}</p>
            <p className="text-sm text-muted-foreground">Keywords getrackt</p>
          </CardContent>
        </Card>
      </div>

      {/* Gap grafiek */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Search Gap vs Eigen Zichtbaarheid</CardTitle>
          <CardDescription>
            Rood = grote gap (veel externe vraag, weinig eigen bereik) — directe actie nodig
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={gapData}>
              <XAxis dataKey="naam" fontSize={9} />
              <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} fontSize={10} />
              <Tooltip formatter={(v: number, name: string) => [`${v}%`, name === "sgs" ? "Search Gap" : "Eigen Zichtbaarheid"]} />
              <Bar dataKey="sgs" name="sgs" radius={[4, 4, 0, 0]}>
                {gapData.map((e, i) => <Cell key={i} fill={e.kleur} />)}
              </Bar>
              <Bar dataKey="ovs" name="ovs" fill="#22c55e" opacity={0.6} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-4 text-xs text-muted-foreground justify-center mt-2">
            <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm bg-red-500 inline-block" />Search Gap</span>
            <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm bg-green-500 inline-block" />Eigen Zichtbaarheid</span>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* SKU tabel */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Search Gap per SKU ({items.length})</CardTitle>
              <Input placeholder="Zoek..." value={zoek} onChange={e => setZoek(e.target.value)} className="w-36 h-7 text-xs" />
            </div>
          </CardHeader>
          <CardContent className="p-0 max-h-[500px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 sticky top-0">
                <tr>
                  {["SKU","Naam","Volume","SGS","Gap","Actie"].map(h => (
                    <th key={h} className="text-left py-2 px-2 text-xs font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gefilterd.map((item: any) => {
                  const stijl = GAP_STIJL(item.sgs);
                  return (
                    <tr key={item.sku_id}
                      className={`border-b cursor-pointer hover:bg-muted/30 ${selected === item.sku_id ? "bg-muted/50" : ""}`}
                      onClick={() => laadDetail(item.sku_id)}>
                      <td className="py-1.5 px-2 font-mono text-xs">{item.sku_id}</td>
                      <td className="py-1.5 px-2 max-w-[120px] truncate text-xs">{item.naam}</td>
                      <td className="py-1.5 px-2 font-mono text-xs">{(item.total_volume || 0).toLocaleString("nl-NL")}</td>
                      <td className="py-1.5 px-2">
                        <div className="flex items-center gap-1">
                          <div className="w-8 bg-muted rounded-full h-1.5">
                            <div className="h-1.5 rounded-full" style={{ width: `${Math.round(item.sgs * 100)}%`, background: stijl.kleur }} />
                          </div>
                          <span className="text-xs font-mono">{Math.round(item.sgs * 100)}%</span>
                        </div>
                      </td>
                      <td className="py-1.5 px-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${stijl.badge}`}>{stijl.label}</span>
                      </td>
                      <td className="py-1.5 px-2 text-xs text-muted-foreground">{item.actie?.split(" ").slice(0,3).join(" ")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Keyword detail panel */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {sdData ? `${sdData.naam} — Keywords` : "Selecteer een SKU"}
            </CardTitle>
            {sdData && (
              <div className="flex gap-3 text-xs text-muted-foreground">
                <span>SGS: <strong className="text-foreground">{Math.round(sdData.scores?.sgs * 100)}%</strong></span>
                <span>Volume: <strong className="text-foreground">{(sdData.aggregaat?.total_volume || 0).toLocaleString("nl-NL")}</strong></span>
                <span>Gap: <strong className="text-foreground">{sdData.scores?.gap_label}</strong></span>
              </div>
            )}
          </CardHeader>
          <CardContent>
            {!sdData ? (
              <div className="flex flex-col items-center justify-center h-48 text-muted-foreground gap-2">
                <Search className="w-8 h-8 opacity-40" />
                <p className="text-sm">Klik op een SKU om keyword-details te zien</p>
              </div>
            ) : (
              <div className="space-y-3">
                {sdData.actie && (
                  <div className="p-3 rounded-lg bg-muted/50 text-sm">
                    <span className="font-medium">Aanbevolen actie:</span> {sdData.actie}
                  </div>
                )}
                <div className="max-h-80 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 sticky top-0">
                      <tr>
                        {["Keyword","Type","Volume","Positie","KOS"].map(h => (
                          <th key={h} className="text-left py-1.5 px-2 font-medium text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(sdData.keywords || []).map((kw: any, i: number) => (
                        <tr key={i} className="border-b hover:bg-muted/30">
                          <td className="py-1.5 px-2 max-w-[160px] truncate font-medium">{kw.keyword}</td>
                          <td className="py-1.5 px-2">
                            <span className="px-1 py-0.5 rounded text-xs bg-primary/10 text-primary">{kw.type}</span>
                          </td>
                          <td className="py-1.5 px-2 font-mono">{(kw.volume || 0).toLocaleString("nl-NL")}</td>
                          <td className="py-1.5 px-2 font-mono">{kw.positie?.toFixed(1)}</td>
                          <td className="py-1.5 px-2">
                            <div className="w-10 bg-muted rounded-full h-1.5">
                              <div className="h-1.5 rounded-full bg-indigo-500" style={{ width: `${Math.round(kw.kos * 100)}%` }} />
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
