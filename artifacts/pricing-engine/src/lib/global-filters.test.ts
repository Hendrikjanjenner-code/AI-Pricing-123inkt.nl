/**
 * Tests Global Filter Context (taak #216):
 * - descendant-selectie (parent dekt subtree; snoei + impliciete selectie)
 * - URL-(de)serialisatie round-trip
 * - contextbehoud bij navigatie (store blijft leidend als URL-params wegvallen)
 */
import { describe, expect, it, beforeEach } from "vitest";
import {
  __resetGlobalFiltersForTests,
  apiFilterParams,
  clearGlobalFilters,
  emptyFilters,
  getGlobalFilters,
  hasActiveFilters,
  isDescendantOf,
  isNodeSelected,
  paramsHaveFilters,
  pruneDescendants,
  readFiltersFromParams,
  setGlobalFilters,
  toggleNode,
  writeFiltersToParams,
  type HierarchyNodeSelection,
} from "./global-filters";

const tuin: HierarchyNodeSelection = { id: 1, name: "Tuin", path: "/1/" };
const gereedschap: HierarchyNodeSelection = { id: 7, name: "Gereedschap", path: "/1/7/" };
const zagen: HierarchyNodeSelection = { id: 23, name: "Zagen", path: "/1/7/23/" };
const keuken: HierarchyNodeSelection = { id: 2, name: "Keuken", path: "/2/" };

describe("descendant-selectie", () => {
  it("herkent descendants via het gematerialiseerde pad", () => {
    expect(isDescendantOf(gereedschap, tuin)).toBe(true);
    expect(isDescendantOf(zagen, tuin)).toBe(true);
    expect(isDescendantOf(keuken, tuin)).toBe(false);
    expect(isDescendantOf(tuin, tuin)).toBe(false); // zelf ≠ descendant
  });

  it("snoeit geselecteerde descendants weg als de parent geselecteerd is", () => {
    expect(pruneDescendants([tuin, gereedschap, zagen, keuken]))
      .toEqual([tuin, keuken]);
  });

  it("toggleNode: parent selecteren verwijdert al geselecteerde descendants", () => {
    const sel = toggleNode([gereedschap, zagen, keuken], tuin);
    expect(sel).toEqual([keuken, tuin]);
  });

  it("toggleNode: nogmaals togglen deselecteert", () => {
    expect(toggleNode([tuin], tuin)).toEqual([]);
  });

  it("markeert descendants van een geselecteerde parent als impliciet geselecteerd", () => {
    const sel = [tuin];
    expect(isNodeSelected(sel, zagen)).toEqual({ explicit: false, implied: true });
    expect(isNodeSelected(sel, tuin)).toEqual({ explicit: true, implied: false });
    expect(isNodeSelected(sel, keuken)).toEqual({ explicit: false, implied: false });
  });

  it("nodes zonder pad (nog niet gehydrateerde deep-link) worden nooit weggesnoeid", () => {
    const los: HierarchyNodeSelection = { id: 99, name: "#99", path: null };
    expect(pruneDescendants([tuin, los])).toEqual([tuin, los]);
  });
});

describe("URL-(de)serialisatie", () => {
  it("round-tript alle filterdimensies", () => {
    const f = {
      hierarchy: [tuin, keuken],
      brands: ["Bosch", "Merk~met/teken"],
      periodDays: 30,
      skuQuery: "boormachine",
    };
    const params = new URLSearchParams("shop_id=3");
    writeFiltersToParams(f, params);
    expect(params.get("shop_id")).toBe("3"); // andere params blijven staan
    expect(paramsHaveFilters(params)).toBe(true);

    const terug = readFiltersFromParams(params, [tuin, keuken]);
    expect(terug.hierarchy).toEqual([tuin, keuken]);
    expect(terug.brands).toEqual(["Bosch", "Merk~met/teken"]);
    expect(terug.periodDays).toBe(30);
    expect(terug.skuQuery).toBe("boormachine");
  });

  it("onbekende node-ids krijgen een placeholder tot hydratatie", () => {
    const params = new URLSearchParams("f_hn=42");
    const f = readFiltersFromParams(params);
    expect(f.hierarchy).toEqual([{ id: 42, name: "#42", path: null }]);
  });

  it("lege filters verwijderen alle f_-params uit de URL", () => {
    const params = new URLSearchParams("f_hn=1&f_brand=x&f_days=7&f_sku=q");
    writeFiltersToParams(emptyFilters(), params);
    expect(paramsHaveFilters(params)).toBe(false);
  });

  it("apiFilterParams stuurt alleen server-side filters mee", () => {
    const qs = apiFilterParams({
      hierarchy: [tuin, keuken], brands: ["Bosch"], periodDays: 30, skuQuery: "x",
    });
    const p = new URLSearchParams(qs);
    expect(p.get("hierarchy_node_ids")).toBe("1,2");
    expect(p.get("brands")).toBe("Bosch");
    expect(p.has("f_days")).toBe(false);
  });
});

describe("contextbehoud bij navigatie tussen modules", () => {
  beforeEach(() => __resetGlobalFiltersForTests());

  it("de store houdt de context vast, ook als een navigatie de URL-params laat vallen", () => {
    setGlobalFilters({ hierarchy: [tuin], brands: ["Bosch"], periodDays: 90 });

    // Simuleer een SPA-navigatie: de nieuwe locatie heeft géén f_-params meer.
    const naNavigatie = new URLSearchParams("");
    expect(paramsHaveFilters(naNavigatie)).toBe(false);

    // De centrale store blijft de bron van waarheid.
    const ctx = getGlobalFilters();
    expect(ctx.hierarchy).toEqual([tuin]);
    expect(ctx.brands).toEqual(["Bosch"]);
    expect(ctx.periodDays).toBe(90);
    expect(hasActiveFilters(ctx)).toBe(true);

    // En de context is opnieuw naar de URL te schrijven voor deelbare links.
    writeFiltersToParams(ctx, naNavigatie);
    expect(naNavigatie.get("f_hn")).toBe("1");
    expect(naNavigatie.get("f_brand")).toBe("Bosch");
  });

  it("deep-link-params winnen van een opgeslagen context", () => {
    const opgeslagen = { ...emptyFilters(), brands: ["OudMerk"] };
    const url = new URLSearchParams("f_brand=NieuwMerk");
    const effectief = paramsHaveFilters(url)
      ? readFiltersFromParams(url, opgeslagen.hierarchy)
      : opgeslagen;
    expect(effectief.brands).toEqual(["NieuwMerk"]);
  });

  it("setGlobalFilters snoeit descendants (server telt ze al mee)", () => {
    setGlobalFilters({ hierarchy: [tuin, zagen] });
    expect(getGlobalFilters().hierarchy).toEqual([tuin]);
  });

  it("'alle filters wissen' maakt de context leeg", () => {
    setGlobalFilters({ hierarchy: [tuin], skuQuery: "zaag" });
    clearGlobalFilters();
    expect(hasActiveFilters(getGlobalFilters())).toBe(false);
  });
});
