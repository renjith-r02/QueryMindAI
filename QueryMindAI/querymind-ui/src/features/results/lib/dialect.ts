import type { Dialect } from "@/types/settings";

/** Rewrite generated PostgreSQL into a second dialect. Mirrors sqlglot.transpile(). */
export function transpile(sql: string, dialect: Dialect): string {
  const trimmed = sql.trim();
  if (dialect === "PostgreSQL") return trimmed;

  return trimmed
    .replace(/DATE_TRUNC\(\s*'month'\s*,\s*([^)]+)\)/gi, "DATE_FORMAT($1, '%Y-%m-01')")
    .replace(
      /DATE_TRUNC\(\s*'quarter'\s*,\s*CURRENT_DATE\)/gi,
      "DATE_ADD(MAKEDATE(YEAR(CURDATE()), 1), INTERVAL (QUARTER(CURDATE()) - 1) QUARTER)",
    )
    .replace(/INTERVAL\s+'(\d+)\s+months'/gi, "INTERVAL $1 MONTH")
    .replace(/INTERVAL\s+'(\d+)\s+days'/gi, "INTERVAL $1 DAY")
    .replace(/\bCURRENT_DATE\b/g, "CURDATE()")
    .replace(/\bILIKE\b/g, "LIKE")
    .replace(/::numeric/gi, "")
    .replace(/\bTRUE\b/g, "1")
    .replace(/\bFALSE\b/g, "0");
}
