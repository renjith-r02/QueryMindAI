import { useEffect, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import type { ProgressStep } from "@/types/progress";

const CONNECTING: ProgressStep = { id: "connect", status: "running", message: "Connecting to QueryMind…" };

/** Live steps while a question is answered, so the page is never blank. */
export function RunProgress({
  question,
  startedAt,
  steps,
}: {
  question: string;
  startedAt: number;
  steps: ProgressStep[];
}) {
  const elapsed = useElapsedSeconds(startedAt);
  const shown = steps.length ? steps : [CONNECTING];
  const current = [...shown].reverse().find((step) => step.status === "running") ?? shown.at(-1)!;

  return (
    <div className="flex flex-col gap-4">
      <Card className="px-4 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">Working on “{question}”</h2>
          <span className="text-xs text-muted tabular-nums" aria-label={`${elapsed} seconds elapsed`}>
            {elapsed}s
          </span>
        </div>
        <ol className="mt-3 flex flex-col gap-2" aria-label="Progress">
          {shown.map((step) => (
            <li key={step.id} className="flex items-start gap-3 text-sm">
              <StepIcon status={step.status} />
              <span
                className={cn(
                  step.status === "running" && "font-medium text-ink",
                  step.status === "done" && "text-muted",
                  step.status === "failed" && "text-danger",
                )}
              >
                {step.message}
              </span>
            </li>
          ))}
        </ol>
        {/* Screen readers hear the current step without the whole list being re-read. */}
        <p className="sr-only" aria-live="polite">
          {current.message}
        </p>
        <p className="mt-3 text-xs text-muted">
          Answers can take up to a minute while the model writes the SQL; a failed query is fixed and retried
          automatically.
        </p>
      </Card>
      <AnswerPlaceholder />
    </div>
  );
}

function StepIcon({ status }: { status: ProgressStep["status"] }) {
  const base = "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full";
  if (status === "running") {
    return (
      <span className={cn(base, "text-primary")} aria-label="In progress">
        <Loader2 className="size-4 animate-spin" />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className={cn(base, "bg-danger-soft text-danger")} aria-label="Failed">
        <X className="size-3.5" />
      </span>
    );
  }
  return (
    <span className={cn(base, "bg-ok-soft text-ok")} aria-label="Done">
      <Check className="size-3.5" />
    </span>
  );
}

/** Grey blocks shaped like the answer, SQL and results that are on the way. */
function AnswerPlaceholder() {
  return (
    <div className="flex flex-col gap-4" aria-hidden="true">
      {[
        ["w-1/4", "w-11/12", "w-3/4"],
        ["w-1/5", "w-full", "w-5/6", "w-2/3"],
      ].map((lines, index) => (
        <Card key={index} className="flex animate-pulse flex-col gap-3 px-4 py-4">
          {lines.map((width, line) => (
            <span key={line} className={cn("h-3 rounded-full bg-line", width, line === 0 && "h-4")} />
          ))}
        </Card>
      ))}
    </div>
  );
}

function useElapsedSeconds(startedAt: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return Math.max(0, Math.floor((now - startedAt) / 1000));
}
