import { create } from "zustand";
import { askQuestion } from "@/api/query";
import { useHistoryStore } from "@/features/history/store";
import type { ProgressStep } from "@/types/progress";
import type { ClarifyOption, QueryResult } from "@/types/query";
import type { Run, RunStatus } from "@/types/run";

export type AskPhase =
  | { kind: "idle" }
  | { kind: "loading"; question: string; startedAt: number; steps: ProgressStep[] }
  | { kind: "clarify"; question: string; options: ClarifyOption[] }
  | { kind: "run"; runId: string }
  | { kind: "unknown"; question: string; message?: string }
  | { kind: "error"; question: string; message: string };

type AskStore = {
  phase: AskPhase;
  /** `fresh` bypasses the semantic cache. */
  ask: (question: string, options?: { fresh?: boolean }) => Promise<void>;
  choose: (optionId: string) => void;
  openRun: (id: string) => void;
};

function toRun(question: string, startedAt: number, result: QueryResult, status: RunStatus): Run {
  return {
    id: crypto.randomUUID(),
    question,
    at: Date.now(),
    ms: Date.now() - startedAt,
    status,
    sql: result.sql,
    explanation: result.explanation,
    columns: result.columns,
    rows: result.rows,
    healingNote: result.heal?.note,
    brokenSql: result.heal?.brokenSql,
    answer: result.answer,
    caveats: result.caveats,
    queries: result.queries,
    mergeSql: result.mergeSql,
    intent: result.intent,
    cached: result.cached,
    notExecuted: result.notExecuted,
  };
}

function blockedRun(question: string, startedAt: number, reason: string): Run {
  return {
    id: crypto.randomUUID(),
    question,
    at: Date.now(),
    ms: Date.now() - startedAt,
    status: "blocked",
    sql: "",
    explanation: "",
    columns: [],
    rows: [],
    reason,
  };
}

/** Replace a step with the same id (running -> done/failed), or append a new one. */
function upsert(steps: ProgressStep[], step: ProgressStep): ProgressStep[] {
  const index = steps.findIndex((item) => item.id === step.id);
  return index < 0 ? [...steps, step] : steps.map((item, i) => (i === index ? step : item));
}

let inFlight: AbortController | null = null;

export const useAskStore = create<AskStore>()((set, get) => {
  function record(run: Run) {
    useHistoryStore.getState().addRun(run);
    set({ phase: { kind: "run", runId: run.id } });
  }

  return {
    phase: { kind: "idle" },

    ask: async (question, { fresh = false } = {}) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      // A newer question supersedes any request still running.
      inFlight?.abort();
      const controller = new AbortController();
      inFlight = controller;

      const startedAt = Date.now();
      set({ phase: { kind: "loading", question: trimmed, startedAt, steps: [] } });

      try {
        const outcome = await askQuestion(trimmed, {
          useCache: !fresh,
          signal: controller.signal,
          onProgress: (step) => {
            if (controller.signal.aborted) return;
            set(({ phase }) =>
              phase.kind === "loading" ? { phase: { ...phase, steps: upsert(phase.steps, step) } } : {},
            );
          },
        });
        if (controller.signal.aborted) return;

        switch (outcome.kind) {
          case "unknown":
            set({ phase: { kind: "unknown", question: trimmed, message: outcome.message } });
            break;
          case "clarify":
            set({ phase: { kind: "clarify", question: trimmed, options: outcome.options } });
            break;
          case "blocked":
            record(blockedRun(trimmed, startedAt, outcome.reason));
            break;
          case "heal":
            record(toRun(trimmed, startedAt, outcome.result, "healed"));
            break;
          case "result":
            record(toRun(trimmed, startedAt, outcome.result, "success"));
            break;
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : "Something went wrong.";
        set({ phase: { kind: "error", question: trimmed, message } });
      } finally {
        if (inFlight === controller) inFlight = null;
      }
    },

    choose: (optionId) => {
      const { phase } = get();
      if (phase.kind !== "clarify") return;
      const option = phase.options.find((item) => item.id === optionId);
      if (!option) return;
      record(toRun(phase.question, Date.now(), option.result, "success"));
    },

    openRun: (id) => {
      inFlight?.abort();
      set({ phase: { kind: "run", runId: id } });
    },
  };
});
