import { INTENTS } from "@/mocks/catalog";
import type { AskOutcome, QueryResult } from "@/types/query";
import type { GuardSettings } from "@/types/settings";

export function capLimit(sql: string, maxRows: number): string {
  if (/LIMIT\s+\d+/i.test(sql)) {
    return sql.replace(/LIMIT\s+(\d+)/i, (_, amount: string) => `LIMIT ${Math.min(Number(amount), maxRows)}`);
  }
  return sql.replace(/;\s*$/, `\nLIMIT ${maxRows};`);
}

function finish(result: QueryResult, maxRows: number): QueryResult {
  return { ...result, sql: capLimit(result.sql, maxRows) };
}

/** In-browser stand-in for the text-to-SQL backend. */
export function interpret(question: string, settings: GuardSettings): AskOutcome {
  const q = question.toLowerCase().trim();
  if (!q) return { kind: "unknown" };

  if ((settings.blockDestructive || settings.selectOnly) && /\b(drop|delete|truncate|update|insert|alter)\b/.test(q)) {
    return {
      kind: "blocked",
      reason: settings.blockDestructive
        ? "Blocked: only read-only questions are allowed. Destructive keywords were detected."
        : "Blocked: this workspace allows SELECT questions only.",
    };
  }
  if (settings.domainRules && /\b(credit card|password|ssn|social security)\b/.test(q)) {
    return {
      kind: "blocked",
      reason:
        "Blocked by e-commerce domain rules. Sensitive fields such as payment data and passwords are not queryable.",
    };
  }

  const intent = INTENTS.find((item) => item.test(q));
  if (!intent) return { kind: "unknown" };
  if (intent.kind === "clarify") {
    return {
      kind: "clarify",
      options: intent.options.map((option) => ({ ...option, result: finish(option.result, settings.maxRows) })),
    };
  }
  if (intent.kind === "heal") return { kind: "heal", result: finish(intent.result, settings.maxRows) };
  return { kind: "result", result: finish(intent.result, settings.maxRows) };
}
