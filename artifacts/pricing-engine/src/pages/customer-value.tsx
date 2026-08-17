import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TrendingUp, Users, HeartPulse, ChevronRight } from "lucide-react";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

const SEGMENTEN = [
  { value: "all", label: "Alle segmenten" },
  { value: "high_value", label: "High value" },
  { value: "mid_value", label: "Mid value" },
  { value: "low_value", label: "Low value" },
  { value: "at_risk", label: "At risk" },
  { value: "lost", label: "Lost" },
];
const SEGMENT_STYLE: Record<string, string> = {
  high_value: "bg-emerald-50 text-emerald-700 border-emerald-200",
  mid_value: "bg-blue-50 text-blue-700 border-blue-200",
  low_value: "bg-slate-50 text-slate-600 border-slate-200",
  at_risk: "bg-amber-50 text-amber-700 border-amber-200",
  lost: "bg-red-50 text-red-700 border-red-200",
};

export default function CustomerValue() {
  const [segment, setSegment] = useState("all");
  const { data, isLoading } = useQuery({
    queryKey: ["customer-value", segment],
    queryFn: () => apiFetch(`/api/loyalty/customer-value?limit=200${segment !== "all" ? `&segment=${segment}` : ""}`),
  });

  const items = data?.items || [];
  const summary = data?.summary || {};

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Customer Value Intelligence</h1>
        <p className="text-sm text-muted-foreground">
          CLV, churn-risico, retentie en Next Best Action per pseudoniem lid (geen PII).
          {data?.run_date ? ` Laatste run: ${data.run_date}.` : " Nog geen intelligence-run uitgevoerd."}
        </p>
      </div>

      {isLoading ? <Skeleton className="h-24 w-full" /> : (
        <div className="grid gap-3 md:grid-cols-4">
          <Card><CardContent className="pt-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1"><Users className="h-3.5 w-3.5" /> Leden gescoord</div>
            <div className="text-2xl font-semibold">{summary.members_scored ?? 0}</div>
          </CardContent></Card>
          <Card><CardContent className="pt-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1"><TrendingUp className="h-3.5 w-3.5" /> Totale CLV-schatting</div>
            <div className="text-2xl font-semibold">€{(summary.total_clv_estimate ?? 0).toLocaleString("nl-NL", { maximumFractionDigits: 0 })}</div>
          </CardContent></Card>
          <Card><CardContent className="pt-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1"><HeartPulse className="h-3.5 w-3.5" /> Gem. churn-risico</div>
            <div className="text-2xl font-semibold">{summary.avg_churn_risk != null ? `${(summary.avg_churn_risk * 100).toFixed(0)}%` : "—"}</div>
          </CardContent></Card>
          <Card><CardContent className="pt-4">
            <div className="text-xs text-muted-foreground">Gem. retentiekans</div>
            <div className="text-2xl font-semibold">{summary.avg_retention != null ? `${(summary.avg_retention * 100).toFixed(0)}%` : "—"}</div>
          </CardContent></Card>
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm">Leden op klantwaarde</CardTitle>
              <CardDescription className="text-xs">Gesorteerd op CLV; NBA vergelijkt gericht loyalty-instrument met generieke prijsverlaging.</CardDescription>
            </div>
            <Select value={segment} onValueChange={setSegment}>
              <SelectTrigger className="w-44 h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>{SEGMENTEN.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <table className="w-full text-xs">
            <thead><tr className="text-muted-foreground text-left border-b">
              <th className="py-1">Klant-ID</th><th>Segment</th>
              <th className="text-right">CLV</th><th className="text-right">Churn</th>
              <th className="text-right">12m besteding</th><th>Next Best Action</th>
              <th className="text-right">NBA-waarde vs. alternatief</th><th></th>
            </tr></thead>
            <tbody>
              {items.map((s: any) => (
                <tr key={s.member_id} className="border-b last:border-0 hover:bg-muted/40">
                  <td className="py-1.5">
                    <span className="font-mono">{s.pseudonymous_customer_id}</span>
                    {s.is_demo_data && <Badge variant="outline" className="ml-1 text-[9px] border-amber-300 text-amber-700">DEMO</Badge>}
                  </td>
                  <td><Badge variant="outline" className={`text-[10px] ${SEGMENT_STYLE[s.value_segment] || ""}`}>{s.value_segment}</Badge></td>
                  <td className="text-right font-medium">€{s.clv_estimate.toFixed(0)}</td>
                  <td className={`text-right ${s.churn_risk >= 0.6 ? "text-red-600 font-medium" : ""}`}>{(s.churn_risk * 100).toFixed(0)}%</td>
                  <td className="text-right">€{s.monetary_12m.toFixed(0)}</td>
                  <td>{s.next_best_action}</td>
                  <td className="text-right text-muted-foreground">€{s.nba_expected_value.toFixed(0)} vs. €{s.nba_alternative_cost.toFixed(0)}</td>
                  <td>
                    <Link href={`/loyalty/leden/${s.member_id}`}><ChevronRight className="h-3.5 w-3.5 text-muted-foreground cursor-pointer" /></Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 && !isLoading && (
            <div className="text-sm text-muted-foreground py-6 text-center">
              Geen scores — draai eerst een intelligence-run vanaf het loyalty-dashboard.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
