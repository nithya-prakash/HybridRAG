import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "RAG Knowledge Assistant",
  description: "Multi-user RAG knowledge assistant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        <AuthProvider>
          <div className="mx-auto flex min-h-screen max-w-5xl flex-col">
            <NavBar />
            <main className="flex-1 px-6 py-8">{children}</main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
