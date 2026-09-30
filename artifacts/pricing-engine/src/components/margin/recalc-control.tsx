import { Button } from "@/components/ui/button";
import { Loader2, RefreshCw, CheckCircle2, AlertTriangle, Clock } from "lucide-react";
import { dt, type MarginInsight } from "@/lib/drs-daily-api";
import { isRunActive } from "@/hooks/use-margin-insight";

interface Props {
  insight: MarginInsight | undefined;
  starting: boolean;
  onRecalculate: () => void;
  shopName?: string;
}

/** Expliciete, shop-gescopeerde herberekenknop met duurzame runstatus. */
export function RecalcControl({ insight, starting, onRecalculate, shopName }: Props) {
  const run = insight?.run ?? null;
  const confirmed = insight?.source.status === "confirmed";
  const active = isRunActive(run?.status);
  const failed = run?.status?.toLowerCase() === "failed";
  const fresh = insight?.expected.status === "fresh";

  return (
    <div className="flex flex-wrap items-center gap-3 text-xs" data-testid="panel-recalc">
      <Button size="sm" onClick={onRecalculate} disabled={!confirmed || active || starting} data-testid="button-margin-recalculate">
        {active || starting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
        {active ? "Herberekening loopt" : `Adviezen herberekenen${shopName ? ` voor ${shopName}` : ""}`}
      </Button>
      <span data-testid="status-margin-run" className="flex items-center gap-1 text-muted-foreground">
        {!confirmed ? <><AlertTriangle className="h-3 w-3 text-amber-600" />Eerst dagverkoop bevestigen</>
          : !run ? <><Clock className="h-3 w-3" />Nog geen herberekening met deze verkoopdata</>
          : active ? <>Gestart {dt(run.started_at)} — status wordt automatisch ververst</>
          : failed ? <span className="text-red-700 flex items-center gap-1"><AlertTriangle className="h-3 w-3" />Mislukt: {run.error_message || "onbekende fout"}</span>
          : fresh ? <><CheckCircle2 className="h-3 w-3 text-emerald-600" />Berekend met nieuwste verkoopdata, {dt(run.completed_at)}</>
          : <><AlertTriangle className="h-3 w-3 text-amber-600" />Laatste run {dt(run.completed_at)} gebruikt niet de nieuwste verkoopdata</>}
      </span>
      <span className="text-muted-foreground">Keurt geen prijzen goed en voert niets uit; menselijke besluiten blijven staan.</span>
    </div>
  );
}
