import { describe, expect, it } from "vitest";
import {
  ROUTES, REDIRECTS, DOMEINEN, sidebarModel, vindRoute, breadcrumbsVoor,
  MIJN_DASHBOARD,
} from "./route-registry";

describe("route registry", () => {
  it("heeft unieke paden (geen dubbele menu-items of routes)", () => {
    const paden = ROUTES.map((r) => r.path);
    expect(new Set(paden).size).toBe(paden.length);
  });

  it("heeft geen alias die botst met een canoniek pad", () => {
    const paden = new Set(ROUTES.map((r) => r.path));
    for (const redirect of REDIRECTS) {
      expect(paden.has(redirect.from)).toBe(false);
      // redirect-doel bestaat als route
      expect(paden.has(redirect.to)).toBe(true);
    }
  });

  it("mapt elke route naar precies één bestaand domein", () => {
    const domeinIds = new Set(DOMEINEN.map((d) => d.id));
    for (const route of ROUTES) {
      expect(domeinIds.has(route.domein)).toBe(true);
    }
  });

  it("heeft 13 domeinen", () => {
    expect(DOMEINEN.length).toBe(13);
  });

  it("verwijst breadcrumbParent altijd naar een bestaande route", () => {
    const paden = new Set(ROUTES.map((r) => r.path));
    for (const route of ROUTES) {
      if (route.breadcrumbParent) {
        expect(paden.has(route.breadcrumbParent), route.path).toBe(true);
      }
    }
  });

  it("houdt detailroutes uit de sidebar", () => {
    for (const route of ROUTES) {
      if (route.path.includes(":")) expect(route.inSidebar).toBe(false);
      if (route.inSidebar) expect(route.icon, route.path).toBeDefined();
    }
  });

  it("pint Mijn Dashboard bovenaan en niet in een groep", () => {
    expect(MIJN_DASHBOARD.path).toBe("/");
    const groepen = sidebarModel();
    for (const groep of groepen) {
      expect(groep.items.some((i) => i.path === "/")).toBe(false);
    }
  });

  it("matcht concrete locaties op de juiste route", () => {
    expect(vindRoute("/")?.label).toBe("Mijn Dashboard");
    expect(vindRoute("/competition")?.label).toBe("CI Dashboard");
    expect(vindRoute("/competition/competitors/42")?.path).toBe("/competition/competitors/:id");
    expect(vindRoute("/producten/123")?.path).toBe("/producten/:id");
    expect(vindRoute("/traffic/categorie")?.path).toBe("/traffic/categorie");
    expect(vindRoute("/traffic/categorie/fietsen")?.path).toBe("/traffic/categorie/:category");
    expect(vindRoute("/bestaat-niet")).toBeUndefined();
  });

  it("bouwt breadcrumbs als domein > (ouder) > pagina", () => {
    expect(breadcrumbsVoor("/prijsadviezen/9").map((k) => k.label)).toEqual([
      "Pricing", "Prijsadviezen", "Prijsadvies-detail",
    ]);
    expect(breadcrumbsVoor("/bcg/sku/7").map((k) => k.label)).toEqual([
      "CatMan", "BCG Dashboard", "SKU BCG-matrix", "SKU BCG-detail",
    ]);
    // ouders zijn klikbaar, huidige pagina niet
    const kruimels = breadcrumbsVoor("/bcg/sku-matrix");
    expect(kruimels[kruimels.length - 1].href).toBeUndefined();
    expect(kruimels.find((k) => k.label === "BCG Dashboard")?.href).toBe("/bcg/dashboard");
  });

  it("dekt alle oude deep links met een redirect of route", () => {
    const oudePaden = [
      "/recommendations", "/recommendations/:id", "/skus", "/skus/:id",
      "/categories", "/categories/hierarchy", "/data-upload", "/data-quality",
      "/substitutions", "/model-health", "/settings",
    ];
    const froms = new Set(REDIRECTS.map((r) => r.from));
    for (const pad of oudePaden) expect(froms.has(pad), pad).toBe(true);
  });
});
