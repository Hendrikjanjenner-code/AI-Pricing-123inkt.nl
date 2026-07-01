import { useGetDashboardSummary, useGetMarginByCategory, useGetRecsByStrategy, useGetConfidenceDistribution, useGetPriceChangeDistribution } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line } from "recharts";
import { ArrowUpRight, ArrowDownRight, AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/InfoTooltip";
import { WidgetError } from "@/components/WidgetError";

const STRATEGIE_LABELS: Record<string, string> = {
  SUBSTITUTION_PORTFOLIO: "Substitutieportfolio",
  COMPETITOR_INDEX: "Concurrentie-index",
  MARGIN_OPTIMIZATION: "Margeoptimalisatie",
  STOCK_CLEARANCE: "Voorraadopruiming",
  BASKET_BUILDER: "Winkelmandbouwer",
  VOLUME_DISCOUNT: "Volumekorting",
  REPEAT_PURCHASE: "Herhalingsaankoop",
  LOW_VELOCITY: "Laag volume",
  PRIVATE_LABEL_PUSH: "Huismerk push",
  PORTFOLIO_MARGIN_OPTIMIZATION: "Portfolio margeoptimalisatie",
  TRAFFIC_TO_MARGIN_SWITCH: "Traffic naar marge",
};

export default function Dashboard() {
  const { data: summary, isLoading: loadingSummary, isError: summaryError } = useGetDashboardSummary();
  const { data: marginData, isLoading: loadingMargin, isError: marginError } = useGetMarginByCategory();
  const { data: recsData, isLoading: loadingRecs, isError: recsError } = useGetRecsByStrategy();
  const { data: confData, isLoading: loadingConf, isError: confError } = useGetConfidenceDistribution();
  const { data: priceData, isLoading: loadingPrice, isError: priceError } = useGetPriceChangeDistribution();

  if (summaryError) {
    console.error("[dashboard] failed to load summary");
  }

  const formatBedrag = (val: number) => new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(val);
  const formatGetal = (val: number) => new Intl.NumberFormat('nl-NL').format(val);

  const COLORS = ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))'];

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">Dagelijks overzicht</h1>

      {loadingSummary ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-[120px] w-full" />)}
        </div>
      ) : summaryError ? (
        <Card className="p-6">
          <WidgetError message="Kon dashboardsamenvatting niet laden." />
        </Card>
      ) : summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                Verwachte margeverbetering
                <InfoTooltip inline={{
                  naam: "Verwachte Margeverbetering",
                  korteUitleg: "Totale extra marge als alle openstaande adviezen worden goedgekeurd en uitgevoerd.",
                  uitgebreideUitleg: "Dit bedrag is de som van de verwachte margeverbeteringen van alle openstaande prijsadviezen. Het is een theoretisch maximum — in de praktijk worden niet alle adviezen goedgekeurd en reageert de markt soms anders dan verwacht.",
                  interpretatie: "Hoog bedrag = veel optimalisatieruimte aanwezig.\nLaag bedrag = pricing is al grotendeels geoptimaliseerd.",
                  businessImpact: "Gebruik dit als dagelijks prioriteringssignaal: hoe hoger het bedrag, hoe meer urgentie om adviezen te reviewen.",
                  formule: "Som van (aanbevolen_prijs – huidige_prijs) × verwacht_volume per openstaand advies",
                }} />
              </CardTitle>
              <ArrowUpRight className="h-4 w-4 text-emerald-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-emerald-600">{formatBedrag(summary.estimated_margin_impact)}</div>
              <p className="text-xs text-muted-foreground mt-1">Op basis van openstaande adviezen</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                Openstaande adviezen
                <InfoTooltip inline={{
                  naam: "Openstaande Adviezen",
                  korteUitleg: "Aantal prijsadviezen dat nog wacht op goedkeuring of afwijzing door een pricing analist.",
                  uitgebreideUitleg: "Openstaande adviezen zijn prijsaanbevelingen die door het AI-model zijn gegenereerd maar nog niet zijn verwerkt. Ze staan klaar voor review, goedkeuring (→ uitvoeren via de interne prijsmodule) of afwijzing.",
                  interpretatie: "Hoog getal = veel werkload voor pricing team.\nLaag getal = team heeft backlog verwerkt of weinig adviezen beschikbaar.",
                  businessImpact: "Adviezen ouder dan 2 dagen kunnen verouderd zijn doordat de markt is veranderd. Prioriteer verse adviezen met hoge margewaarde.",
                }} />
              </CardTitle>
              <CheckCircle2 className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatGetal(summary.pending_count)}</div>
              <p className="text-xs text-muted-foreground mt-1">Van {summary.total_recommendations} in totaal</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                Gem. betrouwbaarheid
                <InfoTooltip definitieId="confidence_score" />
              </CardTitle>
              <ActivityIcon className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{(summary.avg_confidence_score * 100).toFixed(1)}%</div>
              <p className="text-xs text-muted-foreground mt-1">Modelkwaliteit {summary.data_quality_score > 80 ? 'optimaal' : 'verminderd'}</p>
            </CardContent>
          </Card>
          <Card className="border-destructive/50">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-destructive flex items-center gap-1">
                Veiligheidswaarschuwingen
                <InfoTooltip inline={{
                  naam: "Veiligheidswaarschuwingen",
                  korteUitleg: "Adviezen die door veiligheidsregels zijn gemarkeerd voor verplichte handmatige controle.",
                  uitgebreideUitleg: "Veiligheidswaarschuwingen treden op wanneer een pricingadvies een of meer veiligheidsregels schendt:\n• Prijs onder kostprijsvloer (kostprijs × 1.01)\n• Prijswijziging groter dan 5% per dag\n• Modelbetrouwbaarheid onder 40%\n• Product uit voorraad",
                  interpretatie: "0 waarschuwingen = geen actie vereist.\n1+ waarschuwingen = direct review door pricing analist.",
                  businessImpact: "Negeer waarschuwingen nooit — ze voorkomen prijsfouten en verlieslatende transacties.",
                }} />
              </CardTitle>
              <ShieldAlert className="h-4 w-4 text-destructive" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-destructive">{formatGetal(summary.safety_warnings_count)}</div>
              <p className="text-xs text-muted-foreground mt-1">Handmatige controle vereist</p>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Margeverbetering per categorie</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {marginError ? (
              <WidgetError />
            ) : marginData ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={marginData}>
                  <XAxis dataKey="category" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v) => `€${v}`} />
                  <Tooltip formatter={(value: number) => [`€${value}`, 'Margeverbetering']} cursor={{fill: 'var(--muted)'}} />
                  <Bar dataKey="margin_uplift" fill="var(--primary)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : loadingMargin ? <Skeleton className="w-full h-full" /> : <WidgetError />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Adviezen per strategie</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {recsError ? (
              <WidgetError />
            ) : recsData ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={recsData.map((d: any) => ({ ...d, name: STRATEGIE_LABELS[d.strategy_type] || d.strategy_type }))}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="count"
                    nameKey="name"
                  >
                    {recsData.map((_: any, index: number) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(val: number, name: string) => [val, name]} />
                </PieChart>
              </ResponsiveContainer>
            ) : loadingRecs ? <Skeleton className="w-full h-full" /> : <WidgetError />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Verdeling prijswijzigingen</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {priceError ? (
              <WidgetError />
            ) : priceData ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={priceData}>
                  <XAxis dataKey="bucket" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{fill: 'var(--muted)'}} />
                  <Bar dataKey="count" fill="var(--chart-4)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : loadingPrice ? <Skeleton className="w-full h-full" /> : <WidgetError />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Modelbetrouwbaarheid</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {confError ? (
              <WidgetError />
            ) : confData ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={confData}>
                  <XAxis dataKey="bucket" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="count" stroke="var(--chart-2)" strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : loadingConf ? <Skeleton className="w-full h-full" /> : <WidgetError />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ActivityIcon(props: any) {
  return (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}
