import { Link, useLocation } from "wouter";
import { ChevronRight } from "lucide-react";
import { breadcrumbsVoor } from "@/lib/route-registry";
import { useGlobalFilters } from "@/hooks/use-global-filters";
import { activeContextSummary } from "@/components/filters/GlobalFilterBar";

/**
 * Breadcrumbs boven ieder scherm, gegenereerd uit de Route Registry:
 * Domein > (ouders) > Pagina > actieve hiërarchie-/filtercontext.
 */
export function Breadcrumbs() {
  const [location] = useLocation();
  const kruimels = breadcrumbsVoor(location);
  const globalFilters = useGlobalFilters();
  const contextSummary = activeContextSummary(globalFilters);

  if (kruimels.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" data-testid="breadcrumbs" className="min-w-0">
      <ol className="flex items-center gap-1 text-sm min-w-0 flex-wrap">
        {kruimels.map((kruimel, i) => {
          const laatste = i === kruimels.length - 1 && !contextSummary;
          return (
            <li key={`${kruimel.label}-${i}`} className="flex items-center gap-1 min-w-0">
              {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50 shrink-0" />}
              {kruimel.href ? (
                <Link href={kruimel.href}>
                  <span className="text-muted-foreground hover:text-foreground cursor-pointer truncate">
                    {kruimel.label}
                  </span>
                </Link>
              ) : (
                <span
                  className={laatste || i === kruimels.length - 1
                    ? "font-semibold text-foreground truncate"
                    : "text-muted-foreground truncate"}
                  aria-current={i === kruimels.length - 1 ? "page" : undefined}
                >
                  {kruimel.label}
                </span>
              )}
            </li>
          );
        })}
        {contextSummary && (
          <li className="flex items-center gap-1 min-w-0" data-testid="breadcrumb-context">
            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50 shrink-0" />
            <span className="text-xs text-muted-foreground truncate" title={contextSummary}>
              {contextSummary}
            </span>
          </li>
        )}
      </ol>
    </nav>
  );
}
