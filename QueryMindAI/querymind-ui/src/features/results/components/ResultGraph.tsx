import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Check, LayoutDashboard } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useDashboardStore } from "@/features/dashboard/store";
import { ChartCanvas, StatTiles } from "@/features/results/components/ChartCanvas";
import { describeView, labelLookup } from "@/features/results/lib/chartLabels";
import { planCharts, type ChartView } from "@/features/results/lib/chartViews";
import { cn } from "@/lib/cn";
import type { Column, Row } from "@/types/query";

/** Where the result came from, so the chart can be saved to the dashboard. */
export type GraphSource = { runId: string; question: string; sql: string };

/** Graph view of a query result: picks suitable chart types and lets the user switch between them. */
export function ResultGraph({ columns, rows, source }: { columns: Column[]; rows: Row[]; source?: GraphSource }) {
  const plan = useMemo(() => planCharts(columns, rows), [columns, rows]);
  const [selected, setSelected] = useState(0);
  const view = plan.views[selected] ?? plan.views[0];
  if (!view) return null;

  const labelOf = labelLookup(columns);
  const save = source ? (
    <SaveButton source={source} view={view} columns={columns} rows={plan.rows} notes={plan.notes} />
  ) : null;

  if (view.kind === "stat") {
    return (
      <section aria-label="Graph view" className="flex flex-col gap-3">
        {save ? <div className="flex justify-end">{save}</div> : null}
        <StatTiles view={view} rows={rows} labelOf={labelOf} />
      </section>
    );
  }

  return (
    <Card className="px-4 py-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">Graph view</h2>
          <p className="text-xs text-muted">{describeView(view, labelOf)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {plan.views.length > 1 ? (
            <div role="group" aria-label="Chart type" className="flex flex-wrap gap-1 rounded-xl bg-paper p-1">
              {plan.views.map((option, index) => (
                <button
                  key={option.kind}
                  type="button"
                  aria-pressed={option === view}
                  onClick={() => setSelected(index)}
                  className={cn(
                    "min-h-9 rounded-lg px-3 text-xs font-medium text-muted",
                    option === view && "bg-surface text-ink shadow-sm",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}
          {save}
        </div>
      </div>
      <div className="h-80">
        <ChartCanvas view={view} rows={plan.rows} labelOf={labelOf} />
      </div>
      {plan.notes.map((note) => (
        <p key={note} className="mt-2 text-xs text-muted">
          {note}
        </p>
      ))}
    </Card>
  );
}

function SaveButton({
  source,
  view,
  columns,
  rows,
  notes,
}: {
  source: GraphSource;
  view: ChartView;
  columns: Column[];
  rows: Row[];
  notes: string[];
}) {
  const add = useDashboardStore((state) => state.add);
  const saved = useDashboardStore((state) =>
    state.tiles.some((tile) => tile.runId === source.runId && tile.view.kind === view.kind),
  );

  if (saved) {
    return (
      <Link
        to="/dashboard"
        className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-medium text-ok hover:bg-ok-soft"
      >
        <Check className="size-4" />
        Saved · View dashboard
      </Link>
    );
  }
  return (
    <Button onClick={() => add({ ...source, view, columns, rows, notes })}>
      <LayoutDashboard className="size-4" />
      Save to dashboard
    </Button>
  );
}
