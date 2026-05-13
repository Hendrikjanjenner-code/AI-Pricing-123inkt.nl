import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { AlertTriangle, TrendingDown, TrendingUp } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const PRIO_BADGE: Record<string, string> = {
  hoog:      "bg-red-100 text-red-800 border-red-200",
  gemiddeld: "bg-amber-100 text-amber-800 border-amber-200",
  laag:      "bg-slate-100 text-slate-600 border-slate-200",
};

const SIGNAAL_KLEUR: Record<string, string> = {
  CONVERSION_DROP_DETECTED:       "#ef4444",
  TRAFFIC_DROP_DETECTED:          "#f97316",
  SEARCH_DEMAND_HIGH_LOW_TRAFFIC: "#3b82f6",
  HIGH_TRAFFIC_LOW_CONVERSION:    "#f59e0b",
  PRICING_POWER_FROM_DEMAND:      "#10b981",
  NEW_SKU_HIGH_SEARCH_DEMAND:     "#06b6d4",
  TRAFFIC_OPPORTUNITY_HIGH:       "#22c55e",
  NO_SIGNAL:                      "#cbd5e1",
};

export default function ConversieMonitoring() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoek, setZoek] = useState("");
  const [filter, setFilter] = useState<"alle" | "hoog" | "gemiddeld">("alle");
  const { toast } = useToast();

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/conversie/signalen`, { headers: { Authorization: `Bearer ${getAuthToken()}` } });
        if (!r.ok) throw new Error();
        setData(await r.json());
      } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
      setLoading(false);
    })();
  }, []);

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-56" />
      <Skeleton className="h-64 w-full" />
    </div>
  );

  const signalen: any[] = data?.signalen || [];
  const gefilterd = signalen
    .filter(s => filter === "alle" || s.prioriteit === filter)
    .filter(s => !zoek || s.naam?.toLowerCase().includes(zoek.toLowerCase()) || s.sku_id?.toLowerCase().includes(zoek.toLowerCase()));

  const crsData = signalen.slice(0, 12).map((s: any) => ({
    naam: s.sku_id,
    crs: Math.round(s.crs * 100),
    kleur: s.crs >= 0.60 ? "#ef4444" : s.crs >= 0.40 ? "#f59e0b" : "#94a3b8",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Conversie Monitoring</h1>
        <p className="text-muted-foreground text-sm mt-1">Detecteer conversiedalingen, oorzaken en aanbevolen acties</p>
      </div>

      {/* KPI's */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="border-red-200">
          <CardContent className="pt-6">
            <p className="text-3xl font-bold text-red-600">{data?.hoge_prioriteit || 0}</p>
            <p className="text-sm text-muted-foreground">Hoge prioriteit signalen</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-3xl font-bold">{data?.totaal || 0}</p>
            <p className="text-sm text-muted-foreground">Totaal signalen</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-3xl font-bold">{signalen.filter(s => s.signaal === "CONVERSION_DROP_DETECTED").length}</p>
            <p className="text-sm text-muted-foreground">Conversiedalingen</p>
          </CardContent>
        </Card>
      </div>

      {/* CRS grafiek */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Conversie Risk Score per SKU</CardTitle>
          <CardDescription>Hoog = serieus conversierisico — monitor nauwlettend</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={crsData}>
              <XAxis dataKey="naam" fontSize={9} />
              <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} fontSize={10} />
              <Tooltip formatter={(v: number) => [`${v}%`, "CRS"]} />
              <Bar dataKey="crs" radius={[4, 4, 0, 0]}>
                {crsData.map((e, i) => <Cell key={i} fill={e.kleur} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Tabel */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <CardTitle className="text-base">Signalen Overzicht ({gefilterd.length})</CardTitle>
            <div className="flex gap-2">
              {(["alle","hoog","gemiddeld"] as const).map(f => (
                <Button key={f} size="sm" variant={filter === f ? "default" : "outline"}
                  className="h-7 text-xs capitalize" onClick={() => setFilter(f)}>{f}</Button>
              ))}
              <Input placeholder="Zoek..." value={zoek} onChange={e => setZoek(e.target.value)} className="w-40 h-7 text-xs" />
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {["SKU","Naam","Categorie","Signaal","Prioriteit","CRS","Traffic","Conversie","Prijs Index","Oorzaak","Advies",""].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gefilterd.map((s: any) => (
                  <tr key={s.sku_id} className="border-b hover:bg-muted/30">
                    <td className="py-2 px-3 font-mono text-xs">{s.sku_id}</td>
                    <td className="py-2 px-3 max-w-[160px] truncate">{s.naam}</td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">{s.categorie}</td>
                    <td className="py-2 px-3">
                      <span className="px-1.5 py-0.5 rounded-full text-xs text-white whitespace-nowrap"
                        style={{ background: SIGNAAL_KLEUR[s.signaal] || "#94a3b8" }}>
                        {s.signaal_nl}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${PRIO_BADGE[s.prioriteit]}`}>
                        {s.prioriteit}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-1">
                        <div className="w-10 bg-muted rounded-full h-1.5">
                          <div className="h-1.5 rounded-full bg-red-500" style={{ width: `${Math.round(s.crs * 100)}%` }} />
                        </div>
                        <span className="font-mono text-xs">{Math.round(s.crs * 100)}%</span>
                      </div>
                    </td>
                    <td className="py-2 px-3 text-xs font-mono">
                      <span className={s.traffic_growth >= 0 ? "text-green-600" : "text-red-600"}>
                        {s.traffic_growth >= 0 ? "+" : ""}{Math.round(s.traffic_growth * 100)}%
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs font-mono">
                      <span className={s.conv_trend >= 0 ? "text-green-600" : "text-red-600"}>
                        {s.conv_trend >= 0 ? "+" : ""}{Math.round(s.conv_trend * 100)}%
                      </span>
                    </td>
                    <td className="py-2 px-3 font-mono text-xs">{s.price_index?.toFixed(2) || "—"}</td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">{s.oorzaak || "—"}</td>
                    <td className="py-2 px-3 text-xs max-w-[180px] truncate">{s.advies}</td>
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
