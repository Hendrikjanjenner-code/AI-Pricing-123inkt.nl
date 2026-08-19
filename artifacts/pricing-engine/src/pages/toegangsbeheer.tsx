/**
 * Afdelingen & Rechten (taak 219).
 *
 * Beheer-UI voor het granulaire autorisatiemodel:
 *  - Afdelingen (workspaces): naam, zichtbare domeinen, default-permissies,
 *    startpagina.
 *  - Rollen & Rechten-matrix: opgebouwd uit de echte permissiecatalogus
 *    (niet hardcoded), direct bewerkbaar; elke wijziging krijgt een
 *    audittrail-regel (zichtbaar in de Audit Log).
 */
import { useMemo, useState } from "react";
import {
  useListAuthzDepartments, useUpdateAuthzDepartment,
  useGetRolesMatrix, useUpdateRolesMatrix,
  getListAuthzDepartmentsQueryKey, getGetRolesMatrixQueryKey,
  type Department, type PermissionDef,
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Shield, Building2, Save } from "lucide-react";

const ROL_LABELS: Record<string, string> = {
  admin: "Beheerder",
  pricing_manager: "Prijsmanager",
  analyst: "Analist",
  viewer: "Lezer",
};

function DepartmentCard({ dept }: { dept: Department }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [bewerken, setBewerken] = useState(false);
  const [naam, setNaam] = useState(dept.name);
  const [startRoute, setStartRoute] = useState(dept.default_route);
  const update = useUpdateAuthzDepartment();

  const opslaan = async () => {
    try {
      await update.mutateAsync({
        deptId: dept.id,
        data: { name: naam, default_route: startRoute },
      });
      queryClient.invalidateQueries({ queryKey: getListAuthzDepartmentsQueryKey() });
      toast({ title: "Afdeling bijgewerkt", description: `${naam} is opgeslagen (met audittrail).` });
      setBewerken(false);
    } catch (e: any) {
      toast({ title: "Opslaan mislukt", description: e?.data?.detail || e?.message, variant: "destructive" });
    }
  };

  return (
    <Card data-testid={`afdeling-${dept.code}`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Building2 className="w-4 h-4 text-muted-foreground" />
            {dept.name}
            {!dept.active && <Badge variant="outline">inactief</Badge>}
          </CardTitle>
          <Button size="sm" variant="outline" onClick={() => setBewerken((b) => !b)}>
            {bewerken ? "Annuleren" : "Bewerken"}
          </Button>
        </div>
        <CardDescription>
          Code: <code className="font-mono">{dept.code}</code> · Startpagina:{" "}
          <code className="font-mono">{dept.default_route}</code>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {bewerken && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Naam</Label>
              <Input value={naam} onChange={(e) => setNaam(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Startpagina (route)</Label>
              <Input value={startRoute} onChange={(e) => setStartRoute(e.target.value)} />
            </div>
            <div className="sm:col-span-2">
              <Button size="sm" onClick={opslaan} disabled={update.isPending}>
                <Save className="w-4 h-4 mr-1" />
                {update.isPending ? "Opslaan..." : "Opslaan"}
              </Button>
            </div>
          </div>
        )}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">Zichtbare domeinen (workspace)</p>
          <div className="flex flex-wrap gap-1">
            {dept.workspace_domains.map((d) => (
              <Badge key={d} variant="secondary" className="font-mono text-xs">{d}</Badge>
            ))}
          </div>
        </div>
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">Default-permissies</p>
          <div className="flex flex-wrap gap-1">
            {dept.default_permissions.map((p) => (
              <Badge key={p} variant="outline" className="font-mono text-xs">{p}</Badge>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RollenMatrix() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading } = useGetRolesMatrix();
  const update = useUpdateRolesMatrix();
  const [wijzigingen, setWijzigingen] = useState<Record<string, string[]> | null>(null);

  const matrix = wijzigingen ?? (data?.matrix as Record<string, string[]> | undefined) ?? {};
  const rollen = data?.roles ?? [];
  const permissies: PermissionDef[] = useMemo(
    () => [...(data?.permissions ?? [])].sort((a, b) => a.code.localeCompare(b.code)),
    [data?.permissions],
  );

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;

  const heeft = (rol: string, code: string) => (matrix[rol] ?? []).includes(code);
  const toggle = (rol: string, code: string) => {
    const basis = wijzigingen ?? JSON.parse(JSON.stringify(data.matrix));
    const set = new Set(basis[rol] ?? []);
    if (set.has(code)) set.delete(code);
    else set.add(code);
    setWijzigingen({ ...basis, [rol]: [...set].sort() });
  };

  const opslaan = async () => {
    if (!wijzigingen) return;
    try {
      await update.mutateAsync({ data: { matrix: wijzigingen } });
      queryClient.invalidateQueries({ queryKey: getGetRolesMatrixQueryKey() });
      setWijzigingen(null);
      toast({ title: "Matrix opgeslagen", description: "Wijzigingen zijn direct actief en gelogd in de audittrail." });
    } catch (e: any) {
      toast({ title: "Opslaan mislukt", description: e?.data?.detail || e?.message, variant: "destructive" });
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Rollen & Rechten-matrix</CardTitle>
            <CardDescription>
              Rol-basisrechten per permissie. Afdelings-defaults en persoonlijke
              extra rechten komen hier bovenop. De admin-rol behoudt altijd
              volledige toegang.
            </CardDescription>
          </div>
          <Button size="sm" onClick={opslaan} disabled={!wijzigingen || update.isPending} data-testid="matrix-opslaan">
            <Save className="w-4 h-4 mr-1" />
            {update.isPending ? "Opslaan..." : "Wijzigingen opslaan"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2 pr-4 font-medium">Permissie</th>
              {rollen.map((rol) => (
                <th key={rol} className="text-center py-2 px-3 font-medium">{ROL_LABELS[rol] ?? rol}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {permissies.map((p) => (
              <tr key={p.code} className="border-b last:border-0 hover:bg-muted/40">
                <td className="py-1.5 pr-4">
                  <div className="font-mono text-xs">{p.code}</div>
                  <div className="text-xs text-muted-foreground">{p.label}</div>
                </td>
                {rollen.map((rol) => (
                  <td key={rol} className="text-center py-1.5 px-3">
                    <Checkbox
                      checked={rol === "admin" ? true : heeft(rol, p.code)}
                      disabled={rol === "admin" || update.isPending}
                      onCheckedChange={() => toggle(rol, p.code)}
                      data-testid={`matrix-${rol}-${p.code}`}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

export default function Toegangsbeheer() {
  const { data: deptData, isLoading } = useListAuthzDepartments();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Shield className="w-7 h-7" />
          Afdelingen & Rechten
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Afdelingsworkspaces bepalen welke domeinen zichtbaar zijn en welke
          startpagina geldt; de backend dwingt dezelfde permissies af op elke
          API-route. Persoonlijke rechten en afdelingskoppeling beheer je per
          gebruiker onder Instellingen.
        </p>
      </div>

      <RollenMatrix />

      <div>
        <h2 className="text-lg font-semibold mb-3">Afdelingen (workspaces)</h2>
        {isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {(deptData?.departments ?? []).map((d) => (
              <DepartmentCard key={d.id} dept={d} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
