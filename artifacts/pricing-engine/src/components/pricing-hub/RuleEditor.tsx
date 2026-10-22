import { useEffect, useState } from "react";
import { Plus, RotateCcw, Trash2, X } from "lucide-react";
import type { CostPriorityRules } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PriorityList } from "./PriorityList";
import {
  addCategoryOverride, describeTarget, orderOf, parseTargetKey, removeCategoryOverride, removeCustomSource,
  resetToExcelDefault, setCustomSource, targetKey, validateCustomName, withOrder,
} from "@/lib/cost-priority/model";

export function RuleEditor({ rules, onChange, dirty, onDiscard, canEdit, activeKey, onActiveKey }: {
  rules: CostPriorityRules; onChange: (r: CostPriorityRules) => void; dirty: boolean; onDiscard: () => void;
  canEdit: boolean; activeKey: string; onActiveKey: (k: string) => void;
}) {
  const [newCat, setNewCat] = useState("");
  const [customName, setCustomName] = useState(rules.custom_source ?? "");
  const [customErr, setCustomErr] = useState<string | null>(null);
  useEffect(() => { setCustomName(rules.custom_source ?? ""); setCustomErr(null); }, [rules.custom_source]);
  const overrides = Object.keys(rules.categories).sort((a, b) => a.localeCompare(b, "nl"));
  const target = parseTargetKey(activeKey);
  const validTarget = target.kind !== "category" || overrides.includes(target.name);
  const effective = validTarget ? target : { kind: "print" as const };
  const tabs = [{ key: "print", label: "Print" }, { key: "other", label: "Overige" }, ...overrides.map(n => ({ key: `cat:${n}`, label: n }))];

  const addOverride = () => {
    const name = newCat.trim();
    if (!name || name.length > 100 || overrides.length >= 50) return;
    onChange(addCategoryOverride(rules, name));
    onActiveKey(`cat:${name}`);
    setNewCat("");
  };
  const applyCustom = () => {
    const err = validateCustomName(customName, rules);
    setCustomErr(err);
    if (!err) onChange(setCustomSource(rules, customName));
  };

  return (
    <div className="rounded-lg border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <h2 className="font-semibold">Volgorde kostbronnen</h2>
          <p className="text-xs text-muted-foreground">Sleep de kaarten of gebruik de pijlknoppen / Alt+pijl. Prio 1 wordt eerst geprobeerd.</p>
        </div>
        {dirty && <Badge variant="outline" className="border-amber-500 text-amber-700" data-testid="status-draft-dirty">Concept gewijzigd</Badge>}
      </div>

      <div className="flex flex-wrap gap-1 border-b px-3 py-2" role="tablist" aria-label="Regeldoel">
        {tabs.map(t => (
          <button
            key={t.key} role="tab" aria-selected={targetKey(effective) === t.key}
            onClick={() => onActiveKey(t.key)}
            className={`rounded-md px-3 py-1 text-sm ${targetKey(effective) === t.key ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            data-testid={`tab-target-${t.key}`}
          >{t.label}</button>
        ))}
      </div>

      <div className="space-y-3 p-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span data-testid="text-target-description">Geldt voor: {describeTarget(effective)}</span>
          {effective.kind === "category" && canEdit && (
            <Button size="sm" variant="ghost" onClick={() => { onChange(removeCategoryOverride(rules, effective.name)); onActiveKey("other"); }} data-testid="button-remove-override">
              <Trash2 className="mr-1 h-3 w-3" />Override verwijderen
            </Button>
          )}
        </div>
        <PriorityList order={orderOf(rules, effective)} onChange={o => onChange(withOrder(rules, effective, o))} disabled={!canEdit} testPrefix={targetKey(effective)} />
      </div>

      {canEdit && (
        <div className="grid gap-4 border-t p-4 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="input-new-override" className="text-xs">Categorie-override (exacte categorienaam)</Label>
            <div className="flex gap-2">
              <Input id="input-new-override" value={newCat} maxLength={100} onChange={e => setNewCat(e.target.value)} placeholder="bijv. Toner" data-testid="input-new-override" />
              <Button size="sm" variant="outline" onClick={addOverride} disabled={!newCat.trim() || overrides.length >= 50} data-testid="button-add-override"><Plus className="h-4 w-4" /></Button>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="input-custom-source" className="text-xs">Optionele vijfde bron (numeriek, max. 80 tekens)</Label>
            <div className="flex gap-2">
              <Input id="input-custom-source" value={customName} maxLength={80} onChange={e => setCustomName(e.target.value)} placeholder="bijv. Contractprijs" data-testid="input-custom-source" />
              <Button size="sm" variant="outline" onClick={applyCustom} disabled={customName === (rules.custom_source ?? "")} data-testid="button-apply-custom-source">
                {rules.custom_source ? "Hernoemen" : "Toevoegen"}
              </Button>
              {rules.custom_source && (
                <Button size="sm" variant="ghost" onClick={() => { onChange(removeCustomSource(rules)); setCustomName(""); }} data-testid="button-remove-custom-source"><X className="h-4 w-4" /></Button>
              )}
            </div>
            {customErr && <p className="text-xs text-destructive" data-testid="text-custom-source-error">{customErr}</p>}
            <p className="text-[11px] text-muted-foreground">Wordt in elke volgorde achteraan toegevoegd. Werkboek moet een kolom met exact deze naam hebben.</p>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-t px-4 py-3">
        <Button variant="outline" size="sm" disabled={!canEdit} onClick={() => onChange(resetToExcelDefault(rules))} data-testid="button-reset-excel-default">
          <RotateCcw className="mr-1 h-4 w-4" />Excel-default als concept
        </Button>
        <Button variant="ghost" size="sm" disabled={!dirty} onClick={onDiscard} data-testid="button-discard-draft">
          <X className="mr-1 h-4 w-4" />Concept verwerpen
        </Button>
      </div>
      <p className="px-4 pb-3 text-xs text-muted-foreground">Excel-default verwijdert overrides en zet alleen een concept. Pas na preview en expliciet activeren wordt een versie opgeslagen.</p>
    </div>
  );
}
