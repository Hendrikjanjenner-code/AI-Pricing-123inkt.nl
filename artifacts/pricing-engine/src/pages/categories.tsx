import { useState } from "react";
import { useListCategories, useListCategoryStrategies, useUpdateCategoryStrategy } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Save, AlertCircle } from "lucide-react";

export default function Categories() {
  const { data: strategies, isLoading } = useListCategoryStrategies();
  const updateMut = useUpdateCategoryStrategy();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [edits, setEdits] = useState<Record<number, { strategy_type: string, notes: string }>>({});

  const handleEdit = (id: number, field: string, value: string) => {
    setEdits(prev => ({
      ...prev,
      [id]: {
        ...prev[id],
        strategy_type: prev[id]?.strategy_type ?? strategies?.find(s => s.id === id)?.strategy_type ?? "",
        notes: prev[id]?.notes ?? strategies?.find(s => s.id === id)?.notes ?? "",
        [field]: value
      }
    }));
  };

  const handleSave = async (id: number) => {
    const edit = edits[id];
    if (!edit) return;
    
    try {
      await updateMut.mutateAsync({ 
        id, 
        data: { 
          strategy_type: edit.strategy_type,
          notes: edit.notes || null 
        } 
      });
      queryClient.invalidateQueries({ queryKey: ["/api/category-strategies"] });
      
      const newEdits = { ...edits };
      delete newEdits[id];
      setEdits(newEdits);
      
      toast({ title: "Strategy updated successfully" });
    } catch (err) {
      toast({ title: "Error updating strategy", variant: "destructive" });
    }
  };

  const strategyOptions = [
    "SUBSTITUTION_PORTFOLIO",
    "COMPETITOR_INDEX",
    "MARGIN_OPTIMIZATION",
    "STOCK_CLEARANCE",
    "BASKET_BUILDER",
    "VOLUME_DISCOUNT",
    "REPEAT_PURCHASE",
    "LOW_VELOCITY"
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Category Strategy Mapping</h1>
          <p className="text-muted-foreground mt-1">Define default pricing strategies at the category and subcategory level.</p>
        </div>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Category</TableHead>
              <TableHead>Subcategory</TableHead>
              <TableHead>Strategy Type</TableHead>
              <TableHead>Notes</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                  <TableCell><Skeleton className="h-10 w-48" /></TableCell>
                  <TableCell><Skeleton className="h-10 w-64" /></TableCell>
                  <TableCell><Skeleton className="h-10 w-24 ml-auto" /></TableCell>
                </TableRow>
              ))
            ) : strategies?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-32 text-center text-muted-foreground">
                  No category strategies defined.
                </TableCell>
              </TableRow>
            ) : strategies?.map((strat) => {
              const isEdited = edits[strat.id] !== undefined;
              const currentStrat = isEdited ? edits[strat.id].strategy_type : strat.strategy_type;
              const currentNotes = isEdited ? edits[strat.id].notes : (strat.notes || "");

              return (
                <TableRow key={strat.id} className="group">
                  <TableCell className="font-medium">{strat.category}</TableCell>
                  <TableCell>{strat.subcategory || <span className="text-muted-foreground italic">All</span>}</TableCell>
                  <TableCell>
                    <Select value={currentStrat} onValueChange={(v) => handleEdit(strat.id, "strategy_type", v)}>
                      <SelectTrigger className="w-[240px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {strategyOptions.map(opt => (
                          <SelectItem key={opt} value={opt}>{opt.replace(/_/g, ' ')}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Input 
                      value={currentNotes} 
                      onChange={(e) => handleEdit(strat.id, "notes", e.target.value)} 
                      placeholder="Add logic notes..."
                      className="max-w-[400px]"
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    {isEdited ? (
                      <Button size="sm" onClick={() => handleSave(strat.id)} disabled={updateMut.isPending}>
                        <Save className="h-4 w-4 mr-2" /> Save
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {strat.updated_at ? `Updated ${new Date(strat.updated_at).toLocaleDateString()}` : ''}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
