import { useGetDashboardSummary, useGetMarginByCategory, useGetRecsByStrategy, useGetConfidenceDistribution, useGetPriceChangeDistribution } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line } from "recharts";
import { ArrowUpRight, ArrowDownRight, AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

export default function Dashboard() {
  const { data: summary, isLoading: loadingSummary } = useGetDashboardSummary();
  const { data: marginData } = useGetMarginByCategory();
  const { data: recsData } = useGetRecsByStrategy();
  const { data: confData } = useGetConfidenceDistribution();
  const { data: priceData } = useGetPriceChangeDistribution();

  const formatCurrency = (val: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(val);
  const formatNumber = (val: number) => new Intl.NumberFormat('en-US').format(val);

  const COLORS = ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))'];

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">Morning Briefing</h1>

      {loadingSummary ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-[120px] w-full" />)}
        </div>
      ) : summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Est. Margin Uplift</CardTitle>
              <ArrowUpRight className="h-4 w-4 text-emerald-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-emerald-600">{formatCurrency(summary.estimated_margin_impact)}</div>
              <p className="text-xs text-muted-foreground mt-1">Based on pending recs</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Pending Recs</CardTitle>
              <CheckCircle2 className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatNumber(summary.pending_count)}</div>
              <p className="text-xs text-muted-foreground mt-1">Out of {summary.total_recommendations} total</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Avg Confidence</CardTitle>
              <ActivityIcon className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{(summary.avg_confidence_score * 100).toFixed(1)}%</div>
              <p className="text-xs text-muted-foreground mt-1">Model health {summary.data_quality_score > 80 ? 'optimal' : 'degraded'}</p>
            </CardContent>
          </Card>
          <Card className="border-destructive/50">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-destructive">Safety Warnings</CardTitle>
              <ShieldAlert className="h-4 w-4 text-destructive" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-destructive">{formatNumber(summary.safety_warnings_count)}</div>
              <p className="text-xs text-muted-foreground mt-1">Require manual review</p>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Margin Uplift by Category</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {marginData ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={marginData}>
                  <XAxis dataKey="category" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v) => `€${v}`} />
                  <Tooltip formatter={(value: number) => [`€${value}`, 'Margin Uplift']} cursor={{fill: 'var(--muted)'}} />
                  <Bar dataKey="margin_uplift" fill="var(--primary)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Skeleton className="w-full h-full" />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recommendations by Strategy</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {recsData ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={recsData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="count"
                    nameKey="strategy_type"
                  >
                    {recsData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : <Skeleton className="w-full h-full" />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Price Change Distribution</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {priceData ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={priceData}>
                  <XAxis dataKey="bucket" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{fill: 'var(--muted)'}} />
                  <Bar dataKey="count" fill="var(--chart-4)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Skeleton className="w-full h-full" />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Model Confidence</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {confData ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={confData}>
                  <XAxis dataKey="bucket" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="count" stroke="var(--chart-2)" strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : <Skeleton className="w-full h-full" />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ActivityIcon(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}
