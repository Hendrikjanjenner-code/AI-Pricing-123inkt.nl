import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, ZAxis,
} from "recharts";
import { getAuthToken } from "@/lib/auth";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

const API = import.meta.env.BASE_URL.replace(/\/$/, "");

const MATRIX_TYPE_LABELS: Record<string, { x: string; y: string; title: string }> = {
  internal: { x: "Interne Bedrijfskracht (IBSS)", y: "Groeipotentieel (GPS)", title: "Interne BCG Matrix" },
  external: { x: "Concurrentiesterkte (CSS)", y: "Marktkans (MOS)", title: "Externe BCG Matrix" },
  hybrid:   { x: "Pricing Power", y: "Concurrentiedruk", title: "Hybride Pricing Matrix" },
};

const KWADRANT_LABELS: Record<string, { intern: string; extern: string; hybrid: string }> = {
  "hoog-hoog": { intern: "Ster ⭐", extern: "Externe Ster ⭐", hybrid: "Pricing Power Ster ⭐" },
  "hoog-laag": { intern: "Cash Cow 💰", extern: "Externe Cash Cow 💰", hybrid: "Defensieve Cash Cow 💰" },
  "laag-hoog": { intern: "Vraagteken ❓", extern: "Extern Vraagteken ❓", hybrid: "Experimenteel ❓" },
  "laag-laag": { intern: "Dog 🐕", extern: "Externe Dog 🐕", hybrid: "Lage Prioriteit Dog 🐕" },
};

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-popover border rounded-lg p-3 shadow-lg text-xs max-w-[220px]">
      <p className="font-semibold mb-1 truncate">{d.naam}</p>
      <p className="text-muted-foreground">{d.klasse_nl}</p>
      <p className="mt-1">X: <strong>{d.x}</strong> · Y: <strong>{d.y}</strong></p>
      <p className="text-muted-foreground mt-1">{d.strategie}</p>
    </div>
  );
};

export default function BcgSkuMatrix() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [matrixType, setMatrixType] = useState("internal");
  const [zoek, setZoek] = useState("");
  const [selectedSku, setSelectedSku] = useState<string | null>(null);
  const { toast } = useToast();
  const globalFilters = useGlobalFilters();
  const filterQs = apiFilterParams(globalFilters);

  useEffect(() => { laden(matrixType); }, [matrixType, filterQs]);

  async function laden(type: string) {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/bcg/sku-matrix?type=${type}${filterQs ? `&${filterQs}` : ""}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      if (!r.ok) throw new Error();
      setData(await r.json());
    } catch { toast({ title: "Laden mislukt", variant: "destructive" }); }
    setLoading(false);
  }

  const items: any[] = data?.items || [];
  const gefilterdeItems = zoek
    ? items.filter(i => i.naam.toLowerCase().includes(zoek.toLowerCase()) || i.sku_id.toLowerCase().includes(zoek.toLowerCase()))
    : items;

  const meta = MATRIX_TYPE_LABELS[matrixType];

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-80 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">SKU BCG Analyse</h1>
          <p className="text-muted-foreground text-sm mt-1">Scatter-plot van alle SKU's in de BCG-matrix</p>
        </div>
        <Select value={matrixType} onValueChange={setMatrixType}>
          <SelectTrigger className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="internal">Interne BCG Matrix</SelectItem>
            <SelectItem value="external">Externe BCG Matrix</SelectItem>
            <SelectItem value="hybrid">Hybride Pricing Matrix</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <GlobalFilterBar />

      {/* Scatter plot */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{meta.title}</CardTitle>
          <CardDescription>
            X-as: {meta.x} · Y-as: {meta.y} · Drempelwaarde: 0.60
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Kwadrant labels */}
          <div className="grid grid-cols-2 gap-2 mb-4 text-xs">
            {[
              { pos: "hoog-hoog", kleur: "bg-green-50 border-green-200 text-green-800", label: matrixType === "internal" ? "Ster" : matrixType === "external" ? "Externe Ster" : "Pricing Power Ster" },
              { pos: "laag-hoog", kleur: "bg-blue-50 border-blue-200 text-blue-800", label: "Vraagteken" },
              { pos: "hoog-laag", kleur: "bg-amber-50 border-amber-200 text-amber-800", label: "Cash Cow" },
              { pos: "laag-laag", kleur: "bg-slate-50 border-slate-200 text-slate-600", label: "Dog" },
            ].map(q => (
              <div key={q.pos} className={`border rounded-md px-3 py-2 ${q.kleur}`}>
                <span className="font-semibold">{q.label}</span>
              </div>
            ))}
          </div>

          <ResponsiveContainer width="100%" height={380}>
            <ScatterChart margin={{ top: 20, right: 20, bottom: 30, left: 20 }}>
              <XAxis
                type="number" dataKey="x" domain={[0, 1]} name={meta.x}
                label={{ value: meta.x, position: "insideBottom", offset: -10, fontSize: 11 }}
                fontSize={10} tickFormatter={v => `${Math.round(v * 100)}%`}
              />
              <YAxis
                type="number" dataKey="y" domain={[0, 1]} name={meta.y}
                label={{ value: meta.y, angle: -90, position: "insideLeft", fontSize: 11 }}
                fontSize={10} tickFormatter={v => `${Math.round(v * 100)}%`}
              />
              <ZAxis type="number" dataKey="bubble" range={[40, 400]} />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine x={0.60} stroke="#94a3b8" strokeDasharray="4 4" />
              <ReferenceLine y={0.60} stroke="#94a3b8" strokeDasharray="4 4" />
              <Scatter
                data={gefilterdeItems}
                onClick={(d: any) => setSelectedSku(d.sku_id)}
              >
                {gefilterdeItems.map((e: any, i: number) => (
                  <Cell
                    key={i}
                    fill={e.kleur}
                    opacity={selectedSku && selectedSku !== e.sku_id ? 0.35 : 1}
                    stroke={selectedSku === e.sku_id ? "#1e40af" : "transparent"}
                    strokeWidth={2}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Tabel */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">SKU Overzicht ({items.length} SKU's)</CardTitle>
            <Input
              placeholder="Zoek SKU of naam..."
              value={zoek}
              onChange={e => setZoek(e.target.value)}
              className="w-56 h-8 text-sm"
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {["SKU", "Naam", "Categorie", "Classificatie", "X-score", "Y-score", "Pricing Power", "Strategie", ""].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-xs font-medium text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gefilterdeItems.map((item: any) => (
                  <tr
                    key={item.sku_id}
                    className={`border-b hover:bg-muted/30 cursor-pointer transition-colors ${selectedSku === item.sku_id ? "bg-blue-50" : ""}`}
                    onClick={() => setSelectedSku(selectedSku === item.sku_id ? null : item.sku_id)}
                  >
                    <td className="py-2 px-3 font-mono text-xs">{item.sku_id}</td>
                    <td className="py-2 px-3 max-w-[180px] truncate">{item.naam}</td>
                    <td className="py-2 px-3 text-muted-foreground text-xs">{item.categorie}</td>
                    <td className="py-2 px-3">
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium text-white" style={{ background: item.kleur }}>
                        {item.klasse_nl}
                      </span>
                    </td>
                    <td className="py-2 px-3 font-mono text-xs">{Math.round(item.x * 100)}%</td>
                    <td className="py-2 px-3 font-mono text-xs">{Math.round(item.y * 100)}%</td>
                    <td className="py-2 px-3 font-mono text-xs">{Math.round(item.pricing_power * 100)}%</td>
                    <td className="py-2 px-3 text-xs text-muted-foreground max-w-[160px] truncate">{item.strategie}</td>
                    <td className="py-2 px-3">
                      <Link href={`/bcg/sku/${item.sku_id}`}>
                        <Button variant="ghost" size="sm" className="h-6 text-xs px-2">Detail</Button>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
