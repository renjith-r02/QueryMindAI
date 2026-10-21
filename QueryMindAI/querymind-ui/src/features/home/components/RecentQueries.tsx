import { useState } from "react";
import { Pin, PinOff } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Notice";
import { Tabs } from "@/components/ui/Tabs";
import { useAskNavigation } from "@/features/ask/hooks/useAskNavigation";
import { StatusBadge } from "@/features/history/components/StatusBadge";
import { useHistoryStore } from "@/features/history/store";
import { usePinnedStore } from "@/features/pinned/store";
import { cn } from "@/lib/cn";
import { formatWhen } from "@/lib/format";
import type { RunStatus } from "@/types/run";

const RECENT_LIMIT = 6;

type RecentTab = "all" | RunStatus;
const RECENT_TABS: { id: RecentTab; label: string }[] = [
  { id: "all", label: "All" },
  { id: "success", label: "Answered" },
  { id: "healed", label: "Self-healed" },
  { id: "blocked", label: "Blocked" },
];
const EMPTY_TAB: Record<RecentTab, string> = {
  all: "No queries yet. Ask a question above.",
  success: "No answered queries yet.",
  healed: "No queries needed a retry.",
  blocked: "No queries were blocked by guardrails.",
};

/** Latest questions, in tabs by outcome, with a pin button on each. */
export function RecentQueries({ pinned }: { pinned: string[] }) {
  const history = useHistoryStore((state) => state.history);
  const pin = usePinnedStore((state) => state.pin);
  const unpin = usePinnedStore((state) => state.unpin);
  const { open } = useAskNavigation();
  const [tab, setTab] = useState<RecentTab>("all");

  const recent = (tab === "all" ? history : history.filter((run) => run.status === tab)).slice(0, RECENT_LIMIT);
  const tabs = RECENT_TABS.map((item) => ({
    ...item,
    count: item.id === "all" ? history.length : history.filter((run) => run.status === item.id).length,
  }));

  return (
    <section aria-labelledby="recent-heading">
      <h2 id="recent-heading" className="mb-2 text-sm font-semibold">
        Recent queries
      </h2>
      <Tabs label="Recent queries by outcome" items={tabs} value={tab} onChange={setTab}>
        {recent.length === 0 ? (
          <EmptyState>{EMPTY_TAB[tab]}</EmptyState>
        ) : (
          <Card as="ul" className="divide-y divide-line overflow-hidden">
            {recent.map((run) => {
              const isPinned = pinned.includes(run.question);
              return (
                <li key={run.id} className="flex items-center gap-2 pr-2 hover:bg-paper">
                  <button
                    type="button"
                    className="flex min-h-14 min-w-0 flex-1 flex-col items-start justify-center gap-1 px-4 py-3 text-left sm:flex-row sm:items-center sm:justify-between"
                    onClick={() => open(run.id)}
                  >
                    <span className="font-medium">{run.question}</span>
                    <span className="flex items-center gap-3 text-sm text-muted">
                      {tab === "all" ? <StatusBadge status={run.status} /> : null}
                      {formatWhen(run.at)}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={isPinned ? `Unpin "${run.question}"` : `Pin "${run.question}"`}
                    aria-pressed={isPinned}
                    title={isPinned ? "Unpin" : "Pin"}
                    onClick={() => (isPinned ? unpin(run.question, pinned) : pin(run.question, pinned))}
                    className={cn(
                      "inline-flex size-9 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-surface hover:text-ink",
                      isPinned && "text-primary",
                    )}
                  >
                    {isPinned ? <PinOff className="size-4" /> : <Pin className="size-4" />}
                  </button>
                </li>
              );
            })}
          </Card>
        )}
      </Tabs>
    </section>
  );
}
