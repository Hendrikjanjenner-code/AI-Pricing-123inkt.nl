/**
 * SavedViewsMenu (taak #221) — opgeslagen views in de Global Filter Bar.
 *
 * Slaat de huidige Global Filter Context (hiërarchie, merken, periode,
 * SKU-zoek) op als view met sharing-niveau Private / Team / Department
 * (rechten-afhankelijk; de backend dwingt dit af). Een department-view kan
 * als afdelings-default worden gemarkeerd; die wordt automatisch toegepast
 * wanneer de gebruiker nog geen eigen filtercontext heeft.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bookmark, BookmarkPlus, Trash2, Star, Users, Building2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { getAuthHeaders, useAuth } from "@/lib/auth";
import {
  getGlobalFilters, setGlobalFilters, hasActiveFilters, emptyFilters,
  type GlobalFilters,
} from "@/lib/global-filters";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const PAGE_KEY = "*"; // Global Filter Context geldt platformbreed
// Per gebruiker, zodat een gebruikerswissel in dezelfde browsersessie de
// afdelings-default van de nieuwe gebruiker alsnog toepast.
const defaultAppliedKey = (userId: string | number) =>
  `saved_views.department_default_applied_v1.${userId}`;

export interface SavedView {
  id: number;
  name: string;
  page_key: string;
  scope: "private" | "team" | "department";
  department: { id: number; code: string; name: string } | null;
  department_id: number | null;
  is_department_default: boolean;
  config: { filters?: Partial<GlobalFilters> };
  owner_user_id: number;
  owner_username: string | null;
}

const SCOPE_META = {
  private: { label: "Privé", icon: Lock },
  team: { label: "Team", icon: Users },
  department: { label: "Afdeling", icon: Building2 },
} as const;

function applyView(view: SavedView) {
  const f = view.config?.filters ?? {};
  setGlobalFilters({
    ...emptyFilters(),
    hierarchy: Array.isArray(f.hierarchy) ? f.hierarchy : [],
    brands: Array.isArray(f.brands) ? f.brands : [],
    periodDays: typeof f.periodDays === "number" ? f.periodDays : null,
    skuQuery: typeof f.skuQuery === "string" ? f.skuQuery : "",
  });
}

/**
 * Past éénmalig per sessie de department-default toe wanneer de gebruiker
 * zonder actieve filtercontext binnenkomt.
 */
export function useDepartmentDefaultView() {
  const { user } = useAuth();
  const userId = user?.id;
  useEffect(() => {
    if (userId == null) return;
    try {
      const key = defaultAppliedKey(userId);
      if (sessionStorage.getItem(key)) return;
      sessionStorage.setItem(key, "1");
    } catch {
      return; // zonder sessionStorage geen betrouwbare éénmaligheid
    }
    if (hasActiveFilters(getGlobalFilters())) return;
    void (async () => {
      try {
        const res = await fetch(
          `${BASE}/api/saved-views/department-default?page_key=${encodeURIComponent(PAGE_KEY)}`,
          { headers: getAuthHeaders() },
        );
        if (!res.ok) return;
        const data = await res.json();
        if (data?.view && !hasActiveFilters(getGlobalFilters())) {
          applyView(data.view as SavedView);
        }
      } catch {
        /* best-effort */
      }
    })();
  }, [userId]);
}

export function SavedViewsMenu() {
  const { user } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [naam, setNaam] = useState("");
  const [scope, setScope] = useState<"private" | "team" | "department">("private");
  const [departmentId, setDepartmentId] = useState<string>("");
  const [alsDefault, setAlsDefault] = useState(false);

  const { data } = useQuery<{ views: SavedView[] }>({
    queryKey: ["/api/saved-views", PAGE_KEY],
    queryFn: async () => {
      const res = await fetch(
        `${BASE}/api/saved-views?page_key=${encodeURIComponent(PAGE_KEY)}`,
        { headers: getAuthHeaders() },
      );
      if (!res.ok) throw new Error("Views laden mislukt");
      return res.json();
    },
    enabled: open,
    staleTime: 30_000,
  });

  const magTeam = ["analyst", "pricing_manager", "admin"].includes(user?.role);
  const magDepartment = ["pricing_manager", "admin"].includes(user?.role);
  const afdelingen: { id: number; name: string }[] = user?.departments ?? [];

  const opslaanMut = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${BASE}/api/saved-views`, {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          name: naam.trim(),
          page_key: PAGE_KEY,
          scope,
          department_id: scope === "department" ? Number(departmentId) || null : null,
          is_department_default: scope === "department" && alsDefault,
          config: { filters: getGlobalFilters() },
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Opslaan mislukt");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/saved-views"] });
      setNaam(""); setAlsDefault(false);
      toast({ title: "View opgeslagen" });
    },
    onError: (e: Error) => toast({ title: "Opslaan mislukt", description: e.message, variant: "destructive" }),
  });

  const verwijderMut = useMutation({
    mutationFn: async (id: number) => {
      const res = await fetch(`${BASE}/api/saved-views/${id}`, {
        method: "DELETE", headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("Verwijderen mislukt");
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["/api/saved-views"] }),
  });

  const views = data?.views ?? [];
  const kanOpslaan = useMemo(
    () => naam.trim().length > 0 && (scope !== "department" || departmentId),
    [naam, scope, departmentId],
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2" data-testid="button-saved-views">
          <Bookmark className="w-4 h-4" />
          Views
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96" align="end">
        <div className="space-y-4">
          <div>
            <h4 className="text-sm font-semibold mb-2">Opgeslagen views</h4>
            {views.length === 0 && (
              <p className="text-sm text-muted-foreground">Nog geen views opgeslagen.</p>
            )}
            <div className="space-y-1 max-h-56 overflow-y-auto">
              {views.map((v) => {
                const Meta = SCOPE_META[v.scope] ?? SCOPE_META.private;
                const Icon = Meta.icon;
                const eigen = v.owner_user_id === user?.id;
                return (
                  <div key={v.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent group">
                    <button
                      type="button"
                      className="flex-1 flex items-center gap-2 text-left text-sm min-w-0"
                      onClick={() => { applyView(v); setOpen(false); }}
                      data-testid={`saved-view-${v.id}`}
                    >
                      <Icon className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate">{v.name}</span>
                      {v.is_department_default && (
                        <Star className="w-3 h-3 shrink-0 text-amber-500 fill-amber-500" />
                      )}
                      <Badge variant="outline" className="ml-auto shrink-0 text-[10px]">
                        {v.scope === "department" && v.department
                          ? v.department.name : Meta.label}
                      </Badge>
                    </button>
                    {(eigen || user?.role === "admin") && (
                      <button
                        type="button"
                        onClick={() => verwijderMut.mutate(v.id)}
                        className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                        data-testid={`delete-saved-view-${v.id}`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="border-t pt-3 space-y-2">
            <Label className="text-sm font-semibold">Huidige filters opslaan</Label>
            <Input
              placeholder="Naam van de view"
              value={naam}
              onChange={(e) => setNaam(e.target.value)}
              data-testid="input-view-name"
            />
            <div className="flex gap-2">
              <Select value={scope} onValueChange={(v) => setScope(v as typeof scope)}>
                <SelectTrigger className="flex-1" data-testid="select-view-scope">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="private">Privé</SelectItem>
                  {magTeam && <SelectItem value="team">Team</SelectItem>}
                  {magDepartment && <SelectItem value="department">Afdeling</SelectItem>}
                </SelectContent>
              </Select>
              {scope === "department" && (
                <Select value={departmentId} onValueChange={setDepartmentId}>
                  <SelectTrigger className="flex-1" data-testid="select-view-department">
                    <SelectValue placeholder="Afdeling" />
                  </SelectTrigger>
                  <SelectContent>
                    {afdelingen.map((d) => (
                      <SelectItem key={d.id} value={String(d.id)}>{d.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            {scope === "department" && (
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={alsDefault}
                  onCheckedChange={(v) => setAlsDefault(v === true)}
                  data-testid="checkbox-view-default"
                />
                Gebruik als afdelings-default
              </label>
            )}
            <Button
              size="sm"
              className="w-full gap-2"
              disabled={!kanOpslaan || opslaanMut.isPending}
              onClick={() => opslaanMut.mutate()}
              data-testid="button-save-view"
            >
              <BookmarkPlus className="w-4 h-4" />
              View opslaan
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
