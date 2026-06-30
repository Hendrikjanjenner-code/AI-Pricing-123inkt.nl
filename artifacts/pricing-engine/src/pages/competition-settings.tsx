import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { Settings, Save, RefreshCw } from "lucide-react";

export default function CompetitionSettings() {
  const { toast } = useToast();

  const [minDiscoveryConfidence, setMinDiscoveryConfidence] = useState(60);
  const [minMatchConfidence, setMinMatchConfidence] = useState(50);
  const [autoApproveThreshold, setAutoApproveThreshold] = useState(90);
  const [lookbackDays, setLookbackDays] = useState(30);
  const [autoDiscoveryEnabled, setAutoDiscoveryEnabled] = useState(false);
  const [relevanceWeights, setRelevanceWeights] = useState({
    pricing: 25,
    assortment: 30,
    traffic: 20,
    authority: 15,
    coverage: 10,
  });

  function saveSettings() {
    toast({
      title: "Instellingen opgeslagen",
      description: "De competition intelligence instellingen zijn bijgewerkt.",
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Competition Intelligence — Instellingen</h1>
        <p className="text-muted-foreground mt-1">Drempelwaarden voor auto-discovery, matching en relevantiescoreweging.</p>
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
          {Object.entries(relevanceWeights).map(([key, val]) => (
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
            Totaal: <strong>{Object.values(relevanceWeights).reduce((s, v) => s + v, 0)}%</strong>
            {Object.values(relevanceWeights).reduce((s, v) => s + v, 0) !== 100 && (
              <span className="text-amber-600 ml-2">⚠ Totaal moet 100% zijn</span>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex gap-3">
        <Button onClick={saveSettings} className="gap-2">
          <Save className="h-4 w-4" /> Instellingen Opslaan
        </Button>
        <Button variant="outline" className="gap-2" onClick={() => {
          setMinDiscoveryConfidence(60);
          setMinMatchConfidence(50);
          setAutoApproveThreshold(90);
          setLookbackDays(30);
          setAutoDiscoveryEnabled(false);
          setRelevanceWeights({ pricing: 25, assortment: 30, traffic: 20, authority: 15, coverage: 10 });
          toast({ title: "Standaardwaarden hersteld" });
        }}>
          <RefreshCw className="h-4 w-4" /> Standaard Herstellen
        </Button>
      </div>
    </div>
  );
}
