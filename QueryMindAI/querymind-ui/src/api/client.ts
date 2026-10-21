import { env } from "@/config/env";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await request(path, init, "application/json");
  return (await response.json()) as T;
}

/** POST/GET that answers with Server-Sent Events; returns the response for reading its body. */
export async function apiStream(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await request(path, init, "text/event-stream");
  if (!response.body) throw new ApiError(response.status, "The API returned an empty stream.");
  return response;
}

async function request(path: string, init: RequestInit, accept: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}${path}`, {
      ...init,
      headers: { Accept: accept, "Content-Type": "application/json", ...init.headers },
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError(0, `Could not reach the QueryMind API at ${env.apiUrl}. Is it running?`);
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return response;
}

/** FastAPI errors are `{"detail": "..."}`, or a list of field problems for validation errors. */
async function errorMessage(response: Response): Promise<string> {
  const text = await response.text().catch(() => "");
  try {
    const { detail } = JSON.parse(text) as { detail?: unknown };
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item: { msg?: string }) => item.msg ?? JSON.stringify(item)).join("; ");
    }
  } catch {
    // Not JSON; fall through to the raw text.
  }
  return text || `${response.status} ${response.statusText}`;
}
