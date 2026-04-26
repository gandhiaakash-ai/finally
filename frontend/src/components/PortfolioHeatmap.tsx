"use client";

import { useEffect, useRef, useState } from "react";
import { squarify } from "@/lib/treemap";
import { formatPercent } from "@/lib/format";
import type { PositionView } from "@/types/api";

type Props = {
  positions: PositionView[];
};

/**
 * Treemap of positions: rectangle area = market value, fill = unrealized P&L %.
 * Renders SVG (no canvas needed for ~10–30 cells).
 */
export function PortfolioHeatmap({ positions }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 320, height: 200 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      setSize({ width: el.clientWidth, height: el.clientHeight });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const items = positions
    .filter((p) => p.market_value > 0)
    .sort((a, b) => b.market_value - a.market_value)
    .map((p) => ({ key: p.ticker, value: p.market_value }));

  const cells = squarify(items, size.width, size.height);

  return (
    <div className="panel flex flex-col h-full" data-testid="portfolio-heatmap">
      <div className="panel-header">Portfolio Heatmap</div>
      <div ref={containerRef} className="flex-1 relative min-h-[180px]">
        {positions.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--color-text-muted)]">
            No positions yet — buy something to see it here.
          </div>
        ) : (
          <svg
            width={size.width}
            height={size.height}
            className="absolute inset-0"
          >
            {cells.map((cell) => {
              const position = positions.find((p) => p.ticker === cell.key);
              if (!position) return null;
              const fill = pnlColor(position.unrealized_pl_percent);
              return (
                <g key={cell.key} data-testid={`heatmap-tile-${cell.key}`}>
                  <rect
                    x={cell.x}
                    y={cell.y}
                    width={cell.width - 1}
                    height={cell.height - 1}
                    fill={fill}
                    stroke="var(--color-bg-base)"
                    strokeWidth={1}
                    rx={3}
                  />
                  {cell.width > 50 && cell.height > 28 ? (
                    <>
                      <text
                        x={cell.x + 6}
                        y={cell.y + 16}
                        className="mono"
                        fontSize={11}
                        fontWeight={600}
                        fill="#fff"
                      >
                        {cell.key}
                      </text>
                      <text
                        x={cell.x + 6}
                        y={cell.y + 30}
                        className="mono"
                        fontSize={10}
                        fill="rgba(255,255,255,0.85)"
                      >
                        {formatPercent(position.unrealized_pl_percent)}
                      </text>
                    </>
                  ) : null}
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}

/** Map a P&L percent to a color: red below, gray near zero, green above. */
function pnlColor(pct: number): string {
  if (Number.isNaN(pct)) return "#3a3f55";
  // Saturate beyond +/- 5% to keep extremes from washing out the gradient.
  const clamped = Math.max(-5, Math.min(5, pct));
  const t = (clamped + 5) / 10; // 0 → red, 1 → green
  const r = Math.round(239 + (34 - 239) * t);
  const g = Math.round(68 + (197 - 68) * t);
  const b = Math.round(68 + (94 - 68) * t);
  return `rgb(${r}, ${g}, ${b})`;
}
