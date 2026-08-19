/**
 * Hook voor asynchrone engine-herberekeningen (basket/promotion/forecast/
 * opportunity). De POST naar het run-endpoint retourneert direct een job-id;
 * deze hook pollt daarna GET /api/engine-jobs/{job_id} tot de job klaar is,
 * zodat er geen minutenlange open HTTP-verbinding meer nodig is.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
const POLL_INTERVAL_MS = 2_000;

interface EngineJob {
  job_id: string;
  engine: string;
  status: "running" | "completed" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
}

interface UseEngineRunOptions {
  /** Run-endpoint, bijv. `${BASE}/api/basket/run` */
  runUrl: string;
  /** Wordt aangeroepen zodra de job succesvol is afgerond (bijv. queries invalideren). */
  onCompleted?: (result: Record<string, unknown> | null) => void;
}

export function useEngineRun({ runUrl, onCompleted }: UseEngineRunOptions) {
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef(false);
  const onCompletedRef = useRef(onCompleted);
  onCompletedRef.current = onCompleted;

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const poll = useCallback((jobId: string) => {
    timerRef.current = setTimeout(async () => {
      if (!activeRef.current) return;
      try {
        const res = await fetch(`${BASE}/api/engine-jobs/${jobId}`, { headers: getAuthHeaders() });
        if (res.status === 404) {
          throw new Error("De job is verlopen (server herstart?). Start de herberekening opnieuw.");
        }
        if (!res.ok) throw new Error("Kon jobstatus niet ophalen");
        const job: EngineJob = await res.json();
        if (!activeRef.current) return;
        if (job.status === "running") {
          poll(jobId);
          return;
        }
        setIsRunning(false);
        if (job.status === "failed") {
          setError(job.error || "Herberekening mislukt");
        } else {
          onCompletedRef.current?.(job.result);
        }
      } catch (e) {
        if (!activeRef.current) return;
        setIsRunning(false);
        setError(e instanceof Error ? e.message : "Herberekening mislukt");
      }
    }, POLL_INTERVAL_MS);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setIsRunning(true);
    try {
      const res = await fetch(runUrl, { method: "POST", headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Kon herberekening niet starten");
      const job: EngineJob = await res.json();
      if (!job.job_id) throw new Error("Ongeldig antwoord van de server");
      poll(job.job_id);
    } catch (e) {
      setIsRunning(false);
      setError(e instanceof Error ? e.message : "Kon herberekening niet starten");
    }
  }, [runUrl, poll]);

  return { start, isRunning, error };
}
