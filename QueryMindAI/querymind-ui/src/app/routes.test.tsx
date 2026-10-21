import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { useDashboardStore } from "@/features/dashboard/store";
import { useHistoryStore } from "@/features/history/store";
import { usePinnedStore } from "@/features/pinned/store";
import { renderRoute } from "@/test/renderRoute";
import type { Run, RunStatus } from "@/types/run";

const renderAt = renderRoute;

async function askFromHome(question: string) {
  await userEvent.type(await screen.findByLabelText("Question"), question);
  await userEvent.click(screen.getByRole("button", { name: "Generate SQL" }));
}

describe("routes", () => {
  it.each([
    ["/", "Turn questions into SQL"],
    ["/ask", "Ask a question"],
    ["/history", "History"],
    ["/dashboard", "Dashboard"],
    ["/settings", "Settings"],
    ["/admin", "Overview"],
    ["/admin/schema", "Schema"],
    ["/admin/logs", "Logs"],
    ["/admin/guardrails", "Guardrails"],
    ["/admin/model", "Model config"],
    ["/admin/okta", "Okta"],
    ["/does-not-exist", "Page not found"],
  ])("renders %s inside the layout", async (path, heading) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    expect(screen.getAllByText("QueryMind").length).toBeGreaterThan(0);
  });

  it("asks a question from Home and shows the result", async () => {
    const router = renderAt("/");
    await askFromHome("Orders by shipping method");

    expect(router.state.location.pathname).toBe("/ask");
    expect(await screen.findByRole("heading", { level: 1, name: "Orders by shipping method" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Results" })).toBeInTheDocument();
  });

  it("saves a result's chart to the dashboard and shows it there", async () => {
    const router = renderAt("/");
    await askFromHome("Orders by shipping method");

    await userEvent.click(await screen.findByRole("button", { name: "Bars" }));
    await userEvent.click(screen.getByRole("button", { name: "Save to dashboard" }));
    await userEvent.click(screen.getByRole("link", { name: /Saved · View dashboard/ }));

    expect(router.state.location.pathname).toBe("/dashboard");
    const tile = await screen.findByRole("article", { name: "Orders by shipping method" });
    expect(tile).toHaveTextContent("Orders by Shipping method");
    expect(within(tile).getByRole("button", { name: "Remove from dashboard" })).toBeInTheDocument();
    expect(useDashboardStore.getState().tiles[0]?.view.kind).toBe("bar");
  });
});

describe("home page", () => {
  beforeEach(() => {
    usePinnedStore.setState({ pinned: null });
    useHistoryStore.setState({
      history: [run("1", "Low stock products by category", "success"), run("2", "delete all orders", "blocked")],
    });
  });

  it("pins the first example questions and unpins one with its x", async () => {
    renderAt("/");
    const pinned = await screen.findByRole("region", { name: "Pinned questions" });
    expect(within(pinned).getAllByRole("listitem")).toHaveLength(4);
    expect(within(pinned).getByRole("button", { name: "Show total amount last month" })).toBeInTheDocument();

    await userEvent.click(within(pinned).getByRole("button", { name: 'Unpin "Show total amount last month"' }));
    expect(within(pinned).queryByRole("button", { name: "Show total amount last month" })).not.toBeInTheDocument();
    expect(within(pinned).getAllByRole("listitem")).toHaveLength(3);
    expect(usePinnedStore.getState().pinned).not.toContain("Show total amount last month");
  });

  it("pins a recent query", async () => {
    renderAt("/");
    const recent = await screen.findByRole("region", { name: "Recent queries" });
    await userEvent.click(within(recent).getByRole("button", { name: 'Pin "delete all orders"' }));

    const pinned = screen.getByRole("region", { name: "Pinned questions" });
    expect(within(pinned).getByRole("button", { name: "delete all orders" })).toBeInTheDocument();
    expect(within(recent).getByRole("button", { name: 'Unpin "delete all orders"' })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("filters recent queries by outcome with tabs", async () => {
    renderAt("/");
    const recent = await screen.findByRole("region", { name: "Recent queries" });
    expect(within(recent).getByRole("tab", { name: "All (2)" })).toHaveAttribute("aria-selected", "true");

    await userEvent.click(within(recent).getByRole("tab", { name: "Blocked (1)" }));
    const panel = within(recent).getByRole("tabpanel");
    expect(within(panel).getByText("delete all orders")).toBeInTheDocument();
    expect(within(panel).queryByText("Low stock products by category")).not.toBeInTheDocument();

    await userEvent.keyboard("{ArrowRight}");
    expect(within(recent).getByRole("tab", { name: "All (2)" })).toHaveAttribute("aria-selected", "true");

    await userEvent.click(within(recent).getByRole("tab", { name: "Self-healed (0)" }));
    expect(within(recent).getByText("No queries needed a retry.")).toBeInTheDocument();
  });
});

function run(id: string, question: string, status: RunStatus): Run {
  return { id, question, status, at: Date.UTC(2026, 9, 1), ms: 1, sql: "", explanation: "", columns: [], rows: [] };
}
