/**
 * Kies uitsluitend een echte, positieve shop-id voor Copilot-verzoeken.
 * `0` is nooit een geldige fallback: als er nog geen shop bekend is, moet de
 * caller wachten of de shop uit de zojuist aangemaakte conversatie gebruiken.
 */
export function resolveCopilotShopId(
  ...candidates: Array<number | null | undefined>
): number | null {
  return candidates.find(
    (value): value is number => Number.isInteger(value) && value != null && value > 0,
  ) ?? null;
}

export function copilotMessageUrl(
  base: string,
  conversationId: number,
  shopId: number,
): string {
  const validShopId = resolveCopilotShopId(shopId);
  if (validShopId == null) {
    throw new Error("Copilot shop is nog niet beschikbaar");
  }
  return `${base}/api/copilot/conversations/${conversationId}/messages?shop_id=${validShopId}`;
}

export function copilotScopeErrorMessage(status: number, detail?: string | null): string {
  if (detail) return detail;
  if (status === 404) {
    return "Dit gesprek hoort niet bij de actieve winkel. Open een nieuw gesprek en probeer het opnieuw.";
  }
  if (status === 403) {
    return "Je hebt geen toegang tot de winkel van dit gesprek.";
  }
  return "De actieve winkel kon niet worden vastgesteld. Vernieuw de pagina en probeer het opnieuw.";
}