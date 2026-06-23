import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertCircle, CheckCircle2, Circle, FileSpreadsheet, Link, Server } from "lucide-react";

const VEREISTE_VELDEN = [
  { veld: "product_id", type: "string", beschr: "Interne product-ID in DRS", verplicht: true },
  { veld: "sku_code", type: "string", beschr: "EAN / artikelnummer", verplicht: true },
  { veld: "description", type: "string", beschr: "Productomschrijving", verplicht: true },
  { veld: "category_code", type: "string", beschr: "Categoriecode", verplicht: true },
  { veld: "cost_price", type: "decimal", beschr: "Inkoopprijs excl. BTW", verplicht: true },
  { veld: "selling_price", type: "decimal", beschr: "Huidige verkoopprijs incl. BTW", verplicht: true },
  { veld: "stock_qty", type: "integer", beschr: "Actuele voorraad", verplicht: true },
  { veld: "sales_qty_7d", type: "integer", beschr: "Verkopen afgelopen 7 dagen", verplicht: false },
  { veld: "sales_qty_30d", type: "integer", beschr: "Verkopen afgelopen 30 dagen", verplicht: false },
  { veld: "last_sale_date", type: "date", beschr: "Datum laatste verkoop (YYYY-MM-DD)", verplicht: false },
  { veld: "supplier_id", type: "string", beschr: "Leverancier-ID", verplicht: false },
];

const CHECKLIST = [
  { item: "Verbinding: DRS API-endpoint beschikbaar en bereikbaar vanuit deze omgeving", gereed: false },
  { item: "Authenticatie: API-sleutel of OAuth2-token verkregen van DRS-beheerder", gereed: false },
  { item: "Veldmapping: DRS-velden gemapt naar intern schema (zie tabel)", gereed: false },
  { item: "Testimport: Klein subset (10 SKU's) succesvol geïmporteerd", gereed: false },
  { item: "Go-live: Volledige Paper_Copy catalogus geïmporteerd en gevalideerd", gereed: false },
];

export default function DrsIntegratie() {
  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">DRS Integratie</h1>
        <p className="text-muted-foreground mt-1">
          Dynamisch Retail Systeem — productdata, verkopen en voorraad importeren.
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
              DRS API-koppeling is nog niet geconfigureerd.
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
              Gebruik de Gegevensintegratie-pagina om DRS-data handmatig te uploaden als CSV.
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
            <Badge variant="outline" className="text-muted-foreground">DRS REST API</Badge>
            <p className="text-xs text-muted-foreground mt-2">
              Directe API-koppeling voor real-time synchronisatie (nog niet geïmplementeerd).
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Vereiste datavelden</CardTitle>
          <CardDescription>
            Deze velden worden verwacht vanuit DRS bij een API-koppeling of CSV-export.
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
          <CardTitle>Technische checklist</CardTitle>
          <CardDescription>
            Doorloop deze stappen om de DRS API-koppeling in te stellen.
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
            Zolang de DRS API-koppeling nog niet is gerealiseerd, exporteer data handmatig uit DRS als CSV
            en upload via <strong>Gegevensintegratie → Productcatalogus / Verkoopdata / Voorraad</strong>.
            De CSV-formaten zijn afgestemd op het DRS-exportformaat.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
