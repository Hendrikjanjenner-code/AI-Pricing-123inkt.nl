import { useRoute, Link } from "wouter";
import { useGetProduct, useGetSkuHistory } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, Package, Tag, ArrowUpRight, ArrowDownRight, Layers } from "lucide-react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, AreaChart, Area } from "recharts";

export default function ProductDetail() {
  const [, params] = useRoute("/producten/:id");
  const id = params?.id as string;

  const { data: product, isLoading: loadingProduct } = useGetProduct(id, { query: { enabled: !!id } });
  const { data: history, isLoading: loadingHistory } = useGetSkuHistory(id, { query: { enabled: !!id } });

  if (loadingProduct) return <div className="p-8"><Skeleton className="h-96 w-full" /></div>;
  if (!product) return <div>Product niet gevonden</div>;

  const fmtBedrag = (v: number | null | undefined) =>
    v != null ? new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(v) : '-';

  const datumFmt = (v: string) => new Date(v).toLocaleDateString('nl-NL', { month: 'short', day: 'numeric' });

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/producten">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{product.product_name}</h1>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
            <span className="font-mono bg-muted px-1 rounded">{product.sku_id}</span>
            <span>•</span>
            <span>{product.brand}</span>
            <span>•</span>
            <span>{product.category} › {product.subcategory}</span>
            {product.ean && (<><span>•</span><span>EAN: <span className="font-mono">{product.ean}</span></span></>)}
            {product.oem_code && (<><span>•</span><span>OEM: <span className="font-mono">{product.oem_code}</span></span></>)}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {product.is_private_label && <Badge variant="secondary">Huismerk</Badge>}
          {product.is_a_brand && <Badge variant="outline" className="border-primary text-primary">A-merk</Badge>}
          <Badge className="uppercase tracking-wider">
            {product.lifecycle_status === 'active' ? 'Actief' : product.lifecycle_status === 'end_of_life' ? 'Einde levensduur' : product.lifecycle_status}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Verkoopprijs</CardTitle>
            <Tag className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{fmtBedrag(product.current_price)}</div>
            <div className="flex justify-between text-xs text-muted-foreground mt-2">
              <span>Min: {fmtBedrag(product.min_price)}</span>
              <span>Max: {fmtBedrag(product.max_price)}</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Kostprijs</CardTitle>
            <ArrowDownRight className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{fmtBedrag(product.cost_price)}</div>
            <div className="text-xs text-muted-foreground mt-2">
              Marge: {product.current_price && product.cost_price
                ? (((product.current_price - product.cost_price) / product.current_price) * 100).toFixed(1)
                : '-'}%
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Voorraad</CardTitle>
            <Package className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{product.stock_quantity?.toLocaleString('nl-NL') ?? '-'}</div>
            <div className="text-xs text-muted-foreground mt-2">Eenheden beschikbaar</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Strategie</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-lg font-bold truncate" title={product.strategy_type || ''}>{product.strategy_type?.replace(/_/g, ' ') || 'Geen'}</div>
            <div className="text-xs text-muted-foreground mt-2">
              Datakwaliteit: <span className={(product.data_quality_score || 0) >= 80 ? 'text-emerald-600' : 'text-amber-600'}>{product.data_quality_score}%</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="price">
        <TabsList className="bg-card border w-full justify-start h-12 rounded-md px-2">
          <TabsTrigger value="price" className="data-[state=active]:bg-muted">Prijshistorie</TabsTrigger>
          <TabsTrigger value="competitor" className="data-[state=active]:bg-muted">Concurrenten</TabsTrigger>
          <TabsTrigger value="sales" className="data-[state=active]:bg-muted">Verkoopvolume</TabsTrigger>
          <TabsTrigger value="margin" className="data-[state=active]:bg-muted">Marge</TabsTrigger>
          <TabsTrigger value="stock" className="data-[state=active]:bg-muted">Voorraadniveau</TabsTrigger>
        </TabsList>

        <div className="mt-4 border rounded-md bg-card p-6">
          {loadingHistory ? <Skeleton className="h-[400px] w-full" /> : history && (
            <>
              <TabsContent value="price" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Historische prijsontwikkeling</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={history.price_history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={datumFmt} />
                    <YAxis fontSize={12} tickLine={false} axisLine={false} domain={['auto', 'auto']} tickFormatter={v => `€${v}`} />
                    <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString('nl-NL')} formatter={(v: number) => [`€${v}`, 'Prijs']} />
                    <Line type="stepAfter" dataKey="value" stroke="var(--primary)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </TabsContent>

              <TabsContent value="competitor" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Concurrentenprijzen vs. eigen prijs</h3>
                {(() => {
                  const dates = Array.from(new Set([
                    ...history.price_history.map((p: any) => p.date),
                    ...history.competitor_price_history.map((p: any) => p.date)
                  ])).sort();
                  const chartData = dates.map(date => {
                    const row: any = { date };
                    const ours = history.price_history.find((p: any) => p.date === date);
                    if (ours) row['Eigen prijs'] = ours.value;
                    history.competitor_price_history.filter((p: any) => p.date === date).forEach((p: any) => {
                      row[p.competitor_name] = p.value;
                    });
                    return row;
                  });
                  const concurrenten = Array.from(new Set(history.competitor_price_history.map((p: any) => p.competitor_name))) as string[];
                  const colors = ['hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))'];
                  return (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={datumFmt} />
                        <YAxis fontSize={12} tickLine={false} axisLine={false} domain={['auto', 'auto']} tickFormatter={v => `€${v}`} />
                        <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString('nl-NL')} formatter={(v: number, n: string) => [`€${v}`, n]} />
                        <Line type="stepAfter" dataKey="Eigen prijs" stroke="var(--primary)" strokeWidth={3} dot={false} />
                        {concurrenten.map((c, i) => (
                          <Line key={c} type="stepAfter" dataKey={c} stroke={colors[i % colors.length]} strokeWidth={2} strokeDasharray="5 5" dot={false} />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  );
                })()}
              </TabsContent>

              <TabsContent value="sales" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Verkoopvolume</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history.sales_history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={datumFmt} />
                    <YAxis fontSize={12} tickLine={false} axisLine={false} />
                    <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString('nl-NL')} formatter={(v: number) => [v, 'Eenheden verkocht']} />
                    <Area type="monotone" dataKey="value" fill="var(--chart-2)" fillOpacity={0.2} stroke="var(--chart-2)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </TabsContent>

              <TabsContent value="margin" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Margehistorie (%)</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={history.margin_history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={datumFmt} />
                    <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={v => `${v}%`} />
                    <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString('nl-NL')} formatter={(v: number) => [`${v}%`, 'Marge']} />
                    <Line type="stepAfter" dataKey="value" stroke="var(--chart-3)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </TabsContent>

              <TabsContent value="stock" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Voorraadniveau</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history.stock_history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={datumFmt} />
                    <YAxis fontSize={12} tickLine={false} axisLine={false} />
                    <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString('nl-NL')} formatter={(v: number) => [v, 'Eenheden op voorraad']} />
                    <Area type="stepAfter" dataKey="value" fill="var(--chart-4)" fillOpacity={0.2} stroke="var(--chart-4)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </TabsContent>
            </>
          )}
        </div>
      </Tabs>
    </div>
  );
}
