import { useAuth } from "@/lib/auth";
import { Link, useLocation } from "wouter";
import {
  BarChart3,
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
} from "lucide-react";
import { Button } from "@/components/ui/button";

const navGroepen = [
  {
    label: "Operaties",
    items: [
      { href: "/", label: "Dashboard", icon: BarChart3 },
      { href: "/prijsadviezen", label: "Prijsadviezen", icon: List },
      { href: "/producten", label: "Producten", icon: Box },
    ],
  },
  {
    label: "Concurrentie-analyse",
    items: [
      { href: "/concurrentie", label: "Concurrentie-intelligentie", icon: Crosshair },
      { href: "/sku-concurrentie", label: "SKU Concurrentie (CIS)", icon: Target },
      { href: "/elasticiteit", label: "Elasticiteitsmonitor", icon: TrendingDown },
      { href: "/huismerk-impact", label: "Huismerk Impact (ISV)", icon: ArrowRightLeft },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/ab-tests", label: "A/B-testmonitor", icon: FlaskConical },
      { href: "/substituties", label: "Substitutiemonitor", icon: LineChart },
    ],
  },
  {
    label: "Configuratie",
    items: [
      { href: "/categorieen", label: "Categorieregels", icon: Layers },
      { href: "/modelgezondheid", label: "Modelgezondheid", icon: Activity },
    ],
  },
  {
    label: "Gegevens",
    items: [
      { href: "/datakwaliteit", label: "Datakwaliteit", icon: Database },
      { href: "/gegevensintegratie", label: "Gegevensintegratie", icon: Upload },
      { href: "/export", label: "Export naar PriceShape", icon: Download },
      { href: "/instellingen", label: "Instellingen", icon: Settings },
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
