/**
 * ShopSwitcher — winkelkeuze-dropdown in de navigatiebalk.
 *
 * Toont de winkels waartoe de ingelogde gebruiker toegang heeft
 * (GET /api/shops) en laat wisselen van actieve shop-scope.
 * Na wisselen worden alle actieve queries opnieuw geladen.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Store } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useShopId, setActiveShopId } from "@/hooks/use-shop-id";

interface Shop {
  id: number;
  shop_code: string;
  name: string;
  is_default: boolean;
  active: boolean;
}

export function ShopSwitcher() {
  const queryClient = useQueryClient();
  const shopId = useShopId();

  const { data } = useQuery<{ shops: Shop[] }>({
    queryKey: ["/api/shops"],
    queryFn: async () => {
      const res = await fetch("/api/shops", {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("auth_token")}`,
        },
      });
      if (!res.ok) throw new Error("Winkels laden mislukt");
      return res.json();
    },
    staleTime: 5 * 60 * 1000,
  });

  const shops = (data?.shops ?? []).filter((s) => s.active);
  if (shops.length === 0) return null;

  const defaultShop = shops.find((s) => s.is_default) ?? shops[0];
  const actieveShop =
    shops.find((s) => s.id === shopId) ?? defaultShop;

  const wissel = (value: string) => {
    const nieuw = parseInt(value, 10);
    if (!Number.isFinite(nieuw) || nieuw === actieveShop.id) return;
    setActiveShopId(nieuw);
    // Herlaad alle actieve queries zodat elk scherm de nieuwe shop toont
    queryClient.invalidateQueries();
  };

  return (
    <Select value={String(actieveShop.id)} onValueChange={wissel}>
      <SelectTrigger
        className="h-9 w-[200px] gap-2"
        aria-label="Actieve winkel"
        data-testid="select-shop"
      >
        <Store className="w-4 h-4 shrink-0 text-muted-foreground" />
        <SelectValue placeholder="Kies winkel" />
      </SelectTrigger>
      <SelectContent>
        {shops.map((s) => (
          <SelectItem key={s.id} value={String(s.id)}>
            {s.name}
            {s.is_default ? " (standaard)" : ""}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
