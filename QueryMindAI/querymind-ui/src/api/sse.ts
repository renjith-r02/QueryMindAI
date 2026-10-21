export type ServerEvent = { event: string; data: string };

/**
 * Read a `text/event-stream` body and call `onEvent` for each event as it arrives.
 * Used instead of EventSource because the endpoints are POST (and need an abort signal).
 * Comment lines (keep-alive pings) are skipped; multi-line `data:` fields are joined.
 */
export async function readEventStream(body: ReadableStream<Uint8Array>, onEvent: (event: ServerEvent) => void) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n?/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const event = parseEvent(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        if (event) onEvent(event);
      }
    }
    const last = parseEvent(buffer + decoder.decode());
    if (last) onEvent(last);
  } finally {
    reader.releaseLock();
  }
}

function parseEvent(block: string): ServerEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, data: data.join("\n") } : null;
}
