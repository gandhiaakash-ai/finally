"use client";

import { useMemo } from "react";

type Props = {
  data: number[];
  width?: number;
  height?: number;
  strokeWidth?: number;
  /** Optional explicit color; defaults to direction-based green/red. */
  color?: string;
  className?: string;
};

/**
 * Tiny SVG sparkline. Renders a single polyline scaled to fit the box.
 * Color defaults to green/red based on whether the series is overall up.
 *
 * Pure data → SVG: no canvas, no deps, performant for 60-240 points per row.
 */
export function Sparkline({
  data,
  width = 80,
  height = 22,
  strokeWidth = 1.25,
  color,
  className = "",
}: Props) {
  const path = useMemo(() => {
    if (data.length < 2) return "";
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = width / (data.length - 1);
    return data
      .map((v, i) => {
        const x = i * stepX;
        const y = height - ((v - min) / range) * height;
        return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }, [data, width, height]);

  if (data.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        className={className}
        aria-hidden="true"
      />
    );
  }

  const stroke =
    color ??
    (data[data.length - 1]! >= data[0]!
      ? "var(--color-tick-up)"
      : "var(--color-tick-down)");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden="true"
    >
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
