import { describe, expect, it } from "vitest";
import { QueryFailedError, toAskOutcome, type RunResponse } from "@/api/runAdapter";

const query = {
  database: "ecommerce",
  dialect: "mysql",
  sql: " SELECT category, SUM(x) AS revenue FROM t ",
  purpose: "p",
};
const plan = { answerable: true, queries: [query], merge_sql: null, explanation: "Sums x.", assumptions: ["All time"] };
const table = {
  database: "ecommerce",
  columns: ["category", "revenue"],
  rows: [
    ["Shoes", 10],
    ["Hats", null],
  ],
  truncated: false,
  error: null,
};

function response(overrides: Partial<RunResponse> = {}): RunResponse {
  return {
    question: "revenue by category",
    status: "answered",
    model: "gpt-6-luna",
    final: { answer: "Shoes lead.", caveats: ["Small sample"] },
    result: table,
    warnings: [],
    attempts: [{ plan, results: [table], merged: null }],
    ...overrides,
  };
}

describe("toAskOutcome", () => {
  it("maps an answered run to a result", () => {
    const outcome = toAskOutcome(response());
    expect(outcome.kind).toBe("result");
    if (outcome.kind !== "result") return;
    const { result } = outcome;
    expect(result.answer).toBe("Shoes lead.");
    expect(result.caveats).toEqual(["Small sample"]);
    expect(result.sql).toBe("SELECT category, SUM(x) AS revenue FROM t");
    expect(result.explanation).toBe("Sums x.\nAssumption: All time");
    expect(result.columns).toEqual([
      { key: "category", label: "category" },
      { key: "revenue", label: "revenue" },
    ]);
    expect(result.rows).toEqual([
      { category: "Shoes", revenue: 10 },
      { category: "Hats", revenue: "" },
    ]);
    expect(result.queries).toEqual([query]);
  });

  it("reports a repaired run as healed with the first attempt's error", () => {
    const failed = { ...table, rows: [], error: "Unknown column 'x'" };
    const outcome = toAskOutcome(
      response({
        attempts: [
          { plan, results: [failed], merged: null },
          { plan, results: [table], merged: null },
        ],
      }),
    );
    expect(outcome.kind).toBe("heal");
    if (outcome.kind === "heal") {
      expect(outcome.result.heal).toEqual({
        brokenSql: "SELECT category, SUM(x) AS revenue FROM t",
        note: "[ecommerce] Unknown column 'x'",
      });
    }
  });

  it("notes truncation and keeps duplicate column names apart", () => {
    const outcome = toAskOutcome(
      response({ result: { ...table, columns: ["id", "id"], rows: [[1, 2]], truncated: true } }),
    );
    if (outcome.kind !== "result") throw new Error("expected result");
    expect(outcome.result.rows).toEqual([{ id: 1, id_2: 2 }]);
    expect(outcome.result.caveats).toContain("Only the first 1 rows were fetched.");
  });

  it("maps not_answerable to unknown with the model's explanation", () => {
    const outcome = toAskOutcome(
      response({
        status: "not_answerable",
        final: null,
        result: null,
        attempts: [{ plan: { ...plan, answerable: false, explanation: "No profit data." }, results: [], merged: null }],
      }),
    );
    expect(outcome).toEqual({ kind: "unknown", message: "No profit data." });
  });

  it("throws with the database errors when the run failed", () => {
    const failed = { ...table, rows: [], error: "timeout" };
    const run = response({ status: "failed", final: null, attempts: [{ plan, results: [failed], merged: null }] });
    expect(() => toAskOutcome(run)).toThrow(QueryFailedError);
    expect(() => toAskOutcome(run)).toThrow("The SQL could not be run after 1 attempt. [ecommerce] timeout");
  });
});

describe("intent statuses", () => {
  const selectIntent = {
    query_type: "SELECT_AGGREGATE" as const,
    tables_mentioned: ["order_lines"],
    columns_mentioned: [],
    traits: ["aggregate"],
    reason: "Totals.",
    source: "model" as const,
    blocked_message: null,
  };

  it("carries the intent onto the result", () => {
    const outcome = toAskOutcome(response({ intent: selectIntent }));
    if (outcome.kind !== "result") throw new Error("expected result");
    expect(outcome.result.intent?.query_type).toBe("SELECT_AGGREGATE");
    expect(outcome.result.notExecuted).toBeUndefined();
  });

  it("turns a refused request into a blocked outcome", () => {
    const outcome = toAskOutcome(
      response({
        status: "blocked",
        final: null,
        result: null,
        intent: {
          ...selectIntent,
          query_type: "UNSUPPORTED",
          source: "rules",
          blocked_message: "Deleting data is not allowed.",
        },
        attempts: [{ plan: { ...plan, answerable: false, queries: [] }, results: [], merged: null }],
      }),
    );
    expect(outcome).toEqual({ kind: "blocked", reason: "Deleting data is not allowed." });
  });

  it("marks a drafted UPDATE as not executed", () => {
    const update = {
      database: "ecommerce",
      dialect: "mysql",
      sql: "UPDATE orders SET status = 'x' WHERE order_id = 1",
      purpose: "p",
    };
    const outcome = toAskOutcome(
      response({
        status: "generated",
        result: null,
        intent: { ...selectIntent, query_type: "UPDATE", traits: [] },
        attempts: [{ plan: { ...plan, queries: [update] }, results: [], merged: null }],
      }),
    );
    if (outcome.kind !== "result") throw new Error("expected result");
    expect(outcome.result.notExecuted).toBe(true);
    expect(outcome.result.sql).toBe(update.sql);
    expect(outcome.result.rows).toEqual([]);
  });

  it("explains a withheld UPDATE draft without claiming anything ran", () => {
    const run = response({
      status: "failed",
      final: null,
      result: null,
      warnings: [
        "The drafted statement for ecommerce was withheld: an UPDATE without a WHERE clause would change every row.",
      ],
      intent: { ...selectIntent, query_type: "UPDATE", traits: [] },
      attempts: [{ plan: { ...plan, queries: [] }, results: [], merged: null }],
    });
    expect(() => toAskOutcome(run)).toThrow(/could not be drafted safely; nothing was run\. .*WHERE clause/);
  });
});

describe("semantic cache", () => {
  it("marks answers served from the cache", () => {
    const outcome = toAskOutcome(
      response({ cache: { hit: true, similarity: 0.98, question: "Revenue by category", cached_at: 1_700_000_000 } }),
    );
    if (outcome.kind !== "result") throw new Error("expected result");
    expect(outcome.result.cached).toEqual({
      similarity: 0.98,
      question: "Revenue by category",
      cachedAt: 1_700_000_000_000,
    });
  });

  it("leaves fresh answers unmarked", () => {
    const outcome = toAskOutcome(response({ cache: null }));
    if (outcome.kind !== "result") throw new Error("expected result");
    expect(outcome.result.cached).toBeUndefined();
  });
});
