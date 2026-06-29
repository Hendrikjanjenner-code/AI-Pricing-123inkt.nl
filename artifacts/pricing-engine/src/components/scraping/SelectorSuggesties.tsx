import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown, Info, Zap, Shield, Code } from "lucide-react";

interface Kandidaat {
  selector: string;
  sample_text: string;
  score: number;
}

interface AnalyseResultaat {
  prijs_kandidaten: Kandidaat[];
  titel_kandidaten: Kandidaat[];
  voorraad_kandidaten: Kandidaat[];
  js_rendering_waarschijnlijk: boolean;
  geblokkeerd: boolean;
  blok_reden?: string | null;
  aanbevolen_actie: string;
  html_preview?: string | null;
}

interface Props {
  resultaat: AnalyseResultaat;
  isAdmin?: boolean;
}

function confidence(score: number): { label: string; cls: string } {
  if (score >= 80) return { label: `${score}%`, cls: "bg-green-100 text-green-800 border-green-200" };
  if (score >= 50) return { label: `${score}%`, cls: "bg-amber-100 text-amber-800 border-amber-200" };
  return { label: `${score}%`, cls: "bg-red-100 text-red-800 border-red-200" };
}

function KandidaatLijst({ titel, kandidaten }: { titel: string; kandidaten: Kandidaat[] }) {
  if (!kandidaten.length) {
    return (
      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">{titel}</p>
        <p className="text-xs text-muted-foreground italic">Geen kandidaten gevonden</p>
      </div>
    );
  }
  return (
    <div>
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">{titel}</p>
      <ol className="space-y-1.5">
        {kandidaten.map((k, i) => {
          const conf = confidence(k.score);
          return (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="shrink-0 text-muted-foreground text-xs mt-0.5 w-4">{i + 1}.</span>
              <div className="flex-1 min-w-0">
                <code className="block font-mono text-xs bg-muted rounded px-1.5 py-0.5 truncate" title={k.selector}>
                  {k.selector}
                </code>
                {k.sample_text && (
                  <span className="text-xs text-muted-foreground truncate block max-w-xs" title={k.sample_text}>
                    &ldquo;{k.sample_text}&rdquo;
                  </span>
                )}
              </div>
              <span className={`shrink-0 inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${conf.cls}`}>
                {conf.label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function SelectorSuggesties({ resultaat, isAdmin = false }: Props) {
  const [htmlOpen, setHtmlOpen] = useState(false);

  return (
    <div className="space-y-4 border border-blue-200 rounded-lg bg-blue-50/40 p-4">
      <div className="flex items-center gap-2">
        <Zap className="w-4 h-4 text-blue-600 shrink-0" />
        <p className="text-sm font-semibold text-blue-900">Selector-suggesties</p>
        {resultaat.js_rendering_waarschijnlijk && (
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            <Zap className="w-3 h-3" />
            JS-rendering
          </span>
        )}
        {resultaat.geblokkeerd && (
          <span className="inline-flex items-center gap-1 rounded-full border border-red-300 bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
            <Shield className="w-3 h-3" />
            Geblokkeerd
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KandidaatLijst titel="Prijs" kandidaten={resultaat.prijs_kandidaten} />
        <KandidaatLijst titel="Titel" kandidaten={resultaat.titel_kandidaten} />
        <KandidaatLijst titel="Voorraad" kandidaten={resultaat.voorraad_kandidaten} />
      </div>

      <Alert className="border-blue-200 bg-blue-50">
        <Info className="h-4 w-4 text-blue-600" />
        <AlertDescription className="text-blue-900 text-sm">
          <span className="font-medium">Aanbevolen actie: </span>
          {resultaat.aanbevolen_actie}
        </AlertDescription>
      </Alert>

      {isAdmin && resultaat.html_preview && (
        <Collapsible open={htmlOpen} onOpenChange={setHtmlOpen}>
          <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <Code className="w-3.5 h-3.5" />
            HTML-preview (eerste 20 KB)
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${htmlOpen ? "rotate-180" : ""}`} />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-3 text-xs font-mono whitespace-pre-wrap break-all">
              {resultaat.html_preview}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
