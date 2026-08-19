import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Coins, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface UsageRow {
  username: string;
  calls_reserved: number;
  tokens_reserved: number;
  tokens_actual: number;
  budget_exceeded_count: number;
  max_calls_per_day: number | null;
  max_tokens_per_day: number | null;
  calls_pct: number | null;
  tokens_pct: number | null;
}

interface ConfigRow {
  id: number;
  username: string | null; // null = globale standaard
  max_calls_per_day: number | null;
  max_tokens_per_day: number | null;
  updated_at: string | null;
  updated_by: string | null;
}

function authHeaders(json = false): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${getAuthToken()}` };
  if (json) h["Content-Type"] = "application/json";
  return h;
}

function pctBadge(pct: number | null) {
  if (pct === null) return <span className="text-muted-foreground">—</span>;
  const cls =
    pct >= 100
      ? "text-red-600 border-red-600/40 bg-red-50 font-semibold"
      : pct >= 80
        ? "text-amber-600 border-amber-600/40"
        : "text-green-600 border-green-600/40";
  return (
    <Badge variant="outline" className={cls}>
      {pct.toLocaleString("nl-NL")}%
    </Badge>
  );
}

export default function AiBudgetBeheer() {
  const { toast } = useToast();

  const [usage, setUsage] = useState<UsageRow[] | null>(null);
  const [usageDate, setUsageDate] = useState<string | null>(null);
  const [configs, setConfigs] = useState<ConfigRow[] | null>(null);
  const [laden, setLaden] = useState(false);

  // Bewerk-dialoog: null = gesloten; { username: null } = globale standaard
  const [editOpen, setEditOpen] = useState(false);
  const [editUsername, setEditUsername] = useState<string | null>(null);
  const [editNieuweGebruiker, setEditNieuweGebruiker] = useState("");
  const [editIsNieuw, setEditIsNieuw] = useState(false);
  const [editCalls, setEditCalls] = useState("");
  const [editTokens, setEditTokens] = useState("");
  const [opslaanBezig, setOpslaanBezig] = useState(false);

  const laad = useCallback(async () => {
    setLaden(true);
    try {
      const [uRes, cRes] = await Promise.all([
        fetch(`${BASE}/api/copilot/budget/usage`, { headers: authHeaders() }),
        fetch(`${BASE}/api/copilot/budget/config`, { headers: authHeaders() }),
      ]);
      if (!uRes.ok || !cRes.ok) throw new Error();
      const u = await uRes.json();
      setUsage(u.users ?? []);
      setUsageDate(u.date ?? null);
      setConfigs(await cRes.json());
    } catch {
      toast({ title: "AI-budgetgegevens ophalen mislukt", variant: "destructive" });
    } finally {
      setLaden(false);
    }
  }, [toast]);

  useEffect(() => {
    laad();
  }, [laad]);

  const openEdit = (username: string | null, isNieuw = false) => {
    setEditUsername(username);
    setEditIsNieuw(isNieuw);
    setEditNieuweGebruiker("");
    const bestaand = configs?.find((c) => c.username === username);
    setEditCalls(bestaand?.max_calls_per_day != null ? String(bestaand.max_calls_per_day) : "");
    setEditTokens(bestaand?.max_tokens_per_day != null ? String(bestaand.max_tokens_per_day) : "");
    setEditOpen(true);
  };

  const opslaan = async () => {
    const username = editIsNieuw ? editNieuweGebruiker.trim() : editUsername;
    if (editIsNieuw && !username) return;
    setOpslaanBezig(true);
    try {
      const payload: Record<string, unknown> = {
        username,
        max_calls_per_day: editCalls.trim() === "" ? null : Number(editCalls),
        max_tokens_per_day: editTokens.trim() === "" ? null : Number(editTokens),
      };
      const res = await fetch(`${BASE}/api/copilot/budget/config`, {
        method: "PUT",
        headers: authHeaders(true),
        body: JSON.stringify(payload),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d?.detail || "Opslaan mislukt");
      toast({ title: "Budgetlimiet opgeslagen" });
      setEditOpen(false);
      laad();
    } catch (e: any) {
      toast({ title: "Budgetlimiet opslaan mislukt", description: e?.message, variant: "destructive" });
    } finally {
      setOpslaanBezig(false);
    }
  };

  const verwijderen = async (config: ConfigRow) => {
    const naam = config.username ?? "de globale standaard";
    if (!confirm(`Weet je zeker dat je de budgetlimiet voor ${naam} wilt verwijderen?`)) return;
    try {
      const res = await fetch(`${BASE}/api/copilot/budget/config/${config.id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => null);
        throw new Error(d?.detail || "Verwijderen mislukt");
      }
      toast({ title: "Budgetlimiet verwijderd" });
      laad();
    } catch (e: any) {
      toast({ title: "Verwijderen mislukt", description: e?.message, variant: "destructive" });
    }
  };

  const globaal = configs?.find((c) => c.username === null) ?? null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Coins className="w-5 h-5" />
              AI-budget per gebruiker
            </CardTitle>
            <CardDescription>
              Dagverbruik van de Copilot (calls en tokens) en budgetlimieten.
              {usageDate ? ` Verbruik van ${new Date(usageDate).toLocaleDateString("nl-NL")}.` : ""}
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={laad} disabled={laden}>
              <RefreshCw className="w-4 h-4 mr-1" /> Vernieuwen
            </Button>
            <Button size="sm" onClick={() => openEdit(null)}>
              <Pencil className="w-4 h-4 mr-1" /> Globale standaard
            </Button>
            <Button size="sm" variant="outline" onClick={() => openEdit(null, true)}>
              <Plus className="w-4 h-4 mr-1" /> Limiet per gebruiker
            </Button>
          </div>
        </div>
        {globaal && (
          <p className="text-sm text-muted-foreground mt-2">
            Globale standaard: {globaal.max_calls_per_day?.toLocaleString("nl-NL") ?? "systeemstandaard"} calls/dag,{" "}
            {globaal.max_tokens_per_day?.toLocaleString("nl-NL") ?? "systeemstandaard"} tokens/dag
            {globaal.updated_by ? ` — laatst gewijzigd door ${globaal.updated_by}` : ""}.
          </p>
        )}
      </CardHeader>
      <CardContent className="p-0">
        <div className="px-6 pb-2 text-sm font-medium text-muted-foreground">Dagverbruik vandaag</div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Gebruiker</TableHead>
              <TableHead className="text-right">Calls</TableHead>
              <TableHead className="text-right">% van limiet</TableHead>
              <TableHead className="text-right">Tokens (gereserveerd)</TableHead>
              <TableHead className="text-right">Tokens (werkelijk)</TableHead>
              <TableHead className="text-right">% van limiet</TableHead>
              <TableHead className="text-right">Geweigerd (budget op)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {laden && usage === null ? (
              Array.from({ length: 3 }).map((_, i) => (
                <TableRow key={i}>
                  {[1, 2, 3, 4, 5, 6, 7].map((j) => (
                    <TableCell key={j}><Skeleton className="h-6 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : !usage || usage.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                  Nog geen AI-verbruik vandaag.
                </TableCell>
              </TableRow>
            ) : (
              usage.map((u) => {
                const overschreden =
                  (u.calls_pct !== null && u.calls_pct >= 100) ||
                  (u.tokens_pct !== null && u.tokens_pct >= 100) ||
                  u.budget_exceeded_count > 0;
                return (
                  <TableRow key={u.username} className={overschreden ? "bg-red-50/60" : undefined}>
                    <TableCell className="font-medium">
                      {u.username}
                      {overschreden && (
                        <Badge variant="outline" className="ml-2 text-red-600 border-red-600/40">
                          Budget overschreden
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {u.calls_reserved.toLocaleString("nl-NL")}
                      <span className="text-muted-foreground"> / {u.max_calls_per_day?.toLocaleString("nl-NL") ?? "∞"}</span>
                    </TableCell>
                    <TableCell className="text-right">{pctBadge(u.calls_pct)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {u.tokens_reserved.toLocaleString("nl-NL")}
                      <span className="text-muted-foreground"> / {u.max_tokens_per_day?.toLocaleString("nl-NL") ?? "∞"}</span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{u.tokens_actual.toLocaleString("nl-NL")}</TableCell>
                    <TableCell className="text-right">{pctBadge(u.tokens_pct)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {u.budget_exceeded_count > 0 ? (
                        <span className="text-red-600 font-semibold">{u.budget_exceeded_count}</span>
                      ) : (
                        <span className="text-muted-foreground">0</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>

        <div className="px-6 pt-6 pb-2 text-sm font-medium text-muted-foreground">Budgetlimieten</div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Geldt voor</TableHead>
              <TableHead className="text-right">Max. calls/dag</TableHead>
              <TableHead className="text-right">Max. tokens/dag</TableHead>
              <TableHead>Laatst gewijzigd</TableHead>
              <TableHead className="text-right">Acties</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {laden && configs === null ? (
              Array.from({ length: 2 }).map((_, i) => (
                <TableRow key={i}>
                  {[1, 2, 3, 4, 5].map((j) => (
                    <TableCell key={j}><Skeleton className="h-6 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : !configs || configs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                  Nog geen budgetlimieten ingesteld; de ingebouwde standaard geldt voor iedereen.
                </TableCell>
              </TableRow>
            ) : (
              configs.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    {c.username ?? <Badge variant="secondary">Globale standaard</Badge>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {c.max_calls_per_day?.toLocaleString("nl-NL") ?? <span className="text-muted-foreground">standaard</span>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {c.max_tokens_per_day?.toLocaleString("nl-NL") ?? <span className="text-muted-foreground">standaard</span>}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {c.updated_at ? new Date(c.updated_at).toLocaleString("nl-NL") : "—"}
                    {c.updated_by ? ` door ${c.updated_by}` : ""}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(c.username)}>
                      <Pencil className="w-4 h-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => verwijderen(c)}>
                      <Trash2 className="w-4 h-4 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editIsNieuw
                ? "Limiet per gebruiker instellen"
                : editUsername
                  ? `Budgetlimiet voor ${editUsername}`
                  : "Globale standaardlimiet"}
            </DialogTitle>
            <DialogDescription>
              Laat een veld leeg om terug te vallen op de {editIsNieuw || editUsername ? "globale standaard" : "ingebouwde standaard"}.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {editIsNieuw && (
              <div className="space-y-2">
                <Label>Gebruikersnaam</Label>
                <Input
                  value={editNieuweGebruiker}
                  onChange={(e) => setEditNieuweGebruiker(e.target.value)}
                  placeholder="bijv. jan.jansen"
                />
              </div>
            )}
            <div className="space-y-2">
              <Label>Max. calls per dag</Label>
              <Input
                type="number"
                min={1}
                value={editCalls}
                onChange={(e) => setEditCalls(e.target.value)}
                placeholder="standaard"
              />
            </div>
            <div className="space-y-2">
              <Label>Max. tokens per dag</Label>
              <Input
                type="number"
                min={1}
                value={editTokens}
                onChange={(e) => setEditTokens(e.target.value)}
                placeholder="standaard"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>Annuleren</Button>
            <Button onClick={opslaan} disabled={opslaanBezig || (editIsNieuw && !editNieuweGebruiker.trim())}>
              {opslaanBezig ? "Opslaan..." : "Opslaan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
