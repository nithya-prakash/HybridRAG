export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // response body wasn't JSON — fall through to generic message
  }
  return `Request failed with status ${res.status}`;
}

/**
 * The double-submit CSRF token, held in memory rather than read from
 * `document.cookie`. That would work if this frontend and the backend
 * shared an origin, but they don't have to — this app can be deployed with
 * the frontend on one host and the API on another (e.g. Vercel + Render;
 * see docs/DEPLOY_FREE_TIER.md), and a page can never read a cookie set by
 * a *different* origin no matter its SameSite/Secure attributes. The
 * backend's CsrfMiddleware (backend/app/core/csrf.py) still sets the
 * `csrf_token` cookie the browser sends back automatically on every
 * request, but it also now echoes that same value as an `X-CSRF-Token`
 * *response header* on the request that first issues it, exposed
 * cross-origin via `Access-Control-Expose-Headers` — a page can read an
 * exposed header from its own fetch() response even when it could never
 * read that origin's cookies directly. `captureCsrfToken` below is called
 * after every request; `csrfHeaders` echoes whatever it last captured back
 * as the header the backend's double-submit check requires on every
 * unsafe-method (POST/PUT/PATCH/DELETE) request.
 */
let csrfToken: string | null = null;

/** Call with every fetch Response — a no-op if it didn't carry a fresh token. */
export function captureCsrfToken(res: Response): void {
  const token = res.headers.get("X-CSRF-Token");
  if (token) csrfToken = token;
}

/**
 * Returns `{}` before any response has carried a token yet (the very first
 * request of a session necessarily has none to send) rather than throwing —
 * the backend rejects with a clear 403 in that case instead.
 */
export function csrfHeaders(): Record<string, string> {
  return csrfToken ? { "X-CSRF-Token": csrfToken } : {};
}

/** Test-only: the module-level token otherwise has no way to reset between tests. */
export function _resetCsrfTokenForTests(): void {
  csrfToken = null;
}

export interface HealthResponse {
  status: string;
  app_name: string;
  environment: string;
  version: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  captureCsrfToken(res);
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return res.json();
}
