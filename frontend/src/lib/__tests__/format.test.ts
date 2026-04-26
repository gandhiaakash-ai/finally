import { describe, it, expect } from "vitest";
import {
  formatNumber,
  formatPercent,
  formatSignedUsd,
  formatUsd,
  formatUsdCompact,
} from "../format";

describe("format helpers", () => {
  it("formats USD with two decimals", () => {
    expect(formatUsd(1234.5)).toBe("$1,234.50");
    expect(formatUsd(0)).toBe("$0.00");
  });

  it("formats compact USD for large values", () => {
    expect(formatUsdCompact(1500)).toMatch(/1\.5K/);
    expect(formatUsdCompact(1_250_000)).toMatch(/1\.25M/);
  });

  it("formats percent with sign on positive", () => {
    expect(formatPercent(1.234)).toBe("+1.23%");
    expect(formatPercent(-0.5)).toBe("-0.50%");
    expect(formatPercent(0)).toBe("0.00%");
  });

  it("formats signed USD with sign", () => {
    expect(formatSignedUsd(50)).toBe("+$50.00");
    expect(formatSignedUsd(-25)).toBe("-$25.00");
    expect(formatSignedUsd(0)).toBe("$0.00");
  });

  it("formats arbitrary numbers", () => {
    expect(formatNumber(1234.5)).toBe("1,234.5");
    expect(formatNumber(0.0001)).toBe("0.0001");
  });
});
