import { useState, useEffect } from "react";
import { SidebarLayout } from "@/components/layout/SidebarLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Globe, Play, Plus, RefreshCw, CheckCircle2, XCircle, Clock, AlertTriangle } from "lucide-react";
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

const STATUS_ICON: Record<string, React.ReactElement> = {
  SCRAPE_SUCCESS: <CheckCircle2 className="w-4 h-4 text-green-600" />,
  SCRAPE_FAILED_TIMEOUT: <XCircle className="w-4 h-4 text-red-500" />,
  SCRAPE_FAILED_SELECTOR_MISSING: <XCircle className="w-4 h-4 text-red-500" />,
  SCRAPE_FAILED_BLOCKED: <AlertTriangle className="w-4 h-4 text-amber-500" />,
  SCRAPE_SKIPPED_ROBOTS: <AlertTriangle className="w-4 h-4 text-amber-500" />,
  SCRAPE_FAILED_INVALID_PRICE: <XCircle className="w-4 h-4 text-red-500" />,
};

const STATUS_LABELS: Record<string, string> = {
  SCRAPE_SUCCESS: "Geslaagd",
  SCRAPE_FAILED_TIMEOUT: "Timeout",
  SCRAPE_FAILED_SELECTOR_MISSING: "Selector ontbreekt",
  SCRAPE_FAILED_BLOCKED: "Geblokkeerd",
  SCRAPE_SKIPPED_ROBOTS: "Robots.txt",
  SCRAPE_FAILED_INVALID_PRICE: "Ongeldige prijs",
};

export default function ScrapingConfiguratie() {
  const { toast } = useToast();
  const [configs, setConfigs] = useState<any>(null);
  const [resultaten, setResultaten] = useState<any>(null);
  const [laden, setLaden] = useState(true);
  const [testResultaat, setTestResultaat] = useState<any>(null);
  const [testenBezig, setTestenBezig] = useState(false);
  const [runBezig, setRunBezig] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  // Nieuw concurrent formulier
  const [nieuwNaam, setNieuwNaam] = useState("");
  const [nieuwUrl, setNieuwUrl] = useState("");
  const [nieuwType, setNieuwType] = useState("online");
  const [nieuwPriceSelector, setNieuwPriceSelector] = useState("");
  const [nieuwTitleSelector, setNieuwTitleSelector] = useState("");

  // Test scrape formulier
  const [testUrl, setTestUrl] = useState("");
  const [testPriceSelector, setTestPriceSelector] = useState("");
  const [testTitleSelector, setTestTitleSelector] = useState("");

  useEffect(() => { laadData(); }, []);

  async function laadData() {
    setLaden(true);
    try {
      const [c, r] = await Promise.all([
        apiFetch("/api/scraping/configs"),
        apiFetch("/api/scraping/results?limit=30"),
      ]);
      setConfigs(c);
      setResultaten(r);
    } catch { toast({ title: "Fout", description: "Kon gegevens niet laden", variant: "destructive" }); }
    setLaden(false);
  }

  async function voegConcurrentToe() {
    try {
      await apiFetch("/api/scraping/configs", {
        method: "POST",
        body: JSON.stringify({
          competitor_name: nieuwNaam, base_url: nieuwUrl, competitor_type: nieuwType,
          price_selector: nieuwPriceSelector, title_selector: nieuwTitleSelector,
        }),
      });
      toast({ title: "Concurrent toegevoegd" });
      setDialogOpen(false);
      setNieuwNaam(""); setNieuwUrl(""); setNieuwPriceSelector(""); setNieuwTitleSelector("");
      laadData();
    } catch { toast({ title: "Fout", description: "Concurrent toevoegen mislukt", variant: "destructive" }); }
  }

  async function testScrape() {
    if (!testUrl) return;
    setTestenBezig(true);
    setTestResultaat(null);
    try {
      const r = await apiFetch("/api/scraping/test", {
        method: "POST",
        body: JSON.stringify({ url: testUrl, price_selector: testPriceSelector, title_selector: testTitleSelector }),
      });
      setTestResultaat(r);
    } catch { toast({ title: "Test mislukt", variant: "destructive" }); }
    setTestenBezig(false);
  }

  async function runScrape(competitor_id: number) {
    setRunBezig(competitor_id);
    try {
      const r = await apiFetch("/api/scraping/run", {
        method: "POST",
        body: JSON.stringify({ competitor_id }),
      });
      toast({ title: "Scrape uitgevoerd", description: `Statussen: ${r.statussen?.join(", ") || r.status}` });
      laadData();
    } catch { toast({ title: "Scrape mislukt", variant: "destructive" }); }
    setRunBezig(null);
  }

  return (
    <SidebarLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Scraping Configuratie</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Beheer concurrenten, selectors en scrape-resultaten. Respecteert robots.txt en rate limits.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={laadData}><RefreshCw className="w-4 h-4 mr-2" />Vernieuwen</Button>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm"><Plus className="w-4 h-4 mr-2" />Concurrent toevoegen</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Nieuwe concurrent toevoegen</DialogTitle></DialogHeader>
                <div className="space-y-4 py-2">
                  <div><Label>Naam *</Label><Input value={nieuwNaam} onChange={e => setNieuwNaam(e.target.value)} placeholder="bv. Bol.com" /></div>
                  <div><Label>Basis-URL</Label><Input value={nieuwUrl} onChange={e => setNieuwUrl(e.target.value)} placeholder="https://www.bol.com" /></div>
                  <div>
                    <Label>Type</Label>
                    <Select value={nieuwType} onValueChange={setNieuwType}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="online">Online retailer</SelectItem>
                        <SelectItem value="marketplace">Marketplace</SelectItem>
                        <SelectItem value="local">Lokale concurrent</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Titel-selector (CSS)</Label><Input value={nieuwTitleSelector} onChange={e => setNieuwTitleSelector(e.target.value)} placeholder=".product-title h1" /></div>
                  <div><Label>Prijs-selector (CSS)</Label><Input value={nieuwPriceSelector} onChange={e => setNieuwPriceSelector(e.target.value)} placeholder=".price-block__price" /></div>
                  <Button onClick={voegConcurrentToe} disabled={!nieuwNaam} className="w-full">Toevoegen</Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        <Tabs defaultValue="concurrenten">
          <TabsList>
            <TabsTrigger value="concurrenten">Concurrenten</TabsTrigger>
            <TabsTrigger value="test">Test scrape</TabsTrigger>
            <TabsTrigger value="resultaten">Scrape-resultaten</TabsTrigger>
          </TabsList>

          <TabsContent value="concurrenten" className="mt-4">
            {laden ? (
              <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-20 w-full" />)}</div>
            ) : (
              <div className="grid gap-4">
                {configs?.concurrenten?.map((c: any) => (
                  <Card key={c.competitor_id}>
                    <CardContent className="pt-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                            <Globe className="w-5 h-5 text-primary" />
                          </div>
                          <div>
                            <div className="font-semibold">{c.competitor_name}</div>
                            <div className="text-xs text-muted-foreground">{c.base_url || "Geen URL"}</div>
                            <div className="flex gap-2 mt-1">
                              <Badge variant="outline" className="text-[10px]">{c.competitor_type}</Badge>
                              <Badge variant={c.scraping_enabled ? "default" : "secondary"} className="text-[10px]">
                                {c.scraping_enabled ? "Scraping actief" : "Scraping uit"}
                              </Badge>
                              <Badge variant="outline" className="text-[10px]">{c.configs_count} config(s)</Badge>
                            </div>
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          {c.laatste_scrape && (
                            <div className="text-xs text-muted-foreground mb-2">
                              <Clock className="w-3 h-3 inline mr-1" />
                              {new Date(c.laatste_scrape).toLocaleDateString("nl-NL")}
                              {c.laatste_status && (
                                <span className="ml-2">{STATUS_LABELS[c.laatste_status] || c.laatste_status}</span>
                              )}
                            </div>
                          )}
                          <Button size="sm" variant="outline" disabled={runBezig === c.competitor_id || !c.scraping_enabled}
                            onClick={() => runScrape(c.competitor_id)}>
                            <Play className="w-3 h-3 mr-1" />
                            {runBezig === c.competitor_id ? "Bezig..." : "Run scrape"}
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {(!configs?.concurrenten?.length) && (
                  <Card><CardContent className="py-12 text-center text-muted-foreground">
                    <Globe className="w-10 h-10 mx-auto mb-3 opacity-30" />
                    <p className="font-medium">Nog geen concurrenten geconfigureerd</p>
                    <p className="text-sm mt-1">Voeg een concurrent toe om te beginnen</p>
                  </CardContent></Card>
                )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="test" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Test scrape uitvoeren</CardTitle>
                <CardDescription>Voer een eenmalige testscrape uit op een URL. Robots.txt wordt gerespecteerd.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div><Label>URL *</Label><Input value={testUrl} onChange={e => setTestUrl(e.target.value)} placeholder="https://www.concurrent.nl/product/xyz" /></div>
                <div className="grid grid-cols-2 gap-4">
                  <div><Label>Titel-selector</Label><Input value={testTitleSelector} onChange={e => setTestTitleSelector(e.target.value)} placeholder=".product-title" /></div>
                  <div><Label>Prijs-selector</Label><Input value={testPriceSelector} onChange={e => setTestPriceSelector(e.target.value)} placeholder=".price" /></div>
                </div>
                <Button onClick={testScrape} disabled={testenBezig || !testUrl}>
                  <Play className="w-4 h-4 mr-2" />{testenBezig ? "Testen..." : "Test uitvoeren"}
                </Button>
                {testResultaat && (
                  <div className="mt-4 p-4 rounded-lg border bg-muted/30 space-y-2">
                    <div className="flex items-center gap-2 font-medium">
                      {STATUS_ICON[testResultaat.scrape_status] || <Clock className="w-4 h-4" />}
                      {STATUS_LABELS[testResultaat.scrape_status] || testResultaat.scrape_status}
                    </div>
                    {testResultaat.product_title && <div className="text-sm"><span className="text-muted-foreground">Titel:</span> {testResultaat.product_title}</div>}
                    {testResultaat.price_inc_vat && <div className="text-sm"><span className="text-muted-foreground">Prijs:</span> €{testResultaat.price_inc_vat}</div>}
                    {testResultaat.stock_status && <div className="text-sm"><span className="text-muted-foreground">Voorraad:</span> {testResultaat.stock_status}</div>}
                    {testResultaat.delivery_days && <div className="text-sm"><span className="text-muted-foreground">Levertijd:</span> {testResultaat.delivery_days} dagen</div>}
                    {testResultaat.error_message && <div className="text-sm text-red-600"><span className="text-muted-foreground">Fout:</span> {testResultaat.error_message}</div>}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="resultaten" className="mt-4">
            {laden ? <Skeleton className="h-64 w-full" /> : (
              <div className="rounded-md border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Concurrent</TableHead>
                      <TableHead>Producttitel</TableHead>
                      <TableHead className="text-right">Prijs</TableHead>
                      <TableHead>Voorraad</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Tijdstip</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resultaten?.resultaten?.map((r: any) => (
                      <TableRow key={r.scrape_id}>
                        <TableCell className="font-medium text-sm">{r.competitor_name}</TableCell>
                        <TableCell className="text-sm max-w-[200px] truncate">{r.product_title || <span className="text-muted-foreground italic">—</span>}</TableCell>
                        <TableCell className="text-right font-mono text-sm">{r.price_inc_vat ? `€${r.price_inc_vat.toFixed(2)}` : "—"}</TableCell>
                        <TableCell className="text-sm">{r.stock_status || "—"}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            {STATUS_ICON[r.scrape_status] || <Clock className="w-4 h-4 text-muted-foreground" />}
                            <span className="text-xs">{STATUS_LABELS[r.scrape_status] || r.scrape_status}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {new Date(r.scraped_at).toLocaleString("nl-NL")}
                        </TableCell>
                      </TableRow>
                    ))}
                    {!resultaten?.resultaten?.length && (
                      <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Nog geen scrape-resultaten</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </SidebarLayout>
  );
}
