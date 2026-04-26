import { describe, it, expect } from "vitest";
import { squarify } from "../treemap";

describe("squarify", () => {
  it("returns no cells when total is zero", () => {
    expect(squarify([], 100, 100)).toEqual([]);
    expect(squarify([{ key: "a", value: 0 }], 100, 100)).toEqual([]);
  });

  it("preserves total area = width × height", () => {
    const cells = squarify(
      [
        { key: "a", value: 60 },
        { key: "b", value: 30 },
        { key: "c", value: 10 },
      ],
      200,
      100,
    );
    const totalArea = cells.reduce((s, c) => s + c.width * c.height, 0);
    expect(totalArea).toBeCloseTo(200 * 100, 1);
    expect(cells).toHaveLength(3);
  });

  it("emits one cell per item with non-negative dimensions", () => {
    const cells = squarify(
      [
        { key: "x", value: 40 },
        { key: "y", value: 35 },
        { key: "z", value: 25 },
      ],
      300,
      200,
    );
    expect(cells.map((c) => c.key).sort()).toEqual(["x", "y", "z"]);
    for (const c of cells) {
      expect(c.width).toBeGreaterThan(0);
      expect(c.height).toBeGreaterThan(0);
      expect(c.x).toBeGreaterThanOrEqual(0);
      expect(c.y).toBeGreaterThanOrEqual(0);
    }
  });

  it("sizes a single item to fill the rectangle", () => {
    const [cell] = squarify([{ key: "only", value: 1 }], 50, 80);
    expect(cell?.width).toBeCloseTo(50);
    expect(cell?.height).toBeCloseTo(80);
  });
});
