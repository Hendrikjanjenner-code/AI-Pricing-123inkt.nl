/**
 * InfoTooltip — herbruikbare (i)-knop met hover-tooltip en klik-modal.
 *
 * Gebruik:
 *   <InfoTooltip definitieId="pcis" />          — opzoeken in KPI_DEFINITIES
 *   <InfoTooltip inline={{                       — aangepaste definitie (inline)
 *     naam: "Mijn KPI",
 *     korteUitleg: "Korte uitleg",
 *     uitgebreideUitleg: "Lange uitleg...",
 *     interpretatie: "Schaal...",
 *     businessImpact: "Impact...",
 *   }} />
 */
import { useState, useRef } from "react";
import { Info, X, BookOpen, Calculator, TrendingUp, Lightbulb } from "lucide-react";
import { KPI_DEFINITIES, type KpiDefinition } from "@/lib/kpi-definitions";

interface InlineDefinition {
  naam: string;
  afkorting?: string;
  korteUitleg: string;
  uitgebreideUitleg: string;
  formule?: string;
  interpretatie: string;
  businessImpact: string;
  voorbeeld?: string;
}

interface InfoTooltipProps {
  definitieId?: string;
  inline?: InlineDefinition;
  size?: "sm" | "md";
  className?: string;
}

export function InfoTooltip({ definitieId, inline, size = "sm", className = "" }: InfoTooltipProps) {
  const [showModal, setShowModal] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const def: KpiDefinition | InlineDefinition | undefined =
    definitieId ? KPI_DEFINITIES[definitieId] : inline;

  if (!def) return null;

  const iconSize = size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4";

  return (
    <>
      <span className={`relative inline-flex items-center ${className}`}>
        <button
          type="button"
          className={`inline-flex items-center justify-center rounded-full text-muted-foreground/60 hover:text-primary hover:bg-primary/10 transition-colors focus:outline-none focus:ring-1 focus:ring-primary/30 ${size === "sm" ? "w-4 h-4" : "w-5 h-5"}`}
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
          onClick={(e) => { e.stopPropagation(); setShowTooltip(false); setShowModal(true); }}
          aria-label={`Uitleg over ${def.naam}`}
        >
          <Info className={iconSize} />
        </button>

        {/* Hover tooltip */}
        {showTooltip && (
          <div
            ref={tooltipRef}
            className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 pointer-events-none"
          >
            <div className="bg-popover border border-border rounded-lg shadow-lg p-3 text-xs text-left">
              <div className="font-semibold text-foreground mb-1 flex items-center gap-1.5">
                {"afkorting" in def && def.afkorting && (
                  <span className="bg-primary/10 text-primary rounded px-1 py-0.5 text-[10px] font-mono">{def.afkorting}</span>
                )}
                {def.naam}
              </div>
              <p className="text-muted-foreground leading-relaxed">{def.korteUitleg}</p>
              <p className="text-primary/70 mt-1.5 text-[10px]">Klik voor volledige uitleg →</p>
            </div>
            {/* Pijl */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 -translate-y-px border-4 border-transparent border-t-border" />
          </div>
        )}
      </span>

      {/* Uitleg Modal */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          onClick={() => setShowModal(false)}
        >
          <div
            className="relative bg-card border border-border rounded-xl shadow-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="sticky top-0 bg-card border-b border-border px-5 py-4 flex items-start justify-between gap-3 z-10">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  {"afkorting" in def && def.afkorting && (
                    <span className="bg-primary text-primary-foreground rounded-md px-2 py-0.5 text-xs font-mono font-bold">{def.afkorting}</span>
                  )}
                  <h2 className="text-base font-bold text-foreground">{def.naam}</h2>
                </div>
                {("categorie" in def && def.categorie)
                  ? <p className="text-xs text-muted-foreground mt-0.5 capitalize">{String(def.categorie).replace(/_/g, " ")}</p>
                  : null}
              </div>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Content */}
            <div className="px-5 py-4 space-y-4 text-sm">
              {/* Uitgebreide uitleg */}
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  <BookOpen className="w-3.5 h-3.5" />
                  Uitleg
                </div>
                <p className="text-foreground leading-relaxed whitespace-pre-line">{def.uitgebreideUitleg}</p>
              </div>

              {/* Formule */}
              {def.formule && (
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                    <Calculator className="w-3.5 h-3.5" />
                    Formule
                  </div>
                  <div className="bg-muted/40 border border-border rounded-lg p-3 font-mono text-xs whitespace-pre-line text-foreground/80">
                    {def.formule}
                  </div>
                </div>
              )}

              {/* Interpretatie */}
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  <TrendingUp className="w-3.5 h-3.5" />
                  Interpretatie schaal
                </div>
                <div className="bg-muted/20 rounded-lg p-3 text-xs whitespace-pre-line text-foreground/80 leading-relaxed font-mono">
                  {def.interpretatie}
                </div>
              </div>

              {/* Business impact */}
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  <Lightbulb className="w-3.5 h-3.5" />
                  Impact op pricingstrategie
                </div>
                <p className="text-foreground/80 leading-relaxed whitespace-pre-line">{def.businessImpact}</p>
              </div>

              {/* Voorbeeld */}
              {def.voorbeeld && (
                <div className="bg-primary/5 border border-primary/20 rounded-lg p-3">
                  <div className="text-xs font-semibold text-primary mb-1">📌 Praktijkvoorbeeld</div>
                  <p className="text-xs text-foreground/80 leading-relaxed">{def.voorbeeld}</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 bg-card border-t border-border px-5 py-3 flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Klik buiten het venster om te sluiten</span>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="text-xs bg-primary text-primary-foreground rounded-md px-3 py-1.5 hover:opacity-90 transition-opacity"
              >
                Sluiten
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default InfoTooltip;
