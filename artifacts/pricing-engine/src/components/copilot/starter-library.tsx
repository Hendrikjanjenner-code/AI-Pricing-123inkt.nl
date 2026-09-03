import { CopilotStarter } from "@workspace/api-client-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Sparkles, MessageSquarePlus } from "lucide-react";

export function StarterLibraryDialog({
  open,
  onOpenChange,
  starters,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  starters: CopilotStarter[];
  onSelect: (starter?: CopilotStarter) => void;
}) {
  // Group starters by module_label
  const grouped = starters.reduce((acc, s) => {
    const label = s.module_label || "Overig";
    if (!acc[label]) acc[label] = [];
    acc[label].push(s);
    return acc;
  }, {} as Record<string, CopilotStarter[]>);

  // competition prominent -> ensure "Concurrentie" or "Competition" comes first
  const sortedLabels = Object.keys(grouped).sort((a, b) => {
    const aLower = a.toLowerCase();
    const bLower = b.toLowerCase();
    const aIsComp = aLower.includes("concurrentie") || aLower.includes("competition");
    const bIsComp = bLower.includes("concurrentie") || bLower.includes("competition");
    if (aIsComp && !bIsComp) return -1;
    if (!aIsComp && bIsComp) return 1;
    return a.localeCompare(b);
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-4xl flex flex-col p-0" data-testid="dialog-starter-library">
        <DialogHeader className="px-6 pt-6 pb-2">
          <DialogTitle className="flex items-center gap-2 text-xl font-semibold">
            <Sparkles className="h-5 w-5 text-primary" /> Nieuw gesprek starten
          </DialogTitle>
          <DialogDescription>
            Kies een gespreksonderwerp om de Copilot gericht de juiste data te laten analyseren, of start een blanco gesprek.
          </DialogDescription>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-6">
          <div className="space-y-3">
            <div className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Algemeen</div>
            <button
              type="button"
              data-testid="button-starter-blank"
              className="w-full text-left rounded-xl border bg-card p-4 transition-all hover:border-primary hover:shadow-sm"
              onClick={() => onSelect()}
            >
              <div className="flex items-center gap-2 mb-1">
                <MessageSquarePlus className="h-4 w-4 text-muted-foreground" />
                <h3 className="font-semibold">Blanco gesprek</h3>
              </div>
              <p className="text-sm text-muted-foreground ml-6">
                Start een nieuw gesprek zonder vooraf ingestelde context.
              </p>
            </button>
          </div>

          {sortedLabels.map((label) => (
            <div key={label} className="space-y-3">
              <div className="text-sm font-medium text-muted-foreground uppercase tracking-wider">{label}</div>
              <div className="grid gap-3 md:grid-cols-2">
                {grouped[label].map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    data-testid={`button-starter-${s.key}`}
                    disabled={!s.available}
                    className={`text-left rounded-xl border p-4 transition-all ${
                      s.available
                        ? "bg-card hover:border-primary hover:shadow-sm cursor-pointer"
                        : "bg-muted/50 opacity-60 cursor-not-allowed"
                    }`}
                    onClick={() => s.available && onSelect(s)}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <h3 className="text-sm font-semibold line-clamp-1" title={s.title}>
                        {s.title}
                      </h3>
                      {!s.available && s.availability_reason && (
                        <Badge
                          variant="outline"
                          className="shrink-0 whitespace-nowrap border-amber-200 bg-amber-50 text-[10px] text-amber-900"
                        >
                          {s.availability_reason}
                        </Badge>
                      )}
                    </div>
                    <p className="mb-1.5 text-xs font-medium text-foreground line-clamp-2" title={s.question}>
                      "{s.question}"
                    </p>
                    <p className="text-xs text-muted-foreground line-clamp-2" title={s.description}>
                      {s.description}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
