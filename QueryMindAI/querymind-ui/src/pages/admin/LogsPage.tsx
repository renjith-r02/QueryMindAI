import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { useHistoryStore } from "@/features/history/store";
import { formatWhen } from "@/lib/format";

const HEADINGS = ["When", "Question", "Status", "Time", "Feedback"];

export function LogsPage() {
  const history = useHistoryStore((state) => state.history);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <PageHeader title="Logs" description="Every question asked in this browser session and the seeded examples." />
      <Card as="div" className="overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="bg-paper text-xs tracking-wide text-muted uppercase">
            <tr>
              {HEADINGS.map((heading) => (
                <th key={heading} className="px-4 py-3 font-medium">
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {history.map((run) => (
              <tr key={run.id} className="border-t border-line">
                <td className="px-4 py-3 whitespace-nowrap">{formatWhen(run.at)}</td>
                <td className="px-4 py-3">{run.question}</td>
                <td className="px-4 py-3 capitalize">{run.status}</td>
                <td className="px-4 py-3">{run.ms} ms</td>
                <td className="px-4 py-3">{run.feedback ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
