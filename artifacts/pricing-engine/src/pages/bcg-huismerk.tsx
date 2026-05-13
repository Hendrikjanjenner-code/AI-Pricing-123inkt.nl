import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { Tag, TrendingUp, ArrowRightLeft, Star } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const PL_KLEUR: Record<string, string> = {
  "PRIVATE_LABEL_STAR":         "#8b5cf6",
  "PRIVATE_LABEL_GROWTH":       "#22c55e",
  "PRIVATE_LABEL_DEFENSIVE":    "#f59e0b",
  "PRIVATE_LABEL_LOW_PRIORITY": "#94a3b8",
};
const PL_KLEUR_NL: Record<string, string> = {
  "Huismerk Ster":             "#8b5cf6",
  "Huismerk Groei":            "#22c55e",
  "Huismerk Defensief":        "#f59e0b",
  "Huismerk Laag Prioriteit":  "#94a3b8",
};

export default function BcgHuismerk() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoek, setZoek] = useState("");
  const { toast } = useToast();

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/bcg/huismerk`, {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
        });
        if (!r.ok) throw new Error();
        setData(await r.json());
      } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
      setLoading(false);
    })();
  }, []);

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-64" />
      <div className="grid grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
      <Skeleton className="h-80 w-full" />
    </div>
  );

  const items: any[] = data?.items || [];
  const tellingen = data?.tellingen || {};
  const gefilterd = zoek
    ? items.filter(i => i.naam.toLowerCase().includes(zoek.toLowerCase()) || i.sku_id.toLowerCase().includes(zoek.toLowerCase()))
    : items;

  const grafiekData = items.map(i => ({
    naam: i.sku_id,
    plsv: Math.round(i.plsv * 100),
    kleur: PL_KLEUR[i.klasse] || "#94a3b8",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Huismerk Intelligence</h1>
        <p className="text-muted-foreground text-sm mt-1">
          PLSV-scores, substitutiepotentie en traffic-to-margin strategieën voor 123inkt huismerken
        </p>
      </div>

      {/* KPI tellers */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Huismerk Sterren", key: "Huismerk Ster", icon: Star, kleur: "text-purple-600 bg-purple-50" },
          { label: "Groei Potentie", key: "Huismerk Groei", icon: TrendingUp, kleur: "text-green-600 bg-green-50" },
          { label: "Defensief", key: "Huismerk Defensief", icon: ArrowRightLeft, kleur: "text-amber-600 bg-amber-50" },
          { label: "Laag Prioriteit", key: "Huismerk Laag Prioriteit", icon: Tag, kleur: "text-slate-600 bg-slate-100" },
        ].map(({ label, key, icon: Icon, kleur }) => (
          <Card key={key}>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${kleur}`}><Icon className="w-5 h-5" /></div>
                <div>
                  <p className="text-2xl font-bold">{tellingen[key] ?? 0}</p>
                  <p className="text-sm text-muted-foreground">{label}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* PLSV staafgrafiek */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Private Label Strategic Value Score (PLSV)</CardTitle>
          <CardDescription>Schaal 0–100% — hoger = meer strategische huismerkwaarde</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={grafiekData}>
              <XAxis dataKey="naam" fontSize={10} />
              <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} fontSize={10} />
              <Tooltip formatter={(v: number) => [`${v}%`, "PLSV"]} />
              <Bar dataKey="plsv" radius={[4, 4, 0, 0]}>
                {grafiekData.map((e, i) => <Cell key={i} fill={e.kleur} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Tabel */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Huismerk SKU Overzicht ({items.length} SKU's)</CardTitle>
            <Input
              placeholder="Zoek..."
              value={zoek}
              onChange={e => setZoek(e.target.value)}
              className="w-48 h-8 text-sm"
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {["SKU", "Naam", "Categorie", "Klasse", "PLSV", "Overstapkans", "Margeverschil", "ISV", "A-merk", "Strategie", ""].map(h => (
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
                    <td className="py-2 px-3">
                      <span
                        className="px-2 py-0.5 rounded-full text-xs font-medium text-white whitespace-nowrap"
                        style={{ background: PL_KLEUR_NL[item.klasse_nl] || "#94a3b8" }}
                      >
                        {item.klasse_nl}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 bg-muted rounded-full h-1.5">
                          <div className="h-1.5 rounded-full bg-purple-500" style={{ width: `${Math.round(item.plsv * 100)}%` }} />
                        </div>
                        <span className="font-mono text-xs">{Math.round(item.plsv * 100)}%</span>
                      </div>
                    </td>
                    <td className="py-2 px-3 font-mono text-xs">{Math.round(item.overstapkans * 100)}%</td>
                    <td className="py-2 px-3 font-mono text-xs">€{item.margeverschil?.toFixed(2)}</td>
                    <td className="py-2 px-3 font-mono text-xs">{item.isv?.toFixed(3)}</td>
                    <td className="py-2 px-3 text-xs text-muted-foreground font-mono">{item.a_brand_sku || "—"}</td>
                    <td className="py-2 px-3 text-xs max-w-[140px] truncate">{item.strategie || "—"}</td>
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

      {/* Uitleg */}
      <Card className="bg-purple-50 border-purple-200">
        <CardContent className="pt-4 pb-4">
          <p className="text-sm font-semibold text-purple-800 mb-2">Traffic-to-Margin Strategie (123inkt)</p>
          <p className="text-xs text-purple-700">
            Huismerk Sterren met hoge PLSV (&gt;70%) worden gepromoot via de A-merk pagina als goedkoper alternatief.
            De ISV (Internal Substitution Value) meet hoeveel marge er gewonnen wordt bij een succesvolle switch.
            SKU's met PLSV &gt;70% krijgen automatisch de strategie <strong>PRIVATE_LABEL_PUSH</strong>.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
