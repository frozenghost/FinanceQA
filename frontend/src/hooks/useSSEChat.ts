/**
 * SSE streaming chat hook — replaces Vercel AI SDK's useChat.
 * Uses native fetch + ReadableStream for streaming.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { chatStorage } from "../services/chatStorage";

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

export interface CoordinatorData {
  reasoning: string;
  tool_plan: Array<{
    tool: string;
    params: Record<string, unknown>;
    purpose: string;
  }>;
  needs_tools: boolean;
  isComplete?: boolean;
  analysis_start?: string;
  analysis_end?: string;
}

export interface EarningsChartSeries {
  quarterly?: { labels: string[]; revenue: (number | null)[]; earnings: (number | null)[]; eps: (number | null)[]; profit_margin: (number | null)[]; operating_margin: (number | null)[] };
  annual?: { labels: string[]; revenue: (number | null)[]; earnings: (number | null)[]; eps: (number | null)[]; profit_margin: (number | null)[]; operating_margin: (number | null)[] };
  eps_surprise?: { dates: string[]; eps_actual: (number | null)[]; eps_estimate: (number | null)[]; surprise_percent: (number | null)[] };
}

export interface MessageMetadata {
  type: "market" | "technical" | "rag" | "hybrid" | "earnings";
  ticker?: string;
  ohlcv?: OHLCV[];
  current?: number;
  change_pct?: number;
  trend?: string;
  indicators?: Record<string, number | null>;
  signals?: string[];
  steps?: AgentStep[];
  coordinator?: CoordinatorData;
  quarterly?: unknown[];
  annual?: unknown[];
  earnings_surprise?: unknown[];
  earnings_dates?: unknown[];
  chart_series?: EarningsChartSeries;
  no_earnings_in_range?: boolean;
  reason?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata?: MessageMetadata;
}

export interface UseSSEChatOptions {
  skipInitialLoad?: boolean;
}

export function useSSEChat(
  conversationId?: string,
  options?: UseSSEChatOptions
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<
    string | null
  >(conversationId || null);
  const abortRef = useRef<AbortController | null>(null);
  const dbInitialized = useRef(false);
  const skipInitialLoad = options?.skipInitialLoad ?? false;

  useEffect(() => {
    const init = async () => {
      if (!dbInitialized.current) {
        try {
          await chatStorage.init();
          dbInitialized.current = true;
        } catch (error) {
          console.error("Failed to initialize chat storage:", error);
          return;
        }
      }
      if (conversationId) {
        setCurrentConversationId(conversationId);
        if (!skipInitialLoad) {
          const msgs = await chatStorage.getMessages(conversationId);
          setMessages(msgs);
        }
      }
    };
    init();
  }, [conversationId, skipInitialLoad]);

  // Abort SSE on unmount or when conversationId changes (e.g. page/conversation switch)
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    abortRef.current?.abort();
    setIsLoading(false);
  }, [conversationId]);

  const send = useCallback(
    async (input: string) => {
      setIsLoading(true);
      abortRef.current = new AbortController();

      // Create or reuse conversation
      let convId = currentConversationId;
      if (!convId && dbInitialized.current) {
        try {
          convId = await chatStorage.createConversation(input);
          setCurrentConversationId(convId);
        } catch (error) {
          console.error("Failed to create conversation:", error);
        }
      }

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

      if (convId && dbInitialized.current) {
        try {
          await chatStorage.saveMessage(convId, userMsg);
        } catch (error) {
          console.error("Failed to save user message:", error);
        }
      }

      const body: { message: string; history?: Array<{ role: string; content: string }>; thread_id?: string } = {
        message: input,
        history: convId ? [] : messages.slice(-10).map((m) => ({ role: m.role, content: m.content })),
      };
      if (convId) {
        body.thread_id = convId;
      }

      try {
        const res = await fetch("/api/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: abortRef.current.signal,
        });

        if (!res.ok) {
          throw new Error(`API error: ${res.status}`);
        }

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalAssistantMsg: Message = assistantMsg;

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

              if (data.type === "answer") {
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id === assistantId) {
                      finalAssistantMsg = {
                        ...m,
                        content: m.content + data.token,
                      };
                      return finalAssistantMsg;
                    }
                    return m;
                  })
                );
              } else if (data.type === "thinking") {
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id !== assistantId) return m;
                    
                    // Stream tokens for live display (Markdown format)
                    if (data.token !== undefined) {
                      const cur = m.metadata?.coordinator;
                      let currentReasoning = (cur?.reasoning ?? "") + data.token;
                      
                      // Track if we're inside a JSON code block
                      const jsonBlockStart = currentReasoning.indexOf("```json");
                      
                      if (jsonBlockStart !== -1) {
                        // Found ```json, check if the block is closed
                        const afterJsonStart = currentReasoning.substring(jsonBlockStart + 7); // 7 = length of "```json"
                        const jsonBlockEnd = afterJsonStart.indexOf("```");
                        
                        if (jsonBlockEnd === -1) {
                          // JSON block not closed yet, truncate at ```json
                          currentReasoning = currentReasoning.substring(0, jsonBlockStart).trim();
                        } else {
                          // JSON block is closed, remove the entire block
                          const blockEndPos = jsonBlockStart + 7 + jsonBlockEnd + 3; // +3 for closing ```
                          currentReasoning = currentReasoning.substring(0, jsonBlockStart).trim() + 
                                           currentReasoning.substring(blockEndPos).trim();
                        }
                      }
                      
                      finalAssistantMsg = {
                        ...m,
                        metadata: {
                          ...m.metadata,
                          coordinator: {
                            reasoning: currentReasoning,
                            tool_plan: [],
                            needs_tools: false,
                          },
                        } as MessageMetadata,
                      };
                    }
                    return finalAssistantMsg!;
                  })
                );
              } else if (data.type === "thinking_complete") {
                // Coordinator thinking complete - replace with final Markdown and analysis window
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id !== assistantId) return m;
                    const payload = data as { markdown?: string; analysis_start?: string; analysis_end?: string };
                    finalAssistantMsg = {
                      ...m,
                      metadata: {
                        ...m.metadata,
                        coordinator: {
                          reasoning: payload.markdown || "",
                          tool_plan: [],
                          needs_tools: true,
                          isComplete: true,
                          analysis_start: payload.analysis_start,
                          analysis_end: payload.analysis_end,
                        },
                      } as MessageMetadata,
                    };
                    return finalAssistantMsg;
                  })
                );
              } else if (data.type === "metadata") {
                // Structured metadata (market data, steps, etc.)
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id === assistantId) {
                      const prevMeta: Partial<MessageMetadata> = m.metadata ?? {};
                      const payload = (data.payload ?? {}) as {
                        type?: MessageMetadata["type"];
                        steps?: unknown[];
                        [k: string]: unknown;
                      };

                      // Merge type (e.g. market + technical -> hybrid)
                      const types = new Set<string>();
                      if (typeof prevMeta.type === "string") types.add(prevMeta.type);
                      if (typeof payload.type === "string") types.add(payload.type);

                      let mergedType: MessageMetadata["type"] | undefined =
                        payload.type ?? prevMeta.type;

                      if (types.has("market") && types.has("technical")) {
                        mergedType = "hybrid";
                      }

                      // Only update steps if payload has them, preserve existing steps
                      const mergedSteps = payload.steps !== undefined 
                        ? payload.steps 
                        : prevMeta.steps;

                      finalAssistantMsg = {
                        ...m,
                        metadata: {
                          ...prevMeta,
                          ...payload,
                          ...(mergedType ? { type: mergedType } : {}),
                          steps: mergedSteps,
                        } as MessageMetadata,
                      };
                      return finalAssistantMsg;
                    }
                    return m;
                  })
                );
              } else if (data.type === "error") {
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id === assistantId) {
                      finalAssistantMsg = {
                        ...m,
                        content: m.content + `\n\n> Error: ${data.message}`,
                      };
                      return finalAssistantMsg;
                    }
                    return m;
                  })
                );
              }
            } catch {
              // Skip malformed JSON lines
            }
          }
        }

        if (convId && dbInitialized.current) {
          setMessages((prev) => {
            const assistantMsg = prev.find((m) => m.id === assistantId);
            if (assistantMsg?.content) {
              chatStorage.saveMessage(convId, assistantMsg).catch((error) => {
                console.error("Failed to save assistant message:", error);
              });
            }
            return prev;
          });
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: m.content || "Request failed. Please try again later.",
                  }
                : m
            )
          );
        }
      } finally {
        setIsLoading(false);
      }
    },
    [messages, currentConversationId]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setCurrentConversationId(null);
  }, []);

  return {
    messages,
    isLoading,
    send,
    stop,
    clearMessages,
    conversationId: currentConversationId,
  };
}
