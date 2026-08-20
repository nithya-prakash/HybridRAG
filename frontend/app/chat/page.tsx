"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChatComposer } from "@/components/ChatComposer";
import { ChatMessages } from "@/components/ChatMessages";
import { ConversationSidebar } from "@/components/ConversationSidebar";
import { useAuth } from "@/lib/auth-context";
import {
  createConversation,
  getConversation,
  listConversations,
  streamMessage,
  type CitationsPayload,
  type Conversation,
  type Message,
} from "@/lib/conversations-api";

export default function ChatPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [creating, setCreating] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const streamingTextRef = useRef("");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const refreshConversations = useCallback(async () => {
    const list = await listConversations();
    setConversations(list);
    return list;
  }, []);

  useEffect(() => {
    if (!user) return;
    void refreshConversations().then((list) => {
      if (list.length > 0) setSelectedId((current) => current ?? list[0].id);
    });
  }, [user, refreshConversations]);

  useEffect(() => {
    if (!selectedId) {
      setMessages([]);
      return;
    }
    setLoadingConversation(true);
    getConversation(selectedId)
      .then((detail) => setMessages(detail.messages))
      .finally(() => setLoadingConversation(false));
  }, [selectedId]);

  async function handleNew() {
    setCreating(true);
    try {
      const conversation = await createConversation();
      setConversations((prev) => [conversation, ...prev]);
      setSelectedId(conversation.id);
    } finally {
      setCreating(false);
    }
  }

  async function handleSend(content: string) {
    if (!selectedId) return;
    setError(null);

    const optimisticUser: Message = {
      id: `pending-${Date.now()}`,
      role: "user",
      content,
      rewritten_query: null,
      citations: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);
    streamingTextRef.current = "";
    setStreamingContent("");

    let citationsPayload: CitationsPayload | null = null;

    await streamMessage(selectedId, content, {
      onToken: (delta) => {
        streamingTextRef.current += delta;
        setStreamingContent(streamingTextRef.current);
      },
      onCitations: (payload) => {
        citationsPayload = payload;
      },
      onError: (detail) => {
        setError(detail);
        setStreamingContent(null);
      },
      onDone: () => {
        setMessages((prev) => [
          ...prev,
          {
            id: citationsPayload?.message_id ?? `local-${Date.now()}`,
            role: "assistant",
            content: streamingTextRef.current,
            rewritten_query: citationsPayload?.rewritten_query ?? null,
            citations: citationsPayload?.citations ?? [],
            created_at: new Date().toISOString(),
          },
        ]);
        setStreamingContent(null);
        void refreshConversations();
      },
    });
  }

  if (loading || !user) {
    return <p className="text-slate-400">Loading…</p>;
  }

  return (
    <div className="flex gap-6">
      <ConversationSidebar
        conversations={conversations}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onNew={handleNew}
        creating={creating}
      />
      <div className="min-w-0 flex-1">
        <div>
          <h1 className="text-2xl font-bold">Chat</h1>
          <p className="mt-1 text-slate-400">
            Ask questions about your uploaded documents — answers are grounded in retrieved
            excerpts, with citations back to the source.
          </p>
        </div>
        {error && (
          <p className="mt-3 rounded-md border border-red-800 bg-red-950/40 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        )}
        {!selectedId ? (
          <p className="py-8 text-center text-sm text-slate-500">
            Select a conversation or start a new one.
          </p>
        ) : loadingConversation ? (
          <p className="py-8 text-center text-sm text-slate-500">Loading…</p>
        ) : (
          <ChatMessages messages={messages} streamingContent={streamingContent} />
        )}
        {selectedId && <ChatComposer onSend={handleSend} disabled={streamingContent !== null} />}
      </div>
    </div>
  );
}
