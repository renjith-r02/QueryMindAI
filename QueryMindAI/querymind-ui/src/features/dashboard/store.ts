import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ChartView } from "@/features/results/lib/chartViews";
import type { Column, Row } from "@/types/query";

/** Rows kept per saved chart, so browser storage stays small. */
export const MAX_TILE_ROWS = 1000;

/** A saved chart: a snapshot of the data at save time, redrawn on the dashboard. */
export type DashboardTile = {
  id: string;
  title: string;
  question: string;
  sql: string;
  /** The run the chart came from; used to show "Saved" on that result. */
  runId: string;
  view: ChartView;
  columns: Column[];
  rows: Row[];
  notes: string[];
  savedAt: number;
};

export type NewTile = Omit<DashboardTile, "id" | "savedAt" | "title"> & { title?: string };

type DashboardStore = {
  tiles: DashboardTile[];
  /** Saves the chart and returns the tile id. */
  add: (tile: NewTile) => string;
  rename: (id: string, title: string) => void;
  remove: (id: string) => void;
  /** Moves a tile one place earlier (-1) or later (+1). */
  move: (id: string, offset: -1 | 1) => void;
};

export const useDashboardStore = create<DashboardStore>()(
  persist(
    (set) => ({
      tiles: [],
      add: (tile) => {
        const id = crypto.randomUUID();
        const keys = [tile.view.x, ...tile.view.series].filter((key): key is string => Boolean(key));
        const notes = [...tile.notes];
        if (tile.rows.length > MAX_TILE_ROWS) {
          notes.push(`Saved the first ${MAX_TILE_ROWS} of ${tile.rows.length} rows.`);
        }
        const saved: DashboardTile = {
          ...tile,
          id,
          title: tile.title?.trim() || tile.question,
          // Keep only the plotted columns of the plotted rows.
          columns: tile.columns.filter((column) => keys.includes(column.key)),
          rows: tile.rows.slice(0, MAX_TILE_ROWS).map((row) => Object.fromEntries(keys.map((k) => [k, row[k] ?? ""]))),
          notes,
          savedAt: Date.now(),
        };
        set((state) => ({ tiles: [...state.tiles, saved] }));
        return id;
      },
      rename: (id, title) =>
        set((state) => ({ tiles: state.tiles.map((tile) => (tile.id === id ? { ...tile, title } : tile)) })),
      remove: (id) => set((state) => ({ tiles: state.tiles.filter((tile) => tile.id !== id) })),
      move: (id, offset) =>
        set((state) => {
          const from = state.tiles.findIndex((tile) => tile.id === id);
          const to = from + offset;
          if (from < 0 || to < 0 || to >= state.tiles.length) return state;
          const tiles = [...state.tiles];
          [tiles[from], tiles[to]] = [tiles[to]!, tiles[from]!];
          return { tiles };
        }),
    }),
    { name: "querymind-dashboard", version: 1 },
  ),
);
