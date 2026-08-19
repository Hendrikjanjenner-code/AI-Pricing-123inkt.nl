import { useEffect } from "react";
import { Switch, Route, Router as WouterRouter, useParams, useLocation } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { ROUTES, REDIRECTS } from "@/lib/route-registry";
import NotFound from "@/pages/not-found";
import Login from "@/pages/login";

const queryClient = new QueryClient();

/**
 * Redirect voor verplaatste/hernoemde paden. Vult :params uit het oude pad
 * in op het nieuwe pad, zodat oude deep links (bijv. /skus/123) blijven werken.
 */
function RedirectRoute({ to }: { to: string }) {
  const params = useParams();
  const [, setLocation] = useLocation();
  useEffect(() => {
    const doel = to.replace(/:([A-Za-z_]+)/g, (_, naam) => params[naam] ?? "");
    setLocation(doel, { replace: true });
  }, [to, params, setLocation]);
  return null;
}

/**
 * De router wordt volledig gegenereerd uit de centrale Route Registry
 * (src/lib/route-registry.tsx). Nieuwe pagina's worden dáár toegevoegd.
 */
function Router() {
  return (
    <Switch>
      <Route path="/login" component={Login} />

      {ROUTES.map((route) => {
        const Component = route.component;
        return (
          <Route key={route.path} path={route.path}>
            <ProtectedRoute>
              <Component />
            </ProtectedRoute>
          </Route>
        );
      })}

      {/* Oude paden blijven werken via redirects uit de registry */}
      {REDIRECTS.map((redirect) => (
        <Route key={redirect.from} path={redirect.from}>
          <RedirectRoute to={redirect.to} />
        </Route>
      ))}

      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <AuthProvider>
            <Router />
          </AuthProvider>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
