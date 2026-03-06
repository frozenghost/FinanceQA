/**
 * Chat history hook
 */

import { useState, useEffect, useCallback } from "react";
import { chatStorage, type Conversation } from "../services/chatStorage";
import type { Message } from "./useSSEChat";

export function useChatHistory() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Init DB and load conversation list
  useEffect(() => {
    const init = async () => {
      try {
        await chatStorage.init();
        await loadConversations();
      } catch (error) {
        console.error("Failed to initialize chat storage:", error);
      } finally {
        setIsLoading(false);
      }
    };
    init();
  }, []);

  const loadConversations = useCallback(async () => {
    try {
      const convs = await chatStorage.getConversations();
      setConversations(convs);
    } catch (error) {
      console.error("Failed to load conversations:", error);
    }
  }, []);

  const loadMessages = useCallback(
    async (conversationId: string): Promise<Message[]> => {
      try {
        return await chatStorage.getMessages(conversationId);
      } catch (error) {
        console.error("Failed to load messages:", error);
        return [];
      }
    },
    []
  );

  const deleteConversation = useCallback(
    async (conversationId: string) => {
      try {
        await chatStorage.deleteConversation(conversationId);
        await loadConversations();
      } catch (error) {
        console.error("Failed to delete conversation:", error);
      }
    },
    [loadConversations]
  );

  const clearAll = useCallback(async () => {
    try {
      await chatStorage.clearAll();
      setConversations([]);
    } catch (error) {
      console.error("Failed to clear all conversations:", error);
    }
  }, []);

  return {
    conversations,
    isLoading,
    loadConversations,
    loadMessages,
    deleteConversation,
    clearAll,
  };
}
