import { ApiError } from "@/api/client";
import type {
  GuardrailCheck,
  GuardrailCheckRequest,
  GuardrailPolicy,
  GuardrailSettings,
  QuestionRule,
} from "@/api/guardrails";

/** Stand-in for querymind-api's /guardrails endpoints (and querymind.guardrails); keeps the policy in this browser. */
const KEY = "querymind-mock-guardrails";

const POLITE_TOKEN = "{polite}";
const POLITE =
  "^\\s*(?:please\\s+)?(?:(?:can|could|would|will)\\s+you\\s+(?:please\\s+)?|i\\s+(?:want|need)\\s+to\\s+|let'?s\\s+)?";

const REQUIRED_SQL_KEYWORDS = [
  "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE",
]; // prettier-ignore

const LOCKED_RULES: QuestionRule[] = [
  {
    id: "delete-data",
    label: "Deleting data",
    message: "Deleting data is not allowed. QueryMind only reads data, and can draft UPDATE statements for review.",
    patterns: [
      "{polite}(?:delete|remove|purge|wipe|erase|truncate|clear\\s+out|get\\s+rid\\s+of)\\b",
      "\\bdelete\\s+(?:from|all|every|the|any|rows?|records?|them|it|those|these)\\b|\\btruncate\\s+table\\b",
      "\\b(?:and|then)\\s+(?:then\\s+)?(?:delete|remove|purge|wipe|erase|drop)\\b",
    ],
    enabled: true,
    locked: true,
  },
  {
    id: "change-structure",
    label: "Changing the database structure (DDL)",
    message: "Changing the database structure (DDL) is not allowed.",
    patterns: [
      "{polite}(?:drop|alter|create|rename)\\s+(?:the\\s+)?(?:table|view|index|column|schema|database)\\b",
      "\\b(?:drop|alter)\\s+(?:table|view|index|column|schema|database)\\b",
    ],
    enabled: true,
    locked: true,
  },
  {
    id: "insert-rows",
    label: "Adding rows (INSERT)",
    message:
      "Adding rows (INSERT) is not allowed. QueryMind only reads data, and can draft UPDATE statements for review.",
    patterns: ["{polite}(?:insert|add\\s+(?:a\\s+)?new\\s+(?:row|record))\\b", "\\binsert\\s+into\\b"],
    enabled: true,
    locked: true,
  },
  {
    id: "permissions",
    label: "Changing permissions",
    message: "Changing permissions is not allowed.",
    patterns: ["{polite}(?:grant|revoke)\\b", "\\b(?:grant|revoke)\\s+\\w+\\s+(?:on|to|from)\\b"],
    enabled: true,
    locked: true,
  },
];

export const DEFAULT_POLICY: GuardrailPolicy = {
  question_rules: [
    ...LOCKED_RULES,
    {
      id: "sensitive-data",
      label: "Passwords and payment card data",
      message: "Passwords, payment card numbers and similar sensitive fields can't be queried.",
      patterns: [
        "\\b(?:show|list|get|give|select|reveal|display|export|what\\s+(?:is|are))\\b.*\\b(?:passwords?" +
          "|password\\s+hash(?:es)?|credit\\s+card\\s+numbers?|card\\s+numbers?|cvv|ssn|social\\s+security\\s+numbers?)\\b",
      ],
      enabled: true,
      locked: false,
    },
  ],
  blocked_sql_keywords: [
    ...REQUIRED_SQL_KEYWORDS,
    "REPLACE INTO", "COMMIT", "ROLLBACK", "CALL", "EXEC", "EXECUTE", "COPY", "LOAD", "HANDLER", "LOCK", "SET",
    "INTO OUTFILE",
  ], // prettier-ignore
  restricted_columns: ["users.password_hash"],
  max_rows: 1000,
};

const LOCKED_IDS = LOCKED_RULES.map((rule) => rule.id);

function withBaseline(policy: GuardrailPolicy, updatedAt: number): GuardrailSettings {
  const rules = policy.question_rules.map((rule) => {
    const locked = LOCKED_IDS.includes(rule.id);
    return { ...rule, locked, enabled: rule.enabled || locked };
  });
  const missing = LOCKED_RULES.filter((locked) => !rules.some((rule) => rule.id === locked.id));
  const keywords = [
    ...policy.blocked_sql_keywords,
    ...REQUIRED_SQL_KEYWORDS.filter((keyword) => !policy.blocked_sql_keywords.includes(keyword)),
  ];
  return {
    ...policy,
    question_rules: [...missing, ...rules],
    blocked_sql_keywords: keywords,
    updated_at: updatedAt,
    required_sql_keywords: REQUIRED_SQL_KEYWORDS,
    locked_rule_ids: [...LOCKED_IDS].sort(),
    polite_token: POLITE_TOKEN,
  };
}

function problems(policy: GuardrailPolicy): string[] {
  const found: string[] = [];
  for (const locked of LOCKED_RULES) {
    const rule = policy.question_rules.find((r) => r.id === locked.id);
    if (!rule) found.push(`the rule '${locked.id}' (${locked.label}) cannot be removed`);
    else if (!rule.enabled) found.push(`the rule '${locked.id}' (${locked.label}) cannot be disabled`);
    else if (locked.patterns.some((p) => !rule.patterns.includes(p)))
      found.push(`the built-in patterns of '${locked.id}' cannot be removed`);
  }
  const missing = REQUIRED_SQL_KEYWORDS.filter((k) => !policy.blocked_sql_keywords.includes(k));
  if (missing.length) found.push(`these SQL keywords are always blocked: ${missing.join(", ")}`);
  for (const rule of policy.question_rules) {
    for (const pattern of rule.patterns) {
      try {
        new RegExp(pattern.replaceAll(POLITE_TOKEN, POLITE), "i");
      } catch {
        found.push(`invalid regular expression '${pattern}'`);
      }
    }
  }
  return found;
}

function load(): GuardrailSettings {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) return JSON.parse(saved) as GuardrailSettings;
  } catch {
    // Unreadable; fall back to the defaults.
  }
  return withBaseline(structuredClone(DEFAULT_POLICY), 0);
}

export async function getGuardrails(): Promise<GuardrailSettings> {
  return load();
}

export async function saveGuardrails(policy: GuardrailPolicy): Promise<GuardrailSettings> {
  const found = problems(policy);
  if (found.length) {
    const message = found.join("; ");
    throw new ApiError(422, `${message[0]!.toUpperCase()}${message.slice(1)}.`);
  }
  const saved = withBaseline(structuredClone(policy), Date.now() / 1000);
  localStorage.setItem(KEY, JSON.stringify(saved));
  return saved;
}

export async function resetGuardrails(): Promise<GuardrailSettings> {
  return saveGuardrails(structuredClone(DEFAULT_POLICY));
}

/** The first enabled rule that refuses the question, or null. */
export function refuseQuestion(policy: GuardrailPolicy, question: string): QuestionRule | null {
  return (
    policy.question_rules.find(
      (rule) =>
        rule.enabled && rule.patterns.some((p) => new RegExp(p.replaceAll(POLITE_TOKEN, POLITE), "i").test(question)),
    ) ?? null
  );
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Why generated SQL would not run, or null. Mirrors `Guardrails.check_sql`. */
export function checkSql(policy: GuardrailPolicy, sql: string): string | null {
  const code = sql
    .replace(/'(?:[^']|'')*'/g, "''")
    .replace(/"[^"]*"|`[^`]*`/g, '""')
    .replace(/--[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\//g, " ")
    .trim()
    .replace(/;$/, "")
    .trim();
  if (!code) return "empty query";
  if (code.includes(";")) return "multiple statements are not allowed";
  if (!/^\s*\(?\s*(SELECT|WITH)\b/i.test(code)) return "only SELECT / WITH queries are allowed";
  for (const keyword of [...policy.blocked_sql_keywords].sort((a, b) => b.length - a.length)) {
    if (new RegExp(`\\b${keyword.split(" ").map(escape).join("\\s+")}\\b`, "i").test(code))
      return `keyword ${keyword} is not allowed`;
  }
  const identifiers = sql
    .replace(/'(?:[^']|'')*'/g, "''")
    .replace(/--[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\//g, " ")
    .replace(/["`[\]]/g, " ");
  for (const column of policy.restricted_columns) {
    const name = column.split(".").pop()!;
    if (new RegExp(`\\b${escape(name)}\\b`, "i").test(identifiers)) return `column ${name} is restricted`;
  }
  return null;
}

export async function checkGuardrails(request: GuardrailCheckRequest): Promise<GuardrailCheck> {
  const policy = request.policy ? withBaseline(request.policy, 0) : load();
  const rule = request.question === undefined ? undefined : refuseQuestion(policy, request.question);
  const reason = request.sql === undefined ? undefined : checkSql(policy, request.sql);
  return {
    question: rule === undefined ? null : { allowed: !rule, rule_id: rule?.id ?? null, message: rule?.message ?? null },
    sql: reason === undefined ? null : { allowed: !reason, reason },
  };
}
