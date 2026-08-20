"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { DocumentList } from "@/components/DocumentList";
import { DocumentUpload } from "@/components/DocumentUpload";
import { useAuth } from "@/lib/auth-context";

export default function DocumentsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [refreshSignal, setRefreshSignal] = useState(0);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return <p className="text-slate-400">Loading…</p>;
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Documents</h1>
        <p className="mt-1 text-slate-400">
          Upload PDF, DOCX, TXT, or Markdown files. Once a document reaches the ready
          state, ask questions about it in Chat.
        </p>
      </div>
      <DocumentUpload onUploaded={() => setRefreshSignal((n) => n + 1)} />
      <DocumentList refreshSignal={refreshSignal} />
    </div>
  );
}
