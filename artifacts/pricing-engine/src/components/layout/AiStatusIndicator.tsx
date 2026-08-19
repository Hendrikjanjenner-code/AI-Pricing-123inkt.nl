import { useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import { AlertTriangle, Sparkles, WifiOff } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";
import { useAuth } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface ProviderStatus {
  id: string;
  label: string;
  active: boolean;
  configured: boolean;
  reachable: boolean | null;
  error: string | null;
}

/**
 * Klein AI-statusbadge in de navigatiebalk (Task #93).
 * Alleen zichtbaar voor admins; klik linkt naar de AI-provider-sectie
 * van de instellingenpagina.
 */
export function AiStatusIndicator() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [providers, setProviders] = useState<ProviderStatus[] | null>(null);
  const activeRef = useRef(true);

  useEffect(() => {
    if (!isAdmin) return;
    activeRef.current = true;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const load = async () => {
      if (document.hidden) return;
      try {
        const resp = await fetch(`${BASE}/api/copilot/provider`, {
          headers: getAuthHeaders(),
        });
        if (!resp.ok) throw new Error("fetch failed");
        const data = await resp.json();
        if (!activeRef.current) return;
        setProviders(Array.isArray(data?.providers) ? data.providers : []);
      } catch {
        // Behoud de laatst bekende status bij een mislukte refresh.
      }
    };

    load();
    intervalId = setInterval(load, 60000);
    const onVisibilityChange = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      activeRef.current = false;
      if (intervalId) clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [isAdmin]);

  if (!isAdmin || !providers) return null;

  const active = providers.find((p) => p.active);

  // Drie zichtbare toestanden voor de beheerder:
  // - "unavailable": geen actieve provider of actieve provider niet geconfigureerd
  // - "unreachable": geconfigureerd maar de live-probe faalt
  // - "ok": geconfigureerd en bereikbaar (of probe nog onbekend maar wel geconfigureerd)
  let state: "ok" | "unreachable" | "unavailable";
  let label: string;
  let title: string;
  if (!active) {
    state = "unavailable";
    label = "AI niet geconfigureerd";
    title = "Geen AI-provider geconfigureerd — Copilot is niet beschikbaar. Klik voor de AI-providerinstellingen.";
  } else if (!active.configured) {
    state = "unavailable";
    label = "AI niet geconfigureerd";
    title = `AI-provider ${active.label} is nog niet geconfigureerd — Copilot is niet beschikbaar. Klik voor de AI-providerinstellingen.`;
  } else if (active.reachable === false) {
    state = "unreachable";
    label = "AI onbereikbaar";
    title = `AI-verbinding verbroken — ${active.label} is niet bereikbaar. Klik voor de AI-providerinstellingen.`;
  } else {
    state = "ok";
    label = "AI verbonden";
    title = `AI verbonden via ${active.label} — klik voor de AI-providerinstellingen.`;
  }

  return (
    <Link
      href="/settings#ai-provider"
      title={title}
      aria-label={title}
      data-testid="ai-status-indicator"
      className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
        state === "ok"
          ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
          : "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100"
      }`}
    >
      {state === "ok" ? (
        <Sparkles className="h-3.5 w-3.5" />
      ) : state === "unreachable" ? (
        <WifiOff className="h-3.5 w-3.5" />
      ) : (
        <AlertTriangle className="h-3.5 w-3.5" />
      )}
      <span>{label}</span>
    </Link>
  );
}
