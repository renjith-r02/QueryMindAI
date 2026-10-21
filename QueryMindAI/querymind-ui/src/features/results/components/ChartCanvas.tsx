import type { ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { StatCard } from "@/components/ui/StatCard";
import { seriesColor } from "@/features/results/lib/chartPalette";
import { histogram, type ChartView } from "@/features/results/lib/chartViews";
import { formatCell } from "@/lib/format";
import { themeColor } from "@/lib/theme";
import type { Row } from "@/types/query";

const SURFACE = "#ffffff";
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export function StatTiles({ view, rows, labelOf }: { view: ChartView; rows: Row[]; labelOf: (key: string) => string }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {view.series.map((key) => (
        <StatCard key={key} label={labelOf(key)} value={formatCell(key, rows[0]?.[key] ?? "")} />
      ))}
    </div>
  );
}

/** Draws one chart view. Shared by the results graph and saved dashboard tiles. */
export function ChartCanvas({
  view,
  rows,
  labelOf,
}: {
  view: ChartView;
  rows: Row[];
  labelOf: (key: string) => string;
}) {
  const grid = themeColor("line", "#e3e8ef");
  const tick = { fill: themeColor("muted", "#5e6b7c"), fontSize: 12 };
  const x = view.x ?? "";
  const legend = view.series.length > 1 ? <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} /> : null;
  const tooltip = (
    <Tooltip
      formatter={(value, name, item) => [
        typeof value === "number" ? formatCell(String(item.dataKey ?? name), value) : String(value),
        labelOf(String(name)),
      ]}
    />
  );
  const valueAxis = (props: object = {}) => (
    <YAxis tick={tick} tickFormatter={(v: number) => compact.format(v)} axisLine={false} tickLine={false} {...props} />
  );
  const container = (chart: ReactNode) => (
    <ResponsiveContainer width="100%" height="100%">
      {chart as React.ReactElement}
    </ResponsiveContainer>
  );

  switch (view.kind) {
    case "line":
    case "area": {
      const Series = view.kind === "line" ? LineChart : AreaChart;
      return container(
        <Series data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey={x} tick={tick} tickLine={false} axisLine={{ stroke: grid }} minTickGap={16} />
          {valueAxis()}
          {tooltip}
          {legend}
          {view.series.map((key, index) =>
            view.kind === "line" ? (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={key}
                stroke={seriesColor(index)}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5, stroke: SURFACE, strokeWidth: 2 }}
              />
            ) : (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                name={key}
                stroke={seriesColor(index)}
                strokeWidth={2}
                fill={seriesColor(index)}
                fillOpacity={0.1}
                activeDot={{ r: 5, stroke: SURFACE, strokeWidth: 2 }}
              />
            ),
          )}
        </Series>,
      );
    }

    case "column":
    case "groupedColumn":
    case "stackedColumn":
      return container(
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }} barGap={2}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey={x} tick={tick} tickLine={false} axisLine={{ stroke: grid }} interval="preserveStartEnd" />
          {valueAxis()}
          {tooltip}
          {legend}
          {view.series.map((key, index) => (
            <Bar
              key={key}
              dataKey={key}
              name={key}
              fill={seriesColor(index)}
              maxBarSize={24}
              stackId={view.kind === "stackedColumn" ? "stack" : undefined}
              stroke={view.kind === "stackedColumn" ? SURFACE : undefined}
              strokeWidth={view.kind === "stackedColumn" ? 2 : 0}
              radius={view.kind === "stackedColumn" && index < view.series.length - 1 ? 0 : [4, 4, 0, 0]}
            />
          ))}
        </BarChart>,
      );

    case "bar":
      return container(
        <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={grid} horizontal={false} />
          <XAxis type="number" tick={tick} tickFormatter={(v: number) => compact.format(v)} axisLine={false} />
          <YAxis type="category" dataKey={x} tick={tick} width={160} tickLine={false} axisLine={{ stroke: grid }} />
          {tooltip}
          <Bar
            dataKey={view.series[0]!}
            name={view.series[0]!}
            fill={seriesColor(0)}
            maxBarSize={24}
            radius={[0, 4, 4, 0]}
          />
        </BarChart>,
      );

    case "pie":
      return container(
        <PieChart>
          {tooltip}
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Pie
            data={rows}
            dataKey={view.series[0]!}
            nameKey={x}
            innerRadius="55%"
            outerRadius="80%"
            stroke={SURFACE}
            strokeWidth={2}
            isAnimationActive={false}
          >
            {rows.map((row, index) => (
              <Cell key={String(row[x])} fill={seriesColor(index)} />
            ))}
          </Pie>
        </PieChart>,
      );

    case "scatter": {
      const y = view.series[0]!;
      return container(
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={grid} />
          <XAxis
            type="number"
            dataKey={x}
            name={x}
            tick={tick}
            tickFormatter={(v: number) => compact.format(v)}
            label={{ value: labelOf(x), position: "insideBottom", offset: -4, fill: tick.fill, fontSize: 12 }}
          />
          {valueAxis({ type: "number", dataKey: y, name: y })}
          {tooltip}
          <Scatter data={rows} fill={seriesColor(0)} stroke={SURFACE} strokeWidth={2} />
        </ScatterChart>,
      );
    }

    case "histogram": {
      const key = view.series[0]!;
      const bins = histogram(rows, key, (v) => compact.format(v));
      return container(
        <BarChart data={bins} margin={{ top: 8, right: 16, bottom: 8, left: 0 }} barCategoryGap={2}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="range" tick={tick} tickLine={false} axisLine={{ stroke: grid }} />
          <YAxis tick={tick} allowDecimals={false} axisLine={false} tickLine={false} />
          <Tooltip formatter={(value) => [String(value), "Rows"]} />
          <Bar dataKey="count" name="Rows" fill={seriesColor(0)} radius={[4, 4, 0, 0]} />
        </BarChart>,
      );
    }

    default:
      return null;
  }
}
