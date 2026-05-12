import { useState } from "react";
import { useListUsers, useCreateUser, useDeleteUser, useUpdateUser } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Trash2, UserPlus } from "lucide-react";

const ROL_LABELS: Record<string, string> = {
  admin: "Beheerder",
  pricing_manager: "Prijsmanager",
  analyst: "Analist",
  viewer: "Lezer",
};

export default function Instellingen() {
  const { data: gebruikers, isLoading } = useListUsers();
  const aanmakenMut = useCreateUser();
  const verwijderenMut = useDeleteUser();
  const bijwerkenMut = useUpdateUser();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [open, setOpen] = useState(false);
  const [formulier, setFormulier] = useState({ username: '', email: '', password: '', role: 'viewer', full_name: '' });

  const handleAanmaken = async () => {
    try {
      await aanmakenMut.mutateAsync({ data: formulier as any });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      setOpen(false);
      setFormulier({ username: '', email: '', password: '', role: 'viewer', full_name: '' });
      toast({ title: "Gebruiker aangemaakt" });
    } catch {
      toast({ title: "Fout bij aanmaken gebruiker", variant: "destructive" });
    }
  };

  const handleVerwijderen = async (id: number) => {
    if (!confirm("Weet je zeker dat je deze gebruiker wilt verwijderen?")) return;
    try {
      await verwijderenMut.mutateAsync({ id });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      toast({ title: "Gebruiker verwijderd" });
    } catch {
      toast({ title: "Fout bij verwijderen", variant: "destructive" });
    }
  };

  const handleRolWijzigen = async (id: number, rol: string) => {
    try {
      await bijwerkenMut.mutateAsync({ id, data: { role: rol } });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      toast({ title: "Rol bijgewerkt" });
    } catch {
      toast({ title: "Fout bij bijwerken rol", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Systeeminstellingen</h1>
          <p className="text-muted-foreground mt-1">Beheer gebruikers en toegangsrechten.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button><UserPlus className="w-4 h-4 mr-2" /> Gebruiker toevoegen</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Nieuwe gebruiker toevoegen</DialogTitle></DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2"><Label>Gebruikersnaam</Label><Input value={formulier.username} onChange={e => setFormulier(f => ({ ...f, username: e.target.value }))} /></div>
              <div className="space-y-2"><Label>Volledige naam</Label><Input value={formulier.full_name} onChange={e => setFormulier(f => ({ ...f, full_name: e.target.value }))} /></div>
              <div className="space-y-2"><Label>E-mailadres</Label><Input type="email" value={formulier.email} onChange={e => setFormulier(f => ({ ...f, email: e.target.value }))} /></div>
              <div className="space-y-2"><Label>Wachtwoord</Label><Input type="password" value={formulier.password} onChange={e => setFormulier(f => ({ ...f, password: e.target.value }))} /></div>
              <div className="space-y-2"><Label>Rol</Label>
                <Select value={formulier.role} onValueChange={v => setFormulier(f => ({ ...f, role: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Beheerder</SelectItem>
                    <SelectItem value="pricing_manager">Prijsmanager</SelectItem>
                    <SelectItem value="analyst">Analist</SelectItem>
                    <SelectItem value="viewer">Lezer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Annuleren</Button>
              <Button onClick={handleAanmaken} disabled={aanmakenMut.isPending || !formulier.username || !formulier.password}>Aanmaken</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Gebruikersbeheer</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Gebruiker</TableHead>
                <TableHead>E-mail</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Acties</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    {[1,2,3,4,5].map(j => <TableCell key={j}><Skeleton className="h-8 w-full" /></TableCell>)}
                  </TableRow>
                ))
              ) : gebruikers?.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <div className="font-medium">{user.full_name || user.username}</div>
                    <div className="text-xs text-muted-foreground">{user.username}</div>
                  </TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell>
                    <Select value={user.role} onValueChange={(v) => handleRolWijzigen(user.id, v)}>
                      <SelectTrigger className="w-[180px] h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">Beheerder</SelectItem>
                        <SelectItem value="pricing_manager">Prijsmanager</SelectItem>
                        <SelectItem value="analyst">Analist</SelectItem>
                        <SelectItem value="viewer">Lezer</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    {user.is_active
                      ? <Badge variant="secondary" className="bg-emerald-50 text-emerald-600">Actief</Badge>
                      : <Badge variant="outline">Inactief</Badge>}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-8 w-8"
                      onClick={() => handleVerwijderen(user.id)} disabled={verwijderenMut.isPending}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
