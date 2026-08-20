"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteDocument, listDocuments, type DocumentRecord, type DocumentStatus } from "@/lib/documents-api";

const POLL_INTERVAL_MS = 2000;
const PENDING_STATUSES: ReadonlySet<DocumentStatus> = new Set(["uploaded", "processing"]);

const STATUS_STYLES: Record<DocumentStatus, string> = {
  uploaded: "border-slate-700 bg-slate-800 text-slate-300",
  processing: "border-amber-800 bg-amber-950/40 text-amber-300",
  ready: "border-emerald-800 bg-emerald-950/40 text-emerald-300",
  failed: "border-red-800 bg-red-950/40 text-red-300",
};

function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function DocumentList({ refreshSignal }: { refreshSignal: number }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const docs = await listDocuments();
    setDocuments(docs);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refreshSignal, refresh]);

  useEffect(() => {
    if (!documents.some((d) => PENDING_STATUSES.has(d.status))) return;
    const timer = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [documents, refresh]);

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) {
    return <p className="text-slate-400">Loading documents…</p>;
  }

  if (documents.length === 0) {
    return <p className="text-slate-400">No documents yet — upload one above.</p>;
  }

  return (
    <ul className="divide-y divide-slate-800 rounded-lg border border-slate-800">
      {documents.map((doc) => (
        <li key={doc.id} className="flex items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{doc.filename}</p>
            <p className="text-xs text-slate-500">
              {doc.file_type.toUpperCase()} · v{doc.version} · {formatSize(doc.file_size_bytes)}
            </p>
            {doc.status === "failed" && doc.error_message && (
              <p className="mt-1 text-xs text-red-400">{doc.error_message}</p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <StatusBadge status={doc.status} />
            <button
              onClick={() => handleDelete(doc.id)}
              disabled={deletingId === doc.id}
              className="text-xs text-slate-500 hover:text-red-400 disabled:opacity-50"
            >
              {deletingId === doc.id ? "Deleting…" : "Delete"}
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
