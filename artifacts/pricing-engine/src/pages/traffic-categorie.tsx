import { useState, useEffect } from "react";
import { useParams, Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { ArrowLeft } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const CATEGORIES = [
  "Ink & Toner", "Office Supplies", "Paper", "Packaging",
  "Cleaning", "Furniture", "Electronics", "Canvas & Art", "Printers",
];

const SIGNAAL_KLEUR: Record<string, string> = {
  CONVERSION_DROP_DETECTED:       "#ef4444",
  TRAFFIC_DROP_DETECTED:          "#f97316",
  SEARCH_DEMAND_HIGH_LOW_TRAFFIC: "#3b82f6",
  HIGH_TRAFFIC_LOW_CONVERSION:    "#f59e0b",
  PRICING_POWER_FROM_DEMAND:      "#10b981",
  NEW_SKU_HIGH_SEARCH_DEMAND:     "#06b6d4",
  TRAFFIC_OPPORTUNITY_HIGH:       "#22c55e",
  NO_SIGNAL:                      "#94a3b8",
};

export default function TrafficCategorie() {
  const params = useParams<{ category?: string }>();
  const [selectedCat, setSelectedCat] = useState(params.category || CATEGORIES[0]);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => { laden(selectedCat); }, [selectedCat]);

  async function laden(cat: string) {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/traffic/categorie/${encodeURIComponent(cat)}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      if (!r.ok) throw new Error();
      setData(await r.json());
    } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
    setLoading(false);
  }

  const t = data?.traffic || {};
  const breakdown: any[] = data?.sku_breakdown || [];

  const dssData = breakdown.map(s => ({
    naam: s.sku_id,
    dss: Math.round(s.dss * 100),
    chs: Math.round(s.chs * 100),
    crs: Math.round(s.crs * 100),
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/traffic/dashboard">
          <Button variant="outline" size="sm"><ArrowLeft className="w-4 h-4 mr-2" />Terug</Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">Categorie Traffic Analyse</h1>
        </div>
        <Select value={selectedCat} onValueChange={setSelectedCat}>
          <SelectTrigger className="w-52"><SelectValue /></SelectTrigger>
          <SelectContent>
            {CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <>
          {/* Traffic KPI's */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Sessies (30d)", val: (t.sessies || 0).toLocaleString("nl-NL") },
              { label: "Pageviews", val: (t.pageviews || 0).toLocaleString("nl-NL") },
              { label: "Orders", val: (t.orders || 0).toLocaleString("nl-NL") },
              { label: "Conversieratio", val: `${((t.conversieratio || 0) * 100).toFixed(2)}%` },
              { label: "Omzet (30d)", val: `€${(t.omzet || 0).toLocaleString("nl-NL", { minimumFractionDigits: 0 })}` },
              { label: "Marge (30d)", val: `€${(t.marge || 0).toLocaleString("nl-NL", { minimumFractionDigits: 0 })}` },
              { label: "SKU's", val: data?.totaal_skus || 0 },
              { label: "DSS Gem.", val: `${Math.round((data?.scores?.dss || 0) * 100)}%` },
            ].map(({ label, val }) => (
              <Card key={label}>
                <CardContent className="pt-4 pb-3">
                  <p className="text-xl font-bold">{val}</p>
                  <p className="text-xs text-muted-foreground">{label}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Scores grafiek */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">DSS / CHS / CRS per SKU in {selectedCat}</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={dssData}>
                  <XAxis dataKey="naam" fontSize={9} />
                  <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} fontSize={10} />
                  <Tooltip formatter={(v: number, name: string) => [`${v}%`, name.toUpperCase()]} />
                  <Bar dataKey="dss" fill="#6366f1" name="dss" radius={[2, 2, 0, 0]} />
                  <Bar dataKey="chs" fill="#22c55e" name="chs" radius={[2, 2, 0, 0]} />
                  <Bar dataKey="crs" fill="#ef4444" name="crs" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="flex gap-4 text-xs text-muted-foreground mt-2 justify-center">
                {[["#6366f1","DSS — Demand Signal"],["#22c55e","CHS — Conversie Health"],["#ef4444","CRS — Conversie Risico"]].map(([c,l]) => (
                  <span key={l} className="flex items-center gap-1">
                    <span className="w-3 h-2 rounded-sm inline-block" style={{ background: c }} />{l}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* SKU Breakdown */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">SKU Breakdown — {selectedCat}</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    {["SKU","Naam","DSS","CHS","CRS","SGS","Signaal",""].map(h => (
                      <th key={h} className="text-left py-2 px-3 text-xs font-medium text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {breakdown.map((s: any) => (
                    <tr key={s.sku_id} className="border-b hover:bg-muted/30">
                      <td className="py-2 px-3 font-mono text-xs">{s.sku_id}</td>
                      <td className="py-2 px-3 max-w-[200px] truncate">{s.naam}</td>
                      {["dss","chs","crs","sgs"].map(k => (
                        <td key={k} className="py-2 px-3">
                          <div className="flex items-center gap-1">
                            <div className="w-12 bg-muted rounded-full h-1.5">
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
                      <td className="py-2 px-3">
                        <Link href={`/traffic/sku/${s.sku_id}`}>
                          <Button variant="ghost" size="sm" className="h-6 text-xs px-2">Detail</Button>
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {breakdown.length === 0 && (
                    <tr><td colSpan={8} className="py-8 text-center text-sm text-muted-foreground">Geen data voor deze categorie</td></tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
