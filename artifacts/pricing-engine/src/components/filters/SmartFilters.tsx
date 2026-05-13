/**
 * SmartFilters — dynamische trapsgewijze filtercomponent
 * 8 filterdimensies: categorie → subcategorie → sub-subcategorie → merk →
 *                    merktype → BCG intern → BCG extern → actie nodig
 *
 * Database-driven, searchable, cascaderend en multi-select.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { Check, ChevronsUpDown, X, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const getToken = () => localStorage.getItem("auth_token") || "";

// ── Types ────────────────────────────────────────────────────────────────────

interface HierarchyNode {
  category_id: number;
  category_name: string;
  parent_category_id: number | null;
  category_level: number;
}

interface FilterOptions {
  merken: string[];
  bcg_intern: string[];
  bcg_extern: string[];
  merktype_opties: { value: string; label: string }[];
  actie_nodig_opties: { value: string; label: string }[];
}

export interface SmartFilterValues {
  categorie_id: number | null;
  subcategorie_id: number | null;
  sub_subcategorie_id: number | null;
  merken: string[];
  merktype: string | null;          // "huismerk" | "a_merk" | "overig" | null
  bcg_intern: string | null;
  bcg_extern: string | null;
  actie_nodig: boolean | null;
}

export const EMPTY_FILTERS: SmartFilterValues = {
  categorie_id: null,
  subcategorie_id: null,
  sub_subcategorie_id: null,
  merken: [],
  merktype: null,
  bcg_intern: null,
  bcg_extern: null,
  actie_nodig: null,
};

interface SmartFiltersProps {
  onChange: (filters: SmartFilterValues) => void;
  className?: string;
}

// ── Multi-select combobox ────────────────────────────────────────────────────

function MultiCombobox({
  label,
  placeholder,
  options,
  selected,
  onToggle,
  disabled = false,
}: {
  label: string;
  placeholder: string;
  options: { value: string; label: string }[];
  selected: string[];
  onToggle: (value: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</span>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className={cn(
              "w-full justify-between bg-background font-normal h-9",
              selected.length > 0 && "border-primary/50"
            )}
          >
            {selected.length === 0 ? (
              <span className="text-muted-foreground text-sm">{placeholder}</span>
            ) : (
              <div className="flex items-center gap-1 overflow-hidden">
                {selected.slice(0, 2).map(v => (
                  <Badge key={v} variant="secondary" className="text-[10px] px-1 py-0 max-w-[80px] truncate">
                    {options.find(o => o.value === v)?.label || v}
                  </Badge>
                ))}
                {selected.length > 2 && (
                  <Badge variant="secondary" className="text-[10px] px-1 py-0">+{selected.length - 2}</Badge>
                )}
              </div>
            )}
            <ChevronsUpDown className="ml-1 h-3.5 w-3.5 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[220px] p-0" align="start">
          <Command>
            <CommandInput placeholder={`Zoek ${label.toLowerCase()}...`} className="h-8" />
            <CommandList>
              <CommandEmpty>Geen resultaten.</CommandEmpty>
              <CommandGroup>
                {options.map((opt) => (
                  <CommandItem
                    key={opt.value}
                    value={opt.value}
                    onSelect={() => onToggle(opt.value)}
                    className="gap-2"
                  >
                    <Check
                      className={cn("h-3.5 w-3.5", selected.includes(opt.value) ? "opacity-100" : "opacity-0")}
                    />
                    <span className="text-sm">{opt.label}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

// ── Single-select combobox ───────────────────────────────────────────────────

function SingleCombobox({
  label,
  placeholder,
  options,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  placeholder: string;
  options: { value: string; label: string }[];
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find(o => o.value === value);

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</span>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className={cn(
              "w-full justify-between bg-background font-normal h-9",
              value && "border-primary/50"
            )}
          >
            {selected ? (
              <span className="text-sm truncate">{selected.label}</span>
            ) : (
              <span className="text-muted-foreground text-sm">{placeholder}</span>
            )}
            <ChevronsUpDown className="ml-1 h-3.5 w-3.5 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[220px] p-0" align="start">
          <Command>
            <CommandInput placeholder={`Zoek ${label.toLowerCase()}...`} className="h-8" />
            <CommandList>
              <CommandEmpty>Geen resultaten.</CommandEmpty>
              <CommandGroup>
                {value && (
                  <CommandItem value="__clear__" onSelect={() => { onChange(null); setOpen(false); }} className="gap-2 text-muted-foreground">
                    <X className="h-3.5 w-3.5" /> Wis selectie
                  </CommandItem>
                )}
                {options.map((opt) => (
                  <CommandItem
                    key={opt.value}
                    value={opt.value}
                    onSelect={(v) => { onChange(v === value ? null : v); setOpen(false); }}
                    className="gap-2"
                  >
                    <Check className={cn("h-3.5 w-3.5", value === opt.value ? "opacity-100" : "opacity-0")} />
                    <span className="text-sm">{opt.label}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

// ── Hoofd SmartFilters component ─────────────────────────────────────────────

export default function SmartFilters({ onChange, className }: SmartFiltersProps) {
  const [filters, setFilters] = useState<SmartFilterValues>(EMPTY_FILTERS);
  const [collapsed, setCollapsed] = useState(false);

  // Hiërarchie data
  const [categories, setCategories] = useState<HierarchyNode[]>([]);
  const [subcategories, setSubcategories] = useState<HierarchyNode[]>([]);
  const [subSubcategories, setSubSubcategories] = useState<HierarchyNode[]>([]);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    merken: [], bcg_intern: [], bcg_extern: [], merktype_opties: [], actie_nodig_opties: [],
  });

  const [loadingCats, setLoadingCats] = useState(false);
  const [loadingSubs, setLoadingSubs] = useState(false);
  const [loadingSubSubs, setLoadingSubSubs] = useState(false);

  const authHeader = { Authorization: `Bearer ${getToken()}` };

  // Initieel laden
  useEffect(() => {
    setLoadingCats(true);
    fetch(`${BASE}/api/category-hierarchy/categories`, { headers: authHeader })
      .then(r => r.json()).then(setCategories).catch(() => {}).finally(() => setLoadingCats(false));

    fetch(`${BASE}/api/category-hierarchy/filter-options`, { headers: authHeader })
      .then(r => r.json()).then(setFilterOptions).catch(() => {});
  }, []);

  // Cascade: wanneer categorie verandert → laad subcategorieën
  useEffect(() => {
    setLoadingSubs(true);
    const url = filters.categorie_id
      ? `${BASE}/api/category-hierarchy/subcategories?parent_id=${filters.categorie_id}`
      : `${BASE}/api/category-hierarchy/subcategories`;
    fetch(url, { headers: authHeader })
      .then(r => r.json()).then(setSubcategories).catch(() => {}).finally(() => setLoadingSubs(false));
    // Reset lager niveau
    setSubSubcategories([]);
  }, [filters.categorie_id]);

  // Cascade: wanneer subcategorie verandert → laad sub-subcategorieën
  useEffect(() => {
    if (!filters.subcategorie_id) { setSubSubcategories([]); return; }
    setLoadingSubSubs(true);
    fetch(`${BASE}/api/category-hierarchy/sub-subcategories?parent_id=${filters.subcategorie_id}`, { headers: authHeader })
      .then(r => r.json()).then(setSubSubcategories).catch(() => {}).finally(() => setLoadingSubSubs(false));
  }, [filters.subcategorie_id]);

  // Notify parent bij elke filterwijziging
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  useEffect(() => { onChangeRef.current(filters); }, [filters]);

  const update = useCallback(<K extends keyof SmartFilterValues>(key: K, value: SmartFilterValues[K]) => {
    setFilters(prev => {
      const next = { ...prev, [key]: value };
      // Cascade reset
      if (key === "categorie_id") { next.subcategorie_id = null; next.sub_subcategorie_id = null; }
      if (key === "subcategorie_id") { next.sub_subcategorie_id = null; }
      return next;
    });
  }, []);

  const toggleMerk = useCallback((merk: string) => {
    setFilters(prev => ({
      ...prev,
      merken: prev.merken.includes(merk) ? prev.merken.filter(m => m !== merk) : [...prev.merken, merk],
    }));
  }, []);

  const resetAll = () => { setFilters(EMPTY_FILTERS); };

  const activeCount = [
    filters.categorie_id, filters.subcategorie_id, filters.sub_subcategorie_id,
    filters.merken.length > 0 ? true : null,
    filters.merktype, filters.bcg_intern, filters.bcg_extern,
    filters.actie_nodig !== null ? true : null,
  ].filter(Boolean).length;

  const catOptions = categories.map(c => ({ value: String(c.category_id), label: c.category_name }));
  const subOptions = subcategories.map(c => ({ value: String(c.category_id), label: c.category_name }));
  const subSubOptions = subSubcategories.map(c => ({ value: String(c.category_id), label: c.category_name }));
  const merkOptions = filterOptions.merken.map(m => ({ value: m, label: m }));
  const bcgInternOptions = filterOptions.bcg_intern.map(b => ({ value: b, label: b.replace(/_/g, " ") }));
  const bcgExternOptions = filterOptions.bcg_extern.map(b => ({ value: b, label: b.replace(/_/g, " ") }));

  return (
    <div className={cn("bg-card border rounded-lg", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">Slimme filters</span>
          {activeCount > 0 && (
            <Badge className="h-5 min-w-5 px-1.5 text-[10px] bg-primary text-primary-foreground">
              {activeCount}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeCount > 0 && (
            <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground" onClick={resetAll}>
              <X className="h-3 w-3 mr-1" /> Wis alles
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setCollapsed(c => !c)}>
            <ChevronDown className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />
          </Button>
        </div>
      </div>

      {/* Filter grid */}
      {!collapsed && (
        <div className="p-4 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          {/* 1. Categorie */}
          <SingleCombobox
            label="Categorie"
            placeholder={loadingCats ? "Laden…" : "Alle categorieën"}
            options={catOptions}
            value={filters.categorie_id ? String(filters.categorie_id) : null}
            onChange={v => update("categorie_id", v ? Number(v) : null)}
          />

          {/* 2. Subcategorie */}
          <SingleCombobox
            label="Subcategorie"
            placeholder={loadingSubs ? "Laden…" : filters.categorie_id ? "Alle subcategorieën" : "Kies eerst categorie"}
            options={subOptions}
            value={filters.subcategorie_id ? String(filters.subcategorie_id) : null}
            onChange={v => update("subcategorie_id", v ? Number(v) : null)}
          />

          {/* 3. Sub-subcategorie */}
          <SingleCombobox
            label="Sub-subcategorie"
            placeholder={loadingSubSubs ? "Laden…" : filters.subcategorie_id ? "Alle sub-sub" : "Kies subcategorie"}
            options={subSubOptions}
            value={filters.sub_subcategorie_id ? String(filters.sub_subcategorie_id) : null}
            onChange={v => update("sub_subcategorie_id", v ? Number(v) : null)}
            disabled={!filters.subcategorie_id}
          />

          {/* 4. Merk */}
          <MultiCombobox
            label="Merk"
            placeholder="Alle merken"
            options={merkOptions}
            selected={filters.merken}
            onToggle={toggleMerk}
          />

          {/* 5. Huismerk / A-merk */}
          <SingleCombobox
            label="Merktype"
            placeholder="Alle merktypes"
            options={filterOptions.merktype_opties}
            value={filters.merktype}
            onChange={v => update("merktype", v)}
          />

          {/* 6. BCG intern */}
          <SingleCombobox
            label="BCG intern"
            placeholder="Alle klassen"
            options={bcgInternOptions}
            value={filters.bcg_intern}
            onChange={v => update("bcg_intern", v)}
          />

          {/* 7. BCG extern */}
          <SingleCombobox
            label="BCG extern"
            placeholder="Alle klassen"
            options={bcgExternOptions}
            value={filters.bcg_extern}
            onChange={v => update("bcg_extern", v)}
          />

          {/* 8. Actie nodig */}
          <SingleCombobox
            label="Actie nodig"
            placeholder="Alle"
            options={[
              { value: "ja", label: "Actie nodig" },
              { value: "nee", label: "Geen actie" },
            ]}
            value={filters.actie_nodig === true ? "ja" : filters.actie_nodig === false ? "nee" : null}
            onChange={v => update("actie_nodig", v === "ja" ? true : v === "nee" ? false : null)}
          />
        </div>
      )}

      {/* Actieve filter badges */}
      {!collapsed && activeCount > 0 && (
        <div className="px-4 pb-3 flex flex-wrap gap-1.5">
          {filters.categorie_id && (
            <ActiveBadge
              label={`Categorie: ${catOptions.find(o => o.value === String(filters.categorie_id))?.label}`}
              onRemove={() => update("categorie_id", null)}
            />
          )}
          {filters.subcategorie_id && (
            <ActiveBadge
              label={`Sub: ${subOptions.find(o => o.value === String(filters.subcategorie_id))?.label}`}
              onRemove={() => update("subcategorie_id", null)}
            />
          )}
          {filters.sub_subcategorie_id && (
            <ActiveBadge
              label={`Sub-sub: ${subSubOptions.find(o => o.value === String(filters.sub_subcategorie_id))?.label}`}
              onRemove={() => update("sub_subcategorie_id", null)}
            />
          )}
          {filters.merken.map(m => (
            <ActiveBadge key={m} label={`Merk: ${m}`} onRemove={() => toggleMerk(m)} />
          ))}
          {filters.merktype && (
            <ActiveBadge
              label={filterOptions.merktype_opties.find(o => o.value === filters.merktype)?.label || filters.merktype}
              onRemove={() => update("merktype", null)}
            />
          )}
          {filters.bcg_intern && (
            <ActiveBadge label={`BCG int: ${filters.bcg_intern.replace(/_/g, " ")}`} onRemove={() => update("bcg_intern", null)} />
          )}
          {filters.bcg_extern && (
            <ActiveBadge label={`BCG ext: ${filters.bcg_extern.replace(/_/g, " ")}`} onRemove={() => update("bcg_extern", null)} />
          )}
          {filters.actie_nodig !== null && (
            <ActiveBadge
              label={filters.actie_nodig ? "Actie nodig" : "Geen actie"}
              onRemove={() => update("actie_nodig", null)}
            />
          )}
        </div>
      )}
    </div>
  );
}

function ActiveBadge({ label, onRemove }: { label: string | undefined; onRemove: () => void }) {
  if (!label) return null;
  return (
    <Badge
      variant="secondary"
      className="text-[11px] pl-2 pr-1 py-0.5 flex items-center gap-1 cursor-pointer hover:bg-muted"
      onClick={onRemove}
    >
      {label}
      <X className="h-3 w-3 text-muted-foreground" />
    </Badge>
  );
}
