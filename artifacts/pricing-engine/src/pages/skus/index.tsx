import { useState, useCallback } from "react";
import { Link } from "wouter";
import { useListProducts, ListProductsIdentityStatus } from "@workspace/api-client-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, ChevronRight, Download } from "lucide-react";
import type { Product } from "@workspace/api-client-react";
import SmartFilters, { SmartFilterValues, EMPTY_FILTERS } from "@/components/filters/SmartFilters";
import { GlobalFilterBar } from "@/components/filters/GlobalFilterBar";
import { useGlobalFilters } from "@/hooks/use-global-filters";

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
    f.categorie_naam === null &&
    f.subcategorie_id === null &&
    f.subcategorie_naam === null &&
    f.sub_subcategorie_id === null &&
    f.sub_subcategorie_naam === null &&
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
    a.categorie_naam === b.categorie_naam &&
    a.subcategorie_id === b.subcategorie_id &&
    a.subcategorie_naam === b.subcategorie_naam &&
    a.sub_subcategorie_id === b.sub_subcategorie_id &&
    a.sub_subcategorie_naam === b.sub_subcategorie_naam &&
    a.merken.length === b.merken.length &&
    a.merken.every((m, i) => m === b.merken[i]) &&
    a.merktype === b.merktype &&
    a.bcg_intern === b.bcg_intern &&
    a.bcg_extern === b.bcg_extern &&
    a.actie_nodig === b.actie_nodig
  );
}

/** Gelijk op alles behalve de hiërarchie-ids (die worden asynchroon op naam
 *  opgelost na een deep-link; dat mag geen 'pending changes' opleveren). */
function filtersEqualIgnoringIds(a: SmartFilterValues, b: SmartFilterValues): boolean {
  return filtersEqual(
    { ...a, categorie_id: null, subcategorie_id: null, sub_subcategorie_id: null },
    { ...b, categorie_id: null, subcategorie_id: null, sub_subcategorie_id: null },
  );
}

/** Leest deep-link filters uit de URL-querystring (bv. vanaf een beslissingsdetail):
 *  /producten?category=X&subcategory=Y&merktype=huismerk */
function filtersFromUrl(): SmartFilterValues {
  const qs = new URLSearchParams(window.location.search);
  const category = qs.get("category");
  const subcategory = qs.get("subcategory");
  const merktype = qs.get("merktype");
  if (!category && !subcategory && !merktype) return EMPTY_FILTERS;
  return {
    ...EMPTY_FILTERS,
    categorie_naam: category,
    subcategorie_naam: subcategory,
    merktype: merktype === "huismerk" || merktype === "a_merk" || merktype === "overig" ? merktype : null,
  };
}

function xmlEsc(v: unknown): string {
  return (v == null ? "" : String(v)).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Excel-werkmap (SpreadsheetML) met elke cel expliciet als tekst: voorloopnullen
// blijven behouden en waarden worden nooit als formule uitgevoerd.
function exportIdentiteit(rows: Product[]) {
  const head = ["Technisch ID", "Zakelijke SKU", "EAN", "OEM", "Bron-ID's", "Productnaam", "Merk"];
  const data = rows.map(p => [
    p.sku_id, p.business_sku, p.ean, p.oem_code,
    (p.source_aliases || []).map(a => `${a.source}:${a.code}${a.shop_id != null ? "@" + a.shop_id : ""}`).join(" | "),
    p.product_name, p.brand,
  ]);
  const row = (cells: unknown[]) => `<Row>${cells.map(c => `<Cell><Data ss:Type="String">${xmlEsc(c)}</Data></Cell>`).join("")}</Row>`;
  const xml = `<?xml version="1.0" encoding="UTF-8"?><?mso-application progid="Excel.Sheet"?>` +
    `<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">` +
    `<Styles><Style ss:ID="Default"><NumberFormat ss:Format="@"/></Style></Styles>` +
    `<Worksheet ss:Name="Productidentiteit"><Table>${[head, ...data].map(row).join("")}</Table></Worksheet></Workbook>`;
  const url = URL.createObjectURL(new Blob([xml], { type: "application/vnd.ms-excel" }));
  const a = document.createElement("a");
  a.href = url; a.download = `productidentiteit-${new Date().toISOString().slice(0, 10)}.xls`;
  a.click(); URL.revokeObjectURL(url);
}

export default function Producten() {
  const [page, setPage] = useState(1);

  // Globale filtercontext (hiërarchie + merk + status + zoekterm) — zelfde
  // context als de dashboards, zodat een categoriekeuze ook de productenlijst
  // filtert.
  const globalFilters = useGlobalFilters();
  const hierarchyNodeIds =
    globalFilters.hierarchy.length > 0
      ? globalFilters.hierarchy.map((n) => n.id).join(",")
      : undefined;
  const globalBrands =
    globalFilters.brands.length > 0 ? globalFilters.brands.join(",") : undefined;
  const globalStatuses =
    globalFilters.statuses.length > 0 ? globalFilters.statuses.join(",") : undefined;
  const globalSkuQuery =
    globalFilters.skuQuery.trim() !== "" ? globalFilters.skuQuery.trim() : undefined;

  // Deep-link filters uit de URL (eenmalig bij mount gelezen)
  const [initialFilters] = useState<SmartFilterValues>(() => filtersFromUrl());

  // resetKey: incrementing counter passed to SmartFilters to reset its internal UI
  const [resetKey, setResetKey] = useState(0);

  // Staged: what the user is composing but hasn't applied yet
  const [stagedZoekterm, setStagedZoekterm] = useState("");
  const [stagedFilters, setStagedFilters] = useState<SmartFilterValues>(initialFilters);

  // Applied: what actually drives the API call and client-side filter
  const [zoekterm, setZoekterm] = useState("");
  const [identityStatus, setIdentityStatus] = useState<ListProductsIdentityStatus>(ListProductsIdentityStatus.all);
  const [appliedFilters, setAppliedFilters] = useState<SmartFilterValues>(initialFilters);

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
    hierarchy_node_ids: hierarchyNodeIds,
    brands: globalBrands,
    statuses: globalStatuses,
    sku_query: globalSkuQuery,
    page,
    page_size: 100,
    search: zoekterm || undefined,
    identity_status: identityStatus === ListProductsIdentityStatus.all ? undefined : identityStatus,
    category: appliedFilters.categorie_naam || undefined,
    subcategory: appliedFilters.subcategorie_naam || undefined,
    is_private_label:
      appliedFilters.merktype === "huismerk" ? true : undefined,
  });

  const handleFiltersChange = useCallback((f: SmartFilterValues) => {
    setStagedFilters(f);
    // Na een deep-link lost SmartFilters de hiërarchie-ids asynchroon op naam
    // op; neem die ids dan ook direct over in de toegepaste filters zodat er
    // geen onterecht 'pending changes' ontstaat.
    setAppliedFilters(prev => (filtersEqualIgnoringIds(prev, f) ? f : prev));
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
      const skuSubSub = (sku as unknown as Record<string, unknown>).sub_subcategory as string | null | undefined;
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
      const skuBcgInt = (sku as unknown as Record<string, unknown>).bcg_intern as string | null | undefined;
      if (skuBcgInt !== af.bcg_intern) return false;
    }

    // BCG extern (field may be absent)
    if (af.bcg_extern) {
      const skuBcgExt = (sku as unknown as Record<string, unknown>).bcg_extern as string | null | undefined;
      if (skuBcgExt !== af.bcg_extern) return false;
    }

    // Actie nodig (field may be absent)
    if (af.actie_nodig !== null) {
      const skuActie = (sku as unknown as Record<string, unknown>).actie_nodig as boolean | null | undefined;
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

      {/* Globale filtercontext (hiërarchie + merk), gedeeld met de dashboards */}
      <GlobalFilterBar />

      {/* Zoekbalk + Zoeken-knop + Wis alles */}
      <div className="flex items-center gap-3 bg-card p-3 border rounded-lg">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Zoek op technisch ID, zakelijke SKU, EAN, OEM, naam of merk..."
            className="pl-9 bg-background"
            value={stagedZoekterm}
            onChange={e => setStagedZoekterm(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") applySearch(); }}
          />
        </div>
        <Select value={identityStatus} onValueChange={v => { setIdentityStatus(v as ListProductsIdentityStatus); setPage(1); }}>
          <SelectTrigger className="w-[210px] shrink-0 bg-background" data-testid="select-identity-status"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ListProductsIdentityStatus.all}>Alle identiteiten</SelectItem>
            <SelectItem value={ListProductsIdentityStatus.with_business_sku}>Met zakelijke SKU</SelectItem>
            <SelectItem value={ListProductsIdentityStatus.without_business_sku}>Zonder zakelijke SKU</SelectItem>
            <SelectItem value={ListProductsIdentityStatus.with_ean}>Met EAN</SelectItem>
            <SelectItem value={ListProductsIdentityStatus.without_ean}>Zonder EAN</SelectItem>
            <SelectItem value={ListProductsIdentityStatus.with_oem}>Met OEM</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" className="shrink-0" data-testid="button-export-identity" disabled={items.length === 0} onClick={() => exportIdentiteit(items)} title="Excel-werkmap met identiteitsvelden als tekst (voorloopnullen blijven behouden) voor de getoonde pagina">
          <Download className="h-4 w-4 mr-2" />Identiteit (Excel, tekst)
        </Button>
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

      {/* Actieve filters (o.a. via deep-link vanaf een beslissing) */}
      {!isEmptyFilters(appliedFilters) && (
        <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="active-filter-chips">
          <span className="text-muted-foreground text-xs">Actieve filters:</span>
          {appliedFilters.categorie_naam && <Badge variant="secondary">Categorie: {appliedFilters.categorie_naam}</Badge>}
          {appliedFilters.subcategorie_naam && <Badge variant="secondary">Subcategorie: {appliedFilters.subcategorie_naam}</Badge>}
          {appliedFilters.sub_subcategorie_naam && <Badge variant="secondary">Sub-subcategorie: {appliedFilters.sub_subcategorie_naam}</Badge>}
          {appliedFilters.merktype && <Badge variant="secondary">Merktype: {appliedFilters.merktype === "huismerk" ? "Huismerk" : appliedFilters.merktype === "a_merk" ? "A-merk" : "Overig"}</Badge>}
          {appliedFilters.merken.length > 0 && <Badge variant="secondary">Merken: {appliedFilters.merken.join(", ")}</Badge>}
        </div>
      )}

      {/* Slimme filters — resetKey lets the parent reset filter UI; onClearAll wires panel clear to parent */}
      <SmartFilters
        onChange={handleFiltersChange}
        initialValues={initialFilters}
        resetKey={resetKey}
        onClearAll={clearAll}
      />

      {/* Tabel */}
      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead title="Stabiele interne sleutel; geen zakelijke code">Technisch ID</TableHead>
              <TableHead title="DRS productcode / artikelcode">Zakelijke SKU</TableHead>
              <TableHead>EAN</TableHead>
              <TableHead>OEM</TableHead>
              <TableHead>Bron-ID's</TableHead>
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
                  {Array.from({ length: 15 }).map((__, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={15} className="h-32 text-center text-muted-foreground">
                  Geen producten gevonden voor de geselecteerde filters.
                </TableCell>
              </TableRow>
            ) : items.map((sku) => (
              <TableRow key={sku.sku_id} className="group cursor-pointer hover:bg-muted/50">
                <TableCell className="font-mono text-[11px] text-muted-foreground" data-testid={`text-technical-id-${sku.sku_id}`}>{sku.sku_id}</TableCell>
                <TableCell className="font-mono text-xs font-medium" data-testid={`text-business-sku-${sku.sku_id}`}>{sku.business_sku || <span className="text-muted-foreground/60 font-sans">niet gekoppeld</span>}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{sku.ean || "—"}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{sku.oem_code || "—"}</TableCell>
                <TableCell className="text-xs text-muted-foreground max-w-[180px]">
                  {sku.source_aliases?.length ? sku.source_aliases.slice(0, 2).map((a, i) => (
                    <div key={i} className="truncate"><span className="uppercase text-[10px]">{a.source}</span> <span className="font-mono">{a.code}</span>{a.shop_id != null && <span className="text-[10px]"> #{a.shop_id}</span>}</div>
                  )) : "—"}
                  {(sku.source_aliases?.length ?? 0) > 2 && <div className="text-[10px]">+{(sku.source_aliases?.length ?? 0) - 2}</div>}
                </TableCell>
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
