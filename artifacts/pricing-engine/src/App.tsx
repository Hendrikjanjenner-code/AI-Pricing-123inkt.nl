import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import NotFound from "@/pages/not-found";

// Pages
import Login from "@/pages/login";
import Dashboard from "@/pages/dashboard";
import Recommendations from "@/pages/recommendations";
import RecommendationDetail from "@/pages/recommendations/detail";
import Skus from "@/pages/skus";
import SkuDetail from "@/pages/skus/detail";
import Categories from "@/pages/categories";
import DataUpload from "@/pages/data-upload";
import DataQuality from "@/pages/data-quality";
import Substitutions from "@/pages/substitutions";
import ModelHealth from "@/pages/model-health";
import Export from "@/pages/export";
import Settings from "@/pages/settings";
import Competition from "@/pages/competition";
import CompetitionDetail from "@/pages/competition-detail";
import AbTests from "@/pages/ab-tests";

const queryClient = new QueryClient();

function Router() {
  return (
    <Switch>
      <Route path="/login" component={Login} />
      <Route path="/">
        <ProtectedRoute><Dashboard /></ProtectedRoute>
      </Route>
      <Route path="/recommendations">
        <ProtectedRoute><Recommendations /></ProtectedRoute>
      </Route>
      <Route path="/recommendations/:id">
        <ProtectedRoute><RecommendationDetail /></ProtectedRoute>
      </Route>
      <Route path="/skus">
        <ProtectedRoute><Skus /></ProtectedRoute>
      </Route>
      <Route path="/skus/:id">
        <ProtectedRoute><SkuDetail /></ProtectedRoute>
      </Route>
      <Route path="/categories">
        <ProtectedRoute><Categories /></ProtectedRoute>
      </Route>
      <Route path="/data-upload">
        <ProtectedRoute><DataUpload /></ProtectedRoute>
      </Route>
      <Route path="/data-quality">
        <ProtectedRoute><DataQuality /></ProtectedRoute>
      </Route>
      <Route path="/substitutions">
        <ProtectedRoute><Substitutions /></ProtectedRoute>
      </Route>
      <Route path="/model-health">
        <ProtectedRoute><ModelHealth /></ProtectedRoute>
      </Route>
      <Route path="/export">
        <ProtectedRoute><Export /></ProtectedRoute>
      </Route>
      <Route path="/settings">
        <ProtectedRoute><Settings /></ProtectedRoute>
      </Route>
      <Route path="/competition">
        <ProtectedRoute><Competition /></ProtectedRoute>
      </Route>
      <Route path="/competition/:sku_id">
        <ProtectedRoute><CompetitionDetail /></ProtectedRoute>
      </Route>
      <Route path="/ab-tests">
        <ProtectedRoute><AbTests /></ProtectedRoute>
      </Route>
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
