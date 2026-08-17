import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "wouter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, FlaskConical, ShieldAlert, Wallet, Sparkles } from "lucide-react";

function apiFetch(path: string) {
  const token = localStorage.getItem("auth_token");
  return fetch(path, { headers: { Authorization: `Bearer ${token}` } }).then(r => {
    if (!r.ok) throw new Error(`Fout ${r.status}`);
    return r.json();
  });
}

const TXN_LABELS: Record<string, string> = {
  earn: "Sparen", redeem: "Inwisselen", expire: "Vervallen",
  adjust: "Correctie", referral_bonus: "Referral-bonus", campaign_bonus: "Campagnebonus",
};

export default function LoyaltyMemberDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: m, isLoading, error } = useQuery({
    queryKey: ["loyalty-member", id],
    queryFn: () => apiFetch(`/api/loyalty/members/${id}`),
  });

  if (isLoading) return <div className="p-6"><Skeleton className="h-40 w-full" /></div>;
  if (error || !m) return <div className="p-6 text-sm text-red-600">Lid niet gevonden.</div>;

  const cv = m.customer_value;

  return (
    <div className="p-6 space-y-5">
      <div>
        <Link href="/loyalty" className="text-xs text-muted-foreground flex items-center gap-1 hover:underline">
          <ArrowLeft className="h-3.5 w-3.5" /> Terug naar loyalty-overzicht
        </Link>
        <div className="flex items-center gap-2 mt-1">
          <h1 className="text-2xl font-semibold font-mono">{m.pseudonymous_customer_id}</h1>
          {m.is_demo_data && <Badge variant="outline" className="border-amber-300 text-amber-700"><FlaskConical className="h-3 w-3 mr-1" />DEMO</Badge>}
          <Badge variant="outline">{m.tier_code}</Badge>
          <Badge variant="outline">{m.status}</Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Pseudoniem klant-ID — dit platform verwerkt geen PII. Lid sinds {m.joined_at || "onbekend"}
          {m.referred_by ? ` · geworven door ${m.referred_by}` : ""}
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <Card><CardContent className="pt-4">
          <div className="text-xs text-muted-foreground flex items-center gap-1"><Wallet className="h-3.5 w-3.5" /> Saldo</div>
          <div className="text-2xl font-semibold">{m.balance_points} pt</div>
          <div className="text-xs text-muted-foreground">+{m.lifetime_earned} verdiend · −{m.lifetime_redeemed} ingewisseld</div>
        </CardContent></Card>
        <Card><CardContent className="pt-4">
          <div className="text-xs text-muted-foreground">CLV (24m-schatting)</div>
          <div className="text-2xl font-semibold">€{cv ? cv.clv_estimate.toFixed(0) : "—"}</div>
          <div className="text-xs text-muted-foreground">{cv ? `confidence ${(cv.confidence * 100).toFixed(0)}%` : "nog geen run"}</div>
        </CardContent></Card>
        <Card><CardContent className="pt-4">
          <div className="text-xs text-muted-foreground">Churn-risico</div>
          <div className={`text-2xl font-semibold ${cv && cv.churn_risk >= 0.6 ? "text-red-600" : ""}`}>
            {cv ? `${(cv.churn_risk * 100).toFixed(0)}%` : "—"}
          </div>
          <div className="text-xs text-muted-foreground">{cv ? `retentiekans ${(cv.retention_probability * 100).toFixed(0)}%` : ""}</div>
        </CardContent></Card>
        <Card><CardContent className="pt-4">
          <div className="text-xs text-muted-foreground">Segment</div>
          <div className="text-2xl font-semibold">{cv?.value_segment || "—"}</div>
          <div className="text-xs text-muted-foreground">
            {cv ? `RFM: ${cv.recency_days ?? "∞"}d / ${cv.frequency_12m}x / €${cv.monetary_12m.toFixed(0)}` : ""}
          </div>
        </CardContent></Card>
      </div>

      {cv && (
        <Card className="border-blue-200 bg-blue-50/40">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Sparkles className="h-4 w-4" /> Next Best Action: {cv.next_best_action}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-1">
            <p>{cv.nba_reason}</p>
            <p className="text-xs text-muted-foreground">
              Verwachte incrementele waarde €{cv.nba_expected_value.toFixed(2)} vs. alternatief
              ({cv.nba_alternative}): €{cv.nba_alternative_cost.toFixed(2)} margekosten.
            </p>
            <p className="text-xs text-muted-foreground border-t pt-1 mt-2">{cv.explanation}</p>
          </CardContent>
        </Card>
      )}

      {m.fraud_signals?.length > 0 && (
        <Card className="border-red-200">
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2 text-red-700"><ShieldAlert className="h-4 w-4" /> Open fraudesignalen</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            {m.fraud_signals.map((f: any, i: number) => (
              <div key={i} className="border rounded-md p-2">
                <Badge variant="outline" className="border-red-300 text-red-700 mb-1">{f.type} · {f.severity}</Badge>
                <div className="text-muted-foreground">{f.explanation}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Ledger (laatste {m.transactions.length} transacties)</CardTitle></CardHeader>
          <CardContent>
            <table className="w-full text-xs">
              <thead><tr className="text-muted-foreground text-left border-b">
                <th className="py-1">Datum</th><th>Type</th><th className="text-right">Punten</th><th className="text-right">Orderbedrag</th><th>Omschrijving</th>
              </tr></thead>
              <tbody>
                {m.transactions.map((t: any) => (
                  <tr key={t.id} className="border-b last:border-0">
                    <td className="py-1">{t.date}</td>
                    <td>{TXN_LABELS[t.type] || t.type}</td>
                    <td className={`text-right font-mono ${t.points_delta > 0 ? "text-emerald-600" : "text-red-600"}`}>
                      {t.points_delta > 0 ? "+" : ""}{t.points_delta}
                    </td>
                    <td className="text-right">{t.order_value != null ? `€${t.order_value.toFixed(2)}` : "—"}</td>
                    <td className="text-muted-foreground">{t.description || t.order_reference || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {m.transactions.length === 0 && <div className="text-sm text-muted-foreground py-4 text-center">Geen transacties.</div>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Vouchers</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            {m.vouchers.map((v: any) => (
              <div key={v.id} className="border rounded-md p-2 flex items-center justify-between">
                <div>
                  <div className="font-mono">{v.code}</div>
                  <div className="text-muted-foreground">€{v.value.toFixed(2)} · verloopt {v.expires_at || "—"}</div>
                </div>
                <Badge variant="outline">{v.status}</Badge>
              </div>
            ))}
            {m.vouchers.length === 0 && <div className="text-muted-foreground py-4 text-center">Geen vouchers.</div>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
