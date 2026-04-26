import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { Sparkline } from "../Sparkline";

describe("Sparkline", () => {
  it("renders an empty SVG when fewer than 2 points", () => {
    const { container } = render(<Sparkline data={[]} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(svg?.querySelector("path")).toBeNull();
  });

  it("renders a path with M/L commands when given a series", () => {
    const { container } = render(<Sparkline data={[1, 2, 3, 2]} />);
    const path = container.querySelector("path");
    expect(path).not.toBeNull();
    const d = path?.getAttribute("d") ?? "";
    expect(d.startsWith("M")).toBe(true);
    expect(d.split("L").length).toBeGreaterThan(1);
  });

  it("uses the up color when the series ends higher than it started", () => {
    const { container } = render(<Sparkline data={[1, 2, 3]} />);
    const stroke = container.querySelector("path")?.getAttribute("stroke");
    expect(stroke).toContain("tick-up");
  });

  it("uses the down color when the series ends lower than it started", () => {
    const { container } = render(<Sparkline data={[3, 2, 1]} />);
    const stroke = container.querySelector("path")?.getAttribute("stroke");
    expect(stroke).toContain("tick-down");
  });
});
