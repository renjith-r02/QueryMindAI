export type Column = { key: string; label: string };
export type Row = Record<string, string | number>;

/** What the question asks for, as classified by querymind-api before SQL is written. */
export type QueryIntent = {
  query_type: "SELECT_SIMPLE" | "SELECT_AGGREGATE" | "SELECT_JOIN" | "SELECT_TEMPORAL" | "UPDATE" | "UNSUPPORTED";
  tables_mentioned: string[];
  columns_mentioned: string[];
  traits: string[];
  reason: string;
  source: "rules" | "model" | "rules-fallback";
  blocked_message?: string | null;
};

/** One SQL statement, written in the dialect of the database it runs on. */
export type GeneratedQuery = { database: string; dialect: string; sql: string; purpose: string };

export type QueryResult = {
  sql: string;
  explanation: string;
  columns: Column[];
  rows: Row[];
  heal?: { brokenSql: string; note: string };
  /** Written answer to the question, from the backend (markdown). */
  answer?: string;
  caveats?: string[];
  /** Per-database statements from the backend; when set, `sql` is not transpiled for display. */
  queries?: GeneratedQuery[];
  /** SQLite statement that combines the results of several queries. */
  mergeSql?: string;
  intent?: QueryIntent;
  /** A drafted UPDATE: the SQL is returned for review and was not run. */
  notExecuted?: boolean;
  /** Set when the answer was reused from the semantic cache (no model calls). */
  cached?: CacheInfo;
};

export type CacheInfo = {
  similarity: number;
  /** The question the cached answer was produced for. */
  question: string;
  /** When the cached answer was produced (ms since epoch). */
  cachedAt: number;
};

export type ClarifyOption = {
  id: string;
  title: string;
  detail: string;
  result: QueryResult;
};

export type AskOutcome =
  | { kind: "result"; result: QueryResult }
  | { kind: "clarify"; options: ClarifyOption[] }
  | { kind: "heal"; result: QueryResult }
  | { kind: "blocked"; reason: string }
  | { kind: "unknown"; message?: string };
