import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertCircle, CheckCircle2, Circle, FileSpreadsheet, Link, Server } from "lucide-react";

const VEREISTE_VELDEN = [
  { veld: "sessions", type: "integer", beschr: "Sessies per SKU / categorie / dag", verplicht: true },
  { veld: "pageviews", type: "integer", beschr: "Paginaweergaven per SKU", verplicht: true },
  { veld: "add_to_cart", type: "integer", beschr: "Toevoegingen aan winkelwagen", verplicht: true },
  { veld: "orders", type: "integer", beschr: "Bestellingen vanuit deze pagina", verplicht: true },
  { veld: "conversion_rate", type: "float", beschr: "Conversieratio (orders / sessions)", verplicht: true },
  { veld: "channel", type: "string", beschr: "Verkeerskanaal: organic / paid / direct / email / social", verplicht: true },
  { veld: "device", type: "string", beschr: "Apparaattype: desktop / mobile / tablet", verplicht: false },
  { veld: "landing_page", type: "string", beschr: "Landingspagina-URL of slug (bv. /paper-a4-80g)", verplicht: false },
];

const CHECKLIST = [
  { item: "GA4-property ID opgehaald uit Google Analytics-beheercentrum", gereed: false },
  { item: "Service account aangemaakt in Google Cloud Console met GA4 Viewer-recht", gereed: false },
  { item: "Service account JSON-sleutelbestand veilig opgeslagen als omgevingsvariabele", gereed: false },
  { item: "SKU's gemapt op GA4 item_id of pagina-slug (veldmapping gedocumenteerd)", gereed: false },
  { item: "Testquery: 7 dagen traffic voor 5 test-SKU's succesvol opgehaald", gereed: false },
  { item: "Go-live: Dagelijkse sync ingesteld voor volledige Paper_Copy catalogus", gereed: false },
];

const CSV_VOORBEELD = `datum,sku_id,sessions,pageviews,add_to_cart,orders,conversion_rate,channel,device
2026-06-20,PAP001,142,198,23,8,0.056,organic,desktop
2026-06-20,PAP001,67,89,9,3,0.045,paid,mobile
2026-06-20,PAP002,88,112,15,5,0.057,organic,desktop`;

export default function Ga4Integratie() {
  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">GA4 Integratie</h1>
        <p className="text-muted-foreground mt-1">
          Google Analytics 4 — sessies, conversies en traffic-kanalen per SKU koppelen.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Server className="w-4 h-4 text-muted-foreground" />
              Verbindingsstatus
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-gray-400" />
              <span className="font-medium text-muted-foreground">Niet gekoppeld</span>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              GA4 API-koppeling is nog niet geconfigureerd.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4 text-muted-foreground" />
              Huidige methode
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge className="bg-blue-50 text-blue-600 border-blue-200">CSV Import</Badge>
            <p className="text-xs text-muted-foreground mt-2">
              Exporteer GA4-data als CSV en upload via Gegevensintegratie → Traffic.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Link className="w-4 h-4 text-muted-foreground" />
              Toekomstige optie
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant="outline" className="text-muted-foreground">GA4 Data API v1</Badge>
            <p className="text-xs text-muted-foreground mt-2">
              Directe API-koppeling via service account (nog niet geïmplementeerd).
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Vereiste datavelden (8)</CardTitle>
          <CardDescription>
            Deze velden worden verwacht per SKU per dag, gesegmenteerd op kanaal en apparaat.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Veldnaam</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Omschrijving</TableHead>
                <TableHead>Verplicht</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {VEREISTE_VELDEN.map((v) => (
                <TableRow key={v.veld}>
                  <TableCell className="font-mono text-sm">{v.veld}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs font-mono">{v.type}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">{v.beschr}</TableCell>
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

      <Card>
        <CardHeader>
          <CardTitle>CSV-voorbeeldformaat</CardTitle>
          <CardDescription>
            Gebruik dit formaat bij handmatige CSV-export uit GA4 Looker Studio of Data Export.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="bg-muted rounded-md p-4 text-xs font-mono overflow-x-auto whitespace-pre">
{CSV_VOORBEELD}
          </pre>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Technische checklist</CardTitle>
          <CardDescription>
            Doorloop deze stappen om de GA4 API-koppeling in te stellen.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {CHECKLIST.map((item, i) => (
              <li key={i} className="flex items-start gap-3">
                <div className="mt-0.5 shrink-0">
                  {item.gereed
                    ? <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    : <Circle className="w-5 h-5 text-muted-foreground/50" />}
                </div>
                <div>
                  <span className="text-sm font-medium mr-2 text-muted-foreground">Stap {i + 1}</span>
                  <span className="text-sm">{item.item}</span>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card className="border-amber-200 bg-amber-50/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2 text-amber-700">
            <AlertCircle className="w-4 h-4" />
            Tijdelijke werkwijze
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-amber-700">
            Exporteer traffic-data wekelijks uit GA4 (Verkennen → Exporteren → CSV) en upload via{" "}
            <strong>Gegevensintegratie → Traffic</strong>. Zorg dat het CSV-bestand de 8 vereiste
            velden bevat zoals beschreven in het voorbeeldformaat hierboven.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
