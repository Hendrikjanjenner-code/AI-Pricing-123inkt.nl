import { useState, useEffect } from "react";
import { SidebarLayout } from "@/components/layout/SidebarLayout";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { ClipboardList, RefreshCw, Search, User, Clock } from "lucide-react";
import { getAuthToken } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

async function apiFetch(path: string) {
  const token = getAuthToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const ACTIE_LABELS: Record<string, string> = {
  approve: "Goedgekeurd",
  reject: "Afgewezen",
  override: "Overschreven",
  export_csv: "CSV export",
  api_push: "API push",
  rollback: "Teruggedraaid",
  login: "Ingelogd",
  update_strategy: "Strategie gewijzigd",
  create_user: "Gebruiker aangemaakt",
  update_user: "Gebruiker bijgewerkt",
};

const ENTITEIT_LABELS: Record<string, string> = {
  recommendation: "Prijsadvies",
  execution_job: "Uitvoering-job",
  product: "Product",
  user: "Gebruiker",
  category_strategy: "CategorieStrategie",
};

export default function AuditLogPage() {
  const { toast } = useToast();
  const [data, setData] = useState<any>(null);
  const [laden, setLaden] = useState(true);
  const [zoekterm, setZoekterm] = useState("");
  const [gebruiker, setGebruiker] = useState("all");
  const [actie, setActie] = useState("all");
  const [entiteit, setEntiteit] = useState("all");
  const [pagina, setPagina] = useState(1);

  useEffect(() => { laadData(); }, [gebruiker, actie, entiteit, pagina]);

  async function laadData() {
    setLaden(true);
    try {
      const params = new URLSearchParams({ page: String(pagina), page_size: "50" });
      if (gebruiker !== "all") params.set("gebruiker", gebruiker);
      if (actie !== "all") params.set("actie", actie);
      if (entiteit !== "all") params.set("entiteit", entiteit);
      const d = await apiFetch(`/api/audit-log?${params}`);
      setData(d);
    } catch { toast({ title: "Fout bij laden", variant: "destructive" }); }
    setLaden(false);
  }

  const entries = (data?.entries || []).filter((e: any) => {
    if (!zoekterm) return true;
    const term = zoekterm.toLowerCase();
    return (
      (e.gebruiker || "").toLowerCase().includes(term) ||
      (e.actie || "").toLowerCase().includes(term) ||
      (e.details || "").toLowerCase().includes(term) ||
      (e.entiteit_id || "").toLowerCase().includes(term)
    );
  });

  const filterOpties = data?.filter_opties || {};

  return (
    <SidebarLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Audit Log</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Volledige geschiedenis van alle beslissingen en acties in het systeem.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={laadData}><RefreshCw className="w-4 h-4 mr-2" />Vernieuwen</Button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Totaal acties", waarde: data?.totaal ?? "—", icon: <ClipboardList className="w-5 h-5 text-blue-500" /> },
            { label: "Gebruikers", waarde: filterOpties?.gebruikers?.length ?? "—", icon: <User className="w-5 h-5 text-green-500" /> },
            { label: "Actie-types", waarde: filterOpties?.acties?.length ?? "—", icon: <Clock className="w-5 h-5 text-amber-500" /> },
          ].map(s => (
            <Card key={s.label}>
              <CardContent className="pt-4 flex items-center gap-3">
                {s.icon}
                <div>
                  <div className="text-xl font-bold">{s.waarde}</div>
                  <div className="text-xs text-muted-foreground">{s.label}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Filters */}
        <div className="flex gap-3 flex-wrap bg-card border p-3 rounded-md">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Zoeken in audit log..."
              value={zoekterm}
              onChange={e => setZoekterm(e.target.value)}
            />
          </div>
          <Select value={gebruiker} onValueChange={v => { setGebruiker(v); setPagina(1); }}>
            <SelectTrigger className="w-44"><SelectValue placeholder="Alle gebruikers" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle gebruikers</SelectItem>
              {(filterOpties?.gebruikers || []).map((g: string) => <SelectItem key={g} value={g}>{g}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={actie} onValueChange={v => { setActie(v); setPagina(1); }}>
            <SelectTrigger className="w-44"><SelectValue placeholder="Alle acties" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle acties</SelectItem>
              {(filterOpties?.acties || []).map((a: string) => (
                <SelectItem key={a} value={a}>{ACTIE_LABELS[a] || a}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={entiteit} onValueChange={v => { setEntiteit(v); setPagina(1); }}>
            <SelectTrigger className="w-44"><SelectValue placeholder="Alle entiteiten" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle entiteiten</SelectItem>
              {(filterOpties?.entiteiten || []).map((e: string) => (
                <SelectItem key={e} value={e}>{ENTITEIT_LABELS[e] || e}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Tabel */}
        {laden ? <Skeleton className="h-64 w-full" /> : (
          <div className="rounded-md border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tijdstip</TableHead>
                  <TableHead>Gebruiker</TableHead>
                  <TableHead>Actie</TableHead>
                  <TableHead>Entiteit</TableHead>
                  <TableHead>ID</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((e: any) => (
                  <TableRow key={e.id}>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(e.timestamp).toLocaleString("nl-NL")}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-[10px] font-bold text-primary">
                          {(e.gebruiker || "?").charAt(0).toUpperCase()}
                        </div>
                        <span className="text-sm">{e.gebruiker || "—"}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-muted font-medium">
                        {ACTIE_LABELS[e.actie] || e.actie}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm">{ENTITEIT_LABELS[e.entiteit] || e.entiteit || "—"}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{e.entiteit_id || "—"}</TableCell>
                    <TableCell className="text-sm max-w-[280px] truncate text-muted-foreground">{e.details || "—"}</TableCell>
                  </TableRow>
                ))}
                {!entries.length && (
                  <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">
                    <ClipboardList className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    Geen audit-log-entries gevonden
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>

            {/* Paginering */}
            {data?.totaal > 50 && (
              <div className="flex items-center justify-between p-3 border-t bg-muted/20">
                <span className="text-xs text-muted-foreground">
                  {((pagina - 1) * 50) + 1}–{Math.min(pagina * 50, data.totaal)} van {data.totaal}
                </span>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" disabled={pagina === 1} onClick={() => setPagina(p => p - 1)}>Vorige</Button>
                  <Button size="sm" variant="outline" disabled={pagina * 50 >= data.totaal} onClick={() => setPagina(p => p + 1)}>Volgende</Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </SidebarLayout>
  );
}
