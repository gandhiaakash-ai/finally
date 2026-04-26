"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  AreaSeries,
  type IChartApi,
  type ISeriesApi,
  type AreaData,
  type UTCTimestamp,
} from "lightweight-charts";
import { formatUsdCompact } from "@/lib/format";
import type { PortfolioSnapshot } from "@/types/api";

type Props = {
  snapshots: PortfolioSnapshot[];
};

/**
 * Total portfolio value over time. Area chart in accent yellow → background.
 * Re-seeds the series whenever the snapshot list changes.
 */
export function PnlChart({ snapshots }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: "#9aa3b8",
        fontFamily: "JetBrains Mono, ui-monospace, monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "transparent" },
        horzLines: { color: "#262b3d" },
      },
      timeScale: {
        borderColor: "#353a55",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: { borderColor: "#353a55" },
    });
    const series = chart.addSeries(AreaSeries, {
      lineColor: "#ecad0a",
      topColor: "rgba(236, 173, 10, 0.25)",
      bottomColor: "rgba(236, 173, 10, 0.02)",
      lineWidth: 2,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const data: AreaData<UTCTimestamp>[] = snapshots.map((s) => ({
      time: ((Math.floor(new Date(s.recorded_at).getTime() / 1000)) as unknown) as UTCTimestamp,
      value: s.total_value,
    }));
    series.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [snapshots]);

  const latest = snapshots[snapshots.length - 1]?.total_value;

  return (
    <div className="panel flex flex-col h-full" data-testid="pnl-chart">
      <div className="panel-header">
        <span>P&amp;L</span>
        <span className="mono normal-case tracking-normal text-[var(--color-text-primary)]">
          {latest != null ? formatUsdCompact(latest) : "—"}
        </span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-[180px]" />
    </div>
  );
}
