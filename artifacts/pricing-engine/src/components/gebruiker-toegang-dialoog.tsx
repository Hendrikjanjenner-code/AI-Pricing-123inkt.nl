import { useEffect, useMemo, useState } from "react";
import {
  useGetUserAuthz,
  useUpdateUserAuthz,
  getGetUserAuthzQueryKey,
  useListAuthzDepartments,
  getListAuthzDepartmentsQueryKey,
  useListAuthzPermissions,
  getListAuthzPermissionsQueryKey,
  useListShops,
  getListShopsQueryKey,
  type UserAuthz,
  type UserScope,
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Plus, Trash2 } from "lucide-react";

const GEEN_PRIMAIR = "__geen__";

const SCOPE_TYPE_LABELS: Record<string, string> = {
  shop: "Winkel",
  country: "Land",
  legal_entity: "Juridische entiteit",
};

interface Props {
  userId: number;
  userLabel: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * "Toegang"-dialoog per gebruiker (Task #227): afdelingen (primair + extra),
 * persoonlijke extra permissies en data-scopes beheren via de bestaande
 * authz-endpoints. Effectieve permissies worden ter controle getoond.
 */
export default function GebruikerToegangDialoog({ userId, userLabel, open, onOpenChange }: Props) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const authzQuery = useGetUserAuthz(userId, {
    query: { queryKey: getGetUserAuthzQueryKey(userId), enabled: open },
  });
  const deptsQuery = useListAuthzDepartments({
    query: { queryKey: getListAuthzDepartmentsQueryKey(), enabled: open },
  });
  const permsQuery = useListAuthzPermissions({
    query: { queryKey: getListAuthzPermissionsQueryKey(), enabled: open },
  });
  const shopsQuery = useListShops({
    query: { queryKey: getListShopsQueryKey(), enabled: open },
  });
  const updateMut = useUpdateUserAuthz();

  const authz: UserAuthz | undefined = authzQuery.data;

  // Lokale bewerkbuffer, geïnitialiseerd zodra de authz-data binnen is.
  const [primair, setPrimair] = useState<string>(GEEN_PRIMAIR);
  const [extraAfdelingen, setExtraAfdelingen] = useState<string[]>([]);
  const [extraPermissies, setExtraPermissies] = useState<string[]>([]);
  const [scopes, setScopes] = useState<UserScope[]>([]);

  useEffect(() => {
    if (!open || !authz) return;
    const codes = authz.departments.map((d) => d.code);
    setPrimair(codes[0] ?? GEEN_PRIMAIR);
    setExtraAfdelingen(codes.slice(1));
    setExtraPermissies([...authz.extra_permissions]);
    setScopes(authz.scopes.map((s) => ({ ...s })));
  }, [open, authz]);

  const afdelingen = deptsQuery.data?.departments?.filter((d) => d.active) ?? [];
  const permissies = permsQuery.data?.permissions ?? [];
  const shops = shopsQuery.data?.shops ?? [];

  // Permissies gegroepeerd per domein voor overzichtelijke checkboxes.
  const permissiesPerDomein = useMemo(() => {
    const groepen: Record<string, typeof permissies> = {};
    for (const p of permissies) {
      (groepen[p.domein] ??= []).push(p);
    }
    return Object.entries(groepen).sort(([a], [b]) => a.localeCompare(b));
  }, [permissies]);

  // Mogelijke scope-waarden afgeleid uit de winkellijst.
  const scopeWaarden = useMemo(() => {
    const uniek = (arr: (string | null | undefined)[]) =>
      Array.from(new Set(arr.filter((v): v is string => !!v))).sort();
    return {
      // Let op: shop-scopes gebruiken de numerieke DimShop.id als scope_value
      // (zo interpreteert authz.user_allowed_shop_ids ze); de code is alleen label.
      shop: shops.map((s) => ({ value: String(s.id), label: `${s.name} (${s.shop_code})` })),
      country: uniek(shops.map((s) => s.country)).map((v) => ({ value: v, label: v })),
      legal_entity: uniek(shops.map((s) => s.legal_entity)).map((v) => ({ value: v, label: v })),
    } as Record<string, { value: string; label: string }[]>;
  }, [shops]);

  const toggleExtraAfdeling = (code: string, aan: boolean) => {
    setExtraAfdelingen((prev) => (aan ? [...prev, code] : prev.filter((c) => c !== code)));
  };

  const togglePermissie = (code: string, aan: boolean) => {
    setExtraPermissies((prev) => (aan ? [...prev, code] : prev.filter((c) => c !== code)));
  };

  const wijzigScope = (index: number, patch: Partial<UserScope>) => {
    setScopes((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  };

  const handleOpslaan = async () => {
    const departmentCodes = [
      ...(primair !== GEEN_PRIMAIR ? [primair] : []),
      ...extraAfdelingen.filter((c) => c !== primair),
    ];
    const geldigeScopes = scopes.filter((s) => s.scope_type && s.scope_value);
    try {
      const nieuw = await updateMut.mutateAsync({
        userId,
        data: {
          department_codes: departmentCodes,
          extra_permissions: extraPermissies,
          scopes: geldigeScopes,
        },
      });
      queryClient.setQueryData(getGetUserAuthzQueryKey(userId), nieuw);
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      toast({ title: "Toegangsrechten bijgewerkt" });
      onOpenChange(false);
    } catch (e: any) {
      toast({
        title: "Bijwerken mislukt",
        description: e?.data?.detail || e?.message,
        variant: "destructive",
      });
    }
  };

  const laden = authzQuery.isLoading || deptsQuery.isLoading || permsQuery.isLoading;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Toegang — {userLabel}</DialogTitle>
          <DialogDescription>
            Afdelingen, persoonlijke extra permissies en data-scopes voor deze gebruiker.
            Wijzigingen worden vastgelegd in de audittrail.
          </DialogDescription>
        </DialogHeader>

        {laden ? (
          <div className="space-y-3 py-4">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
          </div>
        ) : authzQuery.isError ? (
          <p className="py-4 text-sm text-destructive">Toegangsgegevens ophalen mislukt.</p>
        ) : (
          <div className="space-y-6 py-2">
            {/* Afdelingen */}
            <section className="space-y-3">
              <div>
                <h3 className="text-sm font-semibold">Afdelingen</h3>
                <p className="text-xs text-muted-foreground">
                  De primaire afdeling bepaalt o.a. de startpagina; extra afdelingen geven aanvullende toegang.
                </p>
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Primaire afdeling</Label>
                <Select value={primair} onValueChange={setPrimair}>
                  <SelectTrigger data-testid="select-primaire-afdeling">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={GEEN_PRIMAIR}>Geen afdeling</SelectItem>
                    {afdelingen.map((d) => (
                      <SelectItem key={d.code} value={d.code}>{d.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Extra afdelingen</Label>
                <div className="grid grid-cols-2 gap-2">
                  {afdelingen.filter((d) => d.code !== primair).map((d) => (
                    <label key={d.code} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={extraAfdelingen.includes(d.code)}
                        onCheckedChange={(v) => toggleExtraAfdeling(d.code, v === true)}
                        data-testid={`checkbox-afdeling-${d.code}`}
                      />
                      {d.name}
                    </label>
                  ))}
                </div>
              </div>
            </section>

            {/* Extra permissies */}
            <section className="space-y-3">
              <div>
                <h3 className="text-sm font-semibold">Extra permissies</h3>
                <p className="text-xs text-muted-foreground">
                  Persoonlijke permissies bovenop wat de rol en afdeling(en) al geven.
                </p>
              </div>
              <div className="space-y-3">
                {permissiesPerDomein.map(([domein, perms]) => (
                  <div key={domein}>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">{domein}</p>
                    <div className="grid grid-cols-2 gap-2">
                      {perms.map((p) => (
                        <label key={p.code} className="flex items-center gap-2 text-sm">
                          <Checkbox
                            checked={extraPermissies.includes(p.code)}
                            onCheckedChange={(v) => togglePermissie(p.code, v === true)}
                            data-testid={`checkbox-permissie-${p.code}`}
                          />
                          {p.label}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* Data-scopes */}
            <section className="space-y-3">
              <div>
                <h3 className="text-sm font-semibold">Data-scopes</h3>
                <p className="text-xs text-muted-foreground">
                  Beperk welke data deze gebruiker ziet. Geen scopes = alle data zichtbaar.
                </p>
              </div>
              <div className="space-y-2">
                {scopes.map((s, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Select
                      value={s.scope_type}
                      onValueChange={(v) => wijzigScope(i, { scope_type: v as UserScope["scope_type"], scope_value: "" })}
                    >
                      <SelectTrigger className="w-[180px]" data-testid={`select-scope-type-${i}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(SCOPE_TYPE_LABELS).map(([v, label]) => (
                          <SelectItem key={v} value={v}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={s.scope_value || undefined} onValueChange={(v) => wijzigScope(i, { scope_value: v })}>
                      <SelectTrigger className="flex-1" data-testid={`select-scope-waarde-${i}`}>
                        <SelectValue placeholder="Kies waarde…" />
                      </SelectTrigger>
                      <SelectContent>
                        {(scopeWaarden[s.scope_type] ?? []).map((o) => (
                          <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive hover:bg-destructive/10"
                      onClick={() => setScopes((prev) => prev.filter((_, j) => j !== i))}
                      data-testid={`button-scope-verwijderen-${i}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1"
                  onClick={() => setScopes((prev) => [...prev, { scope_type: "shop", scope_value: "" }])}
                  data-testid="button-scope-toevoegen"
                >
                  <Plus className="h-4 w-4" /> Scope toevoegen
                </Button>
              </div>
            </section>

            {/* Effectieve permissies ter controle */}
            <section className="space-y-2">
              <h3 className="text-sm font-semibold">Effectieve permissies (huidig opgeslagen)</h3>
              <div className="flex flex-wrap gap-1">
                {authz && authz.effective_permissions.length > 0 ? (
                  authz.effective_permissions.map((code) => (
                    <Badge key={code} variant="secondary" className="font-mono text-[11px]">{code}</Badge>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">Geen permissies.</p>
                )}
              </div>
            </section>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuleren</Button>
          <Button
            onClick={handleOpslaan}
            disabled={laden || authzQuery.isError || updateMut.isPending}
            data-testid="button-toegang-opslaan"
          >
            {updateMut.isPending ? "Opslaan…" : "Opslaan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
