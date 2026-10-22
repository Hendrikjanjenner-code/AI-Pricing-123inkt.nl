import { describe, expect, it } from "vitest";
import fx from "./__fixtures__/backend-snapshots.json";
import {
  ShapeError, parseBasis, parseCalculation, parseConfig, parseExport, parseOverview, parseReadback, parseRun, readbackBuckets,
} from "./model";
import { CmError, decError, detailLines, errLines } from "./api";
import { manualRowErrors, toInputRows } from "./rows";
import { isStale } from "@/components/channelmanager/CalcPanel";

// Fixtures zijn echte responses van routes/channelmanager.py
// (gegenereerd met scripts/channelmanager_fixtures.py).

describe("channelmanager parsers op echte backendresponses", () => {
  it("overzicht leeg en gevuld, inclusief planner-beschikbaarheid", () => {
    const empty = parseOverview(fx.overview_empty);
    expect(empty.config).toBeNull();
    expect(empty.scheduler.available).toBe(false);
    expect(empty.scheduler.reason).toBe("disabled_by_environment_or_tests");
    const full = parseOverview(fx.overview_full);
    expect(full.config?.status).toBe("active");
    expect(full.queues.exported).toBe(1);
    expect(full.counts.readback).toBe(2);
    expect(full.last_run?.kind).toBe("run");
    expect(full.can_export).toBe(true);
  });

  it("config, basis, berekening, export, run", () => {
    expect(parseConfig(fx.config).data.config.rule).toEqual({ kind: "fixed", value: "-1" });
    expect(parseBasis(fx.basis_staged).snap.status).toBe("staged");
    expect(parseBasis(fx.basis_approved).data.approval?.notes).toBe("ok");
    const blocked = parseCalculation(fx.calc_blocked).data;
    expect(blocked.blocked_rows).toBe(1);
    expect(blocked.csv_preview).toBeNull();
    expect(blocked.rows[1].errors).toEqual(["Missing cost or below minimum net margin"]);
    const ok = parseCalculation(fx.calc_preview).data;
    expect(ok.rows[0].target_price).toBe("11.10");
    expect(typeof ok.csv_preview).toBe("string");
    expect(ok.cost_provenance?.cost_basis).toBe("net");
    const exp = parseExport(fx.export).data;
    expect(exp.processed).toBe(false);
    expect(exp.fingerprint).toHaveLength(64);
    expect(parseRun(fx.run).snap.status).toBe("success");
  });

  it("cross-shop: huidige bronprijs nooit als bestemming", () => {
    const row = parseCalculation(fx.calc_cross_shop).data.rows[0];
    expect(row.current_price).toBeNull();
    expect(row.current_delta).toBeNull();
    expect(row.source_current_price).toBe("12.10");
  });

  it("terugmelding: alleen exacte match bewijst verwerking; buckets uit serverlijsten", () => {
    const m = parseReadback(fx.readback_matched);
    expect(m.snap.status).toBe("matched");
    expect(m.data.processed).toBe(true);
    expect(readbackBuckets(m.data).matching).toEqual(["A-1"]);
    const p = parseReadback(fx.readback_partial);
    expect(p.snap.status).toBe("partial");
    expect(p.data.processed).toBe(false);
    const b = readbackBuckets(p.data);
    expect(b.mismatch).toEqual(["A-1"]);
    expect(b.unexpected).toEqual(["ZZ"]);
    expect(b.duplicate).toEqual(["ZZ"]);
    expect(b.missing).toEqual([]);
    expect(b.matching).toEqual([]);
  });

  it("afwijkende vorm of status wordt expliciet geweigerd", () => {
    expect(() => parseCalculation(fx.export)).toThrow(ShapeError);
    expect(() => parseReadback({ ...fx.readback_matched, status: "processed" })).toThrow(/onbekende status/);
    expect(() => parseOverview({ ...fx.overview_full, scheduler: undefined })).toThrow(ShapeError);
  });

  it("verouderd-detectie tegen huidige config/basis", () => {
    const d = parseCalculation(fx.calc_preview).data;
    expect(isStale(d, d.config_id, d.basis_id)).toBe(false);
    expect(isStale(d, d.config_id + 1, d.basis_id)).toBe(true);
    expect(isStale(d, d.config_id, undefined)).toBe(false);
  });
});

describe("foutweergave", () => {
  it("422-lijst leesbaar zonder [object Object]", () => {
    const lines = detailLines(fx.error_422_config);
    expect(lines).toEqual(["config: Value error, VAT must be an explicit fraction between 0 and 1"]);
    const e = errLines(new CmError(422, lines.join("\n"), lines));
    expect(e.title).toBe("Validatiefout");
    expect(e.lines.join(" ")).not.toContain("[object");
  });
  it("409 string-detail", () => {
    expect(detailLines(fx.error_409_config)).toEqual(["Configuration revision changed"]);
  });
  it("meerregelige string-detail (CSV) wordt gesplitst", () => {
    expect(detailLines({ detail: "2 validation errors\nrows.0.base_price\n  bad" })).toHaveLength(3);
  });
});

describe("invoer", () => {
  it("decimalen met tekens en grenzen", () => {
    expect(decError("-2.50", { signed: true })).toBeNull();
    expect(decError("+5", { signed: true })).toBeNull();
    expect(decError("-1")).not.toBeNull();
    expect(decError("0", { required: true, max: 1 })).toBeNull();
    expect(decError("1", { max: 1 })).toBeNull();
    expect(decError("1.01", { max: 1 })).not.toBeNull();
    expect(decError("12,5")).not.toBeNull();
  });
  it("handmatige rijen: fouten per rij en exacte payload", () => {
    const rows = [
      { sku: "A", name: "", category: "", base_price: "1.00", cost: "", current_price: "" },
      { sku: "A", name: "", category: "", base_price: "x", cost: "", current_price: "" },
    ];
    const errs = manualRowErrors(rows);
    expect(errs[0]).toEqual([]);
    expect(errs[1]).toContain("Dubbele SKU");
    expect(errs[1].some(e => e.startsWith("Basisprijs"))).toBe(true);
    expect(toInputRows(rows.slice(0, 1))).toEqual([{ sku: "A", name: "", category: "", base_price: "1.00", cost: null, current_price: null }]);
  });
});
