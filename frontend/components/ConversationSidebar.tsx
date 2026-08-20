"use client";

import type { Conversation } from "@/lib/conversations-api";

export function ConversationSidebar({
  conversations,
  selectedId,
  onSelect,
  onNew,
  creating,
}: {
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  creating: boolean;
}) {
  return (
    <aside className="w-64 shrink-0 space-y-3">
      <button
        onClick={onNew}
        disabled={creating}
        className="w-full rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:border-slate-500 hover:text-white disabled:opacity-50"
      >
        {creating ? "Starting…" : "+ New conversation"}
      </button>
      <ul className="space-y-1">
        {conversations.length === 0 && (
          <li className="px-2 py-4 text-sm text-slate-500">No conversations yet.</li>
        )}
        {conversations.map((c) => (
          <li key={c.id}>
            <button
              onClick={() => onSelect(c.id)}
              className={`w-full truncate rounded-md px-3 py-2 text-left text-sm ${
                c.id === selectedId
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
              }`}
            >
              {c.title ?? "New conversation"}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
