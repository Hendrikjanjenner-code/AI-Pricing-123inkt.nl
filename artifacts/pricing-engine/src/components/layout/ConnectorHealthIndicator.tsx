import { useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

type ConnStatus = "ok" | "not_configured" | "unreachable" | "auth_error" | "error";

interface ConnectorStatus {
  name: string;
  label: string;
  configured: boolean;
  last_test_status: ConnStatus | null;
}

const CONN_STATUS_LABEL: Record<ConnStatus, string> = {
  ok: "Verbonden",
  not_configured: "Niet geconfigureerd",
  unreachable: "Niet bereikbaar",
  auth_error: "Authenticatiefout",
  error: "Fout",
};

export function ConnectorHealthIndicator() {
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [ready, setReady] = useState(false);
  const hasDataRef = useRef(false);

  useEffect(() => {
    let active = true;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const load = async () => {
      if (document.hidden) return;
      try {
        const resp = await fetch(`${BASE}/api/connectors`, { headers: getAuthHeaders() });
        if (!resp.ok) throw new Error("fetch failed");
        const data: ConnectorStatus[] = await resp.json();
        if (!active) return;
        hasDataRef.current = true;
        setConnectors(data);
        setReady(true);
      } catch {
        // Keep last-known status on refresh failures.
      }
    };

    load();
    intervalId = setInterval(load, 60000);

    const onVisibilityChange = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      active = false;
      if (intervalId) clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  if (!ready || connectors.length === 0) return null;

  const problems = connectors.filter(
    (c) => c.configured && c.last_test_status && c.last_test_status !== "ok"
  );
  const anyProblem = problems.length > 0;

  const title = anyProblem
    ? `Databronnen met problemen: ${problems
        .map((c) => `${c.label} (${CONN_STATUS_LABEL[c.last_test_status ?? "error"]})`)
        .join(", ")} — klik voor details`
    : "Alle databronnen verbonden — klik voor details";

  return (
    <Link
      href="/connectoren"
      title={title}
      aria-label={title}
      className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
        anyProblem
          ? "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100"
          : "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
      }`}
    >
      {anyProblem ? (
        <>
          <AlertTriangle className="h-3.5 w-3.5" />
          <span>
            {problems.length} databron{problems.length > 1 ? "nen" : ""} offline
          </span>
        </>
      ) : (
        <>
          <CheckCircle2 className="h-3.5 w-3.5" />
          <span>Databronnen ok</span>
        </>
      )}
    </Link>
  );
}
