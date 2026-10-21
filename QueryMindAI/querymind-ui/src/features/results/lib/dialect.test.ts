import { describe, expect, it } from "vitest";
import { transpile } from "@/features/results/lib/dialect";

describe("transpile", () => {
  it("returns PostgreSQL unchanged apart from trimming", () => {
    expect(transpile("  SELECT 1;  ", "PostgreSQL")).toBe("SELECT 1;");
  });

  it("rewrites PostgreSQL date functions and intervals for MySQL", () => {
    const sql = "WHERE d >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '6 months'";
    expect(transpile(sql, "MySQL")).toBe("WHERE d >= DATE_FORMAT(CURDATE(), '%Y-%m-01') - INTERVAL 6 MONTH");
  });

  it("drops ::numeric casts and maps booleans", () => {
    expect(transpile("SELECT price::numeric WHERE active = TRUE", "MySQL")).toBe("SELECT price WHERE active = 1");
  });
});
