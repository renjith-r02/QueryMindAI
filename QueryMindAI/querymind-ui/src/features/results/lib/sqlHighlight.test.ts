import { describe, expect, it } from "vitest";
import { tokenizeSql } from "@/features/results/lib/sqlHighlight";

describe("tokenizeSql", () => {
  it("flags SQL keywords and keeps the original text", () => {
    const tokens = tokenizeSql("SELECT name FROM products;");
    expect(tokens.map((token) => token.text).join("")).toBe("SELECT name FROM products;");
    expect(tokens.filter((token) => token.keyword).map((token) => token.text)).toEqual(["SELECT", "FROM"]);
  });
});
