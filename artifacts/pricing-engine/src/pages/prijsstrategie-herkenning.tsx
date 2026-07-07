import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { RefreshCw, AlertCircle, TrendingUp, TrendingDown, ShieldAlert, Tag, Zap } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

async function fetchStrategies() {
  const token = getAuthToken();
  const res = await fetch(`${BASE}/api/competition/strategies`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Ophalen mislukt");
  return res.json();
}

const STRATEGIE_KLEUREN: Record<string, string> = {
  EVERYDAY_LOW_PRICE:  "bg-blue-50 text-blue-700 border-blue-200",
  PROMOTION_DRIVEN:    "bg-purple-50 text-purple-700 border-purple-200",
  MARKET_SHARE_ATTACK: "bg-red-50 text-red-700 border-red-200",
  MARGIN_PROTECTION:   "bg-emerald-50 text-emerald-700 border-emerald-200",
  INVENTORY_CLEARANCE: "bg-orange-50 text-orange-700 border-orange-200",
  PRICE_FOLLOWER:      "bg-gray-50 text-gray-700 border-gray-200",
  PRICE_LEADER:        "bg-amber-50 text-amber-700 border-amber-200",
};

const STRATEGIE_ICONEN: Record<string, React.ElementType> = {
  EVERYDAY_LOW_PRICE:  Tag,
  PROMOTION_DRIVEN:    Zap,
  MARKET_SHARE_ATTACK: ShieldAlert,
  MARGIN_PROTECTION:   TrendingUp,
  INVENTORY_CLEARANCE: TrendingDown,
  PRICE_FOLLOWER:      TrendingUp,
  PRICE_LEADER:        Zap,
};

export default function PrijsstrategieHerkenning() {
  const [data, setData] = useState<any>(null);
  const [laden, setLaden] = useState(true);
  const [fout, setFout] = useState<string | null>(null);

  const laad = async () => {
    setLaden(true);
    setFout(null);
    try {
      const d = await fetchStrategies();
      setData(d);
    } catch (e: any) {
      setFout(e.message);
    } finally {
      setLaden(false);
    }
  };

  useEffect(() => { laad(); }, []);

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Prijsstrategie-herkenning</h1>
          <p className="text-muted-foreground mt-1">
            Classificatie van concurrentiestrategieën op basis van historische prijspatronen.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={laad} disabled={laden}>
          <RefreshCw className={`w-4 h-4 mr-2 ${laden ? "animate-spin" : ""}`} />
          Vernieuwen
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Object.entries({
          EVERYDAY_LOW_PRICE: "Altijd-Laagste-Prijs",
          PROMOTION_DRIVEN: "Promotiegedreven",
          MARKET_SHARE_ATTACK: "Marktaandeeloffensief",
          MARGIN_PROTECTION: "Margebescherming",
          INVENTORY_CLEARANCE: "Opruimingsstrategie",
          PRICE_FOLLOWER: "Prijsvolger",
          PRICE_LEADER: "Prijsleider",
        }).map(([type, label]) => {
          const Icon = STRATEGIE_ICONEN[type] || Tag;
          const count = data?.strategieen?.filter((s: any) => s.strategy_type === type).length ?? 0;
          return (
            <div key={type} className={`border rounded-md p-3 text-sm flex items-center gap-2 ${STRATEGIE_KLEUREN[type]}`}>
              <Icon className="w-4 h-4 shrink-0" />
              <div>
                <div className="font-medium">{label}</div>
                <div className="text-xs opacity-70">{count} concurrent(en)</div>
              </div>
            </div>
          );
        })}
      </div>

      {fout && (
        <Card className="border-red-200 bg-red-50/50">
          <CardContent className="pt-6 flex items-center gap-2 text-red-600">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm">{fout}</span>
          </CardContent>
        </Card>
      )}

      {!laden && data?.low_history && (
        <Card className="border-amber-200 bg-amber-50/60">
          <CardContent className="pt-6 flex items-start gap-2 text-amber-700">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span className="text-sm">
              {data.history_notice ||
                "Beperkte prijshistorie beschikbaar — de herkende strategieën zijn indicatief en worden betrouwbaarder naarmate meer concurrentprijs-historie is opgebouwd."}
            </span>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Concurrentenclassificatie</CardTitle>
          <CardDescription>
            Gebaseerd op prijshistorie van de afgelopen 30 dagen.
            {data?.periode && <span className="ml-2 text-muted-foreground">{data.periode}</span>}
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {laden ? (
            <div className="p-6 space-y-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : !data?.strategieen?.length ? (
            <div className="p-10 text-center text-muted-foreground">
              <AlertCircle className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="font-medium">Geen concurrentiedata beschikbaar</p>
              <p className="text-sm mt-1">
                Importeer concurrentieprijzen via Gegevensintegratie om analyses te starten.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Concurrent</TableHead>
                  <TableHead>Strategie</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead className="hidden md:table-cell">Reden</TableHead>
                  <TableHead className="hidden lg:table-cell">Aanbevolen reactie</TableHead>
                  <TableHead className="text-right">Datapunten</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.strategieen.map((s: any) => {
                  const Icon = STRATEGIE_ICONEN[s.strategy_type] || Tag;
                  const conf = Math.round(s.confidence * 100);
                  return (
                    <TableRow key={s.concurrent}>
                      <TableCell className="font-medium">{s.concurrent}</TableCell>
                      <TableCell>
                        <Badge className={`text-xs ${STRATEGIE_KLEUREN[s.strategy_type] || ""}`}>
                          <Icon className="w-3 h-3 mr-1" />
                          {s.label_nl}
                        </Badge>
                      </TableCell>
                      <TableCell className="min-w-[120px]">
                        <div className="flex items-center gap-2">
                          <Progress value={conf} className="h-2 w-20" />
                          <span className="text-xs tabular-nums text-muted-foreground">{conf}%</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground hidden md:table-cell max-w-[200px] truncate">
                        {s.reden}
                      </TableCell>
                      <TableCell className="text-xs hidden lg:table-cell max-w-[220px] text-muted-foreground">
                        {s.aanbevolen_reactie}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm">{s.datapunten ?? "—"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
