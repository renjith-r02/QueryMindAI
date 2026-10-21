import { create } from "zustand";
import { persist } from "zustand/middleware";

/** How many example questions are pinned before the user changes anything. */
export const DEFAULT_PIN_COUNT = 4;

type PinnedStore = {
  /** null until the user pins or unpins something; until then the defaults apply. */
  pinned: string[] | null;
  pin: (question: string, current: string[]) => void;
  unpin: (question: string, current: string[]) => void;
};

export const usePinnedStore = create<PinnedStore>()(
  persist(
    (set) => ({
      pinned: null,
      pin: (question, current) => set({ pinned: current.includes(question) ? current : [...current, question] }),
      unpin: (question, current) => set({ pinned: current.filter((item) => item !== question) }),
    }),
    { name: "querymind-pinned", version: 1 },
  ),
);

/** The pinned questions, falling back to the first example questions. */
export function usePinnedQuestions(examples: string[]): string[] {
  const pinned = usePinnedStore((state) => state.pinned);
  return pinned ?? examples.slice(0, DEFAULT_PIN_COUNT);
}
