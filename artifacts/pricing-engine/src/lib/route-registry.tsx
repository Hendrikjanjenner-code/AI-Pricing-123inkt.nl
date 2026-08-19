/**
 * Centrale Route Registry.
 *
 * Elke route in de applicatie is hier gedefinieerd met:
 *  - domein      : één van de 13 domeinen (sidebar-groep)
 *  - label       : Nederlands label (sidebar + breadcrumb)
 *  - icon        : sidebar-icoon
 *  - permission  : minimale rol die de route mag zien (RBAC-taak bouwt hierop voort)
 *  - department  : afdelings-default (wordt later door department-workspaces gebruikt)
 *  - positie     : sorteervolgorde binnen het domein
 *  - breadcrumbParent : pad van de bovenliggende pagina (voor detailpagina's)
 *  - aliases     : oude paden die naar deze route redirecten (deep links blijven werken)
 *
 * Sidebar, breadcrumbs en de router in App.tsx worden allemaal uit deze
 * registry gegenereerd — nergens dubbel onderhouden.
 */
import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";
import {
  BarChart3, HeartHandshake, Gem, Settings, Upload, Database, List, Box,
  Activity, Layers, ArrowRightLeft, Download, Crosshair, FlaskConical,
  TrendingDown, Target, LineChart, Bell, Zap, ClipboardList, LayoutGrid, Tag,
  Sigma, TrendingUp, SearchIcon, BarChart2, DollarSign, Megaphone, Cpu,
  ShoppingCart, Globe2, FileText, GitBranch, ArrowUpDown, Calculator, Scale,
  Shield, Users, BookOpen, FolderTree, Building2, Puzzle, GitMerge, Radar,
  PackageSearch, BrainCircuit, Binoculars, ClipboardCheck, Map, Server,
  Lightbulb, History, Sparkles, ThumbsUp, Home, Truck, Percent,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Pagina-imports
// ---------------------------------------------------------------------------
import Dashboard from "@/pages/dashboard";
import Signalen from "@/pages/signalen";
import Copilot from "@/pages/copilot";
import CopilotKwaliteit from "@/pages/copilot-kwaliteit";
import Prijsadviezen from "@/pages/recommendations";
import PrijsadviesDetail from "@/pages/recommendations/detail";
import Producten from "@/pages/skus";
import ProductDetail from "@/pages/skus/detail";
import Categorieen from "@/pages/categories";
import CategorieHierarchie from "@/pages/categories-hierarchy";
import ProductHierarchie from "@/pages/product-hierarchie";
import Gegevensintegratie from "@/pages/data-upload";
import DataIntegratie from "@/pages/data-integratie";
import Datakwaliteit from "@/pages/data-quality";
import PimContent from "@/pages/pim-content";
import PimSuggestions from "@/pages/pim-suggestions";
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
import CompetitionDashboard from "@/pages/competition-dashboard";
import CompetitionDiscovery from "@/pages/competition-discovery";
import CompetitionCompetitors from "@/pages/competition-competitors";
import CompetitorDetail from "@/pages/competition-competitor-detail";
import CompetitionCategories from "@/pages/competition-categories";
import CompetitionAiMatching from "@/pages/competition-ai-matching";
import CompetitionAssortmentGap from "@/pages/competition-assortment-gap";
import CompetitionStrategies from "@/pages/competition-strategies";
import CompetitionManagement from "@/pages/competition-management";
import CompetitionDiscoveryLog from "@/pages/competition-discovery-log";
import CompetitionSettings from "@/pages/competition-settings";
import CompetitionTrends from "@/pages/competition-trends";
import ConcurrentieMonitoring from "@/pages/concurrentie-monitoring";
import Uitvoering from "@/pages/uitvoering";
import AuditLogPage from "@/pages/audit-log";
import BcgDashboard from "@/pages/bcg-dashboard";
import BcgSkuMatrix from "@/pages/bcg-sku";
import BcgSkuDetail from "@/pages/bcg-sku-detail";
import BcgCategorie from "@/pages/bcg-categorie";
import BcgHybrid from "@/pages/bcg-hybrid";
import BcgHuismerk from "@/pages/bcg-huismerk";
import BcgPricingPower from "@/pages/bcg-pricing-power";
import BcgTransities from "@/pages/bcg-transities";
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
import TrafficDriverDashboard from "@/pages/traffic-driver-dashboard";
import BasketIntelligenceDashboard from "@/pages/basket-intelligence";
import SkuEcosysteem from "@/pages/sku-ecosystem";
import CrossSellIntelligence from "@/pages/cross-sell-intelligence";
import EntryProductsAnalyse from "@/pages/entry-products";
import ModelDocumentatie from "@/pages/modeldocumentatie";
import Connectoren from "@/pages/connectoren";
import DrsIntegratie from "@/pages/drs-integratie";
import Ga4Integratie from "@/pages/ga4-integratie";
import PrijsstrategieHerkenning from "@/pages/prijsstrategie-herkenning";
import KostprijswijzigingDashboard from "@/pages/kostprijswijziging";
import BreakEvenAnalyse from "@/pages/break-even-analyse";
import PpfsAnalyse from "@/pages/ppfs-analyse";
import MarketingVsKorting from "@/pages/marketing-vs-korting";
import Margebescherming from "@/pages/margebescherming";
import PlatformHealth from "@/pages/platform-health";
import PlatformKosten from "@/pages/platform-kosten";
import PlatformBusinesscase from "@/pages/platform-businesscase";
import BusinessValue from "@/pages/business-value";
import LoyaltyDashboard from "@/pages/loyalty-dashboard";
import LoyaltyMemberDetail from "@/pages/loyalty-member-detail";
import CustomerValue from "@/pages/customer-value";
import PromotionIntelligence from "@/pages/promotion-intelligence";
import ForecastRisk from "@/pages/forecast-risk";
import Opportunities from "@/pages/opportunities";
import ModelRegistry from "@/pages/model-registry";
import Beslissingen from "@/pages/decisions";
import BeslissingDetail from "@/pages/decisions/detail";
import CommandCenter from "@/pages/command-center";
import PlatformGap from "@/pages/platform-gap";
import DocsCenter from "@/pages/docs-center";
import DevBacklog from "@/pages/dev-backlog";
import Eindevaluatie from "@/pages/eindevaluatie";

// ---------------------------------------------------------------------------
// Domeinen (13) — sidebar-volgorde
// ---------------------------------------------------------------------------
export type DomeinId =
  | "command-center" | "concurrentie" | "pricing" | "catman" | "inkoop"
  | "supply-chain" | "search-digital" | "promoties-loyalty" | "forecast-risico"
  | "product-data" | "ai-besluitvorming" | "management" | "beheer";

export interface Domein {
  id: DomeinId;
  label: string;
  icon: LucideIcon;
  positie: number;
}

export const DOMEINEN: Domein[] = [
  { id: "command-center",     label: "Command Center",            icon: LayoutGrid,    positie: 1 },
  { id: "concurrentie",       label: "Concurrentie",              icon: Crosshair,     positie: 2 },
  { id: "pricing",            label: "Pricing",                   icon: Tag,           positie: 3 },
  { id: "catman",             label: "CatMan",                    icon: Layers,        positie: 4 },
  { id: "inkoop",             label: "Inkoop",                    icon: ShoppingCart,  positie: 5 },
  { id: "supply-chain",       label: "Supply Chain",              icon: Truck,         positie: 6 },
  { id: "search-digital",     label: "Search & Digital Growth",   icon: SearchIcon,    positie: 7 },
  { id: "promoties-loyalty",  label: "Promoties & Loyalty",       icon: Percent,       positie: 8 },
  { id: "forecast-risico",    label: "Forecast & Risico",         icon: TrendingUp,    positie: 9 },
  { id: "product-data",       label: "Product & Data",            icon: Database,      positie: 10 },
  { id: "ai-besluitvorming",  label: "AI & Besluitvorming",       icon: BrainCircuit,  positie: 11 },
  { id: "management",         label: "Management",                icon: FileText,      positie: 12 },
  { id: "beheer",             label: "Beheer",                    icon: Settings,      positie: 13 },
];

// ---------------------------------------------------------------------------
// Route-definities
// ---------------------------------------------------------------------------
export type Rol = "viewer" | "analyst" | "pricing_manager" | "admin";
export type Afdeling =
  | "management" | "pricing" | "catman" | "inkoop" | "supply_chain"
  | "digital" | "marketing" | "data" | "beheer";

export interface RouteDef {
  /** wouter-pad; kan :params bevatten */
  path: string;
  label: string;
  domein: DomeinId;
  component: ComponentType;
  /** Minimale rol; wordt door de RBAC-taak afgedwongen, hier alleen vastgelegd. */
  permission: Rol;
  /** Afdeling waarvoor deze route standaard zichtbaar wordt (department-workspaces-taak). */
  department: Afdeling;
  /** Sorteervolgorde binnen het domein. */
  positie: number;
  /** Alleen zichtbaar in de sidebar wanneer true (detailroutes: false). */
  inSidebar: boolean;
  icon?: LucideIcon;
  /** Pad van de bovenliggende pagina voor de breadcrumb (detailpagina's). */
  breadcrumbParent?: string;
  /** Oude paden die permanent naar deze route redirecten. */
  aliases?: string[];
}

const r = (
  path: string, label: string, domein: DomeinId, component: ComponentType,
  positie: number,
  opts: Partial<Pick<RouteDef, "permission" | "department" | "inSidebar" | "icon" | "breadcrumbParent" | "aliases">> = {},
): RouteDef => ({
  path, label, domein, component, positie,
  permission: opts.permission ?? "viewer",
  department: opts.department ?? "management",
  inSidebar: opts.inSidebar ?? true,
  icon: opts.icon,
  breadcrumbParent: opts.breadcrumbParent,
  aliases: opts.aliases,
});

export const ROUTES: RouteDef[] = [
  // --- Command Center -----------------------------------------------------
  r("/", "Mijn Dashboard", "command-center", Dashboard, 1, { icon: Home }),
  r("/command-center", "Command Center", "command-center", CommandCenter, 2, { icon: LayoutGrid }),
  r("/signalen", "Intelligence Signals", "command-center", Signalen, 3, { icon: Bell }),

  // --- Concurrentie ---------------------------------------------------------
  r("/competition", "CI Dashboard", "concurrentie", CompetitionDashboard, 1, { icon: Crosshair, department: "catman" }),
  r("/competition/discovery", "Concurrent Discovery", "concurrentie", CompetitionDiscovery, 2, { icon: Binoculars, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/competitors", "Concurrenten", "concurrentie", CompetitionCompetitors, 3, { icon: Building2, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/competitors/:id", "Concurrent-detail", "concurrentie", CompetitorDetail, 3.1, { inSidebar: false, department: "catman", breadcrumbParent: "/competition/competitors" }),
  r("/competition/categories", "Categorie-analyse", "concurrentie", CompetitionCategories, 4, { icon: Map, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/categories/:category_name", "Categorie-detail", "concurrentie", CompetitionCategories, 4.1, { inSidebar: false, department: "catman", breadcrumbParent: "/competition/categories" }),
  r("/competition/trends", "Trends & Events", "concurrentie", CompetitionTrends, 5, { icon: TrendingUp, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/ai-matching", "AI Matching", "concurrentie", CompetitionAiMatching, 6, { icon: BrainCircuit, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/assortment-gap", "Assortiment Gap", "concurrentie", CompetitionAssortmentGap, 7, { icon: PackageSearch, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/strategies", "Strategie-analyse", "concurrentie", CompetitionStrategies, 8, { icon: Radar, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/strategie-herkenning", "Prijsstrategie-herkenning", "concurrentie", PrijsstrategieHerkenning, 9, { icon: Target, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/management", "Management Intel", "concurrentie", CompetitionManagement, 10, { icon: Puzzle, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/discovery-log", "Discovery Log", "concurrentie", CompetitionDiscoveryLog, 11, { icon: GitMerge, department: "catman", breadcrumbParent: "/competition" }),
  r("/competition/settings", "CI-instellingen", "concurrentie", CompetitionSettings, 12, { icon: Settings, permission: "pricing_manager", department: "catman", breadcrumbParent: "/competition" }),
  r("/concurrentie", "PCIS Overzicht", "concurrentie", ConcurrentieIntelligence, 13, { icon: Target, department: "pricing" }),
  r("/concurrentie/:sku_id", "PCIS SKU-detail", "concurrentie", ConcurrentieDetail, 13.1, { inSidebar: false, department: "pricing", breadcrumbParent: "/concurrentie" }),
  r("/sku-concurrentie", "SKU Concurrentie (CIS)", "concurrentie", SkuConcurrentieAnalyse, 14, { icon: Target, department: "pricing" }),
  r("/monitoring", "Concurrentie-monitoring", "concurrentie", ConcurrentieMonitoring, 15, { icon: Bell, department: "catman" }),

  // --- Pricing --------------------------------------------------------------
  r("/prijsadviezen", "Prijsadviezen", "pricing", Prijsadviezen, 1, { icon: List, department: "pricing", aliases: ["/recommendations"] }),
  r("/prijsadviezen/:id", "Prijsadvies-detail", "pricing", PrijsadviesDetail, 1.1, { inSidebar: false, department: "pricing", breadcrumbParent: "/prijsadviezen", aliases: ["/recommendations/:id"] }),
  r("/elasticiteit", "Elasticiteitsmonitor", "pricing", Elasticiteitsmonitor, 2, { icon: TrendingDown, department: "pricing" }),
  r("/ppfs", "Doorberekenbaarheid (PPFS)", "pricing", PpfsAnalyse, 3, { icon: Scale, department: "pricing" }),
  r("/break-even", "Break-even-analyse", "pricing", BreakEvenAnalyse, 4, { icon: Calculator, department: "pricing" }),
  r("/margebescherming", "Margebescherming", "pricing", Margebescherming, 5, { icon: Shield, department: "pricing" }),
  r("/bcg/pricing-power", "Pricing Power", "pricing", BcgPricingPower, 6, { icon: Zap, department: "pricing" }),
  r("/uitvoering", "Uitvoering prijswijzigingen", "pricing", Uitvoering, 7, { icon: Zap, permission: "pricing_manager", department: "pricing" }),
  r("/export", "Prijsexport", "pricing", ExportPrijsShape, 8, { icon: Download, permission: "pricing_manager", department: "pricing" }),

  // --- CatMan ---------------------------------------------------------------
  r("/bcg/dashboard", "BCG Dashboard", "catman", BcgDashboard, 1, { icon: LayoutGrid, department: "catman" }),
  r("/bcg/sku-matrix", "SKU BCG-matrix", "catman", BcgSkuMatrix, 2, { icon: Target, department: "catman", breadcrumbParent: "/bcg/dashboard" }),
  r("/bcg/sku/:sku_id", "SKU BCG-detail", "catman", BcgSkuDetail, 2.1, { inSidebar: false, department: "catman", breadcrumbParent: "/bcg/sku-matrix" }),
  r("/bcg/categorie", "Categorie-BCG", "catman", BcgCategorie, 3, { icon: Layers, department: "catman", breadcrumbParent: "/bcg/dashboard" }),
  r("/bcg/hybrid", "Hybrid Pricing Matrix", "catman", BcgHybrid, 4, { icon: Sigma, department: "catman", breadcrumbParent: "/bcg/dashboard" }),
  r("/bcg/huismerk", "Huismerk Intelligence", "catman", BcgHuismerk, 5, { icon: Tag, department: "catman", breadcrumbParent: "/bcg/dashboard" }),
  r("/bcg/transities", "BCG-transities", "catman", BcgTransities, 6, { icon: GitBranch, department: "catman", breadcrumbParent: "/bcg/dashboard" }),
  r("/huismerk-impact", "Huismerk-impact (ISV)", "catman", HuismerkImpact, 7, { icon: ArrowRightLeft, department: "catman" }),
  r("/substituties", "Substitutiemonitor", "catman", Substitutiemonitor, 8, { icon: LineChart, department: "catman", aliases: ["/substitutions"] }),

  // --- Inkoop ---------------------------------------------------------------
  r("/kostprijswijziging", "Inkoopprijswijziging", "inkoop", KostprijswijzigingDashboard, 1, { icon: ArrowUpDown, department: "inkoop" }),
  r("/procurement", "Procurement Forecast", "inkoop", ProcurementForecast, 2, { icon: ShoppingCart, department: "inkoop" }),

  // --- Supply Chain -----------------------------------------------------------
  r("/kosten/dashboard", "Kostenoverzicht", "supply-chain", KostenDashboard, 1, { icon: DollarSign, department: "supply_chain" }),
  r("/kosten/operationeel", "Operationele complexiteit", "supply-chain", OperationeleComplexiteit, 2, { icon: Cpu, department: "supply_chain", breadcrumbParent: "/kosten/dashboard" }),

  // --- Search & Digital Growth -----------------------------------------------
  r("/traffic/dashboard", "Traffic Dashboard", "search-digital", TrafficDashboard, 1, { icon: TrendingUp, department: "digital" }),
  r("/traffic/conversie", "Conversie-monitoring", "search-digital", ConversieMonitoring, 2, { icon: Activity, department: "digital", breadcrumbParent: "/traffic/dashboard" }),
  r("/traffic/search-demand", "Search Demand", "search-digital", SearchDemand, 3, { icon: SearchIcon, department: "digital", breadcrumbParent: "/traffic/dashboard" }),
  r("/traffic/opportunity", "Traffic Opportunity", "search-digital", TrafficOpportunity, 4, { icon: Target, department: "digital", breadcrumbParent: "/traffic/dashboard" }),
  r("/traffic/search-gap", "Search Gap-analyse", "search-digital", SearchGap, 5, { icon: BarChart2, department: "digital", breadcrumbParent: "/traffic/dashboard" }),
  r("/traffic/sku/:sku_id", "Traffic SKU-detail", "search-digital", TrafficSkuDetail, 5.1, { inSidebar: false, department: "digital", breadcrumbParent: "/traffic/dashboard" }),
  r("/traffic/categorie", "Traffic per categorie", "search-digital", TrafficCategorie, 5.2, { inSidebar: false, department: "digital", breadcrumbParent: "/traffic/dashboard" }),
  r("/traffic/categorie/:category", "Traffic categorie-detail", "search-digital", TrafficCategorie, 5.3, { inSidebar: false, department: "digital", breadcrumbParent: "/traffic/dashboard" }),
  r("/traffic-driver", "Traffic Driver Score", "search-digital", TrafficDriverDashboard, 6, { icon: TrendingUp, department: "digital" }),
  r("/entry-products", "Entry Products-analyse", "search-digital", EntryProductsAnalyse, 7, { icon: Users, department: "digital" }),
  r("/kosten/marketing", "Marketing Efficiency", "search-digital", MarketingEfficiency, 8, { icon: Megaphone, department: "marketing" }),

  // --- Promoties & Loyalty -----------------------------------------------------
  r("/promotion-intelligence", "Promotion Intelligence", "promoties-loyalty", PromotionIntelligence, 1, { icon: Megaphone, department: "marketing" }),
  r("/marketing-vs-korting", "Marketing vs. korting", "promoties-loyalty", MarketingVsKorting, 2, { icon: Megaphone, department: "marketing" }),
  r("/ab-tests", "A/B-testmonitor", "promoties-loyalty", AbTestMonitor, 3, { icon: FlaskConical, department: "marketing" }),
  r("/basket-intelligence", "Basket Intelligence", "promoties-loyalty", BasketIntelligenceDashboard, 4, { icon: ShoppingCart, department: "marketing" }),
  r("/cross-sell", "Cross-sell Intelligence", "promoties-loyalty", CrossSellIntelligence, 5, { icon: ArrowRightLeft, department: "marketing" }),
  r("/sku-ecosystem", "SKU-ecosysteemwaarde", "promoties-loyalty", SkuEcosysteem, 6, { icon: Layers, department: "marketing" }),
  r("/loyalty", "Loyalty-overzicht", "promoties-loyalty", LoyaltyDashboard, 7, { icon: HeartHandshake, department: "marketing" }),
  r("/loyalty/leden/:id", "Loyalty-lid", "promoties-loyalty", LoyaltyMemberDetail, 7.1, { inSidebar: false, department: "marketing", breadcrumbParent: "/loyalty" }),
  r("/customer-value", "Customer Value", "promoties-loyalty", CustomerValue, 8, { icon: Gem, department: "marketing" }),

  // --- Forecast & Risico ---------------------------------------------------------
  r("/forecast-risk", "Forecast & Risk", "forecast-risico", ForecastRisk, 1, { icon: TrendingUp, department: "supply_chain" }),
  r("/economie", "Economic Intelligence", "forecast-risico", EconomieDashboard, 2, { icon: Globe2 }),

  // --- Product & Data --------------------------------------------------------
  r("/producten", "Producten", "product-data", Producten, 1, { icon: Box, department: "data", aliases: ["/skus"] }),
  r("/producten/:id", "Product-detail", "product-data", ProductDetail, 1.1, { inSidebar: false, department: "data", breadcrumbParent: "/producten", aliases: ["/skus/:id"] }),
  r("/producthierarchie", "Producthiërarchie", "product-data", ProductHierarchie, 2, { icon: FolderTree, department: "data" }),
  r("/categorieen", "Categorieregels", "product-data", Categorieen, 3, { icon: Layers, department: "data", aliases: ["/categories"] }),
  r("/categorieen/hierarchie", "Categorieënhiërarchie", "product-data", CategorieHierarchie, 4, { icon: FolderTree, department: "data", breadcrumbParent: "/categorieen", aliases: ["/categories/hierarchy"] }),
  r("/content-completeness", "Content Completeness (PIM)", "product-data", PimContent, 5, { icon: Layers, department: "data" }),
  r("/contentsuggesties", "AI-contentsuggesties", "product-data", PimSuggestions, 6, { icon: Sparkles, department: "data" }),
  r("/datakwaliteit", "Datakwaliteit", "product-data", Datakwaliteit, 7, { icon: Database, department: "data", aliases: ["/data-quality"] }),
  r("/data-integratie", "Data-integratie (overzicht)", "product-data", DataIntegratie, 8, { icon: GitMerge, department: "data" }),
  r("/connectoren", "Connectoren", "product-data", Connectoren, 9, { icon: Server, permission: "admin", department: "data" }),
  r("/drs-integratie", "DRS-integratie", "product-data", DrsIntegratie, 10, { icon: Database, department: "data" }),
  r("/ga4-integratie", "GA4-integratie", "product-data", Ga4Integratie, 11, { icon: TrendingUp, department: "data" }),
  r("/gegevensintegratie", "Handmatige upload", "product-data", Gegevensintegratie, 12, { icon: Upload, department: "data", aliases: ["/data-upload"] }),

  // --- AI & Besluitvorming -----------------------------------------------------
  r("/copilot", "AI Copilot", "ai-besluitvorming", Copilot, 1, { icon: Sparkles }),
  r("/copilot-kwaliteit", "Copilot-kwaliteit", "ai-besluitvorming", CopilotKwaliteit, 2, { icon: ThumbsUp, breadcrumbParent: "/copilot" }),
  r("/beslissingen", "Beslissingen", "ai-besluitvorming", Beslissingen, 3, { icon: BrainCircuit, department: "pricing" }),
  r("/beslissingen/:id", "Beslissing-detail", "ai-besluitvorming", BeslissingDetail, 3.1, { inSidebar: false, department: "pricing", breadcrumbParent: "/beslissingen" }),
  r("/opportunities", "Opportunity Engine", "ai-besluitvorming", Opportunities, 4, { icon: Lightbulb }),
  r("/modelgezondheid", "Modelgezondheid", "ai-besluitvorming", Modelgezondheid, 5, { icon: Activity, department: "data", aliases: ["/model-health"] }),
  r("/modelregister", "Modelregister", "ai-besluitvorming", ModelRegistry, 6, { icon: History, department: "data" }),
  r("/modeldocumentatie", "Modeldocumentatie", "ai-besluitvorming", ModelDocumentatie, 7, { icon: BookOpen }),

  // --- Management -------------------------------------------------------------
  r("/rapportages", "Management-rapportages", "management", ManagementRapportages, 1, { icon: FileText }),
  r("/platform/health", "Platform Health Center", "management", PlatformHealth, 2, { icon: Activity }),
  r("/platform/kosten", "Cost & Scalability", "management", PlatformKosten, 3, { icon: DollarSign }),
  r("/platform/businesscase", "Businesscase per shop", "management", PlatformBusinesscase, 4, { icon: Calculator }),
  r("/platform/waarde", "Business Value-meting", "management", BusinessValue, 5, { icon: TrendingUp }),
  r("/platform/gap", "Gap Dashboard", "management", PlatformGap, 6, { icon: Target }),
  r("/eindevaluatie", "Eindevaluatie", "management", Eindevaluatie, 7, { icon: ClipboardCheck }),

  // --- Beheer -------------------------------------------------------------------
  r("/instellingen", "Instellingen", "beheer", Instellingen, 1, { icon: Settings, permission: "pricing_manager", department: "beheer", aliases: ["/settings"] }),
  r("/audit-log", "Audit Log", "beheer", AuditLogPage, 2, { icon: ClipboardList, permission: "pricing_manager", department: "beheer" }),
  r("/documentatie", "Platformdocumentatie", "beheer", DocsCenter, 3, { icon: FileText, department: "beheer" }),
  r("/backlog", "Development Backlog", "beheer", DevBacklog, 4, { icon: ClipboardList, department: "beheer" }),
];

// ---------------------------------------------------------------------------
// Redirects (oude paden → canoniek pad), afgeleid uit `aliases`
// ---------------------------------------------------------------------------
export interface RedirectDef { from: string; to: string; }

export const REDIRECTS: RedirectDef[] = ROUTES.flatMap((route) =>
  (route.aliases ?? []).map((from) => ({ from, to: route.path })),
);

// ---------------------------------------------------------------------------
// Helpers: matching, sidebar-model en breadcrumbs
// ---------------------------------------------------------------------------

/** Matcht een concreet pad tegen een registry-pad met :params. */
export function padMatcht(routePath: string, location: string): boolean {
  if (routePath === location) return true;
  const rSegs = routePath.split("/").filter(Boolean);
  const lSegs = location.split("/").filter(Boolean);
  if (rSegs.length !== lSegs.length) return false;
  return rSegs.every((seg, i) => seg.startsWith(":") || seg === lSegs[i]);
}

/** Zoekt de registry-route voor de huidige locatie (meest specifieke match). */
export function vindRoute(location: string): RouteDef | undefined {
  const zonderQuery = location.split("?")[0];
  // Exacte match wint; daarna param-match met de meeste statische segmenten.
  const kandidaten = ROUTES.filter((route) => padMatcht(route.path, zonderQuery));
  if (kandidaten.length === 0) return undefined;
  return kandidaten.sort((a, b) => {
    const statisch = (p: string) => p.split("/").filter((s) => s && !s.startsWith(":")).length;
    const params = (p: string) => p.split("/").filter((s) => s.startsWith(":")).length;
    return statisch(b.path) - statisch(a.path) || params(a.path) - params(b.path);
  })[0];
}

export function vindDomein(id: DomeinId): Domein {
  return DOMEINEN.find((d) => d.id === id)!;
}

export interface SidebarGroep {
  domein: Domein;
  items: RouteDef[];
}

/**
 * Sidebar-model: 13 domeinen in vaste volgorde met hun zichtbare routes.
 * "Mijn Dashboard" ("/") wordt apart bovenaan gepind en zit niet in een groep.
 */
export function sidebarModel(): SidebarGroep[] {
  return [...DOMEINEN]
    .sort((a, b) => a.positie - b.positie)
    .map((domein) => ({
      domein,
      items: ROUTES
        .filter((route) => route.domein === domein.id && route.inSidebar && route.path !== "/")
        .sort((a, b) => a.positie - b.positie),
    }))
    .filter((groep) => groep.items.length > 0);
}

export const MIJN_DASHBOARD: RouteDef = ROUTES.find((route) => route.path === "/")!;

export interface Kruimel {
  label: string;
  href?: string;
}

/** Breadcrumb-pad voor een locatie: Domein > (ouders...) > Pagina. */
export function breadcrumbsVoor(location: string): Kruimel[] {
  const route = vindRoute(location);
  if (!route) return [];
  const keten: RouteDef[] = [];
  let huidige: RouteDef | undefined = route;
  const bezocht = new Set<string>();
  while (huidige && !bezocht.has(huidige.path)) {
    bezocht.add(huidige.path);
    keten.unshift(huidige);
    huidige = huidige.breadcrumbParent
      ? ROUTES.find((x) => x.path === huidige!.breadcrumbParent)
      : undefined;
  }
  const kruimels: Kruimel[] = [];
  if (route.path !== "/") {
    kruimels.push({ label: vindDomein(route.domein).label });
  }
  keten.forEach((schakel, i) => {
    const laatste = i === keten.length - 1;
    kruimels.push({
      label: schakel.label,
      // Alleen ouders zonder :params zijn klikbaar; de huidige pagina niet.
      href: !laatste && !schakel.path.includes(":") ? schakel.path : undefined,
    });
  });
  return kruimels;
}
