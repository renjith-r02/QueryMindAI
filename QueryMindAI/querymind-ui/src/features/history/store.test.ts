import { beforeEach, describe, expect, it } from "vitest";
import { MAX_HISTORY, useHistoryStore } from "@/features/history/store";
import type { Run } from "@/types/run";

function makeRun(id: string): Run {
  return {
    id,
    question: `Question ${id}`,
    at: 0,
    ms: 0,
    status: "success",
    sql: "",
    explanation: "",
    columns: [],
    rows: [],
  };
}

describe("useHistoryStore", () => {
  beforeEach(() => useHistoryStore.setState({ history: [] }));

  it("adds newest runs first and caps the list", () => {
    for (let index = 0; index < MAX_HISTORY + 5; index += 1) {
      useHistoryStore.getState().addRun(makeRun(String(index)));
    }
    const { history } = useHistoryStore.getState();
    expect(history).toHaveLength(MAX_HISTORY);
    expect(history[0]?.id).toBe(String(MAX_HISTORY + 4));
  });

  it("records feedback on a run", () => {
    useHistoryStore.getState().addRun(makeRun("a"));
    useHistoryStore.getState().setFeedback("a", "up");
    expect(useHistoryStore.getState().history[0]?.feedback).toBe("up");
  });

  it("seeds only when empty", () => {
    useHistoryStore.getState().seedIfEmpty([makeRun("seed")]);
    useHistoryStore.getState().seedIfEmpty([makeRun("other")]);
    expect(useHistoryStore.getState().history.map((run) => run.id)).toEqual(["seed"]);
  });
});
