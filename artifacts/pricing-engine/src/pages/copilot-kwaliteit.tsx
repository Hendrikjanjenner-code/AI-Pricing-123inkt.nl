import { useEffect, useState } from "react";
import { getAuthHeaders } from "@/lib/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ThumbsUp, ThumbsDown, Sparkles, AlertTriangle, MessageSquareText } from "lucide-react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

type Agg = { positive: number; negative: number; total: number; score_pct: number | null };
type Quality = {
  period_weeks: number;
  overall: Agg;
  weekly: ({ week: string } & Agg)[];
  per_prompt_version: ({ prompt_version_id: number | null; version: number | null; title: string | null } & Agg)[];
  per_tool: ({ tool: string } & Agg)[];
  low_scoring: {
    feedback_id: number;
    message_id: number;
    conversation_id: number | null;
    username: string | null;
    question: string | null;
    answer_excerpt: string | null;
    comment: string | null;
    tools_used: string[] | null;
    prompt_version_id: number | null;
    created_at: string | null;
  }[];
  open_improvement_suggestions: number;
};
type Faq = { questions: { question: string; count: number; last_asked: string | null }[] };

function ScoreBadge({ agg }: { agg: Agg }) {
  if (!agg.total) return <Badge variant="outline">geen feedback</Badge>;
  const pct = agg.score_pct ?? 0;
  const cls =
    pct >= 70 ? "bg-green-100 text-green-800" : pct >= 40 ? "bg-amber-100 text-amber-800" : "bg-red-100 text-red-800";
  return <Badge className={cls}>{pct}% positief</Badge>;
}

export default function CopilotKwaliteitPage() {
  const [data, setData] = useState<Quality | null>(null);
  const [faq, setFaq] = useState<Faq | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [qRes, fRes] = await Promise.all([
          fetch(`${BASE}/api/copilot/quality`, { headers: getAuthHeaders() }),
          fetch(`${BASE}/api/copilot/faq`, { headers: getAuthHeaders() }),
        ]);
        if (!qRes.ok) throw new Error(`HTTP ${qRes.status}`);
        setData(await qRes.json());
        if (fRes.ok) setFaq(await fRes.json());
      } catch (e) {
        setError("Kwaliteitsdata kon niet worden geladen (analist of hoger vereist).");
      }
    };
    void load();
  }, []);

  if (error) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{error}</div>
    );
  }
  if (!data) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Sparkles className="h-5 w-5 text-primary" /> Copilot-kwaliteit
        </h1>
        <p className="text-sm text-muted-foreground">
          Feedbackscore per week, promptversie en tool (laatste {data.period_weeks} weken) — de leerloop van de Copilot.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Totaal beoordeeld</p>
            <p className="text-2xl font-semibold">{data.overall.total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <ThumbsUp className="h-3 w-3" /> Positief
            </p>
            <p className="text-2xl font-semibold text-green-600">{data.overall.positive}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <ThumbsDown className="h-3 w-3" /> Negatief
            </p>
            <p className="text-2xl font-semibold text-red-600">{data.overall.negative}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Open verbetersuggesties</p>
            <p className="text-2xl font-semibold">{data.open_improvement_suggestions}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Per week</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            {data.weekly.length === 0 && <p className="text-xs text-muted-foreground">Nog geen feedback.</p>}
            {data.weekly.map((w) => (
              <div key={w.week} className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs">{w.week}</span>
                <span className="text-xs text-muted-foreground">
                  {w.positive}↑ / {w.negative}↓
                </span>
                <ScoreBadge agg={w} />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Per promptversie (vergelijking)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            {data.per_prompt_version.length === 0 && (
              <p className="text-xs text-muted-foreground">Nog geen feedback.</p>
            )}
            {data.per_prompt_version.map((v, i) => (
              <div key={i} className="flex items-center justify-between gap-2">
                <span className="text-xs">
                  {v.version != null ? `v${v.version}` : "onbekende versie"}
                  {v.title ? ` — ${v.title}` : ""}
                </span>
                <span className="text-xs text-muted-foreground">
                  {v.positive}↑ / {v.negative}↓
                </span>
                <ScoreBadge agg={v} />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Per tool</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            {data.per_tool.length === 0 && <p className="text-xs text-muted-foreground">Nog geen feedback.</p>}
            {data.per_tool.map((t) => (
              <div key={t.tool} className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs">{t.tool}</span>
                <span className="text-xs text-muted-foreground">
                  {t.positive}↑ / {t.negative}↓
                </span>
                <ScoreBadge agg={t} />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-1.5 text-sm">
              <MessageSquareText className="h-4 w-4" /> Vaker gesteld
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            {(faq?.questions || []).length === 0 && (
              <p className="text-xs text-muted-foreground">Nog geen vragen.</p>
            )}
            {(faq?.questions || []).map((q, i) => (
              <div key={i} className="flex items-center justify-between gap-2">
                <span className="truncate text-xs">{q.question}</span>
                <Badge variant="outline">{q.count}×</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-1.5 text-sm">
            <AlertTriangle className="h-4 w-4 text-amber-600" /> Laag-scorende antwoorden
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.low_scoring.length === 0 && (
            <p className="text-xs text-muted-foreground">Geen negatief beoordeelde antwoorden. 🎉</p>
          )}
          {data.low_scoring.map((r) => (
            <div key={r.feedback_id} className="rounded-md border p-3 text-xs">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-muted-foreground">
                <span>{r.created_at ? r.created_at.slice(0, 16).replace("T", " ") : ""}</span>
                <span>· {r.username || "onbekend"}</span>
                {r.prompt_version_id != null && <span>· promptversie #{r.prompt_version_id}</span>}
                {(r.tools_used || []).map((t) => (
                  <Badge key={t} variant="outline" className="font-mono text-[10px]">
                    {t}
                  </Badge>
                ))}
              </div>
              <p className="font-medium">Vraag: {r.question || "-"}</p>
              <p className="mt-1 text-muted-foreground">Antwoord: {r.answer_excerpt || "-"}</p>
              {r.comment && <p className="mt-1 text-amber-800">Toelichting: {r.comment}</p>}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
