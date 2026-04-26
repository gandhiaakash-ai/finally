"use client";

import type { ConnectionStatus } from "@/hooks/useLivePrices";

type Props = {
  status: ConnectionStatus;
  className?: string;
};

const COPY: Record<ConnectionStatus, string> = {
  connected: "Live",
  reconnecting: "Reconnecting",
  disconnected: "Disconnected",
};

const COLOR: Record<ConnectionStatus, string> = {
  connected: "bg-[var(--color-tick-up)]",
  reconnecting: "bg-[var(--color-accent-yellow)]",
  disconnected: "bg-[var(--color-tick-down)]",
};

/**
 * Small status pill: colored dot + label. Pulses when actively connected.
 */
export function ConnectionDot({ status, className = "" }: Props) {
  const pulse = status === "connected" ? "animate-pulse" : "";
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] ${className}`}
      aria-live="polite"
      data-testid="connection-status"
      data-status={status}
    >
      <span className={`h-2 w-2 rounded-full ${COLOR[status]} ${pulse}`} />
      {COPY[status]}
    </span>
  );
}
