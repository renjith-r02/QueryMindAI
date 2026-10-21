import { describe, expect, it } from "vitest";
import { readEventStream, type ServerEvent } from "@/api/sse";

/** A response body that delivers the text in the given chunks. */
function chunkedBody(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(chunks: string[]): Promise<ServerEvent[]> {
  const events: ServerEvent[] = [];
  await readEventStream(chunkedBody(chunks), (event) => events.push(event));
  return events;
}

describe("readEventStream", () => {
  it("parses events split across chunks and skips keep-alive comments", async () => {
    const events = await collect([
      'event: progress\ndata: {"id":"retr',
      'ieve"}\n\n: ping\n\nevent: result\n',
      'data: {"ok":true}\n\n',
    ]);
    expect(events).toEqual([
      { event: "progress", data: '{"id":"retrieve"}' },
      { event: "result", data: '{"ok":true}' },
    ]);
  });

  it("joins multi-line data, handles CRLF and a final event without a blank line", async () => {
    const events = await collect(["data: line 1\r\ndata: line 2\r\n\r\n", "event: error\ndata: x"]);
    expect(events).toEqual([
      { event: "message", data: "line 1\nline 2" },
      { event: "error", data: "x" },
    ]);
  });

  it("decodes multi-byte characters split between chunks", async () => {
    const bytes = new TextEncoder().encode('data: "café ✓"\n\n');
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 12)); // splits the é
        controller.enqueue(bytes.slice(12));
        controller.close();
      },
    });
    const events: ServerEvent[] = [];
    await readEventStream(body, (event) => events.push(event));
    expect(events).toEqual([{ event: "message", data: '"café ✓"' }]);
  });
});
