import { beforeEach, describe, expect, it } from "vitest";
import { MAX_TILE_ROWS, useDashboardStore, type NewTile } from "@/features/dashboard/store";

const store = () => useDashboardStore.getState();

function tile(overrides: Partial<NewTile> = {}): NewTile {
  return {
    question: "Revenue by category",
    sql: "SELECT 1",
    runId: "run-1",
    view: { kind: "column", label: "Columns", x: "category", series: ["revenue"] },
    columns: [
      { key: "category", label: "Category" },
      { key: "revenue", label: "Revenue" },
      { key: "notes", label: "Notes" },
    ],
    rows: [
      { category: "Shoes", revenue: 10, notes: "x" },
      { category: "Hats", revenue: 5, notes: "y" },
    ],
    notes: [],
    ...overrides,
  };
}

describe("useDashboardStore", () => {
  beforeEach(() => useDashboardStore.setState({ tiles: [] }));

  it("saves a snapshot of only the plotted columns", () => {
    const id = store().add(tile());
    const [saved] = store().tiles;
    expect(saved).toMatchObject({ id, title: "Revenue by category", runId: "run-1" });
    expect(saved?.columns.map((c) => c.key)).toEqual(["category", "revenue"]);
    expect(saved?.rows).toEqual([
      { category: "Shoes", revenue: 10 },
      { category: "Hats", revenue: 5 },
    ]);
  });

  it("caps stored rows and says so", () => {
    const rows = Array.from({ length: MAX_TILE_ROWS + 1 }, (_, i) => ({ category: `C${i}`, revenue: i }));
    store().add(tile({ rows }));
    expect(store().tiles[0]?.rows).toHaveLength(MAX_TILE_ROWS);
    expect(store().tiles[0]?.notes).toEqual([`Saved the first ${MAX_TILE_ROWS} of ${MAX_TILE_ROWS + 1} rows.`]);
  });

  it("renames, reorders and removes", () => {
    const a = store().add(tile({ runId: "a" }));
    const b = store().add(tile({ runId: "b" }));
    store().rename(a, "Top categories");
    store().move(b, -1);
    expect(store().tiles.map((t) => t.id)).toEqual([b, a]);
    expect(store().tiles[1]?.title).toBe("Top categories");

    store().move(b, -1); // already first: no change
    expect(store().tiles.map((t) => t.id)).toEqual([b, a]);

    store().remove(b);
    expect(store().tiles.map((t) => t.id)).toEqual([a]);
  });
});
