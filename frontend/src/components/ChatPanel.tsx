"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type {
  AppliedWatchlistChange,
  ChatResult,
  ExecutedTrade,
} from "@/types/api";

interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  trades?: ExecutedTrade[];
  watchlist_changes?: AppliedWatchlistChange[];
}

type Props = {
  onActions?: () => void;
};

/**
 * Stable id generator. Avoids `localId()` because it is undefined
 * outside secure contexts (e.g. when the app is served from `http://app:8000`
 * during E2E runs in a Docker network — neither HTTPS nor localhost).
 */
let nextLocalId = 0;
const localId = () => `chat-${Date.now()}-${++nextLocalId}`;

/**
 * Conversational sidebar. Posts to /api/chat and renders the assistant's
 * structured response — surfaces auto-executed trades and watchlist changes
 * inline as confirmation chips beneath the message.
 */
export function ChatPanel({ onActions }: Props) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Use scrollTop for environments (jsdom, older browsers) without scrollTo.
    el.scrollTop = el.scrollHeight;
  }, [turns, busy]);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    const userTurn: ChatTurn = {
      id: localId(),
      role: "user",
      content: text,
    };
    setTurns((t) => [...t, userTurn]);
    setDraft("");
    try {
      const res: ChatResult = await api.chat({ message: text });
      setTurns((t) => [
        ...t,
        {
          id: localId(),
          role: "assistant",
          content: res.message,
          trades: res.trades,
          watchlist_changes: res.watchlist_changes,
        },
      ]);
      const hadActions =
        (res.trades?.length ?? 0) > 0 ||
        (res.watchlist_changes?.length ?? 0) > 0;
      if (hadActions) onActions?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel flex flex-col h-full" data-testid="chat-panel">
      <div className="panel-header">
        <span>AI Assistant</span>
        <span className="text-[var(--color-text-muted)] normal-case tracking-normal">
          {turns.length} msgs
        </span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3">
        {turns.length === 0 ? (
          <EmptyState />
        ) : (
          turns.map((turn) => <ChatTurnView key={turn.id} turn={turn} />)
        )}
        {busy ? (
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent-blue)] animate-pulse" />
            FinAlly is thinking…
          </div>
        ) : null}
      </div>

      <form
        onSubmit={send}
        className="flex items-center gap-2 border-t border-[var(--color-border-subtle)] p-2"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask FinAlly to analyze or trade..."
          data-testid="chat-input"
          className="flex-1 bg-[var(--color-bg-base)] border border-[var(--color-border-subtle)] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[var(--color-accent-blue)]"
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          data-testid="chat-send-button"
          className="text-xs uppercase tracking-wider px-3 py-1.5 rounded bg-[var(--color-accent-purple)] text-white disabled:opacity-40 hover:brightness-110 transition"
        >
          Send
        </button>
      </form>
      {error ? (
        <div className="px-3 pb-2 text-xs text-[var(--color-tick-down)]">
          {error}
        </div>
      ) : null}
    </div>
  );
}

function EmptyState() {
  const prompts = [
    "Summarize my portfolio risk.",
    "Buy 5 shares of NVDA.",
    "Add PYPL to my watchlist.",
  ];
  return (
    <div className="text-xs text-[var(--color-text-muted)] space-y-2">
      <p>Ask anything — FinAlly can analyze positions and execute trades.</p>
      <ul className="space-y-1">
        {prompts.map((p) => (
          <li
            key={p}
            className="font-mono text-[var(--color-text-secondary)] before:content-['›'] before:mr-2 before:text-[var(--color-accent-yellow)]"
          >
            {p}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChatTurnView({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";
  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
      data-testid={`chat-message-${turn.role}`}
      data-chat-message="true"
    >
      <div
        data-testid="chat-message"
        className={`max-w-[90%] rounded px-3 py-2 text-sm ${
          isUser
            ? "bg-[var(--color-accent-blue)]/15 border border-[var(--color-accent-blue)]/40 text-[var(--color-text-primary)]"
            : "bg-[var(--color-bg-elevated)] border border-[var(--color-border-subtle)] text-[var(--color-text-primary)]"
        }`}
      >
        <div className="whitespace-pre-wrap leading-relaxed">{turn.content}</div>
        {turn.trades && turn.trades.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {turn.trades.map((t, i) => (
              <ActionChip
                key={`t-${i}`}
                ok={t.status === "filled"}
                label={
                  t.status === "filled"
                    ? `${t.side === "buy" ? "Bought" : "Sold"} ${t.quantity} ${t.ticker}${
                        t.price != null ? ` @ ${formatUsd(t.price)}` : ""
                      }`
                    : `Failed ${t.side} ${t.ticker}: ${t.error ?? "unknown error"}`
                }
              />
            ))}
          </div>
        ) : null}
        {turn.watchlist_changes && turn.watchlist_changes.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {turn.watchlist_changes.map((w, i) => (
              <ActionChip
                key={`w-${i}`}
                ok={w.status === "applied"}
                label={
                  w.status === "applied"
                    ? `${w.action === "add" ? "+" : "−"} ${w.ticker} watchlist`
                    : `Watchlist ${w.action} ${w.ticker} failed: ${w.error ?? ""}`
                }
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ActionChip({ ok, label }: { ok: boolean; label: string }) {
  const cls = ok
    ? "bg-[var(--color-tick-up)]/15 text-[var(--color-tick-up)] border-[var(--color-tick-up)]/40"
    : "bg-[var(--color-tick-down)]/15 text-[var(--color-tick-down)] border-[var(--color-tick-down)]/40";
  return (
    <span
      data-testid="chat-action-confirm"
      className={`mono text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 border ${cls}`}
    >
      {label}
    </span>
  );
}
