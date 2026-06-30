import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { ArrowRight, AlertTriangle } from "lucide-react";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const STRATEGIE_COLORS: Record<string, string> = {
  EVERYDAY_LOW_PRICE:  "bg-blue-100 text-blue-700 border-blue-200",
  PROMOTION_DRIVEN:    "bg-purple-100 text-purple-700 border-purple-200",
  MARKET_SHARE_ATTACK: "bg-red-100 text-red-700 border-red-200",
  MARGIN_PROTECTION:   "bg-emerald-100 text-emerald-700 border-emerald-200",
  INVENTORY_CLEARANCE: "bg-orange-100 text-orange-700 border-orange-200",
  PRICE_FOLLOWER:      "bg-slate-100 text-slate-600 border-slate-200",
  PRICE_LEADER:        "bg-yellow-100 text-yellow-700 border-yellow-200",
};

const STRATEGIE_ICON: Record<string, string> = {
  EVERYDAY_LOW_PRICE:  "💰",
  PROMOTION_DRIVEN:    "🎯",
  MARKET_SHARE_ATTACK: "⚡",
  MARGIN_PROTECTION:   "🛡️",
  INVENTORY_CLEARANCE: "📦",
  PRICE_FOLLOWER:      "🔄",
  PRICE_LEADER:        "👑",
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

export default function CompetitionStrategies() {
  const [lookbackDays, setLookbackDays] = useState("30");
  const [stratFilter, setStratFilter] = useState("all");

  const { data, isLoading } = useQuery({
    queryKey: ["competition-strategies", lookbackDays],
    queryFn: () => apiFetch(`/api/competition/strategies?lookback_days=${lookbackDays}`),
  });

  const strategies: any[] = (data?.strategieen || []).filter((s: any) =>
    stratFilter === "all" || s.strategy_type === stratFilter
  );

  // Verdeling per strategie
  const allStrategies = data?.strategieen || [];
  const distribution: Record<string, number> = {};
  for (const s of allStrategies) {
    distribution[s.strategy_type] = (distribution[s.strategy_type] || 0) + 1;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Strategie Analyse</h1>
        <p className="text-muted-foreground mt-1">Automatisch herkende prijsstrategie per concurrent — confidence, uitleg en aanbevolen reactie.</p>
      </div>

      {/* Strategie-verdeling */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(distribution).map(([type, count]) => (
          <Card key={type} className={`flex-shrink-0 cursor-pointer hover:shadow-md transition-shadow ${stratFilter === type ? "ring-2 ring-primary" : ""}`}
            onClick={() => setStratFilter(stratFilter === type ? "all" : type)}>
            <CardContent className="py-3 px-4">
              <div className="flex items-center gap-2">
                <span>{STRATEGIE_ICON[type] || "📊"}</span>
                <div>
                  <div className="font-medium text-sm">{STRATEGIE_LABELS[type] || type}</div>
                  <div className="text-xs text-muted-foreground">{count} concurrent{count > 1 ? "en" : ""}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <Select value={lookbackDays} onValueChange={setLookbackDays}>
          <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 dagen</SelectItem>
            <SelectItem value="14">14 dagen</SelectItem>
            <SelectItem value="30">30 dagen</SelectItem>
            <SelectItem value="60">60 dagen</SelectItem>
            <SelectItem value="90">90 dagen</SelectItem>
          </SelectContent>
        </Select>
        <Select value={stratFilter} onValueChange={setStratFilter}>
          <SelectTrigger className="w-52"><SelectValue placeholder="Alle strategieën" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle strategieën</SelectItem>
            {Object.entries(STRATEGIE_LABELS).map(([k, v]) => (
              <SelectItem key={k} value={k}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">{[1,2,3,4].map(i => <Skeleton key={i} className="h-48" />)}</div>
      ) : strategies.length === 0 ? (
        <Card><CardContent className="p-12 text-center text-muted-foreground">Geen strategie-data beschikbaar voor de geselecteerde periode.</CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {strategies.map((s: any) => {
            const colorClass = STRATEGIE_COLORS[s.strategy_type] || "bg-slate-100 text-slate-700 border-slate-200";
            return (
              <Card key={s.competitor_name || s.concurrent} className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-base">{s.competitor_name || s.concurrent}</CardTitle>
                      {s.run_date && <CardDescription>Analyse: {s.run_date}</CardDescription>}
                    </div>
                    <Badge variant="outline" className={`text-xs shrink-0 ${colorClass}`}>
                      {STRATEGIE_ICON[s.strategy_type] || "📊"} {s.strategy_label_nl || STRATEGIE_LABELS[s.strategy_type] || s.label_nl || s.strategy_type}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* Strategie-wijziging alert */}
                  {s.strategy_changed && s.previous_strategy_type && (
                    <div className="flex items-start gap-2 text-xs bg-amber-50 border border-amber-200 rounded p-2">
                      <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
                      <span>Gewijzigd van <strong>{STRATEGIE_LABELS[s.previous_strategy_type] || s.previous_strategy_type}</strong>
                        <ArrowRight className="h-3 w-3 inline mx-1" />
                        <strong>{STRATEGIE_LABELS[s.strategy_type] || s.strategy_type}</strong>
                      </span>
                    </div>
                  )}

                  {/* Confidence */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-muted-foreground">Confidence</span>
                      <span className="font-medium">{Math.round((s.confidence || 0) * 100)}%</span>
                    </div>
                    <Progress value={(s.confidence || 0) * 100} className="h-1.5" />
                  </div>

                  {/* Uitleg */}
                  <p className="text-xs text-muted-foreground">{s.explanation_nl || s.reden}</p>

                  {/* Aanbeveling */}
                  <div className="bg-muted/50 rounded p-2.5">
                    <p className="text-xs font-medium mb-1 text-muted-foreground">Aanbevolen reactie:</p>
                    <p className="text-sm">{s.recommended_action_nl || s.aanbevolen_reactie}</p>
                  </div>

                  {(s.period_days || s.datapunten) && (
                    <div className="text-xs text-muted-foreground">
                      {s.period_days && `${s.period_days} dagen`} · {(s.data_points || s.datapunten)} datapunten
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
