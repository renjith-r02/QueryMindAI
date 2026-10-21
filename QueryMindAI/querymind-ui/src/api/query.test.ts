import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunResponse } from "@/api/runAdapter";
import type { ProgressStep } from "@/types/progress";

const GUARDS = { selectOnly: true, blockDestructive: true, domainRules: true, maxRows: 100 };

const table = { database: "ecommerce", columns: ["n"], rows: [[1], [2]], truncated: false, error: null };
const answered: RunResponse = {
  question: "q",
  status: "answered",
  model: "m",
  final: { answer: "Two rows.", caveats: [] },
  result: table,
  warnings: [],
  attempts: [
    {
      plan: {
        answerable: true,
        queries: [{ database: "ecommerce", dialect: "mysql", sql: "SELECT n FROM t", purpose: "p" }],
        merge_sql: null,
        explanation: "e",
        assumptions: [],
      },
      results: [table],
      merged: null,
    },
  ],
};

const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

async function askWithStream(chunks: string[]) {
  vi.stubEnv("VITE_API_URL", "http://api.test");
  vi.stubEnv("VITE_USE_MOCKS", "false");
  const fetchMock = vi.fn(async () => streamResponse(chunks));
  vi.stubGlobal("fetch", fetchMock);
  vi.resetModules();
  const { askQuestion } = await import("@/api/query");
  const steps: ProgressStep[] = [];
  const outcome = askQuestion("q", GUARDS, { onProgress: (step) => steps.push(step) });
  return { outcome, steps, fetchMock };
}

describe("askQuestion over the streaming API", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("posts to /run/stream, reports progress, and returns the result", async () => {
    const step = { id: "retrieve", status: "running", message: "Searching", detail: {} };
    const { outcome, steps, fetchMock } = await askWithStream([
      sse("progress", step),
      ": ping\n\n",
      sse("progress", { ...step, status: "done", message: "Found 3" }),
      sse("result", answered),
    ]);

    const result = await outcome;
    expect(result.kind).toBe("result");
    expect(steps.map((s) => s.status)).toEqual(["running", "done"]);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/run/stream",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ question: "q" }),
        headers: expect.objectContaining({ Accept: "text/event-stream" }),
      }),
    );
  });

  it("throws the server's error event", async () => {
    const { outcome } = await askWithStream([
      sse("error", { status: 503, detail: "The vector store is unavailable." }),
    ]);
    await expect(outcome).rejects.toThrow("The vector store is unavailable.");
  });

  it("fails clearly when the stream ends without an answer", async () => {
    const { outcome } = await askWithStream([sse("progress", { id: "retrieve", status: "running", message: "x" })]);
    await expect(outcome).rejects.toThrow("closed before an answer arrived");
  });

  it("asks the server to skip its cache for a fresh answer", async () => {
    vi.stubEnv("VITE_API_URL", "http://api.test");
    vi.stubEnv("VITE_USE_MOCKS", "false");
    const fetchMock = vi.fn(async () => streamResponse([sse("result", answered)]));
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    const { askQuestion } = await import("@/api/query");
    await askQuestion("q", GUARDS, { useCache: false });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/run/stream",
      expect.objectContaining({ body: JSON.stringify({ question: "q", use_cache: false }) }),
    );
  });
});
