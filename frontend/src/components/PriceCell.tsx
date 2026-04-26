"use client";

import { useEffect, useRef, useState } from "react";
import { formatNumber } from "@/lib/format";

type Props = {
  price: number | null | undefined;
  /** Optional explicit precision; defaults to 2dp. */
  fractionDigits?: number;
  className?: string;
  "data-testid"?: string;
};

/**
 * Numeric price cell that briefly flashes green/red when the price changes.
 * Flash class is applied for ~600ms (matches CSS animation in globals.css).
 */
export function PriceCell({
  price,
  fractionDigits = 2,
  className = "",
  ...rest
}: Props) {
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  const prevRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (price == null) return;
    const prev = prevRef.current;
    if (prev != null && price !== prev) {
      const direction = price > prev ? "up" : "down";
      setFlash(direction);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setFlash(null), 600);
    }
    prevRef.current = price;
  }, [price]);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  const display =
    price == null
      ? "—"
      : price.toLocaleString("en-US", {
          minimumFractionDigits: fractionDigits,
          maximumFractionDigits: fractionDigits,
        });

  const flashClass =
    flash === "up" ? "flash-up" : flash === "down" ? "flash-down" : "";

  return (
    <span
      data-testid={rest["data-testid"]}
      className={`mono inline-block px-1 rounded-sm transition-colors ${flashClass} ${className}`}
    >
      {display}
    </span>
  );
}

// Re-export formatter for callers that need the same precision elsewhere.
export { formatNumber };
