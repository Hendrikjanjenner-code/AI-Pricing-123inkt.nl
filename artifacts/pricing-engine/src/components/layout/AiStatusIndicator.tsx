import { Link } from "wouter";
import { AlertTriangle, Sparkles, WifiOff } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useAiProviderStatus } from "@/hooks/use-ai-provider-status";

/**
 * Klein AI-statusbadge in de navigatiebalk (Task #93).
 * Alleen zichtbaar voor admins; klik linkt naar de AI-provider-sectie
 * van de instellingenpagina.
 *
 * Leest uit de gedeelde React Query-cache (Task #104), zodat een
 * providerwissel of verbindingstest op de instellingenpagina direct
 * in het badge zichtbaar is.
 */
export function AiStatusIndicator() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data } = useAiProviderStatus(isAdmin);
  const providers = data?.providers;

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
