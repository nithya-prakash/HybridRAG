import { API_BASE_URL, ApiError, parseErrorDetail } from "./api";

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  marker: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number | null;
  excerpt: string;
}

export type MessageRole = "user" | "assistant";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  rewritten_query: string | null;
  citations: Citation[];
  created_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

async function conversationsFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, credentials: "include" });
  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res));
  }
  return res;
}

export async function listConversations(): Promise<Conversation[]> {
  const res = await conversationsFetch("/conversations", { cache: "no-store" });
  return res.json();
}

export async function createConversation(): Promise<Conversation> {
  const res = await conversationsFetch("/conversations", { method: "POST" });
  return res.json();
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await conversationsFetch(`/conversations/${id}`, { cache: "no-store" });
  return res.json();
}

export interface CitationsPayload {
  message_id: string;
  rewritten_query: string;
  citations: Citation[];
}

export interface StreamCallbacks {
  onToken: (delta: string) => void;
  onCitations: (payload: CitationsPayload) => void;
  onError: (detail: string) => void;
  onDone: () => void;
}

/**
 * POST /conversations/{id}/messages streams Server-Sent Events over a
 * chunked response body. `EventSource` can't be used here — it's GET-only
 * and can't carry a JSON request body — so this reads the raw stream via
 * `fetch` + a `ReadableStream` reader instead, buffering until each
 * `\n\n`-terminated SSE record is complete before parsing it.
 */
export async function streamMessage(
  conversationId: string,
  content: string,
  callbacks: StreamCallbacks
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/conversations/${conversationId}/messages`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
  } catch {
    callbacks.onError("Could not reach the server.");
    return;
  }

  if (!res.ok || !res.body) {
    callbacks.onError(await parseErrorDetail(res));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      dispatchSseRecord(buffer.slice(0, boundary), callbacks);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function dispatchSseRecord(record: string, callbacks: StreamCallbacks): void {
  let event = "message";
  let data = "";
  for (const line of record.split("\n")) {
    if (line.startsWith("event:")) event = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data = line.slice("data:".length).trim();
  }
  if (!data) return;

  const parsed = JSON.parse(data);
  switch (event) {
    case "token":
      callbacks.onToken(parsed.delta);
      break;
    case "citations":
      callbacks.onCitations(parsed);
      break;
    case "error":
      callbacks.onError(parsed.detail);
      break;
    case "done":
      callbacks.onDone();
      break;
  }
}
