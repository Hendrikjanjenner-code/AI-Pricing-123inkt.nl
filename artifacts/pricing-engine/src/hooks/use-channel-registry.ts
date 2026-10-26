import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";
import type { CmScope } from "@/hooks/use-channelmanager";
import { CmError, errText } from "@/lib/channelmanager/api";
import { regApi, regKeys } from "@/lib/channelmanager/registry";
import type { Registry } from "@/lib/channelmanager/registry";

export function useChannelRegistry(scope: CmScope) {
  return useQuery({
    queryKey: regKeys.list(scope.userKey, scope.shopId),
    queryFn: ({ signal }) => regApi.list(scope.shopId, signal),
    staleTime: 10_000,
    retry: 1,
  });
}

/** Voert een registermutatie uit; resultaat wordt alleen toegepast als winkel/gebruiker nog dezelfde is. */
export function useRegistryAction(scope: CmScope) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const busyRef = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const run = useCallback(async (label: string, fn: () => Promise<Registry>, ok?: string): Promise<boolean> => {
    if (busyRef.current) return false;
    const token = scope.scopeToken;
    const key = regKeys.list(scope.userKey, scope.shopId);
    const live = () => mounted.current && scope.isCurrent(token);
    busyRef.current = true;
    setBusy(label); setError(null);
    try {
      const reg = await fn();
      if (!live()) return false;
      qc.setQueryData(key, reg);
      if (ok) toast({ title: ok });
      return true;
    } catch (e) {
      if (!live()) return false;
      if (e instanceof CmError && e.status === 409) {
        toast({ title: "Register is intussen gewijzigd", description: "De nieuwste versie is geladen; controleer en probeer opnieuw.", variant: "destructive" });
        void qc.invalidateQueries({ queryKey: key });
      } else toast({ title: "Actie mislukt", description: errText(e), variant: "destructive" });
      setError(e);
      return false;
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(null);
    }
  }, [qc, toast, scope]);
  return { run, busy, error };
}
