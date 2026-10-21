import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LEGACY_KEY } from "@/features/datasources/legacy";
import { renderRoute } from "@/test/renderRoute";

const stored = () => JSON.parse(localStorage.getItem("querymind-mock-datasources") ?? "[]") as { name: string }[];
const list = () => screen.getByRole("list", { name: "" });

describe("Settings (data sources)", () => {
  it("loads, edits and saves through the API", async () => {
    renderRoute("/settings");
    const name = await screen.findByLabelText("Name");
    expect(name).toHaveValue("ecommerce");

    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled(); // nothing changed yet

    await userEvent.clear(name);
    await userEvent.type(name, "shop");
    expect(screen.getByText("Unsaved")).toBeInTheDocument();
    await userEvent.click(save);

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(stored().map((s) => s.name)).toEqual(["shop"]);
    expect(screen.queryByText("Unsaved")).not.toBeInTheDocument();
  });

  it("reverts unsaved edits", async () => {
    renderRoute("/settings");
    const name = await screen.findByLabelText("Name");
    await userEvent.type(name, "-draft");
    await userEvent.click(screen.getByRole("button", { name: "Revert" }));
    expect(name).toHaveValue("ecommerce");
  });

  it("adds and deletes data sources", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderRoute("/settings");
    await screen.findByLabelText("Name");

    await userEvent.selectOptions(screen.getByLabelText("New data source type"), "dynamodb");
    await userEvent.click(screen.getByRole("button", { name: "Add data source" }));
    expect(await screen.findByText('Added "DynamoDB source 1".')).toBeInTheDocument();
    expect(screen.getByLabelText("Region")).toHaveValue("us-east-1");
    expect(stored().map((s) => s.name)).toEqual(["ecommerce", "DynamoDB source 1"]);

    await userEvent.click(screen.getByRole("button", { name: "Delete data source" }));
    expect(await screen.findByText('Deleted "DynamoDB source 1".')).toBeInTheDocument();
    expect(stored().map((s) => s.name)).toEqual(["ecommerce"]);
    confirm.mockRestore();
  });

  it("shows server errors, e.g. a duplicate name", async () => {
    renderRoute("/settings");
    await screen.findByLabelText("Name");
    await userEvent.click(screen.getByRole("button", { name: "Add data source" }));
    await screen.findByText('Added "MySQL source 2".');
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "Ecommerce");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
  });

  it("imports data sources saved in the browser by the old version", async () => {
    localStorage.setItem(
      LEGACY_KEY,
      JSON.stringify({
        state: {
          sources: [
            { name: "ecommerce", type: "mysql", connection: {}, sections: {} },
            { name: "events", type: "cassandra", connection: { contactPoints: "10.0.0.9" }, sections: {} },
          ],
        },
      }),
    );
    renderRoute("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Import" }));

    expect(await screen.findByText("Imported 1 data source. Skipped existing: ecommerce.")).toBeInTheDocument();
    expect(stored().map((s) => s.name)).toEqual(["ecommerce", "events"]);
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
    expect(within(list()).getByText("events")).toBeInTheDocument();
  });
});

describe("Settings with databases from .env", () => {
  it("labels them and saves them to settings", async () => {
    const mocks = await import("@/mocks/datasources");
    const real = mocks.listDataSources;
    const envOnly = {
      id: "env:analytics",
      origin: "env" as const,
      name: "analytics",
      type: "postgresql" as const,
      enabled: true,
      connection: { host: "bi.internal", database: "analytics" },
      sections: {},
      created_at: 0,
      updated_at: 0,
    };
    const list = vi.spyOn(mocks, "listDataSources").mockImplementation(async () => [...(await real()), envOnly]);

    renderRoute("/settings");
    await userEvent.click(await screen.findByRole("button", { name: /analytics/ }));
    expect(screen.getByText("from .env")).toBeInTheDocument();
    expect(screen.getByText(/configured in the server's .env file/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete data source" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Save to settings" }));
    expect(await screen.findByText("Saved to settings.")).toBeInTheDocument();
    expect(stored().map((s) => s.name)).toEqual(["ecommerce", "analytics"]);
    expect(screen.queryByText("from .env")).not.toBeInTheDocument();
    list.mockRestore();
  });
});
