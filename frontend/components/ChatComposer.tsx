"use client";

import { useState, type FormEvent } from "react";

export function ChatComposer({
  onSend,
  disabled,
}: {
  onSend: (content: string) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-800 pt-4">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Ask a question about your documents…"
        disabled={disabled}
        className="flex-1 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-slate-500 focus:outline-none disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-slate-500 hover:text-white disabled:opacity-50"
      >
        Send
      </button>
    </form>
  );
}
