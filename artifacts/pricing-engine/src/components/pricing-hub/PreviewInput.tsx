import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ManualRow } from "@/lib/cost-priority/model";
import { emptyManualRow } from "@/lib/cost-priority/model";

export type InputMode = "workbook" | "manual";

export function PreviewInput({ mode, onMode, file, onFile, fileError, rows, onRows, sources, customSource }: {
  mode: InputMode; onMode: (m: InputMode) => void;
  file: File | null; onFile: (f: File | null) => void; fileError: string | null;
  rows: ManualRow[]; onRows: (r: ManualRow[]) => void; sources: string[]; customSource: string | null;
}) {
  const update = (i: number, patch: Partial<ManualRow>) => onRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const nextId = () => { let n = rows.length + 1; while (rows.some(r => r.id === `scenario-${n}`)) n++; return n; };

  return (
    <Tabs value={mode} onValueChange={v => onMode(v as InputMode)} className="p-4">
      <TabsList>
        <TabsTrigger value="workbook" data-testid="tab-workbook">Werkboek uploaden</TabsTrigger>
        <TabsTrigger value="manual" data-testid="tab-manual">Handmatige scenario's</TabsTrigger>
      </TabsList>

      <TabsContent value="workbook" className="space-y-2 pt-3">
        <Input type="file" accept=".xlsx" onChange={e => onFile(e.target.files?.[0] ?? null)} data-testid="input-workbook" />
        {file && <div className="text-xs text-muted-foreground" data-testid="text-workbook-name">{file.name} ({Math.max(1, Math.round(file.size / 1024))} kB)</div>}
        {file && fileError && <div className="text-xs text-destructive" data-testid="text-workbook-error">{fileError}</div>}
        <p className="text-xs text-muted-foreground" data-testid="text-workbook-headers">
          Verwachte kopteksten op rij 2: Productcode, Category, {sources.join(", ")}.
          {customSource && ` De kolom "${customSource}" is verplicht zolang de vijfde bron in het concept staat.`}
        </p>
      </TabsContent>

      <TabsContent value="manual" className="space-y-3 pt-3">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="table-manual">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="p-1 text-left">Regel-ID</th>
                <th className="p-1 text-left">Categorie</th>
                {sources.map(s => <th key={s} className="p-1 text-left">{s}</th>)}
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} data-testid={`row-manual-${i}`}>
                  <td className="p-1"><Input className="h-8 w-28" value={r.id} maxLength={100} onChange={e => update(i, { id: e.target.value })} aria-label="Regel-ID" data-testid={`input-manual-id-${i}`} /></td>
                  <td className="p-1"><Input className="h-8 w-28" value={r.category} maxLength={100} onChange={e => update(i, { category: e.target.value })} aria-label="Categorie" data-testid={`input-manual-category-${i}`} /></td>
                  {sources.map((s, si) => (
                    <td key={s} className="p-1">
                      <Input
                        className="h-8 w-24" inputMode="decimal" placeholder="ontbreekt" value={r.values[s] ?? ""}
                        onChange={e => update(i, { values: { ...r.values, [s]: e.target.value } })}
                        aria-label={`${s} (EUR)`} data-testid={`input-manual-value-${i}-${si}`}
                      />
                    </td>
                  ))}
                  <td className="p-1">
                    <Button size="icon" variant="ghost" className="h-8 w-8" disabled={rows.length <= 1} onClick={() => onRows(rows.filter((_, j) => j !== i))} aria-label="Scenario verwijderen" data-testid={`button-remove-manual-${i}`}><Trash2 className="h-4 w-4" /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between">
          <Button size="sm" variant="outline" disabled={rows.length >= 500} onClick={() => onRows([...rows, emptyManualRow(nextId(), rows[rows.length - 1]?.category ?? "Print")])} data-testid="button-add-manual-row">
            <Plus className="mr-1 h-4 w-4" />Scenario toevoegen
          </Button>
          <Label className="text-xs font-normal text-muted-foreground">Leeg = ontbreekt (blokkeert activeren). Vul 0 in voor niet beschikbaar.</Label>
        </div>
      </TabsContent>
    </Tabs>
  );
}
