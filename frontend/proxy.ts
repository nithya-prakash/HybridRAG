import { NextResponse, type NextRequest } from "next/server";

const PROTECTED_PREFIXES = ["/dashboard", "/documents"];

// This proxy runs on Vercel's own server, not the API's — `request.cookies`
// only ever contains cookies scoped to *this* request's domain. When the
// frontend and API share an origin, the access_token cookie (set by the
// API) is that domain's cookie too, so checking for it here works. But this
// app can also be deployed with the frontend and API on two different
// origins entirely (e.g. Vercel + Render — see docs/DEPLOY_FREE_TIER.md),
// and in that shape `request.cookies.has("access_token")` can never be
// true here no matter how correctly the API sets its own cookie — a
// same-origin-policy fact about cookies, not a bug to work around with a
// smarter check. Every protected page already re-checks auth itself,
// client-side, against the real API (`useAuth()` in lib/auth-context.tsx,
// via a real cross-origin fetch to /auth/me) — that's the check that
// actually works cross-origin, so this proxy defers to it entirely rather
// than redirecting on a cookie it structurally cannot see.
function isCrossOriginApi(request: NextRequest): boolean {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) return false;
  try {
    // request.nextUrl already reflects wherever this app is actually being
    // reached at right now — custom domain, *.vercel.app, localhost — no
    // separate "what's our own origin" config needed. Note this is a plain
    // hostname comparison, not a real same-site (eTLD+1) check: a single-VM
    // deploy using api.example.com for the backend and example.com for the
    // frontend, with cookie_domain set to the shared .example.com parent
    // (see docs/ARCHITECTURE.md), would trip this and fall back to the
    // client-side-only check too — safe (that check still works
    // correctly), just gives up the server-side pre-check's UX benefit
    // (skipping a flash of protected content before client JS runs) in a
    // case that didn't strictly need to. Not worth a real same-site check
    // for a distinction with no security consequence either way.
    return new URL(apiUrl).hostname !== request.nextUrl.hostname;
  } catch {
    return false;
  }
}

export function proxy(request: NextRequest) {
  const isProtected = PROTECTED_PREFIXES.some((prefix) =>
    request.nextUrl.pathname.startsWith(prefix)
  );

  if (!isProtected || isCrossOriginApi(request)) {
    return NextResponse.next();
  }

  const hasSessionCookie = request.cookies.has("access_token");
  if (!hasSessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/documents/:path*"],
};
