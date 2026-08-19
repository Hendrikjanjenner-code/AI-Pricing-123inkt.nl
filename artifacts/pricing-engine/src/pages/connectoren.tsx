import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
  AlertCircle, CheckCircle2, ChevronDown, ChevronUp, Eye, EyeOff,
  Loader2, RefreshCw, Server, Unlink, Zap,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/auth";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

type ConnStatus = "ok" | "not_configured" | "unreachable" | "auth_error" | "error";

interface FieldOption {
  value: string;
  label: string;
}

interface FieldDef {
  key: string;
  label: string;
  required: boolean;
  secret: boolean;
  placeholder: string;
  type?: "select" | "text";
  options?: FieldOption[];
  default?: string;
  mode?: string;
}

interface FeedOutage {
  unreached_hours: number | null;
  unreached_text: string;
  severity: "error" | "warning";
  failed_at: string | null;
  last_success_at: string | null;
  error_message: string;
}
interface ConnectorSummary {
  name: string;
  feed_outage?: FeedOutage | null;
  label: string;
  configured: boolean;
  source: "db" | "env" | "default" | null;
  default_feed_url?: string | null;
  fields: FieldDef[];
  fields_filled: string[];
  masked_values: Record<string, string>;
  last_test_status: ConnStatus | null;
  last_test_message: string | null;
  last_tested_at: string | null;
  last_synced_at: string | null;
  configured_by: string | null;
  live_status?: ConnStatus;
  live_message?: string;
}

const STATUS_LABEL: Record<ConnStatus, string> = {
  ok: "Verbonden",
  not_configured: "Niet geconfigureerd",
  unreachable: "Niet bereikbaar",
  auth_error: "Authenticatiefout",
  error: "Fout",
};

const STATUS_COLOR: Record<ConnStatus, string> = {
  ok: "bg-emerald-500",
  not_configured: "bg-gray-400",
  unreachable: "bg-red-500",
  auth_error: "bg-amber-500",
  error: "bg-red-500",
};

const STATUS_BADGE: Record<ConnStatus, string> = {
  ok: "bg-emerald-50 text-emerald-700 border-emerald-200",
  not_configured: "bg-gray-100 text-gray-600 border-gray-200",
  unreachable: "bg-red-50 text-red-600 border-red-200",
  auth_error: "bg-amber-50 text-amber-700 border-amber-200",
  error: "bg-red-50 text-red-600 border-red-200",
};

function formatDate(iso: string | null | undefined) {
  if (!iso) return "Nooit";
  try {
    return new Date(iso).toLocaleString("nl-NL", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function StatusDot({ status }: { status: ConnStatus | null | undefined }) {
  if (!status) return <div className="w-2 h-2 rounded-full bg-gray-300" />;
  return <div className={`w-2 h-2 rounded-full ${STATUS_COLOR[status] ?? "bg-gray-400"}`} />;
}

interface ImportSettings {
  components: Record<string, boolean>;
  component_labels: Record<string, string>;
  max_delivery_days: number | null;
  disabled_competitors: string[];
  competitors: { name: string; enabled: boolean }[];
  updated_by: string | null;
  updated_at: string | null;
}

function ImportSettingsPanel() {
  const [settings, setSettings] = useState<ImportSettings | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${BASE}/api/uploads/priceshape/import-settings`, {
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error();
      setSettings(await resp.json());
    } catch {
      setFeedback("Fout: importinstellingen konden niet worden geladen.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && !settings) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const toggleComponent = (key: string) => {
    setSettings((s) => s && ({ ...s, components: { ...s.components, [key]: !s.components[key] } }));
    setDirty(true);
    setFeedback(null);
  };

  const toggleCompetitor = (name: string) => {
    setSettings((s) => {
      if (!s) return s;
      const lower = name.toLowerCase();
      const disabled = new Set(s.disabled_competitors);
      if (disabled.has(lower)) disabled.delete(lower); else disabled.add(lower);
      return {
        ...s,
        disabled_competitors: Array.from(disabled),
        competitors: s.competitors.map((c) =>
          c.name === name ? { ...c, enabled: !c.enabled } : c),
      };
    });
    setDirty(true);
    setFeedback(null);
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setFeedback(null);
    try {
      const resp = await fetch(`${BASE}/api/uploads/priceshape/import-settings`, {
        method: "PUT",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          components: settings.components,
          disabled_competitors: settings.disabled_competitors,
          max_delivery_days: settings.max_delivery_days,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => null);
        throw new Error(err?.detail || "Opslaan mislukt");
      }
      setDirty(false);
      setFeedback("Importinstellingen opgeslagen. Ze gelden voor feed-sync én handmatige upload.");
      await load();
    } catch (e) {
      setFeedback(`Fout: ${e instanceof Error ? e.message : "opslaan mislukt"}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        <span className="ml-1.5">Importinstellingen</span>
      </Button>

      {open && (
        <div className="rounded-md border border-input p-3 space-y-3">
          <p className="text-xs text-muted-foreground">
            Vink aan welke data-onderdelen en concurrenten worden geïmporteerd.
            Uitgevinkte onderdelen worden overgeslagen bij elke sync en upload;
            bestaande data wordt daarbij nooit gewist.
          </p>

          {loading && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}

          {settings && (
            <>
              <div>
                <Label className="text-xs font-medium">Data-onderdelen</Label>
                <div className="mt-1.5 grid gap-1.5">
                  {Object.entries(settings.component_labels).map(([key, label]) => (
                    <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-input"
                        checked={settings.components[key] ?? true}
                        onChange={() => toggleComponent(key)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <Label className="text-xs font-medium">Levertijd-drempel referentieprijs</Label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Concurrenten met een langere levertijd (in dagen) tellen niet mee in de
                  referentieprijs. Leeg laten = geen limiet; onbekende levertijd telt altijd mee.
                </p>
                <Input
                  type="number"
                  min={1}
                  className="mt-1.5 h-8 w-32"
                  placeholder="Geen limiet"
                  value={settings.max_delivery_days ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setSettings((s) => s && ({
                      ...s,
                      max_delivery_days: v === "" ? null : Math.max(1, Math.floor(Number(v))),
                    }));
                    setDirty(true);
                    setFeedback(null);
                  }}
                />
              </div>

              <div>
                <Label className="text-xs font-medium">
                  Concurrenten ({settings.competitors.length})
                </Label>
                {settings.competitors.length === 0 ? (
                  <p className="text-xs text-muted-foreground mt-1">
                    Nog geen concurrenten bekend — draai eerst een synchronisatie of import.
                  </p>
                ) : (
                  <div className="mt-1.5 grid grid-cols-2 gap-1.5 max-h-56 overflow-y-auto pr-1">
                    {settings.competitors.map((c) => (
                      <label key={c.name} className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          className="h-4 w-4 rounded border-input"
                          checked={c.enabled}
                          onChange={() => toggleCompetitor(c.name)}
                        />
                        <span className="truncate" title={c.name}>{c.name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {feedback && (
                <div className={`text-sm rounded-md px-3 py-2 ${
                  feedback.startsWith("Fout")
                    ? "bg-red-50 text-red-800 border border-red-200"
                    : "bg-emerald-50 text-emerald-800 border border-emerald-200"
                }`}>
                  {feedback}
                </div>
              )}

              <Button size="sm" onClick={handleSave} disabled={saving || !dirty}>
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                <span className="ml-1.5">Instellingen opslaan</span>
              </Button>
              {settings.updated_at && (
                <p className="text-xs text-muted-foreground">
                  Laatst gewijzigd {formatDate(settings.updated_at)}
                  {settings.updated_by ? ` door ${settings.updated_by}` : ""}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface ConnectorCardProps {
  connector: ConnectorSummary;
  onRefresh: () => void;
}

function ConnectorCard({ connector, onRefresh }: ConnectorCardProps) {
  const [open, setOpen] = useState(false);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [testResult, setTestResult] = useState<{ status: ConnStatus; message: string } | null>(null);
  const [syncResult, setSyncResult] = useState<{ status: string; message: string; counts: Record<string, number> } | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const displayStatus: ConnStatus | null = connector.live_status ?? connector.last_test_status;

  // De backend kan fields_filled als null teruggeven (bijv. een env-geconfigureerde
  // connector waarvan de config-rij geen opgeslagen credentials heeft). Normaliseer
  // altijd naar een array zodat .includes()/.map()/.length nooit crashen.
  const fieldsFilled = connector.fields_filled ?? [];

  const handleInput = (key: string, value: string) => {
    setFormValues((v) => ({ ...v, [key]: value }));
    setTestResult(null);
  };

  // Modus-ondersteuning: connectors met een "mode"-veld tonen een keuze en
  // filteren hun velden op de gekozen modus.
  const modeField = connector.fields.find((f) => f.key === "mode");
  const storedMode = fieldsFilled.includes("feed_url")
    ? "feed"
    : fieldsFilled.includes("api_url") || fieldsFilled.includes("api_key")
    ? "rest"
    : modeField?.default ?? "rest";
  const currentMode = formValues.mode ?? storedMode;

  const visibleFields = connector.fields.filter(
    (f) => f.key !== "mode" && (!f.mode || f.mode === currentMode)
  );

  const buildPayload = () =>
    modeField ? { ...formValues, mode: currentMode } : formValues;

  const allRequired = visibleFields
    .filter((f) => f.required)
    .every(
      (f) =>
        (formValues[f.key] ?? "").trim() !== "" ||
        fieldsFilled.includes(f.key)
    );

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    setFeedback(null);
    try {
      const resp = await fetch(`${BASE}/api/connectors/${connector.name}/test`, {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ credentials: buildPayload() }),
        // Eigen time-out (60s) i.p.v. de globale 15s: een feed-test kan een
        // externe URL moeten benaderen die traag het eerste antwoord geeft.
        signal: AbortSignal.timeout(60_000),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setTestResult({ status: "error", message: data.detail ?? "Testfout" });
      } else {
        setTestResult(data);
      }
    } catch {
      setTestResult({ status: "error", message: "Netwerkfout." });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setFeedback(null);
    try {
      const resp = await fetch(`${BASE}/api/connectors/${connector.name}/save`, {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ credentials: buildPayload() }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setFeedback(`Fout: ${data.detail ?? "Opslaan mislukt"}`);
      } else {
        setFeedback("Connector opgeslagen.");
        setFormValues({});
        setOpen(false);
        onRefresh();
      }
    } catch {
      setFeedback("Netwerkfout bij opslaan.");
    } finally {
      setSaving(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm(`Weet je zeker dat je ${connector.label} wilt ontkoppelen? De opgeslagen credentials worden verwijderd.`)) return;
    setDisconnecting(true);
    try {
      await fetch(`${BASE}/api/connectors/${connector.name}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      onRefresh();
    } catch {
      /* negeer */
    } finally {
      setDisconnecting(false);
    }
  };

  const handleSync = async (full = false) => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const resp = await fetch(`${BASE}/api/connectors/${connector.name}/sync${full ? "?full=true" : ""}`, {
        method: "POST",
        headers: getAuthHeaders(),
        // Ruime eigen time-out (5 min) i.p.v. de globale 15s: een volledige
        // feed-sync downloadt de complete feed (kan honderden MB's zijn) en
        // schrijft alle concurrentprijzen weg.
        signal: AbortSignal.timeout(300_000),
      });
      const data = await resp.json();
      setSyncResult(data);
      onRefresh();
    } catch {
      setSyncResult({ status: "error", message: "Netwerkfout bij synchronisatie.", counts: {} });
    } finally {
      setSyncing(false);
    }
  };

  const isConnected = displayStatus === "ok";
  const isConfigured = connector.configured;

  return (
    <Card
      className={
        connector.feed_outage?.severity === "error"
          ? "border-red-300 bg-red-50/40"
          : connector.feed_outage
          ? "border-amber-300"
          : isConnected
          ? "border-emerald-200"
          : isConfigured
          ? "border-amber-100"
          : ""
      }
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <Server className="w-5 h-5 text-muted-foreground shrink-0" />
            <div>
              <CardTitle className="text-base">{connector.label}</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                {connector.name === "priceshape" && "Concurrentieprijzen ophalen via PriceShape API"}
                {connector.name === "drs" && "Productcatalogus, verkoop en voorraad via DRS API"}
                {connector.name === "ga4" && "Sessies, conversies en traffic via Google Analytics 4"}
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className="flex items-center gap-1.5">
              <StatusDot status={displayStatus} />
              <span className={`text-xs font-medium ${isConnected ? "text-emerald-600" : "text-muted-foreground"}`}>
                {displayStatus ? STATUS_LABEL[displayStatus] : "Onbekend"}
              </span>
            </div>
            {isConfigured && (
              <Badge variant="outline" className="text-xs">
                {connector.source === "db"
                  ? "DB-config"
                  : connector.source === "default"
                  ? "Standaard-feed"
                  : "Omgevingsvariabele"}
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {connector.feed_outage && (
          <div
            className={`flex items-start gap-2 rounded-md border p-3 text-xs ${
              connector.feed_outage.severity === "error"
                ? "border-red-200 bg-red-50 text-red-700"
                : "border-amber-200 bg-amber-50 text-amber-700"
            }`}
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-semibold">
                Feed niet bereikbaar — {connector.feed_outage.unreached_text.toLowerCase()}
              </p>
              <p>
                Laatste mislukte sync: {formatDate(connector.feed_outage.failed_at)}
                {connector.feed_outage.last_success_at &&
                  ` · Laatste geslaagde sync: ${formatDate(connector.feed_outage.last_success_at)}`}
              </p>
              <p className="opacity-80">{connector.feed_outage.error_message}</p>
            </div>
          </div>
        )}
        {isConfigured && (
          <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
            <div>
              <span className="font-medium">Laatste test:</span>{" "}
              {formatDate(connector.last_tested_at)}
            </div>
            <div>
              <span className="font-medium">Laatste sync:</span>{" "}
              {formatDate(connector.last_synced_at)}
            </div>
            {connector.configured_by && (
              <div>
                <span className="font-medium">Geconfigureerd door:</span>{" "}
                {connector.configured_by}
              </div>
            )}
            {fieldsFilled.length > 0 && (
              <div>
                <span className="font-medium">Velden:</span>{" "}
                {fieldsFilled.map((k) => (
                  <span key={k} className="inline-flex items-center gap-1 mr-1">
                    <span className="font-mono bg-muted px-1 rounded">
                      {k}
                    </span>
                    <span className="text-muted-foreground/60">•••</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {syncResult && (
          <div className={`rounded-md px-3 py-2 text-sm ${
            syncResult.status === "ok"
              ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
              : "bg-red-50 text-red-800 border border-red-200"
          }`}>
            {syncResult.message}
            {Object.keys(syncResult.counts ?? {}).length > 0 && (
              <div className="mt-1 flex flex-wrap gap-3">
                {Object.entries(syncResult.counts).map(([k, v]) => (
                  <span key={k} className="text-xs">
                    <strong>{v}</strong> {k.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {connector.name === "priceshape" && connector.source === "default" && connector.default_feed_url && (
          <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-800">
            <span className="font-medium">Standaard-feed actief.</span>{" "}
            De connector gebruikt automatisch de vaste feed-URL{" "}
            <span className="font-mono break-all">{connector.default_feed_url}</span>.
            Je hoeft niets in te vullen; een eigen URL opslaan overschrijft de standaard,
            ontkoppelen valt hierop terug.
          </div>
        )}

        {connector.name === "priceshape" && <ImportSettingsPanel />}

        <div className="flex flex-wrap gap-2">
          {isConfigured && (
            <Button size="sm" variant="default" onClick={() => handleSync()} disabled={syncing}>
              {syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              <span className="ml-1.5">Nu synchroniseren</span>
            </Button>
          )}
          {isConfigured && connector.name === "priceshape" && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleSync(true)}
              disabled={syncing}
              title="Haal alles opnieuw op en ruim concurrentprijzen op die niet meer in PriceShape staan (vervangen-modus)."
            >
              {syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              <span className="ml-1.5">Volledige sync</span>
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => { setOpen((v) => !v); setTestResult(null); setFeedback(null); }}
          >
            {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            <span className="ml-1.5">{isConfigured ? "Wijzigen / Vervangen" : "Verbinding instellen"}</span>
          </Button>
          {isConfigured && connector.source === "db" && (
            <Button
              size="sm"
              variant="ghost"
              className="text-red-600 hover:text-red-700 hover:bg-red-50"
              onClick={handleDisconnect}
              disabled={disconnecting}
            >
              {disconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unlink className="w-3.5 h-3.5" />}
              <span className="ml-1.5">Ontkoppelen</span>
            </Button>
          )}
        </div>

        {open && (
          <>
            <Separator />
            <div className="space-y-3 pt-1">
              <p className="text-xs text-muted-foreground">
                Vul de verbindingsgegevens in en test de verbinding voor je opslaat.
                Geheimen worden versleuteld opgeslagen en nooit teruggetoond.
              </p>

              {modeField && (
                <div className="space-y-1.5">
                  <Label className="text-xs">{modeField.label}</Label>
                  <div className="grid grid-cols-2 gap-2">
                    {modeField.options?.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => {
                          setFormValues((v) => ({ ...v, mode: opt.value }));
                          setTestResult(null);
                        }}
                        className={`text-left rounded-md border px-3 py-2 text-xs transition-colors ${
                          currentMode === opt.value
                            ? "border-primary bg-primary/5 text-foreground font-medium"
                            : "border-input hover:bg-muted text-muted-foreground"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {visibleFields.map((field) => (
                <div key={field.key} className="space-y-1">
                  <Label className="text-xs" htmlFor={`${connector.name}-${field.key}`}>
                    {field.label}
                    {field.required && <span className="text-red-500 ml-1">*</span>}
                    {!field.required && (
                      <span className="text-muted-foreground ml-1">(optioneel)</span>
                    )}
                  </Label>
                  {field.type === "select" ? (
                    <select
                      id={`${connector.name}-${field.key}`}
                      value={formValues[field.key] ?? field.default ?? ""}
                      onChange={(e) => handleInput(field.key, e.target.value)}
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      {field.options?.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  ) : field.key === "service_account_key" ? (
                    <Textarea
                      id={`${connector.name}-${field.key}`}
                      placeholder={field.placeholder}
                      value={formValues[field.key] ?? ""}
                      onChange={(e) => handleInput(field.key, e.target.value)}
                      className="font-mono text-xs min-h-[80px]"
                      rows={4}
                    />
                  ) : (
                    <div className="relative">
                      <Input
                        id={`${connector.name}-${field.key}`}
                        type={field.secret && !showSecrets[field.key] ? "password" : "text"}
                        placeholder={
                          isConfigured && fieldsFilled.includes(field.key)
                            ? "••••• geconfigureerd (leeg laten om te behouden)"
                            : field.placeholder
                        }
                        value={formValues[field.key] ?? ""}
                        onChange={(e) => handleInput(field.key, e.target.value)}
                        className="font-mono text-sm pr-8"
                      />
                      {field.secret && (
                        <button
                          type="button"
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                          onClick={() => setShowSecrets((v) => ({ ...v, [field.key]: !v[field.key] }))}
                        >
                          {showSecrets[field.key] ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {testResult && (
                <div className={`flex items-start gap-2 rounded-md px-3 py-2 text-sm ${
                  testResult.status === "ok"
                    ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                    : "bg-red-50 text-red-800 border border-red-200"
                }`}>
                  {testResult.status === "ok"
                    ? <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                    : <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />}
                  <span>{testResult.message}</span>
                </div>
              )}

              {feedback && (
                <div className={`text-sm rounded-md px-3 py-2 ${
                  feedback.startsWith("Fout")
                    ? "bg-red-50 text-red-800 border border-red-200"
                    : "bg-emerald-50 text-emerald-800 border border-emerald-200"
                }`}>
                  {feedback}
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleTest}
                  disabled={testing || !allRequired}
                  title={!allRequired ? "Vul alle verplichte velden in" : ""}
                >
                  {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  <span className="ml-1.5">Verbinding testen</span>
                </Button>
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={saving || !allRequired}
                  title={!allRequired ? "Vul alle verplichte velden in" : ""}
                >
                  {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                  <span className="ml-1.5">Opslaan &amp; koppelen</span>
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function Connectoren() {
  const [connectors, setConnectors] = useState<ConnectorSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchConnectors = async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${BASE}/api/connectors`, { headers: getAuthHeaders() });
      if (resp.ok) {
        const data: ConnectorSummary[] = await resp.json();
        const ordered = ["priceshape", "drs", "ga4"]
          .map((name) => data.find((c) => c.name === name))
          .filter(Boolean) as ConnectorSummary[];
        setConnectors(ordered);
      }
    } catch {
      /* netwerk niet beschikbaar */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConnectors();
  }, []);

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Connectoren</h1>
          <p className="text-muted-foreground mt-1">
            Koppel externe databronnen rechtstreeks vanuit de app. Credentials worden versleuteld
            opgeslagen. Omgevingsvariabelen blijven werken als terugval.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchConnectors} disabled={loading}>
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          <span className="ml-1.5">Vernieuwen</span>
        </Button>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="py-8">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                  <span className="text-muted-foreground text-sm">Laden…</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : connectors.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            Geen connectors gevonden.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {connectors.map((c) => (
            <ConnectorCard key={c.name} connector={c} onRefresh={fetchConnectors} />
          ))}
        </div>
      )}

      <Card className="border-dashed">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-muted-foreground" />
            Terugval op omgevingsvariabelen
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            Bestaande omgevingsvariabelen (<span className="font-mono">PRICESHAPE_API_URL</span>,{" "}
            <span className="font-mono">DRS_API_URL</span>,{" "}
            <span className="font-mono">GA4_PROPERTY_ID</span> e.d.) blijven werken als de connector
            niet via de DB is geconfigureerd. DB-configuratie heeft voorrang op omgevingsvariabelen.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
