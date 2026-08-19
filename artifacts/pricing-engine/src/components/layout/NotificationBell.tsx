import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { Bell, CheckCheck } from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

interface Melding {
  id: number;
  type: string;
  kind: string | null;
  title: string;
  message: string | null;
  severity: string;
  link: string | null;
  reference: string | null;
  is_read: boolean;
  created_at: string | null;
}

interface MeldingenResponse {
  notifications: Melding[];
  unread_count: number;
}

const SEVERITY_DOT: Record<string, string> = {
  error: "bg-destructive",
  warning: "bg-amber-500",
  info: "bg-blue-500",
};

function formatTijd(ts: string | null): string {
  if (!ts) return "";
  const d = new Date(ts.replace(" ", "T") + (ts.endsWith("Z") ? "" : "Z"));
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString("nl-NL", {
    day: "2-digit", month: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

export function NotificationBell() {
  const [meldingen, setMeldingen] = useState<Melding[]>([]);
  const [unread, setUnread] = useState(0);
  const [, navigate] = useLocation();

  const load = async () => {
    if (document.hidden) return;
    try {
      const resp = await fetch(`${BASE}/api/notifications?limit=30`, {
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error("fetch failed");
      const data: MeldingenResponse = await resp.json();
      setMeldingen(data.notifications);
      setUnread(data.unread_count);
    } catch {
      // Laat de laatst bekende status staan bij een tijdelijke fout.
    }
  };

  useEffect(() => {
    load();
    const intervalId = setInterval(load, 60000);
    const onVisibilityChange = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const markRead = async (id: number) => {
    try {
      await fetch(`${BASE}/api/notifications/${id}/read`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
    } catch { /* stil — volgende poll corrigeert */ }
    setMeldingen(prev => prev.map(m => (m.id === id ? { ...m, is_read: true } : m)));
    setUnread(prev => Math.max(0, prev - 1));
  };

  const markAllRead = async () => {
    try {
      await fetch(`${BASE}/api/notifications/read-all`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
    } catch { /* stil */ }
    setMeldingen(prev => prev.map(m => ({ ...m, is_read: true })));
    setUnread(0);
  };

  const openMelding = (m: Melding) => {
    if (!m.is_read) markRead(m.id);
    if (m.link) navigate(m.link);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative h-9 w-9" data-testid="button-notifications">
          <Bell className="w-4 h-4" />
          {unread > 0 && (
            <span
              data-testid="badge-unread-count"
              className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-destructive text-destructive-foreground text-[10px] font-bold flex items-center justify-center"
            >
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-96 p-0">
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <span className="font-semibold text-sm">Meldingen</span>
          {unread > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1"
              onClick={markAllRead}
              data-testid="button-mark-all-read"
            >
              <CheckCheck className="w-3.5 h-3.5" />
              Alles gelezen
            </Button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {meldingen.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              Geen meldingen
            </div>
          ) : (
            meldingen.map(m => (
              <button
                key={m.id}
                onClick={() => openMelding(m)}
                data-testid={`notification-item-${m.id}`}
                className={`w-full text-left px-4 py-3 border-b last:border-b-0 hover:bg-accent/50 transition-colors ${
                  m.is_read ? "opacity-60" : ""
                }`}
              >
                <div className="flex items-start gap-2">
                  <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${SEVERITY_DOT[m.severity] || "bg-muted-foreground"}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm truncate ${m.is_read ? "" : "font-semibold"}`}>
                        {m.title}
                      </span>
                      {!m.is_read && <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />}
                    </div>
                    {m.message && (
                      <div className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                        {m.message}
                      </div>
                    )}
                    <div className="text-[11px] text-muted-foreground/70 mt-1">
                      {formatTijd(m.created_at)}
                    </div>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
