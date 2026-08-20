"use client";

import type { Message } from "@/lib/conversations-api";
import { CitationChips } from "./CitationChips";

export function ChatMessages({
  messages,
  streamingContent,
}: {
  messages: Message[];
  streamingContent: string | null;
}) {
  if (messages.length === 0 && streamingContent === null) {
    return (
      <p className="py-8 text-center text-sm text-slate-500">
        Ask a question about your uploaded documents.
      </p>
    );
  }

  return (
    <div className="space-y-4 py-4">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      {streamingContent !== null && (
        <div className="flex justify-start">
          <div className="max-w-2xl rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-100">
            <p className="whitespace-pre-wrap">{streamingContent || "…"}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-2xl rounded-lg border px-4 py-3 text-sm ${
          isUser
            ? "border-sky-800 bg-sky-950/40 text-sky-50"
            : "border-slate-800 bg-slate-900 text-slate-100"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!isUser && <CitationChips citations={message.citations} />}
      </div>
    </div>
  );
}
