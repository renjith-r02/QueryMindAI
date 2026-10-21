import type { CacheInfo, Column, GeneratedQuery, QueryIntent, Row } from "@/types/query";

export type RunStatus = "success" | "healed" | "blocked";
export type Feedback = "up" | "down";

export type Run = {
  id: string;
  question: string;
  at: number;
  ms: number;
  status: RunStatus;
  sql: string;
  explanation: string;
  columns: Column[];
  rows: Row[];
  healingNote?: string;
  brokenSql?: string;
  reason?: string;
  answer?: string;
  caveats?: string[];
  queries?: GeneratedQuery[];
  mergeSql?: string;
  intent?: QueryIntent;
  notExecuted?: boolean;
  cached?: CacheInfo;
  feedback?: Feedback;
};
