/** Leest alleen de kopregel van een CSV lokaal, om kolommen te kunnen koppelen. Geen rekenwerk. */
export async function readCsvHeader(file: File, delimiter: string): Promise<string[]> {
  const head = await file.slice(0, 64 * 1024).text();
  const line = head.replace(/^\uFEFF/, "").split(/\r?\n/)[0] ?? "";
  const out: string[] = []; let cur = ""; let q = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (q) { if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; }
    else if (c === '"') q = true;
    else if (c === delimiter) { out.push(cur.trim()); cur = ""; }
    else cur += c;
  }
  out.push(cur.trim());
  return out.filter(Boolean);
}

export function guessDelimiter(sample: string): string {
  const first = sample.split(/\r?\n/)[0] ?? "";
  const counts = [";", ",", "\t", "|"].map(d => [d, first.split(d).length] as const);
  return counts.sort((a, b) => b[1] - a[1])[0][0];
}

/** Lokale generieke voorbeeldsjabloon met de canonieke kolommen (geen echte data). */
export function downloadTemplate(kind: "basis" | "readback", delimiter: string) {
  const cols = kind === "basis" ? ["sku", "name", "category", "base_price", "cost", "current_price"] : ["sku", "actual_price"];
  const blob = new Blob([cols.join(delimiter) + "\n"], { type: "text/csv;charset=utf-8" });
  saveBlob(blob, `channelmanager-${kind}-sjabloon.csv`);
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const DELIMITERS: { value: string; label: string }[] = [
  { value: ";", label: "Puntkomma ;" }, { value: ",", label: "Komma ," }, { value: "\t", label: "Tab" }, { value: "|", label: "Pipe |" },
];
export const DECIMALS: { value: string; label: string }[] = [{ value: ",", label: "Komma (12,50)" }, { value: ".", label: "Punt (12.50)" }];
