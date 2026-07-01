import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/lib/auth";
import { SidebarLayout } from "./SidebarLayout";
import { Spinner } from "@/components/ui/spinner";

// Hard ceiling on how long the auth check may spin, independent of the
// underlying request timeout. Guarantees the UI never spins forever even if
// something upstream (e.g. a stuck query) doesn't resolve as expected.
const AUTH_CHECK_TIMEOUT_MS = 20_000;

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const [, setLocation] = useLocation();
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) {
      console.warn("[protected-route] no authenticated user — redirecting to login");
      setLocation("/login");
    }
  }, [isLoading, user, setLocation]);

  useEffect(() => {
    if (!isLoading) {
      setTimedOut(false);
      return;
    }
    console.info("[protected-route] dashboard route opened, checking auth");
    const timer = setTimeout(() => {
      console.error("[protected-route] auth check exceeded timeout, forcing redirect to login");
      setTimedOut(true);
    }, AUTH_CHECK_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [isLoading]);

  useEffect(() => {
    if (timedOut) {
      setLocation("/login");
    }
  }, [timedOut, setLocation]);

  if (isLoading && !timedOut) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-background">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!user) {
    return null; // Will redirect
  }

  return <SidebarLayout>{children}</SidebarLayout>;
}
