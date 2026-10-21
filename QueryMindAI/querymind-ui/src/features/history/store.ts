import { create } from "zustand";
import { persist } from "zustand/middleware";
import { readLegacyState } from "@/lib/storage";
import type { Feedback, Run } from "@/types/run";

export const MAX_HISTORY = 40;

type HistoryStore = {
  history: Run[];
  addRun: (run: Run) => void;
  setFeedback: (id: string, value: Feedback) => void;
  /** Show example runs on first visit. No-op once the user has history. */
  seedIfEmpty: (runs: Run[]) => void;
};

export const useHistoryStore = create<HistoryStore>()(
  persist(
    (set, get) => ({
      history: readLegacyState().history ?? [],
      addRun: (run) => set((state) => ({ history: [run, ...state.history].slice(0, MAX_HISTORY) })),
      setFeedback: (id, value) =>
        set((state) => ({
          history: state.history.map((run) => (run.id === id ? { ...run, feedback: value } : run)),
        })),
      seedIfEmpty: (runs) => {
        if (get().history.length === 0) set({ history: runs });
      },
    }),
    { name: "querymind-history", version: 1 },
  ),
);

export function useRun(id: string | undefined): Run | undefined {
  return useHistoryStore((state) => (id ? state.history.find((run) => run.id === id) : undefined));
}
