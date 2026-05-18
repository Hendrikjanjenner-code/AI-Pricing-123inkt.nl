import { useState, useMemo } from "react";
import { Search, BookOpen, Calculator, TrendingUp, Lightbulb, ChevronRight, Info, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { KPI_DEFINITIES, ALLE_CATEGORIEEN, type KpiDefinition, type KpiCategorie } from "@/lib/kpi-definitions";

const CATEGORIE_KLEUREN: Record<KpiCategorie, string> = {
  concurrentie: "bg-red-100 text-red-700 border-red-200",
  pricing:      "bg-blue-100 text-blue-700 border-blue-200",
  marge:        "bg-orange-100 text-orange-700 border-orange-200",
  traffic:      "bg-emerald-100 text-emerald-700 border-emerald-200",
  basket:       "bg-purple-100 text-purple-700 border-purple-200",
  ecosysteem:   "bg-indigo-100 text-indigo-700 border-indigo-200",
  bcg:          "bg-amber-100 text-amber-700 border-amber-200",
  forecasting:  "bg-cyan-100 text-cyan-700 border-cyan-200",
  promotie:     "bg-pink-100 text-pink-700 border-pink-200",
  algemeen:     "bg-slate-100 text-slate-600 border-slate-200",
};

function KpiKaart({ def }: { def: KpiDefinition }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-card border rounded-lg overflow-hidden">
      <button
        className="w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-muted/30 transition-colors"
        onClick={() => setOpen(!open)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {def.afkorting && (
              <span className="bg-primary text-primary-foreground rounded px-1.5 py-0.5 text-[10px] font-mono font-bold">{def.afkorting}</span>
            )}
            <span className="font-semibold text-sm">{def.naam}</span>
            <Badge variant="outline" className={`text-[10px] capitalize ${CATEGORIE_KLEUREN[def.categorie]}`}>
              {def.categorie}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{def.korteUitleg}</p>
        </div>
        <ChevronRight className={`w-4 h-4 text-muted-foreground shrink-0 transition-transform ${open ? "rotate-90" : ""}`} />
      </button>

      {open && (
        <div className="border-t border-border px-4 py-4 space-y-4 text-sm bg-muted/5">
          {/* Uitleg */}
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              <BookOpen className="w-3.5 h-3.5" /> Uitleg
            </div>
            <p className="text-foreground leading-relaxed whitespace-pre-line text-sm">{def.uitgebreideUitleg}</p>
          </div>

          {/* Formule */}
          {def.formule && (
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                <Calculator className="w-3.5 h-3.5" /> Formule
              </div>
              <div className="bg-muted/40 border border-border rounded-lg p-3 font-mono text-xs whitespace-pre-line text-foreground/80">
                {def.formule}
              </div>
            </div>
          )}

          {/* Interpretatie */}
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              <TrendingUp className="w-3.5 h-3.5" /> Interpretatie schaal
            </div>
            <div className="bg-muted/20 rounded-lg p-3 text-xs whitespace-pre-line font-mono text-foreground/80 leading-relaxed">
              {def.interpretatie}
            </div>
          </div>

          {/* Business impact */}
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              <Lightbulb className="w-3.5 h-3.5" /> Impact op pricingstrategie
            </div>
            <p className="text-foreground/80 text-sm leading-relaxed whitespace-pre-line">{def.businessImpact}</p>
          </div>

          {/* Voorbeeld */}
          {def.voorbeeld && (
            <div className="bg-primary/5 border border-primary/20 rounded-lg p-3">
              <div className="text-xs font-semibold text-primary mb-1">📌 Praktijkvoorbeeld</div>
              <p className="text-xs text-foreground/80 leading-relaxed">{def.voorbeeld}</p>
            </div>
          )}

          {/* Gerelateerd */}
          {def.gerelateerd && def.gerelateerd.length > 0 && (
            <div>
              <div className="text-xs text-muted-foreground mb-1.5">Gerelateerde metrics</div>
              <div className="flex flex-wrap gap-1.5">
                {def.gerelateerd.map(id => {
                  const rel = KPI_DEFINITIES[id];
                  return rel ? (
                    <span key={id} className="text-xs bg-muted border border-border rounded px-2 py-0.5 font-mono">
                      {rel.afkorting || rel.naam}
                    </span>
                  ) : null;
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ModelDocumentatie() {
  const [zoekterm, setZoekterm] = useState("");
  const [categorie, setCategorie] = useState<string>("alle");

  const gefilterd = useMemo(() => {
    const defs = Object.values(KPI_DEFINITIES);
    return defs.filter(def => {
      const matchCat = categorie === "alle" || def.categorie === categorie;
      const zoek = zoekterm.toLowerCase();
      const matchZoek = !zoekterm
        || def.naam.toLowerCase().includes(zoek)
        || (def.afkorting || "").toLowerCase().includes(zoek)
        || def.korteUitleg.toLowerCase().includes(zoek)
        || def.uitgebreideUitleg.toLowerCase().includes(zoek);
      return matchCat && matchZoek;
    });
  }, [zoekterm, categorie]);

  const perCategorie = useMemo(() => {
    const map: Record<string, KpiDefinition[]> = {};
    gefilterd.forEach(def => {
      if (!map[def.categorie]) map[def.categorie] = [];
      map[def.categorie].push(def);
    });
    return map;
  }, [gefilterd]);

  const aantalPerCat = useMemo(() => {
    const map: Record<string, number> = {};
    Object.values(KPI_DEFINITIES).forEach(def => {
      map[def.categorie] = (map[def.categorie] || 0) + 1;
    });
    return map;
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Modeldocumentatie</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Volledige uitleg van alle scores, KPI's, formules en businesslogica van het AI Pricing Decision Engine platform.
        </p>
      </div>

      {/* Intro banner */}
      <div className="bg-primary/5 border border-primary/20 rounded-lg p-4 flex gap-3">
        <Info className="w-5 h-5 text-primary shrink-0 mt-0.5" />
        <div>
          <div className="text-sm font-semibold text-primary mb-1">Hoe dit platform werkt</div>
          <p className="text-sm text-foreground/80 leading-relaxed">
            Het AI Pricing Decision Engine combineert directe marge-analyse met commerciële ecosysteemwaarde. 
            Elke pricingbeslissing houdt rekening met traffic-impact, basketwaarde, concurrentiedruk, 
            elasticiteit en herhalingsaankopen — niet alleen de directe marge per SKU. 
            Hieronder vind je uitleg van alle scores en metrics die het platform gebruikt.
          </p>
        </div>
      </div>

      {/* Statistieken */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Gedocumenteerde metrics", value: Object.keys(KPI_DEFINITIES).length },
          { label: "Categorieën", value: ALLE_CATEGORIEEN.length },
          { label: "Scores met formule", value: Object.values(KPI_DEFINITIES).filter(d => d.formule).length },
          { label: "Voorbeelden", value: Object.values(KPI_DEFINITIES).filter(d => d.voorbeeld).length },
        ].map((s, i) => (
          <div key={i} className="bg-card border rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-primary">{s.value}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Zoek + filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Zoek op naam, afkorting of uitleg…"
            value={zoekterm}
            onChange={e => setZoekterm(e.target.value)}
            className="pl-9"
          />
          {zoekterm && (
            <button onClick={() => setZoekterm("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setCategorie("alle")}
            className={`text-xs rounded-full px-3 py-1 border transition-colors ${categorie === "alle" ? "bg-primary text-primary-foreground border-primary" : "bg-card border-border hover:bg-muted"}`}
          >
            Alle ({Object.keys(KPI_DEFINITIES).length})
          </button>
          {ALLE_CATEGORIEEN.map(cat => (
            <button
              key={cat.id}
              onClick={() => setCategorie(cat.id === categorie ? "alle" : cat.id)}
              className={`text-xs rounded-full px-3 py-1 border transition-colors ${categorie === cat.id ? "bg-primary text-primary-foreground border-primary" : "bg-card border-border hover:bg-muted"}`}
            >
              {cat.label} ({aantalPerCat[cat.id] || 0})
            </button>
          ))}
        </div>
      </div>

      {/* Resultaten */}
      {gefilterd.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Search className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p>Geen metrics gevonden voor "{zoekterm}"</p>
        </div>
      ) : categorie === "alle" ? (
        // Gegroepeerd per categorie
        <div className="space-y-6">
          {ALLE_CATEGORIEEN.filter(cat => perCategorie[cat.id]?.length > 0).map(cat => (
            <div key={cat.id}>
              <div className="flex items-center gap-2 mb-3">
                <h2 className="text-base font-semibold">{cat.label}</h2>
                <Badge variant="outline" className={`text-[10px] ${CATEGORIE_KLEUREN[cat.id]}`}>
                  {perCategorie[cat.id]?.length || 0}
                </Badge>
              </div>
              <div className="space-y-2">
                {(perCategorie[cat.id] || []).map(def => (
                  <KpiKaart key={def.id} def={def} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        // Gefilterd op categorie
        <div className="space-y-2">
          {gefilterd.map(def => <KpiKaart key={def.id} def={def} />)}
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-border pt-4 text-xs text-muted-foreground text-center">
        AI Pricing Decision Engine — Documentatie v2.0 · {Object.keys(KPI_DEFINITIES).length} metrics gedocumenteerd · Klik op een metric voor volledige uitleg
      </div>
    </div>
  );
}
