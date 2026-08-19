import { useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line } from "recharts";
import { ArrowUpRight, ArrowDownRight, AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/InfoTooltip";
import { WidgetError } from "@/components/WidgetError";
import { getAuthHeaders, useAuth } from "@/lib/auth";
import { gebruikersPermissies } from "@/lib/route-registry";
import { useToast } from "@/hooks/use-toast";
import { ToastAction } from "@/components/ui/toast";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

type ConnStatus = "ok" | "not_configured" | "unreachable" | "auth_error" | "error";

interface ConnectorStatus {
  name: string;
  label: string;
  configured: boolean;
  last_test_status: ConnStatus | null;
}

const CONN_STATUS_LABEL: Record<ConnStatus, string> = {
  ok: "Verbonden",
  not_configured: "Niet geconfigureerd",
  unreachable: "Niet bereikbaar",
  auth_error: "Authenticatiefout",
  error: "Fout",
};

const CONN_STATUS_DOT: Record<ConnStatus, string> = {
  ok: "bg-emerald-500",
  not_configured: "bg-gray-400",
  unreachable: "bg-red-500",
  auth_error: "bg-amber-500",
  error: "bg-red-500",
};

function connectorStatusOf(c: ConnectorStatus): ConnStatus {
  return c.configured ? (c.last_test_status ?? "error") : "not_configured";
}

function isProblemStatus(status: ConnStatus): boolean {
  return status === "unreachable" || status === "auth_error" || status === "error";
}

function DatabronnenStrip() {
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const hasDataRef = useRef(false);
  const prevStatusRef = useRef<Record<string, ConnStatus>>({});
  const { toast } = useToast();

  useEffect(() => {
    let active = true;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const load = async () => {
      if (document.hidden) return;
      try {
        const resp = await fetch(`${BASE}/api/connectors`, { headers: getAuthHeaders() });
        if (!resp.ok) throw new Error("fetch failed");
        const data: ConnectorStatus[] = await resp.json();
        if (!active) return;
        const ordered = ["priceshape", "drs", "ga4"]
          .map((name) => data.find((c) => c.name === name))
          .filter(Boolean) as ConnectorStatus[];

        // Detect healthy → unhealthy transitions and warn once per transition.
        // Skip on the very first successful load so we only alert on changes,
        // not on connectors that were already down when the page opened.
        const prev = prevStatusRef.current;
        const isFirstLoad = !hasDataRef.current;
        const nextStatuses: Record<string, ConnStatus> = {};
        for (const c of ordered) {
          const status = connectorStatusOf(c);
          nextStatuses[c.name] = status;
          if (!isFirstLoad) {
            const previous = prev[c.name];
            if (previous === "ok" && isProblemStatus(status)) {
              toast({
                title: `Databron probleem: ${c.label}`,
                description: `${c.label} is niet meer bereikbaar (${CONN_STATUS_LABEL[status]}). Bekijk de connectoren voor details.`,
                variant: "destructive",
                action: (
                  <ToastAction altText="Bekijk connectoren" asChild>
                    <Link href="/connectoren">Details</Link>
                  </ToastAction>
                ),
              });
            }
          }
        }
        prevStatusRef.current = nextStatuses;

        hasDataRef.current = true;
        setConnectors(ordered);
        setError(false);
      } catch {
        // Keep last-known status on refresh failures; only surface the error
        // if we never managed to load any data at all.
        if (active && !hasDataRef.current) setError(true);
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    intervalId = setInterval(load, 60000);

    const onVisibilityChange = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      active = false;
      if (intervalId) clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  if (loading) return <Skeleton className="h-[68px] w-full" />;
  if (error || connectors.length === 0) return null;

  const anyProblem = connectors.some(
    (c) => c.configured && c.last_test_status && c.last_test_status !== "ok"
  );

  return (
    <Card className={anyProblem ? "border-amber-200" : ""}>
      <CardContent className="py-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="text-sm font-medium text-muted-foreground">Databronnen</span>
          {connectors.map((c) => {
            const status: ConnStatus = connectorStatusOf(c);
            const isOk = status === "ok";
            return (
              <Link
                key={c.name}
                href="/connectoren"
                className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
                title={`${c.label}: ${CONN_STATUS_LABEL[status]} — klik voor details`}
              >
                <span className={`w-2.5 h-2.5 rounded-full ${CONN_STATUS_DOT[status]}`} />
                <span className="text-sm font-medium">{c.label}</span>
                <span className={`text-xs ${isOk ? "text-emerald-600" : "text-muted-foreground"}`}>
                  {CONN_STATUS_LABEL[status]}
                </span>
              </Link>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

type EngineStatus = "success" | "failed" | "stale" | "missing";

interface EngineShopStatus {
  shop_id: number;
  shop_code: string;
  status: EngineStatus | "running";
  last_run_at: string | null;
  error_message: string | null;
}

interface EngineRunInfo {
  engine: string;
  label: string;
  status: EngineStatus;
  last_run_at: string | null;
  error_message: string | null;
  shops: EngineShopStatus[];
}

interface EngineRunStatusResponse {
  overall: "ok" | "warning";
  engines: EngineRunInfo[];
}

const ENGINE_STATUS_LABEL: Record<EngineStatus, string> = {
  success: "Geslaagd",
  failed: "Mislukt",
  stale: "Verouderd",
  missing: "Nog niet gedraaid",
};

const ENGINE_STATUS_DOT: Record<EngineStatus, string> = {
  success: "bg-emerald-500",
  failed: "bg-red-500",
  stale: "bg-amber-500",
  missing: "bg-gray-400",
};

function formatRunTijd(iso: string | null): string {
  if (!iso) return "—";
  // Backend levert UTC-tijden zonder timezone-suffix.
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString("nl-NL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function NachtelijkeEnginesStrip() {
  const [data, setData] = useState<EngineRunStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const hasDataRef = useRef(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      if (document.hidden) return;
      try {
        const resp = await fetch(`${BASE}/api/engine-runs/status`, { headers: getAuthHeaders() });
        if (!resp.ok) throw new Error("fetch failed");
        const json: EngineRunStatusResponse = await resp.json();
        if (!active) return;
        hasDataRef.current = true;
        setData(json);
        setError(false);
      } catch {
        // Behoud de laatst bekende status bij een tijdelijke fetch-fout.
        if (active && !hasDataRef.current) setError(true);
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    const intervalId = setInterval(load, 60000);
    return () => {
      active = false;
      clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) return <Skeleton className="h-[68px] w-full" />;
  if (error || !data) return null;

  const problemen = data.engines.filter((e) => e.status !== "success");
  const anyProblem = problemen.length > 0;

  return (
    <Card className={anyProblem ? "border-amber-300" : ""} data-testid="nachtelijke-engines-strip">
      <CardContent className="py-3 space-y-2">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="text-sm font-medium text-muted-foreground">Nachtelijke engines</span>
          {data.engines.map((e) => (
            <div
              key={e.engine}
              className="flex items-center gap-1.5"
              title={
                e.status === "failed" && e.error_message
                  ? `${e.label}: ${ENGINE_STATUS_LABEL[e.status]} — ${e.error_message}`
                  : `${e.label}: ${ENGINE_STATUS_LABEL[e.status]}${e.last_run_at ? ` (laatste run ${formatRunTijd(e.last_run_at)})` : ""}`
              }
            >
              <span className={`w-2.5 h-2.5 rounded-full ${ENGINE_STATUS_DOT[e.status]}`} />
              <span className="text-sm font-medium">{e.label}</span>
              <span className={`text-xs ${e.status === "success" ? "text-emerald-600" : "text-muted-foreground"}`}>
                {e.status === "success" ? formatRunTijd(e.last_run_at) : ENGINE_STATUS_LABEL[e.status]}
              </span>
            </div>
          ))}
        </div>
        {anyProblem && (
          <div className="flex items-start gap-2 text-sm text-amber-700">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>
              {problemen.map((e) => {
                const probleemShops = e.shops.filter((s) => s.status !== "success");
                const winkels = probleemShops.length > 0
                  ? ` (winkel: ${probleemShops.map((s) => `${s.shop_code} — ${ENGINE_STATUS_LABEL[s.status as EngineStatus] ?? s.status}`).join(", ")})`
                  : "";
                if (e.status === "failed") return `${e.label} is afgelopen nacht mislukt${e.error_message ? `: ${e.error_message}` : ""}${winkels}`;
                if (e.status === "stale") return `${e.label} heeft afgelopen nacht niet gedraaid${winkels}`;
                return `${e.label} heeft nog niet voor alle winkels gedraaid${winkels}`;
              }).join(". ")}
              . Forecasts en kansen kunnen verouderd zijn.
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

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
  // Afdelingsgericht Command Center (taak 219): widgets zijn permissie-gedreven —
  // een gebruiker zonder pricing.view ziet geen pricing-KPI's of -grafieken.
  const { user } = useAuth();
  const perms = gebruikersPermissies(user);
  const magPricing = perms.has("*") || perms.has("pricing.view");
  const workspaceNaam = user?.departments?.length
    ? user.departments.map((d: any) => d.name).join(", ")
    : null;
  // Global Filter Context (taak #216): alle widgets op dit scherm respecteren
  // dezelfde context; de server expandeert parent-selecties naar descendants.
  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);
  const dash = (path: string) => async () => {
    const url = `${BASE}/api/dashboard/${path}${filterQs ? `?${filterQs}` : ""}`;
    const resp = await fetch(url, { headers: getAuthHeaders() });
    if (!resp.ok) throw new Error(`Dashboard-API fout (${resp.status})`);
    return resp.json();
  };
  const { data: summary, isLoading: loadingSummary, isError: summaryError } =
    useQuery<any>({ queryKey: ["dashboard-summary", filterQs], queryFn: dash("summary"), enabled: magPricing });
  const { data: marginData, isLoading: loadingMargin, isError: marginError } =
    useQuery<any[]>({ queryKey: ["dashboard-margin-by-category", filterQs], queryFn: dash("charts/margin-by-category"), enabled: magPricing });
  const { data: recsData, isLoading: loadingRecs, isError: recsError } =
    useQuery<any[]>({ queryKey: ["dashboard-recs-by-strategy", filterQs], queryFn: dash("charts/recs-by-strategy"), enabled: magPricing });
  const { data: confData, isLoading: loadingConf, isError: confError } =
    useQuery<any[]>({ queryKey: ["dashboard-confidence-dist", filterQs], queryFn: dash("charts/confidence-distribution"), enabled: magPricing });
  const { data: priceData, isLoading: loadingPrice, isError: priceError } =
    useQuery<any[]>({ queryKey: ["dashboard-price-change-dist", filterQs], queryFn: dash("charts/price-change-distribution"), enabled: magPricing });

  if (summaryError) {
    console.error("[dashboard] failed to load summary");
  }

  const formatBedrag = (val: number) => new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(val);
  const formatGetal = (val: number) => new Intl.NumberFormat('nl-NL').format(val);

  const COLORS = ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))'];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dagelijks overzicht</h1>
        {workspaceNaam && (
          <p className="text-sm text-muted-foreground mt-1" data-testid="workspace-naam">
            Workspace: {workspaceNaam}
          </p>
        )}
      </div>

      <GlobalFilterBar />

      <DatabronnenStrip />

      <NachtelijkeEnginesStrip />

      {!magPricing ? (
        <Card className="p-6">
          <p className="text-sm text-muted-foreground">
            Pricing-KPI's zijn niet zichtbaar voor jouw afdeling. Gebruik de
            navigatie links voor de domeinen van jouw workspace.
          </p>
        </Card>
      ) : loadingSummary ? (
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

      {magPricing && <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
      </div>}
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
