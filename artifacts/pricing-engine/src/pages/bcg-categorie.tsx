import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, Cell } from "recharts";
import { getAuthToken } from "@/lib/auth";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const HYBRID_KLEUR: Record<string, string> = {
  "PRICING_POWER_STAR":         "#22c55e",
  "DEFENSIVE_CASH_COW":         "#f59e0b",
  "PRIVATE_LABEL_STAR":         "#8b5cf6",
  "EXPERIMENTAL_QUESTION_MARK": "#3b82f6",
  "LOW_PRIORITY_DOG":           "#94a3b8",
};

const PRIORITEIT_BADGE: Record<string, string> = {
  hoog:      "bg-red-100 text-red-800 border-red-200",
  gemiddeld: "bg-amber-100 text-amber-800 border-amber-200",
  laag:      "bg-slate-100 text-slate-600 border-slate-200",
};

export default function BcgCategorie() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const { toast } = useToast();
  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  useEffect(() => {
    setLoading(true);
    (async () => {
      try {
        const r = await fetch(`${API}/api/bcg/categorie-matrix${filterQs ? `?${filterQs}` : ""}`, {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
        });
        if (!r.ok) throw new Error();
        const d = await r.json();
        setData(d);
        if (d.items?.length) setSelected(d.items[0].categorie);
        else setSelected(null);
      } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
      setLoading(false);
    })();
  }, [filterQs]);

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-56" />
      <div className="grid grid-cols-3 gap-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-40" />)}</div>
    </div>
  );

  const items: any[] = data?.items || [];
  const selectedItem = items.find(i => i.categorie === selected);

  const radarData = selectedItem ? [
    { subject: "IBSS", score: Math.round(selectedItem.ibss * 100) },
    { subject: "GPS", score: Math.round(selectedItem.gps * 100) },
    { subject: "CSS", score: Math.round(selectedItem.css_external * 100) },
    { subject: "MOS", score: Math.round(selectedItem.mos * 100) },
    { subject: "Pricing Power", score: Math.round(selectedItem.pricing_power * 100) },
  ] : [];

  const barData = items.map(i => ({
    naam: i.categorie.length > 12 ? i.categorie.substring(0, 12) + "…" : i.categorie,
    volledigeNaam: i.categorie,
    pps: Math.round(i.pricing_power * 100),
    kleur: HYBRID_KLEUR[i.hybrid_bcg_class] || "#94a3b8",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Categorie BCG Analyse</h1>
        <p className="text-muted-foreground text-sm mt-1">BCG-classificatie op categorieniveau — aggregatie van alle SKU's</p>
      </div>

      <GlobalFilterBar />

      {/* Categorie kaarten */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map((cat: any) => (
          <Card
            key={cat.categorie}
            className={`cursor-pointer transition-all hover:shadow-md ${selected === cat.categorie ? "ring-2 ring-primary" : ""}`}
            onClick={() => setSelected(cat.categorie)}
          >
            <CardContent className="pt-4 pb-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="font-semibold text-sm">{cat.categorie}</p>
                  <span className={`text-xs px-2 py-0.5 rounded-full border font-medium mt-1 inline-block ${PRIORITEIT_BADGE[cat.prioriteit]}`}>
                    {cat.prioriteit}
                  </span>
                </div>
                <div
                  className="px-2 py-1 rounded text-xs font-semibold text-white"
                  style={{ background: HYBRID_KLEUR[cat.hybrid_bcg_class] || "#94a3b8" }}
                >
                  {cat.hybrid_bcg_nl}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  { label: "IBSS", val: cat.ibss },
                  { label: "GPS", val: cat.gps },
                  { label: "Power", val: cat.pricing_power },
                ].map(s => (
                  <div key={s.label} className="bg-muted/40 rounded p-2">
                    <p className="text-base font-bold">{Math.round(s.val * 100)}%</p>
                    <p className="text-xs text-muted-foreground">{s.label}</p>
                  </div>
                ))}
              </div>

              <div className="mt-3 text-xs text-muted-foreground">
                <span className="font-medium">Strategie:</span> {cat.strategie}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Detail geselecteerde categorie */}
      {selectedItem && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Score Radar — {selectedItem.categorie}</CardTitle>
              <CardDescription>Vijf dimensies van de BCG-analyse (schaal 0–100%)</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="subject" fontSize={12} />
                  <Radar
                    name={selectedItem.categorie}
                    dataKey="score"
                    stroke={HYBRID_KLEUR[selectedItem.hybrid_bcg_class] || "#6366f1"}
                    fill={HYBRID_KLEUR[selectedItem.hybrid_bcg_class] || "#6366f1"}
                    fillOpacity={0.25}
                  />
                  <Tooltip formatter={(v: number) => [`${v}%`]} />
                </RadarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Pricing Power per Categorie</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={barData} layout="vertical">
                  <XAxis type="number" domain={[0, 100]} fontSize={10} tickFormatter={v => `${v}%`} />
                  <YAxis type="category" dataKey="naam" width={90} fontSize={10} />
                  <Tooltip formatter={(v: number) => [`${v}%`, "Pricing Power"]} labelFormatter={(_: any, payload: any) => payload?.[0]?.payload?.volledigeNaam || ""} />
                  <Bar dataKey="pps" radius={[0, 4, 4, 0]}>
                    {barData.map((e, i) => (
                      <Cell key={i} fill={e.naam === (selectedItem?.categorie?.length > 12 ? selectedItem.categorie.substring(0, 12) + "…" : selectedItem?.categorie) ? "#1e40af" : e.kleur} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* BCG samenvatting */}
          <Card className="md:col-span-2">
            <CardHeader><CardTitle className="text-base">BCG Classificatie Detail — {selectedItem.categorie}</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-6">
                {[
                  { label: "Interne BCG", klasse: selectedItem.internal_bcg_class, klasse_nl: selectedItem.internal_bcg_nl },
                  { label: "Externe BCG", klasse: selectedItem.external_bcg_class, klasse_nl: selectedItem.external_bcg_nl },
                  { label: "Hybride Pricing BCG", klasse: selectedItem.hybrid_bcg_class, klasse_nl: selectedItem.hybrid_bcg_nl },
                ].map(({ label, klasse, klasse_nl }) => (
                  <div key={label} className="text-center">
                    <p className="text-xs text-muted-foreground mb-2">{label}</p>
                    <div
                      className="rounded-xl py-3 px-4 text-white font-bold text-sm"
                      style={{ background: HYBRID_KLEUR[klasse] || "#94a3b8" }}
                    >
                      {klasse_nl}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 p-3 bg-muted/30 rounded-lg text-sm">
                <span className="font-semibold">Aanbevolen strategie: </span>{selectedItem.strategie}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
