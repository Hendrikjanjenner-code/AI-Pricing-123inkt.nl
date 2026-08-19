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
import { getAuthHeaders, useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Bot, Send, Plus, Trash2, Sparkles, AlertTriangle, Info,
  Database, Clock, Link2, Loader2, ShieldCheck, ThumbsUp, ThumbsDown,
  Brain, Pencil, Gauge,
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
  dbId?: number | null;
};

type BudgetMe = {
  date: string;
  calls_used: number;
  max_calls_per_day: number | null;
  calls_pct: number | null;
  tokens_used: number;
  tokens_reserved: number;
  max_tokens_per_day: number | null;
  tokens_pct: number | null;
};
function FeedbackButtons({ messageId }: { messageId: number }) {
  const [given, setGiven] = useState<1 | -1 | null>(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);

  const send = async (score: 1 | -1, withComment?: string) => {
    setSending(true);
    try {
      const res = await fetch(`${BASE}/api/copilot/messages/${messageId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ score, comment: withComment || undefined }),
      });
      if (res.ok) {
        setGiven(score);
        if (score === 1) setShowComment(false);
      }
    } catch {
      /* noop */
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="mt-2 border-t pt-2">
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-muted-foreground">Was dit antwoord nuttig?</span>
        <button
          type="button"
          aria-label="Duim omhoog"
          disabled={sending}
          className={`rounded p-1 hover:bg-muted ${given === 1 ? "text-green-600" : "text-muted-foreground"}`}
          onClick={() => void send(1)}
        >
          <ThumbsUp className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          aria-label="Duim omlaag"
          disabled={sending}
          className={`rounded p-1 hover:bg-muted ${given === -1 ? "text-red-600" : "text-muted-foreground"}`}
          onClick={() => {
            setShowComment(true);
            void send(-1, comment.trim() || undefined);
          }}
        >
          <ThumbsDown className="h-3.5 w-3.5" />
        </button>
        {given != null && (
          <span className="text-[11px] text-muted-foreground">Bedankt voor je feedback.</span>
        )}
      </div>
      {showComment && (
        <form
          className="mt-1.5 flex items-center gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            void send(-1, comment.trim() || undefined);
          }}
        >
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Optioneel: wat kon beter?"
            className="h-7 flex-1 rounded-md border bg-background px-2 text-xs"
            maxLength={2000}
          />
          <Button type="submit" size="sm" variant="outline" className="h-7 text-xs" disabled={sending}>
            Verstuur
          </Button>
        </form>
      )}
    </div>
  );
}

type MemoryItem = {
  id: number;
  key: string;
  value: string;
  scope: "persoonlijk" | "organisatie";
  editable: boolean;
  updated_at?: string | null;
};

function MemorySection() {
  const { user } = useAuth();
  const canManageOrg = user?.role === "admin" || user?.role === "pricing_manager";
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newScope, setNewScope] = useState<"persoonlijk" | "organisatie">("persoonlijk");
  const [adding, setAdding] = useState(false);

  const addItem = async () => {
    const key = newKey.trim();
    const value = newValue.trim();
    if (!key || !value) return;
    setAdding(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}/api/copilot/memory`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ key, value, scope: newScope }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const created = (await res.json()) as MemoryItem;
      setItems((prev) => {
        const rest = (prev || []).filter((i) => i.id !== created.id);
        return [created, ...rest];
      });
      setNewKey("");
      setNewValue("");
      setNewScope("persoonlijk");
      setShowAdd(false);
    } catch {
      setError("Toevoegen mislukt.");
    } finally {
      setAdding(false);
    }
  };

  const load = async () => {
    setError(null);
    try {
      const res = await fetch(`${BASE}/api/copilot/memory`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setItems((await res.json()) as MemoryItem[]);
    } catch {
      setError("Geheugen kon niet worden geladen.");
    }
  };

  useEffect(() => {
    if (open && items == null) void load();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const remove = async (id: number) => {
    setBusyId(id);
    try {
      const res = await fetch(`${BASE}/api/copilot/memory/${id}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setItems((prev) => (prev || []).filter((i) => i.id !== id));
    } catch {
      setError("Verwijderen mislukt.");
    } finally {
      setBusyId(null);
    }
  };

  const saveEdit = async (id: number) => {
    const value = editValue.trim();
    if (!value) return;
    setBusyId(id);
    try {
      const res = await fetch(`${BASE}/api/copilot/memory/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ value }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated = (await res.json()) as MemoryItem;
      setItems((prev) =>
        (prev || []).map((i) => (i.id === id ? { ...i, value: updated.value } : i)),
      );
      setEditingId(null);
    } catch {
      setError("Opslaan mislukt.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="rounded-md border bg-muted/30 p-2 text-[11px] leading-snug">
      <button
        type="button"
        className="flex w-full items-center gap-1 font-medium text-foreground"
        onClick={() => setOpen((o) => !o)}
      >
        <Brain className="h-3 w-3" /> Wat de Copilot over je onthoudt
        <span className="ml-auto text-muted-foreground">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {error && <p className="text-destructive">{error}</p>}
          {!showAdd ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-6 px-2 text-[10px]"
              onClick={() => setShowAdd(true)}
            >
              <Plus className="mr-1 h-3 w-3" /> Voeg toe
            </Button>
          ) : (
            <form
              className="space-y-1 rounded border bg-background p-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                void addItem();
              }}
            >
              <input
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="Naam (bv. favoriete_categorie)"
                className="h-6 w-full rounded border bg-background px-1.5 text-[11px]"
                maxLength={200}
                autoFocus
              />
              <input
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="Waarde (bv. Dranken)"
                className="h-6 w-full rounded border bg-background px-1.5 text-[11px]"
                maxLength={2000}
              />
              {canManageOrg && (
                <select
                  value={newScope}
                  onChange={(e) =>
                    setNewScope(e.target.value as "persoonlijk" | "organisatie")
                  }
                  className="h-6 w-full rounded border bg-background px-1 text-[11px]"
                  aria-label="Scope van geheugen-item"
                >
                  <option value="persoonlijk">Persoonlijk</option>
                  <option value="organisatie">Organisatie-breed</option>
                </select>
              )}
              <div className="flex items-center gap-1">
                <Button
                  type="submit"
                  size="sm"
                  variant="outline"
                  className="h-6 px-2 text-[10px]"
                  disabled={adding || !newKey.trim() || !newValue.trim()}
                >
                  Opslaan
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-6 px-2 text-[10px]"
                  onClick={() => setShowAdd(false)}
                >
                  Annuleren
                </Button>
              </div>
            </form>
          )}
          {items == null && !error && <Skeleton className="h-10 w-full" />}
          {items != null && items.length === 0 && (
            <p className="text-muted-foreground">
              Nog niets onthouden. De Copilot leert duurzame voorkeuren uit je gesprekken.
            </p>
          )}
          {(items || []).map((m) => (
            <div key={m.id} className="rounded border bg-background p-1.5">
              <div className="flex items-start gap-1.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1">
                    <span className="truncate font-medium">{m.key}</span>
                    {m.scope === "organisatie" && (
                      <Badge variant="outline" className="h-4 px-1 text-[9px]">
                        organisatie
                      </Badge>
                    )}
                  </div>
                  {editingId === m.id ? (
                    <form
                      className="mt-1 flex items-center gap-1"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void saveEdit(m.id);
                      }}
                    >
                      <input
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        className="h-6 flex-1 rounded border bg-background px-1.5 text-[11px]"
                        maxLength={2000}
                        autoFocus
                      />
                      <Button
                        type="submit"
                        size="sm"
                        variant="outline"
                        className="h-6 px-2 text-[10px]"
                        disabled={busyId === m.id || !editValue.trim()}
                      >
                        Opslaan
                      </Button>
                    </form>
                  ) : (
                    <p className="mt-0.5 break-words text-muted-foreground">{m.value}</p>
                  )}
                </div>
                {m.editable && editingId !== m.id && (
                  <div className="flex shrink-0 items-center gap-0.5">
                    <button
                      type="button"
                      aria-label="Bewerk geheugen-item"
                      className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                      onClick={() => {
                        setEditingId(m.id);
                        setEditValue(m.value);
                      }}
                    >
                      <Pencil className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      aria-label="Verwijder geheugen-item"
                      className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-destructive"
                      disabled={busyId === m.id}
                      onClick={() => void remove(m.id)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

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
  const [budgetRefresh, setBudgetRefresh] = useState(0);
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
          dbId: typeof m.id === "number" ? m.id : Number(m.id) || null,
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
          } else if (evt.type === "done" && evt.message_id) {
            // Koppel het DB-id aan het laatste assistant-bericht (voor feedback)
            setMessages((prev) => {
              const next = [...prev];
              for (let i = next.length - 1; i >= 0; i--) {
                if (next[i].role === "assistant") {
                  next[i] = { ...next[i], dbId: evt.message_id as number };
                  break;
                }
              }
              return next;
            });
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
      setBudgetRefresh((n) => n + 1);
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
        <MemorySection />
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
          <BudgetIndicator refreshKey={budgetRefresh} />
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
                      {m.dbId != null && <FeedbackButtons key={m.dbId} messageId={m.dbId} />}
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

function BudgetIndicator({ refreshKey }: { refreshKey: number }) {
  const [budget, setBudget] = useState<BudgetMe | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${BASE}/api/copilot/budget/me`, {
          headers: getAuthHeaders(),
        });
        if (!res.ok) return;
        const data: BudgetMe = await res.json();
        if (!cancelled) setBudget(data);
      } catch {
        /* indicator is informatief; stil falen */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  // Toon de indicator zodra er minstens één limiet actief is.
  if (!budget || (budget.max_calls_per_day == null && budget.max_tokens_per_day == null)) {
    return null;
  }

  const fmt = (n: number) =>
    n >= 10_000 ? `${Math.round(n / 1000).toLocaleString("nl-NL")}k` : n.toLocaleString("nl-NL");

  const parts: string[] = [];
  if (budget.max_calls_per_day != null) {
    parts.push(`${budget.calls_used} van ${budget.max_calls_per_day} vragen`);
  }
  if (budget.max_tokens_per_day != null) {
    parts.push(`${fmt(budget.tokens_reserved)} van ${fmt(budget.max_tokens_per_day)} tokens`);
  }

  // Voortgang en status volgen de meest restrictieve teller: blokkering
  // gebeurt server-side op zowel calls als (gereserveerde) tokens.
  const pct = Math.max(budget.calls_pct ?? 0, budget.tokens_pct ?? 0);
  const atLimit =
    (budget.max_calls_per_day != null && budget.calls_used >= budget.max_calls_per_day) ||
    (budget.max_tokens_per_day != null && budget.tokens_reserved >= budget.max_tokens_per_day);
  const nearLimit = pct >= 80;

  return (
    <div
      className={`flex items-center gap-2 text-xs ${
        atLimit ? "text-destructive" : nearLimit ? "text-amber-600" : "text-muted-foreground"
      }`}
      title={`AI-dagbudget vandaag gebruikt: ${parts.join(" · ")}`}
      data-testid="budget-indicator"
    >
      <Gauge className="h-3.5 w-3.5 shrink-0" />
      <span>{parts.join(" · ")} vandaag gebruikt</span>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full ${
            atLimit ? "bg-destructive" : nearLimit ? "bg-amber-500" : "bg-primary"
          }`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
}
