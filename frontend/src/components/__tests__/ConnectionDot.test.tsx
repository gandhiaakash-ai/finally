import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConnectionDot } from "../ConnectionDot";

describe("ConnectionDot", () => {
  it("shows Live label when connected", () => {
    render(<ConnectionDot status="connected" />);
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("shows Reconnecting label", () => {
    render(<ConnectionDot status="reconnecting" />);
    expect(screen.getByText("Reconnecting")).toBeInTheDocument();
  });

  it("shows Disconnected label", () => {
    render(<ConnectionDot status="disconnected" />);
    expect(screen.getByText("Disconnected")).toBeInTheDocument();
  });

  it("exposes status via data attribute for assertions", () => {
    const { container } = render(<ConnectionDot status="reconnecting" />);
    expect(
      container.querySelector('[data-status="reconnecting"]'),
    ).toBeInTheDocument();
  });
});
