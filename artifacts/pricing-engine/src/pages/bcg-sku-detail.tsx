import { useState, useEffect } from "react";
import { useParams, Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip } from "recharts";
import { ArrowLeft, Star, Shield, Zap, Tag, TrendingDown, Target } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const BCG_KLEUR: Record<string, string> = {
  PRICING_POWER_STAR:          "#22c55e",
  DEFENSIVE_CASH_COW:          "#f59e0b",
  PRIVATE_LABEL_STAR:          "#8b5cf6",
  EXPERIMENTAL_QUESTION_MARK:  "#3b82f6",
  LOW_PRIORITY_DOG:            "#94a3b8",
  INTERNAL_STAR:               "#22c55e",
  INTERNAL_CASH_COW:           "#f59e0b",
  INTERNAL_QUESTION_MARK:      "#3b82f6",
  INTERNAL_DOG:                "#94a3b8",
  EXTERNAL_STAR:               "#10b981",
  EXTERNAL_CASH_COW:           "#f97316",
  EXTERNAL_QUESTION_MARK:      "#6366f1",
  EXTERNAL_DOG:                "#64748b",
};

const STRATEGIE_UITLEG: Record<string, string> = {
  PROTECT_MARGIN:            "Bescherm de huidige winstmarge — geen agressieve kortingen.",
  DEFEND_MARKET_POSITION:    "Volg concurrentieprijzen actief om marktpositie te behouden.",
  PRIVATE_LABEL_PUSH:        "Stuur traffic naar huismerk-alternatief voor hogere marge.",
  EXPERIMENT_PRICE_INCREASE: "Test geleidelijke prijsverhoging om elasticiteit te meten.",
  COMPETITIVE_PRICE_MATCH:   "Match de concurrentieprijs om marktaandeel te behouden.",
  LOW_PRIORITY_AUTOMATION:   "Minimale pricing-aandacht — eventueel clearance pricing.",
};

function ScoreBalk({ label, score, kleur = "#6366f1" }: { label: string; score: number; kleur?: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-muted-foreground w-36 shrink-0">{label}</span>
      <div className="flex-1 bg-muted rounded-full h-2.5">
        <div
          className="h-2.5 rounded-full transition-all"
          style={{ width: `${Math.round(score * 100)}%`, background: kleur }}
        />
      </div>
      <span className="text-xs font-mono w-10 text-right">{Math.round(score * 100)}%</span>
    </div>
  );
}

export default function BcgSkuDetail() {
  const { sku_id } = useParams<{ sku_id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    if (!sku_id) return;
    (async () => {
      try {
        const r = await fetch(`${API}/api/bcg/sku/${sku_id}`, {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
        });
        if (!r.ok) throw new Error();
        setData(await r.json());
      } catch { toast({ title: "SKU niet gevonden", variant: "destructive" }); }
      setLoading(false);
    })();
  }, [sku_id]);

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-48" />
      <div className="grid grid-cols-3 gap-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-32" />)}</div>
      <Skeleton className="h-64 w-full" />
    </div>
  );

  if (!data) return <div className="text-muted-foreground">SKU niet gevonden.</div>;

  const scores = data.scores || {};
  const radarData = [
    { subject: "IBSS", score: Math.round(scores.ibss * 100) },
    { subject: "GPS", score: Math.round(scores.gps * 100) },
    { subject: "CSS", score: Math.round(scores.css_external * 100) },
    { subject: "MOS", score: Math.round(scores.mos * 100) },
    { subject: "Pricing Power", score: Math.round(scores.pricing_power * 100) },
    { subject: "PLSV", score: Math.round((scores.plsv || 0) * 100) },
  ];

  const cl = data.classificaties;
  const concurrentie = data.concurrentie || {};
  const elast = data.elasticiteit || {};
  const huismerk = data.huismerk;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/bcg/sku-matrix">
          <Button variant="outline" size="sm"><ArrowLeft className="w-4 h-4 mr-2" />Terug</Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">{data.naam}</h1>
          <p className="text-muted-foreground text-sm">{sku_id} · {data.categorie} · {data.run_date}</p>
        </div>
      </div>

      {/* Drie BCG classificaties */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: "Interne BCG", obj: cl?.intern, icon: Shield },
          { label: "Externe BCG", obj: cl?.extern, icon: Target },
          { label: "Hybride Pricing BCG", obj: cl?.hybrid, icon: Star },
        ].map(({ label, obj, icon: Icon }) => obj && (
          <Card key={label} className="border-l-4" style={{ borderLeftColor: obj.kleur }}>
            <CardContent className="pt-5 pb-5">
              <div className="flex items-center gap-2 mb-2">
                <Icon className="w-4 h-4" style={{ color: obj.kleur }} />
                <span className="text-xs text-muted-foreground">{label}</span>
              </div>
              <p className="text-xl font-bold">{obj.klasse_nl}</p>
              <p className="text-xs font-mono text-muted-foreground mt-1">{obj.klasse}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Pricingstrategie */}
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="pt-5 pb-5">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-primary/10 rounded-lg"><Zap className="w-5 h-5 text-primary" /></div>
            <div className="flex-1">
              <p className="text-xs text-muted-foreground mb-1">Aanbevolen pricingstrategie</p>
              <p className="text-xl font-bold">{data.pricingstrategie?.strategie_nl}</p>
              <p className="text-sm text-muted-foreground mt-1">
                {STRATEGIE_UITLEG[data.pricingstrategie?.strategie || ""] || ""}
              </p>
            </div>
            <Badge variant={data.pricingstrategie?.prioriteit === "hoog" ? "destructive" : data.pricingstrategie?.prioriteit === "gemiddeld" ? "secondary" : "outline"}>
              {data.pricingstrategie?.prioriteit}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Scores */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle className="text-base">Score Overzicht</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              <ScoreBalk label="IBSS (Interne kracht)" score={scores.ibss} kleur="#6366f1" />
              <ScoreBalk label="GPS (Groeipotentieel)" score={scores.gps} kleur="#22c55e" />
              <ScoreBalk label="CSS (Concurrentiesterkte)" score={scores.css_external} kleur="#f59e0b" />
              <ScoreBalk label="MOS (Marktkans)" score={scores.mos} kleur="#3b82f6" />
              <ScoreBalk label="Pricing Power" score={scores.pricing_power} kleur="#f97316" />
              {scores.plsv > 0 && <ScoreBalk label="PLSV (Huismerkwaarde)" score={scores.plsv} kleur="#8b5cf6" />}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Score Radar</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="subject" fontSize={11} />
                <Radar name={sku_id} dataKey="score" stroke="#6366f1" fill="#6366f1" fillOpacity={0.25} />
                <Tooltip formatter={(v: number) => [`${v}%`]} />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Concurrentie + Elasticiteit */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="w-4 h-4" />Concurrentie Context
            </CardTitle>
          </CardHeader>
          <CardContent>
            {concurrentie.pcis_score != null ? (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">PCIS Score</span>
                  <span className="font-semibold">{Math.round(concurrentie.pcis_score * 100)}%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Concurrentieklasse</span>
                  <Badge variant="outline">{concurrentie.competition_class || "—"}</Badge>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Prijsindex</span>
                  <span className="font-semibold font-mono">{concurrentie.price_index?.toFixed(2) || "—"}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Concurrenten</span>
                  <span className="font-semibold">{concurrentie.competitors_used}</span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Geen concurrentiedata beschikbaar.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingDown className="w-4 h-4" />Elasticiteit
            </CardTitle>
          </CardHeader>
          <CardContent>
            {elast.own != null ? (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Eigen elasticiteit</span>
                  <span className="font-semibold font-mono">{elast.own?.toFixed(2)}</span>
                </div>
                {elast.cross != null && (
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Kruiselasticiteit</span>
                    <span className="font-semibold font-mono">{elast.cross?.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Betrouwbaarheid</span>
                  <Badge variant="outline">{elast.confidence_class || "—"}</Badge>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Geen elasticiteitsdata beschikbaar.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Huismerk intelligence */}
      {huismerk && (
        <Card className="border-purple-200">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Tag className="w-4 h-4 text-purple-600" />Huismerk Intelligence
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">PLSV Score</p>
                <p className="text-xl font-bold text-purple-700">{Math.round((huismerk.plsv || 0) * 100)}%</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Klasse</p>
                <p className="font-semibold text-sm">{huismerk.klasse}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Overstapkans</p>
                <p className="text-xl font-bold">{Math.round((huismerk.overstapkans || 0) * 100)}%</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Margeverschil</p>
                <p className="text-xl font-bold">€{huismerk.margeverschil?.toFixed(2)}</p>
              </div>
            </div>
            {huismerk.a_brand_sku && (
              <div className="mt-3 text-xs text-muted-foreground">
                Gekoppeld A-merk: <span className="font-mono font-medium">{huismerk.a_brand_sku}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Geschiedenis */}
      {data.geschiedenis?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">BCG Wijzigingshistorie</CardTitle></CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-xs">
              <thead className="bg-muted/50">
                <tr>
                  {["Datum", "Type", "Van", "Naar", "Reden"].map(h => (
                    <th key={h} className="text-left py-2 px-3 font-medium text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.geschiedenis.map((h: any, i: number) => (
                  <tr key={i} className="border-b">
                    <td className="py-2 px-3 font-mono">{h.datum}</td>
                    <td className="py-2 px-3">{h.type}</td>
                    <td className="py-2 px-3">
                      <span className="px-1.5 py-0.5 rounded text-white text-xs" style={{ background: BCG_KLEUR[h.oud] || "#94a3b8" }}>
                        {h.oud}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <span className="px-1.5 py-0.5 rounded text-white text-xs" style={{ background: BCG_KLEUR[h.nieuw] || "#6366f1" }}>
                        {h.nieuw}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-muted-foreground max-w-[200px] truncate">{h.reden}</td>
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
