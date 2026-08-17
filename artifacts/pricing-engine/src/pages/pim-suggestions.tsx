import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Check, Loader2, Sparkles, X } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface Suggestie {
  id: number;
  sku_id: string;
  product_name?: string | null;
  attribute_code: string;
  suggested_value: string;
  rationale?: string | null;
  confidence?: number | null;
  model_version?: string | null;
  status: "PENDING" | "APPROVED" | "REJECTED";
  reviewed_by?: string | null;
  created_at?: string | null;
}

function statusBadge(status: string) {
  if (status === "APPROVED") return <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">Goedgekeurd</Badge>;
  if (status === "REJECTED") return <Badge className="bg-red-50 text-red-600 border-red-200 text-xs">Afgewezen</Badge>;
  return <Badge className="bg-amber-50 text-amber-700 border-amber-200 text-xs">Open</Badge>;
}

export default function PimSuggestions() {
  const [rijen, setRijen] = useState<Suggestie[]>([]);
  const [laden, setLaden] = useState(true);
  const [genereren, setGenereren] = useState(false);
  const [bezig, setBezig] = useState<number | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [melding, setMelding] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("PENDING");

  const laad = useCallback(async () => {
    setLaden(true);
    setFout(null);
    try {
      const res = await fetch(`${BASE}/api/pim/suggestions?status=${statusFilter}`, {
        headers: getAuthHeaders(), signal: AbortSignal.timeout(60_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRijen(await res.json());
    } catch (e: any) {
      setFout(e?.message ?? "Laden mislukt");
    } finally {
      setLaden(false);
    }
  }, [statusFilter]);

  useEffect(() => { laad(); }, [laad]);

  const genereer = async () => {
    setGenereren(true);
    setFout(null);
    setMelding(null);
    try {
      const res = await fetch(`${BASE}/api/pim/suggestions/generate?limit=20`, {
        method: "POST", headers: getAuthHeaders(), signal: AbortSignal.timeout(180_000),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? `HTTP ${res.status}`);
      setMelding(data.message ?? "Suggesties gegenereerd.");
      await laad();
    } catch (e: any) {
      setFout(e?.message ?? "Genereren mislukt");
    } finally {
      setGenereren(false);
    }
  };

  const beoordeel = async (id: number, action: "approve" | "reject") => {
    setBezig(id);
    setFout(null);
    try {
      const res = await fetch(`${BASE}/api/pim/suggestions/${id}`, {
        method: "PATCH",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? `HTTP ${res.status}`);
      }
      setRijen((prev) => prev.filter((r) => statusFilter === "PENDING" ? r.id !== id : true));
      if (statusFilter !== "PENDING") await laad();
    } catch (e: any) {
      setFout(e?.message ?? "Beoordelen mislukt");
    } finally {
      setBezig(null);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">AI-contentsuggesties (PIM)</h1>
          <p className="text-sm text-muted-foreground">
            Voorstellen van de AI voor ontbrekende productattributen. Een suggestie wordt pas toegepast na goedkeuring — nooit automatisch.
          </p>
        </div>
        <Button onClick={genereer} disabled={genereren}>
          {genereren ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
          Genereer suggesties
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base">Suggesties</CardTitle>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="PENDING">Open</SelectItem>
                <SelectItem value="APPROVED">Goedgekeurd</SelectItem>
                <SelectItem value="REJECTED">Afgewezen</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-sm text-muted-foreground">{rijen.length} suggestie(s)</span>
          </div>
        </CardHeader>
        <CardContent>
          {melding && <div className="mb-3 text-sm text-emerald-700">{melding}</div>}
          {fout && <div className="mb-3 text-sm text-red-600">{fout}</div>}
          {laden ? (
            <div className="space-y-2">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
          ) : rijen.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              Geen suggesties in deze status. Gebruik “Genereer suggesties” om de AI ontbrekende attributen te laten voorstellen.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead>Attribuut</TableHead>
                  <TableHead>Voorstel</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actie</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rijen.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="font-mono text-xs">{s.sku_id}</TableCell>
                    <TableCell className="max-w-[220px] truncate">{s.product_name ?? "—"}</TableCell>
                    <TableCell><Badge variant="outline" className="text-xs">{s.attribute_code}</Badge></TableCell>
                    <TableCell className="max-w-[280px]">
                      <div className="truncate font-medium">{s.suggested_value}</div>
                      {s.rationale && <div className="truncate text-xs text-muted-foreground">{s.rationale}</div>}
                    </TableCell>
                    <TableCell>{s.confidence != null ? `${Math.round(s.confidence * 100)}%` : "—"}</TableCell>
                    <TableCell>{statusBadge(s.status)}</TableCell>
                    <TableCell className="text-right">
                      {s.status === "PENDING" ? (
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="outline" disabled={bezig === s.id}
                                  onClick={() => beoordeel(s.id, "approve")}>
                            {bezig === s.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4 text-emerald-600" />}
                          </Button>
                          <Button size="sm" variant="outline" disabled={bezig === s.id}
                                  onClick={() => beoordeel(s.id, "reject")}>
                            <X className="h-4 w-4 text-red-500" />
                          </Button>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">{s.reviewed_by ?? ""}</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
