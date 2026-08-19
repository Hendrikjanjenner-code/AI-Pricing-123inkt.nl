import { useState } from "react";
import { Link } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Target, TrendingDown, TrendingUp, ShieldCheck, ShieldAlert } from "lucide-react";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const CIS_KLASSE_KLEUREN: Record<string, string> = {
  "Primaire concurrent": "bg-red-500/15 text-red-700 border-red-300",
  "Sterke concurrent": "bg-orange-500/15 text-orange-700 border-orange-300",
  "Secundaire concurrent": "bg-amber-500/15 text-amber-700 border-amber-300",
  "Zwakke concurrent": "bg-blue-500/15 text-blue-700 border-blue-300",
  "Negeren": "bg-slate-100 text-slate-500 border-slate-200",
};

const STATUS_KLEUREN: Record<string, string> = {
  "Actief": "bg-emerald-500/10 text-emerald-600 border-emerald-200",
  "Monitoren": "bg-amber-500/10 text-amber-600 border-amber-200",
  "Negeren": "bg-slate-100 text-slate-500 border-slate-200",
};

const LAAG_LABELS: Record<string, string> = {
  direct: "Directe concurrentie",
  functioneel: "Functionele concurrentie",
  categorie: "Categorieconcurrentie",
  intern: "Interne concurrentie",
};

export default function SkuConcurrentieAnalyse() {
  const [zoekSku, setZoekSku] = useState("");
  const [huidigSku, setHuidigSku] = useState<string | null>(null);
  const [categorie, setCategorie] = useState("all");
  const [laag, setLaag] = useState("all");

  const { data: overzicht, isLoading: ladenOverzicht } = useQuery({
    queryKey: ["concurrentie-overzicht", categorie],
    queryFn: () => apiFetch(`/api/concurrentie/overzicht?page_size=200${categorie !== "all" ? `&categorie=${encodeURIComponent(categorie)}` : ""}`),
  });

  const { data: skuDetail, isLoading: ladenDetail } = useQuery({
    queryKey: ["concurrentie-sku", huidigSku],
    queryFn: () => apiFetch(`/api/concurrentie/sku/${huidigSku}`),
    enabled: !!huidigSku,
  });

  const gefilterdItems = (overzicht?.items || []).filter((s: any) =>
    !zoekSku || s.sku_id?.toLowerCase().includes(zoekSku.toLowerCase()) || s.product_naam?.toLowerCase().includes(zoekSku.toLowerCase())
  );

  const gefilterdConcurrenten = (skuDetail?.concurrenten || []).filter((c: any) =>
    laag === "all" || c.concurrentielaag === laag
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">SKU Concurrentie-analyse</h1>
        <p className="text-muted-foreground mt-1">CIS · CSRS · CSS per concurrent per SKU — wie volgen we en waarom?</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="md:col-span-1 h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">SKU selecteren</CardTitle>
            <div className="flex gap-2 mt-2">
              <Input
                placeholder="Zoek op SKU of naam..."
                value={zoekSku}
                onChange={e => setZoekSku(e.target.value)}
                className="text-sm"
              />
              <Select value={categorie} onValueChange={setCategorie}>
                <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle cat.</SelectItem>
                  <SelectItem value="Ink & Toner">Inkt & Toner</SelectItem>
                  <SelectItem value="Paper">Papier</SelectItem>
                  <SelectItem value="Office Supplies">Kantoor</SelectItem>
                  <SelectItem value="Electronics">Elektronica</SelectItem>
                  <SelectItem value="Furniture">Meubilair</SelectItem>
                  <SelectItem value="Printers">Printers</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y max-h-[580px] overflow-y-auto">
              {ladenOverzicht ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="p-3"><Skeleton className="h-10 w-full" /></div>
                ))
              ) : gefilterdItems.map((s: any) => (
                <button key={s.sku_id} onClick={() => setHuidigSku(s.sku_id)}
                  className={`w-full text-left p-3 hover:bg-muted/50 transition-colors ${huidigSku === s.sku_id ? "bg-muted" : ""}`}>
                  <div className="flex items-center justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{s.product_naam}</div>
                      <div className="text-xs text-muted-foreground font-mono">{s.sku_id}</div>
                    </div>
                    <div className="ml-2 shrink-0">
                      <Badge variant="outline" className={`text-[10px] ${CIS_KLASSE_KLEUREN[s.cis_klasse] || ""}`}>
                        CIS {Math.round((s.max_cis || 0) * 100)}
                      </Badge>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <div className="md:col-span-2 space-y-4">
          {!huidigSku ? (
            <Card className="h-48 flex items-center justify-center text-center text-muted-foreground">
              <div>
                <Target className="h-10 w-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">Selecteer een SKU</p>
                <p className="text-sm mt-1">om de concurrentenanalyse te bekijken</p>
              </div>
            </Card>
          ) : ladenDetail ? (
            <div className="space-y-4">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-48 w-full" />
            </div>
          ) : skuDetail && (
            <>
              <Card>
                <CardContent className="pt-4">
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div>
                      <div className="font-semibold text-base">{skuDetail.product_naam}</div>
                      <div className="text-sm text-muted-foreground">{skuDetail.merk} · {skuDetail.categorie}</div>
                    </div>
                    <div className="flex gap-4 text-sm">
                      <div>
                        <div className="text-muted-foreground">Eigen prijs</div>
                        <div className="font-semibold">€{skuDetail.eigen_prijs?.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Gewogen referentieprijs</div>
                        <div className="font-semibold text-primary">
                          {skuDetail.gewogen_referentieprijs ? `€${skuDetail.gewogen_referentieprijs.toFixed(2)}` : "—"}
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2 text-xs">
                      {[
                        ["Actief", skuDetail.samenvatting?.actief, "emerald"],
                        ["Monitoren", skuDetail.samenvatting?.monitoren, "amber"],
                        ["Negeren", skuDetail.samenvatting?.negeren, "slate"],
                      ].map(([label, count, color]: any) => (
                        <div key={label} className="text-center">
                          <div className={`text-lg font-bold text-${color}-600`}>{count}</div>
                          <div className="text-muted-foreground">{label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="flex gap-3 items-center">
                <span className="text-sm font-medium text-muted-foreground">Laag:</span>
                <Select value={laag} onValueChange={setLaag}>
                  <SelectTrigger className="w-52 h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Alle concurrentielagen</SelectItem>
                    <SelectItem value="direct">Directe concurrentie</SelectItem>
                    <SelectItem value="functioneel">Functionele concurrentie</SelectItem>
                    <SelectItem value="categorie">Categorieconcurrentie</SelectItem>
                    <SelectItem value="intern">Interne concurrentie</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
                {gefilterdConcurrenten.length === 0 ? (
                  <Card className="p-8 text-center text-muted-foreground">Geen concurrenten voor dit filter.</Card>
                ) : gefilterdConcurrenten.map((c: any, i: number) => (
                  <Card key={i} className={`border ${c.status === "Negeren" ? "opacity-60" : ""}`}>
                    <CardContent className="pt-4 pb-4">
                      <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
                        <div>
                          <div className="font-semibold">{c.concurrent}</div>
                          <div className="text-xs text-muted-foreground">{LAAG_LABELS[c.concurrentielaag] || c.concurrentielaag}</div>
                        </div>
                        <div className="flex gap-2 items-center">
                          {c.concurrent_prijs && (
                            <span className={`font-mono font-semibold ${(c.prijs_vs_eigen_pct || 0) < -5 ? "text-red-600" : (c.prijs_vs_eigen_pct || 0) > 5 ? "text-emerald-600" : ""}`}>
                              €{c.concurrent_prijs.toFixed(2)}
                              {c.prijs_vs_eigen_pct != null && (
                                <span className="text-xs ml-1">({c.prijs_vs_eigen_pct > 0 ? "+" : ""}{c.prijs_vs_eigen_pct.toFixed(1)}%)</span>
                              )}
                            </span>
                          )}
                          <Badge variant="outline" className={`text-[10px] ${
                            c.op_voorraad === true ? "bg-emerald-500/10 text-emerald-600 border-emerald-200"
                            : c.op_voorraad === false ? "bg-red-500/10 text-red-600 border-red-200"
                            : "bg-slate-100 text-slate-500 border-slate-200"
                          }`}>
                            {c.op_voorraad === true ? "Op voorraad" : c.op_voorraad === false ? "Niet op voorraad" : "Voorraad onbekend"}
                          </Badge>
                          <Badge variant="outline" className="text-[10px] bg-slate-100 text-slate-600 border-slate-200">
                            {c.levertijd_dagen != null
                              ? `Levertijd ${c.levertijd_dagen} ${c.levertijd_dagen === 1 ? "dag" : "dgn"}`
                              : "Levertijd onbekend"}
                          </Badge>
                          <Badge variant="outline" className={`text-[10px] ${CIS_KLASSE_KLEUREN[c.cis_klasse] || ""}`}>
                            {c.cis_klasse}
                          </Badge>
                          <Badge variant="outline" className={`text-[10px] ${STATUS_KLEUREN[c.status] || ""}`}>
                            {c.status}
                          </Badge>
                        </div>
                      </div>
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-muted-foreground">CIS-score</span>
                            <span className="font-medium tabular-nums">{Math.round(c.cis_score * 100)}</span>
                          </div>
                          <Progress value={c.cis_score * 100} className="h-1.5" />
                        </div>
                        <div>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-muted-foreground">CSRS (voorraad)</span>
                            <span className={`font-medium tabular-nums ${c.csrs_score < 0.25 ? "text-red-600" : c.csrs_score < 0.60 ? "text-amber-600" : "text-emerald-600"}`}>
                              {Math.round(c.csrs_score * 100)}
                            </span>
                          </div>
                          <Progress value={c.csrs_score * 100} className="h-1.5" />
                        </div>
                        <div>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-muted-foreground">CSS (duurzaamheid)</span>
                            <span className={`font-medium tabular-nums ${c.css_score < 0.45 ? "text-red-600" : c.css_score < 0.70 ? "text-amber-600" : "text-emerald-600"}`}>
                              {Math.round(c.css_score * 100)}
                            </span>
                          </div>
                          <Progress value={c.css_score * 100} className="h-1.5" />
                        </div>
                      </div>
                      {c.actie_reden && (
                        <div className="mt-2 text-xs text-muted-foreground bg-muted/50 rounded px-2 py-1">
                          <span className="font-medium">{c.reden_code}:</span> {c.prijsactie?.replace(/_/g, ' ')}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <Card className="bg-muted/30">
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap gap-6 text-xs text-muted-foreground">
            <div>
              <span className="font-medium text-foreground">CIS</span> = Concurrent Influence Score
              · Primaire &gt;0,80 · Sterk 0,60–0,80 · Secundair 0,40–0,60 · Zwak 0,20–0,40 · Negeren &lt;0,20
            </div>
            <div>
              <span className="font-medium text-foreground">CSRS</span> = Voorraadbetrouwbaarheid
              · Betrouwbaar ≥0,60 · Monitoren 0,25–0,60 · Negeren &lt;0,25
            </div>
            <div>
              <span className="font-medium text-foreground">CSS</span> = Prijsduurzaamheid
              · Duurzaam ≥0,70 · Twijfelachtig 0,45–0,70 · Niet duurzaam &lt;0,45
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
