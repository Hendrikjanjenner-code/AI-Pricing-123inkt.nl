import { useAuth } from "@/lib/auth";
import { Link, useLocation } from "wouter";
import {
  BarChart3,
  HeartHandshake,
  Gem,
  Settings,
  Upload,
  Database,
  LogOut,
  List,
  Box,
  Activity,
  Layers,
  ArrowRightLeft,
  Download,
  Crosshair,
  FlaskConical,
  TrendingDown,
  Target,
  LineChart,
  Globe,
  Link2,
  Bell,
  Zap,
  ClipboardList,
  LayoutGrid,
  Tag,
  Sigma,
  TrendingUp,
  SearchIcon,
  BarChart2,
  DollarSign,
  Megaphone,
  Cpu,
  ShoppingCart,
  Globe2,
  FileText,
  GitBranch,
  ArrowUpDown,
  Calculator,
  Scale,
  Shield,
  Users,
  BookOpen,
  FolderTree,
  Play,
  Building2,
  Puzzle,
  GitMerge,
  Radar,
  PackageSearch,
  BrainCircuit,
  Binoculars,
  ClipboardCheck,
  Map,
  Server,
  Lightbulb,
  History,
  Sparkles,
  ThumbsUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConnectorHealthIndicator } from "@/components/layout/ConnectorHealthIndicator";
import { ShopSwitcher } from "@/components/layout/ShopSwitcher";
import { AiStatusIndicator } from "@/components/layout/AiStatusIndicator";
import { NotificationBell } from "@/components/layout/NotificationBell";

const navGroepen = [
  {
    label: "Operaties",
    items: [
      { href: "/", label: "Dashboard", icon: BarChart3 },
      { href: "/command-center", label: "Command Center", icon: LayoutGrid },
      { href: "/copilot", label: "AI Copilot", icon: Sparkles },
      { href: "/copilot-kwaliteit", label: "Copilot-kwaliteit", icon: ThumbsUp },
      { href: "/signalen", label: "Intelligence Signals", icon: Bell },
      { href: "/beslissingen", label: "Beslissingen", icon: BrainCircuit },
      { href: "/prijsadviezen", label: "Prijsadviezen", icon: List },
      { href: "/producten", label: "Producten", icon: Box },
    ],
  },
  {
    label: "Competition Intelligence",
    items: [
      { href: "/competition",                label: "CI Dashboard",          icon: Crosshair },
      { href: "/competition/discovery",      label: "Concurrent Discovery",  icon: Binoculars },
      { href: "/competition/competitors",    label: "Concurrenten",          icon: Building2 },
      { href: "/competition/categories",     label: "Categorie Analyse",     icon: Map },
      { href: "/competition/trends",         label: "Trends & Events",       icon: TrendingUp },
      { href: "/competition/ai-matching",    label: "AI Matching",           icon: BrainCircuit },
      { href: "/competition/assortment-gap", label: "Assortiment Gap",       icon: PackageSearch },
      { href: "/competition/strategies",     label: "Strategie Analyse",     icon: Radar },
      { href: "/competition/strategie-herkenning", label: "Prijsstrategie-herkenning", icon: Target },
      { href: "/competition/management",     label: "Management Intel",      icon: Puzzle },
      { href: "/competition/discovery-log",  label: "Discovery Log",         icon: GitMerge },
      { href: "/competition/settings",       label: "CI Instellingen",       icon: Settings },
    ],
  },
  {
    label: "Concurrentie (CIS/PCIS)",
    items: [
      { href: "/concurrentie",       label: "PCIS Overzicht",         icon: Target },
      { href: "/sku-concurrentie",   label: "SKU Concurrentie (CIS)", icon: Target },
      { href: "/elasticiteit",       label: "Elasticiteitsmonitor",   icon: TrendingDown },
      { href: "/huismerk-impact",    label: "Huismerk Impact (ISV)",  icon: ArrowRightLeft },
    ],
  },
  {
    label: "Dataverzameling",
    items: [
      { href: "/monitoring",       label: "Concurrentie Monitoring", icon: Bell },
    ],
  },
  {
    label: "Uitvoering",
    items: [
      { href: "/uitvoering", label: "Uitvoering Prijswijzigingen", icon: Zap },
      { href: "/audit-log",  label: "Audit Log",                   icon: ClipboardList },
    ],
  },
  {
    label: "BCG Intelligence",
    items: [
      { href: "/bcg/dashboard",    label: "BCG Dashboard",        icon: LayoutGrid },
      { href: "/bcg/sku-matrix",   label: "SKU BCG Matrix",       icon: Target },
      { href: "/bcg/categorie",    label: "Categorie BCG",        icon: Layers },
      { href: "/bcg/hybrid",       label: "Hybrid Pricing Matrix", icon: Sigma },
      { href: "/bcg/huismerk",     label: "Huismerk Intelligence", icon: Tag },
      { href: "/bcg/pricing-power",label: "Pricing Power",         icon: Zap },
      { href: "/bcg/transities",   label: "BCG Transities",        icon: GitBranch },
    ],
  },
  {
    label: "Traffic & Demand",
    items: [
      { href: "/traffic/dashboard",    label: "Traffic Dashboard",    icon: TrendingUp },
      { href: "/traffic/conversie",    label: "Conversie Monitoring", icon: Activity },
      { href: "/traffic/search-demand",label: "Search Demand",        icon: SearchIcon },
      { href: "/traffic/opportunity",  label: "Traffic Opportunity",  icon: Target },
      { href: "/traffic/search-gap",   label: "Search Gap Analyse",   icon: BarChart2 },
    ],
  },
  {
    label: "Kosten Intelligence",
    items: [
      { href: "/kosten/dashboard",    label: "Kosten Dashboard",           icon: DollarSign },
      { href: "/kosten/marketing",    label: "Marketing Efficiency",        icon: Megaphone },
      { href: "/kosten/operationeel", label: "Operationele Complexiteit",   icon: Cpu },
    ],
  },
  {
    label: "Traffic & Basket Intelligence",
    items: [
      { href: "/traffic-driver",      label: "Traffic Driver Score",     icon: TrendingUp },
      { href: "/entry-products",      label: "Entry Products Analyse",   icon: Users },
      { href: "/basket-intelligence", label: "Basket Intelligence",      icon: ShoppingCart },
      { href: "/cross-sell",          label: "Cross-sell Intelligence",  icon: ArrowRightLeft },
      { href: "/sku-ecosystem",       label: "SKU Ecosysteemwaarde",     icon: Layers },
    ],
  },
  {
    label: "Cost Change & Break-even",
    items: [
      { href: "/kostprijswijziging",  label: "Inkoopprijswijziging",     icon: ArrowUpDown },
      { href: "/ppfs",                label: "Doorberekenbaarheid (PPFS)", icon: Scale },
      { href: "/break-even",          label: "Break-even Analyse",        icon: Calculator },
      { href: "/marketing-vs-korting",label: "Marketing vs. Korting",     icon: Megaphone },
      { href: "/margebescherming",    label: "Margebescherming",          icon: Shield },
    ],
  },
  {
    label: "Forecasting & Procurement",
    items: [
      { href: "/forecast-risk",label: "Forecast & Risk",         icon: TrendingUp },
      { href: "/procurement",  label: "Procurement Forecast",    icon: ShoppingCart },
      { href: "/economie",     label: "Economic Intelligence",   icon: Globe2 },
      { href: "/rapportages",  label: "Management Rapportages",  icon: FileText },
    ],
  },
  {
    label: "Loyalty & Customer Value",
    items: [
      { href: "/loyalty",        label: "Loyalty-overzicht", icon: HeartHandshake },
      { href: "/customer-value", label: "Customer Value",    icon: Gem },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/opportunities", label: "Opportunity Engine",  icon: Lightbulb },
      { href: "/promotion-intelligence", label: "Promotion Intelligence", icon: Megaphone },
      { href: "/ab-tests",   label: "A/B-testmonitor",    icon: FlaskConical },
      { href: "/substituties",label: "Substitutiemonitor", icon: LineChart },
    ],
  },
  {
    label: "Platform & Waarde",
    items: [
      { href: "/platform/health",       label: "Platform Health Center",  icon: Activity },
      { href: "/platform/kosten",       label: "Cost & Scalability",      icon: DollarSign },
      { href: "/platform/businesscase", label: "Businesscase per shop",   icon: Calculator },
      { href: "/platform/waarde",       label: "Business Value-meting",   icon: TrendingUp },
      { href: "/platform/gap",          label: "Gap Dashboard",           icon: Target },
    ],
  },
  {
    label: "Configuratie",
    items: [
      { href: "/producthierarchie",       label: "Producthiërarchie",    icon: FolderTree },
      { href: "/categorieen",             label: "Categorieregels",      icon: Layers },
      { href: "/categorieen/hierarchie",  label: "Categorieënhiërarchie", icon: FolderTree },
      { href: "/modelgezondheid",         label: "Modelgezondheid",      icon: Activity },
      { href: "/modelregister",           label: "Modelregister",        icon: History },
      { href: "/instellingen",            label: "Instellingen",         icon: Settings },
    ],
  },
  {
    label: "Data & Integraties",
    items: [
      { href: "/data-integratie",    label: "Data-integratie (overzicht)", icon: GitMerge },
      { href: "/connectoren",        label: "Connectoren",                 icon: Server },
      { href: "/drs-integratie",     label: "DRS Integratie",              icon: Database },
      { href: "/ga4-integratie",     label: "GA4 Integratie",              icon: TrendingUp },
      { href: "/gegevensintegratie", label: "Handmatige upload",           icon: Upload },
      { href: "/datakwaliteit",      label: "Datakwaliteit",               icon: Database },
      { href: "/content-completeness", label: "Content Completeness (PIM)", icon: Layers },
      { href: "/contentsuggesties",  label: "AI-contentsuggesties",        icon: Sparkles },
      { href: "/export",             label: "Prijsexport",                 icon: Download },
    ],
  },
  {
    label: "Kennisplatform",
    items: [
      { href: "/modeldocumentatie", label: "Modeldocumentatie", icon: BookOpen },
      { href: "/documentatie",      label: "Platformdocumentatie", icon: FileText },
      { href: "/backlog",           label: "Development Backlog",  icon: ClipboardList },
      { href: "/eindevaluatie",     label: "Eindevaluatie",        icon: ClipboardCheck },
    ],
  },
];

const alleItems = navGroepen.flatMap(g => g.items);

const ROL_LABELS: Record<string, string> = {
  admin: "Beheerder",
  pricing_manager: "Prijsmanager",
  analyst: "Analist",
  viewer: "Lezer",
};

export function SidebarLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const [location] = useLocation();

  if (!user) return null;

  const huidigLabel = alleItems.find(i =>
    i.href === "/" ? location === "/" : location.startsWith(i.href)
  )?.label || "Werkruimte";

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <div className="w-64 bg-sidebar border-r border-sidebar-border text-sidebar-foreground flex flex-col flex-shrink-0">
        <div className="h-16 flex items-center px-6 border-b border-sidebar-border font-bold text-xl tracking-tight text-sidebar-primary">
          <Box className="w-6 h-6 mr-3" />
          Pricing Engine
        </div>

        <div className="flex-1 overflow-y-auto py-4 flex flex-col gap-0 px-3">
          {navGroepen.map((groep) => (
            <div key={groep.label} className="mb-3">
              <div className="text-xs font-semibold text-sidebar-foreground/40 uppercase tracking-wider mb-1 px-2">
                {groep.label}
              </div>
              {groep.items.map((item) => {
                const isActief = location === item.href || (item.href !== "/" && location.startsWith(item.href));
                const Icon = item.icon;
                return (
                  <Link key={item.href} href={item.href}>
                    <div className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${
                      isActief
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                    }`}>
                      <Icon className="w-4 h-4 shrink-0" />
                      {item.label}
                    </div>
                  </Link>
                );
              })}
            </div>
          ))}
        </div>

        <div className="p-4 border-t border-sidebar-border bg-sidebar-accent/20">
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="w-8 h-8 rounded-full bg-sidebar-primary flex items-center justify-center text-sidebar-primary-foreground font-bold text-sm">
              {user.username?.charAt(0).toUpperCase()}
            </div>
            <div className="flex flex-col flex-1 overflow-hidden">
              <span className="text-sm font-medium truncate">{user.full_name || user.username}</span>
              <span className="text-xs text-sidebar-foreground/50 truncate">
                {ROL_LABELS[user.role] || user.role.replace('_', ' ')}
              </span>
            </div>
            <Button variant="ghost" size="icon" onClick={logout}
              className="text-sidebar-foreground/70 hover:text-sidebar-foreground h-8 w-8">
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      <main className="flex-1 flex flex-col overflow-hidden bg-background">
        <header className="h-16 border-b bg-card flex items-center justify-between px-8 shrink-0">
          <div className="font-semibold text-foreground">{huidigLabel}</div>
          <div className="flex items-center gap-2">
            {user.role === "admin" && <ShopSwitcher />}
            <AiStatusIndicator />
            <ConnectorHealthIndicator />
            <NotificationBell />
          </div>
        </header>
        <div className="flex-1 overflow-auto p-8">
          <div className="mx-auto max-w-7xl">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
