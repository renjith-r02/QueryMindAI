export const DIALECTS = ["PostgreSQL", "MySQL"] as const;
export type Dialect = (typeof DIALECTS)[number];

export type Settings = {
  explanation: boolean;
  primaryDialect: Dialect;
  secondaryDialect: Dialect;
  multiDialect: boolean;
  maxRows: number;
  selectOnly: boolean;
  blockDestructive: boolean;
  domainRules: boolean;
  rateLimit: boolean;
};

/** The subset of settings the backend needs to apply guardrails. */
export type GuardSettings = Pick<Settings, "selectOnly" | "blockDestructive" | "domainRules" | "maxRows">;
