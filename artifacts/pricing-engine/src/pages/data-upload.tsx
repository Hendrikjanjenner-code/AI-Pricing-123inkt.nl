import { useState } from "react";
import { useListUploads } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { Upload, FileSpreadsheet, Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

const UPLOAD_TYPEN = [
  { id: "products", titel: "Productcatalogus", beschr: "SKU's, merken, categorieën, levenscyclusstatus", endpoint: "/api/upload/products" },
  { id: "sales", titel: "Verkoopdata", beschr: "Historisch volume, verkochte eenheden, omzet", endpoint: "/api/upload/sales" },
  { id: "prices", titel: "Interne prijzen", beschr: "Kostprijzen, verkoopprijzen, min/max-grenzen", endpoint: "/api/upload/prices" },
  { id: "competitor_prices", titel: "Concurrentenprijzen", beschr: "Dagelijks gescrapte concurrentenprijzen", endpoint: "/api/upload/competitor-prices" },
  { id: "inventory", titel: "Voorraad", beschr: "Actuele voorraadniveaus per SKU", endpoint: "/api/upload/inventory" },
  { id: "substitutions", titel: "Substitutieparen", beschr: "A-merk naar huismerk koppelingen", endpoint: "/api/upload/substitutions" },
];

const STATUS_LABELS: Record<string, string> = {
  completed: "Voltooid",
  processing: "Verwerking",
  failed: "Mislukt",
  pending: "In wachtrij",
};

export default function Gegevensintegratie() {
  const { data: uploads, isLoading } = useListUploads();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState<Record<string, boolean>>({});

  const handleBestand = async (typeId: string, endpoint: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const bestand = e.target.files?.[0];
    if (!bestand) return;
    setUploading(prev => ({ ...prev, [typeId]: true }));
    const formData = new FormData();
    formData.append("file", bestand);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Authorization": `Bearer ${localStorage.getItem("auth_token")}` },
        body: formData
      });
      if (!response.ok) throw new Error("Upload mislukt");
      toast({ title: "Bestand geüpload", description: "Verwerking gestart." });
      queryClient.invalidateQueries({ queryKey: ["/api/uploads"] });
    } catch {
      toast({ title: "Upload mislukt", variant: "destructive" });
    } finally {
      setUploading(prev => ({ ...prev, [typeId]: false }));
      if (e.target) e.target.value = '';
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Gegevensintegratie</h1>
        <p className="text-muted-foreground mt-1">Upload CSV-bestanden om het prijsmodel te voeden.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {UPLOAD_TYPEN.map((type) => (
          <Card key={type.id}>
            <CardHeader className="pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <FileSpreadsheet className="h-5 w-5 text-primary" />
                {type.titel}
              </CardTitle>
              <CardDescription>{type.beschr}</CardDescription>
            </CardHeader>
            <CardFooter>
              <div className="relative w-full">
                <Input
                  type="file"
                  accept=".csv"
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  onChange={(e) => handleBestand(type.id, type.endpoint, e)}
                  disabled={uploading[type.id]}
                />
                <Button variant="outline" className="w-full" disabled={uploading[type.id]}>
                  {uploading[type.id] ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Uploaden...</>
                  ) : (
                    <><Upload className="mr-2 h-4 w-4" /> CSV-bestand kiezen</>
                  )}
                </Button>
              </div>
            </CardFooter>
          </Card>
        ))}
      </div>

      <div>
        <h2 className="text-lg font-bold mb-4">Recente importtaken</h2>
        <div className="border rounded-md bg-card">
          <div className="grid grid-cols-6 border-b bg-muted/50 p-3 text-sm font-medium text-muted-foreground">
            <div className="col-span-2">Bestandsnaam</div>
            <div>Type</div>
            <div>Status</div>
            <div className="text-right">Verwerkt / Mislukt</div>
            <div className="text-right">Datum</div>
          </div>
          <div className="divide-y">
            {isLoading ? (
              <div className="p-8 text-center text-muted-foreground">Laden...</div>
            ) : uploads?.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">Geen recente uploads.</div>
            ) : uploads?.map((job) => (
              <div key={job.id} className="grid grid-cols-6 items-center p-3 text-sm">
                <div className="col-span-2 font-medium truncate pr-4">{job.filename}</div>
                <div className="capitalize text-muted-foreground">{job.upload_type?.replace(/_/g, ' ')}</div>
                <div>
                  {job.status === 'completed' && <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200">Voltooid</Badge>}
                  {job.status === 'processing' && <Badge variant="outline" className="bg-blue-50 text-blue-600 border-blue-200">Verwerking</Badge>}
                  {job.status === 'failed' && <Badge variant="destructive">Mislukt</Badge>}
                  {job.status === 'pending' && <Badge variant="secondary">In wachtrij</Badge>}
                </div>
                <div className="text-right tabular-nums">
                  <span className="text-emerald-600">{job.rows_processed}</span> / <span className={job.rows_failed > 0 ? "text-destructive" : ""}>{job.rows_failed}</span>
                </div>
                <div className="text-right text-muted-foreground tabular-nums">
                  {new Date(job.created_at).toLocaleString('nl-NL')}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
