import { useState } from "react";
import { useExportRecommendations } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { format } from "date-fns";
import { Download, ExternalLink, CheckCircle } from "lucide-react";

export default function Export() {
  const [date, setDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const { toast } = useToast();
  const exportMut = useExportRecommendations();
  const [result, setResult] = useState<{url: string, count: number, filename: string} | null>(null);

  const handleExport = async () => {
    try {
      const res = await exportMut.mutateAsync({ params: { date } });
      setResult({
        url: res.download_url,
        count: res.exported_count,
        filename: res.filename
      });
      toast({ title: "Export generated successfully" });
    } catch (err) {
      toast({ title: "Export failed", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Export to PriceShape</h1>
        <p className="text-muted-foreground mt-1">Generate the final pricing payload for downstream systems.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Generate Payload</CardTitle>
          <CardDescription>Exports all 'approved' and 'overridden' recommendations for a specific date.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2 max-w-sm">
            <Label htmlFor="date">Target Date</Label>
            <Input 
              id="date" 
              type="date" 
              value={date} 
              onChange={(e) => setDate(e.target.value)} 
            />
          </div>

          <Button onClick={handleExport} disabled={exportMut.isPending}>
            {exportMut.isPending ? "Generating..." : "Generate Export"}
          </Button>

          {result && (
            <div className="mt-8 p-6 bg-emerald-50 border border-emerald-200 rounded-md">
              <div className="flex items-center gap-3 text-emerald-800 font-medium mb-2">
                <CheckCircle className="w-5 h-5" /> Export Ready
              </div>
              <p className="text-emerald-700 text-sm mb-4">
                Successfully processed {result.count} approved pricing recommendations.
              </p>
              <div className="flex gap-4">
                <Button className="bg-emerald-600 hover:bg-emerald-700 text-white" asChild>
                  <a href={result.url} download={result.filename}>
                    <Download className="w-4 h-4 mr-2" /> Download CSV
                  </a>
                </Button>
                <Button variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-100">
                  <ExternalLink className="w-4 h-4 mr-2" /> Push to PriceShape API
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
