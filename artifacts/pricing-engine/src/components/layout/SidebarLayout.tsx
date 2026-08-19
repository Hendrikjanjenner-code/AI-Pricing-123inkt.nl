import { useEffect, useState, useSyncExternalStore } from "react";
import { useAuth } from "@/lib/auth";
import { Link, useLocation } from "wouter";
import { Box, LogOut, ChevronDown, ChevronRight, Star, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GlobalSearch } from "@/components/layout/GlobalSearch";
import { useDepartmentDefaultView } from "@/components/filters/SavedViewsMenu";
import {
  ensureUserPrefsLoaded, getUserPrefs, subscribeUserPrefs,
  isFavorite, toggleFavorite, recordRecentVisit,
} from "@/lib/user-prefs";
import { ConnectorHealthIndicator } from "@/components/layout/ConnectorHealthIndicator";
import { useFilterUrlSync } from "@/hooks/use-global-filters";
import { ShopSwitcher } from "@/components/layout/ShopSwitcher";
import { AiStatusIndicator } from "@/components/layout/AiStatusIndicator";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import {
  sidebarModel, vindRoute, MIJN_DASHBOARD, type DomeinId, type RouteDef,
} from "@/lib/route-registry";


const OPEN_GROEPEN_KEY = "sidebar.openDomeinen";

function leesOpenGroepen(): DomeinId[] | null {
  try {
    const raw = sessionStorage.getItem(OPEN_GROEPEN_KEY);
    return raw ? (JSON.parse(raw) as DomeinId[]) : null;
  } catch {
    return null;
  }
}

function bewaarOpenGroepen(open: DomeinId[]) {
  try {
    sessionStorage.setItem(OPEN_GROEPEN_KEY, JSON.stringify(open));
  } catch {
    /* sessionStorage kan geblokkeerd zijn; sidebar werkt dan zonder persistentie */
  }
}

const ROL_LABELS: Record<string, string> = {
  admin: "Beheerder",
  pricing_manager: "Prijsmanager",
  analyst: "Analist",
  viewer: "Lezer",
};

function isRouteActief(item: RouteDef, location: string): boolean {
  if (item.path === "/") return location === "/";
  return location === item.path || location.startsWith(`${item.path}/`);
}

function NavItem({ item, location }: { item: RouteDef; location: string }) {
  const actief = isRouteActief(item, location);
  const Icon = item.icon ?? Box;
  const fav = isFavorite(item.path);
  return (
    <Link href={item.path}>
      <div
        data-testid={`nav-${item.path}`}
        className={`group/nav flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium transition-colors cursor-pointer ${
          actief
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
        }`}
      >
        <Icon className="w-4 h-4 shrink-0" />
        <span className="truncate flex-1">{item.label}</span>
        <button
          type="button"
          aria-label={fav ? "Verwijder uit favorieten" : "Voeg toe aan favorieten"}
          data-testid={`fav-toggle-${item.path}`}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleFavorite({ path: item.path, label: item.label });
          }}
          className={`shrink-0 transition-opacity ${
            fav ? "opacity-100 text-amber-400" : "opacity-0 group-hover/nav:opacity-60 hover:!opacity-100"
          }`}
        >
          <Star className={`w-3.5 h-3.5 ${fav ? "fill-amber-400" : ""}`} />
        </button>
      </div>
    </Link>
  );
}

/** Favorieten + recent bezochte pagina's, gepind boven de domeingroepen. */
function FavorietenSectie({ location }: { location: string }) {
  const prefs = useSyncExternalStore(subscribeUserPrefs, getUserPrefs);
  if (!prefs.loaded || (prefs.favorites.length === 0 && prefs.recents.length === 0)) {
    return null;
  }
  const favPaths = new Set(prefs.favorites.map((f) => f.path));
  const recents = prefs.recents.filter((r) => !favPaths.has(r.path)).slice(0, 4);
  return (
    <div className="mb-3" data-testid="sidebar-favorieten">
      {prefs.favorites.length > 0 && (
        <>
          <div className="flex items-center gap-2 px-2 py-1 text-xs font-semibold uppercase tracking-wider text-sidebar-foreground/50">
            <Star className="w-3.5 h-3.5" /> Favorieten
          </div>
          {prefs.favorites.map((f) => {
            const route = vindRoute(f.path);
            return (
              <NavItem
                key={f.path}
                item={route ?? { ...MIJN_DASHBOARD, path: f.path, label: f.label }}
                location={location}
              />
            );
          })}
        </>
      )}
      {recents.length > 0 && (
        <>
          <div className="flex items-center gap-2 px-2 py-1 mt-1 text-xs font-semibold uppercase tracking-wider text-sidebar-foreground/50">
            <Clock className="w-3.5 h-3.5" /> Recent
          </div>
          {recents.map((rec) => (
            <Link key={rec.path} href={rec.path}>
              <div
                data-testid={`recent-${rec.path}`}
                className="flex items-center gap-3 px-3 py-1 rounded-md text-sm text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground cursor-pointer"
              >
                <Clock className="w-3.5 h-3.5 shrink-0 opacity-50" />
                <span className="truncate">{rec.label}</span>
              </div>
            </Link>
          ))}
        </>
      )}
    </div>
  );
}

export function SidebarLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const [location] = useLocation();
  // Houd de f_-URL-params op élke route in sync (deelbare deep links),
  // ook op schermen zonder GlobalFilterBar.
  useFilterUrlSync();
  // Department-default saved view (taak #221): éénmalig per sessie toepassen
  // als de gebruiker zonder eigen filtercontext binnenkomt.
  useDepartmentDefaultView();
  // Favorieten/recents live-houden (herrender bij wijziging).
  useSyncExternalStore(subscribeUserPrefs, getUserPrefs);

  const actieveRoute = vindRoute(location);

  // Per gebruiker laden; een gebruikerswissel reset en herlaadt de store.
  useEffect(() => {
    if (user?.id != null) void ensureUserPrefsLoaded(user.id);
  }, [user?.id]);

  // Recent bezochte pagina's bijhouden (alleen registry-pagina's).
  useEffect(() => {
    const route = vindRoute(location);
    if (route && !route.path.includes(":")) {
      recordRecentVisit({ path: location.split("?")[0], label: route.label });
    }
  }, [location]);
  const [openDomeinen, setOpenDomeinen] = useState<Set<DomeinId>>(() => {
    const bewaard = leesOpenGroepen();
    const open = new Set<DomeinId>(bewaard ?? ["command-center"]);
    if (actieveRoute) open.add(actieveRoute.domein);
    return open;
  });

  if (!user) return null;

  // Workspace-gedreven sidebar (taak 219): domeinen en items worden
  // gefilterd op de afdeling(en) en permissies van de gebruiker.
  const groepen = sidebarModel(user);

  const toggleDomein = (id: DomeinId) => {
    setOpenDomeinen((huidig) => {
      const volgend = new Set(huidig);
      if (volgend.has(id)) volgend.delete(id);
      else volgend.add(id);
      bewaarOpenGroepen([...volgend]);
      return volgend;
    });
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <div className="w-64 bg-sidebar border-r border-sidebar-border text-sidebar-foreground flex flex-col flex-shrink-0">
        <div className="h-16 flex items-center px-6 border-b border-sidebar-border font-bold text-xl tracking-tight text-sidebar-primary">
          <Box className="w-6 h-6 mr-3" />
          Pricing Engine
        </div>

        <div className="flex-1 overflow-y-auto py-4 flex flex-col gap-0 px-3">
          {/* Mijn Dashboard — altijd bovenaan, buiten de domeingroepen */}
          <div className="mb-3">
            <NavItem item={MIJN_DASHBOARD} location={location} />
          </div>

          {/* Favorieten & recent — gepind boven de domeingroepen (taak #221) */}
          <FavorietenSectie location={location} />

          {groepen.map(({ domein, items }) => {
            const open = openDomeinen.has(domein.id);
            const bevatActief = actieveRoute?.domein === domein.id;
            const DomeinIcon = domein.icon;
            return (
              <div key={domein.id} className="mb-1">
                <button
                  type="button"
                  onClick={() => toggleDomein(domein.id)}
                  data-testid={`nav-groep-${domein.id}`}
                  aria-expanded={open}
                  className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs font-semibold uppercase tracking-wider transition-colors ${
                    bevatActief && !open
                      ? "text-sidebar-foreground"
                      : "text-sidebar-foreground/50 hover:text-sidebar-foreground"
                  }`}
                >
                  {open
                    ? <ChevronDown className="w-3.5 h-3.5 shrink-0" />
                    : <ChevronRight className="w-3.5 h-3.5 shrink-0" />}
                  <DomeinIcon className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate text-left">{domein.label}</span>
                </button>
                {open && (
                  <div className="ml-2 border-l border-sidebar-border pl-2 py-0.5">
                    {items.map((item) => (
                      <NavItem key={item.path} item={item} location={location} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
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
                {user.departments?.length
                  ? ` · ${user.departments.map((d: any) => d.name).join(", ")}`
                  : ""}
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
        <header className="h-16 border-b bg-card flex items-center justify-between px-8 shrink-0 gap-4">
          <Breadcrumbs />
          <div className="flex items-center gap-2 shrink-0">
            <GlobalSearch />
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
