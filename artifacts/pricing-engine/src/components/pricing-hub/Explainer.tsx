import { SOURCE_INFO } from "@/lib/cost-priority/model";

export function Explainer({ sources }: { sources: string[] }) {
  return (
    <details className="rounded-lg border bg-card p-4 text-sm" data-testid="section-explainer">
      <summary className="cursor-pointer font-semibold">Uitleg Excel-velden, categorieën en nulwaarden</summary>
      <dl className="mt-3 space-y-2">
        {sources.map(s => (
          <div key={s}>
            <dt className="font-medium">{s}</dt>
            <dd className="text-muted-foreground">{SOURCE_INFO[s]?.uitleg ?? "Optionele vijfde bron; waarde komt uit handmatige invoer of een werkboekkolom met exact deze naam."}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-muted-foreground"><b>Categorieën:</b> Print (hoofdletterongevoelig, zoals in Excel) gebruikt standaard Stockprice → ABCLev → AB → 123inkt.nl Marktprijs. Alle andere categorieën: Stockprice → AB → ABCLev → 123inkt.nl Marktprijs. Een categorie-override geldt alleen bij exact dezelfde naam.</p>
      <p className="mt-2 text-muted-foreground" data-testid="text-zero-semantics">
        <b>Nulwaarden:</b> een waarde van exact 0 op een niet-laatste prioriteit wordt overgeslagen. Staat de laatste prioriteit op 0, dan wordt die 0 gekozen met een waarschuwing (exact de Excel-terugval). Voorraadaantal speelt geen rol.
      </p>
      <p className="mt-2 text-muted-foreground"><b>Ontbrekend is niet nul:</b> een leeg of ongeldig veld is een invoerfout en blokkeert activeren, ook als die bron niet bereikt wordt. Vul expliciet 0 in als een bron niet beschikbaar is. Negatieve bedragen worden geweigerd.</p>
      <p className="mt-2 text-muted-foreground"><b>Werkboek (.xlsx):</b> kopteksten op rij 2: Productcode, Category en de bronlabels hierboven (inclusief een eventuele vijfde bron). Formules in invoervelden worden geweigerd. Maximaal 2 MB en 500 regels. Voorraadaantal wordt genegeerd.</p>
    </details>
  );
}
