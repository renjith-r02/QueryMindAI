import { describe, expect, it } from "vitest";
import { DEFAULT_POLICY } from "@/mocks/guardrails";
import { capLimit, interpret } from "@/mocks/interpret";

const guards = DEFAULT_POLICY;

describe("capLimit", () => {
  it("lowers an existing LIMIT to the maximum", () => {
    expect(capLimit("SELECT 1 LIMIT 50;", 10)).toBe("SELECT 1 LIMIT 10;");
  });

  it("appends a LIMIT when the query has none", () => {
    expect(capLimit("SELECT 1;", 10)).toBe("SELECT 1\nLIMIT 10;");
  });
});

describe("interpret", () => {
  it("blocks destructive questions", () => {
    expect(interpret("delete all orders", guards).kind).toBe("blocked");
  });

  it("blocks sensitive fields only while that rule is enabled", () => {
    expect(interpret("show customer password", guards).kind).toBe("blocked");
    const rules = guards.question_rules.map((rule) =>
      rule.id === "sensitive-data" ? { ...rule, enabled: false } : rule,
    );
    expect(interpret("show customer password", { ...guards, question_rules: rules }).kind).toBe("result");
  });

  it("asks to clarify an ambiguous amount", () => {
    const outcome = interpret("Show total amount last month", guards);
    expect(outcome.kind).toBe("clarify");
  });

  it("returns a self-heal outcome with the broken SQL", () => {
    const outcome = interpret("Product sales summary", guards);
    expect(outcome.kind).toBe("heal");
    if (outcome.kind === "heal") expect(outcome.result.heal?.brokenSql).toContain("'20'");
  });

  it("returns unknown for unrelated questions", () => {
    expect(interpret("what is the weather", guards).kind).toBe("unknown");
  });
});
