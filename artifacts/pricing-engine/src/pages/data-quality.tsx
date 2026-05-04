import { useGetDataQuality } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, CheckCircle2, ShieldAlert, FileWarning, Database } from "lucide-react";

export default function DataQuality() {
  const { data, isLoading } = useGetDataQuality();

  if (isLoading) return <div className="p-8"><Skeleton className="h-[500px] w-full" /></div>;
  if (!data) return <div>No data quality report available.</div>;

  const scoreColor = data.overall_score >= 90 ? 'text-emerald-500' : data.overall_score >= 70 ? 'text-amber-500' : 'text-destructive';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Data Quality Monitor</h1>
          <p className="text-muted-foreground mt-1">Ensure model inputs are healthy and complete.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Card className="col-span-1 border-primary/20 bg-primary/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Overall Data Health</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center justify-center py-6">
              <div className={`text-6xl font-bold ${scoreColor}`}>{data.overall_score}</div>
              <div className="text-sm text-muted-foreground mt-2">/ 100 Score</div>
            </div>
            <div className="mt-4 flex justify-between text-sm">
              <span className="text-muted-foreground">Total SKUs</span>
              <span className="font-medium">{data.total_skus.toLocaleString()}</span>
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-1 md:col-span-3">
          <CardHeader>
            <CardTitle>Issue Summary</CardTitle>
            <CardDescription>Breakdown by severity and type</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-8">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="flex items-center text-sm font-medium"><ShieldAlert className="w-4 h-4 text-destructive mr-2"/> Critical Errors</span>
                  <Badge variant="destructive">{Object.entries(data.summary).reduce((acc, [k, v]) => k.includes('error') ? acc + v : acc, 0)}</Badge>
                </div>
                <div className="text-xs text-muted-foreground pl-6">Missing cost prices, missing strategy</div>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="flex items-center text-sm font-medium"><AlertCircle className="w-4 h-4 text-amber-500 mr-2"/> Warnings</span>
                  <Badge variant="outline" className="text-amber-600 border-amber-200 bg-amber-50">{Object.entries(data.summary).reduce((acc, [k, v]) => k.includes('warning') ? acc + v : acc, 0)}</Badge>
                </div>
                <div className="text-xs text-muted-foreground pl-6">Stale competitor prices, low stock</div>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="flex items-center text-sm font-medium"><FileWarning className="w-4 h-4 text-blue-500 mr-2"/> Info</span>
                  <Badge variant="secondary">{Object.entries(data.summary).reduce((acc, [k, v]) => k.includes('info') ? acc + v : acc, 0)}</Badge>
                </div>
                <div className="text-xs text-muted-foreground pl-6">Missing optional attributes</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Detailed Issues Log</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="grid grid-cols-12 border-b bg-muted/50 p-3 text-sm font-medium text-muted-foreground">
            <div className="col-span-2">Severity</div>
            <div className="col-span-3">Issue Type</div>
            <div className="col-span-5">Message</div>
            <div className="col-span-2 text-right">Affected SKUs</div>
          </div>
          <div className="divide-y max-h-[500px] overflow-y-auto">
            {data.issues.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground flex flex-col items-center">
                <CheckCircle2 className="w-8 h-8 text-emerald-500 mb-2" />
                No data quality issues found!
              </div>
            ) : data.issues.map((issue, i) => (
              <div key={i} className="grid grid-cols-12 items-center p-3 text-sm">
                <div className="col-span-2">
                  {issue.severity === 'error' && <Badge variant="destructive" className="rounded-sm">Error</Badge>}
                  {issue.severity === 'warning' && <Badge variant="outline" className="text-amber-600 border-amber-200 bg-amber-50 rounded-sm">Warning</Badge>}
                  {issue.severity === 'info' && <Badge variant="secondary" className="rounded-sm">Info</Badge>}
                </div>
                <div className="col-span-3 font-mono text-xs">{issue.issue_type}</div>
                <div className="col-span-5">{issue.message}</div>
                <div className="col-span-2 text-right font-medium">{issue.affected_count?.toLocaleString() || '-'}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
