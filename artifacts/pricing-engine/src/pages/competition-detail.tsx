import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useParams, Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell
} from "recharts";
import { ArrowLeft, CheckCircle2, XCircle, AlertTriangle, Calculator } from "lucide-react";
import { useShopId } from "@/hooks/use-shop-id";

const KLASSE_KLEUREN: Record<string, string> = {
  Critical: "bg-red-500/15 text-red-700 border-red-300",
  Strong: "bg-orange-500/15 text-orange-700 border-orange-300",
  Influence: "bg-amber-500/15 text-amber-700 border-amber-300",
  Monitor: "bg-blue-500/15 text-blue-700 border-blue-300",
  Ignore: "bg-slate-100 text-slate-500 border-slate-200",
};

const KLASSE_LABELS_NL: Record<string, string> = {
  Critical: "Kritiek",
  Strong: "Sterk",
  Influence: "Invloed",
  Monitor: "Bewaken",
  Ignore: "Negeren",
};

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const SUB_SCORE_LABELS_NL: Record<string, string> = {
  product_comparability_score: "Productvergelijkbaarheid",
  price_sensitivity_score: "Prijsgevoeligheid",
  substitution_score: "Substitutierisico",
  competitor_relevance_score: "Concurrentenrelevantie",
  competitor_price_reliability_score: "Prijsbetrouwbaarheid",
  basket_dependency_score: "Mandkoppelingsfactor",
  strategic_importance_score: "Strategisch belang",
};

const UITSLUITINGS_LABELS: Record<string, string> = {
  COMPETITOR_IGNORED_OUT_OF_STOCK: "Niet op voorraad",
  COMPETITOR_IGNORED_BAD_MATCH: "Slechte overeenkomst",
  COMPETITOR_IGNORED_OUTLIER: "Uitbijterprijs (>30% afwijking)",
  COMPETITOR_IGNORED_LOW_RELEVANCE: "Lage relevantie",
  COMPETITOR_IGNORED_DIFFERENT_PACK_SIZE: "Andere verpakkingsgrootte",
  COMPETITOR_IGNORED_BAD_DELIVERY: "Onaanvaardbare levering",
  COMPETITOR_IGNORED_LOW_CSRS: "Lage voorraadbetrouwbaarheid (CSRS)",
  COMPETITOR_IGNORED_LOW_CSS: "Lage prijsduurzaamheid (CSS)",
};

const METHODE_LABELS: Record<string, string> = {
  regressie: "Regressie",
  heuristiek: "Heuristiek",
  default: "Standaardwaarde",
};
export default function ConcurrentieDetail() {
  const shopId = useShopId();
  const params = useParams<{ sku_id: string }>();
  const skuId = params.sku_id;

  const { data, isLoading } = useQuery({
    queryKey: ["competition-detail", skuId, shopId],
    queryFn: () => apiFetch(`/api/competition/skus/${skuId}${shopId !== undefined ? `?shop_id=${shopId}` : ""}`),
    enabled: !!skuId,
  });

  if (isLoading) return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-2 gap-4">{[1,2,3,4].map(i => <Skeleton key={i} className="h-28" />)}</div>
      <Skeleton className="h-64" />
    </div>
  );

  const { product, competition_score: score, competitor_detail } = data || {};

  if (!product || !score) return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <p className="text-muted-foreground">Geen concurrentiedata voor <strong>{skuId}</strong>.</p>
      <Link href={`/concurrentie${shopId !== undefined ? `?shop_id=${shopId}` : ""}`}><Button variant="outline"><ArrowLeft className="h-4 w-4 mr-2" />Terug</Button></Link>
    </div>
  );

  const subScores = Object.entries(SUB_SCORE_LABELS_NL).map(([key, label]) => ({
    label, key, value: score[key] || 0,
  }));

  const radarData = subScores.map(s => ({ subject: s.label, value: Math.round(s.value * 100), fullMark: 100 }));

  const opgenomen = (competitor_detail || []).filter((c: any) => !c.is_excluded);
  const uitgesloten = (competitor_detail || []).filter((c: any) => c.is_excluded);

  const piKleur = score.price_index > 1.03 ? "text-emerald-600" : score.price_index < 0.97 ? "text-red-600" : "text-foreground";

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <Link href={`/concurrentie${shopId !== undefined ? `?shop_id=${shopId}` : ""}`}>
          <Button variant="ghost" size="sm" className="mt-1">
            <ArrowLeft className="h-4 w-4 mr-1" /> Terug
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{product.product_name}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
            <span>{product.sku_id}</span><span>·</span>
            <span>{product.brand}</span><span>·</span>
            <span>{product.category}</span>
            {product.ean && (<><span>·</span><span>EAN {product.ean}</span></>)}
            {product.oem_code && (<><span>·</span><span>OEM {product.oem_code}</span></>)}
            {product.is_a_brand && <Badge variant="outline" className="text-xs">A-merk</Badge>}
            {product.is_private_label && <Badge variant="outline" className="text-xs">Huismerk</Badge>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">PCIS-score</CardTitle></CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{(score.pcis_score * 100).toFixed(0)}</div>
            <div className="mt-1">
              <Badge variant="outline" className={`text-xs ${KLASSE_KLEUREN[score.competition_class] || ""}`}>
                {KLASSE_LABELS_NL[score.competition_class] || score.competition_class}
              </Badge>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Prijsindex</CardTitle></CardHeader>
          <CardContent>
            <div className={`text-3xl font-bold ${piKleur}`}>{score.price_index?.toFixed(3) ?? "—"}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {score.price_index > 1.03 ? "Boven marktprijs" : score.price_index < 0.97 ? "Onder marktprijs" : "Op marktprijsniveau"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Eigen prijs</CardTitle></CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">€{product.current_price?.toFixed(2)}</div>
            <p className="text-xs text-muted-foreground mt-1">Ref: {score.reference_price ? `€${score.reference_price.toFixed(2)}` : "n.v.t."}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Concurrenten</CardTitle></CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{score.competitors_used}</div>
            <p className="text-xs text-muted-foreground mt-1">{score.competitors_excluded} uitgesloten</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">PCIS-subscores</CardTitle>
            <CardDescription>Zeven gewogen signalen die de PCIS vormen</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {subScores.map(s => (
              <div key={s.key}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-muted-foreground">{s.label}</span>
                  <span className="font-medium tabular-nums">{(s.value * 100).toFixed(0)}</span>
                </div>
                <Progress value={s.value * 100} className="h-2" />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Scoreradar</CardTitle>
            <CardDescription>Visueel overzicht van alle 7 dimensies</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radarData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
                <PolarGrid />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10 }} />
                <Radar name="Score" dataKey="value" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.2} />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <PrijsSimulatie skuId={skuId} shopId={shopId} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Concurrentenprijsdetail</CardTitle>
          <CardDescription>
            Referentieprijs: {score.reference_price ? `€${score.reference_price.toFixed(2)}` : "n.v.t."} (gewogen mediaan van opgenomen prijzen)
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="border-t">
            <div className="grid grid-cols-8 border-b bg-muted/50 px-4 py-2 text-xs font-medium text-muted-foreground">
              <div className="col-span-2">Concurrent</div>
              <div className="text-right">Prijs</div>
              <div className="text-right">vs Eigen</div>
              <div className="text-right">vs Ref.</div>
              <div className="text-right">Voorraad</div>
              <div className="text-right">Levertijd</div>
              <div className="text-right">Status</div>
            </div>
            {[...opgenomen, ...uitgesloten].length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">Geen recente concurrentendata beschikbaar.</div>
            ) : (
              <div className="divide-y">
                {[...opgenomen, ...uitgesloten].map((c: any, i: number) => (
                  <div key={i} className={`grid grid-cols-8 items-center px-4 py-3 text-sm ${c.is_excluded ? "opacity-50 bg-muted/30" : ""}`}>
                    <div className="col-span-2 font-medium">{c.competitor_name}</div>
                    <div className="text-right tabular-nums">€{c.price?.toFixed(2) ?? "—"}</div>
                    <div className={`text-right tabular-nums text-xs font-medium ${c.price_vs_own_pct > 0 ? "text-emerald-600" : c.price_vs_own_pct < 0 ? "text-red-600" : "text-muted-foreground"}`}>
                      {c.price_vs_own_pct != null ? `${c.price_vs_own_pct > 0 ? "+" : ""}${c.price_vs_own_pct.toFixed(1)}%` : "—"}
                    </div>
                    <div className={`text-right tabular-nums text-xs font-medium ${c.price_vs_reference_pct > 0 ? "text-emerald-600" : c.price_vs_reference_pct < 0 ? "text-red-600" : "text-muted-foreground"}`}>
                      {c.price_vs_reference_pct != null ? `${c.price_vs_reference_pct > 0 ? "+" : ""}${c.price_vs_reference_pct.toFixed(1)}%` : "—"}
                    </div>
                    <div className="text-right text-xs">
                      {c.in_stock === true ? (
                        <span className="font-medium text-emerald-600">Op voorraad</span>
                      ) : c.in_stock === false ? (
                        <span className="font-medium text-red-600">Niet op voorraad</span>
                      ) : (
                        <span className="text-muted-foreground">Onbekend</span>
                      )}
                    </div>
                    <div className="text-right text-xs tabular-nums">
                      {c.delivery_days != null ? (
                        <span>{c.delivery_days} {c.delivery_days === 1 ? "dag" : "dagen"}</span>
                      ) : (
                        <span className="text-muted-foreground">Onbekend</span>
                      )}
                    </div>
                    <div className="flex justify-end">
                      {c.is_excluded ? (
                        <span className="flex items-center gap-1 text-xs text-amber-600">
                          <XCircle className="h-3.5 w-3.5" />
                          {UITSLUITINGS_LABELS[c.exclusion_reason] || "Uitgesloten"}
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-emerald-600">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Opgenomen
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {Object.keys(score.excluded_reasons || {}).length > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" /> Redenen voor uitsluiting concurrenten
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {Object.entries(score.excluded_reasons || {}).map(([code, count]) => (
                <div key={code} className="flex items-center gap-2 text-sm">
                  <Badge variant="outline" className="bg-amber-100 text-amber-700 border-amber-300 text-xs">{String(count)}×</Badge>
                  <span className="text-muted-foreground">{UITSLUITINGS_LABELS[code] || code}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function PrijsSimulatie({ skuId, shopId }: { skuId: string; shopId: number | undefined }) {
  const [changePctInput, setChangePctInput] = useState("-5");

  const simulate = useMutation({
    mutationFn: async (changePct: number) => {
      const token = localStorage.getItem("auth_token");
      const res = await fetch("/api/competition/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          sku_id: skuId,
          change_pct: changePct / 100,
          ...(shopId !== undefined ? { shop_id: shopId } : {}),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Simulatie mislukt (${res.status})`);
      }
      return res.json();
    },
  });

  const parsed = parseFloat(changePctInput.replace(",", "."));
  const invalid = isNaN(parsed) || parsed < -50 || parsed > 50;
  const sim = simulate.data;

  const scenarios = sim && sim.data_available ? [
    { label: "Verwacht (gewogen volgkans)", data: sim.scenario_expected, index: sim.price_index?.expected },
    { label: "Niemand volgt", data: sim.scenario_nobody_follows, index: sim.price_index?.if_nobody_follows },
    { label: "Iedereen volgt", data: sim.scenario_all_follow, index: sim.price_index?.if_all_follow },
  ] : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Calculator className="h-4 w-4" /> Prijssimulatie
        </CardTitle>
        <CardDescription>
          Simuleer een eigen prijswijziging met per-concurrent volgkansen. Er wordt geen prijswijziging uitgevoerd.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm text-muted-foreground" htmlFor="sim-change-pct">Prijswijziging</label>
          <input
            id="sim-change-pct"
            type="number"
            step="0.5"
            min={-50}
            max={50}
            value={changePctInput}
            onChange={e => setChangePctInput(e.target.value)}
            className="w-24 rounded-md border bg-background px-2 py-1.5 text-sm tabular-nums"
          />
          <span className="text-sm text-muted-foreground">%</span>
          <Button
            size="sm"
            disabled={invalid || simulate.isPending}
            onClick={() => simulate.mutate(parsed)}
          >
            {simulate.isPending ? "Simuleren…" : "Simuleer"}
          </Button>
          {invalid && <span className="text-xs text-red-600">Voer een percentage tussen -50 en 50 in.</span>}
        </div>

        {simulate.isError && (
          <div className="text-sm text-red-600">{(simulate.error as Error).message}</div>
        )}

        {sim && sim.data_available === false && (
          <div className="text-sm text-muted-foreground">{sim.note || "Simulatie niet mogelijk voor deze SKU."}</div>
        )}

        {sim && sim.data_available && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">
                €{sim.current_price?.toFixed(2)} → €{sim.new_price?.toFixed(2)}
              </span>
              <span className="text-muted-foreground">
                ({sim.change_pct > 0 ? "+" : ""}{(sim.change_pct * 100).toFixed(1)}%)
              </span>
              <ElasticiteitBadge elasticityUsed={sim.elasticity_used} />
            </div>

            <LageBetrouwbaarheidWaarschuwing elasticityUsed={sim.elasticity_used} />

            <div className="border rounded-md overflow-hidden">
              <div className="grid grid-cols-5 border-b bg-muted/50 px-4 py-2 text-xs font-medium text-muted-foreground">
                <div className="col-span-2">Scenario</div>
                <div className="text-right">Volume-effect</div>
                <div className="text-right">Omzet (30d)</div>
                <div className="text-right">Marge (30d)</div>
              </div>
              <div className="divide-y">
                {scenarios.map(s => (
                  <div key={s.label} className="grid grid-cols-5 items-center px-4 py-2.5 text-sm">
                    <div className="col-span-2">
                      {s.label}
                      {s.index != null && (
                        <span className="ml-2 text-xs text-muted-foreground tabular-nums">PI {Number(s.index).toFixed(3)}</span>
                      )}
                    </div>
                    <div className={`text-right tabular-nums text-xs font-medium ${s.data?.volume_effect_pct > 0 ? "text-emerald-600" : s.data?.volume_effect_pct < 0 ? "text-red-600" : "text-muted-foreground"}`}>
                      {s.data?.volume_effect_pct != null ? `${s.data.volume_effect_pct > 0 ? "+" : ""}${s.data.volume_effect_pct.toFixed(1)}%` : "—"}
                    </div>
                    <div className="text-right tabular-nums">
                      {s.data?.revenue != null ? `€${s.data.revenue.toLocaleString("nl-NL", { maximumFractionDigits: 0 })}` : "—"}
                    </div>
                    <div className="text-right tabular-nums">
                      {s.data?.margin != null ? `€${s.data.margin.toLocaleString("nl-NL", { maximumFractionDigits: 0 })}` : "—"}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {sim.baseline_30d && (
              <p className="text-xs text-muted-foreground">
                Basislijn laatste 30 dagen: {sim.baseline_30d.units} stuks · €{Number(sim.baseline_30d.revenue).toLocaleString("nl-NL", { maximumFractionDigits: 0 })} omzet.
                {" "}{sim.note}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const METHODE_KLEUREN: Record<string, string> = {
  regressie: "bg-emerald-500/15 text-emerald-700 border-emerald-300",
  heuristiek: "bg-amber-500/15 text-amber-700 border-amber-300",
  default: "bg-slate-100 text-slate-500 border-slate-200",
};

const BETROUWBAARHEID_LABELS: Record<string, string> = {
  hoog_betrouwbaar: "Hoog betrouwbaar",
  bruikbaar: "Bruikbaar",
  laag_betrouwbaar: "Laag betrouwbaar",
};
function ElasticiteitBadge({ elasticityUsed }: { elasticityUsed: any }) {
  if (!elasticityUsed || !elasticityUsed.method) return null;
  const method: string = elasticityUsed.method;
  const r2 = elasticityUsed.regression_r2;
  const conf: string | null = elasticityUsed.confidence_class ?? null;
  const label = METHODE_LABELS[method] || method;
  const kleur = METHODE_KLEUREN[method] || METHODE_KLEUREN.default;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Badge
        variant="outline"
        className={`text-xs ${kleur}`}
        title={`Elasticiteitsmethode: ${label}${r2 != null ? ` · R² = ${Number(r2).toFixed(2)}` : ""}`}
      >
        Elasticiteit: {label}
        {r2 != null && <span className="ml-1 tabular-nums">(R² {Number(r2).toFixed(2)})</span>}
      </Badge>
      {conf && (
        <Badge
          variant="outline"
          className={`text-xs ${BETROUWBAARHEID_KLEUREN[conf] || "bg-slate-100 text-slate-500 border-slate-200"}`}
          title="Betrouwbaarheidsklasse van de gebruikte elasticiteit"
        >
          {BETROUWBAARHEID_LABELS[conf] || conf}
        </Badge>
      )}
    </span>
  );
}

function LageBetrouwbaarheidWaarschuwing({ elasticityUsed }: { elasticityUsed: any }) {
  if (!elasticityUsed) return null;
  const isDefault = elasticityUsed.method === "default" || elasticityUsed.source === "default";
  const laag = isDefault || elasticityUsed.confidence_class === "laag_betrouwbaar";
  if (!laag) return null;
  const reden = isDefault
    ? "Er is nog geen elasticiteit berekend voor deze SKU; er is een standaardwaarde gebruikt."
    : elasticityUsed.method === "heuristiek"
    ? "De elasticiteit is geschat met een heuristiek en heeft een lage betrouwbaarheid."
    : "De berekende elasticiteit heeft een lage betrouwbaarheid.";
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50/70 px-3 py-2 text-sm text-amber-800">
      <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-amber-500" />
      <span>
        <strong>Lage betrouwbaarheid:</strong> {reden} Interpreteer de scenario-uitkomsten met voorzichtigheid.
      </span>
    </div>
  );
}

const BETROUWBAARHEID_KLEUREN: Record<string, string> = {
  hoog_betrouwbaar: "bg-emerald-500/15 text-emerald-700 border-emerald-300",
  bruikbaar: "bg-blue-500/15 text-blue-700 border-blue-300",
  laag_betrouwbaar: "bg-amber-500/15 text-amber-700 border-amber-300",
};
