import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { ResultGraph } from "@/features/results/components/ResultGraph";

beforeAll(() => {
  // Recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const columns = [
  { key: "category", label: "Category" },
  { key: "revenue", label: "Revenue" },
];

describe("ResultGraph", () => {
  it("offers the suitable views and switches between them", async () => {
    const rows = ["Shoes", "Hats", "Bags"].map((category, i) => ({ category, revenue: (i + 1) * 100 }));
    render(<ResultGraph columns={columns} rows={rows} />);

    expect(screen.getByRole("heading", { name: "Graph view" })).toBeInTheDocument();
    expect(screen.getByText("Revenue by Category")).toBeInTheDocument();
    const options = screen.getAllByRole("button").map((button) => button.textContent);
    expect(options).toEqual(["Columns", "Bars", "Share"]);
    expect(screen.getByRole("button", { name: "Columns" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: "Share" }));
    expect(screen.getByRole("button", { name: "Share" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Share of Revenue by Category")).toBeInTheDocument();
  });

  it("shows a single-row result as stat tiles", () => {
    render(
      <ResultGraph columns={[{ key: "total_amount", label: "Total amount" }]} rows={[{ total_amount: 502900 }]} />,
    );
    expect(screen.getByText("Total amount")).toBeInTheDocument();
    expect(screen.getByText("$502,900")).toBeInTheDocument();
  });

  it("renders nothing when there is nothing to plot", () => {
    const { container } = render(<ResultGraph columns={[{ key: "name", label: "Name" }]} rows={[{ name: "a" }]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
