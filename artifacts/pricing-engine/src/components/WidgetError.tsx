import { AlertTriangle } from "lucide-react";

export function WidgetError({ message }: { message?: string }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-muted-foreground text-sm">
      <AlertTriangle className="h-6 w-6 text-amber-500" />
      <span>Data tijdelijk niet beschikbaar</span>
      {message && <span className="text-xs opacity-70">{message}</span>}
    </div>
  );
}
