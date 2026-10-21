import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RunProgress } from "@/features/ask/components/RunProgress";

describe("RunProgress", () => {
  it("shows a connecting step before any progress arrives", () => {
    render(<RunProgress question="Top products" startedAt={Date.now()} steps={[]} />);
    expect(screen.getByRole("heading", { name: "Working on “Top products”" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Progress" })).getByText("Connecting to QueryMind…")).toBeVisible();
  });

  it("lists each step with its state and announces the current one", () => {
    render(
      <RunProgress
        question="q"
        startedAt={Date.now() - 12_000}
        steps={[
          { id: "retrieve", status: "done", message: "Found 24 relevant notes" },
          { id: "execute-1-1", status: "failed", message: "ecommerce: unknown column" },
          { id: "generate-2", status: "running", message: "Rewriting the SQL to fix the error (attempt 2)" },
        ]}
      />,
    );
    const items = within(screen.getByRole("list", { name: "Progress" })).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Found 24 relevant notes",
      "ecommerce: unknown column",
      "Rewriting the SQL to fix the error (attempt 2)",
    ]);
    expect(within(items[0]!).getByLabelText("Done")).toBeInTheDocument();
    expect(within(items[1]!).getByLabelText("Failed")).toBeInTheDocument();
    expect(within(items[2]!).getByLabelText("In progress")).toBeInTheDocument();
    expect(screen.getByText("12s")).toBeInTheDocument();
  });
});
