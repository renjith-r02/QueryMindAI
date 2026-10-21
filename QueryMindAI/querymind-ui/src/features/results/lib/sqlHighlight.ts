const KEYWORDS = new Set([
  "SELECT",
  "FROM",
  "WHERE",
  "JOIN",
  "ON",
  "GROUP",
  "BY",
  "ORDER",
  "LIMIT",
  "AS",
  "AND",
  "SUM",
  "COUNT",
  "DESC",
  "ASC",
  "LEFT",
  "INNER",
  "CAST",
  "NUMERIC",
]);

export type SqlToken = { text: string; keyword: boolean };

export function tokenizeSql(sql: string): SqlToken[] {
  return sql
    .split(/(\b[A-Z_]+\b)/g)
    .filter((text) => text !== "")
    .map((text) => ({ text, keyword: KEYWORDS.has(text) }));
}
