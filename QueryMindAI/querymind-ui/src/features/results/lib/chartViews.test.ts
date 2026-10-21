import { describe, expect, it } from "vitest";
import { columnRole, histogram, MAX_CATEGORIES, planCharts } from "@/features/results/lib/chartViews";
import type { Column, Row } from "@/types/query";

const col = (key: string): Column => ({ key, label: key });
const kinds = (columns: Column[], rows: Row[]) => planCharts(columns, rows).views.map((view) => view.kind);

describe("columnRole", () => {
  it("separates measures, identifiers, time and categories", () => {
    const rows = [
      { product_id: 1, revenue: 10.5, month: "2026-01", year: 2026, name: "Hat", placed_at: "x" },
      { product_id: 2, revenue: 3, month: "2026-02", year: 2025, name: "Shoe", placed_at: "y" },
    ];
    expect(columnRole(col("product_id"), rows)).toBe("identifier");
    expect(columnRole(col("revenue"), rows)).toBe("measure");
    expect(columnRole(col("month"), rows)).toBe("time");
    expect(columnRole(col("year"), rows)).toBe("time");
    expect(columnRole(col("name"), rows)).toBe("category");
    expect(columnRole(col("placed_at"), rows)).toBe("time");
  });

  it("recognises month names and quarters", () => {
    expect(columnRole(col("period"), [{ period: "Jan 2026" }, { period: "Feb 2026" }])).toBe("time");
    expect(columnRole(col("q"), [{ q: "2026-Q1" }, { q: "2026-Q2" }])).toBe("time");
  });
});

describe("planCharts", () => {
  it("has no graph for empty or text-only results", () => {
    expect(kinds([col("a")], [])).toEqual([]);
    expect(kinds([col("a")], [{ a: "x" }, { a: "y" }])).toEqual([]);
  });

  it("shows a single row as a stat", () => {
    const plan = planCharts([col("total_amount"), col("orders")], [{ total_amount: 5, orders: 2 }]);
    expect(plan.views).toEqual([{ kind: "stat", label: "Value", series: ["total_amount", "orders"] }]);
  });

  it("draws time series as lines first", () => {
    const rows = [
      { month: "2026-01", revenue: 1 },
      { month: "2026-02", revenue: 2 },
    ];
    expect(kinds([col("month"), col("revenue")], rows)).toEqual(["line", "area", "column"]);
    const two = rows.map((row) => ({ ...row, orders: 3 }));
    expect(kinds([col("month"), col("revenue"), col("orders")], two)).toEqual(["line", "groupedColumn"]);
  });

  it("offers columns, bars and share for a few categories", () => {
    const rows = ["A", "B", "C"].map((category, index) => ({ category, revenue: index + 1 }));
    expect(kinds([col("category"), col("revenue")], rows)).toEqual(["column", "bar", "pie"]);
  });

  it("prefers horizontal bars for many or long labels and drops share", () => {
    const rows = Array.from({ length: 10 }, (_, index) => ({ category: `C${index}`, revenue: index + 1 }));
    expect(kinds([col("category"), col("revenue")], rows)).toEqual(["bar", "column"]);
    const long = [
      { product_name: "Flexo Adjustable Dumbbell Pair", revenue: 2 },
      { product_name: "Hat", revenue: 1 },
    ];
    expect(kinds([col("product_name"), col("revenue")], long)).toEqual(["bar", "column"]);
  });

  it("does not offer share when a value is zero or negative", () => {
    const rows = [
      { c: "A", v: 1 },
      { c: "B", v: 0 },
      { c: "C", v: 2 },
    ];
    expect(kinds([col("c"), col("v")], rows)).not.toContain("pie");
  });

  it("labels by a name column and ignores numeric ids as measures", () => {
    const columns = ["product_id", "sku", "product_name", "net_revenue"].map(col);
    const rows = [
      { product_id: 84, sku: "FIT", product_name: "Dumbbells", net_revenue: 6970.25 },
      { product_id: 89, sku: "CMP", product_name: "Tent", net_revenue: 6080.44 },
    ];
    expect(planCharts(columns, rows).views[0]).toEqual({
      kind: "column",
      label: "Columns",
      x: "product_name",
      series: ["net_revenue"],
    });
  });

  it("groups and stacks several measures per category", () => {
    const rows = Array.from({ length: 5 }, (_, i) => ({ c: `C${i}`, sold: i + 1, returned: i }));
    expect(kinds([col("c"), col("sold"), col("returned")], rows)).toEqual([
      "groupedColumn",
      "stackedColumn",
      "scatter",
    ]);
  });

  it("caps series and categories with notes", () => {
    const columns = [col("c"), ...["a", "b", "d", "e", "f"].map(col)];
    const rows = Array.from({ length: MAX_CATEGORIES + 5 }, (_, i) => ({ c: `C${i}`, a: 1, b: 2, d: 3, e: 4, f: 5 }));
    const plan = planCharts(columns, rows);
    expect(plan.views[0]?.series).toEqual(["a", "b", "d", "e"]);
    expect(plan.rows).toHaveLength(MAX_CATEGORIES);
    expect(plan.notes).toHaveLength(2);
  });

  it("uses scatter or histogram when there is no label", () => {
    const pairs = Array.from({ length: 6 }, (_, i) => ({ price: i, quantity: i * 2 }));
    expect(planCharts([col("price"), col("quantity")], pairs).views).toEqual([
      { kind: "scatter", label: "Scatter", x: "price", series: ["quantity"] },
    ]);
    expect(kinds([col("price")], pairs)).toEqual(["histogram"]);
  });
});

describe("histogram", () => {
  it("bins values into equal-width ranges", () => {
    const rows = Array.from({ length: 10 }, (_, i) => ({ v: i }));
    const bins = histogram(rows, "v");
    expect(bins).toHaveLength(5);
    expect(bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(10);
    expect(bins[0]?.range).toBe("0–1.8");
  });

  it("returns one bin when all values are equal", () => {
    expect(histogram([{ v: 3 }, { v: 3 }], "v")).toEqual([{ range: "3", count: 2 }]);
  });
});
