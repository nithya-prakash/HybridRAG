"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return <p className="text-slate-400">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="mt-1 text-slate-400">
          <Link href="/documents" className="underline hover:text-slate-200">
            Upload documents
          </Link>{" "}
          and then ask questions in{" "}
          <Link href="/chat" className="underline hover:text-slate-200">
            Chat
          </Link>
          .
        </p>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
        <p className="text-sm text-slate-400">Signed in as</p>
        <p className="text-lg">{user.email}</p>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm text-slate-500">
          <dt>User ID</dt>
          <dd className="text-slate-400">{user.id}</dd>
          <dt>Created</dt>
          <dd className="text-slate-400">{new Date(user.created_at).toLocaleString()}</dd>
        </dl>
      </div>
    </div>
  );
}
