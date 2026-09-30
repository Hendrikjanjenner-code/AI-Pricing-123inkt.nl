import { Badge } from "@/components/ui/badge";
import { Info, AlertTriangle, ArrowRight } from "lucide-react";
import { type DailyPreview, type ImportPhase, eurOrDash, num, dt } from "@/lib/drs-daily-api";

const PHASES: Array<{ key: ImportPhase | "preview"; label: string }> = [
  { key: "preview", label: "Preview" },
  { key: "mappings_only", label: "Alleen koppelingen" },
  { key: "confirmed", label: "Verkoop verwerkt" },
];

export const PHASE_LABEL: Record<ImportPhase, string> = {
  blocked: "Preview geblokkeerd — geen verkoop geschreven",
  ready: "Preview klaar — nog geen verkoop geschreven",
  mappings_only: "Alleen koppelingen vastgelegd — geen verkoop geschreven",
  confirmed: "Verkoop verwerkt",
  confirmed_missing: "Verkoop verwerkt — aantallen niet beschikbaar",
};

const PHASE_CLASS: Record<ImportPhase, string> = {
  blocked: "bg-red-50 text-red-700 border-red-200",
  ready: "bg-primary/10 text-primary border-primary/20",
  mappings_only: "bg-amber-50 text-amber-800 border-amber-200",
  confirmed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  confirmed_missing: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

export function PreviewSummary({ preview, phase, shopName }: { preview: DailyPreview; phase: ImportPhase; shopName: string }) {
  const stepIndex = phase === "confirmed" || phase === "confirmed_missing" ? 2 : phase === "mappings_only" ? 1 : 0;
  const salesWritten = preview.mapping_result?.sales_written ?? 0;
  return (
    <div className="space-y-3">
      <ol className="flex flex-wrap items-center gap-1 text-xs" data-testid="steps-daily-phase" aria-label="Importfase">
        {PHASES.map((p, i) => (
          <li key={p.key} className="flex items-center gap-1">
            <span className={`rounded-full border px-2 py-0.5 ${i === stepIndex ? "border-primary bg-primary text-primary-foreground" : i < stepIndex ? "border-primary/40 text-primary" : "text-muted-foreground"}`}>{p.label}</span>
            {i < PHASES.length - 1 && <ArrowRight className="h-3 w-3 text-muted-foreground" />}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge data-testid="status-daily" className={PHASE_CLASS[phase]}>{PHASE_LABEL[phase]}</Badge>
        <span className="text-muted-foreground" data-testid="text-daily-scope">{shopName} · {preview.period_start} t/m {preview.period_end}</span>
        <span className="font-mono text-xs text-muted-foreground" data-testid="text-daily-stage">stage {String(preview.stage_id)}</span>
        {preview.expires_at && phase !== "confirmed" && <span className="text-xs text-muted-foreground">Preview geldig tot {dt(preview.expires_at)}</span>}
        {preview.result?.confirmed_at && <span className="text-xs text-muted-foreground">Bevestigd {dt(preview.result.confirmed_at)}</span>}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {([
          ["Artikelen", num(preview.product_count), "products"],
          ["Dagregels", num(preview.fact_count), "facts"],
          ["Blokkades", num(preview.error_count), "errors"],
          ["Afzet (stuks)", num(preview.totals.quantity), "quantity"],
          ["Omzet excl. btw", eurOrDash(preview.totals.revenue_excl_vat), "rev-excl"],
          ["Omzet incl. btw", eurOrDash(preview.totals.revenue_incl_vat), "rev-incl"],
        ] as const).map(([l, v, id]) => (
          <div key={id} className={`rounded-md border p-3 ${id === "errors" && preview.error_count > 0 ? "border-red-200 bg-red-50/40" : ""}`}>
            <div className="text-lg font-semibold tabular-nums" data-testid={`text-daily-${id}`}>{v}</div>
            <div className="text-xs text-muted-foreground">{l}</div>
          </div>
        ))}
      </div>
      {phase !== "confirmed" && phase !== "confirmed_missing" && (
        <p className="text-xs text-muted-foreground" data-testid="text-daily-not-written">
          Geschreven dagverkoop: {num(salesWritten)} regels. Bovenstaande aantallen komen uit de preview en zijn nog niet vastgelegd.
        </p>
      )}
      <div className="text-xs text-muted-foreground flex items-start gap-1">
        <Info className="w-3 h-3 mt-0.5 shrink-0" />
        Aantallen en bedragen worden exact (met teken) overgenomen. Retourverwerking in DRS is niet geverifieerd;
        dit is niet als geverifieerde netto-omzet te lezen.
      </div>
      {preview.warnings.map((w, i) => (
        <div key={i} className="text-xs text-amber-700 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}</div>
      ))}
    </div>
  );
}
