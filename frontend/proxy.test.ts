import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

function makeRequest(path: string, cookieHeader?: string): NextRequest {
  const url = `https://app.example.com${path}`;
  const headers = cookieHeader ? { cookie: cookieHeader } : undefined;
  return new NextRequest(url, { headers });
}

describe("proxy", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("passes unprotected paths through untouched", () => {
    const res = proxy(makeRequest("/login"));

    expect(res.status).toBe(200); // NextResponse.next() — not a redirect
  });

  describe("same-origin API (NEXT_PUBLIC_API_URL matches the request's own host)", () => {
    it("redirects to /login?next=... when no access_token cookie is present", () => {
      vi.stubEnv("NEXT_PUBLIC_API_URL", "https://app.example.com");

      const res = proxy(makeRequest("/dashboard"));

      expect(res.status).toBe(307);
      const location = new URL(res.headers.get("location")!);
      expect(location.pathname).toBe("/login");
      expect(location.searchParams.get("next")).toBe("/dashboard");
    });

    it("passes through when an access_token cookie is present", () => {
      vi.stubEnv("NEXT_PUBLIC_API_URL", "https://app.example.com");

      const res = proxy(makeRequest("/dashboard", "access_token=some-jwt"));

      expect(res.status).toBe(200);
    });
  });

  describe("cross-origin API (e.g. Vercel frontend + Render backend)", () => {
    // The whole point of this deployment shape: request.cookies here can
    // never contain access_token no matter how correctly the API sets it —
    // it's scoped to the API's own domain, not this one. Asserting
    // "passes through even with zero cookies" is exactly what proves this
    // proxy is deferring to the client-side check (lib/auth-context.tsx)
    // rather than incorrectly gatekeeping on a cookie it can't see.
    it("passes protected paths through with no cookie at all", () => {
      vi.stubEnv("NEXT_PUBLIC_API_URL", "https://hybridrag-backend-414s.onrender.com");

      const res = proxy(makeRequest("/dashboard"));

      expect(res.status).toBe(200);
    });

    it("passes /documents through too, not just /dashboard", () => {
      vi.stubEnv("NEXT_PUBLIC_API_URL", "https://hybridrag-backend-414s.onrender.com");

      const res = proxy(makeRequest("/documents"));

      expect(res.status).toBe(200);
    });
  });

  it("treats a missing NEXT_PUBLIC_API_URL as same-origin (the pre-split-deploy default)", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");

    const res = proxy(makeRequest("/dashboard"));

    expect(res.status).toBe(307); // still gatekeeps — same behavior as before this app could split origins
  });
});
