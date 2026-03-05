/**
 * IndexedDB 聊天存储服务
 */

import type { Message } from "../hooks/useSSEChat";

const DB_NAME = "FinanceQA";
const DB_VERSION = 1;
const STORE_CONVERSATIONS = "conversations";
const STORE_MESSAGES = "messages";

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
}

export interface StoredMessage extends Message {
  conversationId: string;
  timestamp: number;
}

class ChatStorageService {
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // 对话表
        if (!db.objectStoreNames.contains(STORE_CONVERSATIONS)) {
          const conversationStore = db.createObjectStore(STORE_CONVERSATIONS, {
            keyPath: "id",
          });
          conversationStore.createIndex("updatedAt", "updatedAt", {
            unique: false,
          });
        }

        // 消息表
        if (!db.objectStoreNames.contains(STORE_MESSAGES)) {
          const messageStore = db.createObjectStore(STORE_MESSAGES, {
            keyPath: "id",
          });
          messageStore.createIndex("conversationId", "conversationId", {
            unique: false,
          });
          messageStore.createIndex("timestamp", "timestamp", { unique: false });
        }
      };
    });
  }

  private ensureDB(): IDBDatabase {
    if (!this.db) throw new Error("Database not initialized");
    return this.db;
  }

  // 创建新对话
  async createConversation(firstMessage: string): Promise<string> {
    const db = this.ensureDB();
    const id = crypto.randomUUID();
    const now = Date.now();

    const conversation: Conversation = {
      id,
      title: firstMessage.slice(0, 50),
      createdAt: now,
      updatedAt: now,
      messageCount: 0,
    };

    return new Promise((resolve, reject) => {
      const tx = db.transaction([STORE_CONVERSATIONS], "readwrite");
      const store = tx.objectStore(STORE_CONVERSATIONS);
      const request = store.add(conversation);

      request.onsuccess = () => resolve(id);
      request.onerror = () => reject(request.error);
    });
  }

  // 保存消息
  async saveMessage(
    conversationId: string,
    message: Message
  ): Promise<void> {
    const db = this.ensureDB();
    const storedMessage: StoredMessage = {
      ...message,
      conversationId,
      timestamp: Date.now(),
    };

    return new Promise((resolve, reject) => {
      const tx = db.transaction(
        [STORE_MESSAGES, STORE_CONVERSATIONS],
        "readwrite"
      );

      // 保存消息
      const messageStore = tx.objectStore(STORE_MESSAGES);
      messageStore.put(storedMessage);

      // 更新对话
      const convStore = tx.objectStore(STORE_CONVERSATIONS);
      const getRequest = convStore.get(conversationId);

      getRequest.onsuccess = () => {
        const conv = getRequest.result as Conversation;
        if (conv) {
          conv.updatedAt = Date.now();
          conv.messageCount += 1;
          convStore.put(conv);
        }
      };

      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  // 获取所有对话
  async getConversations(): Promise<Conversation[]> {
    const db = this.ensureDB();

    return new Promise((resolve, reject) => {
      const tx = db.transaction([STORE_CONVERSATIONS], "readonly");
      const store = tx.objectStore(STORE_CONVERSATIONS);
      const index = store.index("updatedAt");
      const request = index.openCursor(null, "prev");

      const conversations: Conversation[] = [];

      request.onsuccess = () => {
        const cursor = request.result;
        if (cursor) {
          conversations.push(cursor.value);
          cursor.continue();
        } else {
          resolve(conversations);
        }
      };

      request.onerror = () => reject(request.error);
    });
  }

  // 获取对话的所有消息
  async getMessages(conversationId: string): Promise<Message[]> {
    const db = this.ensureDB();

    return new Promise((resolve, reject) => {
      const tx = db.transaction([STORE_MESSAGES], "readonly");
      const store = tx.objectStore(STORE_MESSAGES);
      const index = store.index("conversationId");
      const request = index.getAll(conversationId);

      request.onsuccess = () => {
        const messages = (request.result as StoredMessage[])
          .sort((a, b) => a.timestamp - b.timestamp)
          .map(({ conversationId, timestamp, ...msg }) => msg);
        resolve(messages);
      };

      request.onerror = () => reject(request.error);
    });
  }

  // 删除对话
  async deleteConversation(conversationId: string): Promise<void> {
    const db = this.ensureDB();

    return new Promise((resolve, reject) => {
      const tx = db.transaction(
        [STORE_CONVERSATIONS, STORE_MESSAGES],
        "readwrite"
      );

      // 删除对话
      const convStore = tx.objectStore(STORE_CONVERSATIONS);
      convStore.delete(conversationId);

      // 删除所有消息
      const messageStore = tx.objectStore(STORE_MESSAGES);
      const index = messageStore.index("conversationId");
      const request = index.openCursor(IDBKeyRange.only(conversationId));

      request.onsuccess = () => {
        const cursor = request.result;
        if (cursor) {
          cursor.delete();
          cursor.continue();
        }
      };

      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  // 清空所有数据
  async clearAll(): Promise<void> {
    const db = this.ensureDB();

    return new Promise((resolve, reject) => {
      const tx = db.transaction(
        [STORE_CONVERSATIONS, STORE_MESSAGES],
        "readwrite"
      );

      tx.objectStore(STORE_CONVERSATIONS).clear();
      tx.objectStore(STORE_MESSAGES).clear();

      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }
}

export const chatStorage = new ChatStorageService();
