import { useState, useEffect } from "react";
import { useParams, Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
} from "recharts";
import { ArrowLeft, TrendingUp, TrendingDown, Search, AlertTriangle } from "lucide-react";
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
  NO_SIGNAL:                      "#94a3b8",
};

const KEYWORD_KLEUR: Record<string, string> = {
  BRAND: "#6366f1", GENERIC: "#22c55e", EAN: "#f59e0b", MPN: "#3b82f6", CATEGORY: "#8b5cf6",
};

function ScoreBar({ score, label, kleur = "#6366f1" }: { score: number; label: string; kleur?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-36 text-muted-foreground text-xs shrink-0">{label}</span>
      <div className="flex-1 bg-muted rounded-full h-2.5">
        <div className="h-2.5 rounded-full transition-all" style={{ width: `${Math.round(score * 100)}%`, background: kleur }} />
      </div>
      <span className="font-mono text-xs font-semibold w-8 text-right">{Math.round(score * 100)}%</span>
    </div>
  );
}

function TrendPill({ val, suffix = "%" }: { val: number; suffix?: string }) {
  const isPos = val >= 0;
  const Icon = isPos ? TrendingUp : TrendingDown;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${isPos ? "text-green-600" : "text-red-600"}`}>
      <Icon className="w-3 h-3" />
      {isPos ? "+" : ""}{typeof val === "number" ? Math.round(val * 100) : "0"}{suffix}
    </span>
  );
}

export default function TrafficSkuDetail() {
  const { sku_id } = useParams<{ sku_id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    if (!sku_id) return;
    (async () => {
      try {
        const r = await fetch(`${API}/api/traffic/sku/${sku_id}`, { headers: { Authorization: `Bearer ${getAuthToken()}` } });
        if (!r.ok) throw new Error("SKU niet gevonden");
        setData(await r.json());
      } catch (e: any) { toast({ title: e.message || "Laden mislukt", variant: "destructive" }); }
      setLoading(false);
    })();
  }, [sku_id]);

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      <Skeleton className="h-64 w-full" />
    </div>
  );

  if (!data) return <div className="text-muted-foreground">SKU niet gevonden.</div>;

  const t = data.traffic || {};
  const s = data.scores || {};
  const signaal = data.signaal || {};
  const trend = data.trend || [];

  const radarData = [
    { subject: "DSS",  A: Math.round(s.dss * 100) },
    { subject: "CHS",  A: Math.round(s.chs * 100) },
    { subject: "TOS",  A: Math.round(s.tos * 100) },
    { subject: "SGS",  A: Math.round(s.sgs * 100) },
    { subject: "1-CRS",A: Math.round((1 - s.crs) * 100) },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link href="/traffic/dashboard">
          <Button variant="outline" size="sm"><ArrowLeft className="w-4 h-4 mr-2" />Terug</Button>
        </Link>
        <div>
          <h1 className="text-xl font-bold">{data.naam}</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs font-mono text-muted-foreground">{sku_id}</span>
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">{data.categorie}</span>
            {data.is_private_label && <Badge variant="outline" className="text-xs">Huismerk</Badge>}
          </div>
        </div>
      </div>

      {/* Signaal banner */}
      {signaal.code && signaal.code !== "NO_SIGNAL" && (
        <div className="rounded-lg p-4 text-white text-sm" style={{ background: SIGNAAL_KLEUR[signaal.code] || "#94a3b8" }}>
          <div className="font-semibold">{signaal.label}</div>
          <div className="mt-1 opacity-90">{signaal.uitleg}</div>
        </div>
      )}

      {/* Traffic KPI's */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Sessies (30d)", val: (t.sessies || 0).toLocaleString("nl-NL") },
          { label: "Pageviews (30d)", val: (t.pageviews || 0).toLocaleString("nl-NL") },
          { label: "Conversieratio", val: `${((t.conversieratio || 0) * 100).toFixed(2)}%` },
          { label: "Add-to-Cart", val: `${((t.add_to_cart_rate || 0) * 100).toFixed(1)}%` },
          { label: "Omzet/Bezoeker", val: `€${(t.omzet_per_bezoeker || 0).toFixed(2)}` },
          { label: "Marge/Bezoeker", val: `€${(t.marge_per_bezoeker || 0).toFixed(2)}` },
          { label: "Bounce Rate", val: `${((t.bounce_rate || 0) * 100).toFixed(0)}%` },
          { label: "Orders (30d)", val: (t.orders || 0).toLocaleString("nl-NL") },
        ].map(({ label, val }) => (
          <Card key={label}>
            <CardContent className="pt-4 pb-3">
              <p className="text-lg font-bold">{val}</p>
              <p className="text-xs text-muted-foreground">{label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Trend + Radar */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Traffic & Conversie Trend</CardTitle>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-blue-500 inline-block" /> Sessies</span>
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-green-500 inline-block" /> Orders</span>
            </div>
          </CardHeader>
          <CardContent>
            {trend.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={trend}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis dataKey="datum" fontSize={9} tickFormatter={d => d.slice(5)} />
                  <YAxis yAxisId="left" fontSize={10} />
                  <YAxis yAxisId="right" orientation="right" fontSize={10} tickFormatter={v => `${(v * 100).toFixed(1)}%`} />
                  <Tooltip labelFormatter={l => `Datum: ${l}`} />
                  <Line yAxisId="left" type="monotone" dataKey="sessies" stroke="#3b82f6" dot={false} strokeWidth={2} name="Sessies" />
                  <Line yAxisId="right" type="monotone" dataKey="conversie" stroke="#22c55e" dot={false} strokeWidth={2} name="Conversie" strokeDasharray="4 2" />
                </LineChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-muted-foreground py-8 text-center">Geen trendata beschikbaar</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Traffic Intelligence Profiel</CardTitle>
            <div className="flex items-center gap-2 mt-1">
              <TrendPill val={s.traffic_growth || 0} />
              <span className="text-xs text-muted-foreground">traffic groei</span>
              <span className="mx-1 text-muted-foreground">·</span>
              <TrendPill val={s.conversion_trend || 0} />
              <span className="text-xs text-muted-foreground">conversietrend</span>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="subject" fontSize={11} />
                <Radar name="Score" dataKey="A" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Score bars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle className="text-base">Traffic Intelligence Scores</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <ScoreBar score={s.dss || 0} label="Demand Signal Score" kleur="#6366f1" />
            <ScoreBar score={s.chs || 0} label="Conversion Health Score" kleur="#22c55e" />
            <ScoreBar score={s.tos || 0} label="Traffic Opportunity Score" kleur="#f59e0b" />
            <ScoreBar score={s.crs || 0} label="Conversion Risk Score" kleur="#ef4444" />
            <ScoreBar score={s.sgs || 0} label="Search Gap Score" kleur="#3b82f6" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Externe Factoren</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {data.concurrentie?.pcis_score != null && (
              <ScoreBar score={data.concurrentie.pcis_score} label="PCIS (concurrentiedruk)" kleur="#f97316" />
            )}
            <div className="pt-2 space-y-2 text-sm">
              {data.concurrentie?.price_index && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground text-xs">Prijsindex</span>
                  <span className={`font-mono text-xs font-semibold ${data.concurrentie.price_index > 1.05 ? "text-red-600" : "text-green-600"}`}>
                    {data.concurrentie.price_index.toFixed(3)}
                  </span>
                </div>
              )}
              {data.elasticiteit?.own != null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground text-xs">Prijselasticiteit</span>
                  <span className="font-mono text-xs font-semibold">{data.elasticiteit.own.toFixed(2)}</span>
                </div>
              )}
              {data.bcg?.hybrid_class && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground text-xs">BCG-klasse</span>
                  <span className="text-xs">{data.bcg.hybrid_class}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Adviezen */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {data.pricing_advies?.actie && (
          <Card className="border-l-4 border-l-primary">
            <CardHeader>
              <CardTitle className="text-sm">Prijsadvies</CardTitle>
              <CardDescription>{data.pricing_advies.actie_nl}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">{data.pricing_advies.toelichting}</p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Prioriteit:</span>
                <Badge variant="outline" className="text-xs capitalize">{data.pricing_advies.prioriteit}</Badge>
              </div>
            </CardContent>
          </Card>
        )}

        {data.promotie_advies?.actie && (
          <Card className="border-l-4 border-l-purple-500">
            <CardHeader>
              <CardTitle className="text-sm">Promotieadvies</CardTitle>
              <CardDescription>{data.promotie_advies.actie_nl}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">{data.promotie_advies.toelichting}</p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Prioriteit:</span>
                <Badge variant="outline" className="text-xs capitalize">{data.promotie_advies.prioriteit}</Badge>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Search demand keywords */}
      {data.search_demand?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Search className="w-4 h-4" />Externe Zoekvraag
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {["Keyword","Type","Volume/mnd","Impressies","Klikken","CTR","Positie","Trend","Concurrentie","CPC"].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.search_demand.map((kw: any, i: number) => (
                  <tr key={i} className="border-b hover:bg-muted/30">
                    <td className="py-2 px-3 font-medium text-sm max-w-[200px] truncate">{kw.keyword}</td>
                    <td className="py-2 px-3">
                      <span className="text-xs px-1.5 py-0.5 rounded-full text-white" style={{ background: KEYWORD_KLEUR[kw.type] || "#94a3b8" }}>
                        {kw.type}
                      </span>
                    </td>
                    <td className="py-2 px-3 font-mono text-xs">{(kw.volume || 0).toLocaleString("nl-NL")}</td>
                    <td className="py-2 px-3 font-mono text-xs">{(kw.impressies || 0).toLocaleString("nl-NL")}</td>
                    <td className="py-2 px-3 font-mono text-xs">{(kw.klikken || 0).toLocaleString("nl-NL")}</td>
                    <td className="py-2 px-3 font-mono text-xs">{((kw.ctr || 0) * 100).toFixed(1)}%</td>
                    <td className="py-2 px-3 font-mono text-xs">{(kw.positie || 0).toFixed(1)}</td>
                    <td className="py-2 px-3">
                      <div className="w-12 bg-muted rounded-full h-1.5">
                        <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${Math.round((kw.trend || 0) * 100)}%` }} />
                      </div>
                    </td>
                    <td className="py-2 px-3">
                      <div className="w-12 bg-muted rounded-full h-1.5">
                        <div className="h-1.5 rounded-full bg-orange-500" style={{ width: `${Math.round((kw.concurrentie || 0) * 100)}%` }} />
                      </div>
                    </td>
                    <td className="py-2 px-3 font-mono text-xs">€{(kw.cpc || 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
