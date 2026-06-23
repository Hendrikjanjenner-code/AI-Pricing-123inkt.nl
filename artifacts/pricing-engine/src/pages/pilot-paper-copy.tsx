import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertCircle, CheckCircle2, TrendingDown, TrendingUp, Package, Users, BarChart3, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getAuthToken } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

async function fetchSummary() {
  const token = getAuthToken();
  const res = await fetch(`${BASE}/api/pilot/paper-copy/summary`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Ophalen mislukt");
  return res.json();
}

function KpiCard({ label, value, sub, icon: Icon, kleur = "default" }: {
  label: string;
  value: string | number | null;
  sub?: string;
  icon: React.ElementType;
  kleur?: "groen" | "rood" | "oranje" | "default";
}) {
  const kleuren: Record<string, string> = {
    groen: "text-emerald-600",
    rood: "text-red-500",
    oranje: "text-amber-500",
    default: "text-foreground",
  };
  return (
    <Card>
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardDescription className="text-xs font-medium uppercase tracking-wide">{label}</CardDescription>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${kleuren[kleur]}`}>
          {value !== null && value !== undefined ? value : "—"}
        </div>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

export default function PilotPaperCopy() {
  const [data, setData] = useState<any>(null);
  const [laden, setLaden] = useState(true);
  const [fout, setFout] = useState<string | null>(null);

  const laad = async () => {
    setLaden(true);
    setFout(null);
    try {
      const d = await fetchSummary();
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
          <h1 className="text-2xl font-bold tracking-tight">Pilot Dashboard — Paper_Copy</h1>
          <p className="text-muted-foreground mt-1">
            KPI-overzicht voor de Paper_Copy pilotcategorie. Data op basis van geïmporteerde CSV's.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={laad} disabled={laden}>
          <RefreshCw className={`w-4 h-4 mr-2 ${laden ? "animate-spin" : ""}`} />
          Vernieuwen
        </Button>
      </div>

      {fout && (
        <Card className="border-red-200 bg-red-50/50">
          <CardContent className="pt-6 flex items-center gap-2 text-red-600">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm">{fout}</span>
          </CardContent>
        </Card>
      )}

      {laden ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i}><CardContent className="pt-6"><Skeleton className="h-12 w-full" /></CardContent></Card>
          ))}
        </div>
      ) : data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard
              label="Geïmporteerde SKU's"
              value={data.geimporteerde_skus}
              icon={Package}
              sub="Paper-categorie"
              kleur={data.geimporteerde_skus > 0 ? "groen" : "rood"}
            />
            <KpiCard
              label="Concurrentieprijzen"
              value={data.concurrentieprijzen?.toLocaleString("nl-NL")}
              icon={BarChart3}
              sub="Totaal geïmporteerd"
              kleur={data.concurrentieprijzen > 0 ? "groen" : "rood"}
            />
            <KpiCard
              label="Scrapes vandaag"
              value={data.scrapes_vandaag}
              icon={RefreshCw}
              sub={data.laatste_scrape_status ?? "Geen scrapes"}
            />
            <KpiCard
              label="Gemiddelde prijsindex"
              value={data.gem_prijsindex !== null ? data.gem_prijsindex?.toFixed(3) : "—"}
              icon={TrendingUp}
              sub="Eigen prijs / marktprijs  (>1 = duurder)"
              kleur={
                data.gem_prijsindex === null ? "default"
                : data.gem_prijsindex > 1.05 ? "rood"
                : data.gem_prijsindex > 1.02 ? "oranje"
                : "groen"
              }
            />
            <KpiCard
              label="Gem. marge"
              value={data.gem_marge_pct !== null ? `${data.gem_marge_pct}%` : "—"}
              icon={TrendingUp}
              sub="Afgelopen 7 dagen"
            />
            <KpiCard
              label="Huismerk-aandeel"
              value={`${data.huismerk_aandeel_pct}%`}
              icon={Package}
              sub="Private label SKU's"
            />
            <KpiCard
              label="OEM vs huismerk gap"
              value={data.oem_vs_huismerk_prijsgap !== null ? `€ ${data.oem_vs_huismerk_prijsgap?.toFixed(2)}` : "—"}
              icon={TrendingDown}
              sub="Gemiddeld prijsverschil"
            />
            <KpiCard
              label="SKU's met prijsrisico"
              value={data.sku_met_prijsrisico?.length ?? 0}
              icon={AlertCircle}
              sub="Eigen prijs > alle concurrenten"
              kleur={data.sku_met_prijsrisico?.length > 0 ? "rood" : "groen"}
            />
          </div>

          <Card className={`border-l-4 ${
            !data.gem_prijsindex ? "border-l-gray-300"
            : data.gem_prijsindex > 1.05 ? "border-l-red-400"
            : data.gem_prijsindex > 1.02 ? "border-l-amber-400"
            : data.gem_prijsindex < 0.97 ? "border-l-blue-400"
            : "border-l-emerald-400"
          }`}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Categorieadvies</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm">{data.categorie_advies}</p>
            </CardContent>
          </Card>

          {data.sku_met_prijsrisico?.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-500" />
                  SKU's met prijsrisico ({data.sku_met_prijsrisico.length})
                </CardTitle>
                <CardDescription>Eigen prijs ligt boven alle concurrenten (elke concurrent is goedkoper).</CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>SKU</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Eigen prijs</TableHead>
                      <TableHead className="text-right">Hoogste concurrent</TableHead>
                      <TableHead className="text-right">Verschil</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.sku_met_prijsrisico.map((r: any) => (
                      <TableRow key={r.sku_id}>
                        <TableCell className="font-mono text-sm">{r.sku_id}</TableCell>
                        <TableCell className="text-sm">{r.product_name}</TableCell>
                        <TableCell className="text-right tabular-nums">€ {r.eigen_prijs?.toFixed(2)}</TableCell>
                        <TableCell className="text-right tabular-nums">€ {r.hoogste_concurrent?.toFixed(2)}</TableCell>
                        <TableCell className="text-right">
                          <Badge className="bg-red-50 text-red-600 border-red-200">
                            +{r.verschil_pct?.toFixed(1)}%
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {data.sku_met_huismerkkans?.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                  SKU's met huismerkkans ({data.sku_met_huismerkkans.length})
                </CardTitle>
                <CardDescription>Concurrentprijs A-merk is hoger dan eigen huismerkprijs — kans om huismerk-voordeel te benadrukken.</CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Huismerk SKU</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Huismerkprijs</TableHead>
                      <TableHead className="text-right">Concurrent A-merk gem.</TableHead>
                      <TableHead className="text-right">Gap</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.sku_met_huismerkkans.map((r: any) => (
                      <TableRow key={r.huismerk_sku}>
                        <TableCell className="font-mono text-sm">{r.huismerk_sku}</TableCell>
                        <TableCell className="text-sm">{r.huismerk_naam}</TableCell>
                        <TableCell className="text-right tabular-nums">€ {r.huismerk_prijs?.toFixed(2)}</TableCell>
                        <TableCell className="text-right tabular-nums">€ {r.a_merk_concurrent_gem?.toFixed(2)}</TableCell>
                        <TableCell className="text-right">
                          <Badge className="bg-emerald-50 text-emerald-600 border-emerald-200">
                            +{r.gap_pct?.toFixed(1)}%
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {data.top5_concurrenten?.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  Top concurrenten — meeste prijswijzigingen (7 dagen)
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Concurrent</TableHead>
                      <TableHead className="text-right">Prijswijzigingen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.top5_concurrenten.map((r: any, i: number) => (
                      <TableRow key={r.concurrent}>
                        <TableCell>
                          <span className="text-muted-foreground mr-2">#{i + 1}</span>
                          {r.concurrent}
                        </TableCell>
                        <TableCell className="text-right tabular-nums font-medium">{r.wijzigingen}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {!data.data_status.heeft_producten && (
            <Card className="border-dashed">
              <CardContent className="pt-8 pb-8 text-center">
                <Package className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                <p className="font-medium">Geen Paper-SKU's gevonden</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Importeer productdata via Gegevensintegratie → Productcatalogus om dit dashboard te vullen.
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
