import { apiFetch } from "@/api/client";
import { env } from "@/config/env";

/** A question is refused when any pattern (case-insensitive regular expression) matches it. */
export type QuestionRule = {
  id: string;
  label: string;
  message: string;
  patterns: string[];
  enabled: boolean;
  /** Part of the baseline: can be reworded but not removed or disabled. Set by the server. */
  locked: boolean;
};

/** The editable policy (querymind-api `PUT /guardrails`). */
export type GuardrailPolicy = {
  question_rules: QuestionRule[];
  blocked_sql_keywords: string[];
  restricted_columns: string[];
  max_rows: number;
};

/** querymind-api `GET /guardrails`: the policy stored in Qdrant, plus the fixed baseline. */
export type GuardrailSettings = GuardrailPolicy & {
  updated_at: number;
  required_sql_keywords: string[];
  locked_rule_ids: string[];
  /** Placeholder in patterns for an optional polite lead-in ("please", "can you", ...). */
  polite_token: string;
};

export type GuardrailCheck = {
  question: { allowed: boolean; rule_id: string | null; message: string | null } | null;
  sql: { allowed: boolean; reason: string | null } | null;
};

export type GuardrailCheckRequest = { question?: string; sql?: string; policy?: GuardrailPolicy };

const mocks = () => import("@/mocks/guardrails");

export function toPolicy(settings: GuardrailSettings): GuardrailPolicy {
  return {
    question_rules: settings.question_rules,
    blocked_sql_keywords: settings.blocked_sql_keywords,
    restricted_columns: settings.restricted_columns,
    max_rows: settings.max_rows,
  };
}

export async function getGuardrails(): Promise<GuardrailSettings> {
  if (env.useMocks) return (await mocks()).getGuardrails();
  return apiFetch<GuardrailSettings>("/guardrails");
}

export async function saveGuardrails(policy: GuardrailPolicy): Promise<GuardrailSettings> {
  if (env.useMocks) return (await mocks()).saveGuardrails(policy);
  return apiFetch<GuardrailSettings>("/guardrails", { method: "PUT", body: JSON.stringify(policy) });
}

export async function resetGuardrails(): Promise<GuardrailSettings> {
  if (env.useMocks) return (await mocks()).resetGuardrails();
  return apiFetch<GuardrailSettings>("/guardrails/reset", { method: "POST" });
}

/** Test a question and/or SQL; with `policy`, against those unsaved edits. Nothing is run. */
export async function checkGuardrails(request: GuardrailCheckRequest): Promise<GuardrailCheck> {
  if (env.useMocks) return (await mocks()).checkGuardrails(request);
  return apiFetch<GuardrailCheck>("/guardrails/check", { method: "POST", body: JSON.stringify(request) });
}
