import { describe, expect, it } from "vitest";

import { orderConnectors } from "./connector-order";

describe("orderConnectors", () => {
  it("toont Creditsafe en behoudt onbekende toekomstige connectors", () => {
    const connectors = [
      { name: "future_source" },
      { name: "ga4" },
      { name: "creditsafe" },
      { name: "priceshape" },
      { name: "drs" },
    ];

    expect(orderConnectors(connectors).map((connector) => connector.name)).toEqual([
      "priceshape",
      "drs",
      "creditsafe",
      "ga4",
      "future_source",
    ]);
  });

  it("wijzigt de ontvangen array niet", () => {
    const connectors = [{ name: "ga4" }, { name: "priceshape" }];

    orderConnectors(connectors);

    expect(connectors.map((connector) => connector.name)).toEqual([
      "ga4",
      "priceshape",
    ]);
  });
});