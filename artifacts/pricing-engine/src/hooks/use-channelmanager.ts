import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { cmApi, cmKeys, errText } from "@/lib/channelmanager/api";
import type { SnapshotKind } from "@/lib/channelmanager/api";
import { useToast } from "@/hooks/use-toast";

export interface CmScope { shopId: number; userKey: string; scopeToken: string; isCurrent: (t: string | null) => boolean }

export function useCmOverview(scope: CmScope) {
  return useQuery({
    queryKey: cmKeys.overview(scope.userKey, scope.shopId),
    queryFn: ({ signal }) => cmApi.overview(scope.shopId, signal),
    staleTime: 10_000,
    retry: 1,
  });
}

export function useCmHistory(scope: CmScope, kind: SnapshotKind, offset: number, limit = 20) {
  return useQuery({
    queryKey: cmKeys.history(scope.userKey, scope.shopId, kind, offset),
    queryFn: ({ signal }) => cmApi.history(scope.shopId, kind, offset, limit, signal),
    staleTime: 10_000,
    retry: 1,
  });
}

/** Haalt een record op en valideert de vorm met de meegegeven parser. */
export function useCmRecord<T>(scope: CmScope, id: number | null, parse: (v: unknown) => T) {
  const parseRef = useRef(parse);
  parseRef.current = parse;
  return useQuery({
    queryKey: cmKeys.record(scope.userKey, scope.shopId, id ?? -1),
    queryFn: async ({ signal }) => parseRef.current(await cmApi.record(scope.shopId, id as number, signal)),
    enabled: id !== null,
    staleTime: 30_000,
    retry: 1,
  });
}

/**
 * Actie-runner: ref-guard tegen dubbel indienen, negeert antwoorden na een
 * gebruiker/winkel-wissel, valideert het antwoord en invalideert alleen de
 * gescopete cache van deze winkel. Fouten blijven zichtbaar via lastError.
 */
export function useCmAction(scope: CmScope) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const busyRef = useRef<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [lastError, setLastError] = useState<{ name: string; error: unknown } | null>(null);
  const scopeRef = useRef(scope);
  scopeRef.current = scope;

  const run = useCallback(async <T,>(name: string, fn: () => Promise<T>, success?: string): Promise<T | undefined> => {
    if (busyRef.current) return undefined;
    const token = scopeRef.current.scopeToken;
    busyRef.current = name; setBusy(name); setLastError(null);
    try {
      const out = await fn();
      if (!scopeRef.current.isCurrent(token)) return undefined;
      await qc.invalidateQueries({ queryKey: cmKeys.shop(scopeRef.current.userKey, scopeRef.current.shopId) });
      if (success) toast({ title: success });
      return out;
    } catch (e) {
      if (scopeRef.current.isCurrent(token)) {
        setLastError({ name, error: e });
        toast({ title: "Actie mislukt", description: errText(e), variant: "destructive" });
        await qc.invalidateQueries({ queryKey: cmKeys.shop(scopeRef.current.userKey, scopeRef.current.shopId) });
      }
      return undefined;
    } finally {
      busyRef.current = null; setBusy(null);
    }
  }, [qc, toast]);

  return { run, busy, lastError };
}
