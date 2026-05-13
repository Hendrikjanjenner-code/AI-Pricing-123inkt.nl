import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { Star, TrendingUp, Shield, HelpCircle, AlertTriangle, Zap, RefreshCw, Tag } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const HYBRID_KLEUR: Record<string, string> = {
  "Pricing Power Ster":        "#22c55e",
  "Defensieve Cash Cow":       "#f59e0b",
  "Huismerk Ster":             "#8b5cf6",
  "Experimenteel Vraagteken":  "#3b82f6",
  "Lage Prioriteit Dog":       "#94a3b8",
};

const ALERT_TYPE_NL: Record<string, string> = {
  SKU_MOVED_TO_DOG:         "SKU verplaatst naar Dog",
  PRICING_POWER_INCREASED:  "Pricing power gestegen",
  PRIVATE_LABEL_OPPORTUNITY:"Huismerk kans",
};

function ScoreRing({ score, kleur = "#22c55e", label }: { score: number; kleur?: string; label: string }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-16 h-16">
        <svg viewBox="0 0 36 36" className="w-16 h-16 -rotate-90">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e2e8f0" strokeWidth="3" />
          <circle
            cx="18" cy="18" r="15.9" fill="none"
            stroke={kleur} strokeWidth="3"
            strokeDasharray={`${pct} ${100 - pct}`}
            strokeLinecap="round"
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-sm font-bold">{pct}%</span>
      </div>
      <span className="text-xs text-muted-foreground text-center">{label}</span>
    </div>
  );
}

export default function BcgDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const { toast } = useToast();

  useEffect(() => { laden(); }, []);

  async function laden() {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/bcg/dashboard`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      if (!r.ok) throw new Error(await r.text());
      setData(await r.json());
    } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
    setLoading(false);
  }

  async function startRun() {
    setRunning(true);
    try {
      const r = await fetch(`${API}/api/bcg/run`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      if (!r.ok) throw new Error(await r.text());
      toast({ title: "BCG engine uitgevoerd", description: "Data is bijgewerkt." });
      await laden();
    } catch { toast({ title: "Run mislukt", variant: "destructive" }); }
    setRunning(false);
  }

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-64" />
      <div className="grid grid-cols-5 gap-4">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-32" />)}</div>
      <div className="grid grid-cols-2 gap-6">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-64" />)}</div>
    </div>
  );

  const hybridGrafiek = Object.entries(data?.hybrid_counts || {}).map(([k, v]) => ({
    naam: k, aantal: v as number, kleur: HYBRID_KLEUR[k] || "#94a3b8",
  }));

  const internalGrafiek = Object.entries(data?.internal_counts || {}).map(([k, v]) => ({
    naam: k.replace("Intern", "").trim(), aantal: v as number,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">BCG Intelligence Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Portfolio-analyse: pricing power, groei, concurrentiedruk en huismerkpotentie
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={laden}><RefreshCw className="w-4 h-4 mr-2" />Vernieuwen</Button>
          <Button size="sm" onClick={startRun} disabled={running}>
            <Zap className="w-4 h-4 mr-2" />{running ? "Bezig..." : "BCG Engine Uitvoeren"}
          </Button>
        </div>
      </div>

      {/* KPI kaarten: interne BCG */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Interne Sterren", key: "Interne Ster", icon: Star, kleur: "text-green-600 bg-green-50" },
          { label: "Cash Cows", key: "Interne Cash Cow", icon: Shield, kleur: "text-amber-600 bg-amber-50" },
          { label: "Vraagtekens", key: "Intern Vraagteken", icon: HelpCircle, kleur: "text-blue-600 bg-blue-50" },
          { label: "Dogs", key: "Interne Dog", icon: AlertTriangle, kleur: "text-slate-600 bg-slate-100" },
        ].map(({ label, key, icon: Icon, kleur }) => (
          <Card key={key}>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${kleur}`}><Icon className="w-5 h-5" /></div>
                <div>
                  <p className="text-2xl font-bold">{data?.internal_counts?.[key] ?? 0}</p>
                  <p className="text-sm text-muted-foreground">{label}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Grafieken */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle className="text-base">Hybride BCG Verdeling</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={hybridGrafiek} layout="vertical">
                <XAxis type="number" fontSize={11} />
                <YAxis type="category" dataKey="naam" width={160} fontSize={10} />
                <Tooltip />
                <Bar dataKey="aantal" radius={[0, 4, 4, 0]}>
                  {hybridGrafiek.map((e, i) => <Cell key={i} fill={e.kleur} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Interne BCG Verdeling</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={internalGrafiek}>
                <XAxis dataKey="naam" fontSize={10} />
                <YAxis fontSize={11} />
                <Tooltip />
                <Bar dataKey="aantal" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Top Pricing Power + Huismerk Stars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" />Top Pricing Power SKU's
            </CardTitle>
            <CardDescription>SKU's met de hoogste prijszettingsvrijheid</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(data?.top_pricing_power || []).map((sku: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium truncate max-w-[200px]">{sku.naam}</p>
                    <p className="text-xs text-muted-foreground">{sku.strategie}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-20 bg-muted rounded-full h-2">
                      <div className="bg-amber-500 h-2 rounded-full" style={{ width: `${Math.round(sku.score * 100)}%` }} />
                    </div>
                    <span className="text-xs font-mono w-10 text-right">{Math.round(sku.score * 100)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Tag className="w-4 h-4 text-purple-500" />Top Huismerk Sterren
            </CardTitle>
            <CardDescription>Huismerk SKU's met hoogste substitutiepotentie</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(data?.top_private_label_stars || []).map((pl: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium font-mono">{pl.sku_id}</p>
                    <p className="text-xs text-muted-foreground">{pl.klasse} · overstapkans {Math.round(pl.overstapkans * 100)}%</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-20 bg-muted rounded-full h-2">
                      <div className="bg-purple-500 h-2 rounded-full" style={{ width: `${Math.round(pl.plsv * 100)}%` }} />
                    </div>
                    <span className="text-xs font-mono w-10 text-right">{Math.round(pl.plsv * 100)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Alerts + Hoge concurrentiedruk */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" />BCG Alerts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(data?.alerts || []).length === 0 && (
                <p className="text-sm text-muted-foreground">Geen actieve alerts.</p>
              )}
              {(data?.alerts || []).map((a: any, i: number) => (
                <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-muted/40">
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: a.kleur }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium">{ALERT_TYPE_NL[a.type] || a.type}</p>
                    <p className="text-xs text-muted-foreground truncate">{a.naam}</p>
                  </div>
                  <Link href={`/bcg/sku/${a.sku_id}`}>
                    <Button variant="ghost" size="sm" className="h-6 text-xs px-2">Detail</Button>
                  </Link>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-orange-500" />Hoge Concurrentiedruk Categorieën
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(data?.hoog_concurrentiedruk_categories || []).length === 0 && (
                <p className="text-sm text-muted-foreground">Geen hoge druk categorieën gevonden.</p>
              )}
              {(data?.hoog_concurrentiedruk_categories || []).map((cat: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium">{cat.categorie}</p>
                    <p className="text-xs text-muted-foreground">{cat.klasse}</p>
                  </div>
                  <Badge variant="destructive">{Math.round(cat.css_score * 100)}% sterkte</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Snelkoppelingen */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {[
          { href: "/bcg/sku-matrix", label: "SKU BCG Matrix", desc: "Scatter plot intern / extern / hybrid", icon: Star },
          { href: "/bcg/categorie", label: "Categorie Analyse", desc: "BCG per productcategorie", icon: Shield },
          { href: "/bcg/hybrid", label: "Hybrid Pricing Matrix", desc: "Pricing power vs concurrentiedruk", icon: Zap },
          { href: "/bcg/huismerk", label: "Huismerk Intelligence", desc: "PLSV scores en substitutiepotentie", icon: Tag },
          { href: "/bcg/pricing-power", label: "Pricing Power", desc: "Ranglijst SKU's op pricing power", icon: TrendingUp },
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
