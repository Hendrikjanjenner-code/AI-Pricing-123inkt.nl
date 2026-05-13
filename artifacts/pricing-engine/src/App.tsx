import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import NotFound from "@/pages/not-found";

// Bestaande pagina's
import Login from "@/pages/login";
import Dashboard from "@/pages/dashboard";
import Prijsadviezen from "@/pages/recommendations";
import PrijsadviesDetail from "@/pages/recommendations/detail";
import Producten from "@/pages/skus";
import ProductDetail from "@/pages/skus/detail";
import Categorieen from "@/pages/categories";
import Gegevensintegratie from "@/pages/data-upload";
import Datakwaliteit from "@/pages/data-quality";
import Substitutiemonitor from "@/pages/substitutions";
import Modelgezondheid from "@/pages/model-health";
import ExportPrijsShape from "@/pages/export";
import Instellingen from "@/pages/settings";
import ConcurrentieIntelligence from "@/pages/competition";
import ConcurrentieDetail from "@/pages/competition-detail";
import AbTestMonitor from "@/pages/ab-tests";
import SkuConcurrentieAnalyse from "@/pages/sku-concurrentie";
import Elasticiteitsmonitor from "@/pages/elasticiteit";
import HuismerkImpact from "@/pages/huismerk-impact";

// Nieuwe module-pagina's
import ScrapingConfiguratie from "@/pages/scraping-configuratie";
import ProductMatching from "@/pages/product-matching";
import ConcurrentieMonitoring from "@/pages/concurrentie-monitoring";
import Uitvoering from "@/pages/uitvoering";
import AuditLogPage from "@/pages/audit-log";

// BCG Intelligence Engine
import BcgDashboard from "@/pages/bcg-dashboard";
import BcgSkuMatrix from "@/pages/bcg-sku";
import BcgCategorie from "@/pages/bcg-categorie";
import BcgHybrid from "@/pages/bcg-hybrid";
import BcgHuismerk from "@/pages/bcg-huismerk";
import BcgPricingPower from "@/pages/bcg-pricing-power";
import BcgSkuDetail from "@/pages/bcg-sku-detail";

const queryClient = new QueryClient();

function Router() {
  return (
    <Switch>
      <Route path="/login" component={Login} />
      <Route path="/">
        <ProtectedRoute><Dashboard /></ProtectedRoute>
      </Route>

      {/* Prijsadviezen */}
      <Route path="/prijsadviezen">
        <ProtectedRoute><Prijsadviezen /></ProtectedRoute>
      </Route>
      <Route path="/prijsadviezen/:id">
        <ProtectedRoute><PrijsadviesDetail /></ProtectedRoute>
      </Route>
      <Route path="/recommendations">
        <ProtectedRoute><Prijsadviezen /></ProtectedRoute>
      </Route>
      <Route path="/recommendations/:id">
        <ProtectedRoute><PrijsadviesDetail /></ProtectedRoute>
      </Route>

      {/* Producten / SKU's */}
      <Route path="/producten">
        <ProtectedRoute><Producten /></ProtectedRoute>
      </Route>
      <Route path="/producten/:id">
        <ProtectedRoute><ProductDetail /></ProtectedRoute>
      </Route>
      <Route path="/skus">
        <ProtectedRoute><Producten /></ProtectedRoute>
      </Route>
      <Route path="/skus/:id">
        <ProtectedRoute><ProductDetail /></ProtectedRoute>
      </Route>

      {/* Concurrentie-intelligentie (PCIS) */}
      <Route path="/concurrentie">
        <ProtectedRoute><ConcurrentieIntelligence /></ProtectedRoute>
      </Route>
      <Route path="/concurrentie/:sku_id">
        <ProtectedRoute><ConcurrentieDetail /></ProtectedRoute>
      </Route>
      <Route path="/competition">
        <ProtectedRoute><ConcurrentieIntelligence /></ProtectedRoute>
      </Route>
      <Route path="/competition/:sku_id">
        <ProtectedRoute><ConcurrentieDetail /></ProtectedRoute>
      </Route>

      {/* CIS / Elasticiteit / Huismerk */}
      <Route path="/sku-concurrentie">
        <ProtectedRoute><SkuConcurrentieAnalyse /></ProtectedRoute>
      </Route>
      <Route path="/elasticiteit">
        <ProtectedRoute><Elasticiteitsmonitor /></ProtectedRoute>
      </Route>
      <Route path="/huismerk-impact">
        <ProtectedRoute><HuismerkImpact /></ProtectedRoute>
      </Route>

      {/* Nieuwe modules */}
      <Route path="/scraping">
        <ProtectedRoute><ScrapingConfiguratie /></ProtectedRoute>
      </Route>
      <Route path="/product-matching">
        <ProtectedRoute><ProductMatching /></ProtectedRoute>
      </Route>
      <Route path="/monitoring">
        <ProtectedRoute><ConcurrentieMonitoring /></ProtectedRoute>
      </Route>
      <Route path="/uitvoering">
        <ProtectedRoute><Uitvoering /></ProtectedRoute>
      </Route>
      <Route path="/audit-log">
        <ProtectedRoute><AuditLogPage /></ProtectedRoute>
      </Route>

      {/* BCG Intelligence Engine */}
      <Route path="/bcg/dashboard">
        <ProtectedRoute><BcgDashboard /></ProtectedRoute>
      </Route>
      <Route path="/bcg/sku-matrix">
        <ProtectedRoute><BcgSkuMatrix /></ProtectedRoute>
      </Route>
      <Route path="/bcg/sku/:sku_id">
        <ProtectedRoute><BcgSkuDetail /></ProtectedRoute>
      </Route>
      <Route path="/bcg/categorie">
        <ProtectedRoute><BcgCategorie /></ProtectedRoute>
      </Route>
      <Route path="/bcg/hybrid">
        <ProtectedRoute><BcgHybrid /></ProtectedRoute>
      </Route>
      <Route path="/bcg/huismerk">
        <ProtectedRoute><BcgHuismerk /></ProtectedRoute>
      </Route>
      <Route path="/bcg/pricing-power">
        <ProtectedRoute><BcgPricingPower /></ProtectedRoute>
      </Route>

      {/* Overige pagina's */}
      <Route path="/categorieen">
        <ProtectedRoute><Categorieen /></ProtectedRoute>
      </Route>
      <Route path="/categories">
        <ProtectedRoute><Categorieen /></ProtectedRoute>
      </Route>
      <Route path="/gegevensintegratie">
        <ProtectedRoute><Gegevensintegratie /></ProtectedRoute>
      </Route>
      <Route path="/data-upload">
        <ProtectedRoute><Gegevensintegratie /></ProtectedRoute>
      </Route>
      <Route path="/datakwaliteit">
        <ProtectedRoute><Datakwaliteit /></ProtectedRoute>
      </Route>
      <Route path="/data-quality">
        <ProtectedRoute><Datakwaliteit /></ProtectedRoute>
      </Route>
      <Route path="/substituties">
        <ProtectedRoute><Substitutiemonitor /></ProtectedRoute>
      </Route>
      <Route path="/substitutions">
        <ProtectedRoute><Substitutiemonitor /></ProtectedRoute>
      </Route>
      <Route path="/modelgezondheid">
        <ProtectedRoute><Modelgezondheid /></ProtectedRoute>
      </Route>
      <Route path="/model-health">
        <ProtectedRoute><Modelgezondheid /></ProtectedRoute>
      </Route>
      <Route path="/export">
        <ProtectedRoute><ExportPrijsShape /></ProtectedRoute>
      </Route>
      <Route path="/instellingen">
        <ProtectedRoute><Instellingen /></ProtectedRoute>
      </Route>
      <Route path="/settings">
        <ProtectedRoute><Instellingen /></ProtectedRoute>
      </Route>
      <Route path="/ab-tests">
        <ProtectedRoute><AbTestMonitor /></ProtectedRoute>
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
