import type { GuardrailPolicy } from "@/api/guardrails";
import { INTENTS } from "@/mocks/catalog";
import { refuseQuestion } from "@/mocks/guardrails";
import type { AskOutcome, QueryResult } from "@/types/query";

export function capLimit(sql: string, maxRows: number): string {
  if (/LIMIT\s+\d+/i.test(sql)) {
    return sql.replace(/LIMIT\s+(\d+)/i, (_, amount: string) => `LIMIT ${Math.min(Number(amount), maxRows)}`);
  }
  return sql.replace(/;\s*$/, `\nLIMIT ${maxRows};`);
}

function finish(result: QueryResult, maxRows: number): QueryResult {
  return { ...result, sql: capLimit(result.sql, maxRows) };
}

/** In-browser stand-in for the text-to-SQL backend, applying the (mock) guardrail policy. */
export function interpret(question: string, policy: GuardrailPolicy): AskOutcome {
  const q = question.toLowerCase().trim();
  if (!q) return { kind: "unknown" };

  const rule = refuseQuestion(policy, q);
  if (rule) return { kind: "blocked", reason: rule.message };

  const intent = INTENTS.find((item) => item.test(q));
  if (!intent) return { kind: "unknown" };
  if (intent.kind === "clarify") {
    return {
      kind: "clarify",
      options: intent.options.map((option) => ({ ...option, result: finish(option.result, policy.max_rows) })),
    };
  }
  if (intent.kind === "heal") return { kind: "heal", result: finish(intent.result, policy.max_rows) };
  return { kind: "result", result: finish(intent.result, policy.max_rows) };
}
