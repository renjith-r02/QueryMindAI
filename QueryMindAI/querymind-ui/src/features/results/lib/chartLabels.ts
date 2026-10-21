import type { ChartView } from "@/features/results/lib/chartViews";
import type { Column } from "@/types/query";

export function labelLookup(columns: Column[]): (key: string) => string {
  const labels = new Map(columns.map((column) => [column.key, column.label]));
  return (key) => labels.get(key) ?? key;
}

export function describeView(view: ChartView, labelOf: (key: string) => string): string {
  const measures = view.series.map(labelOf).join(", ");
  if (view.kind === "histogram") return `Distribution of ${measures}`;
  if (view.kind === "scatter") return `${labelOf(view.series[0]!)} against ${labelOf(view.x!)}`;
  if (view.kind === "pie") return `Share of ${measures} by ${labelOf(view.x!)}`;
  return `${measures} by ${labelOf(view.x!)}`;
}
