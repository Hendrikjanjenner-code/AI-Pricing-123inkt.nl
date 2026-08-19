import { useState, useEffect } from "react";
import { useListUsers, useCreateUser, useDeleteUser, useUpdateUser } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Trash2, UserPlus, AlertTriangle, Database, History, Download, RefreshCw, WifiOff } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { getAuthToken } from "@/lib/auth";
import { useAiProviderStatus, AI_PROVIDER_QUERY_KEY, type AiProviderInfo } from "@/hooks/use-ai-provider-status";
import AiBudgetBeheer from "@/components/ai-budget-beheer";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

const ROL_LABELS: Record<string, string> = {
  admin: "Beheerder",
  pricing_manager: "Prijsmanager",
  analyst: "Analist",
  viewer: "Lezer",
};

export default function Instellingen() {
  const { data: gebruikers, isLoading } = useListUsers();
  const aanmakenMut = useCreateUser();
  const verwijderenMut = useDeleteUser();
  const bijwerkenMut = useUpdateUser();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { user } = useAuth();

  const [open, setOpen] = useState(false);
  const [formulier, setFormulier] = useState({ username: '', email: '', password: '', role: 'viewer', full_name: '' });

  const [clearOpen, setClearOpen] = useState(false);
  const [clearBezig, setClearBezig] = useState(false);
  const [clearBevestig, setClearBevestig] = useState("");
  const [previewData, setPreviewData] = useState<any>(null);
  const [previewLaden, setPreviewLaden] = useState(false);

  const [migraties, setMigraties] = useState<any[]>([]);
  const [migratiesLaden, setMigratiesLaden] = useState(false);

  // AI-provider (Task #79): actieve provider + status van beide opties.
  // Gedeelde React Query-cache (Task #104): dezelfde query voedt ook het
  // AI-statusbadge in de navigatiebalk, dat zo direct meebeweegt.
  const isAdmin = user?.role === "admin";
  const providerQuery = useAiProviderStatus(isAdmin);
  const providerInfo = providerQuery.data ?? null;
  const providerLaden = providerQuery.isFetching;
  const [providerWisselBezig, setProviderWisselBezig] = useState(false);
  const [providerTestBezig, setProviderTestBezig] = useState<string | null>(null);
  const [providerTests, setProviderTests] = useState<Record<string, { reachable: boolean; error: string | null }>>({});

  useEffect(() => {
    if (providerQuery.isError) {
      toast({ title: "AI-providerstatus ophalen mislukt", variant: "destructive" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerQuery.isError]);

  const laadProvider = () => providerQuery.refetch();

  const wisselProvider = async (provider: string | null) => {
    setProviderWisselBezig(true);
    try {
      const res = await fetch(`${BASE}/api/copilot/provider`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${getAuthToken()}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ provider }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d?.detail || "Wisselen mislukt");
      // Direct de gedeelde cache bijwerken zodat badge én pagina meebewegen.
      queryClient.setQueryData<AiProviderInfo>(AI_PROVIDER_QUERY_KEY, d);
      setProviderTests({});
      toast({
        title: "AI-provider gewijzigd",
        description: d.warning ?? undefined,
        variant: d.warning ? "destructive" : undefined,
      });
    } catch (e: any) {
      toast({ title: "AI-provider wisselen mislukt", description: e?.message, variant: "destructive" });
    } finally {
      setProviderWisselBezig(false);
    }
  };

  const testProvider = async (provider: string) => {
    setProviderTestBezig(provider);
    try {
      const res = await fetch(`${BASE}/api/copilot/provider/test`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${getAuthToken()}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ provider }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d?.detail || "Test mislukt");
      setProviderTests(prev => ({ ...prev, [provider]: { reachable: d.reachable, error: d.error } }));
      // Statusquery vernieuwen zodat het navigatiebadge de testuitslag direct toont.
      queryClient.invalidateQueries({ queryKey: AI_PROVIDER_QUERY_KEY });
    } catch (e: any) {
      setProviderTests(prev => ({ ...prev, [provider]: { reachable: false, error: e?.message ?? "Test mislukt" } }));
      queryClient.invalidateQueries({ queryKey: AI_PROVIDER_QUERY_KEY });
    } finally {
      setProviderTestBezig(null);
    }
  };

  const laadMigraties = async () => {
    setMigratiesLaden(true);
    try {
      const res = await fetch(`${BASE}/api/admin/schema-migrations`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      const d = await res.json();
      setMigraties(d.migraties ?? []);
    } catch {
      toast({ title: "Migratiegeschiedenis ophalen mislukt", variant: "destructive" });
    } finally {
      setMigratiesLaden(false);
    }
  };

  const exporteerMigraties = async () => {
    try {
      const res = await fetch(`${BASE}/api/admin/schema-migrations/export`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "schema_migrations.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: "Export mislukt", variant: "destructive" });
    }
  };

  // Scroll naar de AI-provider-sectie bij navigatie via #ai-provider
  // (bijv. vanuit het AI-statusbadge in de navigatiebalk, Task #93).
  useEffect(() => {
    if (user?.role !== "admin") return;
    if (window.location.hash !== "#ai-provider") return;
    const t = setTimeout(() => {
      document.getElementById("ai-provider")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 150);
    return () => clearTimeout(t);
  }, [user?.role]);

  useEffect(() => {
    if (user?.role === "admin") {
      laadMigraties();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.role]);

  // De providerstatus wordt automatisch ververst door de gedeelde
  // useAiProviderStatus-query (elke 60s + bij focus) — geen eigen
  // polling-loop meer nodig (Task #104).

  const laadPreview = async () => {
    setPreviewLaden(true);
    try {
      const res = await fetch(`${BASE}/api/admin/clear-data/preview`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      const d = await res.json();
      setPreviewData(d);
    } catch {
      toast({ title: "Preview ophalen mislukt", variant: "destructive" });
    } finally {
      setPreviewLaden(false);
    }
  };

  const handleClearData = async () => {
    if (clearBevestig !== "VERWIJDER") return;
    setClearBezig(true);
    try {
      const res = await fetch(`${BASE}/api/admin/clear-data`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      const d = await res.json();
      toast({
        title: "Data gewist",
        description: `${d.tabellen_geleegd?.length ?? 0} tabellen geleegd.`,
      });
      setClearOpen(false);
      setClearBevestig("");
      setPreviewData(null);
    } catch {
      toast({ title: "Verwijderen mislukt", variant: "destructive" });
    } finally {
      setClearBezig(false);
    }
  };

  const handleAanmaken = async () => {
    try {
      await aanmakenMut.mutateAsync({ data: formulier as any });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      setOpen(false);
      setFormulier({ username: '', email: '', password: '', role: 'viewer', full_name: '' });
      toast({ title: "Gebruiker aangemaakt" });
    } catch {
      toast({ title: "Fout bij aanmaken gebruiker", variant: "destructive" });
    }
  };

  const handleVerwijderen = async (id: number) => {
    if (!confirm("Weet je zeker dat je deze gebruiker wilt verwijderen?")) return;
    try {
      await verwijderenMut.mutateAsync({ id });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      toast({ title: "Gebruiker verwijderd" });
    } catch {
      toast({ title: "Fout bij verwijderen", variant: "destructive" });
    }
  };

  const handleRolWijzigen = async (id: number, rol: string) => {
    try {
      await bijwerkenMut.mutateAsync({ id, data: { role: rol } });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      toast({ title: "Rol bijgewerkt" });
    } catch {
      toast({ title: "Fout bij bijwerken rol", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Systeeminstellingen</h1>
          <p className="text-muted-foreground mt-1">Beheer gebruikers en toegangsrechten.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button><UserPlus className="w-4 h-4 mr-2" /> Gebruiker toevoegen</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Nieuwe gebruiker toevoegen</DialogTitle></DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2"><Label>Gebruikersnaam</Label><Input value={formulier.username} onChange={e => setFormulier(f => ({ ...f, username: e.target.value }))} /></div>
              <div className="space-y-2"><Label>Volledige naam</Label><Input value={formulier.full_name} onChange={e => setFormulier(f => ({ ...f, full_name: e.target.value }))} /></div>
              <div className="space-y-2"><Label>E-mailadres</Label><Input type="email" value={formulier.email} onChange={e => setFormulier(f => ({ ...f, email: e.target.value }))} /></div>
              <div className="space-y-2"><Label>Wachtwoord</Label><Input type="password" value={formulier.password} onChange={e => setFormulier(f => ({ ...f, password: e.target.value }))} /></div>
              <div className="space-y-2"><Label>Rol</Label>
                <Select value={formulier.role} onValueChange={v => setFormulier(f => ({ ...f, role: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Beheerder</SelectItem>
                    <SelectItem value="pricing_manager">Prijsmanager</SelectItem>
                    <SelectItem value="analyst">Analist</SelectItem>
                    <SelectItem value="viewer">Lezer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Annuleren</Button>
              <Button onClick={handleAanmaken} disabled={aanmakenMut.isPending || !formulier.username || !formulier.password}>Aanmaken</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Gebruikersbeheer</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Gebruiker</TableHead>
                <TableHead>E-mail</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Acties</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    {[1,2,3,4,5].map(j => <TableCell key={j}><Skeleton className="h-8 w-full" /></TableCell>)}
                  </TableRow>
                ))
              ) : gebruikers?.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <div className="font-medium">{user.full_name || user.username}</div>
                    <div className="text-xs text-muted-foreground">{user.username}</div>
                  </TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell>
                    <Select value={user.role} onValueChange={(v) => handleRolWijzigen(user.id, v)}>
                      <SelectTrigger className="w-[180px] h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">Beheerder</SelectItem>
                        <SelectItem value="pricing_manager">Prijsmanager</SelectItem>
                        <SelectItem value="analyst">Analist</SelectItem>
                        <SelectItem value="viewer">Lezer</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    {user.is_active
                      ? <Badge variant="secondary" className="bg-emerald-50 text-emerald-600">Actief</Badge>
                      : <Badge variant="outline">Inactief</Badge>}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-8 w-8"
                      onClick={() => handleVerwijderen(user.id)} disabled={verwijderenMut.isPending}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {user?.role === "admin" && (
        <Card id="ai-provider" className="scroll-mt-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="w-5 h-5" />
              AI-provider (Copilot)
            </CardTitle>
            <CardDescription>
              Kies welke provider de AI Copilot gebruikt. De keuze wordt opgeslagen en
              overleeft een herstart. Een niet-geconfigureerde provider valt nooit stil
              terug op de andere optie.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Waarschuwingsbanner: actieve provider onbereikbaar */}
            {providerInfo?.providers?.some((p: any) => p.active && p.reachable === false) && (() => {
              const activeProvider = providerInfo.providers.find((p: any) => p.active && p.reachable === false);
              return (
                <div className="flex items-start gap-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900">
                  <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                  <div className="flex-1 text-sm">
                    <p className="font-semibold">AI-verbinding verbroken — Copilot werkt in fail-safe modus</p>
                    <p className="mt-0.5 text-amber-800">
                      De actieve provider <strong>{activeProvider?.label}</strong> is niet bereikbaar.
                      De Copilot geeft tijdelijk een gestructureerd foutantwoord. De rest van de applicatie
                      is niet beïnvloed.
                    </p>
                    {activeProvider?.error && (
                      <p className="mt-1 font-mono text-xs break-all text-amber-700">{activeProvider.error}</p>
                    )}
                    <p className="mt-1 text-xs text-amber-700">
                      Controleer de API-sleutel of omgevingsvariabelen. Deze banner verdwijnt zodra de verbinding hersteld is.
                    </p>
                  </div>
                </div>
              );
            })()}
            {providerLaden && !providerInfo ? (
              <Skeleton className="h-24 w-full" />
            ) : providerInfo ? (
              <>
                <div className="text-sm text-muted-foreground">
                  Modus:{" "}
                  <Badge variant="outline">
                    {providerInfo.mode === "manual" ? "Handmatig gekozen" : "Automatisch (Replit AI zodra geconfigureerd)"}
                  </Badge>
                  {providerInfo.updated_by && (
                    <span className="ml-2">
                      Laatst gewijzigd door {providerInfo.updated_by}
                      {providerInfo.updated_at ? ` op ${new Date(providerInfo.updated_at).toLocaleString("nl-NL")}` : ""}
                    </span>
                  )}
                </div>
                <div className="space-y-3">
                  {providerInfo.providers?.map((p: any) => {
                    const test = providerTests[p.id];
                    return (
                      <div key={p.id} className="flex flex-wrap items-center gap-3 border rounded-md p-3">
                        <div className="flex-1 min-w-[220px]">
                          <div className="font-medium flex items-center gap-2">
                            {p.label}
                            {p.active && <Badge>Actief</Badge>}
                          </div>
                          <div className="text-sm mt-1 space-x-2">
                            {p.configured ? (
                              <Badge variant="outline" className="text-green-600 border-green-600/40">Geconfigureerd</Badge>
                            ) : (
                              <Badge variant="outline" className="text-red-600 border-red-600/40">Niet geconfigureerd</Badge>
                            )}
                            {p.active && p.reachable === true && (
                              <Badge variant="outline" className="text-green-600 border-green-600/40">Bereikbaar</Badge>
                            )}
                            {p.active && p.reachable === false && (
                              <Badge variant="outline" className="text-red-600 border-red-600/40">Niet bereikbaar</Badge>
                            )}
                            {test && (
                              <Badge variant="outline" className={test.reachable ? "text-green-600 border-green-600/40" : "text-red-600 border-red-600/40"}>
                                Test: {test.reachable ? "OK" : "mislukt"}
                              </Badge>
                            )}
                          </div>
                          {(p.error || test?.error) && (
                            <p className="text-xs text-red-600 mt-1 break-all">{test?.error ?? p.error}</p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={providerTestBezig === p.id || !p.configured}
                            onClick={() => testProvider(p.id)}
                          >
                            {providerTestBezig === p.id ? "Testen..." : "Test verbinding"}
                          </Button>
                          {!p.active && (
                            <Button
                              size="sm"
                              disabled={providerWisselBezig}
                              onClick={() => wisselProvider(p.id)}
                            >
                              Activeren
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="flex gap-2">
                  {providerInfo.mode === "manual" && (
                    <Button size="sm" variant="outline" disabled={providerWisselBezig} onClick={() => wisselProvider(null)}>
                      Terug naar automatisch
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" disabled={providerLaden} onClick={laadProvider}>
                    <RefreshCw className="w-4 h-4 mr-1" /> Vernieuwen
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Status niet beschikbaar.</p>
            )}
          </CardContent>
        </Card>
      )}

      {user?.role === "admin" && <AiBudgetBeheer />}

      {user?.role === "admin" && (
        <Card className="border-destructive/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <Database className="w-5 h-5" />
              Alle data verwijderen
            </CardTitle>
            <CardDescription>
              Wist alle geïmporteerde data (producten, prijzen, verkoopdata, etc.).
              Gebruikers blijven behouden. Onherstelbaar.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Dialog open={clearOpen} onOpenChange={(v) => { setClearOpen(v); if (v) laadPreview(); else { setClearBevestig(""); setPreviewData(null); } }}>
              <DialogTrigger asChild>
                <Button variant="destructive" className="gap-2">
                  <AlertTriangle className="w-4 h-4" />
                  Alle data verwijderen
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2 text-destructive">
                    <AlertTriangle className="w-5 h-5" />
                    Alle data verwijderen
                  </DialogTitle>
                  <DialogDescription>
                    Dit verwijdert alle producten, prijzen, concurrentieprijzen, aanbevelingen en alle andere geïmporteerde data.
                    Gebruikers blijven behouden. Deze actie is <strong>niet ongedaan te maken</strong>.
                  </DialogDescription>
                </DialogHeader>

                {previewData && (
                  <div className="max-h-48 overflow-y-auto border rounded-md text-sm">
                    <table className="w-full">
                      <thead className="bg-muted/50 sticky top-0">
                        <tr>
                          <th className="text-left p-2 font-medium">Tabel</th>
                          <th className="text-right p-2 font-medium">Rijen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.tabellen?.filter((t: any) => t.rijen !== null && t.rijen > 0).map((t: any) => (
                          <tr key={t.tabel} className="border-t">
                            <td className="p-2 font-mono text-xs">{t.tabel}</td>
                            <td className="p-2 text-right tabular-nums text-red-500">{t.rijen?.toLocaleString("nl-NL")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="space-y-2">
                  <Label className="text-sm">
                    Typ <strong>VERWIJDER</strong> om te bevestigen:
                  </Label>
                  <Input
                    placeholder="VERWIJDER"
                    value={clearBevestig}
                    onChange={e => setClearBevestig(e.target.value)}
                    className="font-mono"
                  />
                </div>

                <DialogFooter>
                  <Button variant="outline" onClick={() => { setClearOpen(false); setClearBevestig(""); setPreviewData(null); }}>
                    Annuleren
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleClearData}
                    disabled={clearBevestig !== "VERWIJDER" || clearBezig}
                  >
                    {clearBezig ? "Verwijderen..." : "Definitief verwijderen"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </CardContent>
        </Card>
      )}

      {user?.role === "admin" && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <History className="w-5 h-5" />
                  Schema-migratiegeschiedenis
                </CardTitle>
                <CardDescription>
                  Kolommen die automatisch aan bestaande tabellen zijn toegevoegd, met tijdstempel.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" className="gap-2" onClick={laadMigraties} disabled={migratiesLaden}>
                  <RefreshCw className={`w-4 h-4 ${migratiesLaden ? "animate-spin" : ""}`} />
                  Vernieuwen
                </Button>
                <Button variant="outline" size="sm" className="gap-2" onClick={exporteerMigraties} disabled={migraties.length === 0}>
                  <Download className="w-4 h-4" />
                  Exporteren (CSV)
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tabel</TableHead>
                  <TableHead>Kolom</TableHead>
                  <TableHead>Type wijziging</TableHead>
                  <TableHead className="text-right">Toegepast op</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {migratiesLaden ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i}>
                      {[1, 2, 3, 4].map(j => <TableCell key={j}><Skeleton className="h-6 w-full" /></TableCell>)}
                    </TableRow>
                  ))
                ) : migraties.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                      Nog geen automatische schemawijzigingen geregistreerd.
                    </TableCell>
                  </TableRow>
                ) : (
                  migraties.map((m) => (
                    <TableRow key={m.id}>
                      <TableCell className="font-mono text-xs">{m.table_name}</TableCell>
                      <TableCell className="font-mono text-xs">{m.column_name}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{m.change_type}</Badge>
                      </TableCell>
                      <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                        {m.applied_at ? new Date(m.applied_at).toLocaleString("nl-NL") : "—"}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
