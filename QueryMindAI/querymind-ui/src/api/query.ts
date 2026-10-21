import { ApiError, apiStream } from "@/api/client";
import { toAskOutcome, type RunResponse } from "@/api/runAdapter";
import { readEventStream } from "@/api/sse";
import { env } from "@/config/env";
import type { ProgressStep } from "@/types/progress";
import type { AskOutcome } from "@/types/query";

export type AskOptions = {
  /** Called for every progress event while the question is being answered. */
  onProgress?: (step: ProgressStep) => void;
  signal?: AbortSignal;
  /** false skips the server's semantic cache and asks the model again. */
  useCache?: boolean;
};

export async function askQuestion(question: string, options: AskOptions = {}): Promise<AskOutcome> {
  if (env.useMocks) {
    const mocks = await import("@/mocks/handlers");
    return mocks.askQuestion(question, options);
  }
  // Guardrails (stored in Qdrant, see /guardrails), model and row limits are applied by the server,
  // so only the question is sent.
  const response = await apiStream("/run/stream", {
    method: "POST",
    body: JSON.stringify(options.useCache === false ? { question, use_cache: false } : { question }),
    signal: options.signal,
  });

  let result: RunResponse | undefined;
  let failure: ApiError | undefined;
  await readEventStream(response.body!, ({ event, data }) => {
    if (event === "progress") options.onProgress?.(JSON.parse(data) as ProgressStep);
    else if (event === "result") result = JSON.parse(data) as RunResponse;
    else if (event === "error") {
      const { status, detail } = JSON.parse(data) as { status: number; detail: string };
      failure = new ApiError(status, detail);
    }
  });

  if (failure) throw failure;
  if (!result) throw new ApiError(0, "The connection to the QueryMind API closed before an answer arrived.");
  return toAskOutcome(result);
}
