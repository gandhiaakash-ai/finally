"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";
import type { PriceUpdate } from "@/types/api";

type Props = {
  ticker: string | null;
  history: number[];
  latest: PriceUpdate | undefined;
  /**
   * When the page just loaded we don't have absolute timestamps for older
   * sparkline points; we use page-load epoch as the starting time and step
   * by `tickIntervalMs` per point. This keeps the x-axis monotonic.
   */
  tickIntervalMs?: number;
};

/**
 * Detailed price chart for the currently selected ticker. Uses lightweight
 * charts (canvas, ~60kb) and updates in place as new SSE ticks arrive.
 */
export function MainChart({
  ticker,
  history,
  latest,
  tickIntervalMs = 500,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  // Track the ticker the chart was last drawn for, so changes reset state.
  const drawnTickerRef = useRef<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: "#9aa3b8",
        fontFamily: "JetBrains Mono, ui-monospace, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#262b3d" },
        horzLines: { color: "#262b3d" },
      },
      timeScale: {
        borderColor: "#353a55",
        timeVisible: true,
        secondsVisible: true,
      },
      rightPriceScale: {
        borderColor: "#353a55",
      },
      crosshair: {
        mode: 0,
      },
    });

    const series = chart.addSeries(LineSeries, {
      color: "#209dd7",
      lineWidth: 2,
      priceLineColor: "#ecad0a",
      priceLineStyle: 2,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      drawnTickerRef.current = null;
    };
  }, []);

  // Reseed series when ticker or initial history changes.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    if (!ticker) {
      series.setData([]);
      drawnTickerRef.current = null;
      return;
    }

    if (drawnTickerRef.current !== ticker) {
      const baseline = Math.floor(Date.now() / 1000) - history.length;
      const data: LineData<UTCTimestamp>[] = history.map((value, i) => ({
        time: ((baseline + i) as unknown) as UTCTimestamp,
        value,
      }));
      series.setData(data);
      chartRef.current?.timeScale().fitContent();
      drawnTickerRef.current = ticker;
    }
  }, [ticker, history]);

  // Live updates: append latest tick.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !ticker || !latest) return;
    if (drawnTickerRef.current !== ticker) return;

    series.update({
      time: (Math.floor(latest.timestamp) as unknown) as UTCTimestamp,
      value: latest.price,
    });
    void tickIntervalMs;
  }, [latest, ticker, tickIntervalMs]);

  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="mono text-[var(--color-text-primary)] text-base normal-case tracking-normal">
          {ticker ?? "—"}
        </span>
        <span className="mono">
          {latest ? latest.price.toFixed(2) : ""}
        </span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-[280px]" />
    </div>
  );
}
