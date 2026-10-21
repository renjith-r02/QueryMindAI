import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAskStore } from "@/features/ask/store";
import { useHistoryStore } from "@/features/history/store";

describe("useAskStore", () => {
  // The API layer loads mocks lazily; load them up front so fake timers see their delays.
  beforeAll(() => import("@/mocks/handlers"));
  afterEach(() => vi.useRealTimers());

  beforeEach(() => {
    vi.useFakeTimers();
    useHistoryStore.setState({ history: [] });
    useAskStore.setState({ phase: { kind: "idle" } });
  });

  it("records a successful run and shows it", async () => {
    const pending = useAskStore.getState().ask("Orders by shipping method");
    expect(useAskStore.getState().phase.kind).toBe("loading");
    await vi.runAllTimersAsync();
    await pending;

    const run = useHistoryStore.getState().history[0];
    expect(run?.status).toBe("success");
    expect(useAskStore.getState().phase).toEqual({ kind: "run", runId: run?.id });
  });

  it("collects live progress steps, updating each in place", async () => {
    const pending = useAskStore.getState().ask("Product sales summary");
    await vi.advanceTimersByTimeAsync(800);

    const { phase } = useAskStore.getState();
    if (phase.kind !== "loading") throw new Error(`expected loading, got ${phase.kind}`);
    expect(phase.steps.map((step) => [step.id, step.status])).toEqual([
      ["retrieve", "done"],
      ["schema", "done"],
      ["generate-1", "done"],
      ["execute-1-1", "failed"],
      ["generate-2", "running"],
    ]);

    await vi.runAllTimersAsync();
    await pending;
    expect(useHistoryStore.getState().history[0]?.status).toBe("healed");
  });

  it("ignores a superseded question", async () => {
    const first = useAskStore.getState().ask("Orders by shipping method");
    const second = useAskStore.getState().ask("Returns by reason");
    await vi.runAllTimersAsync();
    await Promise.all([first, second]);

    const { history } = useHistoryStore.getState();
    expect(history.map((run) => run.question)).toEqual(["Returns by reason"]);
  });

  it("records the chosen clarification", async () => {
    const pending = useAskStore.getState().ask("Show total amount last month");
    await vi.runAllTimersAsync();
    await pending;
    expect(useAskStore.getState().phase.kind).toBe("clarify");

    useAskStore.getState().choose("orders");
    expect(useHistoryStore.getState().history[0]?.sql).toContain("total_amount");
  });
});
