import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "wouter";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Circle, Globe, ShoppingBag, ChevronDown, ChevronRight, Building2, ShieldCheck, Loader2, Landmark, GitCompareArrows } from "lucide-react";
import { useShopId } from "@/hooks/use-shop-id";
import { useAuth } from "@/lib/auth";

function authHeaders() {
  const token = localStorage.getItem("auth_token");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}
function apiFetch(path: string) {
  return fetch(path, { headers: authHeaders() }).then(r => {
    if (!r.ok) throw new Error(`API-fout (${r.status})`);
    return r.json();
  });
}

const TRAFFIC_LIGHT: Record<string, { color: string; label: string }> = {
  green:  { color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "Belangrijk" },
  orange: { color: "text-amber-600 bg-amber-50 border-amber-200",       label: "Monitoren" },
  red:    { color: "text-red-600 bg-red-50 border-red-200",             label: "Laag" },
};

const STRATEGIE_LABELS: Record<string, string> = {
  EVERYDAY_LOW_PRICE:  "Altijd-Laagste-Prijs",
  PROMOTION_DRIVEN:    "Promotiegedreven",
  MARKET_SHARE_ATTACK: "Marktaandeeloffensief",
  MARGIN_PROTECTION:   "Margebescherming",
  INVENTORY_CLEARANCE: "Opruimingsstrategie",
  PRICE_FOLLOWER:      "Prijsvolger",
  PRICE_LEADER:        "Prijsleider",
};

const LAYER_META: Record<string, { label: string; cls: string }> = {
  feit:             { label: "Feit",      cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  schatting:        { label: "Schatting", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  afgeleid_signaal: { label: "Afgeleid",  cls: "bg-blue-50 text-blue-700 border-blue-200" },
  hypothese:        { label: "Hypothese", cls: "bg-purple-50 text-purple-700 border-purple-200" },
};

const BUSINESS_FIELD_LABELS: Record<string, string> = {
  legal_name: "Juridische naam", kvk_number: "KvK-nummer", founded_year: "Opgericht",
  customer_model: "Klantfocus (B2B/B2C)", size_class: "Bedrijfsomvang",
  employee_range_min: "Medewerkers (min)", employee_range_max: "Medewerkers (max)",
  revenue_range_min: "Omzet (min)", revenue_range_max: "Omzet (max)",
  revenue_currency: "Omzetvaluta", geographic_scale: "Geografische schaal",
  ownership_type: "Eigendomsstructuur", headquarters_country: "Hoofdkantoor (land)",
};
const FULFILMENT_FIELD_LABELS: Record<string, string> = {
  inventory_model: "Voorraadmodel", warehouse_count: "Aantal magazijnen",
  warehouse_locations: "Magazijnlocaties", dropship_share_pct: "Dropship-aandeel (%)",
  own_stock_share_pct: "Eigen voorraad-aandeel (%)", next_day_delivery: "Levering volgende dag",
  same_day_delivery: "Levering zelfde dag", marketplace_role: "Marketplace-rol",
};

const VALIDATE_ACTIONS = [
  { value: "bevestigen", label: "Bevestigen" },
  { value: "corrigeren", label: "Corrigeren" },
  { value: "blokkeren", label: "Blokkeren" },
  { value: "unknown", label: "Markeer als onbekend" },
  { value: "heronderzoek", label: "Heronderzoek aanvragen" },
];

function fmtValue(v: any): string {
  if (v === null || v === undefined || v === "") return "Onbekend";
  if (v === true) return "Ja";
  if (v === false) return "Nee";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "Onbekend";
  return String(v);
}

function InfoLayerBadge({ layer }: { layer?: string | null }) {
  const m = layer ? LAYER_META[layer] : null;
  if (!m) return null;
  return <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${m.cls}`}>{m.label}</Badge>;
}

function FieldRow({ field, label, value, meta, onValidate }: {
  field: string; label: string; value: any;
  meta?: Record<string, any> | null;
  onValidate?: (field: string, value: any) => void;
}) {
  const m = meta || {};
  const unknown = value === null || value === undefined || value === "" || m.status === "unknown";
  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b last:border-0" data-testid={`field-${field}`}>
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className={`text-sm font-medium ${unknown ? "text-muted-foreground italic" : ""}`}>
          {m.status === "blocked" ? "Geblokkeerd" : fmtValue(value)}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 mt-1">
          <InfoLayerBadge layer={m.information_layer} />
          {m.source && <span className="text-[10px] text-muted-foreground">bron: {m.source}</span>}
          {(m.as_of_date || m.observed_date) && <span className="text-[10px] text-muted-foreground">peildatum: {m.as_of_date || m.observed_date}</span>}
          {m.confidence != null && <span className="text-[10px] text-muted-foreground">confidence {Math.round(m.confidence * 100)}%</span>}
          {m.human_validated && <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-emerald-50 text-emerald-700 border-emerald-200"><ShieldCheck className="h-2.5 w-2.5 mr-0.5" />gevalideerd</Badge>}
          {m.status === "needs_review" && <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-amber-50 text-amber-700 border-amber-200">heronderzoek</Badge>}
        </div>
      </div>
      {onValidate && (
        <Button size="sm" variant="ghost" className="text-xs shrink-0" onClick={() => onValidate(field, value)} data-testid={`button-validate-${field}`}>
          Valideer
        </Button>
      )}
    </div>
  );
}

function ScoreCard({ title, score, max, subtitle, details, unknownNote, testId }: {
  title: string; score: number | null | undefined; max: 100 | 1;
  subtitle?: string; details?: any; unknownNote?: string; testId: string;
}) {
  const [open, setOpen] = useState(false);
  const display = score == null ? null : max === 1 ? Math.round(score * 100) : Math.round(score);
  const factors: any[] = details?.factors || details?.components || [];
  return (
    <Card data-testid={`scorecard-${testId}`}>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs text-muted-foreground font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {display == null ? (
          <div>
            <div className="text-xl font-bold text-muted-foreground italic">Onbekend</div>
            <p className="text-[11px] text-muted-foreground mt-0.5">{unknownNote || "Onvoldoende data — bewust geen 0."}</p>
          </div>
        ) : (
          <div>
            <div className="text-2xl font-bold tabular-nums">{display}</div>
            {subtitle && <p className="text-[11px] text-muted-foreground">{subtitle}</p>}
          </div>
        )}
        {(factors.length > 0 || details?.explanation) && (
          <button type="button" onClick={() => setOpen(o => !o)}
                  className="flex items-center gap-1 text-[11px] text-primary mt-2 hover:underline"
                  data-testid={`button-factors-${testId}`}>
            {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            Factoren & gewichten
          </button>
        )}
        {open && (
          <div className="mt-2 space-y-1.5" data-testid={`factors-${testId}`}>
            {factors.map((f: any, i: number) => (
              <div key={i} className="text-[11px]">
                <div className="flex justify-between gap-2">
                  <span className="truncate">{f.factor || f.name || f.signal}</span>
                  <span className="tabular-nums shrink-0">
                    {f.score != null ? Math.round(f.score) : "—"}{f.weight != null ? ` · w ${f.weight}` : ""}
                  </span>
                </div>
                {f.source && <div className="text-muted-foreground">bron: {f.source}</div>}
              </div>
            ))}
            {details?.explanation && <p className="text-[11px] text-muted-foreground">{details.explanation}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CorporateStructure({ relations, name }: { relations: any[]; name: string }) {
  const byType = (t: string) => relations.filter(r => r.relation_type === t && !r.valid_to);
  const ultimate = byType("ultimate_parent");
  const parents = byType("parent").concat(byType("holding"));
  const subs = byType("subsidiary");
  const sisters = byType("sister");
  const Box = ({ label, entity, country, muted }: any) => (
    <div className={`rounded-md border px-3 py-1.5 text-sm ${muted ? "bg-muted/40" : "bg-background"}`}>
      <span className="text-[10px] text-muted-foreground block">{label}</span>
      <span className="font-medium">{entity}</span>
      {country && <span className="text-xs text-muted-foreground ml-1.5">({country})</span>}
    </div>
  );
  if (!relations.filter(r => !r.valid_to).length) {
    return <p className="text-sm text-muted-foreground">Geen corporate structuur bekend — <span className="italic">Onbekend</span>, niet "zelfstandig".</p>;
  }
  return (
    <div className="space-y-2" data-testid="corporate-structure">
      {ultimate.map(r => <Box key={r.id} label="Ultimate parent" entity={r.related_entity} country={r.related_country} />)}
      {ultimate.length > 0 && <div className="ml-4 border-l-2 h-3" />}
      {parents.map(r => <Box key={r.id} label="Holding / parent" entity={r.related_entity} country={r.related_country} />)}
      {parents.length > 0 && <div className="ml-4 border-l-2 h-3" />}
      <Box label="Concurrent" entity={name} muted />
      {(subs.length > 0 || sisters.length > 0) && <div className="ml-4 border-l-2 h-3" />}
      <div className="flex flex-wrap gap-2">
        {subs.map(r => <Box key={r.id} label="Dochter / merk" entity={r.related_entity} country={r.related_country} />)}
        {sisters.map(r => <Box key={r.id} label="Zusterbedrijf (zelfde groep)" entity={r.related_entity} country={r.related_country} />)}
      </div>
      {sisters.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Webshops binnen dezelfde groep: {sisters.map(s => s.related_entity).join(", ")} — deze horen tot hetzelfde concern als {name}.
        </p>
      )}
    </div>
  );
}

export default function CompetitorDetail() {
  const shopId = useShopId();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canValidate = !!user && ["admin", "pricing_manager", "analyst"].includes(user.role);
  const { id: competitorName } = useParams<{ id: string }>();
  const name = decodeURIComponent(competitorName || "");
  const shopQ = shopId !== undefined ? `&shop_id=${shopId}` : "";

  const { data, isLoading } = useQuery({
    queryKey: ["competitor-detail", name, shopId],
    queryFn: () => apiFetch(`/api/competition/competitors/${encodeURIComponent(name)}?_=1${shopQ}`),
    enabled: !!name,
  });
  const { data: full, isLoading: fullLoading } = useQuery({
    queryKey: ["competitor-full-profile", name, shopId],
    queryFn: () => apiFetch(`/api/competition/competitor-profile/${encodeURIComponent(name)}?include_scores=true&include_evidence=true${shopQ}`),
    enabled: !!name,
  });

  // Historie met incrementeel bijladen
  const [timelineLimit, setTimelineLimit] = useState(25);
  const { data: timeline, isFetching: timelineLoading } = useQuery({
    queryKey: ["competitor-timeline", name, shopId, timelineLimit],
    queryFn: () => apiFetch(`/api/competition/competitor-profile/${encodeURIComponent(name)}/timeline?limit=${timelineLimit}${shopQ}`),
    enabled: !!name,
  });
  const { data: validations } = useQuery({
    queryKey: ["competitor-validations", name, shopId],
    queryFn: () => apiFetch(`/api/competition/competitor-profile/${encodeURIComponent(name)}/validations?_=1${shopQ}`),
    enabled: !!name,
  });

  // Validatie-dialoog
  const [valOpen, setValOpen] = useState(false);
  const [valSection, setValSection] = useState<"business" | "fulfilment">("business");
  const [valField, setValField] = useState("");
  const [valAction, setValAction] = useState("bevestigen");
  const [valValue, setValValue] = useState("");
  const [valReason, setValReason] = useState("");
  const [valBusy, setValBusy] = useState(false);
  const [valError, setValError] = useState<string | null>(null);

  const openValidate = (section: "business" | "fulfilment") => (field: string, value: any) => {
    setValSection(section); setValField(field);
    setValAction("bevestigen"); setValValue(value == null ? "" : String(value));
    setValReason(""); setValError(null); setValOpen(true);
  };

  const submitValidation = async () => {
    setValBusy(true); setValError(null);
    try {
      const body: any = { section: valSection, field_name: valField, action: valAction, reason: valReason || undefined };
      if (valAction === "corrigeren") {
        const raw = valValue.trim();
        body.human_value = raw === "" ? null : !isNaN(Number(raw)) && raw !== "" && /^-?\d+(\.\d+)?$/.test(raw) ? Number(raw) : raw === "true" ? true : raw === "false" ? false : raw;
      }
      const r = await fetch(`/api/competition/competitor-profile/${encodeURIComponent(name)}/validate${shopId !== undefined ? `?shop_id=${shopId}` : ""}`, {
        method: "POST", headers: authHeaders(), body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `Validatie mislukt (${r.status})`);
      }
      setValOpen(false);
      queryClient.invalidateQueries({ queryKey: ["competitor-full-profile", name] });
      queryClient.invalidateQueries({ queryKey: ["competitor-timeline", name] });
      queryClient.invalidateQueries({ queryKey: ["competitor-validations", name] });
    } catch (e: any) {
      setValError(e.message);
    } finally {
      setValBusy(false);
    }
  };

  if (isLoading || fullLoading) return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-4 gap-4">{[1,2,3,4].map(i => <Skeleton key={i} className="h-28" />)}</div>
      <Skeleton className="h-64" />
    </div>
  );

  const { profile, category_scores, strategy } = data || {};
  if (!profile && !full) return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <p className="text-muted-foreground">Geen profiel gevonden voor <strong>{name}</strong>.</p>
      <Link href="/competition/competitors"><Button variant="outline"><ArrowLeft className="h-4 w-4 mr-2" />Terug</Button></Link>
    </div>
  );

  const tl = TRAFFIC_LIGHT[profile?.traffic_light || "orange"] || TRAFFIC_LIGHT.orange;
  const business = full?.business || null;
  const bMeta = business?.field_meta || {};
  const fulfilment = full?.fulfilment || null;
  const fMeta = fulfilment?.field_meta || {};
  const scores = full?.scores || null;
  const ranking = full?.ranking || null;
  const details = scores?.details || {};
  const roles: any[] = (full?.market_roles || []).filter((r: any) => !r.valid_to);
  const geography: any[] = (full?.geography || []).filter((g: any) => !g.valid_to);
  const relations: any[] = full?.corporate_relations || [];
  const financials: any[] = full?.financials || [];
  const evidence: any[] = full?.evidence?.items || [];
  const completeness = full?.completeness || {};
  const avgCompleteness = (() => {
    const vals = Object.values(completeness).map((c: any) => c?.completeness_pct).filter((v: any) => v != null) as number[];
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null;
  })();

  const fmtRange = (min: any, max: any, suffix = "") => {
    if (min == null && max == null) return "Onbekend";
    if (min != null && max != null) return `${min.toLocaleString("nl-NL")} – ${max.toLocaleString("nl-NL")}${suffix}`;
    return `${(min ?? max).toLocaleString("nl-NL")}${min != null ? "+" : " (max)"}${suffix}`;
  };
  const countries = Array.from(new Set(geography.map((g: any) => g.country_code).filter(Boolean)));

  const summaryItems: { label: string; value: string; unknown?: boolean }[] = [
    { label: "Market role / DNA", value: roles.length ? roles.map((r: any) => r.role).join(", ") : "Onbekend", unknown: !roles.length },
    { label: "Bedrijfsomvang", value: scores?.company_size_class || business?.size_class || "Onbekend", unknown: !(scores?.company_size_class || business?.size_class) },
    { label: "Medewerkers", value: fmtRange(business?.employee_range_min, business?.employee_range_max), unknown: business?.employee_range_min == null && business?.employee_range_max == null },
    { label: "Omzet", value: business?.revenue_range_min != null || business?.revenue_range_max != null ? `${fmtRange(business?.revenue_range_min, business?.revenue_range_max)} ${business?.revenue_currency || "EUR"}` : "Onbekend", unknown: business?.revenue_range_min == null && business?.revenue_range_max == null },
    { label: "Landen", value: countries.length ? countries.join(", ") : "Onbekend", unknown: !countries.length },
    { label: "Klantfocus", value: business?.customer_model || "Onbekend", unknown: !business?.customer_model },
    { label: "Fulfilment", value: scores?.fulfilment_model_class || fulfilment?.inventory_model || "Onbekend", unknown: !(scores?.fulfilment_model_class || fulfilment?.inventory_model) },
    { label: "Financial health", value: scores?.financial_health_score != null ? `${Math.round(scores.financial_health_score)} (${scores.financial_health_status || "?"}) · confidence ${Math.round((scores.financial_data_confidence || 0) * 100)}%` : "Onbekend", unknown: scores?.financial_health_score == null },
    { label: "Procurement power", value: scores?.procurement_power_score != null ? String(Math.round(scores.procurement_power_score)) : "Onbekend", unknown: scores?.procurement_power_score == null },
    { label: "Business strength", value: scores?.business_strength_score != null ? String(Math.round(scores.business_strength_score)) : "Onbekend", unknown: scores?.business_strength_score == null },
    { label: "Relevance / Price / Influence", value: ranking ? `${Math.round((ranking.competition_relevance_score || 0) * 100)} / ${Math.round((ranking.price_relevance_score || 0) * 100)} / ${Math.round((ranking.influence_score || 0) * 100)}` : "Onbekend", unknown: !ranking },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <Link href="/competition/competitors">
          <Button variant="ghost" size="sm" className="mt-1"><ArrowLeft className="h-4 w-4 mr-1" /> Terug</Button>
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight">{profile?.competitor_name || name}</h1>
            {profile && (
              <Badge variant="outline" className={`text-xs ${tl.color}`}>
                <Circle className="h-2 w-2 mr-1 fill-current" />{tl.label}
              </Badge>
            )}
            {roles.map((r: any) => (
              <Badge key={r.id} variant="secondary" className="text-xs">{r.role}{r.human_validated ? " ✓" : ""}</Badge>
            ))}
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
            <Globe className="h-3.5 w-3.5" />{profile?.domain || name}
            {profile?.price_segment && <span className="ml-2 text-xs bg-muted px-2 py-0.5 rounded">{profile.price_segment}</span>}
            {avgCompleteness != null && <span className="ml-2 text-xs">Data Completeness: {avgCompleteness}%</span>}
          </div>
        </div>
        <Link href={`/competition/compare?names=${encodeURIComponent(name)}`}>
          <Button variant="outline" size="sm"><GitCompareArrows className="h-4 w-4 mr-1.5" />Vergelijk</Button>
        </Link>
      </div>

      {/* Managementsamenvatting */}
      <Card data-testid="management-summary">
        <CardHeader className="pb-3"><CardTitle className="text-base">Managementsamenvatting</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-3">
            {summaryItems.map(it => (
              <div key={it.label}>
                <div className="text-[11px] text-muted-foreground">{it.label}</div>
                <div className={`text-sm font-medium ${it.unknown ? "text-muted-foreground italic" : ""}`}>{it.value}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Acht scorecards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="scorecards">
        <ScoreCard title="Competition Relevance" score={ranking?.competition_relevance_score} max={1} subtitle={ranking ? `rank #${ranking.rank}` : undefined} testId="competition-relevance" />
        <ScoreCard title="Price Relevance" score={ranking?.price_relevance_score} max={1} testId="price-relevance" />
        <ScoreCard title="Influence" score={ranking?.influence_score} max={1} testId="influence" />
        <ScoreCard title="Business Strength" score={scores?.business_strength_score} max={100} details={details.business_strength} testId="business-strength" />
        <ScoreCard title="Operational Strength" score={scores?.operational_strength_score} max={100} details={details.operational_strength} testId="operational-strength" />
        <ScoreCard title="Procurement Power" score={scores?.procurement_power_score} max={100} details={details.procurement_power} testId="procurement-power" />
        <ScoreCard title="Financial Health" score={scores?.financial_health_score} max={100} subtitle={scores?.financial_health_status || undefined} details={details.financial_health} testId="financial-health" />
        <ScoreCard title="Data Confidence" score={scores?.data_completeness_pct} max={100} subtitle="data completeness" details={details.data_confidence} unknownNote="Nog geen score-run gedraaid." testId="data-confidence" />
      </div>

      <Tabs defaultValue="overzicht">
        <TabsList className="flex flex-wrap h-auto justify-start">
          {[["overzicht","Overzicht"],["bedrijf","Bedrijfsprofiel"],["markt","Markt & Geografie"],["assortiment","Assortiment & Merken"],["pricing","Pricing"],["fulfilment","Fulfilment"],["inkoop","Inkoop & Leveranciers"],["financieel","Financieel"],["service","Service & Loyalty"],["dna","Competition DNA"],["evidence","Evidence"],["historie","Historie"]].map(([v, l]) => (
            <TabsTrigger key={v} value={v} className="text-xs" data-testid={`tab-${v}`}>{l}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overzicht" className="space-y-4 mt-4">
          {profile && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Assortiment</CardTitle></CardHeader>
                <CardContent><div className="text-2xl font-bold">{profile.assortment_size}</div><p className="text-xs text-muted-foreground">{profile.category_breadth} categorieën</p></CardContent></Card>
              <Card><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Functionele overlap</CardTitle></CardHeader>
                <CardContent><div className="text-2xl font-bold">{Math.round((profile.functional_overlap_score || 0) * 100)}%</div></CardContent></Card>
              <Card><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Prijswijzigingen</CardTitle></CardHeader>
                <CardContent><div className="text-2xl font-bold">{profile.price_change_frequency?.toFixed(1)}/week</div></CardContent></Card>
              <Card><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Voorraadbetrouwbaarheid</CardTitle></CardHeader>
                <CardContent><div className="text-2xl font-bold">{Math.round((profile.in_stock_rate || 0) * 100)}%</div></CardContent></Card>
            </div>
          )}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Data Completeness per sectie</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(completeness).map(([sec, c]: any) => (
                <div key={sec} className="flex items-center gap-3 text-xs">
                  <span className="w-36 capitalize text-muted-foreground">{sec.replace("_", " ")}</span>
                  <Progress value={c?.completeness_pct || 0} className="h-1.5 flex-1" />
                  <span className="w-10 text-right tabular-nums">{Math.round(c?.completeness_pct || 0)}%</span>
                  {c?.stale_fields?.length > 0 && <Badge variant="outline" className="text-[10px] bg-amber-50 text-amber-700 border-amber-200">{c.stale_fields.length} verouderd</Badge>}
                </div>
              ))}
              {!Object.keys(completeness).length && <p className="text-sm text-muted-foreground">Nog geen uitgebreid profiel beschikbaar.</p>}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="bedrijf" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Building2 className="h-4 w-4" />Bedrijfsprofiel</CardTitle>
                <CardDescription className="text-xs">Elke waarde toont informatielaag, bron, peildatum en confidence. Onbekend blijft "Onbekend".</CardDescription></CardHeader>
              <CardContent>
                {Object.entries(BUSINESS_FIELD_LABELS).map(([f, label]) => (
                  <FieldRow key={f} field={f} label={label} value={business?.[f]} meta={bMeta[f]}
                            onValidate={canValidate ? openValidate("business") : undefined} />
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Landmark className="h-4 w-4" />Corporate structuur</CardTitle>
                <CardDescription className="text-xs">Ultimate parent → holding → concurrent → dochters/merken.</CardDescription></CardHeader>
              <CardContent><CorporateStructure relations={relations} name={name} /></CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="markt" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Geografische aanwezigheid</CardTitle>
              <CardDescription className="text-xs">Geografische schaal: {scores?.geographic_scale_class || business?.geographic_scale || "Onbekend"}</CardDescription></CardHeader>
            <CardContent>
              {geography.length === 0 ? <p className="text-sm text-muted-foreground italic">Onbekend</p> : (
                <div className="space-y-2">
                  {geography.map((g: any) => (
                    <div key={g.id} className="flex items-center gap-2 text-sm border-b last:border-0 pb-2">
                      <span className="font-medium w-12">{g.country_code}</span>
                      <Badge variant="outline" className="text-[10px]">{g.presence_type}</Badge>
                      <InfoLayerBadge layer={g.information_layer} />
                      {g.confidence != null && <span className="text-[10px] text-muted-foreground">confidence {Math.round(g.confidence * 100)}%</span>}
                      <span className="text-xs text-muted-foreground ml-auto">
                        Land-voordeel: {g.evidence_id ? "onderbouwd (evidence)" : "Niet vastgesteld"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="assortiment" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Top merken</CardTitle></CardHeader>
              <CardContent>
                {(profile?.top_brands || []).length === 0 ? <p className="text-sm text-muted-foreground italic">Onbekend</p> : (
                  <div className="flex flex-wrap gap-2">
                    {(profile.top_brands || []).map((b: string) => (
                      <div key={b} className="flex items-center gap-2 bg-muted rounded-full px-3 py-1 text-sm">
                        <ShoppingBag className="h-3.5 w-3.5 text-muted-foreground" />{b}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Categoryscores</CardTitle></CardHeader>
              <CardContent>
                {(category_scores || []).length === 0 ? <p className="text-sm text-muted-foreground">Geen categoryscores.</p> : (
                  <div className="space-y-2">
                    {(category_scores || []).slice(0, 6).map((cs: any) => (
                      <div key={cs.category} className="flex items-center gap-2 text-sm">
                        <span className="flex-1 truncate">{cs.category}</span>
                        <Progress value={cs.combined_score || 0} className="h-1.5 w-32" />
                        <span className="w-8 text-right tabular-nums text-xs">{cs.combined_score?.toFixed(0)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="pricing" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Prijssegment & activiteit</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="text-sm">Segment: <strong>{profile?.price_segment || "Onbekend"}</strong></div>
                <div className="text-sm">Prijswijzigingen: <strong>{profile?.price_change_frequency?.toFixed(1) ?? "—"}/week</strong> · laatste {profile?.last_price_change_date || "—"}</div>
                {["budget", "midden", "premium"].map((seg) => {
                  const pct = seg === "budget" ? (profile?.budget_share_pct || 0) * 100
                    : seg === "premium" ? (profile?.premium_share_pct || 0) * 100
                    : Math.max(0, 100 - (profile?.budget_share_pct || 0) * 100 - (profile?.premium_share_pct || 0) * 100);
                  return (
                    <div key={seg}>
                      <div className="flex justify-between text-xs mb-1"><span className="capitalize text-muted-foreground">{seg}</span><span>{Math.round(pct)}%</span></div>
                      <Progress value={pct} className="h-2" />
                    </div>
                  );
                })}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Strategie-herkenning</CardTitle></CardHeader>
              <CardContent>
                {!strategy ? <p className="text-sm text-muted-foreground">Geen strategie-data.</p> : (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-bold">{strategy.strategy_label_nl || STRATEGIE_LABELS[strategy.strategy_type] || strategy.strategy_type}</span>
                      <Badge variant="outline">{Math.round((strategy.confidence || 0) * 100)}%</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{strategy.explanation_nl}</p>
                    {strategy.recommended_action_nl && <p className="text-sm bg-muted/50 rounded p-2">{strategy.recommended_action_nl}</p>}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="fulfilment" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Fulfilment-profiel</CardTitle>
              <CardDescription className="text-xs">Model-classificatie: {scores?.fulfilment_model_class || "Onbekend"}{scores?.fulfilment_model_confidence != null ? ` · confidence ${Math.round(scores.fulfilment_model_confidence * 100)}%` : ""}</CardDescription></CardHeader>
            <CardContent>
              {Object.entries(FULFILMENT_FIELD_LABELS).map(([f, label]) => (
                <FieldRow key={f} field={f} label={label} value={fulfilment?.[f]} meta={fMeta[f]}
                          onValidate={canValidate ? openValidate("fulfilment") : undefined} />
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="inkoop" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ScoreCard title="Procurement Power" score={scores?.procurement_power_score} max={100} details={details.procurement_power} testId="procurement-power-tab" />
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Corporate backing</CardTitle>
                <CardDescription className="text-xs">Groepsstructuur beïnvloedt inkoopmacht.</CardDescription></CardHeader>
              <CardContent><CorporateStructure relations={relations} name={name} /></CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="financieel" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Financiële observaties</CardTitle>
              <CardDescription className="text-xs">Financial health: {scores?.financial_health_score != null ? `${Math.round(scores.financial_health_score)} (${scores.financial_health_status})` : "Onbekend"} · data confidence {scores?.financial_data_confidence != null ? `${Math.round(scores.financial_data_confidence * 100)}%` : "—"}</CardDescription></CardHeader>
            <CardContent>
              {financials.length === 0 ? <p className="text-sm text-muted-foreground italic">Onbekend — geen financiële observaties.</p> : (
                <table className="w-full text-sm">
                  <thead><tr className="border-b text-left text-muted-foreground text-xs">
                    <th className="py-1.5 pr-2">Jaar</th><th className="py-1.5 pr-2">Metric</th><th className="py-1.5 pr-2 text-right">Waarde</th><th className="py-1.5 pr-2">Laag</th><th className="py-1.5 pr-2">Peildatum</th><th className="py-1.5 text-right">Confidence</th>
                  </tr></thead>
                  <tbody>
                    {financials.map((f: any) => (
                      <tr key={f.id} className="border-b last:border-0">
                        <td className="py-1.5 pr-2 tabular-nums">{f.fiscal_year ?? "—"}</td>
                        <td className="py-1.5 pr-2">{f.metric}</td>
                        <td className="py-1.5 pr-2 text-right tabular-nums">
                          {f.is_unknown ? <span className="italic text-muted-foreground">Onbekend</span>
                            : `${f.value_min != null ? Number(f.value_min).toLocaleString("nl-NL") : "?"} – ${f.value_max != null ? Number(f.value_max).toLocaleString("nl-NL") : "?"} ${f.currency || ""}`}
                        </td>
                        <td className="py-1.5 pr-2"><InfoLayerBadge layer={f.information_layer} /></td>
                        <td className="py-1.5 pr-2 text-xs text-muted-foreground">{f.as_of_date || "—"}</td>
                        <td className="py-1.5 text-right tabular-nums text-xs">{f.confidence != null ? `${Math.round(f.confidence * 100)}%` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="service" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Service & Loyalty</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div><div className="text-xs text-muted-foreground">Voorraadbetrouwbaarheid</div><div className="font-medium">{profile?.in_stock_rate != null ? `${Math.round(profile.in_stock_rate * 100)}%` : <span className="italic text-muted-foreground">Onbekend</span>}</div></div>
              <div><div className="text-xs text-muted-foreground">Gem. levertijd</div><div className="font-medium">{profile?.avg_delivery_days != null ? `${profile.avg_delivery_days.toFixed(1)} dagen` : <span className="italic text-muted-foreground">Onbekend</span>}</div></div>
              <div><div className="text-xs text-muted-foreground">Levering volgende dag</div><div className="font-medium">{fulfilment?.next_day_delivery == null ? <span className="italic text-muted-foreground">Onbekend</span> : fulfilment.next_day_delivery ? "Ja" : "Nee"}</div></div>
              <div><div className="text-xs text-muted-foreground">Levering zelfde dag</div><div className="font-medium">{fulfilment?.same_day_delivery == null ? <span className="italic text-muted-foreground">Onbekend</span> : fulfilment.same_day_delivery ? "Ja" : "Nee"}</div></div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="dna" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Competition DNA — marktrollen</CardTitle>
              <CardDescription className="text-xs">Een concurrent kan meerdere rollen tegelijk hebben.</CardDescription></CardHeader>
            <CardContent>
              {roles.length === 0 ? <p className="text-sm text-muted-foreground italic">Onbekend — nog geen rollen toegekend.</p> : (
                <div className="space-y-2">
                  {roles.map((r: any) => (
                    <div key={r.id} className="flex items-center gap-2 text-sm border-b last:border-0 pb-2">
                      <Badge variant="secondary">{r.role}</Badge>
                      <InfoLayerBadge layer={r.information_layer} />
                      {r.confidence != null && <span className="text-[10px] text-muted-foreground">confidence {Math.round(r.confidence * 100)}%</span>}
                      {r.ai_assigned && <Badge variant="outline" className="text-[10px]">AI</Badge>}
                      {r.human_validated && <Badge variant="outline" className="text-[10px] bg-emerald-50 text-emerald-700 border-emerald-200"><ShieldCheck className="h-2.5 w-2.5 mr-0.5" />gevalideerd</Badge>}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="evidence" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Evidence ({full?.evidence?.total ?? 0})</CardTitle></CardHeader>
            <CardContent>
              {evidence.length === 0 ? <p className="text-sm text-muted-foreground">Geen evidence vastgelegd.</p> : (
                <div className="space-y-2">
                  {evidence.map((e: any) => (
                    <div key={e.id} className="border rounded-md p-2.5 text-sm">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium">{e.title || e.source_type}</span>
                        <Badge variant="outline" className="text-[10px]">{e.source_type}</Badge>
                        <Badge variant="outline" className="text-[10px]">{e.reliability}</Badge>
                        {e.confidence != null && <span className="text-[10px] text-muted-foreground">confidence {Math.round(e.confidence * 100)}%</span>}
                        {e.human_validated && <ShieldCheck className="h-3 w-3 text-emerald-600" />}
                      </div>
                      {e.extracted_fact && <p className="text-xs text-muted-foreground mt-1">{e.extracted_fact}</p>}
                      <div className="text-[10px] text-muted-foreground mt-1">
                        {e.source_url && <a className="text-primary hover:underline mr-2" href={e.source_url} target="_blank" rel="noreferrer">{e.source_url}</a>}
                        peildatum {e.observed_date || e.fetched_date || "—"}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="historie" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Competitor Evolution Timeline</CardTitle>
              <CardDescription className="text-xs">Profielwijzigingen, validaties en score-ontwikkeling — {timeline?.total ?? 0} events.</CardDescription></CardHeader>
            <CardContent>
              {(timeline?.items || []).length === 0 ? <p className="text-sm text-muted-foreground">Nog geen historie.</p> : (
                <div className="space-y-0" data-testid="evolution-timeline">
                  {(timeline?.items || []).map((ev: any) => (
                    <div key={ev.id} className="flex gap-3 text-sm border-l-2 border-muted pl-3 pb-3 relative">
                      <div className="absolute -left-[5px] top-1 h-2 w-2 rounded-full bg-primary" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge variant="outline" className="text-[10px]">{ev.section}</Badge>
                          <span className="font-medium text-xs">{ev.field_name || "—"}</span>
                          <Badge variant="secondary" className="text-[10px]">{ev.event_type}</Badge>
                          <span className="text-[10px] text-muted-foreground ml-auto">{ev.occurred_at ? new Date(ev.occurred_at).toLocaleString("nl-NL") : ""}</span>
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {ev.old_value != null && <span>van {JSON.stringify(ev.old_value)} </span>}
                          {ev.new_value != null && <span>naar {JSON.stringify(ev.new_value)}</span>}
                          {ev.changed_by && <span> · door {ev.changed_by}</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                  {timeline && timeline.total > (timeline.items || []).length && (
                    <Button variant="outline" size="sm" className="mt-2" disabled={timelineLoading}
                            onClick={() => setTimelineLimit(l => l + 25)} data-testid="button-timeline-load-more">
                      {timelineLoading ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : null}
                      Meer laden ({(timeline.items || []).length} van {timeline.total})
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Handmatige validaties</CardTitle></CardHeader>
            <CardContent>
              {(validations?.items || []).length === 0 ? <p className="text-sm text-muted-foreground">Nog geen validaties.</p> : (
                <div className="space-y-1.5">
                  {(validations.items || []).slice(0, 20).map((v: any) => (
                    <div key={v.id} className="flex items-center gap-2 text-xs flex-wrap">
                      <Badge variant="outline" className="text-[10px]">{v.section}</Badge>
                      <span className="font-medium">{v.field_name}</span>
                      <Badge variant="secondary" className="text-[10px]">{v.action}</Badge>
                      {v.human_value != null && <span>→ {JSON.stringify(v.human_value)}</span>}
                      <span className="text-muted-foreground ml-auto">{v.reviewer} · {v.created_at ? new Date(v.created_at).toLocaleDateString("nl-NL") : ""}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Validatie-dialoog */}
      <Dialog open={valOpen} onOpenChange={setValOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Veld valideren</DialogTitle>
            <DialogDescription>
              {valSection === "business" ? BUSINESS_FIELD_LABELS[valField] : FULFILMENT_FIELD_LABELS[valField]} ({valSection}) — bevestig, corrigeer, blokkeer, markeer als onbekend of vraag heronderzoek aan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Select value={valAction} onValueChange={setValAction}>
              <SelectTrigger data-testid="select-validate-action"><SelectValue /></SelectTrigger>
              <SelectContent>
                {VALIDATE_ACTIONS.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
              </SelectContent>
            </Select>
            {valAction === "corrigeren" && (
              <Input placeholder="Nieuwe (gecorrigeerde) waarde" value={valValue}
                     onChange={e => setValValue(e.target.value)} data-testid="input-validate-value" />
            )}
            <Input placeholder="Reden (optioneel)" value={valReason} onChange={e => setValReason(e.target.value)} data-testid="input-validate-reason" />
            {valError && <p className="text-xs text-red-600" data-testid="text-validate-error">{valError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setValOpen(false)}>Annuleren</Button>
            <Button onClick={submitValidation} disabled={valBusy} data-testid="button-validate-submit">
              {valBusy && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}Opslaan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
