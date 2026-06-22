import { useState } from "react";
import { useExportRecommendations } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { format } from "date-fns";
import { Download, ExternalLink, CheckCircle } from "lucide-react";

export default function Prijsexport() {
  const [datum, setDatum] = useState(format(new Date(), "yyyy-MM-dd"));
  const { toast } = useToast();
  const exportMut = useExportRecommendations();
  const [resultaat, setResultaat] = useState<{url: string, count: number, filename: string} | null>(null);

  const handleExport = async () => {
    try {
      const res = await exportMut.mutateAsync({ params: { date: datum } });
      setResultaat({ url: res.download_url, count: res.exported_count, filename: res.filename });
      toast({ title: "Export succesvol aangemaakt" });
    } catch {
      toast({ title: "Export mislukt", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Prijsexport</h1>
        <p className="text-muted-foreground mt-1">Genereer de definitieve prijspayload voor downstream systemen.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Payload aanmaken</CardTitle>
          <CardDescription>Exporteert alle 'goedgekeurde' en 'overschreven' adviezen voor een specifieke datum.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2 max-w-sm">
            <Label htmlFor="datum">Doeldatum</Label>
            <Input id="datum" type="date" value={datum} onChange={(e) => setDatum(e.target.value)} />
          </div>

          <Button onClick={handleExport} disabled={exportMut.isPending}>
            {exportMut.isPending ? "Aanmaken..." : "Export genereren"}
          </Button>

          {resultaat && (
            <div className="mt-8 p-6 bg-emerald-50 border border-emerald-200 rounded-md">
              <div className="flex items-center gap-3 text-emerald-800 font-medium mb-2">
                <CheckCircle className="w-5 h-5" /> Export gereed
              </div>
              <p className="text-emerald-700 text-sm mb-4">
                {resultaat.count} goedgekeurde prijsadviezen succesvol verwerkt.
              </p>
              <div className="flex gap-4">
                <Button className="bg-emerald-600 hover:bg-emerald-700 text-white" asChild>
                  <a href={resultaat.url} download={resultaat.filename}>
                    <Download className="w-4 h-4 mr-2" /> CSV downloaden
                  </a>
                </Button>
                <Button variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-100">
                  <ExternalLink className="w-4 h-4 mr-2" /> Doorsturen naar interne prijsmodule
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
