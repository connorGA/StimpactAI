"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import type { ChatMessage, IncidentChatResponse } from "@/lib/types";

function parseJsonSafe(raw: string): unknown {
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return null;
  }
}

function messageFromChatErrorPayload(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const object = payload as Record<string, unknown>;
  if (typeof object.error === "object" && object.error !== null) {
    const errorObject = object.error as Record<string, unknown>;
    if (typeof errorObject.message === "string") {
      return errorObject.message;
    }
  }
  const detail = object.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (typeof first === "object" && first !== null) {
      const row = first as Record<string, unknown>;
      if (typeof row.msg === "string") {
        return row.msg;
      }
    }
    if (typeof first === "string") {
      return first;
    }
  }
  return null;
}

function isIncidentChatResponse(payload: unknown): payload is IncidentChatResponse {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "answer" in payload &&
    typeof (payload as IncidentChatResponse).answer === "string"
  );
}

type ChatPanelProps = {
  title: string;
  description: string;
  endpoint: string;
  extraBody?: Record<string, unknown>;
  suggestedPrompts?: string[];
  /** Match dashboard-style dark surfaces (e.g. incident detail). */
  variant?: "light" | "dark";
  showExpandToggle?: boolean;
  showSuggestedPrompts?: boolean;
  showAssistantIcon?: boolean;
  /** Minimal header (title + optional icon only). */
  compact?: boolean;
  /** Shown as the first assistant line before the user sends anything (display-only, not sent to the API). */
  openingAssistantMessage?: string;
  className?: string;
};

const darkShell =
  "flex min-h-0 flex-col overflow-hidden rounded-2xl border border-white/[0.06] bg-[#0d1119] text-white";

export function ChatPanel({
  title,
  description,
  endpoint,
  extraBody,
  suggestedPrompts = [],
  variant = "light",
  showExpandToggle = true,
  showSuggestedPrompts = true,
  showAssistantIcon = false,
  compact = false,
  openingAssistantMessage = "How can I help?",
  className = "",
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const canSubmit = useMemo(
    () => input.trim().length > 0 && !isSubmitting,
    [input, isSubmitting],
  );

  const hasInteracted = messages.length > 0 || isSubmitting || error !== null;
  useEffect(() => {
    if (!hasInteracted) {
      return;
    }
    const container = scrollRef.current;
    if (!container) {
      return;
    }
    container.scrollTop = container.scrollHeight;
  }, [messages, isSubmitting, error, hasInteracted]);

  async function submitMessage(content: string) {
    const normalized = content.trim();
    if (!normalized || isSubmitting) {
      return;
    }

    const nextMessages: ChatMessage[] = [
      ...messages,
      { role: "user", content: normalized },
    ];

    setMessages(nextMessages);
    setInput("");
    setError(null);
    setIsSubmitting(true);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          messages: nextMessages,
          ...extraBody,
        }),
      });

      const raw = await response.text();
      const payload = parseJsonSafe(raw);

      if (!response.ok) {
        const fromBody =
          messageFromChatErrorPayload(payload) ??
          (raw.length > 0 && raw.length < 400 && !raw.trimStart().startsWith("<")
            ? raw
            : null);
        throw new Error(fromBody ?? `Chat request failed (${response.status}).`);
      }

      if (!isIncidentChatResponse(payload)) {
        const fromBody = messageFromChatErrorPayload(payload);
        throw new Error(fromBody ?? "Chat response was missing an answer.");
      }

      setMessages([
        ...nextMessages,
        { role: "assistant", content: payload.answer },
      ]);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unexpected chat error.",
      );
      setMessages((previous) =>
        previous.length > 0 && previous[previous.length - 1]?.role === "user"
          ? previous.slice(0, -1)
          : previous,
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage(input);
    }
  }

  const dark = variant === "dark";

  return (
    <section
      className={[
        dark ? darkShell : "ops-sheet flex min-h-[22rem] flex-col overflow-hidden rounded-[28px]",
        compact && dark ? "min-h-[28rem] lg:h-full lg:min-h-[32rem]" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {dark ? (
        <div className="h-[2px] w-full shrink-0 bg-[#ff6a3d]/65" aria-hidden />
      ) : null}
      <div
        className={
          dark
            ? compact
              ? "shrink-0 px-5 py-3 sm:px-6"
              : "shrink-0 px-5 py-4 sm:px-6 sm:py-5"
            : "shrink-0 border-b border-[rgba(24,24,27,0.08)] px-6 py-5"
        }
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            {compact && dark ? (
              <div className="flex items-center gap-2">
                {showAssistantIcon ? (
                  <span
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.05] text-[#c4b5fd]"
                    aria-hidden="true"
                  >
                    <AssistantIcon />
                  </span>
                ) : null}
                <h2 className="text-base font-semibold text-white/90">{title}</h2>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  {showAssistantIcon ? (
                    <span
                      className={
                        dark
                          ? "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.05] text-[#c4b5fd]"
                          : "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[rgba(24,24,27,0.08)] bg-white text-[#171717]"
                      }
                      aria-hidden="true"
                    >
                      <AssistantIcon />
                    </span>
                  ) : null}
                  <p
                    className={
                      dark
                        ? "text-[11px] font-semibold uppercase tracking-wider text-white/40"
                        : "ops-kicker text-[11px] font-semibold uppercase"
                    }
                  >
                    Conversational incident analysis
                  </p>
                </div>
                <h2
                  className={
                    dark
                      ? "mt-2 text-lg font-semibold text-white/90 sm:text-xl"
                      : "mt-2 text-xl font-semibold text-[#171717]"
                  }
                >
                  {title}
                </h2>
                <p
                  className={
                    dark
                      ? "mt-1.5 text-sm leading-6 text-white/50"
                      : "mt-1.5 text-sm leading-6 text-[#5f6470]"
                  }
                >
                  {description}
                </p>
              </>
            )}
          </div>
          {showExpandToggle ? (
            <button
              type="button"
              onClick={() => setIsExpanded((current) => !current)}
              className={
                dark
                  ? "shrink-0 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-white/80 transition hover:bg-white/[0.1]"
                  : "ops-button-secondary rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-wide"
              }
              aria-pressed={isExpanded}
            >
              {isExpanded ? "Compact" : "Expand"}
            </button>
          ) : null}
        </div>
        {compact && dark ? null : (
          <div
            className={
              dark
                ? "mt-4 h-px w-36 bg-gradient-to-r from-[#ff6a3d]/50 to-transparent"
                : "mt-4 h-px w-36 bg-[linear-gradient(90deg,#171717,rgba(23,23,23,0.08))]"
            }
          />
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div
          className={
            dark
              ? "mx-3 mb-2 mt-2 flex min-h-0 flex-1 flex-col sm:mx-4"
              : "flex min-h-0 flex-1 flex-col"
          }
        >
          <div
            className={
              dark
                ? "flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-black/25"
                : "flex min-h-0 flex-1 flex-col"
            }
          >
            <div
              ref={scrollRef}
              className={
                dark
                  ? `flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto overflow-x-hidden overscroll-y-contain p-3 touch-pan-y${
                      isExpanded ? " max-h-[36rem]" : ""
                    }`
                  : `touch-pan-y space-y-4 overflow-y-auto overflow-x-hidden overscroll-y-contain px-5 py-4 sm:px-6 sm:py-5${
                      isExpanded ? " max-h-[36rem]" : " max-h-[18rem]"
                    }`
              }
            >
          {messages.length === 0 && openingAssistantMessage ? (
            <div
              className={
                dark
                  ? "chat-bubble-assistant self-start max-w-[min(17rem,78%)] rounded-xl px-3 py-2 text-xs leading-relaxed text-white/95"
                  : "max-w-[92%] rounded-[22px] border border-[rgba(24,24,27,0.08)] bg-white/52 px-4 py-3 text-sm leading-6 text-[#171717]"
              }
            >
              <p
                className={
                  dark
                    ? "mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-white/55"
                    : "mb-1 text-[11px] font-semibold uppercase tracking-wide text-[#8f735c]"
                }
              >
                Incident agent
              </p>
              <p>{openingAssistantMessage}</p>
            </div>
          ) : null}

          {showSuggestedPrompts && suggestedPrompts.length > 0 && messages.length === 0 ? (
            <div className="space-y-3">
              <p
                className={
                  dark
                    ? "text-xs font-semibold uppercase tracking-wide text-white/40"
                    : "text-xs font-semibold uppercase tracking-wide text-[#8f735c]"
                }
              >
                Suggested prompts
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestedPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => void submitMessage(prompt)}
                    className={
                      dark
                        ? "rounded-full border border-white/[0.08] bg-white/[0.04] px-3.5 py-1.5 text-sm text-white/85 transition hover:border-white/15 hover:bg-white/[0.07]"
                        : "ops-button-secondary rounded-full px-3.5 py-1.5 text-sm transition hover:border-[rgba(255,106,61,0.18)]"
                    }
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {messages.map((message, index) => (
            <div
              key={`${message.role}-${index}-${message.content.slice(0, 12)}`}
              className={
                message.role === "user"
                  ? dark
                    ? "ml-auto max-w-[min(17rem,78%)] self-end rounded-xl border border-[#ff6a3d]/35 bg-[#ff6a3d]/12 px-3 py-2 text-xs leading-relaxed text-white"
                    : "ml-auto max-w-[92%] rounded-[22px] bg-[#171717] px-4 py-3 text-sm leading-6 text-white"
                  : dark
                    ? "chat-bubble-assistant self-start max-w-[min(17rem,78%)] rounded-xl px-3 py-2 text-xs leading-relaxed text-white/95"
                    : "max-w-[92%] rounded-[22px] border border-[rgba(24,24,27,0.08)] bg-white/52 px-4 py-3 text-sm leading-6 text-[#171717]"
              }
            >
              <p
                className={
                  dark
                    ? "mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-white/55"
                    : "mb-1 text-[11px] font-semibold uppercase tracking-wide opacity-70"
                }
              >
                {message.role === "user" ? "You" : "Incident agent"}
              </p>
              <p className="whitespace-pre-wrap">{message.content}</p>
            </div>
          ))}

          {isSubmitting ? (
            <div
              className={
                dark
                  ? "chat-bubble-assistant self-start max-w-[min(17rem,78%)] rounded-xl px-3 py-2"
                  : "max-w-[92%] rounded-[22px] border border-[rgba(24,24,27,0.08)] bg-white/52 px-4 py-3"
              }
              aria-live="polite"
              aria-busy="true"
            >
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-white/55">
                Incident agent
              </p>
              <div className="flex items-center gap-1.5" role="status">
                <span className="sr-only">Thinking</span>
                <span
                  className="chat-typing-dot h-1.5 w-1.5 rounded-full bg-[#c4b5fd]"
                  style={{ animationDelay: "0ms" }}
                />
                <span
                  className="chat-typing-dot h-1.5 w-1.5 rounded-full bg-[#c4b5fd]"
                  style={{ animationDelay: "160ms" }}
                />
                <span
                  className="chat-typing-dot h-1.5 w-1.5 rounded-full bg-[#c4b5fd]"
                  style={{ animationDelay: "320ms" }}
                />
              </div>
            </div>
          ) : null}

          <div ref={messagesEndRef} className="h-px w-full shrink-0" aria-hidden="true" />
            </div>
          </div>
        </div>

        <div
          className={
            dark
              ? "mt-auto shrink-0 border-t border-white/[0.06] px-5 py-4 sm:px-6 sm:py-5"
              : "shrink-0 border-t border-[rgba(24,24,27,0.08)] px-6 py-5"
          }
        >
          {error ? (
            <p
              className={
                dark
                  ? "mb-3 rounded-xl border border-[rgba(248,113,113,0.3)] bg-[rgba(248,113,113,0.08)] px-3 py-2 text-sm text-[#fecaca]"
                  : "mb-3 rounded-xl border border-[rgba(255,106,61,0.2)] bg-[rgba(255,106,61,0.08)] px-3 py-2 text-sm text-[#9b3719]"
              }
            >
              {error}
            </p>
          ) : null}

          {dark ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submitMessage(input);
              }}
            >
              <div className="relative">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about this incident or the current incident set..."
                  rows={compact ? 3 : 4}
                  disabled={isSubmitting}
                  className="min-h-[5.5rem] w-full resize-none rounded-xl border border-white/10 bg-black/25 py-3 pl-4 pr-14 text-sm text-white placeholder:text-white/35 outline-none transition focus:border-[#ff6a3d]/45 focus:ring-1 focus:ring-[#ff6a3d]/20 disabled:opacity-60"
                />
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className="absolute right-2.5 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-white/12 bg-white/[0.08] text-white transition hover:border-[#ff6a3d]/40 hover:bg-[#ff6a3d]/15 disabled:cursor-not-allowed disabled:opacity-35"
                  aria-label="Send message"
                >
                  <SendArrowIcon className="h-[18px] w-[18px]" />
                </button>
              </div>
            </form>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void submitMessage(input);
              }}
            >
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about this incident or the current incident set..."
                className="vault-input min-h-28 w-full rounded-[20px] bg-white/62 px-4 py-3 text-sm text-[#171717] transition"
              />
              <div
                className={
                  compact
                    ? "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end"
                    : "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
                }
              >
                {compact ? null : (
                  <p className="text-xs leading-5 text-[#5f6470]">
                    Chat stays grounded in incident data already stored by the
                    platform.
                  </p>
                )}
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className="ops-button rounded-[18px] px-4 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
                >
                  {isSubmitting ? "Thinking..." : "Send"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}

function SendArrowIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <path
        d="M5 12h14m0 0-5-5m5 5-5 5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-white/90"
      />
    </svg>
  );
}

function AssistantIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 3.5v2.2" />
      <rect x="5.5" y="7" width="13" height="10.5" rx="3" />
      <path d="M9.25 21h5.5" />
      <path d="M9 11.25h.01" />
      <path d="M15 11.25h.01" />
      <path d="M9 14.75c.8.6 1.8.9 3 .9s2.2-.3 3-.9" />
    </svg>
  );
}
