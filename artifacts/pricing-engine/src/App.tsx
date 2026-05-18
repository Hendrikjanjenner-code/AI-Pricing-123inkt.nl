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
import TrafficDashboard from "@/pages/traffic-dashboard";
import ConversieMonitoring from "@/pages/conversie-monitoring";
import SearchDemand from "@/pages/search-demand";
import TrafficSkuDetail from "@/pages/traffic-sku-detail";
import TrafficCategorie from "@/pages/traffic-categorie";
import TrafficOpportunity from "@/pages/traffic-opportunity";
import SearchGap from "@/pages/search-gap";
import KostenDashboard from "@/pages/kosten-dashboard";
import MarketingEfficiency from "@/pages/marketing-efficiency";
import OperationeleComplexiteit from "@/pages/operationele-complexiteit";
import ProcurementForecast from "@/pages/procurement-forecast";
import EconomieDashboard from "@/pages/economie-dashboard";
import ManagementRapportages from "@/pages/management-rapportages";
import BcgTransities from "@/pages/bcg-transities";

// Traffic Driver & Basket Intelligence Engine
import TrafficDriverDashboard from "@/pages/traffic-driver-dashboard";
import BasketIntelligenceDashboard from "@/pages/basket-intelligence";
import SkuEcosysteem from "@/pages/sku-ecosystem";
import CrossSellIntelligence from "@/pages/cross-sell-intelligence";
import EntryProductsAnalyse from "@/pages/entry-products";

// Help & Explainability System
import ModelDocumentatie from "@/pages/modeldocumentatie";

// Cost Change & Break-even Intelligence Engine
import KostprijswijzigingDashboard from "@/pages/kostprijswijziging";
import BreakEvenAnalyse from "@/pages/break-even-analyse";
import PpfsAnalyse from "@/pages/ppfs-analyse";
import MarketingVsKorting from "@/pages/marketing-vs-korting";
import Margebescherming from "@/pages/margebescherming";

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

      {/* Traffic & Demand Intelligence */}
      <Route path="/traffic/dashboard">
        <ProtectedRoute><TrafficDashboard /></ProtectedRoute>
      </Route>
      <Route path="/traffic/conversie">
        <ProtectedRoute><ConversieMonitoring /></ProtectedRoute>
      </Route>
      <Route path="/traffic/search-demand">
        <ProtectedRoute><SearchDemand /></ProtectedRoute>
      </Route>
      <Route path="/traffic/sku/:sku_id">
        <ProtectedRoute><TrafficSkuDetail /></ProtectedRoute>
      </Route>
      <Route path="/traffic/categorie/:category">
        <ProtectedRoute><TrafficCategorie /></ProtectedRoute>
      </Route>
      <Route path="/traffic/categorie">
        <ProtectedRoute><TrafficCategorie /></ProtectedRoute>
      </Route>
      <Route path="/traffic/opportunity">
        <ProtectedRoute><TrafficOpportunity /></ProtectedRoute>
      </Route>
      <Route path="/traffic/search-gap">
        <ProtectedRoute><SearchGap /></ProtectedRoute>
      </Route>

      {/* Cost Intelligence Engine */}
      <Route path="/kosten/dashboard">
        <ProtectedRoute><KostenDashboard /></ProtectedRoute>
      </Route>
      <Route path="/kosten/marketing">
        <ProtectedRoute><MarketingEfficiency /></ProtectedRoute>
      </Route>
      <Route path="/kosten/operationeel">
        <ProtectedRoute><OperationeleComplexiteit /></ProtectedRoute>
      </Route>

      {/* Forecasting & Procurement Engine */}
      <Route path="/procurement">
        <ProtectedRoute><ProcurementForecast /></ProtectedRoute>
      </Route>

      {/* Economic Intelligence Engine */}
      <Route path="/economie">
        <ProtectedRoute><EconomieDashboard /></ProtectedRoute>
      </Route>

      {/* Executive Reporting Engine */}
      <Route path="/rapportages">
        <ProtectedRoute><ManagementRapportages /></ProtectedRoute>
      </Route>

      {/* BCG Transition Intelligence */}
      <Route path="/bcg/transities">
        <ProtectedRoute><BcgTransities /></ProtectedRoute>
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

      {/* Traffic Driver & Basket Intelligence */}
      <Route path="/traffic-driver">
        <ProtectedRoute><TrafficDriverDashboard /></ProtectedRoute>
      </Route>
      <Route path="/basket-intelligence">
        <ProtectedRoute><BasketIntelligenceDashboard /></ProtectedRoute>
      </Route>
      <Route path="/sku-ecosystem">
        <ProtectedRoute><SkuEcosysteem /></ProtectedRoute>
      </Route>
      <Route path="/cross-sell">
        <ProtectedRoute><CrossSellIntelligence /></ProtectedRoute>
      </Route>
      <Route path="/entry-products">
        <ProtectedRoute><EntryProductsAnalyse /></ProtectedRoute>
      </Route>

      {/* Cost Change & Break-even Intelligence */}
      <Route path="/kostprijswijziging">
        <ProtectedRoute><KostprijswijzigingDashboard /></ProtectedRoute>
      </Route>
      <Route path="/break-even">
        <ProtectedRoute><BreakEvenAnalyse /></ProtectedRoute>
      </Route>
      <Route path="/ppfs">
        <ProtectedRoute><PpfsAnalyse /></ProtectedRoute>
      </Route>
      <Route path="/marketing-vs-korting">
        <ProtectedRoute><MarketingVsKorting /></ProtectedRoute>
      </Route>
      <Route path="/margebescherming">
        <ProtectedRoute><Margebescherming /></ProtectedRoute>
      </Route>

      <Route path="/modeldocumentatie">
        <ProtectedRoute><ModelDocumentatie /></ProtectedRoute>
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
