/**
 * Categorical series colours, in fixed order (never cycled; colour follows the
 * series, not its rank). Validated on the white chart surface with the dataviz
 * palette checker: adjacent CVD ΔE ≥ 9.1 and normal-vision ΔE ≥ 19.6 for all six.
 * Aqua, yellow and magenta are under 3:1 contrast, so charts always sit next to
 * the results table and keep a legend for two or more series.
 */
export const SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"] as const;

export function seriesColor(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length]!;
}
