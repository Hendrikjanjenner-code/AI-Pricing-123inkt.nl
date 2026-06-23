import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, AlertTriangle, ArrowRight } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const VERWIJDERDE_AFHANKELIJKHEDEN = [
  {
    module: "PriceShape API Export",
    oud: "Geautomatiseerde dagelijkse push naar PriceShape REST API (/api/v1/prices)",
    nieuw: "CSV-exportbestand via Prijsexport-pagina, handmatig te uploaden in PriceShape",
    status: "csv_export",
    impact: "Laag — handmatige stap toegevoegd",
  },
  {
    module: "PriceShape Webhook (prijsacceptatie)",
    oud: "PriceShape bevestigde goedgekeurde prijzen via POST /api/webhooks/priceshape-confirm",
    nieuw: "Status bijhouden in aanbevelingstabel; geen externe bevestiging nodig",
    status: "verwijderd",
    impact: "Geen — audit trail vervangt dit",
  },
  {
    module: "PriceShape SKU-ID sync",
    oud: "Interne SKU-ID's gemapt op PriceShape product_id via synchrone API-call bij aanmaken",
    nieuw: "SKU-ID's gebruikt als-is in CSV-export; mapping gedocumenteerd in export-template",
    status: "vereenvoudigd",
    impact: "Laag — let op ID-mapping bij import in PriceShape",
  },
  {
    module: "PriceShape prijsgrenzen (min/max)",
    oud: "Min/max-grenzen gesynchroniseerd naar PriceShape bij elke aanpassing",
    nieuw: "Grenzen opgeslagen in dim_product; gelden voor eigen engine; PriceShape heeft eigen grenzen",
    status: "losgekoppeld",
    impact: "Middel — dubbele grenzenconfiguratie vermijden",
  },
  {
    module: "PRICESHAPE_API_KEY env var",
    oud: "Vereiste omgevingsvariabele voor API-authenticatie",
    nieuw: "Niet meer nodig — verwijderd uit alle routes en .env",
    status: "verwijderd",
    impact: "Geen — kan omgevingsvariabele veilig verwijderen",
  },
];

const EXPORT_VELDEN = [
  { veld: "sku_id", beschr: "Interne SKU-ID (PriceShape: product_id)", verplicht: true },
  { veld: "product_name", beschr: "Productnaam", verplicht: true },
  { veld: "approved_price", beschr: "Door analist goedgekeurde prijs", verplicht: true },
  { veld: "current_price", beschr: "Huidige prijs (ter referentie)", verplicht: false },
  { veld: "strategy_type", beschr: "Toegepaste prijisstrategie", verplicht: false },
  { veld: "approved_at", beschr: "Tijdstip goedkeuring (ISO 8601)", verplicht: false },
  { veld: "approved_by", beschr: "Gebruikersnaam analist", verplicht: false },
];

const STATUS_STIJL: Record<string, { label: string; klasse: string }> = {
  csv_export:   { label: "CSV export",    klasse: "bg-blue-50 text-blue-700 border-blue-200" },
  verwijderd:   { label: "Verwijderd",    klasse: "bg-gray-50 text-gray-600 border-gray-200" },
  vereenvoudigd:{ label: "Vereenvoudigd", klasse: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  losgekoppeld: { label: "Losgekoppeld",  klasse: "bg-amber-50 text-amber-700 border-amber-200" },
};

export default function PriceShapeMigratie() {
  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Verwijderde PriceShape-afhankelijkheden</h1>
        <p className="text-muted-foreground mt-1">
          Overzicht van PriceShape API-koppelingen die zijn vervangen tijdens de overgang naar de
          interne AI Pricing Engine voor de Paper_Copy pilot.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              Vervangen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-emerald-600">
              {VERWIJDERDE_AFHANKELIJKHEDEN.length}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              PriceShape-afhankelijkheden gemigreerd of verwijderd
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              Aandacht vereist
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-amber-600">1</div>
            <p className="text-xs text-muted-foreground mt-1">
              Dubbele grenzen-configuratie vermijden (min/max)
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <XCircle className="w-4 h-4 text-gray-400" />
              Onnodige vars
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-gray-500">1</div>
            <p className="text-xs text-muted-foreground mt-1">
              PRICESHAPE_API_KEY kan veilig worden verwijderd
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Gemigreerde afhankelijkheden</CardTitle>
          <CardDescription>
            Elk onderdeel van de PriceShape-koppeling en hoe het is vervangen.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Module</TableHead>
                <TableHead>Oud (PriceShape)</TableHead>
                <TableHead>Nieuw (intern)</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Impact</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {VERWIJDERDE_AFHANKELIJKHEDEN.map((r) => (
                <TableRow key={r.module}>
                  <TableCell className="font-medium text-sm">{r.module}</TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-[180px]">{r.oud}</TableCell>
                  <TableCell className="text-xs max-w-[180px]">{r.nieuw}</TableCell>
                  <TableCell>
                    <Badge className={`text-xs ${STATUS_STIJL[r.status]?.klasse || ""}`}>
                      {STATUS_STIJL[r.status]?.label || r.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.impact}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Werkwijze: prijzen exporteren naar PriceShape</CardTitle>
          <CardDescription>
            De handmatige CSV-workflow die de directe API-koppeling vervangt.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {[
              "Keur aanbevelingen goed in de Prijsadviezen-pagina (of via bulkgoedkeuring).",
              "Navigeer naar Prijsexport en stel de gewenste filters in (categorie, datumbereik).",
              "Download het CSV-bestand met goedgekeurde prijzen.",
              "Log in op PriceShape en importeer het CSV-bestand via Import → Prijsbestand.",
              "Controleer in PriceShape of alle SKU-ID's correct zijn gemapt.",
            ].map((stap, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">
                  {i + 1}
                </span>
                <span className="text-sm">{stap}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>CSV-exportformaat</CardTitle>
          <CardDescription>
            Velden in het PriceShape-importbestand dat door Prijsexport wordt gegenereerd.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Veld</TableHead>
                <TableHead>Omschrijving</TableHead>
                <TableHead>Verplicht</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {EXPORT_VELDEN.map((v) => (
                <TableRow key={v.veld}>
                  <TableCell className="font-mono text-sm">{v.veld}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{v.beschr}</TableCell>
                  <TableCell>
                    {v.verplicht
                      ? <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Verplicht</Badge>
                      : <Badge variant="outline" className="text-xs">Optioneel</Badge>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card className="border-blue-200 bg-blue-50/50">
        <CardContent className="pt-6 flex items-start gap-3">
          <ArrowRight className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
          <div className="text-sm text-blue-700">
            <p className="font-medium">Tip: gebruik de interne engine als leidend systeem</p>
            <p className="mt-1">
              De AI Pricing Engine berekent en bewaakt alle prijsregels, veiligheidsmarges en
              concurrentieindices. PriceShape dient als uitvoerplatform. Zorg dat min/max-grenzen
              in PriceShape gelijk zijn aan de grenzen in dim_product — anders kunnen prijzen
              buiten het gewenste bereik vallen.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
