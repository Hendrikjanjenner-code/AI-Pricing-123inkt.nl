import { describe, expect, it } from "vitest";

import {
  copilotMessageUrl,
  copilotScopeErrorMessage,
  resolveCopilotShopId,
} from "./copilot-shop";

describe("Copilot shopinitialisatie", () => {
  it("gebruikt de shop uit het zojuist aangemaakte gesprek bij de eerste klik", () => {
    expect(resolveCopilotShopId(undefined, 7)).toBe(7);
    expect(copilotMessageUrl("", 42, 7)).toBe(
      "/api/copilot/conversations/42/messages?shop_id=7",
    );
  });

  it("maakt nooit een request met shop-id 0", () => {
    expect(resolveCopilotShopId(undefined, null, 0)).toBeNull();
    expect(() => copilotMessageUrl("", 42, 0)).toThrow(
      "Copilot shop is nog niet beschikbaar",
    );
  });

  it("onderscheidt een winkelscopefout van een netwerk- of AI-storing", () => {
    expect(copilotScopeErrorMessage(404)).toContain("actieve winkel");
    expect(copilotScopeErrorMessage(403)).toContain("geen toegang");
    expect(copilotScopeErrorMessage(422)).toContain("winkel kon niet worden vastgesteld");
    expect(copilotScopeErrorMessage(404, "Gesprek niet gevonden")).toBe(
      "Gesprek niet gevonden",
    );
  });
});