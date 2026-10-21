import { Notice } from "@/components/ui/Notice";
import type { Run } from "@/types/run";

export function BlockedNotice({ run }: { run: Run }) {
  return (
    <Notice tone="danger">
      <h2 className="text-base font-semibold text-danger">Query blocked</h2>
      <p className="mt-2">{run.reason}</p>
      <p className="mt-2 text-muted">Question: {run.question}</p>
    </Notice>
  );
}
