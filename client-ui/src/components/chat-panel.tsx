"use client";

import { useMemo, useState } from "react";

import type { ChatMessage, IncidentChatResponse } from "@/lib/types";

type ChatPanelProps = {
  title: string;
  description: string;
  endpoint: string;
  extraBody?: Record<string, unknown>;
  suggestedPrompts?: string[];
};

export function ChatPanel({
  title,
  description,
  endpoint,
  extraBody,
  suggestedPrompts = [],
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const canSubmit = useMemo(
    () => input.trim().length > 0 && !isSubmitting,
    [input, isSubmitting],
  );

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
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          messages: nextMessages,
          ...extraBody,
        }),
      });

      const payload = (await response.json()) as
        | IncidentChatResponse
        | { error?: { message?: string } };

      if (!response.ok || !("answer" in payload)) {
        throw new Error(
          payload && "error" in payload && payload.error?.message
            ? payload.error.message
            : "Chat request failed.",
        );
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
      setMessages(messages);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="ops-sheet overflow-hidden rounded-[28px]">
      <div className="border-b border-[rgba(24,24,27,0.08)] px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Conversational incident analysis
            </p>
            <h2 className="mt-2 text-xl font-semibold text-[#171717]">{title}</h2>
            <p className="mt-1.5 text-sm leading-6 text-[#5f6470]">{description}</p>
          </div>
          <button
            type="button"
            onClick={() => setIsExpanded((current) => !current)}
            className="ops-button-secondary rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-wide"
            aria-pressed={isExpanded}
          >
            {isExpanded ? "Compact" : "Expand"}
          </button>
        </div>
        <div className="mt-4 h-px w-36 bg-[linear-gradient(90deg,#171717,rgba(23,23,23,0.08))]" />
      </div>

      <div
        className={`space-y-4 overflow-y-auto px-6 py-5 ${
          isExpanded ? "max-h-[36rem]" : "max-h-[18rem]"
        }`}
      >
        {suggestedPrompts.length > 0 && messages.length === 0 ? (
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#8f735c]">
              Suggested prompts
            </p>
            <div className="flex flex-wrap gap-2">
              {suggestedPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => void submitMessage(prompt)}
                  className="ops-button-secondary rounded-full px-3.5 py-1.5 text-sm transition hover:border-[rgba(255,106,61,0.18)]"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.length === 0 ? (
          <div className="ops-soft-block rounded-[20px] px-4 py-6 text-sm leading-6 text-[#5f6470]">
            Ask the incident assistant for summaries, likely causes, impacted
            services, or next debugging steps.
          </div>
        ) : null}

        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}-${message.content.slice(0, 12)}`}
            className={`max-w-[92%] rounded-[22px] px-4 py-3 text-sm leading-6 ${
              message.role === "user"
                ? "ml-auto bg-[#171717] text-white"
                : "bg-white/52 text-[#171717] border border-[rgba(24,24,27,0.08)]"
            }`}
          >
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide opacity-70">
              {message.role === "user" ? "You" : "Incident agent"}
            </p>
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
        ))}
      </div>

      <div className="border-t border-[rgba(24,24,27,0.08)] px-6 py-5">
        {error ? (
          <p className="mb-3 rounded-xl border border-[rgba(255,106,61,0.2)] bg-[rgba(255,106,61,0.08)] px-3 py-2 text-sm text-[#9b3719]">
            {error}
          </p>
        ) : null}

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
            placeholder="Ask about this incident or the current incident set..."
            className="vault-input min-h-28 w-full rounded-[20px] bg-white/62 px-4 py-3 text-sm text-[#171717] transition"
          />
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs leading-5 text-[#5f6470]">
              Chat stays grounded in incident data already stored by the
              platform.
            </p>
            <button
              type="submit"
              disabled={!canSubmit}
              className="ops-button rounded-[18px] px-4 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
            >
              {isSubmitting ? "Thinking..." : "Send"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
