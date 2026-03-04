/**
 * SSE streaming chat hook — replaces Vercel AI SDK's useChat.
 * Uses native fetch + ReadableStream for streaming.
 */

import { useState, useCallback, useRef } from "react";

export interface OHLCV {
  Date: string;
  Open: number;
  High: number;
  Low: number;
  Close: number;
  Volume: number;
}

export interface AgentStep {
  id: string;
  tool: string;
  input: Record<string, unknown>;
  status: "running" | "completed";
}

export interface MessageMetadata {
  type: "market" | "technical" | "rag" | "hybrid";
  ticker?: string;
  ohlcv?: OHLCV[];
  current?: number;
  change_pct?: number;
  trend?: string;
  indicators?: Record<string, number | null>;
  signals?: string[];
  steps?: AgentStep[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata?: MessageMetadata;
}

export function useSSEChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (input: string) => {
      setIsLoading(true);
      abortRef.current = new AbortController();

      // Immediately append user message
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: input,
      };

      // Append empty assistant message for streaming
      const assistantId = crypto.randomUUID();
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      try {
        const res = await fetch("/api/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: input,
            history: messages.slice(-10).map((m) => ({
              role: m.role,
              content: m.content,
            })),
          }),
          signal: abortRef.current.signal,
        });

        if (!res.ok) {
          throw new Error(`API error: ${res.status}`);
        }

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // Keep incomplete line in buffer

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;

            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === "token") {
                // Stream text token
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: m.content + data.token }
                      : m
                  )
                );
              } else if (data.type === "metadata") {
                // Structured metadata (market data, steps, etc.)
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          metadata: {
                            ...m.metadata,
                            ...data.payload,
                          } as MessageMetadata,
                        }
                      : m
                  )
                );
              } else if (data.type === "error") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          content:
                            m.content +
                            `\n\n> 错误: ${data.message}`,
                        }
                      : m
                  )
                );
              }
            } catch {
              // Skip malformed JSON lines
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: m.content || "抱歉，请求出现错误，请稍后重试。",
                  }
                : m
            )
          );
        }
      } finally {
        setIsLoading(false);
      }
    },
    [messages]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
  }, []);

  return { messages, isLoading, send, stop };
}
