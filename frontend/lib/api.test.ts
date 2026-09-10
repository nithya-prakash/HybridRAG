import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL, csrfHeaders } from "./api";

describe("API_BASE_URL", () => {
  it("has a value", () => {
    expect(API_BASE_URL.length).toBeGreaterThan(0);
  });
});

function stubCookie(value: string) {
  vi.stubGlobal("document", { cookie: value });
}

describe("csrfHeaders", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns an empty object when document is unavailable (SSR)", () => {
    // vitest's default "node" environment already has no `document` global
    // — this is the real SSR case, not a simulation of one.
    expect(csrfHeaders()).toEqual({});
  });

  it("returns an empty object when no csrf_token cookie is set", () => {
    stubCookie("other=1");

    expect(csrfHeaders()).toEqual({});
  });

  it("reads the csrf_token cookie into an X-CSRF-Token header", () => {
    stubCookie("csrf_token=abc123");

    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "abc123" });
  });

  it("URL-decodes the cookie value", () => {
    stubCookie(`csrf_token=${encodeURIComponent("a+b/c=d")}`);

    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "a+b/c=d" });
  });

  it("picks csrf_token out among other cookies, regardless of position", () => {
    stubCookie("other=1; csrf_token=the-real-token; another=2");

    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "the-real-token" });
  });
});
