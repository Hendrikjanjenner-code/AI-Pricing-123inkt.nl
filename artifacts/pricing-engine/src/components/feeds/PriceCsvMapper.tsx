import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Field, inputCls } from "@/components/channelmanager/common";
import { PRINTER_LABELS } from "@/lib/feeds/api";
import type { PriceRow, PrinterLabel } from "@/lib/feeds/api";
import { WORKBOOK_WIDE, columnOptions, mapRows, parseCsv } from "@/lib/feeds/price-csv";
import type { DecimalSep, Delim, Mapping } from "@/lib/feeds/price-csv";

/**
 * Upload or paste a CSV and map it explicitly. Emits rows only when the
 * mapping is complete, parsing has no errors and the operator confirmed the
 * column assignment. Shop columns use the saved printer config mapping.
 */
export function PriceCsvMapper({ id, label, shops, onRows }: {
  id: string; label: string; shops: Partial<Record<PrinterLabel, number>>; onRows: (rows: PriceRow[] | null) => void;
}) {
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [delim, setDelim] = useState<Delim | "auto">("auto");
  const [dec, setDec] = useState<DecimalSep>(",");
  const [hasHeader, setHasHeader] = useState(true);
  const [mapping, setMapping] = useState<Mapping>(WORKBOOK_WIDE);
  const [confirmed, setConfirmed] = useState(false);

  const parsed = useMemo(() => text.trim() ? parseCsv(text, delim, hasHeader) : null, [text, delim, hasHeader]);
  const cols = useMemo(() => parsed ? columnOptions(parsed) : [], [parsed]);
  const result = useMemo(() => parsed ? mapRows(parsed, mapping, dec, shops) : null, [parsed, mapping, dec, shops]);
  const usedCols = mapping.layout === "long" ? [mapping.sku, mapping.shop, mapping.price]
    : [mapping.sku, ...PRINTER_LABELS.filter(l => shops[l] !== undefined).map(l => mapping.prices[l]).filter((c): c is number => c !== undefined)];
  const outOfRange = usedCols.some(c => c >= cols.length);
  const unnamed = usedCols.filter(c => c < cols.length && !cols[c].header);
  const unmappedShops = mapping.layout === "wide" ? PRINTER_LABELS.filter(l => shops[l] !== undefined && mapping.prices[l] === undefined) : [];
  const ok = !!result && !outOfRange && confirmed && result.errors.length === 0 && result.rows.length > 0;

  const onRowsRef = useRef(onRows); onRowsRef.current = onRows;
  useEffect(() => { onRowsRef.current(ok && result ? result.rows : null); }, [ok, result]);
  // Any change to source or mapping requires re-confirmation.
  useEffect(() => { setConfirmed(false); }, [text, delim, dec, hasHeader, mapping]);

  const colSelect = (value: number | undefined, onChange: (v: number | undefined) => void, testid: string, optional = false) => (
    <select className={inputCls} value={value ?? ""} onChange={e => onChange(e.target.value === "" ? undefined : Number(e.target.value))} data-testid={testid}>
      {optional && <option value="">Niet gebruiken</option>}
      {!cols.length && value !== undefined && <option value={value}>Kolom {String.fromCharCode(65 + value)}</option>}
      {cols.map(c => <option key={c.index} value={c.index}>{c.letter}{c.header ? ` · ${c.header}` : " · (geen kop)"}</option>)}
    </select>
  );

  return (
    <div className="space-y-3" data-testid={`mapper-${id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <input type="file" accept=".csv,text/csv,.txt" className="text-xs" data-testid={`input-${id}-file`}
          onChange={async e => { const f = e.target.files?.[0]; if (f) { setFileName(f.name); setText(await f.text()); } }} />
        <span className="text-[11px] text-muted-foreground">{label}{fileName ? ` · ${fileName}` : ""}. Of plak hieronder.</span>
      </div>
      <textarea className="min-h-[70px] w-full rounded-md border bg-background p-2 font-mono text-[11px]" value={text}
        onChange={e => { setFileName(null); setText(e.target.value); }} placeholder="Plak CSV-inhoud" data-testid={`input-${id}-text`} />

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Indeling">
          <select className={inputCls} value={mapping.layout} data-testid={`select-${id}-layout`}
            onChange={e => setMapping(e.target.value === "long" ? { layout: "long", sku: 0, shop: 1, price: 2 } : WORKBOOK_WIDE)}>
            <option value="wide">Breed: kolom per winkel</option><option value="long">Lang: regel per product en winkel</option>
          </select></Field>
        <Field label="Scheidingsteken">
          <select className={inputCls} value={delim} onChange={e => setDelim(e.target.value as Delim | "auto")} data-testid={`select-${id}-delim`}>
            <option value="auto">Automatisch{parsed ? ` (${parsed.delim === "\t" ? "tab" : parsed.delim})` : ""}</option><option value=";">Puntkomma</option><option value=",">Komma</option><option value={"\t"}>Tab</option>
          </select></Field>
        <Field label="Decimaalteken">
          <select className={inputCls} value={dec} onChange={e => setDec(e.target.value as DecimalSep)} data-testid={`select-${id}-decimal`}>
            <option value=",">Komma (24,95)</option><option value=".">Punt (24.95)</option>
          </select></Field>
        <label className="flex items-end gap-2 pb-2 text-xs"><input type="checkbox" checked={hasHeader} onChange={e => setHasHeader(e.target.checked)} data-testid={`check-${id}-header`} />Eerste regel is kopregel</label>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Productcode">{colSelect(mapping.sku, v => setMapping({ ...mapping, sku: v ?? 0 }), `select-${id}-col-sku`)}</Field>
        {mapping.layout === "long" ? <>
          <Field label="Shop-ID">{colSelect(mapping.shop, v => setMapping({ ...mapping, shop: v ?? 0 }), `select-${id}-col-shop`)}</Field>
          <Field label="Prijs">{colSelect(mapping.price, v => setMapping({ ...mapping, price: v ?? 0 }), `select-${id}-col-price`)}</Field>
        </> : PRINTER_LABELS.filter(l => shops[l] !== undefined).map(l => (
          <Field key={l} label={`${l} (shop #${shops[l]})`}>{colSelect(mapping.prices[l], v => setMapping({ ...mapping, prices: { ...mapping.prices, [l]: v } }), `select-${id}-col-${l}`, true)}</Field>
        ))}
      </div>
      {mapping.layout === "wide" && <p className="text-[11px] text-muted-foreground">Standaard A/E/I/J/K/L is afgeleid uit de werkboekformules en niet bevestigd. Controleer elke kolom.</p>}

      {parsed && (
        <div className="space-y-1 text-xs" data-testid={`status-${id}-parse`}>
          {outOfRange && <div className="text-destructive">Een gekozen kolom bestaat niet in dit bestand.</div>}
          {unnamed.length > 0 && <div className="flex items-center gap-1 text-amber-700"><AlertTriangle className="h-3.5 w-3.5" />Kolom {unnamed.map(c => cols[c].letter).join(", ")} heeft geen kop: toewijzing onbevestigd.</div>}
          {unmappedShops.length > 0 && <div className="text-amber-700">Geen kolom voor {unmappedShops.join(", ")}: die preprijzen ontbreken en blokkeren de berekening.</div>}
          {result && <div className={result.errors.length ? "text-destructive" : "text-foreground"}>
            {parsed.rows.length} regels gelezen → {result.rows.length} prijsrijen · {result.missing} lege cellen (ontbreekt, niet 0)
            {result.outside ? ` · ${result.outside} regels voor niet-gekoppelde winkels overgeslagen` : ""}
            {result.errors.length ? ` · ${result.errors.length} fouten, niets wordt verzonden` : ""}</div>}
          {result && result.errors.length > 0 && <ul className="max-h-28 list-disc overflow-auto pl-4 text-destructive">{result.errors.slice(0, 50).map((e, i) => <li key={i}>{e}</li>)}</ul>}
          {result && result.rows.length > 0 && (
            <div className="max-h-36 overflow-auto rounded border"><table className="w-full font-mono text-[11px]">
              <thead className="sticky top-0 bg-muted"><tr><th className="px-2 text-left">sku</th><th className="px-2 text-left">shop_id</th><th className="px-2 text-right">prijs</th></tr></thead>
              <tbody>{result.rows.slice(0, 15).map((r, i) => <tr key={i} className="border-t"><td className="px-2">{r.sku}</td><td className="px-2">{r.shop_id}</td><td className="px-2 text-right">{r.price}</td></tr>)}</tbody>
            </table></div>
          )}
          <label className="flex items-center gap-2 pt-1"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} disabled={!result || outOfRange} data-testid={`check-${id}-confirmed`} />
            Ik heb de kolomtoewijzing en het voorbeeld gecontroleerd</label>
        </div>
      )}
    </div>
  );
}
