import { useState } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCmHistory, useCmRecord } from "@/hooks/use-channelmanager";
import type { CmScope } from "@/hooks/use-channelmanager";
import { errLines, fmtDate } from "@/lib/channelmanager/api";
import type { SnapshotKind } from "@/lib/channelmanager/api";
import type { Snapshot } from "@/lib/channelmanager/model";

export function Field({ label, error, hint, children }: { label: string; error?: string | null; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="font-medium text-muted-foreground uppercase tracking-wide">{label}</span>
      {children}
      {error ? <span className="text-destructive" role="alert">{error}</span> : hint ? <span className="text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

export const inputCls = "h-9 rounded-md border bg-background px-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-60";

/** Exact de statussen die de backend schrijft. */
export const STATUS_NL: Record<string, string> = {
  active: "Actief", staged: "Klaargezet", approved: "Goedgekeurd", preview: "Preview", exported: "Geëxporteerd",
  matched: "Volledig overeenkomend", partial: "Gedeeltelijk", running: "Bezig", success: "Geslaagd", failed: "Mislukt",
};
const TONE: Record<string, string> = {
  active: "ok", approved: "ok", matched: "ok", success: "ok", exported: "info",
  staged: "warn", preview: "warn", partial: "warn", running: "warn", failed: "bad",
};
export function StatusBadge({ status }: { status: string }) {
  const tone = TONE[status];
  const cls = tone === "ok" ? "bg-emerald-500/10 text-emerald-700 border-emerald-600/30"
    : tone === "bad" ? "bg-destructive/10 text-destructive border-destructive/30"
    : tone === "warn" ? "bg-amber-500/10 text-amber-700 border-amber-600/30"
    : tone === "info" ? "bg-primary/10 text-primary border-primary/30" : "bg-muted text-muted-foreground border-border";
  return <span data-testid={`status-${status}`} className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{STATUS_NL[status] ?? `Onbekend: ${status}`}</span>;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { title, lines } = errLines(error);
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive flex items-start justify-between gap-3" role="alert" data-testid="status-error">
      <div><div className="font-medium">{title}</div>
        <ul className="mt-1 list-disc pl-4 text-xs space-y-0.5">{lines.map((l, i) => <li key={i} data-testid={`text-error-line-${i}`}>{l}</li>)}</ul>
      </div>
      {onRetry && <Button size="sm" variant="outline" onClick={onRetry} data-testid="button-retry">Opnieuw</Button>}
    </div>
  );
}

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border bg-card">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
        <h3 className="text-sm font-semibold">{title}</h3>{aside}
      </header>
      <div className="p-4 space-y-3">{children}</div>
    </section>
  );
}

export interface Col<R> { label: string; cell: (r: R) => ReactNode; mono?: boolean }
export function RowsTable<R>({ rows, columns, isBad, testid, step = 200 }: { rows: R[]; columns: Col<R>[]; isBad?: (r: R) => boolean; testid: string; step?: number }) {
  const [limit, setLimit] = useState(step);
  if (!rows.length) return <p className="text-sm text-muted-foreground" data-testid={`${testid}-empty`}>Geen rijen.</p>;
  return (
    <div className="space-y-2">
      <div className="max-h-[420px] overflow-auto rounded border" data-testid={testid}>
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-muted"><tr>
            <th className="px-2 py-1.5 text-left">#</th>
            {columns.map(c => <th key={c.label} className="px-2 py-1.5 text-left whitespace-nowrap">{c.label}</th>)}
          </tr></thead>
          <tbody>
            {rows.slice(0, limit).map((r, i) => (
              <tr key={i} className={`border-t align-top ${isBad?.(r) ? "bg-destructive/5" : ""}`} data-testid={`${testid}-row-${i}`}>
                <td className="px-2 py-1 text-muted-foreground">{i + 1}</td>
                {columns.map(c => <td key={c.label} className={`px-2 py-1 ${c.mono ? "font-mono tabular-nums" : ""}`}>{c.cell(r)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > limit && <Button size="sm" variant="ghost" onClick={() => setLimit(l => l + 500)} data-testid={`${testid}-more`}>Toon meer ({rows.length - limit} resterend)</Button>}
    </div>
  );
}

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0"><dt className="text-muted-foreground text-[11px]">{label}</dt><dd className="font-mono text-xs break-all">{children}</dd></div>;
}
export function Facts({ children }: { children: ReactNode }) {
  return <dl className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2">{children}</dl>;
}

export function NotesButton({ label, busy, disabled, onSubmit, testid, variant = "default", reason }: {
  label: string; busy: boolean; disabled?: boolean; onSubmit: (notes: string) => void; testid: string;
  variant?: "default" | "outline" | "secondary"; reason?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState("");
  if (!open) return (
    <div className="flex flex-col gap-1">
      <Button size="sm" variant={variant} disabled={disabled || busy} onClick={() => setOpen(true)} data-testid={testid}>{label}</Button>
      {reason && <span className="text-[11px] text-muted-foreground">{reason}</span>}
    </div>
  );
  return (
    <div className="flex w-full flex-col gap-2 rounded-md border p-2">
      <Textarea placeholder="Toelichting (verplicht, wordt geaudit)" maxLength={2000} value={notes} onChange={e => setNotes(e.target.value)} data-testid={`${testid}-notes`} className="text-sm" />
      <div className="flex gap-2">
        <Button size="sm" disabled={busy || !notes.trim()} onClick={() => { onSubmit(notes.trim()); setOpen(false); setNotes(""); }} data-testid={`${testid}-confirm`}>{busy ? "Bezig…" : `Bevestig: ${label}`}</Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)} data-testid={`${testid}-cancel`}>Annuleren</Button>
      </div>
    </div>
  );
}

export function HistoryList({ scope, kind, onSelect, selectedId, title }: {
  scope: CmScope; kind: SnapshotKind; onSelect?: (s: Snapshot) => void; selectedId?: number | null; title: string;
}) {
  const [offset, setOffset] = useState(0);
  const limit = 20;
  const q = useCmHistory(scope, kind, offset, limit);
  return (
    <Section title={title} aside={
      <div className="flex items-center gap-1">
        <Button size="icon" variant="ghost" className="h-7 w-7" disabled={offset === 0} onClick={() => setOffset(o => Math.max(0, o - limit))} data-testid={`button-prev-${kind}`} aria-label="Vorige"><ChevronLeft className="h-4 w-4" /></Button>
        <span className="text-xs text-muted-foreground">{q.data?.items.length ? `${offset + 1}–${offset + q.data.items.length}` : "0"}</span>
        <Button size="icon" variant="ghost" className="h-7 w-7" disabled={!q.data?.has_more} onClick={() => setOffset(o => o + limit)} data-testid={`button-next-${kind}`} aria-label="Volgende"><ChevronRight className="h-4 w-4" /></Button>
      </div>
    }>
      {q.isLoading ? <Skeleton className="h-24" /> : q.isError ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> :
        !q.data?.items.length ? <p className="text-sm text-muted-foreground" data-testid={`text-history-empty-${kind}`}>Nog geen historie.</p> : (
          <ul className="divide-y text-sm">
            {q.data.items.map(s => (
              <li key={s.id}>
                <button type="button" onClick={() => onSelect?.(s)} disabled={!onSelect}
                  className={`flex w-full items-center gap-3 px-1 py-1.5 text-left hover:bg-muted/50 ${selectedId === s.id ? "bg-primary/5" : ""}`}
                  data-testid={`row-history-${kind}-${s.id}`}>
                  <span className="font-mono text-xs w-14">#{s.id}</span>
                  <span className="text-xs text-muted-foreground w-10">r{s.revision}</span>
                  <StatusBadge status={s.status} />
                  <span className="ml-auto text-xs text-muted-foreground">{fmtDate(s.created_at)} · {s.created_by}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
    </Section>
  );
}

export function RecordLoader<T>({ scope, id, parse, onClose, children }: { scope: CmScope; id: number; parse: (v: unknown) => T; onClose: () => void; children: (v: T) => ReactNode }) {
  const q = useCmRecord(scope, id, parse);
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">Record #{id}</span>
        <Button size="sm" variant="ghost" onClick={onClose} data-testid="button-close-record"><X className="h-4 w-4 mr-1" />Sluiten</Button>
      </div>
      {q.isLoading ? <Skeleton className="h-40" /> : q.isError ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : q.data !== undefined ? children(q.data) : null}
    </div>
  );
}
