import { Link } from "wouter";
import { Database, TrendingUp, ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type Bron = "DRS" | "GA4" | "beide";

interface Props {
  titel: string;
  omschrijving: string;
  bron?: Bron;
}

/**
 * Eerlijke lege staat voor modules die een echte externe databron nodig hebben.
 *
 * Deze modules (Traffic, Mandje/Basket, Economic, verkoop-gedreven Elasticiteit)
 * tonen bewust GEEN synthetische data. Ze vereisen een gekoppelde externe
 * databron — DRS (verkoopdata) en/of GA4 (verkeersdata) — voordat er
 * betrouwbare cijfers getoond kunnen worden.
 */
export function ExterneDatabronVereist({ titel, omschrijving, bron = "beide" }: Props) {
  const toonDrs = bron === "DRS" || bron === "beide";
  const toonGa4 = bron === "GA4" || bron === "beide";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{titel}</h1>
        <p className="text-muted-foreground mt-1">{omschrijving}</p>
      </div>

      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center text-center gap-5 py-16 px-6">
          <div className="flex items-center gap-3">
            {toonDrs && (
              <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center">
                <Database className="w-7 h-7 text-primary" />
              </div>
            )}
            {toonGa4 && (
              <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center">
                <TrendingUp className="w-7 h-7 text-primary" />
              </div>
            )}
          </div>

          <div className="max-w-lg space-y-2">
            <h2 className="text-lg font-semibold">Externe databron vereist (DRS / GA4)</h2>
            <p className="text-sm text-muted-foreground">
              Deze module toont bewust geen data zolang er geen echte externe
              databron is gekoppeld. We tonen liever niets dan synthetische
              cijfers die geen operationele beslissingen mogen sturen.
            </p>
            <p className="text-sm text-muted-foreground">
              {bron === "DRS" && "Koppel DRS-verkoopdata om deze module te activeren."}
              {bron === "GA4" && "Koppel GA4-verkeersdata om deze module te activeren."}
              {bron === "beide" &&
                "Koppel DRS-verkoopdata en/of GA4-verkeersdata om deze module te activeren."}
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            {toonDrs && (
              <Link href="/drs-integratie">
                <Button variant="outline" className="gap-2">
                  <Database className="w-4 h-4" />
                  DRS Integratie
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </Link>
            )}
            {toonGa4 && (
              <Link href="/ga4-integratie">
                <Button variant="outline" className="gap-2">
                  <TrendingUp className="w-4 h-4" />
                  GA4 Integratie
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </Link>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default ExterneDatabronVereist;
