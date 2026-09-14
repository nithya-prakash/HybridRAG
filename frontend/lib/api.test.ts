import { afterEach, describe, expect, it } from "vitest";
import {
  API_BASE_URL,
  _resetCsrfTokenForTests,
  captureCsrfToken,
  csrfHeaders,
} from "./api";

describe("API_BASE_URL", () => {
  it("has a value", () => {
    expect(API_BASE_URL.length).toBeGreaterThan(0);
  });
});

// captureCsrfToken/csrfHeaders hold the token in memory rather than reading
// document.cookie — a cross-origin frontend (see docs/DEPLOY_FREE_TIER.md)
// can never read a cookie set by a different origin, so the only value it
// can ever learn is whatever the backend's CsrfMiddleware (backend/app/core/
// csrf.py) echoes back as the X-CSRF-Token *response* header the first time
// it issues one. These tests build real Response objects (Node's global
// fetch API, not a mock) to exercise exactly what a fetch() call site sees.
describe("captureCsrfToken / csrfHeaders", () => {
  afterEach(() => {
    _resetCsrfTokenForTests();
  });

  it("returns an empty object before any response has carried a token", () => {
    expect(csrfHeaders()).toEqual({});
  });

  it("is a no-op when a response carries no X-CSRF-Token header", () => {
    captureCsrfToken(new Response(null));

    expect(csrfHeaders()).toEqual({});
  });

  it("captures the token from a response header", () => {
    captureCsrfToken(new Response(null, { headers: { "X-CSRF-Token": "abc123" } }));

    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "abc123" });
  });

  it("keeps the most recently captured token across multiple responses", () => {
    captureCsrfToken(new Response(null, { headers: { "X-CSRF-Token": "first" } }));
    captureCsrfToken(new Response(null)); // e.g. a later request, cookie already set — no-op
    captureCsrfToken(new Response(null, { headers: { "X-CSRF-Token": "second" } }));

    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "second" });
  });
});
