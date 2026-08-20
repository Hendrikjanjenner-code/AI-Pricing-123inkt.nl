import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, CartesianGrid, ReferenceLine } from "recharts";
import { useShopId } from "@/hooks/use-shop-id";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { apiFilterParams } from "@/lib/global-filters";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => {
    if (!r.ok) throw new Error(`API-fout (${r.status})`);
    return r.json();
  });
}

const SIZE_SCALE: Record<string, number> = { micro: 40, klein: 80, midden: 140, groot: 220, enterprise: 320 };
const DNA_COLORS: Record<string, string> = {
  prijsagressor: "#dc2626", assortimentsbreedte: "#2563eb", servicekampioen: "#059669",
  nichespecialist: "#7c3aed", marketplace: "#d97706", premiummerk: "#be185d",
};
const FALLBACK_COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#64748b"];

export default function CompetitionLandscape() {
  const shopId = useShopId();
  const filters = useGlobalFilters();
  const fp = apiFilterParams(filters);
  const [axes, setAxes] = useState<"strength" | "threat">("strength");

  const { data, isLoading } = useQuery({
    queryKey: ["competition-landscape", shopId, fp],
    queryFn: () => {
      let url = `/api/competition/landscape${shopId !== undefined ? `?shop_id=${shopId}` : ""}`;
      if (fp !== "") url += url.includes("?") ? `&${fp}` : `?${fp}`;
      return apiFetch(url);
    },
  });

  const items: any[] = data?.items || [];
  const yKey = axes === "strength" ? "business_strength_score" : "future_threat_score";
  const yLabel = axes === "strength" ? "Business Strength" : "Future Threat";
  const plottable = items.filter(it => it.competition_relevance_score != null && it[yKey] != null);
  const unknown = items.filter(it => it.competition_relevance_score == null || it[yKey] == null);

  // Kleur per primaire DNA-rol
  const roleColor = (() => {
    const seen: Record<string, string> = {};
    let i = 0;
    return (role: string | undefined) => {
      if (!role) return "#94a3b8";
      const key = role.toLowerCase();
      if (DNA_COLORS[key]) return DNA_COLORS[key];
      if (!seen[key]) seen[key] = FALLBACK_COLORS[i++ % FALLBACK_COLORS.length];
      return seen[key];
    };
  })();

  const points = plottable.map(it => ({
    ...it,
    x: Math.round((it.competition_relevance_score || 0) * 100),
    y: Math.round(it[yKey]),
    z: SIZE_SCALE[(it.company_size_class || "").toLowerCase()] || 100,
    role: it.market_roles?.[0],
  }));
  const byRole: Record<string, any[]> = {};
  points.forEach(p => { byRole[p.role || "onbekend"] = byRole[p.role || "onbekend"] || []; byRole[p.role || "onbekend"].push(p); });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Concurrent Landscape</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Managementview: bubbelgrootte = company scale, kleur = Competition DNA-rol.
            {data?.run_date ? ` Rankings van ${data.run_date}.` : ""}
          </p>
        </div>
        <Select value={axes} onValueChange={v => setAxes(v as any)}>
          <SelectTrigger className="w-72" data-testid="select-landscape-axes"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="strength">Competition Relevance × Business Strength</SelectItem>
            <SelectItem value="threat">Current Relevance × Future Threat</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <GlobalFilterBar />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Competition Relevance × {yLabel}</CardTitle>
          <CardDescription>Concurrenten zonder waarde op een as staan hieronder als "Onbekend" — ze worden nooit als 0 geplot.</CardDescription>
        </CardHeader>
        <CardContent className="h-[480px]">
          {isLoading ? <Skeleton className="h-full w-full" /> : points.length === 0 ? (
            <p className="text-sm text-muted-foreground">Geen plotbare data — draai eerst de rankings- en scores-engines.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 16, right: 24, bottom: 16, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" dataKey="x" name="Competition Relevance" domain={[0, 100]} fontSize={11}
                       label={{ value: "Competition Relevance", position: "insideBottom", offset: -8, fontSize: 11 }} />
                <YAxis type="number" dataKey="y" name={yLabel} domain={[0, 100]} fontSize={11}
                       label={{ value: yLabel, angle: -90, position: "insideLeft", fontSize: 11 }} />
                <ZAxis type="number" dataKey="z" range={[60, 400]} />
                <ReferenceLine x={50} stroke="#94a3b8" strokeDasharray="4 4" />
                <ReferenceLine y={50} stroke="#94a3b8" strokeDasharray="4 4" />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ payload }) => {
                  const p: any = payload?.[0]?.payload;
                  if (!p) return null;
                  return (
                    <div className="rounded-md border bg-background p-2.5 text-xs shadow-md">
                      <div className="font-semibold">{p.competitor_name}</div>
                      <div>Relevance: {p.x} · {yLabel}: {p.y}</div>
                      <div>Scale: {p.company_size_class || "Onbekend"} · DNA: {p.market_roles?.join(", ") || "Onbekend"}</div>
                      {p.data_completeness_pct != null && <div>Data completeness: {Math.round(p.data_completeness_pct)}%</div>}
                    </div>
                  );
                }} />
                {Object.entries(byRole).map(([role, pts]) => (
                  <Scatter key={role} name={role} data={pts} fill={roleColor(role === "onbekend" ? undefined : role)} fillOpacity={0.75} />
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        {Object.keys(byRole).map(role => (
          <Badge key={role} variant="outline" className="text-xs">
            <span className="h-2.5 w-2.5 rounded-full mr-1.5" style={{ background: roleColor(role === "onbekend" ? undefined : role) }} />
            {role}
          </Badge>
        ))}
      </div>

      {unknown.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Niet geplot — Onbekend op minstens één as ({unknown.length})</CardTitle>
            <CardDescription className="text-xs">Ontbrekende scores worden expliciet als Onbekend getoond, nooit als 0.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2" data-testid="landscape-unknown">
            {unknown.map(it => (
              <Link key={it.competitor_name} href={`/competition/competitors/${encodeURIComponent(it.competitor_name)}`}>
                <Badge variant="secondary" className="text-xs cursor-pointer hover:bg-muted">{it.competitor_name}</Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
