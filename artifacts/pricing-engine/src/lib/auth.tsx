import React, { createContext, useContext, useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useGetCurrentUser, setAuthTokenGetter, ApiError } from "@workspace/api-client-react";
import { resetUserPrefs } from "@/lib/user-prefs";

// Initialize auth token getter
setAuthTokenGetter(() => localStorage.getItem("auth_token"));

const CACHED_USER_KEY = "auth_user_cache";

export const getAuthToken = (): string => localStorage.getItem("auth_token") || "";

export const getAuthHeaders = (): Record<string, string> => ({
  Authorization: `Bearer ${getAuthToken()}`,
});

export const setAuthToken = (token: string | null) => {
  if (token) {
    localStorage.setItem("auth_token", token);
  } else {
    localStorage.removeItem("auth_token");
    localStorage.removeItem(CACHED_USER_KEY);
  }
};

// Optimistic user cache: hydrated synchronously from the login response so
// the dashboard never has to wait on a fresh GET /me round-trip to render.
// GET /me still runs in the background to keep this in sync / catch
// genuinely revoked sessions (401/403), but a slow or transiently-failing
// /me can no longer block or reverse a successful login.
export const setCachedUser = (user: unknown) => {
  try {
    localStorage.setItem(CACHED_USER_KEY, JSON.stringify(user));
  } catch {
    // Best-effort only; absence just means we fall back to /me.
  }
};

export const getCachedUser = (): any | null => {
  try {
    const raw = localStorage.getItem(CACHED_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const AuthContext = createContext<{
  user: any;
  isLoading: boolean;
  logout: () => void;
}>({
  user: null,
  isLoading: true,
  logout: () => {},
});

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [, setLocation] = useLocation();
  const [user, setUser] = useState<any>(() => getCachedUser());
  const hasToken = !!getAuthToken();

  // Orval levert zelf een default queryKey; alleen retry uitzetten.
  const { data, isLoading, isError, error } = useGetCurrentUser({
    query: {
      retry: false,
    } as never,
  });

  useEffect(() => {
    if (!hasToken) {
      // No token at all — definitely not authenticated, no reason to wait.
      setUser(null);
      setLocation("/login");
      return;
    }
    if (isLoading) return;

    if (data) {
      console.info("[auth] user loaded/refreshed:", (data as any)?.username);
      setUser(data);
      setCachedUser(data);
      return;
    }

    if (isError) {
      const status = error instanceof ApiError ? error.status : undefined;
      const isUnauthenticated = status === 401 || status === 403;

      if (isUnauthenticated) {
        // Token is genuinely invalid/expired — this is the only case where
        // we should force the user back to the login screen.
        console.error("[auth] session rejected by server (status %s):", status, (error as any)?.message || error);
        setAuthToken(null);
        setUser(null);
        resetUserPrefs();
        setLocation("/login");
        return;
      }

      // Network error, timeout, or 5xx: keep using the optimistically
      // cached user (from login or a prior successful /me) so a flaky
      // backend call can't kick an already-authenticated user out.
      console.warn(
        "[auth] GET /me failed (non-auth error), keeping cached session if available:",
        (error as any)?.message || error,
      );
      if (!getCachedUser()) {
        setLocation("/login");
      }
    }
  }, [hasToken, isLoading, isError, error, data, setLocation]);

  // isLoading is only true while we have neither a cached user nor a
  // resolved /me response — i.e. the very first load with no optimistic
  // data available yet. Once a cached user exists (e.g. right after login),
  // the dashboard renders immediately instead of waiting on the network.
  const effectiveIsLoading = hasToken && !user && isLoading;

  const logout = () => {
    setAuthToken(null);
    setUser(null);
    // Persoonlijke favorieten/recents wissen zodat een volgende gebruiker in
    // dezelfde browser niet andermans voorkeuren ziet.
    resetUserPrefs();
    setLocation("/login");
  };

  return (
    <AuthContext.Provider value={{ user, isLoading: effectiveIsLoading, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
