import { useQuery } from "@tanstack/react-query";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

export interface AiProviderStatus {
  id: string;
  label: string;
  active: boolean;
  configured: boolean;
  reachable: boolean | null;
  error: string | null;
}

export interface AiProviderInfo {
  mode?: string;
  updated_by?: string | null;
  updated_at?: string | null;
  providers: AiProviderStatus[];
}

/**
 * Gedeelde React Query-sleutel voor de AI-providerstatus (Task #104).
 * Zowel het statusbadge in de navigatiebalk als de instellingenpagina
 * lezen uit deze ene cache, zodat een providerwissel of verbindingstest
 * direct overal zichtbaar is — zonder dubbele polling-loops.
 */
export const AI_PROVIDER_QUERY_KEY = ["/api/copilot/provider"] as const;

export function useAiProviderStatus(enabled: boolean) {
  return useQuery<AiProviderInfo>({
    queryKey: AI_PROVIDER_QUERY_KEY,
    enabled,
    queryFn: async () => {
      const resp = await fetch(`${BASE}/api/copilot/provider`, {
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error("AI-providerstatus ophalen mislukt");
      return resp.json();
    },
    // Eén polling-loop voor alle consumers; React Query dedupliceert.
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    // Behoud de laatst bekende status bij een mislukte refresh.
    retry: false,
  });
}
