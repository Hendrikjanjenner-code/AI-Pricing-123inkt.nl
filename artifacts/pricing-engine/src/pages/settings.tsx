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

export default function Settings() {
  const { data: users, isLoading } = useListUsers();
  const createMut = useCreateUser();
  const deleteMut = useDeleteUser();
  const updateMut = useUpdateUser();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [open, setOpen] = useState(false);
  const [formData, setFormData] = useState({ username: '', email: '', password: '', role: 'viewer', full_name: '' });

  const handleCreate = async () => {
    try {
      await createMut.mutateAsync({ data: formData as any });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      setOpen(false);
      setFormData({ username: '', email: '', password: '', role: 'viewer', full_name: '' });
      toast({ title: "User created" });
    } catch (err) {
      toast({ title: "Error creating user", variant: "destructive" });
    }
  };

  const handleDelete = async (id: number) => {
    if(!confirm("Are you sure you want to delete this user?")) return;
    try {
      await deleteMut.mutateAsync({ id });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      toast({ title: "User deleted" });
    } catch (err) {
      toast({ title: "Error deleting user", variant: "destructive" });
    }
  };

  const handleRoleChange = async (id: number, role: string) => {
    try {
      await updateMut.mutateAsync({ id, data: { role } });
      queryClient.invalidateQueries({ queryKey: ["/api/users"] });
      toast({ title: "Role updated" });
    } catch (err) {
      toast({ title: "Error updating role", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">System Settings</h1>
          <p className="text-muted-foreground mt-1">Manage users and access control.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button><UserPlus className="w-4 h-4 mr-2"/> Add User</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Add New User</DialogTitle></DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2"><Label>Username</Label><Input value={formData.username} onChange={e => setFormData(f=>({ ...f, username: e.target.value}))}/></div>
              <div className="space-y-2"><Label>Full Name</Label><Input value={formData.full_name} onChange={e => setFormData(f=>({ ...f, full_name: e.target.value}))}/></div>
              <div className="space-y-2"><Label>Email</Label><Input type="email" value={formData.email} onChange={e => setFormData(f=>({ ...f, email: e.target.value}))}/></div>
              <div className="space-y-2"><Label>Password</Label><Input type="password" value={formData.password} onChange={e => setFormData(f=>({ ...f, password: e.target.value}))}/></div>
              <div className="space-y-2"><Label>Role</Label>
                <Select value={formData.role} onValueChange={v => setFormData(f=>({ ...f, role: v}))}>
                  <SelectTrigger><SelectValue/></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="pricing_manager">Pricing Manager</SelectItem>
                    <SelectItem value="analyst">Analyst</SelectItem>
                    <SelectItem value="viewer">Viewer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={()=>setOpen(false)}>Cancel</Button>
              <Button onClick={handleCreate} disabled={createMut.isPending || !formData.username || !formData.password}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>User Management</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                 Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                    <TableCell><Skeleton className="h-8 w-32" /></TableCell>
                    <TableCell><Skeleton className="h-6 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-8 w-8 ml-auto" /></TableCell>
                  </TableRow>
                ))
              ) : users?.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <div className="font-medium">{user.full_name || user.username}</div>
                    <div className="text-xs text-muted-foreground">{user.username}</div>
                  </TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell>
                    <Select value={user.role} onValueChange={(v) => handleRoleChange(user.id, v)}>
                      <SelectTrigger className="w-[180px] h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">Admin</SelectItem>
                        <SelectItem value="pricing_manager">Pricing Manager</SelectItem>
                        <SelectItem value="analyst">Analyst</SelectItem>
                        <SelectItem value="viewer">Viewer</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    {user.is_active ? <Badge variant="secondary" className="bg-emerald-50 text-emerald-600">Active</Badge> : <Badge variant="outline">Inactive</Badge>}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-8 w-8" onClick={() => handleDelete(user.id)} disabled={deleteMut.isPending}>
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
