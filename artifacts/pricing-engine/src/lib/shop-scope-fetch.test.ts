/**
 * Tests voor de shop-scope URL-helper: elke /api-request krijgt de actieve
 * shop_id mee, zonder bestaande parameters te overschrijven en zonder
 * auth- of externe URL's aan te raken.
 */
import { describe, it, expect } from "vitest";
import { scopeApiUrl } from "./shop-scope-fetch";

describe("scopeApiUrl", () => {
  it("voegt shop_id toe aan een kale /api-URL (winkel B geselecteerd)", () => {
    expect(scopeApiUrl("/api/dashboard/summary", 2)).toBe(
      "/api/dashboard/summary?shop_id=2"
    );
  });

  it("voegt shop_id toe achter bestaande queryparameters", () => {
    expect(scopeApiUrl("/api/products?days=30", 2)).toBe(
      "/api/products?days=30&shop_id=2"
    );
  });

  it("overschrijft een expliciete shop_id van de caller nooit", () => {
    expect(scopeApiUrl("/api/products?shop_id=1", 2)).toBe(
      "/api/products?shop_id=1"
    );
  });

  it("laat auth-endpoints ongemoeid", () => {
    expect(scopeApiUrl("/api/auth/login", 2)).toBe("/api/auth/login");
  });

  it("laat niet-API-paden ongemoeid", () => {
    expect(scopeApiUrl("/assets/logo.svg", 2)).toBe("/assets/logo.svg");
  });

  it("doet niets zonder actieve shop", () => {
    expect(scopeApiUrl("/api/products", undefined)).toBe("/api/products");
  });

  it("scoped ook absolute same-origin URL's op pad", () => {
    expect(scopeApiUrl("http://local/api/products", 2)).toBe(
      "http://local/api/products?shop_id=2"
    );
  });
});
