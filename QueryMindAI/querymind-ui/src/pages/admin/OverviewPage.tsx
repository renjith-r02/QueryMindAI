import { useLoaderData } from "react-router-dom";
import { getSchema } from "@/api/catalog";
import { Card, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatCard } from "@/components/ui/StatCard";
import { useHistoryStore } from "@/features/history/store";
import { formatWhen } from "@/lib/format";

export async function loader() {
  return { tableCount: (await getSchema()).reduce((count, file) => count + file.tables.length, 0) };
}

export function OverviewPage() {
  const { tableCount } = useLoaderData<typeof loader>();
  const history = useHistoryStore((state) => state.history);
  const blocked = history.filter((run) => run.status === "blocked").length;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader title="Overview" description="Usage of this sample workspace." />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Schema tables" value={tableCount} />
        <StatCard label="Saved questions" value={history.length} />
        <StatCard label="Answered" value={history.length - blocked} />
        <StatCard label="Guardrail blocks" value={blocked} />
      </div>
      <Card className="overflow-hidden">
        <CardHeader title="Recent activity" />
        <ul className="divide-y divide-line">
          {history.slice(0, 5).map((run) => (
            <li key={run.id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <span className="font-medium">{run.question}</span>
              <span className="text-sm text-muted">{formatWhen(run.at)}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
