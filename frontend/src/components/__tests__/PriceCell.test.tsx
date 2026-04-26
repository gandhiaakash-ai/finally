import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PriceCell } from "../PriceCell";

describe("PriceCell", () => {
  it("renders an em dash for null/undefined price", () => {
    render(<PriceCell price={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("formats price to two decimals by default", () => {
    render(<PriceCell price={190.5} />);
    expect(screen.getByText("190.50")).toBeInTheDocument();
  });

  it("flashes up when price increases", async () => {
    const { rerender, container } = render(<PriceCell price={100} />);
    rerender(<PriceCell price={101} />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("flash-up");
  });

  it("flashes down when price decreases", async () => {
    const { rerender, container } = render(<PriceCell price={100} />);
    rerender(<PriceCell price={99} />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("flash-down");
  });

  it("does not flash on first render", () => {
    const { container } = render(<PriceCell price={100} />);
    const span = container.querySelector("span");
    expect(span?.className).not.toContain("flash-up");
    expect(span?.className).not.toContain("flash-down");
  });
});
