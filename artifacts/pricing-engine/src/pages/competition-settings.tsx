import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { useShopId, shopParam } from "@/hooks/use-shop-id";
import { Settings, Save, RefreshCw, Loader2 } from "lucide-react";

function apiFetch(path: string, init?: RequestInit) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });
}

type RelevanceWeights = {
  pricing: number;
  assortment: number;
  traffic: number;
  authority: number;
  coverage: number;
};

type CompetitionSettings = {
  min_discovery_confidence: number; // fractie 0–1
  auto_approve_threshold: number;   // fractie 0–1
  auto_discovery_enabled: boolean;
  lookback_days: number;
  min_match_confidence: number;     // fractie 0–1
  relevance_weights: RelevanceWeights;
};

const DEFAULTS: CompetitionSettings = {
  min_discovery_confidence: 0.6,
  auto_approve_threshold: 0.9,
  auto_discovery_enabled: false,
  lookback_days: 30,
  min_match_confidence: 0.5,
  relevance_weights: { pricing: 25, assortment: 30, traffic: 20, authority: 15, coverage: 10 },
};

export default function CompetitionSettings() {
  const { toast } = useToast();
  const shopId = useShopId();
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["competition-settings", shopId],
    queryFn: async () => {
      const res = await apiFetch(`/api/competition/settings?${shopParam(shopId)}`);
      if (!res.ok) throw new Error("Instellingen laden mislukt");
      return res.json() as Promise<{ shop_id: number; settings: CompetitionSettings }>;
    },
  });

  // Percentages in de UI; fracties op de API.
  const [minDiscoveryConfidence, setMinDiscoveryConfidence] = useState(60);
  const [minMatchConfidence, setMinMatchConfidence] = useState(50);
  const [autoApproveThreshold, setAutoApproveThreshold] = useState(90);
  const [lookbackDays, setLookbackDays] = useState(30);
  const [autoDiscoveryEnabled, setAutoDiscoveryEnabled] = useState(false);
  const [relevanceWeights, setRelevanceWeights] = useState<RelevanceWeights>(DEFAULTS.relevance_weights);

  useEffect(() => {
    if (!data?.settings) return;
    const s = data.settings;
    setMinDiscoveryConfidence(Math.round(s.min_discovery_confidence * 100));
    setMinMatchConfidence(Math.round(s.min_match_confidence * 100));
    setAutoApproveThreshold(Math.round(s.auto_approve_threshold * 100));
    setLookbackDays(s.lookback_days);
    setAutoDiscoveryEnabled(s.auto_discovery_enabled);
    setRelevanceWeights({ ...s.relevance_weights });
  }, [data]);

  const weightTotal = Object.values(relevanceWeights).reduce((s, v) => s + v, 0);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        min_discovery_confidence: minDiscoveryConfidence / 100,
        min_match_confidence: minMatchConfidence / 100,
        auto_approve_threshold: autoApproveThreshold / 100,
        lookback_days: lookbackDays,
        auto_discovery_enabled: autoDiscoveryEnabled,
        relevance_weights: relevanceWeights,
      };
      const res = await apiFetch(`/api/competition/settings?${shopParam(shopId)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Opslaan mislukt");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["competition-settings"] });
      toast({
        title: "Instellingen opgeslagen",
        description: "De competition intelligence instellingen zijn opgeslagen voor deze winkel.",
      });
    },
    onError: (err: Error) => {
      toast({ title: "Opslaan mislukt", description: err.message, variant: "destructive" });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground py-12 justify-center">
        <Loader2 className="h-4 w-4 animate-spin" /> Instellingen laden…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-sm text-destructive py-12 text-center">
        Instellingen konden niet worden geladen. Probeer de pagina te verversen.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Competition Intelligence — Instellingen</h1>
        <p className="text-muted-foreground mt-1">Drempelwaarden voor auto-discovery, matching en relevantiescoreweging. Instellingen gelden per winkel.</p>
      </div>

      {/* Discovery instellingen */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2"><Settings className="h-4 w-4" /> Discovery Instellingen</CardTitle>
          <CardDescription>Parameters voor de automatische concurrent-discovery engine.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label className="text-sm">Minimale confidence voor ontdekking: <strong>{minDiscoveryConfidence}%</strong></Label>
            <p className="text-xs text-muted-foreground">Concurrenten met een lager confidence-niveau worden niet voorgesteld.</p>
            <Slider value={[minDiscoveryConfidence]} onValueChange={v => setMinDiscoveryConfidence(v[0])} min={30} max={95} step={5} className="max-w-sm" />
          </div>

          <div className="space-y-2">
            <Label className="text-sm">Auto-goedkeuring drempel: <strong>{autoApproveThreshold}%</strong></Label>
            <p className="text-xs text-muted-foreground">Concurrenten boven deze drempel worden automatisch goedgekeurd zonder menselijke review.</p>
            <Slider value={[autoApproveThreshold]} onValueChange={v => setAutoApproveThreshold(v[0])} min={70} max={100} step={5} className="max-w-sm" />
          </div>

          <div className="flex items-center gap-3">
            <Switch checked={autoDiscoveryEnabled} onCheckedChange={setAutoDiscoveryEnabled} />
            <div>
              <Label className="text-sm">Automatische dagelijkse discovery-run</Label>
              <p className="text-xs text-muted-foreground">Start elke nacht automatisch een discovery-run voor alle actieve categorieën.</p>
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-sm">Terugkijkperiode analyse: <strong>{lookbackDays} dagen</strong></Label>
            <Slider value={[lookbackDays]} onValueChange={v => setLookbackDays(v[0])} min={7} max={90} step={7} className="max-w-sm" />
          </div>
        </CardContent>
      </Card>

      {/* AI Matching instellingen */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">AI Matching Instellingen</CardTitle>
          <CardDescription>Parameters voor de AI-productkoppelingsengine.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label className="text-sm">Minimale match-confidence: <strong>{minMatchConfidence}%</strong></Label>
            <p className="text-xs text-muted-foreground">Matches onder dit niveau worden niet opgeslagen of weergegeven.</p>
            <Slider value={[minMatchConfidence]} onValueChange={v => setMinMatchConfidence(v[0])} min={10} max={90} step={5} className="max-w-sm" />
          </div>
        </CardContent>
      </Card>

      {/* Relevantiescore weging */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Weging Relevantiescores</CardTitle>
          <CardDescription>Bepaal hoe zwaar elke dimensie meeweegt in de gecombineerde relevantiescore per categorie. Totaal moet 100% zijn.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {(Object.entries(relevanceWeights) as [keyof RelevanceWeights, number][]).map(([key, val]) => (
            <div key={key} className="space-y-1">
              <div className="flex justify-between">
                <Label className="text-sm capitalize">{key.charAt(0).toUpperCase() + key.slice(1)} Relevantie</Label>
                <span className="text-sm font-medium">{val}%</span>
              </div>
              <Slider
                value={[val]}
                onValueChange={v => setRelevanceWeights(prev => ({ ...prev, [key]: v[0] }))}
                min={0} max={60} step={5} className="max-w-sm"
              />
            </div>
          ))}
          <div className="text-sm text-muted-foreground border-t pt-3">
            Totaal: <strong>{weightTotal}%</strong>
            {weightTotal !== 100 && (
              <span className="text-amber-600 ml-2">⚠ Totaal moet 100% zijn</span>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex gap-3">
        <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending || weightTotal !== 100} className="gap-2">
          {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Instellingen Opslaan
        </Button>
        <Button variant="outline" className="gap-2" onClick={() => {
          setMinDiscoveryConfidence(60);
          setMinMatchConfidence(50);
          setAutoApproveThreshold(90);
          setLookbackDays(30);
          setAutoDiscoveryEnabled(false);
          setRelevanceWeights({ ...DEFAULTS.relevance_weights });
          toast({ title: "Standaardwaarden hersteld", description: "Klik op 'Instellingen Opslaan' om ze te bewaren." });
        }}>
          <RefreshCw className="h-4 w-4" /> Standaard Herstellen
        </Button>
      </div>
    </div>
  );
}
