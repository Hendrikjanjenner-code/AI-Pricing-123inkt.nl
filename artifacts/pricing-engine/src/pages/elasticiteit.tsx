import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TrendingDown, TrendingUp, Info } from "lucide-react";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const BETROUWBAAR_KLEUREN: Record<string, string> = {
  hoog_betrouwbaar: "bg-emerald-500/10 text-emerald-600 border-emerald-200",
  bruikbaar: "bg-amber-500/10 text-amber-600 border-amber-200",
  laag_betrouwbaar: "bg-red-500/10 text-red-600 border-red-200",
};

export default function Elasticiteitsmonitor() {
  const [zoekterm, setZoekterm] = useState("");
  const [categorie, setCategorie] = useState("all");
  const [vertrouwen, setVertrouwen] = useState("all");
  const [huidigSku, setHuidigSku] = useState<string | null>(null);

  const { data: overzicht, isLoading: ladenOverzicht } = useQuery({
    queryKey: ["elasticiteit-overzicht", categorie, vertrouwen],
    queryFn: () =>
      apiFetch(`/api/elasticiteit/overzicht?page_size=200${
        categorie !== "all" ? `&categorie=${encodeURIComponent(categorie)}` : ""
      }${vertrouwen !== "all" ? `&vertrouwen=${vertrouwen}` : ""}`),
  });

  const { data: detail, isLoading: ladenDetail } = useQuery({
    queryKey: ["elasticiteit-sku", huidigSku],
    queryFn: () => apiFetch(`/api/elasticiteit/sku/${huidigSku}`),
    enabled: !!huidigSku,
  });

  const items = (overzicht?.items || []).filter((s: any) =>
    !zoekterm || s.sku_id?.toLowerCase().includes(zoekterm.toLowerCase()) || s.product_naam?.toLowerCase().includes(zoekterm.toLowerCase())
  );

  const formatElast = (v: number | null | undefined) => {
    if (v == null) return "—";
    const kleur = v < -1.5 ? "text-red-600" : v < -0.5 ? "text-amber-600" : "text-muted-foreground";
    return <span className={`font-mono font-semibold ${kleur}`}>{v.toFixed(2)}</span>;
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Elasticiteitsmonitor</h1>
        <p className="text-muted-foreground mt-1">Prijsgevoeligheid per SKU — eigen, kruiselasticiteit, competitief en intern.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-muted-foreground">
        {[
          { label: "Hoog betrouwbaar", beschr: "Betrouwbaarheidsscore >0,80", kleur: "emerald" },
          { label: "Bruikbaar", beschr: "Betrouwbaarheidsscore 0,50–0,80", kleur: "amber" },
          { label: "Laag betrouwbaar", beschr: "Betrouwbaarheidsscore <0,50 — interpreteer voorzichtig", kleur: "red" },
        ].map(item => (
          <Card key={item.label} className={`border-${item.kleur}-200 bg-${item.kleur}-50/30`}>
            <CardContent className="pt-3 pb-3 flex items-center gap-3">
              <Info className={`h-4 w-4 text-${item.kleur}-600 shrink-0`} />
              <div>
                <div className={`font-medium text-${item.kleur}-700`}>{item.label}</div>
                <div className="text-xs">{item.beschr}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex items-center gap-3 bg-card p-4 border rounded-md">
        <div className="relative flex-1">
          <Input placeholder="Zoek op SKU of productnaam..." value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
        </div>
        <Select value={categorie} onValueChange={setCategorie}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Alle categorieën" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle categorieën</SelectItem>
            <SelectItem value="Ink & Toner">Inkt & Toner</SelectItem>
            <SelectItem value="Paper">Papier</SelectItem>
            <SelectItem value="Office Supplies">Kantoorartikelen</SelectItem>
            <SelectItem value="Electronics">Elektronica</SelectItem>
            <SelectItem value="Furniture">Meubilair</SelectItem>
            <SelectItem value="Printers">Printers</SelectItem>
          </SelectContent>
        </Select>
        <Select value={vertrouwen} onValueChange={setVertrouwen}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Betrouwbaarheid" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle klassen</SelectItem>
            <SelectItem value="hoog_betrouwbaar">Hoog betrouwbaar</SelectItem>
            <SelectItem value="bruikbaar">Bruikbaar</SelectItem>
            <SelectItem value="laag_betrouwbaar">Laag betrouwbaar</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
        <div className="md:col-span-3 border rounded-md bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>SKU / Product</TableHead>
                <TableHead className="text-right">ε Eigen</TableHead>
                <TableHead className="text-right">ε Competitief</TableHead>
                <TableHead className="text-right">ε Intern</TableHead>
                <TableHead className="text-center">Betrouwbaarheid</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ladenOverzicht ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <TableRow key={i}>
                    {[1,2,3,4,5].map(j => <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>)}
                  </TableRow>
                ))
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">Geen data gevonden.</TableCell>
                </TableRow>
              ) : items.map((s: any) => (
                <TableRow key={s.sku_id}
                  className={`cursor-pointer hover:bg-muted/50 ${huidigSku === s.sku_id ? "bg-muted" : ""}`}
                  onClick={() => setHuidigSku(s.sku_id)}>
                  <TableCell>
                    <div className="font-medium text-sm truncate max-w-[200px]">{s.product_naam}</div>
                    <div className="text-xs text-muted-foreground font-mono">{s.sku_id}</div>
                  </TableCell>
                  <TableCell className="text-right">{formatElast(s.eigen_prijselasticiteit)}</TableCell>
                  <TableCell className="text-right">{formatElast(s.competitieve_elasticiteit)}</TableCell>
                  <TableCell className="text-right">{formatElast(s.interne_substitutie_elasticiteit)}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className={`text-[10px] ${BETROUWBAAR_KLEUREN[s.betrouwbaarheidsklasse] || ""}`}>
                      {s.betrouwbaarheidslabel}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="md:col-span-2">
          {!huidigSku ? (
            <Card className="h-48 flex items-center justify-center text-center text-muted-foreground">
              <div>
                <TrendingDown className="h-10 w-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">Selecteer een SKU</p>
                <p className="text-sm mt-1">voor elasticiteitsdetail</p>
              </div>
            </Card>
          ) : ladenDetail ? (
            <Skeleton className="h-64 w-full" />
          ) : detail?.data_beschikbaar ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">{detail.product_naam}</CardTitle>
                <CardDescription className="font-mono text-xs">{detail.sku_id}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="space-y-4">
                  {[
                    { label: "Eigen prijselasticiteit (ε)", waarde: detail.eigen_prijselasticiteit, interp: detail.interpretatie?.eigen },
                    { label: "Kruiselasticiteit (ε cross)", waarde: detail.kruiselasticiteit, interp: null },
                    { label: "Competitieve elasticiteit", waarde: detail.competitieve_elasticiteit, interp: detail.interpretatie?.competitief },
                    { label: "Interne substitutie-elasticiteit", waarde: detail.interne_substitutie_elasticiteit, interp: detail.interpretatie?.intern },
                  ].map(item => (
                    <div key={item.label}>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="font-medium">{item.label}</span>
                        <span className={`font-mono tabular-nums font-semibold ${(item.waarde || 0) < -1.5 ? "text-red-600" : (item.waarde || 0) < -0.5 ? "text-amber-600" : "text-muted-foreground"}`}>
                          {item.waarde?.toFixed(3) ?? "—"}
                        </span>
                      </div>
                      {item.interp && <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">{item.interp}</div>}
                    </div>
                  ))}
                </div>

                <div className="border-t pt-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Betrouwbaarheid</span>
                    <Badge variant="outline" className={`${BETROUWBAAR_KLEUREN[detail.betrouwbaarheidsklasse] || ""}`}>
                      {detail.betrouwbaarheidslabel}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground mt-2 space-y-1">
                    <div>Score: {(detail.betrouwbaarheidsscore * 100).toFixed(0)}%</div>
                    {detail.verkoopvolume_30d && <div>Volume 30d: {detail.verkoopvolume_30d} eenheden</div>}
                    {detail.pcis_score_gebruikt && <div>PCIS: {(detail.pcis_score_gebruikt * 100).toFixed(0)}</div>}
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="h-48 flex items-center justify-center text-center text-muted-foreground">
              <div>Geen elasticiteitsdata beschikbaar voor {huidigSku}</div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
