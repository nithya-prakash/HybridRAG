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
 * Reads the `csrf_token` cookie (set by the backend's CsrfMiddleware on the
 * first safe-method request — see backend/app/core/csrf.py) and returns it
 * as a header the backend's double-submit-cookie check requires on every
 * unsafe-method (POST/PUT/PATCH/DELETE) request. Deliberately *not*
 * httpOnly on the backend side so this can read it — the whole point of
 * the double-submit pattern is that only same-origin JS can do this.
 * Returns `{}` before the cookie exists yet (SSR, or a request that
 * somehow races the very first page load) rather than throwing — the
 * backend rejects with a clear 403 in that case instead.
 */
export function csrfHeaders(): Record<string, string> {
  if (typeof document === "undefined") return {};
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
  return match ? { "X-CSRF-Token": decodeURIComponent(match[1]) } : {};
}

export interface HealthResponse {
  status: string;
  app_name: string;
  environment: string;
  version: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return res.json();
}
