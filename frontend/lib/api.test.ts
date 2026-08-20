import { describe, expect, it } from "vitest";
import { API_BASE_URL } from "./api";

describe("API_BASE_URL", () => {
  it("has a value", () => {
    expect(API_BASE_URL.length).toBeGreaterThan(0);
  });
});
