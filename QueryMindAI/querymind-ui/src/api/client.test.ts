import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "@/api/client";

function mockFetch(implementation: () => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(implementation));
}

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns parsed JSON", async () => {
    mockFetch(async () => Response.json({ ok: true }));
    await expect(apiFetch("/x")).resolves.toEqual({ ok: true });
  });

  it("uses the FastAPI detail message", async () => {
    mockFetch(async () => Response.json({ detail: "The vector store is unavailable." }, { status: 503 }));
    await expect(apiFetch("/x")).rejects.toEqual(new ApiError(503, "The vector store is unavailable."));
  });

  it("joins validation errors", async () => {
    mockFetch(async () => Response.json({ detail: [{ msg: "Field required" }, { msg: "Too long" }] }, { status: 422 }));
    await expect(apiFetch("/x")).rejects.toThrow("Field required; Too long");
  });

  it("explains network failures", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(apiFetch("/x")).rejects.toThrow("Could not reach the QueryMind API");
  });
});
