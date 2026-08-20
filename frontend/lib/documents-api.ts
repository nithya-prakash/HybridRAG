import { API_BASE_URL, ApiError, parseErrorDetail } from "./api";

export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

export interface DocumentRecord {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: DocumentStatus;
  version: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

async function documentsFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
  });
  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res));
  }
  return res;
}

export async function uploadDocument(
  file: File,
  existingDocumentId?: string
): Promise<DocumentRecord> {
  const formData = new FormData();
  formData.append("file", file);
  if (existingDocumentId) {
    formData.append("document_id", existingDocumentId);
  }
  const res = await documentsFetch("/documents/upload", {
    method: "POST",
    body: formData,
  });
  return res.json();
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  const res = await documentsFetch("/documents", { cache: "no-store" });
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  await documentsFetch(`/documents/${id}`, { method: "DELETE" });
}
