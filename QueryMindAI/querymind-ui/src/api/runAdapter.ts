import type { AskOutcome, Column, GeneratedQuery, QueryIntent, QueryResult, Row } from "@/types/query";

/** Response of querymind-api `POST /run` (see querymind-api/docs/openapi.yaml, RunResponse). */
export type RunResponse = {
  question: string;
  /** generated = an UPDATE was drafted and NOT run; blocked = refused by the intent classifier. */
  status: "answered" | "not_answerable" | "failed" | "blocked" | "generated";
  model: string;
  intent?: QueryIntent | null;
  cache?: { hit: boolean; similarity: number; question: string; cached_at: number } | null;
  final: { answer: string; caveats: string[] } | null;
  result: ResultTable | null;
  warnings: string[];
  attempts: { plan: SqlPlan; results: ResultTable[]; merged: ResultTable | null }[];
};

type SqlPlan = {
  answerable: boolean;
  queries: GeneratedQuery[];
  merge_sql: string | null;
  explanation: string;
  assumptions: string[];
};

type ResultTable = {
  database: string;
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
  error: string | null;
};

export class QueryFailedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "QueryFailedError";
  }
}

/** Convert a `/run` response into the outcome the Ask page renders. */
export function toAskOutcome(response: RunResponse): AskOutcome {
  const attempts = response.attempts;
  const last = attempts.at(-1);

  if (response.status === "blocked") {
    const reason = response.intent?.blocked_message || last?.plan.explanation || "This request is not allowed.";
    return { kind: "blocked", reason };
  }
  if (response.status === "not_answerable") {
    return { kind: "unknown", message: last?.plan.explanation || undefined };
  }
  if (response.status === "failed" || !last) {
    throw new QueryFailedError(failureMessage(response));
  }

  const result = toQueryResult(response, last.plan);
  if (response.status === "generated") return { kind: "result", result: { ...result, notExecuted: true } };
  const first = attempts[0];
  if (attempts.length > 1 && first) {
    // The first SQL failed and the backend regenerated it with the error.
    result.heal = { brokenSql: joinSql(first.plan.queries), note: attemptErrors(first).join(" ") };
    return { kind: "heal", result };
  }
  return { kind: "result", result };
}

function toQueryResult(response: RunResponse, plan: SqlPlan): QueryResult {
  const table = response.result;
  const columns = toColumns(table?.columns ?? []);
  const rows = (table?.rows ?? []).map((values) => toRow(columns, values));
  const caveats = [...(response.final?.caveats ?? []), ...response.warnings];
  if (table?.truncated) caveats.push(`Only the first ${rows.length} rows were fetched.`);

  return {
    sql: joinSql(plan.queries),
    explanation: [plan.explanation, ...plan.assumptions.map((a) => `Assumption: ${a}`)].join("\n"),
    columns,
    rows,
    answer: response.final?.answer,
    caveats,
    queries: plan.queries,
    mergeSql: plan.merge_sql ?? undefined,
    intent: response.intent ?? undefined,
    cached: response.cache?.hit
      ? {
          similarity: response.cache.similarity,
          question: response.cache.question,
          cachedAt: response.cache.cached_at * 1000,
        }
      : undefined,
  };
}

/** Column names can repeat (e.g. two `id` columns), so keys are made unique. */
function toColumns(names: string[]): Column[] {
  const seen = new Map<string, number>();
  return names.map((name) => {
    const count = (seen.get(name) ?? 0) + 1;
    seen.set(name, count);
    return { key: count === 1 ? name : `${name}_${count}`, label: name };
  });
}

function toRow(columns: Column[], values: unknown[]): Row {
  return Object.fromEntries(columns.map((column, index) => [column.key, toCell(values[index])]));
}

function toCell(value: unknown): string | number {
  if (typeof value === "number" || typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function joinSql(queries: GeneratedQuery[]): string {
  return queries.map((query) => query.sql.trim()).join("\n\n");
}

function attemptErrors(attempt: RunResponse["attempts"][number]): string[] {
  return [...attempt.results, attempt.merged]
    .filter((table): table is ResultTable => Boolean(table?.error))
    .map((table) => `[${table.database}] ${table.error}`);
}

function failureMessage(response: RunResponse): string {
  if (response.intent?.query_type === "UPDATE") {
    return ["The UPDATE could not be drafted safely; nothing was run.", ...response.warnings].join(" ");
  }
  const last = response.attempts.at(-1);
  const errors = last ? attemptErrors(last) : [];
  const count = response.attempts.length;
  const summary = `The SQL could not be run after ${count} attempt${count === 1 ? "" : "s"}.`;
  return errors.length ? `${summary} ${errors.join(" ")}` : summary;
}
