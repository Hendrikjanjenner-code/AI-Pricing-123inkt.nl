import { useState } from "react";
import type { DragEvent, KeyboardEvent } from "react";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SOURCE_INFO, isMarket, moveItem } from "@/lib/cost-priority/model";

export function PriorityList({ order, onChange, disabled, testPrefix }: {
  order: string[]; onChange: (o: string[]) => void; disabled?: boolean; testPrefix: string;
}) {
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [overIdx, setOverIdx] = useState<number | null>(null);
  const [live, setLive] = useState("");
  const slug = (s: string) => s.replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase();

  const move = (from: number, to: number) => {
    if (disabled) return;
    const next = moveItem(order, from, to);
    if (next !== order) { onChange(next); setLive(`${order[from]} verplaatst naar prioriteit ${to + 1}`); }
  };
  const onDrop = (e: DragEvent, to: number) => { e.preventDefault(); if (dragIdx !== null) move(dragIdx, to); setDragIdx(null); setOverIdx(null); };
  const onKey = (e: KeyboardEvent, i: number) => {
    if (!e.altKey) return;
    if (e.key === "ArrowUp") { e.preventDefault(); move(i, i - 1); }
    if (e.key === "ArrowDown") { e.preventDefault(); move(i, i + 1); }
  };

  return (
    <>
      <ol className="space-y-2" aria-label="Kostprioriteit" data-testid={`list-priorities-${testPrefix}`}>
        {order.map((src, i) => {
          const info = SOURCE_INFO[src];
          const id = slug(src);
          return (
            <li
              key={src}
              draggable={!disabled}
              tabIndex={0}
              aria-label={`Prioriteit ${i + 1}: ${src}. Alt+pijl omhoog of omlaag om te verplaatsen.`}
              onKeyDown={e => onKey(e, i)}
              onDragStart={e => { setDragIdx(i); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", src); }}
              onDragOver={e => { e.preventDefault(); setOverIdx(i); }}
              onDragLeave={() => setOverIdx(o => (o === i ? null : o))}
              onDrop={e => onDrop(e, i)}
              onDragEnd={() => { setDragIdx(null); setOverIdx(null); }}
              className={`flex items-center gap-3 rounded-md border bg-background p-3 transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${dragIdx === i ? "opacity-50" : ""} ${overIdx === i && dragIdx !== i ? "-translate-y-0.5 border-primary" : ""}`}
              data-testid={`card-source-${id}`}
            >
              <GripVertical className={`h-4 w-4 text-muted-foreground ${disabled ? "" : "cursor-grab"}`} aria-hidden />
              <span className="w-14 shrink-0 font-mono text-xs font-semibold text-primary" data-testid={`text-prio-${id}`}>Prio {i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 font-medium">
                  <span data-testid={`text-source-name-${id}`}>{src}</span>
                  {isMarket(src) && <Badge variant="outline" className="border-amber-500 text-[10px] text-amber-700" data-testid={`badge-market-${id}`}>Marktterugval — geen geverifieerde historische kostprijs</Badge>}
                  {!info && <Badge variant="secondary" className="text-[10px]" data-testid={`badge-custom-${id}`}>Vijfde bron</Badge>}
                  {i === order.length - 1 && <Badge variant="outline" className="text-[10px]">Laatste: 0 wordt gekozen</Badge>}
                </div>
                <div className="text-xs text-muted-foreground">{info?.uitleg ?? "Eigen numerieke bron; waarde via handmatige invoer of gelijknamige werkboekkolom."}</div>
              </div>
              <div className="flex gap-1">
                <Button size="icon" variant="ghost" className="h-7 w-7" disabled={disabled || i === 0} onClick={() => move(i, i - 1)} aria-label={`${src} omhoog`} data-testid={`button-up-${id}`}><ArrowUp className="h-4 w-4" /></Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" disabled={disabled || i === order.length - 1} onClick={() => move(i, i + 1)} aria-label={`${src} omlaag`} data-testid={`button-down-${id}`}><ArrowDown className="h-4 w-4" /></Button>
              </div>
            </li>
          );
        })}
      </ol>
      <div aria-live="polite" className="sr-only">{live}</div>
    </>
  );
}
