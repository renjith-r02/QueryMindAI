import { describe, expect, it } from "vitest";
import { ECOMMERCE_MYSQL } from "@/features/datasources/defaults";
import { buildSchemaHeader } from "@/features/datasources/schemaHeader";
import type { DataSourceInput } from "@/features/datasources/types";

describe("buildSchemaHeader", () => {
  it("renders every section in the schema-file comment format", () => {
    const header = buildSchemaHeader(ECOMMERCE_MYSQL);
    const lines = header.split("\n");

    expect(lines[1]).toBe("-- ECOMMERCE  (MySQL)   database: ecommerce");
    expect(lines[3]).toBe("-- PURPOSE");
    for (const heading of [
      "DATA LOCATION MAP",
      "TABLE OVERVIEW",
      "RELATIONSHIPS",
      "ENTITY DIAGRAM (text)",
      "STANDARD JOIN PATHS (MySQL)",
      "QUESTIONS THAT INVOLVE RETURNS",
      "BUSINESS RULES AND QUERY GUIDANCE",
    ]) {
      const index = lines.indexOf(`-- ${heading}`);
      expect(index, heading).toBeGreaterThan(3);
      expect(lines[index - 1]).toMatch(/^-- -{69}$/);
      expect(lines[index + 1]).toMatch(/^-- -{69}$/);
    }
    expect(header).toContain("--   1. Historical revenue: ALWAYS use order_lines.unit_price");
    expect(lines.every((line) => line.startsWith("--"))).toBe(true);
  });

  it("skips empty sections and names access paths per store type", () => {
    const source: DataSourceInput = {
      name: "orders",
      type: "dynamodb",
      enabled: true,
      connection: { region: "us-east-1" },
      sections: { purpose: "Order events.", join_paths: "Query Orders by pk = USER#<id>.", table_overview: "  " },
    };
    const header = buildSchemaHeader(source);
    expect(header).toContain("-- STANDARD ACCESS PATTERNS (DynamoDB)");
    expect(header).not.toContain("TABLE OVERVIEW");
    expect(header.split("\n")[1]).toBe("-- ORDERS  (DynamoDB)   database: orders");
  });
});
