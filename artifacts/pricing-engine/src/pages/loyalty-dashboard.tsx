import { useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  Users, Coins, ShieldAlert, Wallet, PlayCircle, Upload, Search,
  FlaskConical, Ticket, ChevronRight,
} from "lucide-react";

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${localStorage.getItem("auth_token")}` };
}
function apiFetch(path: string) {
  return fetch(path, { headers: authHeaders() }).then(async r => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail || `Fout ${r.status}`);
    return r.json();
  });
}

const TIER_LABELS: Record<string, string> = { bronze: "Brons", silver: "Zilver", gold: "Goud" };
const SEGMENT_STYLE: Record<string, string> = {
  high_value: "bg-emerald-50 text-emerald-700 border-emerald-200",
  mid_value: "bg-blue-50 text-blue-700 border-blue-200",
  low_value: "bg-slate-50 text-slate-600 border-slate-200",
  at_risk: "bg-amber-50 text-amber-700 border-amber-200",
  lost: "bg-red-50 text-red-700 border-red-200",
};

function UploadCard({ titel, omschrijving, uploadType, endpoint }: {
  titel: string; omschrijving: string; uploadType: string; endpoint: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [rapport, setRapport] = useState<any>(null);
  const [bestand, setBestand] = useState<File | null>(null);
  const [bezig, setBezig] = useState(false);
  const { toast } = useToast();
  const qc = useQueryClient();

  const valideer = async (f: File) => {
    setBezig(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch(`/api/uploads/validate?upload_type=${uploadType}`, {
        method: "POST", headers: authHeaders(), body: fd,
      });
      const j = await r.json();
      setRapport(j);
      setBestand(f);
    } catch (e: any) {
      toast({ title: "Validatie mislukt", description: String(e), variant: "destructive" });
    } finally { setBezig(false); }
  };

  const importeer = async () => {
    if (!bestand) return;
    setBezig(true);
    try {
      const fd = new FormData();
      fd.append("file", bestand);
      const r = await fetch(endpoint, { method: "POST", headers: authHeaders(), body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j?.detail || "Import mislukt");
      toast({
        title: `${titel}: ${j.rows_processed} rijen geïmporteerd`,
        description: j.rows_failed ? `${j.rows_failed} rijen overgeslagen — zie importgeschiedenis` : undefined,
      });
      setRapport(null); setBestand(null);
      qc.invalidateQueries({ queryKey: ["loyalty-overview"] });
      qc.invalidateQueries({ queryKey: ["loyalty-members"] });
    } catch (e: any) {
      toast({ title: "Import mislukt", description: String(e.message || e), variant: "destructive" });
    } finally { setBezig(false); }
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2"><Upload className="h-4 w-4" />{titel}</CardTitle>
        <CardDescription className="text-xs">{omschrijving}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) valideer(f); e.target.value = ""; }} />
        <Button size="sm" variant="outline" disabled={bezig} onClick={() => inputRef.current?.click()}>
          Kies bestand (CSV/XLSX)
        </Button>
        {rapport && (
          <div className="text-xs space-y-1 border rounded-md p-2 bg-muted/40">
            <div>{rapport.rows_valid}/{rapport.rows_total} rijen geldig
              {rapport.missing_fields?.length > 0 && (
                <span className="text-red-600"> — ontbrekend: {rapport.missing_fields.join(", ")}</span>
              )}
            </div>
            {rapport.kan_importeren
              ? <Button size="sm" disabled={bezig} onClick={importeer}>Importeer {bestand?.name}</Button>
              : <div className="text-red-600">Import niet mogelijk — corrigeer het bestand.</div>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function LoyaltyDashboard() {
  const [zoek, setZoek] = useState("");
  const { toast } = useToast();
  const qc = useQueryClient();

  const { data: overview, isLoading } = useQuery({
    queryKey: ["loyalty-overview"], queryFn: () => apiFetch("/api/loyalty/overview"),
  });
  const { data: leden } = useQuery({
    queryKey: ["loyalty-members", zoek],
    queryFn: () => apiFetch(`/api/loyalty/members?limit=50${zoek ? `&search=${encodeURIComponent(zoek)}` : ""}`),
  });
  const { data: liability } = useQuery({
    queryKey: ["loyalty-liability"], queryFn: () => apiFetch("/api/loyalty/liability"),
  });
  const { data: fraud } = useQuery({
    queryKey: ["loyalty-fraud"], queryFn: () => apiFetch("/api/loyalty/fraud"),
  });
  const { data: campagnes } = useQuery({
    queryKey: ["loyalty-campaigns"], queryFn: () => apiFetch("/api/loyalty/campaigns"),
  });

  const runEngine = useMutation({
    mutationFn: () => fetch("/api/loyalty/run", { method: "POST", headers: authHeaders() })
      .then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j?.detail); return j; }),
    onSuccess: (j) => {
      toast({ title: "Intelligence-run voltooid", description: `${j.members_scored} leden gescoord, ${j.intelligence_signals_published} signalen gepubliceerd.` });
      qc.invalidateQueries();
    },
    onError: (e: any) => toast({ title: "Run mislukt", description: String(e.message || e), variant: "destructive" }),
  });

  const seedDemo = useMutation({
    mutationFn: () => fetch("/api/loyalty/seed-demo", { method: "POST", headers: authHeaders() })
      .then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j?.detail); return j; }),
    onSuccess: (j) => { toast({ title: "Demodata aangemaakt", description: `${j.members_created} demo-leden (expliciet gemarkeerd).` }); qc.invalidateQueries(); },
    onError: (e: any) => toast({ title: "Demodata mislukt", description: String(e.message || e), variant: "destructive" }),
  });

  const geenData = !isLoading && (overview?.members_total ?? 0) === 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Loyalty & Customer Value</h1>
          <p className="text-sm text-muted-foreground">
            Membership, wallets, campagnes, financial liability en fraudesignalen — op pseudonieme klant-ID's (geen PII).
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => runEngine.mutate()} disabled={runEngine.isPending || geenData}>
            <PlayCircle className="h-4 w-4 mr-1" /> Intelligence-run
          </Button>
          {geenData && (
            <Button size="sm" variant="outline" onClick={() => seedDemo.mutate()} disabled={seedDemo.isPending}>
              <FlaskConical className="h-4 w-4 mr-1" /> Demodata laden
            </Button>
          )}
        </div>
      </div>

      {overview?.contains_demo_data && (
        <div className="text-xs rounded-md border border-amber-300 bg-amber-50 text-amber-800 px-3 py-2">
          <FlaskConical className="h-3.5 w-3.5 inline mr-1" />
          Deze module bevat <b>{overview.members_demo}</b> expliciet gemarkeerde demo-leden — er is nog geen live loyalty-databron aangesloten.
        </div>
      )}

      {isLoading ? <Skeleton className="h-24 w-full" /> : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <Card><CardContent className="pt-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1"><Users className="h-3.5 w-3.5" /> Leden</div>
            <div className="text-2xl font-semibold">{overview?.members_total ?? 0}</div>
            <div className="text-xs text-muted-foreground">
              {Object.entries(overview?.members_by_tier || {}).map(([t, n]) => `${TIER_LABELS[t] || t}: ${n}`).join(" · ") || "—"}
            </div>
          </CardContent></Card>
          <Card><CardContent className="pt-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1"><Coins className="h-3.5 w-3.5" /> Punten (30d)</div>
            <div className="text-2xl font-semibold">+{overview?.points_earned_30d ?? 0}</div>
            <div className="text-xs text-muted-foreground">−{overview?.points_redeemed_30d ?? 0} ingewisseld</div>
          </CardContent></Card>
          <Card><CardContent className="pt-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1"><Wallet className="h-3.5 w-3.5" /> Financial liability</div>
            <div className="text-2xl font-semibold">€{(overview?.liability?.total_liability_eur ?? 0).toFixed(2)}</div>
            <div className="text-xs text-muted-foreground">
              {overview?.liability?.outstanding_points ?? 0} punten + {overview?.liability?.open_vouchers ?? 0} vouchers
            </div>
          </CardContent></Card>
          <Card><CardContent className="pt-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1"><ShieldAlert className="h-3.5 w-3.5" /> Fraudesignalen</div>
            <div className={`text-2xl font-semibold ${(overview?.open_fraud_signals ?? 0) > 0 ? "text-red-600" : ""}`}>
              {overview?.open_fraud_signals ?? 0}
            </div>
            <div className="text-xs text-muted-foreground">
              {overview?.ledger_mismatches ? `${overview.ledger_mismatches} ledger-mismatches!` : "Ledger-integriteit OK"}
            </div>
          </CardContent></Card>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-sm">Leden</CardTitle>
              <div className="relative w-56">
                <Search className="h-3.5 w-3.5 absolute left-2 top-2.5 text-muted-foreground" />
                <Input className="h-8 pl-7 text-xs" placeholder="Zoek op klant-ID…" value={zoek} onChange={e => setZoek(e.target.value)} />
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="divide-y">
              {(leden?.items || []).slice(0, 15).map((m: any) => (
                <Link key={m.id} href={`/loyalty/leden/${m.id}`}>
                  <div className="flex items-center justify-between py-2 cursor-pointer hover:bg-muted/50 px-1 rounded">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-mono">{m.pseudonymous_customer_id}</span>
                      {m.is_demo_data && <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-700">DEMO</Badge>}
                      <Badge variant="outline" className="text-[10px]">{TIER_LABELS[m.tier_code] || m.tier_code}</Badge>
                      {m.value_segment && (
                        <Badge variant="outline" className={`text-[10px] ${SEGMENT_STYLE[m.value_segment] || ""}`}>{m.value_segment}</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>{m.balance_points} pt</span>
                      {m.clv_estimate != null && <span>CLV €{m.clv_estimate.toFixed(0)}</span>}
                      <ChevronRight className="h-3.5 w-3.5" />
                    </div>
                  </div>
                </Link>
              ))}
              {(leden?.items || []).length === 0 && (
                <div className="text-sm text-muted-foreground py-6 text-center">
                  Nog geen leden — importeer loyalty-data of laad demodata.
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <UploadCard titel="Import: leden" uploadType="loyalty-members" endpoint="/api/uploads/loyalty-members"
            omschrijving="Kolommen: pseudonymous_customer_id, joined_at, tier_code, referral_code, referred_by" />
          <UploadCard titel="Import: transacties" uploadType="loyalty-transactions" endpoint="/api/uploads/loyalty-transactions"
            omschrijving="Kolommen: pseudonymous_customer_id, date, txn_type (earn/redeem/expire/adjust), points_delta, order_value, external_ref" />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Wallet className="h-4 w-4" /> Liability per tier</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            {(liability?.per_tier || []).map((t: any) => (
              <div key={t.tier} className="flex justify-between">
                <span>{t.name}</span>
                <span className="text-muted-foreground">{t.points} pt · €{t.liability_eur.toFixed(2)}</span>
              </div>
            ))}
            <div className="flex justify-between border-t pt-1 font-medium">
              <span>Totaal (incl. vouchers)</span><span>€{(liability?.total_liability_eur ?? 0).toFixed(2)}</span>
            </div>
            {(liability?.vouchers_expiring_30d ?? 0) > 0 && (
              <div className="text-xs text-amber-700">{liability.vouchers_expiring_30d} vouchers verlopen binnen 30 dagen</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> Fraudesignalen</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            {(fraud || []).slice(0, 6).map((f: any) => (
              <div key={f.id} className="border rounded-md p-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono">{f.pseudonymous_customer_id}</span>
                  <Badge variant="outline" className={f.severity === "critical" || f.severity === "high" ? "border-red-300 text-red-700" : "border-amber-300 text-amber-700"}>
                    {f.fraud_type}
                  </Badge>
                </div>
                <div className="text-muted-foreground mt-1">{f.explanation}</div>
              </div>
            ))}
            {(fraud || []).length === 0 && <div className="text-muted-foreground py-4 text-center">Geen open fraudesignalen.</div>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Ticket className="h-4 w-4" /> Campagnes (met controlegroep)</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            {(campagnes || []).map((c: any) => (
              <div key={c.id} className="border rounded-md p-2">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{c.name}</span>
                  <Badge variant="outline">{c.status}</Badge>
                </div>
                <div className="text-muted-foreground mt-1">
                  {c.treatment_members} treatment / {c.control_members} control · {c.bonus_points_issued} bonuspunten · ×{c.bonus_multiplier}
                </div>
              </div>
            ))}
            {(campagnes || []).length === 0 && <div className="text-muted-foreground py-4 text-center">Nog geen campagnes.</div>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
