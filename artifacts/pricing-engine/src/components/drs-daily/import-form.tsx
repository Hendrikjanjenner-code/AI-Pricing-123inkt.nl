import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface ImportFormValues {
  year: string; start: string; end: string; sheet: string;
  codeCol: string; eanCol: string; firstDayCol: string;
}

export function ImportForm({ values, onChange }: { values: ImportFormValues; onChange: (v: ImportFormValues) => void }) {
  const set = (k: keyof ImportFormValues, v: string) => onChange({ ...values, [k]: v });
  const digits = (v: string) => v.replace(/\D/g, "");
  return (
    <div className="grid gap-3 md:grid-cols-4">
      <div className="space-y-1"><Label htmlFor="dd-year">Jaar eerste dag</Label>
        <Input id="dd-year" data-testid="input-daily-year" inputMode="numeric" value={values.year} onChange={e => set("year", digits(e.target.value).slice(0, 4))} /></div>
      <div className="space-y-1"><Label htmlFor="dd-start">Periode vanaf</Label>
        <Input id="dd-start" data-testid="input-daily-start" type="date" value={values.start} onChange={e => set("start", e.target.value)} /></div>
      <div className="space-y-1"><Label htmlFor="dd-end">Periode t/m</Label>
        <Input id="dd-end" data-testid="input-daily-end" type="date" value={values.end} onChange={e => set("end", e.target.value)} /></div>
      <div className="space-y-1"><Label htmlFor="dd-sheet">Tabblad (optioneel)</Label>
        <Input id="dd-sheet" data-testid="input-daily-sheet" placeholder="eerste tabblad" value={values.sheet} onChange={e => set("sheet", e.target.value)} /></div>
      <div className="md:col-span-4 rounded-md border bg-muted/30 p-3 space-y-2">
        <div className="text-xs font-medium">Template <span className="font-mono">drs-sales-wide-v1</span> — kolomkoppeling (1 = kolom A)</div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="space-y-1"><Label className="text-xs">Productcode (zakelijke SKU)</Label>
            <Input data-testid="input-daily-codecol" inputMode="numeric" value={values.codeCol} onChange={e => set("codeCol", digits(e.target.value))} /></div>
          <div className="space-y-1"><Label className="text-xs">EAN</Label>
            <Input data-testid="input-daily-eancol" inputMode="numeric" value={values.eanCol} onChange={e => set("eanCol", digits(e.target.value))} /></div>
          <div className="space-y-1"><Label className="text-xs">Eerste dagkolom</Label>
            <Input data-testid="input-daily-daycol" inputMode="numeric" value={values.firstDayCol} onChange={e => set("firstDayCol", digits(e.target.value))} /></div>
        </div>
        <p className="text-xs text-muted-foreground">OEM wordt nooit als unieke sleutel gebruikt. ProductName wordt alleen als label getoond.</p>
      </div>
    </div>
  );
}
