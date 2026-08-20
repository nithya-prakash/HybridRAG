"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export function NavBar() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <header className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
      <Link href="/" className="text-lg font-semibold">
        RAG Knowledge Assistant
      </Link>
      <nav className="flex items-center gap-4 text-sm">
        {loading ? null : user ? (
          <>
            <Link href="/dashboard" className="text-slate-300 hover:text-white">
              Dashboard
            </Link>
            <Link href="/documents" className="text-slate-300 hover:text-white">
              Documents
            </Link>
            <Link href="/chat" className="text-slate-300 hover:text-white">
              Chat
            </Link>
            <span className="text-slate-500">{user.email}</span>
            <button
              onClick={handleLogout}
              className="rounded-md border border-slate-700 px-3 py-1 text-slate-300 hover:border-slate-500 hover:text-white"
            >
              Log out
            </button>
          </>
        ) : (
          <>
            <Link href="/login" className="text-slate-300 hover:text-white">
              Log in
            </Link>
            <Link
              href="/register"
              className="rounded-md border border-slate-700 px-3 py-1 text-slate-300 hover:border-slate-500 hover:text-white"
            >
              Sign up
            </Link>
          </>
        )}
      </nav>
    </header>
  );
}
