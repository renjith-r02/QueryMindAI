import type { Column, Row } from "@/types/query";

/**
 * Pick the graph views that suit a query result.
 *
 * Columns are profiled as a time axis, a category (label), a numeric measure, or an
 * identifier (numeric ids are labels, not measures). The data's shape then decides
 * the forms: one row is a stat, a time axis is a line, categories are bars, two
 * measures without a label are a scatter, a lone measure is a histogram. The first
 * view returned is the recommended default.
 */

export type ColumnRole = "time" | "category" | "measure" | "identifier";

export type ChartKind =
  "stat" | "line" | "area" | "column" | "bar" | "groupedColumn" | "stackedColumn" | "pie" | "scatter" | "histogram";

export type ChartView = {
  kind: ChartKind;
  label: string;
  /** Column key for the x axis / categories (scatter: the x measure). */
  x?: string;
  /** Measure column keys, one per series. */
  series: string[];
};

export type ChartPlan = {
  views: ChartView[];
  /** Rows to plot; category charts are capped so bars stay readable. */
  rows: Row[];
  notes: string[];
};

/** All-pairs and stacked forms stay legible up to four series (see palette validation). */
export const MAX_SERIES = 4;
export const MAX_CATEGORIES = 30;
const PIE_SLICES = { min: 3, max: 6 };

const TIME_NAME = /(^|_)(date|day|week|month|quarter|year|period|time)s?($|_)|_at$|^at$/i;
const ID_NAME = /(^|_)(id|ids|key|code|number|no|zip|phone)$/i;
const LABEL_NAME = /(name|title|label)/i;
const ISO_DATE = /^\d{4}-\d{2}(-\d{2})?([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/;
const MONTH_YEAR = /^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{4}$/i;
const QUARTER = /^(\d{4}[- ]?Q[1-4]|Q[1-4][- ]?\d{4})$/i;

export function columnRole(column: Column, rows: Row[]): ColumnRole {
  const values = rows.map((row) => row[column.key]).filter((value) => value !== "" && value !== undefined);
  const allNumbers = values.length > 0 && values.every((value) => typeof value === "number");

  if (allNumbers) {
    if (TIME_NAME.test(column.key) && values.every((v) => Number.isInteger(v) && Number(v) >= 1900)) return "time";
    return ID_NAME.test(column.key) ? "identifier" : "measure";
  }
  const strings = values.map(String);
  if (strings.length > 0 && strings.every((v) => ISO_DATE.test(v) || MONTH_YEAR.test(v) || QUARTER.test(v))) {
    return "time";
  }
  return TIME_NAME.test(column.key) && strings.length > 0 ? "time" : "category";
}

export function planCharts(columns: Column[], rows: Row[]): ChartPlan {
  const notes: string[] = [];
  if (rows.length === 0 || columns.length === 0) return { views: [], rows, notes };

  const roles = new Map(columns.map((column) => [column.key, columnRole(column, rows)]));
  const keysWith = (role: ColumnRole) => columns.filter((c) => roles.get(c.key) === role).map((c) => c.key);

  let measures = keysWith("measure");
  if (measures.length === 0) return { views: [], rows, notes };
  if (measures.length > MAX_SERIES) {
    notes.push(`Showing the first ${MAX_SERIES} of ${measures.length} numeric columns.`);
    measures = measures.slice(0, MAX_SERIES);
  }

  if (rows.length === 1) {
    return { views: [{ kind: "stat", label: "Value", series: measures }], rows, notes };
  }

  const time = keysWith("time")[0];
  const categories = keysWith("category");
  const label = time ?? categories.find((key) => LABEL_NAME.test(key)) ?? categories[0] ?? keysWith("identifier")[0];

  if (!label) {
    return { views: unlabelledViews(measures, rows.length), rows, notes };
  }

  if (label === time) {
    const views: ChartView[] =
      measures.length === 1
        ? [
            { kind: "line", label: "Line", x: label, series: measures },
            { kind: "area", label: "Area", x: label, series: measures },
            { kind: "column", label: "Columns", x: label, series: measures },
          ]
        : [
            { kind: "line", label: "Lines", x: label, series: measures },
            { kind: "groupedColumn", label: "Grouped columns", x: label, series: measures },
          ];
    return { views, rows, notes };
  }

  let plotted = rows;
  if (rows.length > MAX_CATEGORIES) {
    plotted = rows.slice(0, MAX_CATEGORIES);
    notes.push(`Showing the first ${MAX_CATEGORIES} of ${rows.length} rows; the table has all of them.`);
  }
  return { views: categoryViews(label, measures, plotted), rows: plotted, notes };
}

function categoryViews(label: string, measures: string[], rows: Row[]): ChartView[] {
  if (measures.length === 1) {
    const longLabels = rows.some((row) => String(row[label] ?? "").length > 14);
    const column: ChartView = { kind: "column", label: "Columns", x: label, series: measures };
    const bar: ChartView = { kind: "bar", label: "Bars", x: label, series: measures };
    const views = rows.length > 8 || longLabels ? [bar, column] : [column, bar];

    const values = rows.map((row) => row[measures[0]!]);
    const positive = values.every((value) => typeof value === "number" && value > 0);
    if (positive && rows.length >= PIE_SLICES.min && rows.length <= PIE_SLICES.max) {
      views.push({ kind: "pie", label: "Share", x: label, series: measures });
    }
    return views;
  }

  const views: ChartView[] = [{ kind: "groupedColumn", label: "Grouped columns", x: label, series: measures }];
  const nonNegative = rows.every((row) => measures.every((key) => typeof row[key] !== "number" || row[key] >= 0));
  if (nonNegative) views.push({ kind: "stackedColumn", label: "Stacked columns", x: label, series: measures });
  if (rows.length >= 5) views.push(scatter(measures));
  return views;
}

function unlabelledViews(measures: string[], rowCount: number): ChartView[] {
  if (measures.length >= 2) return [scatter(measures)];
  return rowCount >= 5 ? [{ kind: "histogram", label: "Distribution", series: measures }] : [];
}

function scatter(measures: string[]): ChartView {
  return { kind: "scatter", label: "Scatter", x: measures[0], series: [measures[1]!] };
}

export type HistogramBin = { range: string; count: number };

/** Equal-width bins (Sturges' rule, 5–20 bins) over the numeric values of one column. */
export function histogram(rows: Row[], key: string, format: (value: number) => string = String): HistogramBin[] {
  const values = rows.map((row) => row[key]).filter((value): value is number => typeof value === "number");
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [{ range: format(min), count: values.length }];

  const binCount = Math.min(20, Math.max(5, Math.ceil(Math.log2(values.length)) + 1));
  const width = (max - min) / binCount;
  const counts = new Array<number>(binCount).fill(0);
  for (const value of values) {
    counts[Math.min(binCount - 1, Math.floor((value - min) / width))]! += 1;
  }
  return counts.map((count, index) => ({
    range: `${format(min + index * width)}–${format(min + (index + 1) * width)}`,
    count,
  }));
}
