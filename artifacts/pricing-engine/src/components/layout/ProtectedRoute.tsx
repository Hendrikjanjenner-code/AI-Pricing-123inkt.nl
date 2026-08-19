import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { useAuth } from "@/lib/auth";
import { SidebarLayout } from "./SidebarLayout";
import { Spinner } from "@/components/ui/spinner";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { vindRoute, magRoute } from "@/lib/route-registry";

/**
 * Geen-toegang-scherm (taak 219). Menu-verbergen is alleen UX: ook wie een
 * URL rechtstreeks intikt, ziet dit scherm; de backend geeft bovendien 403.
 */
function GeenToegang() {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="text-center max-w-md space-y-4">
        <ShieldAlert className="w-12 h-12 mx-auto text-muted-foreground" />
        <h1 className="text-xl font-semibold">Geen toegang</h1>
        <p className="text-sm text-muted-foreground">
          Je afdeling of rol geeft geen toegang tot dit onderdeel. Vraag een
          beheerder om extra rechten als je dit scherm nodig hebt.
        </p>
        <Button asChild variant="outline">
          <Link href="/">Terug naar Mijn Dashboard</Link>
        </Button>
      </div>
    </div>
  );
}

// Hard ceiling on how long the auth check may spin, independent of the
// underlying request timeout. Guarantees the UI never spins forever even if
// something upstream (e.g. a stuck query) doesn't resolve as expected.
const AUTH_CHECK_TIMEOUT_MS = 20_000;

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const [location, setLocation] = useLocation();
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
        <Spinner className="size-8" />
      </div>
    );
  }

  if (!user) {
    return null; // Will redirect
  }

  // Permissie-check per route (taak 219): verborgen menu-items zijn via
  // directe URL niet bereikbaar.
  const route = vindRoute(location);
  if (route && !magRoute(route, user)) {
    return <SidebarLayout><GeenToegang /></SidebarLayout>;
  }

  return <SidebarLayout>{children}</SidebarLayout>;
}
