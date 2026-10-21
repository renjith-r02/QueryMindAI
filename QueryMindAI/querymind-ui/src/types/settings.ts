export const DIALECTS = ["PostgreSQL", "MySQL"] as const;
export type Dialect = (typeof DIALECTS)[number];

export type Settings = {
  explanation: boolean;
  primaryDialect: Dialect;
  secondaryDialect: Dialect;
  multiDialect: boolean;
};
