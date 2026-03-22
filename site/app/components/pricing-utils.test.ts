import { describe, expect, it } from "vitest";
import {
  calcAgencyOsCost,
  calcDirectCost,
  calcSmartRoutingCost,
  fmt,
  fmtDollars,
} from "./pricing-utils";

describe("pricing utils", () => {
  it("formats token counts compactly", () => {
    expect(fmt(500)).toBe("500");
    expect(fmt(25_000)).toBe("25K");
    expect(fmt(5_000_000)).toBe("5M");
  });

  it("formats dollar values with precision by magnitude", () => {
    expect(fmtDollars(0.009)).toBe("$0.009");
    expect(fmtDollars(9.5)).toBe("$9.50");
    expect(fmtDollars(1500.1)).toBe("$1,500.10");
  });

  it("calculates direct and smart-routed costs", () => {
    const tokens = 1_000_000;
    const direct = calcDirectCost("Claude Sonnet 4", tokens);
    const smartRouting = calcSmartRoutingCost(tokens);
    const agencyOs = calcAgencyOsCost("Claude Sonnet 4", tokens);

    expect(direct).toBeCloseTo(9, 6);
    expect(smartRouting.agencyOs).toBeCloseTo(0.585, 6);
    expect(smartRouting.label).toBe("auto (smart routing)");
    expect(agencyOs).toBeCloseTo(1.755, 6);
    expect(agencyOs).toBeLessThan(direct);
  });

  it("returns zero for unknown models", () => {
    expect(calcDirectCost("unknown-model", 1_000_000)).toBe(0);
    expect(calcAgencyOsCost("unknown-model", 1_000_000)).toBe(0);
  });
});
