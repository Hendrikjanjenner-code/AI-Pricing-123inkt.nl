import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from "recharts";
import { TrendingDown, TrendingUp, Target, AlertTriangle } from "lucide-react";
import { useState } from "react";

const KLASSE_KLEUREN: Record<string, string> = {
  Critical: "bg-red-500/15 text-red-700 border-red-300",
  Strong: "bg-orange-500/15 text-orange-700 border-orange-300",
  Influence: "bg-amber-500/15 text-amber-700 border-amber-300",
  Monitor: "bg-blue-500/15 text-blue-700 border-blue-300",
  Ignore: "bg-slate-100 text-slate-500 border-slate-200",
};

const KLASSE_LABELS_NL: Record<string, string> = {
  Critical: "Kritiek",
  Strong: "Sterk",
  Influence: "Invloed",
  Monitor: "Bewaken",
  Ignore: "Negeren",
};

const KLASSE_BAR_KLEUREN: Record<string, string> = {
  Critical: "#ef4444",
  Strong: "#f97316",
  Influence: "#f59e0b",
  Monitor: "#3b82f6",
  Ignore: "#94a3b8",
};

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

export default function ConcurrentieIntelligence() {
  const [klasseFilter, setKlasseFilter] = useState("all");
  const [zoekterm, setZoekterm] = useState("");

  const { data: samenvatting, isLoading: ladenSamenvatting } = useQuery({
    queryKey: ["competition-summary"],
    queryFn: () => apiFetch("/api/competition/summary"),
  });

  const { data: skuData, isLoading: ladenSkus } = useQuery({
    queryKey: ["competition-skus", klasseFilter],
    queryFn: () => apiFetch(`/api/competition/skus?page_size=200${klasseFilter !== "all" ? `&competition_class=${klasseFilter}` : ""}`),
  });

  const { data: verdelingData } = useQuery({
    queryKey: ["competition-dist"],
    queryFn: () => apiFetch("/api/competition/charts/pcis-distribution"),
  });

  const { data: prijsIndexData } = useQuery({
    queryKey: ["competition-price-index"],
    queryFn: () => apiFetch("/api/competition/charts/price-index-by-category"),
  });

  const items = (skuData?.items || []).filter(
    (s: any) => !zoekterm
      || s.product_name?.toLowerCase().includes(zoekterm.toLowerCase())
      || s.sku_id?.toLowerCase().includes(zoekterm.toLowerCase())
  );

  const fmt = (v: number) => (v * 100).toFixed(0) + "%";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Concurrentie-intelligentie</h1>
        <p className="text-muted-foreground mt-1">PCIS-scores, concurrentenrelevantie en prijspositionering per SKU.</p>
      </div>

      {ladenSamenvatting ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : samenvatting && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm font-medium text-muted-foreground">Gem. PCIS-score</CardTitle>
              <Target className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{fmt(samenvatting.avg_pcis)}</div>
              <p className="text-xs text-muted-foreground mt-1">{samenvatting.total_skus_scored} SKU's gescoord</p>
            </CardContent>
          </Card>
          <Card className="border-red-200">
            <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm font-medium text-muted-foreground">Kritiek / Sterk</CardTitle>
              <AlertTriangle className="h-4 w-4 text-red-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">
                {samenvatting.critical_count + samenvatting.strong_count}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {samenvatting.critical_count} kritiek · {samenvatting.strong_count} sterk
              </p>
            </CardContent>
          </Card>
          <Card className="border-amber-200">
            <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm font-medium text-muted-foreground">Prijsdruk</CardTitle>
              <TrendingDown className="h-4 w-4 text-amber-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-amber-600">{samenvatting.downward_pressure_count}</div>
              <p className="text-xs text-muted-foreground mt-1">SKU's duurder dan markt</p>
            </CardContent>
          </Card>
          <Card className="border-emerald-200">
            <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm font-medium text-muted-foreground">Opwaartse ruimte</CardTitle>
              <TrendingUp className="h-4 w-4 text-emerald-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-emerald-600">{samenvatting.upward_opportunity_count}</div>
              <p className="text-xs text-muted-foreground mt-1">SKU's goedkoper dan markt</p>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">PCIS-verdeling</CardTitle>
            <CardDescription>SKU's per concurrentieklasse</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={(verdelingData || []).map((d: any) => ({ ...d, label: KLASSE_LABELS_NL[d.class] || d.class }))} barSize={40}>
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" radius={[4,4,0,0]}>
                  {(verdelingData || []).map((entry: any) => (
                    <Cell key={entry.class} fill={KLASSE_BAR_KLEUREN[entry.class] || "#94a3b8"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Prijsindex per categorie</CardTitle>
            <CardDescription>Eigen prijs ÷ gewogen mediaanreferentieprijs (1,00 = marktgemiddelde)</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={prijsIndexData || []} layout="vertical" barSize={14}>
                <XAxis type="number" domain={[0.88, 1.1]} tick={{ fontSize: 11 }} tickFormatter={v => v.toFixed(2)} />
                <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={110} />
                <Tooltip formatter={(v: number) => v.toFixed(3)} />
                <ReferenceLine x={1.0} stroke="#64748b" strokeDasharray="4 2" />
                <Bar dataKey="avg_price_index" radius={[0,4,4,0]}>
                  {(prijsIndexData || []).map((entry: any) => (
                    <Cell key={entry.category}
                      fill={entry.avg_price_index > 1.03 ? "#10b981" : entry.avg_price_index < 0.97 ? "#ef4444" : "#3b82f6"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <CardTitle className="text-base">SKU Concurrentiescores</CardTitle>
              <CardDescription>Klik op een rij voor het volledige concurrentiedetail</CardDescription>
            </div>
            <div className="flex gap-3">
              <Input placeholder="Zoek SKU of naam..." className="w-52" value={zoekterm} onChange={e => setZoekterm(e.target.value)} />
              <Select value={klasseFilter} onValueChange={setKlasseFilter}>
                <SelectTrigger className="w-44">
                  <SelectValue placeholder="Alle klassen" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle klassen</SelectItem>
                  <SelectItem value="Critical">Kritiek</SelectItem>
                  <SelectItem value="Strong">Sterk</SelectItem>
                  <SelectItem value="Influence">Invloed</SelectItem>
                  <SelectItem value="Monitor">Bewaken</SelectItem>
                  <SelectItem value="Ignore">Negeren</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="border-t">
            <div className="grid grid-cols-12 border-b bg-muted/50 px-4 py-2 text-xs font-medium text-muted-foreground">
              <div className="col-span-3">SKU / Product</div>
              <div className="col-span-2">Categorie</div>
              <div className="col-span-2 text-center">Klasse</div>
              <div className="col-span-1 text-right">PCIS</div>
              <div className="col-span-1 text-right">P.Index</div>
              <div className="col-span-1 text-right">Eigen prijs</div>
              <div className="col-span-1 text-right">Ref.prijs</div>
              <div className="col-span-1 text-right">Excl.</div>
            </div>
            {ladenSkus ? (
              <div className="p-8 text-center text-muted-foreground">Laden...</div>
            ) : items.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">Geen SKU's gevonden.</div>
            ) : (
              <div className="divide-y max-h-[480px] overflow-y-auto">
                {items.map((s: any) => (
                  <Link key={s.sku_id} href={`/concurrentie/${s.sku_id}`}>
                    <div className="grid grid-cols-12 items-center px-4 py-2.5 text-sm hover:bg-muted/50 cursor-pointer transition-colors">
                      <div className="col-span-3">
                        <div className="font-medium truncate pr-2">{s.product_name}</div>
                        <div className="text-xs text-muted-foreground">{s.sku_id}</div>
                      </div>
                      <div className="col-span-2 text-xs text-muted-foreground truncate pr-2">{s.category}</div>
                      <div className="col-span-2 flex justify-center">
                        <Badge variant="outline" className={`text-xs ${KLASSE_KLEUREN[s.competition_class] || ""}`}>
                          {KLASSE_LABELS_NL[s.competition_class] || s.competition_class}
                        </Badge>
                      </div>
                      <div className="col-span-1 text-right font-mono text-sm font-semibold">
                        {(s.pcis_score * 100).toFixed(0)}
                      </div>
                      <div className={`col-span-1 text-right font-mono text-xs font-medium ${
                        s.price_index > 1.03 ? "text-emerald-600" : s.price_index < 0.97 ? "text-red-600" : "text-foreground"
                      }`}>
                        {s.price_index?.toFixed(2) ?? "—"}
                      </div>
                      <div className="col-span-1 text-right text-xs tabular-nums">
                        €{s.current_price?.toFixed(2) ?? "—"}
                      </div>
                      <div className="col-span-1 text-right text-xs tabular-nums text-muted-foreground">
                        {s.reference_price ? `€${s.reference_price.toFixed(2)}` : "—"}
                      </div>
                      <div className="col-span-1 text-right">
                        {s.competitors_excluded > 0
                          ? <span className="text-xs text-amber-600 font-medium">{s.competitors_excluded}</span>
                          : <span className="text-xs text-muted-foreground">—</span>}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span className="font-medium">PCIS-drempelwaarden:</span>
        {[["Critical","85–100","Kritiek"],["Strong","70–85","Sterk"],["Influence","45–70","Invloed"],["Monitor","20–45","Bewaken"],["Ignore","0–20","Negeren"]]
          .map(([cls, range, label]) => (
            <span key={cls} className="flex items-center gap-1">
              <Badge variant="outline" className={`text-xs py-0 ${KLASSE_KLEUREN[cls]}`}>{label}</Badge>
              {range}
            </span>
          ))}
      </div>
    </div>
  );
}
