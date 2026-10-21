import { interpret } from "@/mocks/interpret";
import type { Run } from "@/types/run";
import type { GuardSettings } from "@/types/settings";

const SEED: Pick<Run, "id" | "question" | "at" | "ms">[] = [
  {
    id: "seed-products",
    question: "Top 10 products by revenue last quarter",
    at: Date.UTC(2026, 4, 19, 14, 24),
    ms: 1180,
  },
  { id: "seed-trend", question: "Monthly sales trend for 2026", at: Date.UTC(2026, 4, 18, 16, 2), ms: 960 },
  { id: "seed-stock", question: "Low stock products by category", at: Date.UTC(2026, 4, 17, 11, 40), ms: 740 },
];

/** Example history shown on first visit, before the user has asked anything. */
export function seedHistory(settings: GuardSettings): Run[] {
  return SEED.map((seed) => {
    const outcome = interpret(seed.question, settings);
    const result = outcome.kind === "result" ? outcome.result : null;
    return {
      ...seed,
      status: "success",
      sql: result?.sql ?? "",
      explanation: result?.explanation ?? "",
      columns: result?.columns ?? [],
      rows: result?.rows ?? [],
    };
  });
}
