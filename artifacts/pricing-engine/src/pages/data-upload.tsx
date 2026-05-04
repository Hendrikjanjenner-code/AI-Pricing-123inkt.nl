import { useState } from "react";
import { useListUploads } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Upload, FileSpreadsheet, CheckCircle2, AlertCircle, Clock, Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

export default function DataUpload() {
  const { data: uploads, isLoading } = useListUploads();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [uploading, setUploading] = useState<Record<string, boolean>>({});

  const uploadTypes = [
    { id: "products", title: "Product Catalog", desc: "SKUs, brands, categories, lifecycle status", endpoint: "/api/upload/products" },
    { id: "sales", title: "Sales Data", desc: "Historical volume, units sold, revenue", endpoint: "/api/upload/sales" },
    { id: "prices", title: "Internal Prices", desc: "Cost prices, current prices, min/max guards", endpoint: "/api/upload/prices" },
    { id: "competitor_prices", title: "Competitor Prices", desc: "Daily scraped competitor pricing", endpoint: "/api/upload/competitor-prices" },
    { id: "inventory", title: "Inventory", desc: "Current stock levels", endpoint: "/api/upload/inventory" },
    { id: "substitutions", title: "Substitution Pairs", desc: "A-brand to Private Label mappings", endpoint: "/api/upload/substitutions" },
  ];

  const handleFileChange = async (typeId: string, endpoint: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(prev => ({ ...prev, [typeId]: true }));

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${localStorage.getItem("auth_token")}`
        },
        body: formData
      });

      if (!response.ok) {
        throw new Error("Upload failed");
      }

      toast({ title: "File uploaded successfully", description: "Processing started." });
      queryClient.invalidateQueries({ queryKey: ["/api/uploads"] });
    } catch (err) {
      toast({ title: "Upload failed", variant: "destructive" });
    } finally {
      setUploading(prev => ({ ...prev, [typeId]: false }));
      if (e.target) e.target.value = '';
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Data Integration</h1>
        <p className="text-muted-foreground mt-1">Upload CSV datasets to feed the pricing model.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {uploadTypes.map((type) => (
          <Card key={type.id}>
            <CardHeader className="pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <FileSpreadsheet className="h-5 w-5 text-primary" />
                {type.title}
              </CardTitle>
              <CardDescription>{type.desc}</CardDescription>
            </CardHeader>
            <CardFooter>
              <div className="relative w-full">
                <Input 
                  type="file" 
                  accept=".csv" 
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" 
                  onChange={(e) => handleFileChange(type.id, type.endpoint, e)}
                  disabled={uploading[type.id]}
                />
                <Button variant="outline" className="w-full" disabled={uploading[type.id]}>
                  {uploading[type.id] ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Uploading...</>
                  ) : (
                    <><Upload className="mr-2 h-4 w-4" /> Select CSV File</>
                  )}
                </Button>
              </div>
            </CardFooter>
          </Card>
        ))}
      </div>

      <div>
        <h2 className="text-lg font-bold mb-4">Recent Upload Jobs</h2>
        <div className="border rounded-md bg-card">
          <div className="grid grid-cols-6 border-b bg-muted/50 p-3 text-sm font-medium text-muted-foreground">
            <div className="col-span-2">Filename</div>
            <div>Type</div>
            <div>Status</div>
            <div className="text-right">Processed / Failed</div>
            <div className="text-right">Date</div>
          </div>
          <div className="divide-y">
            {isLoading ? (
              <div className="p-8 text-center text-muted-foreground">Loading...</div>
            ) : uploads?.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">No recent uploads.</div>
            ) : uploads?.map((job) => (
              <div key={job.id} className="grid grid-cols-6 items-center p-3 text-sm">
                <div className="col-span-2 font-medium truncate pr-4">{job.filename}</div>
                <div className="capitalize">{job.upload_type.replace(/_/g, ' ')}</div>
                <div>
                  {job.status === 'completed' && <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200">Completed</Badge>}
                  {job.status === 'processing' && <Badge variant="outline" className="bg-blue-50 text-blue-600 border-blue-200">Processing</Badge>}
                  {job.status === 'failed' && <Badge variant="destructive">Failed</Badge>}
                  {job.status === 'pending' && <Badge variant="secondary">Pending</Badge>}
                </div>
                <div className="text-right tabular-nums">
                  <span className="text-emerald-600">{job.rows_processed}</span> / <span className={job.rows_failed > 0 ? "text-destructive" : ""}>{job.rows_failed}</span>
                </div>
                <div className="text-right text-muted-foreground tabular-nums">
                  {new Date(job.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
