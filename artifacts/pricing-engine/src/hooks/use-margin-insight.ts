import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useDrsScope } from "@/hooks/use-drs-scope";
import { drsApi, type MarginInsight } from "@/lib/drs-daily-api";
import { useToast } from "@/hooks/use-toast";

const ACTIVE = new Set(["queued", "pending", "running", "started"]);
export const isRunActive = (s?: string | null) => !!s && ACTIVE.has(s.toLowerCase());

export const marginInsightKey = (userKey: string, shopId: number | undefined, filterQs: string) =>
  ["drs-margin-insight", userKey, shopId, filterQs] as const;

/** Prefix voor alle legacy dashboard-queries (summary/charts) per gebruiker/winkel. */
export const dashboardScopeKey = (userKey: string, shopId: number | undefined) =>
  ["dashboard", userKey, shopId] as const;

/**
 * Marge-inzicht + shop-gescopeerde herberekening. De runstatus is duurzaam
 * server-side; polling herstart na reload zodra de run nog loopt.
 */
export function useMarginInsight(filterQs = "", enabled = true) {
  const scope = useDrsScope();
  const { shopId, userKey, scopeToken, isCurrent } = scope;
  const qc = useQueryClient();
  const { toast } = useToast();
  const [starting, setStarting] = useState(false);

  const query = useQuery<MarginInsight>({
    queryKey: marginInsightKey(userKey, shopId, filterQs),
    queryFn: () => drsApi.marginInsight(shopId as number, filterQs),
    enabled: enabled && shopId !== undefined,
    refetchInterval: q => (isRunActive(q.state.data?.run?.status) ? 4000 : false),
  });

  // Run afgerond (running -> completed/failed): legacy KPI's en grafieken verversen
  // zodat summary/categorie hetzelfde adviessnapshot tonen als de bronkaart.
  const runStatus = query.data?.run?.status;
  const runId = query.data?.run?.id;
  const prevRun = useRef<{ token: string | null; id?: number; status?: string }>({ token: null });
  useEffect(() => {
    const prev = prevRun.current;
    prevRun.current = { token: scopeToken, id: runId, status: runStatus };
    if (prev.token !== scopeToken || !runStatus) return;
    const finishedNow = !isRunActive(runStatus) && (isRunActive(prev.status) || (prev.id !== undefined && prev.id !== runId));
    if (finishedNow) qc.invalidateQueries({ queryKey: dashboardScopeKey(userKey, shopId) });
  }, [runStatus, runId, scopeToken, userKey, shopId, qc]);

  const recalculate = async () => {
    if (shopId === undefined || starting) return;
    const token = scopeToken;
    setStarting(true);
    try {
      const run = await drsApi.marginRecalculate(shopId);
      if (!isCurrent(token)) return;
      qc.setQueriesData<MarginInsight>({ queryKey: ["drs-margin-insight", userKey, shopId] }, old => (old ? { ...old, run } : old));
      qc.invalidateQueries({ queryKey: ["drs-margin-insight", userKey, shopId] });
      toast({ title: "Herberekening gestart", description: "Adviezen worden voor de hele winkel herberekend. Prijsbesluiten blijven behouden." });
    } catch (e: any) {
      if (!isCurrent(token)) return;
      const title = e.status === 409 ? "Geen bevestigde verkoop" : e.status === 403 ? "Geen rechten voor herberekening" : e.status === 404 ? "Winkel niet beschikbaar" : "Herberekenen mislukt";
      toast({ title, description: e.message, variant: "destructive" });
    } finally { if (isCurrent(token)) setStarting(false); }
  };

  return { ...scope, query, recalculate, starting };
}
