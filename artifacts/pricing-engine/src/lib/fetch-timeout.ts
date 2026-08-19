/**
 * Global safety net for raw `fetch()` calls made directly from page/module
 * code (bypassing the generated `customFetch` client, which already has its
 * own timeout). Several pages in this app call `fetch()` directly against
 * `/api/...` endpoints; without this, any one of those calls could hang
 * forever on a stuck backend and spin the UI indefinitely.
 *
 * This patches `window.fetch` once at app startup so every call gets a
 * default AbortSignal-based timeout unless the caller already supplied its
 * own `signal`.
 */
const DEFAULT_GLOBAL_FETCH_TIMEOUT_MS = 15_000;

/**
 * Timeout for known long-running synchronous requests. The engine "run"
 * endpoints (basket/promotion/forecast/opportunity) are now asynchronous
 * job-starts (see lib/use-engine-run.ts) and no longer need this; keep the
 * helper for any remaining call that legitimately holds a connection open.
 */
export const LONG_RUN_FETCH_TIMEOUT_MS = 5 * 60_000;

export function longRunSignal(timeoutMs: number = LONG_RUN_FETCH_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}

let installed = false;

export function installGlobalFetchTimeout(timeoutMs: number = DEFAULT_GLOBAL_FETCH_TIMEOUT_MS): void {
  if (installed || typeof window === "undefined" || typeof window.fetch !== "function") {
    return;
  }
  installed = true;

  const originalFetch = window.fetch.bind(window);

  window.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    if (init.signal) {
      // Caller already manages its own abort/timeout behavior — don't override it.
      return originalFetch(input, init);
    }
    return originalFetch(input, { ...init, signal: AbortSignal.timeout(timeoutMs) });
  };
}
