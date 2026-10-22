import type { ChannelInputRow } from "@workspace/api-client-react";
import { decError } from "./api";
import type { BasisCsvMapping } from "./api";

type FieldKey = keyof BasisCsvMapping;

export function manualRowErrors(rows: Record<FieldKey, string>[]): string[][] {
  const skus = rows.map(r => r.sku.trim());
  return rows.map((r, i) => {
    const e: string[] = [];
    if (!r.sku.trim()) e.push("SKU verplicht");
    else if (skus.indexOf(r.sku.trim()) !== i) e.push("Dubbele SKU");
    (["sku", "name", "category"] as const).forEach(k => { if (r[k].length > 500) e.push(`${k}: max 500 tekens`); });
    const bp = decError(r.base_price, { required: true }); if (bp) e.push(`Basisprijs: ${bp}`);
    const c = decError(r.cost); if (c) e.push(`Kost: ${c}`);
    const cp = decError(r.current_price); if (cp) e.push(`Huidig: ${cp}`);
    return e;
  });
}
export function toInputRows(rows: Record<FieldKey, string>[]): ChannelInputRow[] {
  return rows.map(r => ({
    sku: r.sku.trim(), name: r.name.trim(), category: r.category.trim(), base_price: r.base_price.trim(),
    cost: r.cost.trim() || null, current_price: r.current_price.trim() || null,
  }));
}

