import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { useAskNavigation } from "@/features/ask/hooks/useAskNavigation";
import { StatusBadge } from "@/features/history/components/StatusBadge";
import { useHistoryStore } from "@/features/history/store";
import { formatWhen } from "@/lib/format";

export function HistoryPage() {
  const history = useHistoryStore((state) => state.history);
  const { open } = useAskNavigation();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <PageHeader title="History" description="Questions from this browser stay on this device." />
      <Card as="ul" className="divide-y divide-line overflow-hidden">
        {history.map((run) => (
          <li key={run.id}>
            <button
              type="button"
              className="flex w-full flex-col gap-1 px-4 py-4 text-left hover:bg-paper sm:flex-row sm:items-center sm:justify-between"
              onClick={() => open(run.id)}
            >
              <span>
                <span className="block font-medium">{run.question}</span>
                <span className="text-sm text-muted">{formatWhen(run.at)}</span>
              </span>
              <StatusBadge status={run.status} />
            </button>
          </li>
        ))}
      </Card>
    </div>
  );
}
