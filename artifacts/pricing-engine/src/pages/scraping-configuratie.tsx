import { useState, useEffect } from "react";
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
import { Globe, Play, Plus, RefreshCw, CheckCircle2, XCircle, Clock, AlertTriangle, CalendarClock, Pencil, Trash2 } from "lucide-react";
import { Switch } from "@/components/ui/switch";
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
  const [rooster, setRooster] = useState<any>(null);
  const [laden, setLaden] = useState(true);
  const [testResultaat, setTestResultaat] = useState<any>(null);
  const [testenBezig, setTestenBezig] = useState(false);
  const [runBezig, setRunBezig] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [nieuwSlotDialogOpen, setNieuwSlotDialogOpen] = useState(false);
  const [nieuwSlotTijd, setNieuwSlotTijd] = useState("09:00");
  const [nieuwSlotLabel, setNieuwSlotLabel] = useState("");
  const [slotBezig, setSlotBezig] = useState<number | null>(null);

  // Nieuw concurrent formulier
  const [nieuwNaam, setNieuwNaam] = useState("");
  const [nieuwUrl, setNieuwUrl] = useState("");
  const [nieuwType, setNieuwType] = useState("online");
  const [nieuwPriceSelector, setNieuwPriceSelector] = useState("");
  const [nieuwTitleSelector, setNieuwTitleSelector] = useState("");
  const [nieuwStockSelector, setNieuwStockSelector] = useState("");
  const [nieuwDeliverySelector, setNieuwDeliverySelector] = useState("");
  const [nieuwEanSelector, setNieuwEanSelector] = useState("");
  const [nieuwUrlPattern, setNieuwUrlPattern] = useState("");

  // Bewerk concurrent formulier
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editConcurrent, setEditConcurrent] = useState<any>(null);
  const [editNaam, setEditNaam] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [editType, setEditType] = useState("online");
  const [editPriceSelector, setEditPriceSelector] = useState("");
  const [editTitleSelector, setEditTitleSelector] = useState("");
  const [editStockSelector, setEditStockSelector] = useState("");
  const [editDeliverySelector, setEditDeliverySelector] = useState("");
  const [editEanSelector, setEditEanSelector] = useState("");
  const [editUrlPattern, setEditUrlPattern] = useState("");

  // Test scrape formulier
  const [testUrl, setTestUrl] = useState("");
  const [testPriceSelector, setTestPriceSelector] = useState("");
  const [testTitleSelector, setTestTitleSelector] = useState("");

  useEffect(() => { laadData(); }, []);

  async function laadData() {
    setLaden(true);
    try {
      const [c, r, s] = await Promise.all([
        apiFetch("/api/scraping/configs"),
        apiFetch("/api/scraping/results?limit=30"),
        apiFetch("/api/scraping/schedule"),
      ]);
      setConfigs(c);
      setResultaten(r);
      setRooster(s);
    } catch { toast({ title: "Fout", description: "Kon gegevens niet laden", variant: "destructive" }); }
    setLaden(false);
  }

  async function voegConcurrentToe() {
    try {
      await apiFetch("/api/scraping/configs", {
        method: "POST",
        body: JSON.stringify({
          competitor_name: nieuwNaam, base_url: nieuwUrl, competitor_type: nieuwType,
          url_pattern: nieuwUrlPattern,
          price_selector: nieuwPriceSelector, title_selector: nieuwTitleSelector,
          stock_selector: nieuwStockSelector, delivery_selector: nieuwDeliverySelector,
          ean_selector: nieuwEanSelector,
        }),
      });
      toast({ title: "Concurrent toegevoegd" });
      setDialogOpen(false);
      setNieuwNaam(""); setNieuwUrl(""); setNieuwUrlPattern(""); setNieuwPriceSelector(""); setNieuwTitleSelector("");
      setNieuwStockSelector(""); setNieuwDeliverySelector(""); setNieuwEanSelector("");
      laadData();
    } catch { toast({ title: "Fout", description: "Concurrent toevoegen mislukt", variant: "destructive" }); }
  }

  function openEditDialog(c: any) {
    const cfg = c.configs?.[0] ?? {};
    setEditConcurrent(c);
    setEditNaam(c.competitor_name);
    setEditUrl(c.base_url || "");
    setEditType(c.competitor_type || "online");
    setEditUrlPattern(cfg.url_pattern || "");
    setEditPriceSelector(cfg.price_selector || "");
    setEditTitleSelector(cfg.title_selector || "");
    setEditStockSelector(cfg.stock_selector || "");
    setEditDeliverySelector(cfg.delivery_selector || "");
    setEditEanSelector(cfg.ean_selector || "");
    setEditDialogOpen(true);
  }

  async function wijzigConcurrent() {
    if (!editConcurrent) return;
    try {
      await apiFetch(`/api/scraping/configs/${editConcurrent.competitor_id}`, {
        method: "PUT",
        body: JSON.stringify({
          competitor_name: editNaam, base_url: editUrl, competitor_type: editType,
          url_pattern: editUrlPattern,
          price_selector: editPriceSelector, title_selector: editTitleSelector,
          stock_selector: editStockSelector, delivery_selector: editDeliverySelector,
          ean_selector: editEanSelector,
        }),
      });
      toast({ title: "Concurrent bijgewerkt" });
      setEditDialogOpen(false);
      laadData();
    } catch { toast({ title: "Fout", description: "Bijwerken mislukt", variant: "destructive" }); }
  }

  async function verwijderConcurrent(competitor_id: number, naam: string) {
    if (!confirm(`"${naam}" deactiveren? Dit schakelt scraping uit.`)) return;
    try {
      await apiFetch(`/api/scraping/configs/${competitor_id}`, { method: "DELETE" });
      toast({ title: `"${naam}" gedeactiveerd` });
      laadData();
    } catch { toast({ title: "Fout", description: "Deactiveren mislukt", variant: "destructive" }); }
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

  async function toggleSlot(id: number, active: boolean) {
    setSlotBezig(id);
    try {
      await apiFetch(`/api/scraping/schedule/${id}`, { method: "PUT", body: JSON.stringify({ active }) });
      const s = await apiFetch("/api/scraping/schedule");
      setRooster(s);
    } catch { toast({ title: "Fout", description: "Tijdslot bijwerken mislukt", variant: "destructive" }); }
    setSlotBezig(null);
  }

  async function voegSlotToe() {
    if (!nieuwSlotTijd.match(/^\d{2}:\d{2}$/)) {
      toast({ title: "Ongeldig tijdformaat", description: "Gebruik HH:MM (bijv. 10:00)", variant: "destructive" });
      return;
    }
    try {
      await apiFetch("/api/scraping/schedule", {
        method: "POST",
        body: JSON.stringify({ time_slot: nieuwSlotTijd, label: nieuwSlotLabel, active: true }),
      });
      toast({ title: "Tijdslot toegevoegd" });
      setNieuwSlotDialogOpen(false);
      setNieuwSlotTijd("09:00");
      setNieuwSlotLabel("");
      const s = await apiFetch("/api/scraping/schedule");
      setRooster(s);
    } catch (e: any) {
      const msg = e.message?.includes("409") ? "Tijdslot bestaat al" : "Toevoegen mislukt";
      toast({ title: "Fout", description: msg, variant: "destructive" });
    }
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
                <div className="space-y-3 py-2">
                  <div><Label>Naam *</Label><Input value={nieuwNaam} onChange={e => setNieuwNaam(e.target.value)} placeholder="bv. Bol.com" /></div>
                  <div><Label>Basis-URL (homepage)</Label><Input value={nieuwUrl} onChange={e => setNieuwUrl(e.target.value)} placeholder="https://www.bol.com" /></div>
                  <div><Label>Product-URL patroon</Label><Input value={nieuwUrlPattern} onChange={e => setNieuwUrlPattern(e.target.value)} placeholder="https://www.bol.com/nl/p/{sku}/" /></div>
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
                  <p className="text-xs text-muted-foreground font-medium pt-1">CSS-selectors (optioneel)</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label>Titel</Label><Input value={nieuwTitleSelector} onChange={e => setNieuwTitleSelector(e.target.value)} placeholder=".product-title h1" /></div>
                    <div><Label>Prijs</Label><Input value={nieuwPriceSelector} onChange={e => setNieuwPriceSelector(e.target.value)} placeholder=".price-block__price" /></div>
                    <div><Label>Voorraadstatus</Label><Input value={nieuwStockSelector} onChange={e => setNieuwStockSelector(e.target.value)} placeholder=".stock-status" /></div>
                    <div><Label>Levertijd</Label><Input value={nieuwDeliverySelector} onChange={e => setNieuwDeliverySelector(e.target.value)} placeholder=".delivery-info" /></div>
                    <div><Label>EAN</Label><Input value={nieuwEanSelector} onChange={e => setNieuwEanSelector(e.target.value)} placeholder="[data-ean]" /></div>
                  </div>
                  <Button onClick={voegConcurrentToe} disabled={!nieuwNaam} className="w-full mt-1">Toevoegen</Button>
                </div>
              </DialogContent>
            </Dialog>

            {/* Bewerk concurrent dialog */}
            <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
              <DialogContent>
                <DialogHeader><DialogTitle>Concurrent bewerken</DialogTitle></DialogHeader>
                <div className="space-y-3 py-2">
                  <div><Label>Naam *</Label><Input value={editNaam} onChange={e => setEditNaam(e.target.value)} /></div>
                  <div><Label>Basis-URL (homepage)</Label><Input value={editUrl} onChange={e => setEditUrl(e.target.value)} /></div>
                  <div><Label>Product-URL patroon</Label><Input value={editUrlPattern} onChange={e => setEditUrlPattern(e.target.value)} placeholder="https://www.example.nl/p/{sku}/" /></div>
                  <div>
                    <Label>Type</Label>
                    <Select value={editType} onValueChange={setEditType}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="online">Online retailer</SelectItem>
                        <SelectItem value="marketplace">Marketplace</SelectItem>
                        <SelectItem value="local">Lokale concurrent</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <p className="text-xs text-muted-foreground font-medium pt-1">CSS-selectors</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label>Titel</Label><Input value={editTitleSelector} onChange={e => setEditTitleSelector(e.target.value)} placeholder=".product-title h1" /></div>
                    <div><Label>Prijs</Label><Input value={editPriceSelector} onChange={e => setEditPriceSelector(e.target.value)} placeholder=".price-block__price" /></div>
                    <div><Label>Voorraadstatus</Label><Input value={editStockSelector} onChange={e => setEditStockSelector(e.target.value)} placeholder=".stock-status" /></div>
                    <div><Label>Levertijd</Label><Input value={editDeliverySelector} onChange={e => setEditDeliverySelector(e.target.value)} placeholder=".delivery-info" /></div>
                    <div><Label>EAN</Label><Input value={editEanSelector} onChange={e => setEditEanSelector(e.target.value)} placeholder="[data-ean]" /></div>
                  </div>
                  <Button onClick={wijzigConcurrent} disabled={!editNaam} className="w-full mt-1">Opslaan</Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        <Tabs defaultValue="concurrenten">
          <TabsList>
            <TabsTrigger value="concurrenten">Concurrenten</TabsTrigger>
            <TabsTrigger value="rooster">Rooster</TabsTrigger>
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
                        <div className="text-right shrink-0 space-y-2">
                          {c.laatste_scrape && (
                            <div className="text-xs text-muted-foreground">
                              <Clock className="w-3 h-3 inline mr-1" />
                              {new Date(c.laatste_scrape).toLocaleDateString("nl-NL")}
                              {c.laatste_status && (
                                <span className="ml-2">{STATUS_LABELS[c.laatste_status] || c.laatste_status}</span>
                              )}
                            </div>
                          )}
                          <div className="flex gap-1 justify-end">
                            <Button size="sm" variant="outline" disabled={runBezig === c.competitor_id || !c.scraping_enabled}
                              onClick={() => runScrape(c.competitor_id)}>
                              <Play className="w-3 h-3 mr-1" />
                              {runBezig === c.competitor_id ? "Bezig..." : "Run scrape"}
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => openEditDialog(c)}>
                              <Pencil className="w-3 h-3" />
                            </Button>
                            <Button size="sm" variant="outline" className="text-red-600 hover:text-red-700"
                              onClick={() => verwijderConcurrent(c.competitor_id, c.competitor_name)}>
                              <Trash2 className="w-3 h-3" />
                            </Button>
                          </div>
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

          <TabsContent value="rooster" className="mt-4">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-sm">Dagelijks scraperooster</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Scrapes worden op deze tijden uitgevoerd. Standaard 3× per dag.
                    {rooster && <span className="ml-1 font-medium text-foreground">{rooster.frequentie_per_dag} actief</span>}
                  </p>
                </div>
                <Dialog open={nieuwSlotDialogOpen} onOpenChange={setNieuwSlotDialogOpen}>
                  <DialogTrigger asChild>
                    <Button size="sm" variant="outline"><Plus className="w-4 h-4 mr-2" />Tijdslot toevoegen</Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader><DialogTitle>Nieuw tijdslot toevoegen</DialogTitle></DialogHeader>
                    <div className="space-y-4 py-2">
                      <div>
                        <Label>Tijdstip (HH:MM) *</Label>
                        <Input
                          value={nieuwSlotTijd}
                          onChange={e => setNieuwSlotTijd(e.target.value)}
                          placeholder="10:00"
                          maxLength={5}
                        />
                      </div>
                      <div>
                        <Label>Omschrijving (optioneel)</Label>
                        <Input
                          value={nieuwSlotLabel}
                          onChange={e => setNieuwSlotLabel(e.target.value)}
                          placeholder="bv. Extra run marktopening"
                        />
                      </div>
                      <Button onClick={voegSlotToe} className="w-full" disabled={!nieuwSlotTijd}>
                        <CalendarClock className="w-4 h-4 mr-2" />Toevoegen
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>

              {laden ? (
                <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-16 w-full" />)}</div>
              ) : (
                <div className="space-y-2">
                  {rooster?.tijdsloten?.map((slot: any) => (
                    <Card key={slot.id} className={slot.active ? "" : "opacity-50"}>
                      <CardContent className="py-3 px-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <Clock className="w-4 h-4 text-muted-foreground" />
                            <div>
                              <span className="font-mono font-semibold text-sm">{slot.time_slot}</span>
                              {slot.label && (
                                <span className="text-xs text-muted-foreground ml-2">{slot.label}</span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">{slot.active ? "Actief" : "Inactief"}</span>
                            <Switch
                              checked={slot.active}
                              disabled={slotBezig === slot.id}
                              onCheckedChange={v => toggleSlot(slot.id, v)}
                            />
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                  {!rooster?.tijdsloten?.length && (
                    <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">
                      <CalendarClock className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      Geen tijdsloten geconfigureerd
                    </CardContent></Card>
                  )}
                </div>
              )}
            </div>
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
  );
}
