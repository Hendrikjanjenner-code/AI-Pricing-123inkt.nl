import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { ArrowRightLeft, TrendingUp, ShieldCheck } from "lucide-react";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const ACTIE_KLEUREN: Record<string, string> = {
  PRIVATE_LABEL_PUSH: "bg-emerald-500/10 text-emerald-600 border-emerald-200",
  PORTFOLIO_MARGIN_OPTIMIZATION: "bg-primary/10 text-primary border-primary/20",
  TRAFFIC_TO_MARGIN_SWITCH: "bg-amber-500/10 text-amber-600 border-amber-200",
  PRICE_A_BRAND_COMPETITIVELY: "bg-blue-500/10 text-blue-600 border-blue-200",
  HOLD_PRICE_MONITOR: "bg-slate-100 text-slate-500 border-slate-200",
};

export default function HuismerkImpact() {
  const [minIsv, setMinIsv] = useState("0");
  const [actie, setActie] = useState("all");
  const [huidigSku, setHuidigSku] = useState<string | null>(null);

  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  const { data: overzicht, isLoading: ladenOverzicht } = useQuery({
    queryKey: ["huismerk-overzicht", minIsv, actie, filterQs],
    queryFn: () =>
      apiFetch(`/api/huismerk-impact/overzicht?page_size=200&min_isv=${minIsv}${actie !== "all" ? `&actie=${actie}` : ""}${filterQs ? `&${filterQs}` : ""}`),
  });

  const { data: detail, isLoading: ladenDetail } = useQuery({
    queryKey: ["huismerk-sku", huidigSku],
    queryFn: () => apiFetch(`/api/huismerk-impact/sku/${huidigSku}`),
    enabled: !!huidigSku,
  });

  const items = overzicht?.items || [];

  const fmtBedrag = (v: number | null | undefined) =>
    v != null ? new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(v) : '—';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Huismerk Impact Monitor</h1>
        <p className="text-muted-foreground mt-1">A-merk vs. huismerk — ISV (Internal Substitution Value) en aanbevolen portefeuilleactie.</p>
      </div>

      <GlobalFilterBar />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground flex items-center gap-2 mb-1"><ArrowRightLeft className="h-4 w-4" /> Actieve paren</div>
            <div className="text-2xl font-bold">{items.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground flex items-center gap-2 mb-1"><TrendingUp className="h-4 w-4 text-emerald-500" /> Hoge ISV-kansen</div>
            <div className="text-2xl font-bold text-emerald-600">{items.filter((s: any) => s.isv >= 0.50).length}</div>
            <div className="text-xs text-muted-foreground">ISV ≥ 0,50 — huismerk push overwegen</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground flex items-center gap-2 mb-1"><ShieldCheck className="h-4 w-4 text-primary" /> Gem. ISV</div>
            <div className="text-2xl font-bold text-primary">
              {items.length ? (items.reduce((a: number, s: any) => a + (s.isv || 0), 0) / items.length).toFixed(3) : "—"}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-3 bg-card p-4 border rounded-md">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium whitespace-nowrap">Min. ISV:</span>
          <Input type="number" min="0" max="1" step="0.05" value={minIsv}
            onChange={e => setMinIsv(e.target.value)} className="w-24" />
        </div>
        <Select value={actie} onValueChange={setActie}>
          <SelectTrigger className="w-64"><SelectValue placeholder="Alle acties" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle aanbevolen acties</SelectItem>
            <SelectItem value="PRIVATE_LABEL_PUSH">Huismerk push</SelectItem>
            <SelectItem value="PORTFOLIO_MARGIN_OPTIMIZATION">Portfolio margeopt.</SelectItem>
            <SelectItem value="TRAFFIC_TO_MARGIN_SWITCH">Traffic → marge</SelectItem>
            <SelectItem value="PRICE_A_BRAND_COMPETITIVELY">A-merk competitief prijzen</SelectItem>
            <SelectItem value="HOLD_PRICE_MONITOR">Handhaven, monitoren</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
        <div className="md:col-span-3 border rounded-md bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>A-merk</TableHead>
                <TableHead>Huismerk</TableHead>
                <TableHead className="text-right">ISV</TableHead>
                <TableHead className="text-right">Schakelkans</TableHead>
                <TableHead>Actie</TableHead>
                <TableHead>EAN / OEM</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ladenOverzicht ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    {[1,2,3,4,5,6].map(j => <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>)}
                  </TableRow>
                ))
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">Geen paren gevonden.</TableCell>
                </TableRow>
              ) : items.map((s: any) => (
                <TableRow key={`${s.a_merk_sku}-${s.huismerk_sku}`}
                  className={`cursor-pointer hover:bg-muted/50 ${huidigSku === s.a_merk_sku ? "bg-muted" : ""}`}
                  onClick={() => setHuidigSku(s.a_merk_sku)}>
                  <TableCell>
                    <div className="text-sm font-medium truncate max-w-[140px]">{s.a_merk_naam}</div>
                    <div className="text-xs text-muted-foreground font-mono">{s.a_merk_sku}</div>
                    {s.a_merk_prijs && <div className="text-xs text-muted-foreground">{fmtBedrag(s.a_merk_prijs)}</div>}
                  </TableCell>
                  <TableCell>
                    <div className="text-sm font-medium truncate max-w-[140px] text-primary">{s.huismerk_naam}</div>
                    <div className="text-xs text-muted-foreground font-mono">{s.huismerk_sku}</div>
                    {s.huismerk_prijs && <div className="text-xs text-muted-foreground">{fmtBedrag(s.huismerk_prijs)}</div>}
                  </TableCell>
                  <TableCell className="text-right">
                    <span className={`font-mono font-bold tabular-nums text-sm ${s.isv >= 0.5 ? "text-emerald-600" : s.isv >= 0.3 ? "text-amber-600" : "text-muted-foreground"}`}>
                      {s.isv.toFixed(3)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <span className="font-mono tabular-nums text-sm">{(s.schakelkans * 100).toFixed(0)}%</span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[10px] ${ACTIE_KLEUREN[s.aanbevolen_actie] || ""}`}>
                      {s.actie_label}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs font-mono text-muted-foreground">
                    <div>A: {s.a_merk_ean || "—"} / {s.a_merk_oem || "—"}</div>
                    <div>H: {s.huismerk_ean || "—"} / {s.huismerk_oem || "—"}</div>
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
                <ArrowRightLeft className="h-10 w-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">Selecteer een paar</p>
                <p className="text-sm mt-1">voor ISV-details</p>
              </div>
            </Card>
          ) : ladenDetail ? (
            <Skeleton className="h-64 w-full" />
          ) : detail?.data_beschikbaar ? (
            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">{detail.product_naam}</CardTitle>
                  <CardDescription className="text-xs">
                    {detail.is_a_merk ? "A-merk" : detail.is_huismerk ? "Huismerk" : ""} · {detail.categorie}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-center py-3">
                    <div className="text-xs text-muted-foreground">Hoogste ISV</div>
                    <div className={`text-4xl font-bold mt-1 ${detail.hoogste_isv >= 0.5 ? "text-emerald-600" : detail.hoogste_isv >= 0.3 ? "text-amber-600" : "text-muted-foreground"}`}>
                      {detail.hoogste_isv.toFixed(3)}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">ISV = schakelkans × margekloof</div>
                  </div>
                  {detail.primaire_aanbeveling && (
                    <Badge variant="outline" className={`w-full justify-center text-sm py-1.5 ${ACTIE_KLEUREN[detail.primaire_aanbeveling] || ""}`}>
                      {detail.paren?.[0]?.actie_label}
                    </Badge>
                  )}
                </CardContent>
              </Card>

              {detail.paren?.map((p: any, i: number) => (
                <Card key={i}>
                  <CardContent className="pt-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <div className="text-muted-foreground text-xs">A-merk prijs</div>
                        <div className="font-semibold">{fmtBedrag(p.a_merk_prijs)}</div>
                        {p.a_merk_marge_pct && <div className="text-xs text-muted-foreground">Marge: {(p.a_merk_marge_pct * 100).toFixed(1)}%</div>}
                      </div>
                      <div>
                        <div className="text-muted-foreground text-xs">Huismerk prijs</div>
                        <div className="font-semibold text-primary">{fmtBedrag(p.huismerk_prijs)}</div>
                        {p.huismerk_marge_pct && <div className="text-xs text-muted-foreground">Marge: {(p.huismerk_marge_pct * 100).toFixed(1)}%</div>}
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-muted-foreground">Schakelkans</span>
                        <span className="font-medium">{(p.schakelkans * 100).toFixed(0)}%</span>
                      </div>
                      <Progress value={p.schakelkans * 100} className="h-2" />
                    </div>
                    {p.actie_reden && (
                      <div className="text-xs text-muted-foreground bg-muted/50 rounded p-2">{p.actie_reden}</div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="h-48 flex items-center justify-center text-center text-muted-foreground">
              <div>Geen ISV-data beschikbaar voor {huidigSku}</div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
