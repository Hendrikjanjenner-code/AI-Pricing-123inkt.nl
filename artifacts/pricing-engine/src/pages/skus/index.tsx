import { useState, useCallback } from "react";
import { Link } from "wouter";
import { useListProducts } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, ChevronRight } from "lucide-react";
import SmartFilters, { SmartFilterValues, EMPTY_FILTERS } from "@/components/filters/SmartFilters";

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

function isEmptyFilters(f: SmartFilterValues): boolean {
  return (
    f.categorie_id === null &&
    f.subcategorie_id === null &&
    f.sub_subcategorie_id === null &&
    f.merken.length === 0 &&
    f.merktype === null &&
    f.bcg_intern === null &&
    f.bcg_extern === null &&
    f.actie_nodig === null
  );
}

function filtersEqual(a: SmartFilterValues, b: SmartFilterValues): boolean {
  return (
    a.categorie_id === b.categorie_id &&
    a.subcategorie_id === b.subcategorie_id &&
    a.sub_subcategorie_id === b.sub_subcategorie_id &&
    a.merken.length === b.merken.length &&
    a.merken.every((m, i) => m === b.merken[i]) &&
    a.merktype === b.merktype &&
    a.bcg_intern === b.bcg_intern &&
    a.bcg_extern === b.bcg_extern &&
    a.actie_nodig === b.actie_nodig
  );
}

export default function Producten() {
  const [page, setPage] = useState(1);

  // resetKey: incrementing counter passed to SmartFilters to reset its internal UI
  const [resetKey, setResetKey] = useState(0);

  // Staged: what the user is composing but hasn't applied yet
  const [stagedZoekterm, setStagedZoekterm] = useState("");
  const [stagedFilters, setStagedFilters] = useState<SmartFilterValues>(EMPTY_FILTERS);

  // Applied: what actually drives the API call and client-side filter
  const [zoekterm, setZoekterm] = useState("");
  const [appliedFilters, setAppliedFilters] = useState<SmartFilterValues>(EMPTY_FILTERS);

  const hasPendingChanges =
    stagedZoekterm !== zoekterm || !filtersEqual(stagedFilters, appliedFilters);

  const hasApplied = zoekterm !== "" || !isEmptyFilters(appliedFilters);
  const hasAnything = hasPendingChanges || hasApplied;

  const applySearch = useCallback(() => {
    setZoekterm(stagedZoekterm);
    setAppliedFilters(stagedFilters);
    setPage(1);
  }, [stagedZoekterm, stagedFilters]);

  const clearAll = useCallback(() => {
    setStagedZoekterm("");
    setStagedFilters(EMPTY_FILTERS);
    setZoekterm("");
    setAppliedFilters(EMPTY_FILTERS);
    setPage(1);
    setResetKey(k => k + 1);
  }, []);

  const { data, isLoading } = useListProducts({
    page,
    page_size: 100,
    search: zoekterm || undefined,
    category: appliedFilters.categorie_naam || undefined,
  });

  const handleFiltersChange = useCallback((f: SmartFilterValues) => {
    setStagedFilters(f);
  }, []);

  // Client-side filtering on all 8 dimensions using applied (not staged) filters
  const items = (data?.items || []).filter(sku => {
    const af = appliedFilters;

    // Categorie — also enforced server-side via API category param, but client-side as safety net
    if (af.categorie_naam && sku.category !== af.categorie_naam) return false;

    // Subcategorie
    if (af.subcategorie_naam && sku.subcategory !== af.subcategorie_naam) return false;

    // Sub-subcategorie (field may be absent on older records)
    if (af.sub_subcategorie_naam) {
      const skuSubSub = (sku as Record<string, unknown>).sub_subcategory as string | null | undefined;
      if (skuSubSub !== af.sub_subcategorie_naam) return false;
    }

    // Merk (multi-select)
    if (af.merken.length > 0 && !af.merken.includes(sku.brand || "")) return false;

    // Merktype
    if (af.merktype === "huismerk" && !sku.is_private_label) return false;
    if (af.merktype === "a_merk" && !sku.is_a_brand) return false;
    if (af.merktype === "overig" && (sku.is_private_label || sku.is_a_brand)) return false;

    // BCG intern (field may be absent)
    if (af.bcg_intern) {
      const skuBcgInt = (sku as Record<string, unknown>).bcg_intern as string | null | undefined;
      if (skuBcgInt !== af.bcg_intern) return false;
    }

    // BCG extern (field may be absent)
    if (af.bcg_extern) {
      const skuBcgExt = (sku as Record<string, unknown>).bcg_extern as string | null | undefined;
      if (skuBcgExt !== af.bcg_extern) return false;
    }

    // Actie nodig (field may be absent)
    if (af.actie_nodig !== null) {
      const skuActie = (sku as Record<string, unknown>).actie_nodig as boolean | null | undefined;
      if (Boolean(skuActie) !== af.actie_nodig) return false;
    }

    return true;
  });

  const fmtBedrag = (v: number | null | undefined) =>
    v != null ? new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(v) : '-';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Productbeheer</h1>
        <div className="text-sm text-muted-foreground">
          {isLoading ? "…" : `${items.length} producten`}
        </div>
      </div>

      {/* Zoekbalk + Zoeken-knop + Wis alles */}
      <div className="flex items-center gap-3 bg-card p-3 border rounded-lg">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Zoek op SKU-ID, naam of merk..."
            className="pl-9 bg-background"
            value={stagedZoekterm}
            onChange={e => setStagedZoekterm(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") applySearch(); }}
          />
        </div>
        <Button
          onClick={applySearch}
          variant={hasPendingChanges ? "default" : "outline"}
          className="shrink-0"
        >
          <Search className="h-4 w-4 mr-2" />
          Zoeken
        </Button>
        {hasAnything && (
          <Button variant="ghost" size="sm" className="shrink-0 text-muted-foreground" onClick={clearAll}>
            Wis alles
          </Button>
        )}
      </div>

      {/* Slimme filters — resetKey lets the parent reset filter UI; onClearAll wires panel clear to parent */}
      <SmartFilters
        onChange={handleFiltersChange}
        resetKey={resetKey}
        onClearAll={clearAll}
      />

      {/* Tabel */}
      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU-ID</TableHead>
              <TableHead>Naam</TableHead>
              <TableHead>Merk</TableHead>
              <TableHead>Categorie</TableHead>
              <TableHead>Subcategorie</TableHead>
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
                  {Array.from({ length: 11 }).map((__, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={11} className="h-32 text-center text-muted-foreground">
                  Geen producten gevonden voor de geselecteerde filters.
                </TableCell>
              </TableRow>
            ) : items.map((sku) => (
              <TableRow key={sku.sku_id} className="group cursor-pointer hover:bg-muted/50">
                <TableCell className="font-mono text-xs">{sku.sku_id}</TableCell>
                <TableCell className="font-medium max-w-[200px] truncate" title={sku.product_name}>
                  {sku.product_name}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  <div className="flex items-center gap-1">
                    {sku.brand}
                    {sku.is_private_label && <Badge variant="secondary" className="text-[9px] px-1 py-0">HM</Badge>}
                    {sku.is_a_brand && <Badge className="text-[9px] px-1 py-0 bg-blue-100 text-blue-700">A</Badge>}
                  </div>
                </TableCell>
                <TableCell>{sku.category}</TableCell>
                <TableCell className="text-muted-foreground text-xs">{sku.subcategory || "—"}</TableCell>
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
