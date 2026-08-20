"use client";

import { useCallback, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { ApiError } from "@/lib/api";
import { uploadDocument } from "@/lib/documents-api";

const ACCEPTED_EXTENSIONS = ".pdf,.docx,.txt,.md";

export function DocumentUpload({ onUploaded }: { onUploaded: () => void }) {
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        await uploadDocument(file);
        onUploaded();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [onUploaded]
  );

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void upload(file);
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void upload(file);
    e.target.value = "";
  }

  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragActive
            ? "border-slate-400 bg-slate-900/50"
            : "border-slate-700 hover:border-slate-600"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          className="hidden"
          onChange={handleFileChange}
          disabled={uploading}
        />
        <p className="text-sm text-slate-300">
          {uploading ? "Uploading…" : "Drag and drop a file here, or click to browse"}
        </p>
        <p className="mt-1 text-xs text-slate-500">PDF, DOCX, TXT, or Markdown</p>
      </div>
      {error && (
        <p className="rounded-md border border-red-800 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}
    </div>
  );
}
