import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderRoute } from "@/test/renderRoute";

describe("Schema", () => {
  it("shows each database's tables and views with column details", async () => {
    renderRoute("/admin/schema");
    expect(await screen.findByRole("heading", { level: 1, name: "Schema" })).toBeInTheDocument();
    const ecommerce = screen.getByRole("region", { name: "ecommerce" });
    expect(within(ecommerce).getByText(/MySQL · 3 tables · 1 view/)).toBeInTheDocument();
    expect(within(ecommerce).getByText("ecommerce_mysql_schema.sql")).toBeInTheDocument();
    expect(within(ecommerce).getByText("View")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "returns_db" })).toHaveTextContent("rma.returns");

    const orders = within(ecommerce).getByText("orders", { selector: "span.font-mono" }).closest("article")!;
    await userEvent.click(within(orders).getByText("orders", { selector: "span.font-mono" }));
    const userId = within(orders).getByText("user_id").closest("tr")!;
    expect(userId).toHaveTextContent("BIGINT UNSIGNED");
    expect(userId).toHaveTextContent("users.user_id");
    expect(within(orders).getAllByLabelText("primary key")).toHaveLength(1);
  });

  it("filters tables and columns", async () => {
    renderRoute("/admin/schema");
    await screen.findByRole("heading", { level: 1, name: "Schema" });
    await userEvent.type(screen.getByLabelText("Filter"), "refund_method");
    expect(screen.queryByRole("region", { name: "ecommerce" })).not.toBeInTheDocument();
    const returnsDb = screen.getByRole("region", { name: "returns_db" });
    expect(within(returnsDb).getByText("refund_method")).toBeVisible(); // cards open while filtering
    expect(within(returnsDb).queryByText("rma_number")).not.toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("Filter"));
    await userEvent.type(screen.getByLabelText("Filter"), "zzz");
    expect(screen.getByText('Nothing matches "zzz".')).toBeInTheDocument();
  });
});
