import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useHistoryStore } from "@/features/history/store";
import { cn } from "@/lib/cn";
import type { Run } from "@/types/run";

const BASE = "inline-flex size-11 items-center justify-center rounded-xl border border-line bg-surface";

export function FeedbackButtons({ run }: { run: Run }) {
  const setFeedback = useHistoryStore((state) => state.setFeedback);

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted">Was this useful?</span>
      <button
        type="button"
        aria-label="Helpful"
        aria-pressed={run.feedback === "up"}
        className={cn(BASE, run.feedback === "up" && "border-primary bg-primary-soft text-primary")}
        onClick={() => setFeedback(run.id, "up")}
      >
        <ThumbsUp className="size-4" />
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        aria-pressed={run.feedback === "down"}
        className={cn(BASE, run.feedback === "down" && "border-danger bg-danger-soft text-danger")}
        onClick={() => setFeedback(run.id, "down")}
      >
        <ThumbsDown className="size-4" />
      </button>
    </div>
  );
}
