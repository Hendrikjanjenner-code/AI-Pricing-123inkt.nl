import { useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import { useQueryClient } from "@tanstack/react-query";
import {
  useGetCopilotStatus,
  useListCopilotConversations,
  useCreateCopilotConversation,
  useDeleteCopilotConversation,
  useGetCopilotConversation,
  getGetCopilotConversationQueryKey,
  getListCopilotConversationsQueryKey,
} from "@workspace/api-client-react";
import { getAuthHeaders } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Bot, Send, Plus, Trash2, Sparkles, AlertTriangle, Info,
  Database, Clock, Link2, Loader2, ShieldCheck,
} from "lucide-react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

type CopilotAnswer = {
  conclusion?: string | null;
  period?: string | null;
  sources?: { function: string; data_source?: string | null; records?: number | null }[];
  data_freshness?: Record<string, string | null> | null;
  records?: number | null;
  confidence?: number | null;
  limitations?: string[];
  warnings?: string[];
  suggested_action?: string | null;
  links?: { label: string; path: string }[];
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer?: CopilotAnswer | null;
};

function ConfidenceBadge({ value }: { value: number | null | undefined }) {
  const v = typeof value === "number" ? value : 0;
  const pct = Math.round(v * 100);
  const cls =
    v >= 0.7
      ? "bg-green-100 text-green-800"
      : v >= 0.4
        ? "bg-amber-100 text-amber-800"
        : "bg-red-100 text-red-800";
  return <Badge className={cls}>Confidence {pct}%</Badge>;
}

function AnswerCard({ answer }: { answer: CopilotAnswer }) {
  const freshness = answer.data_freshness || {};
  const freshItems = Object.entries(freshness).filter(([, v]) => v);
  return (
    <div className="space-y-3">
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{answer.conclusion}</p>

      <div className="flex flex-wrap gap-2 text-xs">
        <ConfidenceBadge value={answer.confidence} />
        {answer.period && (
          <Badge variant="outline" className="gap-1">
            <Clock className="h-3 w-3" /> {answer.period}
          </Badge>
        )}
        <Badge variant="outline" className="gap-1">
          <Database className="h-3 w-3" /> {answer.records ?? 0} records
        </Badge>
      </div>

      {(answer.sources?.length ?? 0) > 0 && (
        <div className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Bronnen: </span>
          {answer.sources!.map((s, i) => (
            <span key={i}>
              {i > 0 && ", "}
              {s.function}
              {s.data_source ? ` (${s.data_source}${s.records != null ? `, ${s.records} rec` : ""})` : ""}
            </span>
          ))}
        </div>
      )}

      {freshItems.length > 0 && (
        <div className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Dataversheid: </span>
          {freshItems.map(([k, v], i) => (
            <span key={k}>
              {i > 0 && " · "}
              {k}: {String(v).slice(0, 10)}
            </span>
          ))}
        </div>
      )}

      {(answer.warnings?.length ?? 0) > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
          {answer.warnings!.map((w, i) => (
            <div key={i} className="flex gap-1.5">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {w}
            </div>
          ))}
        </div>
      )}

      {(answer.limitations?.length ?? 0) > 0 && (
        <div className="text-xs text-muted-foreground">
          {answer.limitations!.map((l, i) => (
            <div key={i} className="flex gap-1.5">
              <Info className="mt-0.5 h-3 w-3 shrink-0" /> {l}
            </div>
          ))}
        </div>
      )}

      {answer.suggested_action && (
        <div className="rounded-md border bg-muted/50 p-2 text-xs">
          <span className="font-medium">Voorgestelde actie: </span>
          {answer.suggested_action}
        </div>
      )}

      {(answer.links?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-2">
          {answer.links!.map((l, i) => (
            <Link key={i} href={l.path}>
              <Button variant="outline" size="sm" className="h-7 gap-1 text-xs">
                <Link2 className="h-3 w-3" /> {l.label}
              </Button>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function CopilotPage() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: status } = useGetCopilotStatus();
  const { data: conversations, isLoading: convsLoading } = useListCopilotConversations();
  const createConv = useCreateCopilotConversation();
  const deleteConv = useDeleteCopilotConversation();
  const { data: activeConv } = useGetCopilotConversation(activeId ?? 0, {
    query: {
      enabled: activeId != null,
      queryKey: getGetCopilotConversationQueryKey(activeId ?? 0),
    },
  });

  useEffect(() => {
    if (activeConv && activeConv.id === activeId) {
      setMessages(
        (activeConv.messages || []).map((m) => ({
          id: String(m.id),
          role: m.role as "user" | "assistant",
          content: m.content,
          answer: (m.answer as CopilotAnswer | null) ?? null,
        })),
      );
    }
  }, [activeConv, activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusLine]);

  const refreshConversations = () =>
    queryClient.invalidateQueries({ queryKey: getListCopilotConversationsQueryKey() });

  const newConversation = async (): Promise<number | null> => {
    try {
      const conv = await createConv.mutateAsync({ data: {} });
      await refreshConversations();
      setActiveId(conv.id);
      setMessages([]);
      return conv.id;
    } catch {
      return null;
    }
  };

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    let convId = activeId;
    if (convId == null) {
      convId = await newConversation();
      if (convId == null) return;
    }
    setBusy(true);
    setInput("");
    setStatusLine("Bezig…");
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: q }]);

    try {
      // Eigen AbortSignal: LLM-antwoorden duren langer dan de globale 15s-timeout.
      const res = await fetch(`${BASE}/api/copilot/conversations/${convId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ content: q }),
        signal: AbortSignal.timeout(180_000),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          let evt: any;
          try {
            evt = JSON.parse(line.slice(5));
          } catch {
            continue;
          }
          if (evt.type === "status") setStatusLine(evt.message);
          else if (evt.type === "tool")
            setStatusLine(`Data opgehaald: ${evt.name}${evt.records != null ? ` (${evt.records} records)` : ""}`);
          else if (evt.type === "answer") {
            const a: CopilotAnswer = evt.answer || {};
            setMessages((prev) => [
              ...prev,
              { id: `a-${Date.now()}`, role: "assistant", content: a.conclusion || "", answer: a },
            ]);
          }
        }
      }
      refreshConversations();
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content:
            "Het antwoord kon niet worden opgehaald (netwerk- of AI-storing). De rest van de applicatie blijft gewoon werken — probeer het zo opnieuw.",
          answer: null,
        },
      ]);
    } finally {
      setBusy(false);
      setStatusLine(null);
    }
  };

  const removeConversation = async (id: number) => {
    try {
      await deleteConv.mutateAsync({ id });
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
      }
      refreshConversations();
    } catch {
      /* noop */
    }
  };

  return (
    <div className="flex h-[calc(100vh-6rem)] gap-4">
      {/* Gespreksgeschiedenis */}
      <div className="hidden w-64 shrink-0 flex-col gap-2 md:flex">
        <Button onClick={() => void newConversation()} className="gap-2" size="sm">
          <Plus className="h-4 w-4" /> Nieuw gesprek
        </Button>
        <div className="flex-1 space-y-1 overflow-y-auto">
          {convsLoading && <Skeleton className="h-24 w-full" />}
          {(conversations || []).map((c) => (
            <div
              key={c.id}
              className={`group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted ${
                activeId === c.id ? "bg-muted font-medium" : ""
              }`}
              onClick={() => setActiveId(c.id)}
            >
              <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">{c.title}</span>
              <button
                className="hidden text-muted-foreground hover:text-destructive group-hover:block"
                onClick={(e) => {
                  e.stopPropagation();
                  void removeConversation(c.id);
                }}
                aria-label="Verwijder gesprek"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
          {!convsLoading && (conversations || []).length === 0 && (
            <p className="px-2 py-4 text-xs text-muted-foreground">Nog geen gesprekken.</p>
          )}
        </div>
        <div className="rounded-md border bg-muted/30 p-2 text-[11px] leading-snug text-muted-foreground">
          <div className="mb-1 flex items-center gap-1 font-medium text-foreground">
            <ShieldCheck className="h-3 w-3" /> AI Gateway
          </div>
          Antwoorden komen uitsluitend uit goedgekeurde semantic-layer-functies — geen vrije SQL,
          geen persoonsgegevens richting het model. Elke call wordt gelogd.
        </div>
      </div>

      {/* Chat */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold">
              <Sparkles className="h-5 w-5 text-primary" /> Commercial AI Copilot
            </h1>
            <p className="text-sm text-muted-foreground">
              Stel vragen over pricing, marge, concurrentie, promoties en kansen.
            </p>
          </div>
          {status && (
            <Badge variant={status.ai_available ? "default" : "destructive"}>
              {status.ai_available ? `AI actief (${status.model})` : "AI niet beschikbaar"}
            </Badge>
          )}
        </div>

        {status && !status.ai_available && (
          <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            De AI-dienst is momenteel niet geconfigureerd of niet bereikbaar. De applicatie werkt
            gewoon door; zodra de AI-integratie actief is, beantwoordt de Copilot hier vragen.
          </div>
        )}

        <Card className="flex min-h-0 flex-1 flex-col">
          <CardContent className="flex min-h-0 flex-1 flex-col p-4">
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
              {messages.length === 0 && (
                <div className="space-y-3 py-6">
                  <p className="text-sm text-muted-foreground">Voorbeeldvragen:</p>
                  <div className="flex flex-wrap gap-2">
                    {(status?.example_questions || []).map((q, i) => (
                      <Button
                        key={i}
                        variant="outline"
                        size="sm"
                        className="h-auto whitespace-normal py-1.5 text-left text-xs"
                        onClick={() => void ask(q)}
                        disabled={busy}
                      >
                        {q}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex justify-start">
                    <div className="max-w-[90%] rounded-lg border bg-card px-3 py-2.5">
                      {m.answer ? (
                        <AnswerCard answer={m.answer} />
                      ) : (
                        <p className="text-sm">{m.content}</p>
                      )}
                    </div>
                  </div>
                ),
              )}
              {busy && statusLine && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> {statusLine}
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <form
              className="mt-3 flex items-end gap-2 border-t pt-3"
              onSubmit={(e) => {
                e.preventDefault();
                void ask(input);
              }}
            >
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void ask(input);
                  }
                }}
                placeholder="Stel een vraag, bv. 'Waar verliezen we marge?'"
                className="min-h-[44px] flex-1 resize-none"
                rows={1}
                disabled={busy}
              />
              <Button type="submit" disabled={busy || !input.trim()} className="gap-1.5">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Vraag
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
