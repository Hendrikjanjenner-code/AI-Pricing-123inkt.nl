/**
 * Client-side mapping of pre/post price CSVs to {sku, shop_id, price} rows.
 * Two layouts: "long" (one row per product+shop) and "wide" (one row per
 * product, one price column per printer label, e.g. the workbook A/E/I/J/K/L
 * layout). Blank cells are reported as missing and never sent as zero.
 */
import type { PriceRow, PrinterLabel } from "./api";

export type Delim = ";" | "," | "\t";
export type DecimalSep = "," | ".";
export interface ParsedCsv { header: string[]; rows: string[][]; delim: Delim }
export interface ColumnOption { index: number; letter: string; header: string }

export function colLetter(i: number): string {
  let s = ""; let n = i + 1;
  while (n > 0) { const m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); }
  return s;
}

function splitLine(line: string, d: Delim): string[] {
  const out: string[] = []; let cur = ""; let q = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (q) { if (c === '"') { if (line[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += c; }
    else if (c === '"') q = true;
    else if (c === d) { out.push(cur); cur = ""; }
    else cur += c;
  }
  out.push(cur);
  return out;
}

export function detectDelim(first: string): Delim {
  const count = (c: string) => first.split(c).length;
  const best = ([";", "\t", ","] as Delim[]).sort((a, b) => count(b) - count(a))[0];
  return best;
}

export function parseCsv(text: string, delim: Delim | "auto", hasHeader: boolean): ParsedCsv {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(l => l.trim() !== "");
  const d = delim === "auto" ? detectDelim(lines[0] ?? "") : delim;
  const all = lines.map(l => splitLine(l, d));
  const width = all.reduce((m, r) => Math.max(m, r.length), 0);
  const header = hasHeader && all.length ? all[0] : Array.from({ length: width }, () => "");
  return { header, rows: hasHeader ? all.slice(1) : all, delim: d };
}

export function columnOptions(p: ParsedCsv): ColumnOption[] {
  const width = Math.max(p.header.length, ...p.rows.slice(0, 50).map(r => r.length), 0);
  return Array.from({ length: width }, (_, i) => ({ index: i, letter: colLetter(i), header: (p.header[i] ?? "").trim() }));
}

export function normPrice(raw: string, dec: DecimalSep): string | null {
  const t = raw.trim().replace(/\s/g, "").replace(/^€/, "");
  if (!t) return null;
  const n = dec === "," ? t.replace(/\./g, "").replace(",", ".") : t.replace(/,/g, "");
  return /^\d+(\.\d+)?$/.test(n) ? n : "invalid";
}

export interface LongMapping { layout: "long"; sku: number; shop: number; price: number }
export interface WideMapping { layout: "wide"; sku: number; prices: Partial<Record<PrinterLabel, number>> }
export type Mapping = LongMapping | WideMapping;
export interface MapResult { rows: PriceRow[]; errors: string[]; missing: number; outside: number }

export function mapRows(p: ParsedCsv, m: Mapping, dec: DecimalSep, shops: Partial<Record<PrinterLabel, number>>): MapResult {
  const rows: PriceRow[] = []; const errors: string[] = []; let missing = 0; let outside = 0;
  const allowed = new Set(Object.values(shops));
  const lineNo = (i: number) => i + (p.header.some(Boolean) ? 2 : 1);
  p.rows.forEach((r, i) => {
    const sku = (r[m.sku] ?? "").trim();
    if (!sku) { errors.push(`Regel ${lineNo(i)}: productcode leeg`); return; }
    if (m.layout === "long") {
      const shop = Number((r[m.shop] ?? "").trim());
      if (!Number.isInteger(shop) || shop <= 0) { errors.push(`Regel ${lineNo(i)}: ongeldige shop_id`); return; }
      if (!allowed.has(shop)) { outside++; return; }
      const price = normPrice(r[m.price] ?? "", dec);
      if (price === null) { missing++; return; }
      if (price === "invalid") { errors.push(`Regel ${lineNo(i)}: prijs ongeldig (${r[m.price]})`); return; }
      rows.push({ sku, shop_id: shop, price });
    } else {
      for (const [label, col] of Object.entries(m.prices) as [PrinterLabel, number][]) {
        const shop = shops[label];
        if (shop === undefined || col === undefined) continue;
        const price = normPrice(r[col] ?? "", dec);
        if (price === null) { missing++; continue; }
        if (price === "invalid") { errors.push(`Regel ${lineNo(i)} ${label}: prijs ongeldig (${r[col]})`); continue; }
        rows.push({ sku, shop_id: shop, price });
      }
    }
  });
  return { rows, errors, missing, outside };
}

/** Workbook-inferred layout: A=product, E=123inkt, I=Printerland, J=Printabout, K=Sneltoner, L=Tonershop. Unconfirmed. */
export const WORKBOOK_WIDE: WideMapping = { layout: "wide", sku: 0, prices: { "123inkt": 4, Printerland: 8, Printabout: 9, Sneltoner: 10, Tonershop: 11 } };
