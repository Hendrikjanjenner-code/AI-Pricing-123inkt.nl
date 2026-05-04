import { useRoute, Link } from "wouter";
import { useGetProduct, useGetSkuHistory } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, Package, Tag, ArrowUpRight, ArrowDownRight, Layers } from "lucide-react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, AreaChart, Area } from "recharts";

export default function SkuDetail() {
  const [, params] = useRoute("/skus/:id");
  const id = params?.id as string;
  
  const { data: product, isLoading: loadingProduct } = useGetProduct(id, { query: { enabled: !!id } });
  const { data: history, isLoading: loadingHistory } = useGetSkuHistory(id, { query: { enabled: !!id } });

  if (loadingProduct) return <div className="p-8"><Skeleton className="h-96 w-full" /></div>;
  if (!product) return <div>SKU not found</div>;

  const formatCurrency = (val: number | null | undefined) => 
    val != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' }).format(val) : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/skus">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{product.product_name}</h1>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
            <span className="font-mono bg-muted px-1 rounded">{product.sku_id}</span>
            <span>•</span>
            <span>{product.brand}</span>
            <span>•</span>
            <span>{product.category} &gt; {product.subcategory}</span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {product.is_private_label && <Badge variant="secondary">Private Label</Badge>}
          {product.is_a_brand && <Badge variant="outline" className="border-primary text-primary">A-Brand</Badge>}
          <Badge className="uppercase tracking-wider">{product.lifecycle_status?.replace(/_/g, ' ')}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Current Price</CardTitle>
            <Tag className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(product.current_price)}</div>
            <div className="flex justify-between text-xs text-muted-foreground mt-2">
              <span>Min: {formatCurrency(product.min_price)}</span>
              <span>Max: {formatCurrency(product.max_price)}</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Cost Price</CardTitle>
            <ArrowDownRight className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(product.cost_price)}</div>
            <div className="text-xs text-muted-foreground mt-2">
              Margin: {product.current_price && product.cost_price ? (((product.current_price - product.cost_price) / product.current_price) * 100).toFixed(1) : '-'}%
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Stock</CardTitle>
            <Package className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{product.stock_quantity?.toLocaleString() ?? '-'}</div>
            <div className="text-xs text-muted-foreground mt-2">Units available</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Strategy</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-lg font-bold truncate" title={product.strategy_type || ''}>{product.strategy_type?.replace(/_/g, ' ') || 'None'}</div>
            <div className="text-xs text-muted-foreground mt-2">
              Data Quality: <span className={(product.data_quality_score || 0) >= 80 ? 'text-emerald-600' : 'text-amber-600'}>{product.data_quality_score}%</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="price">
        <TabsList className="bg-card border w-full justify-start h-12 rounded-md px-2">
          <TabsTrigger value="price" className="data-[state=active]:bg-muted">Price History</TabsTrigger>
          <TabsTrigger value="competitor" className="data-[state=active]:bg-muted">Competitors</TabsTrigger>
          <TabsTrigger value="sales" className="data-[state=active]:bg-muted">Sales Volume</TabsTrigger>
          <TabsTrigger value="margin" className="data-[state=active]:bg-muted">Margin</TabsTrigger>
          <TabsTrigger value="stock" className="data-[state=active]:bg-muted">Stock Level</TabsTrigger>
        </TabsList>
        
        <div className="mt-4 border rounded-md bg-card p-6">
          {loadingHistory ? <Skeleton className="h-[400px] w-full" /> : history && (
            <>
              <TabsContent value="price" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Historical Price Development</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={history.price_history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={v => new Date(v).toLocaleDateString(undefined, {month: 'short', day: 'numeric'})} />
                    <YAxis fontSize={12} tickLine={false} axisLine={false} domain={['auto', 'auto']} tickFormatter={v => `€${v}`} />
                    <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString()} formatter={(value: number) => [`€${value}`, 'Price']} />
                    <Line type="stepAfter" dataKey="value" stroke="var(--primary)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </TabsContent>

              <TabsContent value="competitor" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Competitor Prices vs Our Price</h3>
                {/* Transform data for multi-line chart */}
                {(() => {
                  const dates = Array.from(new Set([
                    ...history.price_history.map(p => p.date),
                    ...history.competitor_price_history.map(p => p.date)
                  ])).sort();

                  const chartData = dates.map(date => {
                    const row: any = { date };
                    const ourPrice = history.price_history.find(p => p.date === date);
                    if (ourPrice) row['Our Price'] = ourPrice.value;
                    
                    history.competitor_price_history
                      .filter(p => p.date === date)
                      .forEach(p => {
                        row[p.competitor_name] = p.value;
                      });
                    return row;
                  });

                  const competitors = Array.from(new Set(history.competitor_price_history.map(p => p.competitor_name)));
                  const colors = ['hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))'];

                  return (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={v => new Date(v).toLocaleDateString(undefined, {month: 'short', day: 'numeric'})} />
                        <YAxis fontSize={12} tickLine={false} axisLine={false} domain={['auto', 'auto']} tickFormatter={v => `€${v}`} />
                        <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString()} formatter={(value: number, name: string) => [`€${value}`, name]} />
                        <Line type="stepAfter" dataKey="Our Price" stroke="var(--primary)" strokeWidth={3} dot={false} />
                        {competitors.map((c, i) => (
                          <Line key={c} type="stepAfter" dataKey={c} stroke={colors[i % colors.length]} strokeWidth={2} strokeDasharray="5 5" dot={false} />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  );
                })()}
              </TabsContent>

              <TabsContent value="sales" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Sales Volume</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history.sales_history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={v => new Date(v).toLocaleDateString(undefined, {month: 'short', day: 'numeric'})} />
                    <YAxis fontSize={12} tickLine={false} axisLine={false} />
                    <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString()} formatter={(value: number) => [value, 'Units Sold']} />
                    <Area type="monotone" dataKey="value" fill="var(--chart-2)" fillOpacity={0.2} stroke="var(--chart-2)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </TabsContent>

              <TabsContent value="margin" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Margin History (%)</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={history.margin_history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={v => new Date(v).toLocaleDateString(undefined, {month: 'short', day: 'numeric'})} />
                    <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={v => `${v}%`} />
                    <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString()} formatter={(value: number) => [`${value}%`, 'Margin']} />
                    <Line type="stepAfter" dataKey="value" stroke="var(--chart-3)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </TabsContent>

              <TabsContent value="stock" className="m-0 h-[400px]">
                <h3 className="font-semibold mb-4">Stock Level</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history.stock_history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} tickFormatter={v => new Date(v).toLocaleDateString(undefined, {month: 'short', day: 'numeric'})} />
                    <YAxis fontSize={12} tickLine={false} axisLine={false} />
                    <Tooltip labelFormatter={v => new Date(v as string).toLocaleDateString()} formatter={(value: number) => [value, 'Units in Stock']} />
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
