/**
 * Help & Begrippen (taak #221) — zoekbare begrippenlijst over alle KPI's,
 * scores en platformconcepten (CRS, Influence, BCG, GEO, AEO, Product
 * Hierarchy, …). Bouwt op de centrale kennisbank (kpi-definitions.ts).
 */
import { useMemo, useState } from "react";
import { BookOpen, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  KPI_DEFINITIES, ALLE_CATEGORIEEN, type KpiCategorie, type KpiDefinition,
} from "@/lib/kpi-definitions";

export default function Begrippen() {
  const [zoek, setZoek] = useState("");
  const [categorie, setCategorie] = useState<KpiCategorie | "alle">("alle");

  const definities = useMemo(() => {
    const term = zoek.trim().toLowerCase();
    const uniek = new Map<string, KpiDefinition>();
    for (const d of Object.values(KPI_DEFINITIES)) uniek.set(d.id, d);
    return [...uniek.values()]
      .filter((d) => categorie === "alle" || d.categorie === categorie)
      .filter((d) =>
        !term ||
        d.naam.toLowerCase().includes(term) ||
        (d.afkorting ?? "").toLowerCase().includes(term) ||
        d.korteUitleg.toLowerCase().includes(term) ||
        d.uitgebreideUitleg.toLowerCase().includes(term))
      .sort((a, b) => a.naam.localeCompare(b.naam));
  }, [zoek, categorie]);

  const catLabel = (id: KpiCategorie) =>
    ALLE_CATEGORIEEN.find((c) => c.id === id)?.label ?? id;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BookOpen className="w-6 h-6" /> Help & Begrippen
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Alle KPI's, scores en platformbegrippen — doorzoekbaar en per categorie.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Zoek op naam, afkorting of uitleg (bv. CRS, BCG, GEO)…"
            value={zoek}
            onChange={(e) => setZoek(e.target.value)}
            data-testid="input-begrippen-zoek"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge
            variant={categorie === "alle" ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => setCategorie("alle")}
            data-testid="begrippen-cat-alle"
          >
            Alle
          </Badge>
          {ALLE_CATEGORIEEN.map((c) => (
            <Badge
              key={c.id}
              variant={categorie === c.id ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => setCategorie(c.id)}
              data-testid={`begrippen-cat-${c.id}`}
            >
              {c.label}
            </Badge>
          ))}
        </div>
      </div>

      <p className="text-xs text-muted-foreground" data-testid="begrippen-aantal">
        {definities.length} begrippen
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        {definities.map((d) => (
          <Card key={d.id} data-testid={`begrip-${d.id}`}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2 flex-wrap">
                {d.naam}
                {d.afkorting && <Badge variant="secondary">{d.afkorting}</Badge>}
                <Badge variant="outline" className="ml-auto text-[10px]">
                  {catLabel(d.categorie)}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>{d.uitgebreideUitleg}</p>
              {d.formule && (
                <p className="font-mono text-xs bg-muted rounded px-2 py-1">{d.formule}</p>
              )}
              <p className="text-muted-foreground"><span className="font-medium text-foreground">Interpretatie:</span> {d.interpretatie}</p>
              <p className="text-muted-foreground"><span className="font-medium text-foreground">Business-impact:</span> {d.businessImpact}</p>
            </CardContent>
          </Card>
        ))}
        {definities.length === 0 && (
          <p className="text-muted-foreground col-span-2 text-center py-12">
            Geen begrippen gevonden voor deze zoekopdracht.
          </p>
        )}
      </div>
    </div>
  );
}
