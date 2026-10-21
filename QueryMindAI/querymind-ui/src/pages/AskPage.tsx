import { EmptyState, Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { BlockedNotice } from "@/features/ask/components/BlockedNotice";
import { ClarifyOptions } from "@/features/ask/components/ClarifyOptions";
import { Composer } from "@/features/ask/components/Composer";
import { RunProgress } from "@/features/ask/components/RunProgress";
import { useAskStore } from "@/features/ask/store";
import { useRun } from "@/features/history/store";
import { QueryView } from "@/features/results/components/QueryView";

export function AskPage() {
  const phase = useAskStore((state) => state.phase);
  const choose = useAskStore((state) => state.choose);
  const run = useRun(phase.kind === "run" ? phase.runId : undefined);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        title="Ask a question"
        description="Ambiguous columns are clarified before SQL is generated. Failed queries are fixed and retried."
      />
      <Composer />
      {phase.kind === "idle" || (phase.kind === "run" && !run) ? (
        <EmptyState>Ask about revenue, stock, shipping, returns, or try “Show total amount last month”.</EmptyState>
      ) : null}
      {phase.kind === "loading" ? (
        <RunProgress question={phase.question} startedAt={phase.startedAt} steps={phase.steps} />
      ) : null}
      {phase.kind === "unknown" ? (
        <Notice>
          {phase.message ? (
            <>
              <p className="font-medium">“{phase.question}” can’t be answered from the available data.</p>
              <p className="mt-1 text-muted">{phase.message}</p>
            </>
          ) : (
            <>
              I can answer product, order, customer, inventory, and return questions for this sample store. Try one of
              the suggestions on Home. “{phase.question}” did not match a known metric.
            </>
          )}
        </Notice>
      ) : null}
      {phase.kind === "error" ? (
        <Notice tone="danger">
          <p className="font-medium text-danger">The question could not be answered.</p>
          <p className="mt-1">{phase.message}</p>
        </Notice>
      ) : null}
      {phase.kind === "clarify" ? (
        <ClarifyOptions question={phase.question} options={phase.options} onChoose={choose} />
      ) : null}
      {run?.status === "blocked" ? <BlockedNotice run={run} /> : null}
      {run && run.status !== "blocked" ? <QueryView run={run} /> : null}
    </div>
  );
}
