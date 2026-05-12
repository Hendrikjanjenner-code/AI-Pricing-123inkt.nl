import { useState } from "react";
import { Link } from "wouter";
import { useListProducts } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, ChevronRight } from "lucide-react";

const STRATEGIE_LABELS: Record<string, string> = {
  SUBSTITUTION_PORTFOLIO: "Substitutieportfolio",
  COMPETITOR_INDEX: "Concurrentie-index",
  MARGIN_OPTIMIZATION: "Margeoptimalisatie",
  STOCK_CLEARANCE: "Voorraadopruiming",
  BASKET_BUILDER: "Winkelmandbouwer",
  VOLUME_DISCOUNT: "Volumekorting",
  REPEAT_PURCHASE: "Herhalingsaankoop",
  LOW_VELOCITY: "Laag volume",
  PRIVATE_LABEL_PUSH: "Huismerk push",
  PORTFOLIO_MARGIN_OPTIMIZATION: "Portfolio margeopt.",
  TRAFFIC_TO_MARGIN_SWITCH: "Traffic → marge",
};

const LIFECYCLE_LABELS: Record<string, string> = {
  active: "Actief",
  end_of_life: "Einde levensduur",
  discontinued: "Stopgezet",
  new: "Nieuw",
};

export default function Producten() {
  const [page, setPage] = useState(1);
  const [zoekterm, setZoekterm] = useState("");
  const [categorie, setCategorie] = useState<string>("all");

  const { data, isLoading } = useListProducts({
    params: {
      page,
      page_size: 50,
      search: zoekterm || null,
      category: categorie !== "all" ? categorie : null,
    }
  });

  const fmtBedrag = (v: number | null | undefined) =>
    v != null ? new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(v) : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Productbeheer</h1>
      </div>

      <div className="flex items-center gap-4 bg-card p-4 border rounded-md">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Zoek op SKU-ID, naam of merk..."
            className="pl-9 bg-background"
            value={zoekterm}
            onChange={e => { setZoekterm(e.target.value); setPage(1); }}
          />
        </div>
        <div className="w-64">
          <Select value={categorie} onValueChange={(v) => { setCategorie(v); setPage(1); }}>
            <SelectTrigger className="bg-background">
              <SelectValue placeholder="Categorie" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle categorieën</SelectItem>
              <SelectItem value="Ink & Toner">Inkt & Toner</SelectItem>
              <SelectItem value="Office Supplies">Kantoorartikelen</SelectItem>
              <SelectItem value="Paper">Papier</SelectItem>
              <SelectItem value="Packaging">Verpakking</SelectItem>
              <SelectItem value="Cleaning">Schoonmaak</SelectItem>
              <SelectItem value="Canteen Supplies">Kantinebenodigdheden</SelectItem>
              <SelectItem value="Electronics">Elektronica</SelectItem>
              <SelectItem value="Furniture">Meubilair</SelectItem>
              <SelectItem value="Printers">Printers</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU-ID</TableHead>
              <TableHead>Naam</TableHead>
              <TableHead>Merk</TableHead>
              <TableHead>Categorie</TableHead>
              <TableHead>Strategie</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Kostprijs</TableHead>
              <TableHead className="text-right">Verkoopprijs</TableHead>
              <TableHead className="text-center">Datakwaliteit</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 10 }).map((__, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : data?.items?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} className="h-32 text-center text-muted-foreground">
                  Geen producten gevonden.
                </TableCell>
              </TableRow>
            ) : data?.items?.map((sku) => (
              <TableRow key={sku.sku_id} className="group cursor-pointer hover:bg-muted/50">
                <TableCell className="font-mono text-xs">{sku.sku_id}</TableCell>
                <TableCell className="font-medium max-w-[200px] truncate" title={sku.product_name}>
                  {sku.product_name}
                </TableCell>
                <TableCell className="text-muted-foreground">{sku.brand}</TableCell>
                <TableCell>{sku.category}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-[10px] font-normal">
                    {STRATEGIE_LABELS[sku.strategy_type || ""] || sku.strategy_type?.replace(/_/g, ' ')}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary" className="text-[10px] font-normal uppercase">
                    {LIFECYCLE_LABELS[sku.lifecycle_status || ""] || sku.lifecycle_status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">{fmtBedrag(sku.cost_price)}</TableCell>
                <TableCell className="text-right tabular-nums font-medium">{fmtBedrag(sku.current_price)}</TableCell>
                <TableCell className="text-center">
                  <div className={`text-sm font-semibold ${(sku.data_quality_score || 0) >= 80 ? 'text-emerald-600' : 'text-amber-600'}`}>
                    {sku.data_quality_score}%
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <Link href={`/producten/${sku.sku_id}`}>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground group-hover:text-foreground">
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div>
            {(data.page - 1) * data.page_size + 1}–{Math.min(data.page * data.page_size, data.total)} van {data.total} producten
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Vorige</Button>
            <Button variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)}>Volgende</Button>
          </div>
        </div>
      )}
    </div>
  );
}
