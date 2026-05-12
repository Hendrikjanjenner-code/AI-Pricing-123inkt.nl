import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { CheckCircle2, XCircle, AlertTriangle, Link2, RefreshCw, Play } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

async function apiFetch(path: string, options?: RequestInit) {
  const token = getAuthToken();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(options?.headers || {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const MATCH_TYPE_LABELS: Record<string, string> = {
  EXACT_MATCH: "Exacte match",
  STRONG_MATCH: "Sterke match",
  PROBABLE_MATCH: "Waarschijnlijke match",
  FUNCTIONAL_MATCH: "Functionele match",
  NO_MATCH: "Geen match",
};

const MATCH_TYPE_VARIANT: Record<string, string> = {
  EXACT_MATCH: "bg-green-100 text-green-800",
  STRONG_MATCH: "bg-blue-100 text-blue-800",
  PROBABLE_MATCH: "bg-amber-100 text-amber-800",
  FUNCTIONAL_MATCH: "bg-orange-100 text-orange-800",
  NO_MATCH: "bg-red-100 text-red-800",
};

const REASON_LABELS: Record<string, string> = {
  MATCH_EXACT_EAN: "EAN exacte match",
  MATCH_EXACT_MPN: "MPN exacte match",
  MATCH_STRONG_TITLE_BRAND: "Sterke titel + merk-match",
  MATCH_PACK_SIZE_DIFFERENCE: "Verpakking verschilt",
  MATCH_LOW_CONFIDENCE: "Lage confidence",
  MATCH_MANUAL_OVERRIDE: "Handmatig gekoppeld",
  MATCH_REJECTED: "Afgewezen",
};

function ConfidentieBalk({ waarde }: { waarde: number }) {
  const pct = Math.round(waarde * 100);
  const kleur = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-blue-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-muted rounded-full h-1.5 overflow-hidden">
        <div className={`h-full rounded-full ${kleur}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono tabular-nums w-8">{pct}%</span>
    </div>
  );
}

export default function ProductMatching() {
  const { toast } = useToast();
  const [suggestions, setSuggestions] = useState<any>(null);
  const [goedgekeurd, setGoedgekeurd] = useState<any>(null);
  const [laden, setLaden] = useState(true);
  const [matchenBezig, setMatchenBezig] = useState(false);
  const [actiefTab, setActiefTab] = useState("pending");

  useEffect(() => { laadData(); }, []);

  async function laadData() {
    setLaden(true);
    try {
      const [s, g] = await Promise.all([
        apiFetch("/api/matching/suggestions?status=pending"),
        apiFetch("/api/matching/suggestions?status=goedgekeurd&page_size=20"),
      ]);
      setSuggestions(s);
      setGoedgekeurd(g);
    } catch { toast({ title: "Fout bij laden", variant: "destructive" }); }
    setLaden(false);
  }

  async function runMatching() {
    setMatchenBezig(true);
    try {
      const r = await apiFetch("/api/matching/run", { method: "POST", body: JSON.stringify({}) });
      toast({ title: "Matching uitgevoerd", description: `${r.nieuwe_voorstellen} nieuwe voorstellen gegenereerd` });
      laadData();
    } catch { toast({ title: "Matching mislukt", variant: "destructive" }); }
    setMatchenBezig(false);
  }

  async function keurGoed(match_id: number) {
    try {
      await apiFetch("/api/matching/approve", { method: "POST", body: JSON.stringify({ match_id }) });
      toast({ title: "Match goedgekeurd" });
      laadData();
    } catch { toast({ title: "Fout", variant: "destructive" }); }
  }

  async function wijs_af(match_id: number) {
    try {
      await apiFetch("/api/matching/reject", { method: "POST", body: JSON.stringify({ match_id }) });
      toast({ title: "Match afgewezen" });
      laadData();
    } catch { toast({ title: "Fout", variant: "destructive" }); }
  }

  const pending = suggestions?.items || [];
  const approved = goedgekeurd?.items || [];

  return (
    <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Product Matching</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Koppel concurrent-producten aan eigen SKU's. Slechte matches beïnvloeden nooit de prijsstelling.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={laadData}><RefreshCw className="w-4 h-4 mr-2" />Vernieuwen</Button>
            <Button size="sm" onClick={runMatching} disabled={matchenBezig}>
              <Play className="w-4 h-4 mr-2" />{matchenBezig ? "Matchen..." : "Matching uitvoeren"}
            </Button>
          </div>
        </div>

        {/* KPI balk */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Openstaande voorstellen", waarde: suggestions?.totaal ?? "—", kleur: "text-amber-600" },
            { label: "Goedgekeurde matches", waarde: goedgekeurd?.totaal ?? "—", kleur: "text-green-600" },
            { label: "Gemiddelde confidence", waarde: pending.length ? `${Math.round(pending.reduce((s: number, m: any) => s + m.match_confidence, 0) / pending.length * 100)}%` : "—", kleur: "text-blue-600" },
          ].map(k => (
            <Card key={k.label}>
              <CardContent className="pt-4">
                <div className={`text-2xl font-bold ${k.kleur}`}>{k.waarde}</div>
                <div className="text-xs text-muted-foreground mt-1">{k.label}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        <Tabs value={actiefTab} onValueChange={setActiefTab}>
          <TabsList>
            <TabsTrigger value="pending">Openstaand ({suggestions?.totaal || 0})</TabsTrigger>
            <TabsTrigger value="goedgekeurd">Goedgekeurd ({goedgekeurd?.totaal || 0})</TabsTrigger>
          </TabsList>

          <TabsContent value="pending" className="mt-4">
            {laden ? <Skeleton className="h-64 w-full" /> : (
              <div className="rounded-md border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Eigen SKU</TableHead>
                      <TableHead>Concurrent</TableHead>
                      <TableHead>Match type</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Reden</TableHead>
                      <TableHead>Waarschuwing</TableHead>
                      <TableHead className="text-right">Actie</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pending.map((m: any) => (
                      <TableRow key={m.match_id}>
                        <TableCell>
                          <div className="font-medium text-sm">{m.product_naam}</div>
                          <div className="text-xs font-mono text-muted-foreground">{m.own_sku_id}</div>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm font-medium">{m.concurrent}</div>
                          <div className="text-xs text-muted-foreground font-mono">{m.competitor_sku}</div>
                        </TableCell>
                        <TableCell>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${MATCH_TYPE_VARIANT[m.match_type] || ""}`}>
                            {MATCH_TYPE_LABELS[m.match_type] || m.match_type}
                          </span>
                        </TableCell>
                        <TableCell className="min-w-[120px]">
                          <ConfidentieBalk waarde={m.match_confidence} />
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {REASON_LABELS[m.match_reason] || m.match_reason}
                        </TableCell>
                        <TableCell>
                          {m.pack_size_warning && (
                            <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-300">
                              <AlertTriangle className="w-3 h-3 mr-1" />Verpakking
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex gap-1 justify-end">
                            <Button size="sm" variant="ghost" className="text-green-600 h-7 px-2" onClick={() => keurGoed(m.match_id)}>
                              <CheckCircle2 className="w-4 h-4" />
                            </Button>
                            <Button size="sm" variant="ghost" className="text-red-500 h-7 px-2" onClick={() => wijs_af(m.match_id)}>
                              <XCircle className="w-4 h-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                    {!pending.length && (
                      <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                        <Link2 className="w-8 h-8 mx-auto mb-2 opacity-30" />
                        Geen openstaande match-voorstellen
                      </TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>

          <TabsContent value="goedgekeurd" className="mt-4">
            {laden ? <Skeleton className="h-64 w-full" /> : (
              <div className="rounded-md border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Eigen SKU</TableHead>
                      <TableHead>Concurrent</TableHead>
                      <TableHead>Match type</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Goedgekeurd door</TableHead>
                      <TableHead>Datum</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {approved.map((m: any) => (
                      <TableRow key={m.match_id}>
                        <TableCell>
                          <div className="font-medium text-sm">{m.product_naam}</div>
                          <div className="text-xs font-mono text-muted-foreground">{m.own_sku_id}</div>
                        </TableCell>
                        <TableCell className="text-sm">{m.concurrent}</TableCell>
                        <TableCell>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${MATCH_TYPE_VARIANT[m.match_type] || ""}`}>
                            {MATCH_TYPE_LABELS[m.match_type] || m.match_type}
                          </span>
                        </TableCell>
                        <TableCell className="min-w-[120px]"><ConfidentieBalk waarde={m.match_confidence} /></TableCell>
                        <TableCell className="text-sm">{m.approved_by || "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {m.approved_at ? new Date(m.approved_at).toLocaleDateString("nl-NL") : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                    {!approved.length && (
                      <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Nog geen goedgekeurde matches</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>
        </Tabs>
    </div>
  );
}
