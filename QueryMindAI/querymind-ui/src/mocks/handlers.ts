import { SUGGESTIONS } from "@/mocks/catalog";
import { getGuardrails } from "@/mocks/guardrails";
import { interpret } from "@/mocks/interpret";
import { SCHEMA } from "@/mocks/schema";
import type { AskOptions } from "@/api/query";
import type { ProgressStep } from "@/types/progress";
import type { AskOutcome } from "@/types/query";
import type { SchemaFile } from "@/types/schema";

/** Simulated time per step, so the mock shows the same live progress as the real API. */
const STEP_MS = 180;

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

/** Mirrors the progress events of querymind-api `POST /run/stream`. */
export async function askQuestion(question: string, options: AskOptions = {}) {
  const step = async (id: string, running: string, end: string, status: ProgressStep["status"] = "done") => {
    options.onProgress?.({ id, status: "running", message: running });
    await wait(STEP_MS, options.signal);
    options.onProgress?.({ id, status, message: end });
  };

  const outcome = interpret(question, await getGuardrails());
  if (outcome.kind === "blocked") {
    await step("guard", "Checking the question against guardrails", outcome.reason, "failed");
    return outcome;
  }

  await step(
    "retrieve",
    "Searching the knowledge base for relevant tables, rules and examples",
    "Found 24 relevant notes across ecommerce",
  );
  await step("schema", "Checking which tables exist in the databases", "Checked 1 database");
  await step("generate-1", "Writing SQL", generatedMessage(outcome));
  if (outcome.kind === "unknown" || outcome.kind === "clarify") return outcome;

  const rows = outcome.result.rows.length;
  if (outcome.kind === "heal") {
    await step(
      "execute-1-1",
      "Running the query on ecommerce (postgresql)",
      "ecommerce: operator does not exist: text >= integer",
      "failed",
    );
    await step("generate-2", "Rewriting the SQL to fix the error (attempt 2)", "Wrote 1 query for ecommerce");
    await step("execute-2-1", "Running the query on ecommerce (postgresql)", `${rows} rows from ecommerce in 12 ms`);
  } else {
    await step("execute-1-1", "Running the query on ecommerce (postgresql)", `${rows} rows from ecommerce in 9 ms`);
  }
  await step("answer", "Writing the answer from the results", "Answer ready");
  return outcome;
}

function generatedMessage(outcome: AskOutcome): string {
  if (outcome.kind === "unknown") return "The question can't be answered from the available data";
  if (outcome.kind === "clarify") return "More than one column matches; choose one";
  return "Wrote 1 query for ecommerce";
}

export async function getSchema(database?: string): Promise<SchemaFile[]> {
  return SCHEMA.filter((file) => !database || file.database.toLowerCase() === database.toLowerCase());
}

export async function getExamples(): Promise<string[]> {
  return SUGGESTIONS;
}
