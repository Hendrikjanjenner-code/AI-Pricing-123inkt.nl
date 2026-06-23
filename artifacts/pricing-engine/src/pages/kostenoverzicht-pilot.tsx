import { useState, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Calculator, TrendingUp } from "lucide-react";

const VASTE_KOSTEN = [
  { post: "Replit hosting (maandelijks)", bedrag: 25, eenheid: "maand" },
  { post: "PostgreSQL opslag (Replit managed)", bedrag: 0, eenheid: "maand", toelichting: "Inbegrepen in Replit-plan tot 1 GB" },
  { post: "Scraping compute (server-side requests)", bedrag: 5, eenheid: "maand", toelichting: "Afhankelijk van volume" },
  { post: "Optionele proxy (anti-bot bypass)", bedrag: 30, eenheid: "maand", toelichting: "Alleen nodig bij geblokkeerde concurrenten" },
];

const ALTERNATIEVEN = [
  { naam: "PriceShape (SaaS)", maandelijks: 299, per_sku: 0.5, opmerkingen: "Min. 500 SKU's, geen eigen AI-engine" },
  { naam: "Prisync", maandelijks: 119, per_sku: 0.3, opmerkingen: "Basis competitor tracking, geen strategie-engine" },
  { naam: "Minderest", maandelijks: 499, per_sku: 1.2, opmerkingen: "Enterprise, DRS-koppeling beschikbaar" },
  { naam: "In-house (deze tool)", maandelijks: null, per_sku: null, opmerkingen: "Eigen data, volledige controle, Paper_Copy optimized" },
];

export default function KostenoverzichtPilot() {
  const [params, setParams] = useState({
    aantal_skus: 50,
    aantal_concurrenten: 5,
    scrapes_per_dag: 3,
    ai_analyses_per_dag: 100,
    kosten_per_ai_analyse: 0.002,
    opslag_per_maand: 10,
    hosting_per_maand: 25,
  });

  const set = (key: string, val: number) =>
    setParams(p => ({ ...p, [key]: val }));

  const kosten = useMemo(() => {
    const scrape_calls_per_maand = params.aantal_skus * params.aantal_concurrenten * params.scrapes_per_dag * 30;
    const scrape_kosten_per_maand = scrape_calls_per_maand * 0.00001;
    const ai_kosten_per_maand = params.ai_analyses_per_dag * 30 * params.kosten_per_ai_analyse;
    const maandelijks = params.opslag_per_maand + params.hosting_per_maand + scrape_kosten_per_maand + ai_kosten_per_maand;
    return {
      scrape_calls_per_maand: Math.round(scrape_calls_per_maand),
      scrape_kosten_per_maand: scrape_kosten_per_maand,
      ai_kosten_per_maand,
      maandelijks,
      kwartaal: maandelijks * 3,
      jaar: maandelijks * 12,
      per_sku_per_maand: params.aantal_skus > 0 ? maandelijks / params.aantal_skus : 0,
    };
  }, [params]);

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Kostenoverzicht Pilot</h1>
        <p className="text-muted-foreground mt-1">
          Bereken de geschatte kosten van de AI Pricing Pilot op basis van pilotparameters.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Calculator className="w-4 h-4" />
              Pilotparameters
            </CardTitle>
            <CardDescription>Pas de parameters aan om de kosten te berekenen.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              { key: "aantal_skus", label: "Aantal SKU's", min: 1, max: 10000 },
              { key: "aantal_concurrenten", label: "Aantal concurrenten", min: 1, max: 20 },
              { key: "scrapes_per_dag", label: "Scrapes per dag", min: 1, max: 24 },
              { key: "ai_analyses_per_dag", label: "AI-analyses per dag", min: 0, max: 10000 },
            ].map(({ key, label, min, max }) => (
              <div key={key} className="space-y-1">
                <Label className="text-sm">{label}</Label>
                <div className="flex items-center gap-3">
                  <Input
                    type="number"
                    min={min}
                    max={max}
                    value={(params as any)[key]}
                    onChange={e => set(key, Number(e.target.value) || 0)}
                    className="w-32 text-right"
                  />
                  <input
                    type="range"
                    min={min}
                    max={max}
                    value={(params as any)[key]}
                    onChange={e => set(key, Number(e.target.value))}
                    className="flex-1 accent-primary"
                  />
                </div>
              </div>
            ))}

            <div className="space-y-1">
              <Label className="text-sm">Kosten per AI-analyse (€)</Label>
              <Input
                type="number"
                step="0.0001"
                value={params.kosten_per_ai_analyse}
                onChange={e => set("kosten_per_ai_analyse", Number(e.target.value) || 0)}
                className="w-32 text-right"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-sm">Opslag/maand (€)</Label>
                <Input
                  type="number"
                  value={params.opslag_per_maand}
                  onChange={e => set("opslag_per_maand", Number(e.target.value) || 0)}
                  className="text-right"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-sm">Hosting/maand (€)</Label>
                <Input
                  type="number"
                  value={params.hosting_per_maand}
                  onChange={e => set("hosting_per_maand", Number(e.target.value) || 0)}
                  className="text-right"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Geschatte kosten
            </CardTitle>
            <CardDescription>Berekend op basis van ingestelde parameters.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-3">
              {[
                { label: "Per maand", value: kosten.maandelijks, highlight: false },
                { label: "Per kwartaal (3 maanden)", value: kosten.kwartaal, highlight: false },
                { label: "Per jaar", value: kosten.jaar, highlight: true },
              ].map(({ label, value, highlight }) => (
                <div key={label} className={`flex items-center justify-between p-3 rounded-md ${highlight ? "bg-primary/5 border border-primary/20" : "bg-muted/50"}`}>
                  <span className={`text-sm ${highlight ? "font-semibold" : ""}`}>{label}</span>
                  <span className={`font-bold tabular-nums ${highlight ? "text-primary text-lg" : ""}`}>
                    € {value.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>

            <div className="border-t pt-3 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Scrape-calls/maand</span>
                <span className="tabular-nums">{kosten.scrape_calls_per_maand.toLocaleString("nl-NL")}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Scraping-kosten/maand</span>
                <span className="tabular-nums">€ {kosten.scrape_kosten_per_maand.toFixed(4)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">AI-analysekosten/maand</span>
                <span className="tabular-nums">€ {kosten.ai_kosten_per_maand.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm font-medium border-t pt-2">
                <span>Kosten per SKU per maand</span>
                <span className="tabular-nums">€ {kosten.per_sku_per_maand.toFixed(4)}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Vaste kostenposten</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kostenpost</TableHead>
                <TableHead className="text-right">Bedrag</TableHead>
                <TableHead>Toelichting</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {VASTE_KOSTEN.map((k) => (
                <TableRow key={k.post}>
                  <TableCell className="text-sm">{k.post}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">
                    {k.bedrag === 0
                      ? <Badge variant="secondary" className="text-xs">Gratis</Badge>
                      : `€ ${k.bedrag} / ${k.eenheid}`}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{k.toelichting}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Vergelijking met externe tooling</CardTitle>
          <CardDescription>Op basis van {params.aantal_skus} SKU's.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tool</TableHead>
                <TableHead className="text-right">Maandelijks</TableHead>
                <TableHead className="text-right">Per SKU / maand</TableHead>
                <TableHead>Opmerkingen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ALTERNATIEVEN.map((a) => (
                <TableRow key={a.naam} className={a.naam.includes("eigen") || a.naam.includes("house") ? "bg-primary/5" : ""}>
                  <TableCell className="font-medium text-sm">
                    {a.naam}
                    {(a.naam.includes("eigen") || a.naam.includes("house")) && (
                      <Badge className="ml-2 bg-primary/10 text-primary text-xs">Huidige tool</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">
                    {a.maandelijks !== null
                      ? `€ ${a.maandelijks}`
                      : <span className="font-bold text-primary">€ {kosten.maandelijks.toFixed(2)}</span>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">
                    {a.per_sku !== null
                      ? `€ ${a.per_sku}`
                      : <span className="font-bold text-primary">€ {kosten.per_sku_per_maand.toFixed(4)}</span>}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{a.opmerkingen}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
